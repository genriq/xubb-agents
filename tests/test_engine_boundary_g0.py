"""Engine-boundary acceptance through the REAL engine (XUBB-ITC-1 §8.4).

3.0.0: this module was `test_engine_boundary_g0.py` and drove the `legacy_v2`
regime. The regime is gone; most of the rules it asserted are not, so the module
was migrated rather than deleted, and each surviving rule now runs against the
one contract. What changed in every case is the DISPOSITION, not the rule: the
legacy path answered an insight-only error with `partial` (reject the insight,
keep valid state); the typed path rejects the whole response (§8.4). Retired
outright, with reasons, at the foot of this file.

These are the framework-scope leaves registered in docs/CONTRACTS.yaml:

  ITC-04.FW  only an actual Boolean ``true`` authorizes a candidate
  ITC-05.FW  valid silence preserves valid state-only output
  ITC-06.FW  unknown / disallowed labels reject without relabeling
  ITC-13.FW  one rejection callback per execution result; callback failure cannot leak content
  ITC-23.FW  model-authored ``error`` rejects; framework ERROR is sanitized and unforgeable
  ITC-24.FW  legacy partial acceptance is explicit and observable; no parse-time durable mutation
  INV-4      agent-proposed ``sys.*`` writes reject the whole response at the engine boundary

Every test drives ``AgentEngine.process_turn`` (or ``DynamicAgent.evaluate``)
with a faked LLM; no network. Negative controls assert the exact prohibited
behaviours: a truthy string gate speaking, an unknown label surfacing as any
human-facing type, private state mutating before acceptance, a rejected
response touching the Blackboard, raw exception text reaching an insight.
"""
import asyncio
from unittest.mock import patch

import pytest

from xubb_agents.core.agent import AgentConfig, BaseAgent
from xubb_agents.core.blackboard import Blackboard
from xubb_agents.core.callbacks import AgentCallbackHandler
from xubb_agents.core.engine import AgentEngine
from xubb_agents.core.llm import LLMResult
from xubb_agents.core.models import (
    AgentContext, AgentResponse, InsightType, TranscriptSegment, TriggerType, InsightDiagnostic,
)
from xubb_agents.library.dynamic import DynamicAgent
from xubb_agents.utils.tracing import StructuredLogTracer

from tests.test_dynamic_agent import FakeLLM, make_agent, make_context, run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class UsageFakeLLM:
    """Fake exposing the enriched generate() path so usage survives rejection."""

    def __init__(self, parsed, category=None, usage=None):
        self._r = LLMResult(parsed=parsed, error_category=category, usage=usage)

    async def generate(self, model=None, messages=None, **kwargs):
        return self._r


class Recording(AgentCallbackHandler):
    def __init__(self, raise_on_validation=False):
        self.validation = []
        self.raise_on_validation = raise_on_validation

    async def on_insight_validation_error(self, issue):
        self.validation.append(issue)
        if self.raise_on_validation:
            raise RuntimeError("callback boom")


class CustomAgent(BaseAgent):
    """A custom BaseAgent subclass — exercises the engine boundary check."""

    def __init__(self, name, response_fn):
        super().__init__(AgentConfig(name=name, trigger_types=[TriggerType.TURN_BASED]))
        self.response_fn = response_fn

    async def evaluate(self, context):
        return self.response_fn(self, context)


def engine_with(agent, result=None, *, callbacks=None, llm=None):
    """Register `agent` and (re)inject a fake LLM AFTER registration, since
    register_agent injects the engine's real client."""
    engine = AgentEngine(api_key="test_key", callbacks=callbacks or [])
    engine.register_agent(agent)
    if isinstance(agent, DynamicAgent):
        agent.llm = llm if llm is not None else FakeLLM(result)
    return engine


def ctx(turn_count=1):
    return AgentContext(
        session_id="g0",
        recent_segments=[TranscriptSegment(speaker="CUSTOMER", text="What's the budget?", timestamp=1.0)],
        blackboard=Blackboard(),
        turn_count=turn_count,
    )


