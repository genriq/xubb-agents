"""G1 part 2 — typed acceptance (typed_v1) through the REAL engine.

Framework-scope leaves registered in docs/CONTRACTS.yaml:

  ITC-03.FW  prompt, schema descriptor and effective vocabulary agree (generated instruction)
  ITC-07.FW  capability intersection is enforced, even under FORCE
  ITC-08.FW  an empty allowed set is state-only: silence-only envelope, never an empty enum
  ITC-09.FW  the runtime mints unique ids and preserves them; producers cannot supply them
  ITC-10.FW  strict confidence input, runtime-derived provenance, public representation,
             confidence-neutral D-CR ranking
  ITC-11.FW  explicit urgency → agent override → per-type fallback; invalid explicit rejects
  ITC-12.FW  typed rejection has no domain or private-memory effects; telemetry survives
  ITC-04/05/06/13/24 typed edges (extend the G0 contracts to typed_v1)
  TYPED-SCHEMA-DERIVATION  local validation agrees with the packaged JSON Schema fixtures

The legacy_v2 path is untouched: tests/test_legacy_acceptance_g0.py still passes.
"""
import asyncio
import json
import math
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from xubb_agents import (
    AgentEngine, AgentConfigurationError, DynamicAgent, AgentContext, Blackboard,
    HostInsightCapabilities, InsightConfig,
)
from xubb_agents.core.agent import AgentConfig, BaseAgent
from xubb_agents.core.callbacks import AgentCallbackHandler
from xubb_agents.core.insight_validation import (
    HUMAN_WIRE_VALUES, IMPLEMENTED_TYPED_TYPES, TYPE_URGENCY_FALLBACK, MISSING, EffectiveTypes,
    confidence_output, resolve_urgency, rank_candidates, acceptance_decision,
    validate_typed_candidate, evaluate_typed_gate, rank_key,
)
from xubb_agents.core.models import AgentResponse, InsightType, TranscriptSegment, TriggerType, AgentInsight

from tests.test_dynamic_agent import FakeLLM, make_context, run
from tests.test_legacy_acceptance_g0 import UsageFakeLLM, Recording, FACT

FIXTURES = Path(__file__).parent / "fixtures" / "insight_contract_1.2.0"
ALL_NINE = list(HUMAN_WIRE_VALUES)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def caps_all():
    return HostInsightCapabilities(supported_types=ALL_NINE, reply_drafts=True,
                                   text_questions=True, corrections=True)


def tctx(*, principal="p-1", caps=None, turn_count=1):
    return AgentContext(
        session_id="typed", turn_count=turn_count,
        recent_segments=[TranscriptSegment(speaker="CLIENT", text="Can we keep the date?", timestamp=1.0)],
        blackboard=Blackboard(), principal_id=principal,
        insight_capabilities=caps if caps is not None else caps_all(),
    )


def tagent(result, *, insight_config=None, output_format="insight_v1", agent_id="typed_agent"):
    cfg = {"id": agent_id, "name": agent_id, "text": "You observe.", "output_format": output_format,
           "trigger_config": {"cooldown": 0}}
    if insight_config is not None:
        cfg["insight_config"] = insight_config
    agent = DynamicAgent(cfg)
    agent.llm = FakeLLM(result)
    return agent


def tengine(*agents, callbacks=None):
    engine = AgentEngine(api_key="k", insight_contract="typed_v1", callbacks=callbacks or [])
    for a in agents:
        fake = a.llm
        engine.register_agent(a)
        a.llm = fake          # register_agent injects the real client; restore the fake
    return engine


def turn(engine, ctx=None, **kw):
    ctx = ctx or tctx()
    return asyncio.run(engine.process_turn(ctx, **kw)), ctx


def codes(resp):
    return [d.code for d in resp.diagnostics]


def envelope(insight=None, **channels):
    body = {"has_insight": insight is not None, "insight": insight}
    body.update(channels)
    return body


def cand(**over):
    base = {"type": "warning", "content": "The date depends on an approval that is not scheduled.",
            "confidence": 0.8, "urgency": "now"}
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# Contract selection now works; adapter gating at registration
# ---------------------------------------------------------------------------

class TestTypedRegistration:
    def test_typed_engine_constructs_and_injects_contract(self):
        agent = tagent(envelope())
        engine = tengine(agent)
        assert engine.insight_contract == "typed_v1" and agent.insight_contract == "typed_v1"

    @pytest.mark.parametrize("schema", ["default", "custom1", "ui_control", "widget_control"])
    def test_schema_without_typed_adapter_fails_at_registration(self, schema):
        engine = AgentEngine(api_key="k", insight_contract="typed_v1")
        with pytest.raises(AgentConfigurationError, match="does not support insight_contract='typed_v1'"):
            engine.register_agent(tagent(envelope(), output_format=schema))
        assert engine.agents == []

    def test_insight_v1_is_typed_only(self):
        engine = AgentEngine(api_key="k")   # legacy
        with pytest.raises(AgentConfigurationError, match="does not support insight_contract='legacy_v2'"):
            engine.register_agent(tagent(envelope(), output_format="insight_v1"))

    @pytest.mark.parametrize("schema", ["insight_v1", "default_v2", "v2_raw"])
    def test_typed_adapters_register(self, schema):
        engine = tengine(tagent(envelope(), output_format=schema))
        assert len(engine.agents) == 1


# ---------------------------------------------------------------------------
# ITC-03.FW — generated instruction agrees with descriptor and effective set
# ---------------------------------------------------------------------------

class TestGeneratedInstruction:
    def sent_prompt(self, agent, ctx):
        run(agent.evaluate(ctx))
        return agent.llm.calls[-1]["messages"][0]["content"]

    def test_instruction_lists_exactly_the_effective_types(self):
        agent = tagent(envelope(), insight_config={"allowed_types": ["fact", "warning", "observation"]})
        tengine(agent)
        prompt = self.sent_prompt(agent, tctx())
        listed = prompt.split("must be EXACTLY one of: ")[1].split(" —")[0]
        assert listed == "fact, observation, warning"
        # no conflicting literal enum from the static instruction, and no unoffered value
        assert "suggestion" not in prompt.split("OUTPUT FORMAT")[1].split("RULES")[0]
        assert '"praise"' not in prompt and '"reply"' not in prompt

    def test_host_restriction_narrows_the_instruction(self):
        agent = tagent(envelope())
        tengine(agent)
        prompt = self.sent_prompt(agent, tctx(caps=HostInsightCapabilities(supported_types=["fact", "warning"])))
        assert prompt.split("must be EXACTLY one of: ")[1].split(" —")[0] == "fact, warning"

    def test_static_legacy_enum_is_not_sent_in_typed_mode(self):
        """NEGATIVE CONTROL: the flat schema's static instruction offers exactly the
        five legacy literals; typed mode must not send it alongside the generated one."""
        agent = tagent({"has_insight": False}, output_format="default_v2")
        tengine(agent)
        prompt = self.sent_prompt(agent, tctx())
        assert "OUTPUT FORMAT" in prompt and prompt.count("OUTPUT FORMAT") == 1
        assert "Set has_insight=true only if you have meaningful advice" not in prompt


# ---------------------------------------------------------------------------
# ITC-08.FW — empty effective set
# ---------------------------------------------------------------------------

class TestEmptySet:
    def test_state_only_agent_gets_silence_only_instruction_and_commits_state(self):
        agent = tagent(envelope(facts=[FACT]), insight_config={"allowed_types": []})
        engine = tengine(agent)
        run(agent.evaluate(tctx()))
        prompt = agent.llm.calls[-1]["messages"][0]["content"]
        assert '"has_insight": false' in prompt and "EXACTLY one of" not in prompt
        final, ctx = turn(engine)
        assert final.acceptance_by_agent[agent.config.id] == "accepted_silent"
        assert ctx.blackboard.has_fact("budget", "primary")

    def test_candidate_from_state_only_agent_is_rejected_not_relabelled(self):
        agent = tagent(envelope(cand(), facts=[FACT]), insight_config={"allowed_types": []})
        final, ctx = turn(tengine(agent))
        assert final.insights == [] and "type_not_allowed" in codes(final)
        assert final.acceptance_by_agent[agent.config.id] == "rejected"
        assert not ctx.blackboard.has_fact("budget", "primary")   # typed atomicity