def turn(engine, context=None):
    context = context or ctx()
    return asyncio.run(engine.process_turn(context)), context


def codes(response):
    return [d.code for d in response.diagnostics]


FACT = {"type": "budget", "key": "primary", "value": 50000, "confidence": 0.9}


# ---------------------------------------------------------------------------
# ITC-04.FW — strict Boolean gates
# ---------------------------------------------------------------------------

class TestStrictBooleanGate:
    @pytest.mark.parametrize("gate", ["true", "false", "yes", 1, 0, None])
    def test_non_boolean_gate_never_speaks_and_is_reported(self, gate):
        """NEGATIVE CONTROL: under the superseded truthiness rule "true"/"false"/1
        all spoke. Now: zero insights and invalid_gate. 3.0.0 changed only the
        disposition — a malformed gate rejects the WHOLE response (§8.4), so the
        facts no longer commit. The rule the control protects is unchanged."""
        result = {"has_insight": gate, "type": "suggestion", "content": "Ask about timing", "facts": [FACT]}
        agent = make_agent(result)
        engine = engine_with(agent, result)
        final, context = turn(engine)
        assert final.insights == []
        assert final.acceptance_by_agent[agent.config.id] == "rejected"
        assert "invalid_gate" in codes(final)
        assert not context.blackboard.has_fact("budget", "primary"),             "typed rejection is whole-response: nothing commits"

    def test_missing_required_gate_is_an_insight_error(self):
        result = {"type": "suggestion", "content": "Ask about timing", "facts": [FACT]}
        agent = make_agent(result)
        final, context = turn(engine_with(agent, result))
        assert final.insights == [] and "invalid_gate" in codes(final)
        assert not context.blackboard.has_fact("budget", "primary")

    def test_boolean_true_speaks(self):
        result = {"has_insight": True, "type": "warning", "content": "Budget risk"}
        agent = make_agent(result)
        final, _ = turn(engine_with(agent, result))
        assert [i.type for i in final.insights] == [InsightType.WARNING]
        assert final.acceptance_by_agent[agent.config.id] == "accepted"
        assert final.diagnostics == []

    def test_root_presence_adapter_rejects_non_object_root(self):
        result = {"insight": "just a string", "state_snapshot": {"phase": "demo"}}
        agent = make_agent(result, output_format="v2_raw")
        final, context = turn(engine_with(agent, result))
        assert final.insights == [] and "invalid_gate" in codes(final)
        assert context.blackboard.get_var("phase") is None

    def test_a_removed_schema_is_refused_by_name_and_never_falls_back(self):
        """3.0.0, replacing the custom1 content-presence case. custom1 was the only
        shipped schema on that gate mode and is deleted — but deleting the FILE is
        not what makes it fail. `_load_schema` falls back to `default.json` for any
        name it cannot find, so without an explicit refusal an agent still
        configured for custom1 would silently register under a different envelope
        with different channels. It is refused by name, before the fallback.

        The gate MODE survives and keeps unit coverage in
        test_insight_validation.py::TestContentPresenceGate — an embedder's own
        schema may still declare it."""
        from xubb_agents.core.engine import AgentConfigurationError
        with pytest.raises(AgentConfigurationError, match="custom1"):
            make_agent({"sales_tip": "x"}, output_format="custom1")

    def test_an_unrecognised_schema_name_is_refused_too(self):
        """INVERTED IN 3.1.0 (F6). This used to assert that an unknown name kept
        resolving to `default`, so the custom1 refusal had to be scoped to that
        one identifier. That fallback WAS the defect: a typo re-homed an agent
        into a different envelope with different channels, silently. Every
        unresolved name now raises, and the message names the supported formats.
        """
        from xubb_agents.core.engine import AgentConfigurationError
        with pytest.raises(AgentConfigurationError, match="Unknown output_format"):
            make_agent({"has_insight": True, "type": "warning", "content": "x"},
                       output_format="an-embedders-own-schema")

    @pytest.mark.parametrize("value,expected", [
        (None, "output_format is null"),
        ("", "output_format is empty"),
        ("   ", "output_format is empty"),
        (7, "output_format must be a string"),
        (["insight_v1"], "output_format must be a string"),
    ])
    def test_every_other_unresolved_value_raises_with_its_own_message(self, value, expected):
        """NEGATIVE CONTROL for the resolution order: an OMITTED key is the only
        value that inherits the implicit default. Explicit null, empty,
        whitespace and non-string values are distinct errors, not silent
        synonyms for it."""
        from xubb_agents.core.engine import AgentConfigurationError
        with pytest.raises(AgentConfigurationError, match=expected):
            make_agent({"has_insight": False}, output_format=value)

    def test_an_omitted_key_inherits_the_implicit_default(self):
        from xubb_agents.core.output_format import implicit_default
        agent = DynamicAgent({"id": "implicit", "name": "implicit", "text": "t",
                              "trigger_config": {"cooldown": 0}})
        assert agent.config.output_format == implicit_default()