# ---------------------------------------------------------------------------
# ITC-04 / ITC-05 typed edges — gates
# ---------------------------------------------------------------------------

class TestTypedGates:
    @pytest.mark.parametrize("gate", ["true", "false", 1, 0, None])
    def test_non_boolean_gate_rejects_whole_response(self, gate):
        agent = tagent({"has_insight": gate, "insight": cand(), "facts": [FACT]})
        final, ctx = turn(tengine(agent))
        assert final.insights == [] and "invalid_gate" in codes(final)
        assert final.acceptance_by_agent[agent.config.id] == "rejected"
        assert not ctx.blackboard.has_fact("budget", "primary")

    def test_missing_gate_rejects(self):
        agent = tagent({"insight": cand()})
        final, _ = turn(tengine(agent))
        assert "invalid_gate" in codes(final) and final.insights == []

    def test_true_gate_with_null_candidate_is_inconsistent(self):
        agent = tagent({"has_insight": True, "insight": None})
        final, _ = turn(tengine(agent))
        assert "inconsistent_gate" in codes(final)

    def test_false_gate_with_candidate_is_inconsistent(self):
        agent = tagent({"has_insight": False, "insight": cand()})
        final, _ = turn(tengine(agent))
        assert "inconsistent_gate" in codes(final) and final.insights == []

    def test_false_gate_preserves_state(self):
        cb = Recording()
        agent = tagent(envelope(facts=[FACT], variable_updates={"phase": "closing"}))
        final, ctx = turn(tengine(agent, callbacks=[cb]))
        assert final.acceptance_by_agent[agent.config.id] == "accepted_silent"
        assert ctx.blackboard.get_var("phase") == "closing" and cb.validation == []

    def test_flat_adapter_discards_placeholders_under_false_gate(self):
        agent = tagent({"has_insight": False, "type": "warning", "content": "", "facts": [FACT]},
                       output_format="default_v2")
        final, ctx = turn(tengine(agent))
        assert final.acceptance_by_agent[agent.config.id] == "accepted_silent"
        assert ctx.blackboard.has_fact("budget", "primary")

    def test_root_adapter_presence_gate(self):
        silent = tagent({"state_snapshot": {"phase": "x"}}, output_format="v2_raw")
        final, ctx = turn(tengine(silent))
        assert final.acceptance_by_agent[silent.config.id] == "accepted_silent"
        assert ctx.blackboard.get_var("phase") == "x"
        bad = tagent({"insight": "a string"}, output_format="v2_raw")
        final, _ = turn(tengine(bad))
        assert "invalid_gate" in codes(final)


# ---------------------------------------------------------------------------
# ITC-06 typed — exact type values, no relabel
# ---------------------------------------------------------------------------

class TestTypedTypeValues:
    @pytest.mark.parametrize("label,code", [("briefing", "unknown_type"), ("Warning", "unknown_type"),
                                            ("INFORMATION", "unknown_type"), ("information", "unknown_type"),
                                            ("error", "unknown_type"), ("reply", "type_not_allowed"),
                                            ("question", "type_not_allowed"), ("correction", "type_not_allowed")])
    def test_label_rejects_whole_response(self, label, code):
        # reply/question: not in the default insight_config.allowed_types → type_not_allowed
        agent = tagent(envelope(cand(type=label), facts=[FACT]))
        final, ctx = turn(tengine(agent))
        assert final.insights == [] and code in codes(final)
        assert final.acceptance_by_agent[agent.config.id] == "rejected"
        assert not ctx.blackboard.has_fact("budget", "primary")

    def test_implemented_types_are_accepted_and_stamped(self):
        # the six ordinary purposes are in the default allowed set; reply/question
        # need explicit permission (tests/test_reply_question_g3.py)
        for value in ("fact", "observation", "suggestion", "warning", "opportunity", "praise"):
            agent = tagent(envelope(cand(type=value, urgency="soon")))
            final, _ = turn(tengine(agent))
            assert [i.type.value for i in final.insights] == [value], value
            ins = final.insights[0]
            assert ins.contract_version == "typed_v1" and ins.turn == 1 and ins.id
            assert ins.urgency == "soon" and ins.confidence_provided is True

    def test_information_emits_as_fact_on_the_wire(self):
        agent = tagent(envelope(cand(type="fact")))
        final, _ = turn(tengine(agent))
        assert final.insights[0].type is InsightType.INFORMATION
        assert json.loads(final.insights[0].model_dump_json())["type"] == "fact"


# ---------------------------------------------------------------------------
# ITC-07.FW — capability intersection, FORCE cannot bypass
# ---------------------------------------------------------------------------

class TestCapabilityIntersection:
    def test_agent_allowed_types_restrict(self):
        agent = tagent(envelope(cand(type="warning")), insight_config={"allowed_types": ["fact"]})
        final, _ = turn(tengine(agent))
        d = next(d for d in final.diagnostics if d.code == "type_not_allowed")
        assert d.classification == "not_in_agent_allowed_types"

    def test_host_without_observation_declaration_restricts(self):
        agent = tagent(envelope(cand(type="observation", urgency="whenever")))
        final, _ = turn(tengine(agent), tctx(caps=HostInsightCapabilities()))
        d = next(d for d in final.diagnostics if d.code == "type_not_allowed")
        assert d.classification == "not_supported_by_host"

    def test_force_does_not_bypass(self):
        """NEGATIVE CONTROL: FORCE is an execution trigger, not authorization."""
        agent = tagent(envelope(cand(type="warning")), insight_config={"allowed_types": ["fact"]})
        final, _ = turn(tengine(agent), trigger_type=TriggerType.FORCE)
        assert final.insights == [] and "type_not_allowed" in codes(final)

    def test_missing_principal_is_a_run_specific_capability_diagnostic(self):
        agent = tagent(envelope(cand(type="fact", urgency="whenever")),
                       insight_config={"allowed_types": ["fact", "reply"], "allow_reply": True})
        final, _ = turn(tengine(agent), tctx(principal=None))
        # the fact still lands; the lost capability is observable
        assert [i.type.value for i in final.insights] == ["fact"]
        d = next(d for d in final.diagnostics if d.code == "capability_unavailable")
        assert d.classification == "reply:missing_principal"
        assert final.acceptance_by_agent[agent.config.id] == "accepted"

    def test_unimplemented_interactive_type_stays_unavailable_even_when_permitted(self):
        """§15.2 gate mechanism: a release that has not implemented a type keeps it
        unavailable even when every permission holds (pinned via the pure function;
        every purpose is implemented since G3 part 2)."""
        from xubb_agents.core.insight_validation import effective_insight_types
        e = effective_insight_types(contract="typed_v1", allowed_types=list(HUMAN_WIRE_VALUES), allow_reply=True,
                                    allow_question=True, allow_correction=True, schema_supported=None,
                                    host_supported=list(HUMAN_WIRE_VALUES), host_reply_drafts=True, host_text_questions=True,
                                    host_corrections=True, principal_present=True, implemented=("fact",))
        assert "correction" not in e and e.unavailable["correction"] == "not_implemented_in_this_release"

    def test_custom_agent_is_held_to_the_same_set(self):
        class Custom(BaseAgent):
            def __init__(self):
                super().__init__(AgentConfig(name="custom", cooldown=0, trigger_types=[TriggerType.TURN_BASED],
                                             insight_config=InsightConfig(allowed_types=["fact"])))
            async def evaluate(self, context):
                return AgentResponse(insights=[self.create_insight("Budget risk ahead", type=InsightType.WARNING)],
                                     facts=[])
        agent = Custom()
        engine = AgentEngine(api_key="k", insight_contract="typed_v1"); engine.register_agent(agent)
        final, _ = turn(engine)
        assert final.insights == [] and "type_not_allowed" in codes(final)