# ---------------------------------------------------------------------------
# ITC-05.FW — valid silence preserves valid state-only output
# ---------------------------------------------------------------------------

class TestValidSilencePreservesState:
    def test_false_gate_commits_state_with_accepted_silent_status(self):
        cb = Recording()
        result = {"has_insight": False, "facts": [FACT], "variable_updates": {"phase": "closing"},
                  "events": ["question_detected"], "memory_updates": {"seen": 1}}
        agent = make_agent(result)
        final, context = turn(engine_with(agent, result, callbacks=[cb]))
        assert final.insights == []
        assert final.acceptance_by_agent[agent.config.id] == "accepted_silent"
        assert final.diagnostics == [] and cb.validation == []
        bb = context.blackboard
        assert bb.get_fact("budget", "primary").value == 50000
        assert bb.get_var("phase") == "closing"
        assert bb.get_memory(agent.config.id) == {"seen": 1}
        assert [e.name for e in final.events] == ["question_detected"]

    def test_silence_is_distinguishable_from_rejection(self):
        """NEGATIVE CONTROL: a rejected result must not read as deliberate silence."""
        silent = {"has_insight": False}
        rejected = {"has_insight": True, "type": "briefing", "content": "Offer a 20% discount"}
        a1 = make_agent(silent); a2 = make_agent(rejected, config_extra={"id": "agent_two"})
        engine = AgentEngine(api_key="k")
        engine.register_agent(a1); engine.register_agent(a2)
        a1.llm = FakeLLM(silent); a2.llm = FakeLLM(rejected)
        final, _ = turn(engine)
        assert final.acceptance_by_agent[a1.config.id] == "accepted_silent"
        assert final.acceptance_by_agent[a2.config.id] == "rejected"


# ---------------------------------------------------------------------------
# ITC-06.FW — unknown / disallowed types reject without relabeling
# ---------------------------------------------------------------------------