# ---------------------------------------------------------------------------
# ITC-09.FW — identity
# ---------------------------------------------------------------------------

class TestIdentity:
    def test_ids_unique_across_agents_and_turns_and_preserved(self):
        a1 = tagent(envelope(cand()), agent_id="a1")
        a2 = tagent(envelope(cand(type="suggestion", urgency="soon")), agent_id="a2")
        engine = tengine(a1, a2)
        ids = []
        for t in (1, 2):
            final, _ = turn(engine, tctx(turn_count=t))
            for ins in final.insights:
                assert ins.turn == t and ins.contract_version == "typed_v1"
                assert json.loads(ins.model_dump_json())["id"] == ins.id
                ids.append(ins.id)
        assert len(ids) == 4 and len(set(ids)) == 4

    def test_model_supplied_identity_rejects(self):
        for key in ("id", "turn", "contract_version", "confidence_provided", "acceptance_status", "source_snapshot_id"):
            agent = tagent(envelope(cand(**{key: "forged"})))
            final, _ = turn(tengine(agent))
            d = next(d for d in final.diagnostics if d.field_path == f"insight.{key}")
            assert d.code == "invalid_field" and d.classification == "engine_owned", key
            assert final.insights == []

    def test_metadata_cannot_carry_engine_owned_provenance(self):
        agent = tagent(envelope(cand(metadata={"confidence_provided": True, "origin": "framework"})))
        final, _ = turn(tengine(agent))
        assert "invalid_metadata" in codes(final) and final.insights == []

    def test_custom_agent_cannot_mint_its_own_id(self):
        class Custom(BaseAgent):
            def __init__(self):
                super().__init__(AgentConfig(name="minter", cooldown=0, trigger_types=[TriggerType.TURN_BASED]))
            async def evaluate(self, context):
                ins = self.create_insight("Budget risk ahead", type=InsightType.WARNING)
                ins.id = "chosen-by-agent"
                return AgentResponse(insights=[ins])
        engine = AgentEngine(api_key="k", insight_contract="typed_v1"); engine.register_agent(Custom())
        final, _ = turn(engine)
        assert final.insights == []
        assert any(d.code == "invalid_field" and d.classification == "engine_owned" for d in final.diagnostics)

    def test_custom_agent_insight_is_stamped_and_provenance_unknown_is_false(self):
        class Custom(BaseAgent):
            def __init__(self):
                super().__init__(AgentConfig(name="plain", cooldown=0, trigger_types=[TriggerType.TURN_BASED]))
            async def evaluate(self, context):
                return AgentResponse(insights=[self.create_insight("Budget risk ahead", type=InsightType.WARNING)])
        engine = AgentEngine(api_key="k", insight_contract="typed_v1"); engine.register_agent(Custom())
        final, _ = turn(engine)
        ins = final.insights[0]
        assert ins.id and ins.turn == 1 and ins.contract_version == "typed_v1"
        assert ins.confidence_provided is False and ins.urgency == "now"


# ---------------------------------------------------------------------------
# ITC-10.FW — confidence
# ---------------------------------------------------------------------------