class TestUnknownTypeRejectsWithoutRelabel:
    @pytest.mark.parametrize("label,code", [
        ("briefing", "unknown_type"), ("summary", "unknown_type"), ("INFORMATION", "unknown_type"),
        ("observation", "type_not_allowed"), ("reply", "type_not_allowed"),
        ("correction", "type_not_allowed"), ("question", "type_not_allowed"),
        # 3.0.0: `error` is not in the human vocabulary at all (it is
        # framework-manufactured), so a model authoring it is UNKNOWN rather than
        # recognised-and-disallowed. Legacy listed it as reserved.
        ("error", "unknown_type"),
    ])
    def test_label_rejects_the_whole_response_without_relabelling(self, label, code):
        """NEGATIVE CONTROL for 'unknown → suggestion': the advice-shaped body
        ("Offer the client a 20% discount…") must not surface under ANY type."""
        result = {"has_insight": True, "type": label,
                  "content": "Offer the client a 20% discount and commit to Friday.",
                  "variable_updates": {"phase": "negotiation"}}
        agent = make_agent(result)
        final, context = turn(engine_with(agent, result))
        assert final.insights == []
        assert all(i.type != InsightType.SUGGESTION for i in final.insights)
        # 3.0.0: whole-response rejection (§8.4) where legacy answered `partial`.
        assert final.acceptance_by_agent[agent.config.id] == "rejected"
        diag = next(d for d in final.diagnostics if d.code == code)
        assert diag.field_path == "insight.type"   # typed paths are rooted at the candidate
        if code == "unknown_type":
            # Nothing in the vocabulary matched, so the offending label IS the
            # classification — bounded, verbatim, and never the content. Legacy
            # casefolded it here; typed reports exactly what the model wrote,
            # which is what a prompt author needs to see.
            assert diag.classification == label
        else:
            # 3.0.0 improvement over the legacy echo: a recognised-but-disallowed
            # value reports WHY it is unavailable for this run, from the effective
            # set's own reason vocabulary, rather than repeating the label back.
            assert diag.classification in {"not_in_agent_allowed_types", "not_supported_by_host",
                                           "not_supported_by_schema", "not_implemented_in_this_release",
                                           "reply_not_permitted", "question_not_permitted",
                                           "correction_not_permitted", "missing_principal", "missing_history"}
        # the discount text never leaks into a diagnostic — unchanged, and the
        # point of the control
        assert all("discount" not in (d.classification or "") for d in final.diagnostics)
        assert context.blackboard.get_var("phase") is None, "nothing commits from a rejected response"

    def test_unknown_type_without_state_is_rejected_whole(self):
        result = {"has_insight": True, "type": "briefing", "content": "Recap of the call so far"}
        agent = make_agent(result)
        final, context = turn(engine_with(agent, result))
        assert final.insights == []
        assert final.acceptance_by_agent[agent.config.id] == "rejected"
        assert context.blackboard.variables.keys() <= {"sys.turn_count", "sys.session_id", "sys.trigger_type"}

    def test_a_miscased_type_is_not_silently_folded(self):
        """RETIRED-AND-INVERTED. Legacy declared case-folding as an adapter
        normalisation, so "WARNING" became a warning. Typed asks for an exact
        lowercase value and says so in the generated instruction, so the same
        input is now `unknown_type` — the engine does not guess what was meant."""
        result = {"has_insight": True, "type": "WARNING", "content": "Budget risk"}
        agent = make_agent(result)
        final, _ = turn(engine_with(agent, result))
        assert final.insights == []
        assert next(d for d in final.diagnostics if d.code == "unknown_type").classification == "WARNING"

    def test_an_absent_type_is_not_defaulted_to_suggestion(self):
        """RETIRED-AND-INVERTED. Legacy defaulted an absent type to "suggestion"
        (the `default` schema's parser did so since v1). Inventing a purpose the
        model did not state is exactly what the typed contract exists to stop."""
        result = {"has_insight": True, "content": "Ask about the timeline"}
        agent = make_agent(result)
        final, _ = turn(engine_with(agent, result))
        assert final.insights == []
        assert final.acceptance_by_agent[agent.config.id] == "rejected"

    def test_an_action_bearing_sidecar_is_not_withheld_but_rejected_whole(self):
        """RETIRED-AND-REPLACED (ITC-24). The legacy `partial` disposition kept
        valid channels while withholding the action-bearing sidecar, and reported
        which was which in `partial_legacy_response`. Typed has no partial: a bad
        insight rejects everything, so there is nothing to withhold selectively.
        The property that mattered — an unusable insight never lets ui_actions
        through — is stronger now, not weaker."""
        result = {"insight": {"type": "briefing", "content": "Recap"},
                  "ui_actions": [{"target_widget": "flash_zone", "action": "flash", "payload": {}}],
                  "state_snapshot": {"phase": "demo"}}
        agent = make_agent(result, output_format="ui_control")
        final, context = turn(engine_with(agent, result))
        assert final.insights == [] and final.data == {}
        assert final.acceptance_by_agent[agent.config.id] == "rejected"
        assert not any(d.code == "partial_legacy_response" for d in final.diagnostics)
        assert context.blackboard.get_var("phase") is None


# ---------------------------------------------------------------------------
# INV-4 / D-LR fatal rows — reserved writes and invalid domain payloads
# ---------------------------------------------------------------------------

class TestFatalRejection:
    def test_reserved_sys_write_rejects_whole_response(self):
        """A valid insight does not survive a proposed sys.* write (D-LR fatal row)."""
        result = {"has_insight": True, "type": "warning", "content": "Budget risk",
                  "variable_updates": {"sys.turn_count": 99, "phase": "x"}, "facts": [FACT]}
        agent = make_agent(result)
        final, context = turn(engine_with(agent, result))
        assert final.insights == [] and final.acceptance_by_agent[agent.config.id] == "rejected"
        assert "reserved_state_write" in codes(final)
        bb = context.blackboard
        assert bb.get_var("sys.turn_count") == 1          # engine value, untouched
        assert bb.get_var("phase") is None                 # nothing committed
        assert not bb.has_fact("budget", "primary")

    @pytest.mark.parametrize("field,value", [("facts", "none"), ("events", "none"),
                                             ("variable_updates", ["a"]), ("queue_pushes", {"q": "x"})])
    def test_invalid_domain_payload_rejects_whole_response(self, field, value):
        result = {"has_insight": True, "type": "warning", "content": "Budget risk",
                  "memory_updates": {"seen": 1}, field: value}
        agent = make_agent(result)
        final, context = turn(engine_with(agent, result))
        assert final.insights == [] and "invalid_domain_payload" in codes(final)
        assert final.acceptance_by_agent[agent.config.id] == "rejected"
        assert context.blackboard.get_memory(agent.config.id) == {}

    def test_custom_agent_reserved_write_rejected_at_boundary(self):
        def make(agent, context):
            resp = AgentResponse(insights=[agent.create_insight("hello there")])
            resp.variable_updates = {"sys.session_id": "evil", "fine": 1}
            return resp
        agent = CustomAgent("custom", make)
        final, context = turn(engine_with(agent))
        assert final.insights == [] and "reserved_state_write" in codes(final)
        assert context.blackboard.get_var("fine") is None
        assert context.blackboard.get_var("sys.session_id") == "g0"


# ---------------------------------------------------------------------------
# ITC-24.FW — partial acceptance observable; no parse-time durable mutation
# ---------------------------------------------------------------------------