class TestConfidence:
    @pytest.mark.parametrize("value", ["0.9", True, False, 1.5, -0.1, math.nan, math.inf, [0.5]])
    def test_invalid_confidence_rejects(self, value):
        agent = tagent(envelope(cand(confidence=value), facts=[FACT]))
        final, ctx = turn(tengine(agent))
        assert "invalid_confidence" in codes(final) and final.insights == []
        assert not ctx.blackboard.has_fact("budget", "primary")

    def test_omitted_or_null_is_placeholder_not_estimate(self):
        for c in ({}, {"confidence": None}):
            agent = tagent(envelope({k: v for k, v in cand(**c).items() if not (k == "confidence" and not c)}))
            final, _ = turn(tengine(agent))
            ins = final.insights[0]
            assert ins.confidence == 1.0 and ins.confidence_provided is False

    def test_declared_estimate_is_kept_with_provenance(self):
        agent = tagent(envelope(cand(confidence=0)))
        final, _ = turn(tengine(agent))
        assert final.insights[0].confidence == 0.0 and final.insights[0].confidence_provided is True

    def test_public_serialization_numeric_plus_flag_and_legacy_projection(self):
        agent = tagent(envelope(cand(confidence=0.4)))
        final, _ = turn(tengine(agent))
        dumped = json.loads(final.insights[0].model_dump_json())
        assert dumped["confidence"] == 0.4 and dumped["confidence_provided"] is True
        legacy = final.insights[0].model_dump_legacy()
        assert set(legacy) == {"agent_id", "agent_name", "type", "content", "confidence", "expiry", "action_label", "metadata"}

    def test_default_ranking_ignores_confidence(self):
        """D-CR: the fixed total key never consults confidence; the reference cycle
        A=.9/order3, B=unknown/order2, C=.1/order1 sorts C, B, A regardless."""
        records = [{"id": "A", "urgency": "soon", "priority": 0, "merge_order": (1, 0, 3), "confidence": 0.9},
                   {"id": "B", "urgency": "soon", "priority": 0, "merge_order": (1, 0, 2), "confidence": None},
                   {"id": "C", "urgency": "soon", "priority": 0, "merge_order": (1, 0, 1), "confidence": 0.1}]
        import itertools
        for perm in itertools.permutations(records):
            assert rank_candidates(list(perm)) == ["C", "B", "A"]
        assert rank_key("now", 5, (1, 0, 0)) < rank_key("soon", 9, (1, 0, 0))
        assert rank_key("soon", 9, (1, 0, 0)) < rank_key("soon", 5, (1, 0, 0))

    def test_engine_stamps_stable_merge_order_not_arrival(self):
        a1 = tagent(envelope(cand()), agent_id="a1")
        a2 = tagent(envelope(cand(type="suggestion", urgency="soon")), agent_id="a2")
        engine = tengine(a1, a2)
        final, _ = turn(engine)
        orders = {i.agent_id: i.merge_order for i in final.insights}
        assert orders == {"a1": (1, 0, 0), "a2": (1, 1, 0)}


# ---------------------------------------------------------------------------
# ITC-11.FW — urgency precedence
# ---------------------------------------------------------------------------

class TestUrgency:
    def test_explicit_wins(self):
        agent = tagent(envelope(cand(type="fact", urgency="now")))
        final, _ = turn(tengine(agent))
        assert final.insights[0].urgency == "now"

    def test_agent_override_then_type_fallback(self):
        body = cand(type="warning"); del body["urgency"]
        with_override = tagent(envelope(body), insight_config={"default_urgency": "whenever"})
        final, _ = turn(tengine(with_override))
        assert final.insights[0].urgency == "whenever"
        without = tagent(envelope(body))
        final, _ = turn(tengine(without))
        assert final.insights[0].urgency == "now"

    def test_fallback_table_is_versioned(self):
        assert TYPE_URGENCY_FALLBACK == {"fact": "whenever", "observation": "whenever", "suggestion": "soon",
                                         "praise": "soon", "question": "soon", "warning": "now",
                                         "opportunity": "now", "reply": "now", "correction": "now"}

    @pytest.mark.parametrize("value", ["asap", "NOW", "", None, 1])
    def test_invalid_explicit_rejects_never_defaults(self, value):
        """NEGATIVE CONTROL for silent defaulting of an invalid explicit value."""
        agent = tagent(envelope(cand(urgency=value)), insight_config={"default_urgency": "soon"})
        final, _ = turn(tengine(agent))
        assert "invalid_urgency" in codes(final) and final.insights == []


# ---------------------------------------------------------------------------
# ITC-12.FW — typed atomicity
# ---------------------------------------------------------------------------