class TestNoParseTimeMutation:
    def test_default_v2_memory_never_touches_private_state(self):
        """NEGATIVE CONTROL: the superseded parser did self.private_state.update()
        while parsing. Memory must reach the Blackboard only via the engine merge."""
        result = {"has_insight": False, "memory_updates": {"seen": "first"}}
        agent = make_agent(result)
        before = dict(agent.private_state)
        resp = run(agent.evaluate(make_context()))
        assert agent.private_state == before == {}
        assert resp.memory_updates == {"seen": "first"}

        final, context = turn(engine_with(agent, result))
        assert agent.private_state == {}
        assert context.blackboard.get_memory(agent.config.id) == {"seen": "first"}

    def test_default_schema_memory_path_stages_merged_view_without_mutation(self):
        """The E-3 memory channel is NOT contract-bound and is unchanged (spec §2.5).
        Only the field name moved: typed canonicalises the insight body to
        `content`, where the `default` schema's legacy parse read `message`."""
        result = {"has_insight": True, "type": "suggestion", "content": "noted", "memory_updates": {"seen": "first"}}
        agent = make_agent(result, output_format="default")
        context = make_context()
        context.shared_state[f"memory_{agent.config.id}"] = {"committed": True}
        resp = run(agent.evaluate(context))
        assert agent.private_state == {}
        assert resp.state_updates[f"memory_{agent.config.id}"] == {"committed": True, "seen": "first"}

    def test_rejected_response_writes_nothing_to_memory(self):
        result = {"has_insight": True, "type": "briefing", "content": "Recap", "facts": "none",
                  "memory_updates": {"seen": "leak"}}
        agent = make_agent(result)
        final, context = turn(engine_with(agent, result))
        assert agent.private_state == {}
        assert context.blackboard.get_memory(agent.config.id) == {}
        assert final.acceptance_by_agent[agent.config.id] == "rejected"

    def test_status_is_serializable_and_engine_derived_never_model_authored(self):
        """The rule survives; only the value changed. A model cannot author its own
        acceptance — it says "accepted" here and is overruled. 3.0.0: the overruling
        value is `rejected`, because `partial` went with the legacy disposition."""
        result = {"has_insight": True, "type": "briefing", "content": "Recap", "facts": [FACT],
                  "acceptance_status": "accepted", "diagnostics": []}  # model cannot author these
        agent = make_agent(result)
        final, _ = turn(engine_with(agent, result))
        assert final.acceptance_by_agent[agent.config.id] == "rejected"
        dumped = final.model_dump()
        assert dumped["acceptance_by_agent"][agent.config.id] == "rejected"
        assert not any(d["code"] == "partial_legacy_response" for d in dumped["diagnostics"])

    def test_invalid_envelope_is_rejected_and_usage_survives(self):
        agent = make_agent({})
        usage = {"prompt_tokens": 10, "completion_tokens": 300}
        engine = engine_with(agent, llm=UsageFakeLLM(None, "truncated", usage))
        final, _ = turn(engine)
        assert final.acceptance_by_agent[agent.config.id] == "rejected"
        assert "invalid_envelope" in codes(final)
        resp = run(agent.evaluate(make_context()))
        assert resp.usage == usage and resp.acceptance_status == "rejected"


# ---------------------------------------------------------------------------
# ITC-13.FW — one rejection callback per execution result; failures cannot leak
# ---------------------------------------------------------------------------

class TestRejectionCallback:
    def test_exactly_one_callback_per_rejected_result(self):
        cb = Recording()
        results = {
            "ok": {"has_insight": True, "type": "warning", "content": "Budget risk"},
            "silent": {"has_insight": False, "facts": [FACT]},
            "badtype": {"has_insight": True, "type": "briefing", "content": "Recap", "facts": [FACT]},
            "rejected": {"has_insight": True, "type": "warning", "content": "x y", "facts": "none",
                         "variable_updates": {"sys.a": 1}},
        }
        engine = AgentEngine(api_key="k", callbacks=[cb])
        agents = {}
        for name, result in results.items():
            agent = make_agent(result, config_extra={"id": f"agent_{name}"})
            engine.register_agent(agent)
            agent.llm = FakeLLM(result)
            agents[name] = agent
        final, _ = turn(engine)
        by_agent = {issue.agent_id: issue for issue in cb.validation}
        # ITC-13 unchanged: exactly one callback per failed execution result, and
        # none for the accepted or the silent one.
        assert set(by_agent) == {"agent_badtype", "agent_rejected"}
        assert len(cb.validation) == 2
        assert by_agent["agent_badtype"].code == "unknown_type"
        assert by_agent["agent_rejected"].code in {"invalid_domain_payload", "reserved_state_write"}
        assert not any(d.code == "partial_legacy_response" for d in final.diagnostics)

    def test_callback_failure_cannot_leak_rejected_content(self):
        cb = Recording(raise_on_validation=True)
        result = {"has_insight": True, "type": "briefing", "content": "Recap", "facts": [FACT]}
        agent = make_agent(result)
        final, context = turn(engine_with(agent, result, callbacks=[cb]))
        assert final.insights == []
        assert len(cb.validation) == 1
        # 3.0.0: the rule under test is that a THROWING callback cannot make
        # rejected content leak — unchanged. What changed is that the fact no
        # longer commits either, because typed rejection is whole-response.
        assert not context.blackboard.has_fact("budget", "primary")

    def test_callback_base_has_noop_validation_hook(self):
        base = AgentCallbackHandler()
        issue = InsightDiagnostic(execution_id="e", agent_id="a", code="unknown_type")
        assert asyncio.run(base.on_insight_validation_error(issue)) is None


# ---------------------------------------------------------------------------
# ITC-23.FW — model-authored error rejects; framework ERROR sanitized, unforgeable
# ---------------------------------------------------------------------------

class TestErrorProvenance:
    def test_a_crashing_agent_leaks_nothing_and_surfaces_no_error_card(self):
        """NEGATIVE CONTROL, migrated. Two superseded behaviours, one rule.

        The oldest path shipped ``str(e)`` as insight content — the leak this
        control exists to catch. The legacy contract sanitised it to a category
        but still let a framework-manufactured ERROR insight survive rejection and
        reach the human channel (H1 / XA-07). 3.0.0 removes that surface: a
        framework error is a DIAGNOSTIC, never an insight. The sanitisation rule
        is unchanged and still asserted — nothing about the exception may escape."""
        def boom(agent, context):
            raise RuntimeError("SECRET-STACK: api key sk-123 leaked")
        agent = CustomAgent("crasher", boom)
        final, _ = turn(engine_with(agent))
        assert [i for i in final.insights if i.type == InsightType.ERROR] == [],             "the legacy-only ERROR card went with the contract"
        assert final.acceptance_by_agent[agent.config.id] == "rejected"
        # The leak control, which is the part that matters, on the whole response.
        blob = str(final.model_dump())
        assert "SECRET-STACK" not in blob and "sk-123" not in blob

    def test_raw_exception_lives_only_in_protected_debug_channel(self):
        def boom(agent, context):
            raise ValueError("raw detail")
        agent = CustomAgent("crasher", boom)
        resp = asyncio.run(agent.process(ctx()))
        assert resp.debug_info["error"] == "raw detail"
        assert "raw detail" not in resp.model_dump_json()  # debug_info is exclude=True

    def test_agent_authored_error_insight_is_dropped_at_boundary(self):
        def fake_error(agent, context):
            resp = AgentResponse(insights=[agent.create_insight("fake system alert", type=InsightType.ERROR)])
            resp.facts = []
            return resp
        agent = CustomAgent("forger", fake_error)
        final, _ = turn(engine_with(agent))
        assert final.insights == []
        assert "unknown_type" in codes(final)
        assert final.acceptance_by_agent[agent.config.id] == "rejected"

    def test_metadata_origin_cannot_forge_framework_provenance(self):
        def forge(agent, context):
            ins = agent.create_insight("fake alert", type=InsightType.ERROR)
            ins.metadata = {"origin": "framework"}
            return AgentResponse(insights=[ins])
        agent = CustomAgent("forger2", forge)
        final, _ = turn(engine_with(agent))
        # `error` is not in the human vocabulary, so a forged one is unknown_type;
        # the forged `origin` metadata buys nothing either way.
        assert final.insights == [] and "unknown_type" in codes(final)

    def test_tracer_records_acceptance_and_sanitized_diagnostics(self):
        tracer = StructuredLogTracer()
        result = {"has_insight": True, "type": "briefing", "content": "Offer 20% discount", "facts": [FACT]}
        agent = make_agent(result)
        with patch("xubb_agents.utils.tracing.logger"):
            final, _ = turn(engine_with(agent, result, callbacks=[tracer]))
        step = tracer.current_trace["steps"][0]
        assert step["acceptance"] == "rejected"
        assert any(d["code"] == "unknown_type" for d in step["diagnostics"])
        assert "discount" not in str(step["diagnostics"])