class TestTypedAtomicity:
    def test_rejection_has_no_domain_or_private_effects_but_keeps_telemetry(self):
        cb = Recording()
        agent = tagent(envelope(cand(type="briefing"), facts=[FACT], variable_updates={"phase": "x"},
                                events=["ping"], memory_updates={"seen": 1}, queue_pushes={"q": [1]}))
        usage = {"prompt_tokens": 5, "completion_tokens": 7}
        agent.llm = UsageFakeLLM(agent.llm._result, None, usage)
        engine = tengine(agent, callbacks=[cb])
        final, ctx = turn(engine)
        bb = ctx.blackboard
        assert final.insights == [] and final.events == [] and final.facts == []
        assert bb.get_var("phase") is None and not bb.has_fact("budget", "primary")
        assert bb.get_memory(agent.config.id) == {} and bb.queue_length("q") == 0
        assert agent.private_state == {}
        assert len(cb.validation) == 1 and cb.validation[0].code == "unknown_type"
        resp = run(agent.evaluate(tctx()))
        assert resp.usage == usage and resp.acceptance_status == "rejected"

    def test_invalid_domain_payload_rejects_typed_too(self):
        agent = tagent(envelope(cand(), facts="none"))
        final, _ = turn(tengine(agent))
        assert "invalid_domain_payload" in codes(final) and final.insights == []

    def test_valid_response_commits_everything(self):
        agent = tagent(envelope(cand(), facts=[FACT], variable_updates={"phase": "x"}, memory_updates={"seen": 1}))
        final, ctx = turn(tengine(agent))
        assert len(final.insights) == 1 and ctx.blackboard.get_var("phase") == "x"
        assert ctx.blackboard.get_memory(agent.config.id) == {"seen": 1}
        assert final.acceptance_by_agent[agent.config.id] == "accepted"


# ---------------------------------------------------------------------------
# Analytical fields and extension fields (strict local checks)
# ---------------------------------------------------------------------------

class TestAnalyticalFields:
    def test_unexpected_key_rejects(self):
        agent = tagent(envelope(cand(zone="A")))
        final, _ = turn(tengine(agent))
        assert any(d.code == "invalid_field" and d.field_path == "insight.zone" for d in final.diagnostics)

    def test_content_extension_fields_reject_until_negotiated(self):
        for key in ("preview", "content_format"):
            agent = tagent(envelope(cand(**{key: "plain_text" if key == "content_format" else "short"})))
            final, _ = turn(tengine(agent))
            assert "content_extension_not_enabled" in codes(final)

    def test_subtype_requires_consulting_profile_and_observation(self):
        agent = tagent(envelope(cand(type="observation", urgency="whenever", observation_kind="hypothesis",
                                     rationale="r", validation_step="v",
                                     evidence_refs=[{"kind": "segment", "ref_id": "s1", "revision": None}])))
        final, _ = turn(tengine(agent))
        assert "capability_unavailable" in codes(final) and final.insights == []
        on_warning = tagent(envelope(cand(observation_kind="implication", rationale="r")),
                            insight_config={"analysis_profile": "consulting"})
        final, _ = turn(tengine(on_warning))
        assert any(d.classification == "subtype_on_non_observation" for d in final.diagnostics)

    def test_hypothesis_needs_validation_step_and_evidence_is_unresolvable_without_catalog(self):
        base = cand(type="observation", urgency="whenever", observation_kind="hypothesis", rationale="Requests wait.")
        agent = tagent(envelope(base), insight_config={"analysis_profile": "consulting"})
        final, _ = turn(tengine(agent))
        assert any(d.classification == "hypothesis_requires_validation_step" for d in final.diagnostics)
        with_refs = tagent(envelope(dict(base, validation_step="Compare wait times.",
                                         evidence_refs=[{"kind": "segment", "ref_id": "s1", "revision": None}])),
                           insight_config={"analysis_profile": "consulting"})
        final, _ = turn(tengine(with_refs))
        assert "unknown_reference" in codes(final)   # per-agent catalog lands at G2

    def test_general_observation_without_evidence_is_accepted(self):
        agent = tagent(envelope(cand(type="observation", urgency="whenever")))
        final, _ = turn(tengine(agent))
        assert [i.type.value for i in final.insights] == ["observation"]


# ---------------------------------------------------------------------------
# Reference-compatible policy functions against the packaged amendment fixtures
# ---------------------------------------------------------------------------

class TestAmendmentFixtures:
    OPS = {"confidence_output": confidence_output, "resolve_urgency": resolve_urgency,
           "rank_candidates": rank_candidates, "acceptance_decision": acceptance_decision}

    def test_reference_policy_fixtures_reproduce(self):
        fixtures = json.loads((FIXTURES / "amendment_fixtures.json").read_text(encoding="utf-8"))["fixtures"]
        ran, skipped = 0, []
        for f in fixtures:
            fn = self.OPS.get(f["operation"])
            if fn is None:
                skipped.append(f["operation"]); continue
            args = dict(f["args"])
            if f["operation"] == "acceptance_decision":
                mode = args.pop("mode")
                call = lambda: fn(mode, **args)
            elif f["operation"] == "rank_candidates":
                call = lambda: fn([dict(r, merge_order=tuple(r["merge_order"])) for r in args["records"]])
            else:
                call = lambda: fn(**args)
            if f.get("expected_error"):
                with pytest.raises(ValueError, match=f["expected_error"]):
                    call()
            else:
                assert call() == f["expected"], f["id"]
            ran += 1
        # 19 acceptance_decision + 14 resolve_urgency + 10 confidence_output; the
        # package builds its rank_candidates permutations inline (pinned in
        # TestConfidence.test_default_ranking_ignores_confidence).
        assert ran == 43
        assert set(skipped) == {"allow_schema_fallback", "arbitrate_corrections"}   # G2 / G3


# ---------------------------------------------------------------------------
# TYPED-SCHEMA-DERIVATION — local validation agrees with the packaged JSON Schema
# ---------------------------------------------------------------------------

class TestSchemaDerivation:
    def test_local_validator_agrees_with_normalized_schema_on_every_fixture(self):
        schema = json.loads((FIXTURES / "normalized_insight.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        fixtures = json.loads((FIXTURES / "examples.json").read_text(encoding="utf-8"))["fixtures"]
        permissive = EffectiveTypes(tuple(ALL_NINE), {})
        # The provider-shaped normalized envelope REQUIRES every candidate key to be
        # present (nullable); the local contract tolerates OMISSION of these and
        # applies the documented defaults (§8.3). That is the one documented
        # divergence, and it must be the only one.
        omission_tolerant = {"confidence", "urgency", "observation_kind", "evidence_refs", "rationale",
                             "validation_step", "assumptions", "correction", "question", "metadata"}
        disagreements, tolerated = [], []
        for f in fixtures:
            env = deepcopy(f["envelope"])
            schema_valid = validator.is_valid(env)
            assert schema_valid == f["expected_valid"], f["id"]
            speak, gate_issue = evaluate_typed_gate("boolean", env.get("has_insight", MISSING), env.get("insight"))
            local_valid = gate_issue is None
            if speak:
                # the schema knows nothing about profiles, catalogs or negotiation:
                # compare at the shape level with all of those granted
                _, issues = validate_typed_candidate(env["insight"], effective=permissive,
                                                     analysis_profile="consulting",
                                                     reference_context_available=True,
                                                     content_extension_enabled=True)
                local_valid = not issues
            if local_valid == schema_valid:
                continue
            # Was omission the ONLY defect? Fill the absent optional keys with the
            # documented defaults (urgency with its resolved fallback) and re-check.
            filled = deepcopy(env)
            defaults = {"evidence_refs": [], "assumptions": [], "metadata": {}, "urgency": "whenever"}
            if isinstance(filled.get("insight"), dict):
                for key in omission_tolerant:
                    filled["insight"].setdefault(key, defaults.get(key))
            if local_valid and validator.is_valid(filled):
                tolerated.append(f["id"])
            else:
                disagreements.append(f["id"])
        assert disagreements == [], disagreements
        assert tolerated == ["missing_normalized_field"]
        assert len(fixtures) == 71
