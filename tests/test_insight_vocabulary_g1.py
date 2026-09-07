"""G1 part 1 — vocabulary, alias, contract selection, insight_config, capabilities.

Framework-scope leaves registered in docs/CONTRACTS.yaml:

  ITC-01.FW  exactly nine human-facing values; ERROR excluded
  ITC-02.FW  INFORMATION aliases FACT: identity, canonical name, "fact" wire value,
             10 unique members / 11 names, labels from an explicit map
  ITC-14.FW  trusted context extensions (principal_id, insight_capabilities) survive
             both phases unchanged
  INSIGHT-CONTRACT-SELECTION   legacy_v2 default; typed_v1 fails closed; junk rejected
  INSIGHT-CONFIG-LOAD-TIME     per-agent insight_config validated at construction and
             registration; contradictions fail before any registry mutation

Everything here is inert on the wire: no behaviour of the legacy_v2 path changes.
"""
import asyncio
import enum
import json
import re
from pathlib import Path

import pytest

import xubb_agents
from xubb_agents import (
    AgentEngine, AgentConfigurationError, DynamicAgent, AgentContext, Blackboard,
    HUMAN_INSIGHT_TYPES, INSIGHT_TYPE_LABELS, InsightConfig, HostInsightCapabilities,
)
from xubb_agents.core.agent import AgentConfig, BaseAgent
from xubb_agents.core.insight_validation import (
    HUMAN_WIRE_VALUES, LEGACY_HUMAN_TYPES, RESERVED_WIRE_VALUES, INSIGHT_CONTRACTS,
    effective_insight_types,
)
from xubb_agents.core.models import (
    AgentResponse, InsightType, TranscriptSegment, TriggerType, AgentInsight,
)

from tests.test_dynamic_agent import FakeLLM


# ---------------------------------------------------------------------------
# ITC-01.FW / ITC-02.FW — vocabulary and alias
# ---------------------------------------------------------------------------

class TestVocabulary:
    def test_exactly_nine_human_values_error_excluded(self):
        values = [t.value for t in HUMAN_INSIGHT_TYPES]
        assert values == ["fact", "observation", "suggestion", "warning", "opportunity",
                          "praise", "reply", "correction", "question"]
        assert len(set(values)) == 9
        assert "error" not in values
        assert InsightType.ERROR not in HUMAN_INSIGHT_TYPES

    def test_validation_module_mirrors_the_enum(self):
        assert HUMAN_WIRE_VALUES == tuple(t.value for t in HUMAN_INSIGHT_TYPES)
        assert set(RESERVED_WIRE_VALUES) == ({"error"} | set(HUMAN_WIRE_VALUES)) - set(LEGACY_HUMAN_TYPES)

    def test_no_unrestricted_enum_iteration_in_type_offering_code(self):
        """NEGATIVE CONTROL for 'just iterate the enum': iteration includes ERROR and
        would offer it to a model."""
        assert InsightType.ERROR in list(InsightType)
        assert InsightType.ERROR not in HUMAN_INSIGHT_TYPES


class TestInformationAlias:
    def test_alias_identity_value_and_canonical_name(self):
        assert InsightType.INFORMATION is InsightType.FACT
        assert InsightType.INFORMATION.value == "fact"
        assert InsightType.INFORMATION.name == "FACT"
        assert InsightType("fact") is InsightType.INFORMATION

    def test_ten_unique_members_eleven_names(self):
        assert len(list(InsightType)) == 10
        assert len(InsightType.__members__) == 11
        assert InsightType.__members__["INFORMATION"] is InsightType.FACT

    def test_enum_is_not_decorated_unique(self):
        """@unique would raise at class creation on the alias — so its absence is
        proven by the alias existing at all; pin it explicitly."""
        with pytest.raises(ValueError):
            enum.unique(InsightType)

    def test_serialization_keeps_fact_on_the_wire(self):
        ins = AgentInsight(agent_id="a", agent_name="a", type=InsightType.INFORMATION, content="datum")
        assert json.loads(ins.model_dump_json())["type"] == "fact"
        assert AgentInsight(agent_id="a", agent_name="a", type="fact", content="datum").type is InsightType.INFORMATION

    def test_display_label_comes_from_explicit_map_not_name(self):
        assert INSIGHT_TYPE_LABELS[InsightType.INFORMATION] == "Information"
        assert INSIGHT_TYPE_LABELS[InsightType.FACT] == "Information"   # same key
        assert InsightType.INFORMATION.name != "INFORMATION"
        assert set(INSIGHT_TYPE_LABELS) == set(InsightType)

    def test_future_information_wire_value_is_not_accepted(self):
        with pytest.raises(ValueError):
            InsightType("information")


# ---------------------------------------------------------------------------
# INSIGHT-CONTRACT-SELECTION
# ---------------------------------------------------------------------------

class TestContractSelection:
    def test_default_is_legacy_v2(self):
        assert AgentEngine(api_key="k").insight_contract == "legacy_v2"
        assert INSIGHT_CONTRACTS == ("legacy_v2", "typed_v1")

    def test_typed_v1_is_selectable_and_injected(self):
        """G1 part 2: typed acceptance exists, so typed_v1 constructs; the engine
        injects the contract into every registered agent (never silently legacy)."""
        engine = AgentEngine(api_key="k", insight_contract="typed_v1")
        assert engine.insight_contract == "typed_v1"
        agent = dyn()
        engine.register_agent(agent)
        assert agent.insight_contract == "typed_v1"

    @pytest.mark.parametrize("value", ["legacy", "typed", "", None, 2])
    def test_unknown_contract_is_a_value_error(self, value):
        with pytest.raises(ValueError):
            AgentEngine(api_key="k", insight_contract=value)


# ---------------------------------------------------------------------------
# INSIGHT-CONFIG-LOAD-TIME
# ---------------------------------------------------------------------------

def dyn(insight_config=None, agent_id="a1"):
    cfg = {"id": agent_id, "name": agent_id, "text": "t", "output_format": "default_v2",
           "trigger_config": {"cooldown": 0}}
    if insight_config is not None:
        cfg["insight_config"] = insight_config
    return DynamicAgent(cfg)


class TestInsightConfig:
    def test_defaults_are_the_six_ordinary_purposes(self):
        cfg = InsightConfig()
        assert cfg.allowed_types == ["fact", "observation", "suggestion", "warning", "opportunity", "praise"]
        assert (cfg.allow_reply, cfg.allow_question, cfg.allow_correction) == (False, False, False)
        assert cfg.analysis_profile == "general" and cfg.default_urgency is None
        assert dyn().config.insight_config == cfg
        assert AgentConfig(name="x").insight_config == cfg

    def test_empty_allowed_types_is_state_only_not_all(self):
        cfg = InsightConfig(allowed_types=[])
        assert cfg.allowed_types == []
        eff = effective_insight_types(contract="typed_v1", allowed_types=[], allow_reply=False,
                                      allow_question=False, allow_correction=False, schema_supported=None,
                                      host_supported=list(HUMAN_WIRE_VALUES), host_reply_drafts=True,
                                      host_text_questions=True, host_corrections=True, principal_present=True)
        assert eff.types == ()

    @pytest.mark.parametrize("bad", [{"allowed_types": ["fact", "briefing"]},
                                     {"allowed_types": ["fact", "fact"]},
                                     {"allowed_types": ["INFORMATION"]},
                                     {"allowed_types": ["error"]},
                                     {"analysis_profile": "legal"},
                                     {"default_urgency": "asap"},
                                     {"allowed_typo": ["fact"]}])
    def test_malformed_config_fails_at_construction(self, bad):
        with pytest.raises(ValueError):
            InsightConfig(**bad)
        with pytest.raises(AgentConfigurationError):
            dyn(bad)

    def test_non_object_config_fails_at_construction(self):
        with pytest.raises(AgentConfigurationError, match="must be an object"):
            dyn("consulting")

    @pytest.mark.parametrize("cfg,fragment", [
        ({"allowed_types": ["fact", "reply"]}, "allow_reply is false"),
        ({"allow_reply": True}, "not in allowed_types"),
        ({"allowed_types": ["question"], "allow_question": False}, "allow_question is false"),
        ({"allow_correction": True}, "never implicitly expand"),
    ])
    def test_contradiction_fails_registration_before_mutation(self, cfg, fragment):
        """Flags never expand allowed_types and a listed interactive type needs its
        flag; the engine refuses the agent and touches nothing."""
        engine = AgentEngine(api_key="k")
        agent = dyn(cfg)
        with pytest.raises(AgentConfigurationError, match=re.escape(fragment)):
            engine.register_agent(agent)
        assert engine.agents == [] and agent.llm is None

    def test_consistent_interactive_config_registers(self):
        agent = dyn({"allowed_types": ["fact", "reply", "question"], "allow_reply": True, "allow_question": True})
        engine = AgentEngine(api_key="k")
        engine.register_agent(agent)
        assert engine.agents == [agent]

    def test_replace_agents_is_all_or_nothing_on_contradiction(self):
        engine = AgentEngine(api_key="k")
        good = dyn(agent_id="good")
        engine.register_agent(good)
        bad = dyn({"allow_reply": True}, agent_id="bad")
        with pytest.raises(AgentConfigurationError, match="all-or-nothing"):
            engine.replace_agents([dyn(agent_id="new_good"), bad])
        assert [a.config.id for a in engine.agents] == ["good"]


# ---------------------------------------------------------------------------
# Effective type set (§7.2) — pure function, exercised ahead of typed enforcement
# ---------------------------------------------------------------------------

def eff(**overrides):
    """Pure §7.2 intersection with the release's implementation gate LIFTED
    (implemented=all nine) so the permission semantics are tested on their own;
    the gate itself is pinned in test_release_implementation_gate."""
    base = dict(contract="typed_v1",
                allowed_types=list(HUMAN_WIRE_VALUES),
                allow_reply=True, allow_question=True, allow_correction=True,
                schema_supported=None,
                host_supported=list(HUMAN_WIRE_VALUES),
                host_reply_drafts=True, host_text_questions=True, host_corrections=True,
                principal_present=True, implemented=HUMAN_WIRE_VALUES)
    base.update(overrides)
    return effective_insight_types(**base)


class TestEffectiveTypes:
    def test_legacy_contract_is_the_host_safe_five(self):
        e = eff(contract="legacy_v2")
        assert set(e.types) == set(LEGACY_HUMAN_TYPES)
        assert e.unavailable["observation"] == "typed_contract_required"

    def test_full_permissions_yield_all_nine_in_canonical_order(self):
        assert eff().types == HUMAN_WIRE_VALUES

    def test_release_implementation_gate_keeps_interactive_types_unavailable(self):
        """§15.2: a type existing in the enum does not make it available before its
        supporting path exists. The default gate (G1 part 2) implements the six
        ordinary purposes; reply/correction/question wait for G3."""
        from xubb_agents.core.insight_validation import IMPLEMENTED_TYPED_TYPES
        base = dict(contract="typed_v1", allowed_types=list(HUMAN_WIRE_VALUES),
                    allow_reply=True, allow_question=True, allow_correction=True, schema_supported=None,
                    host_supported=list(HUMAN_WIRE_VALUES), host_reply_drafts=True, host_text_questions=True,
                    host_corrections=True, principal_present=True)
        e = effective_insight_types(**base)
        assert e.types == HUMAN_WIRE_VALUES                               # all nine since G3 part 2
        assert set(IMPLEMENTED_TYPED_TYPES) == set(HUMAN_WIRE_VALUES)
        # the gate mechanism itself still works when a release narrows it
        narrowed = effective_insight_types(**base, implemented=("fact",))
        assert narrowed.types == ("fact",) and narrowed.unavailable["reply"] == "not_implemented_in_this_release"

    def test_intersection_with_schema_and_host(self):
        e = eff(schema_supported=["fact", "warning", "reply"], host_supported=["fact", "reply"])
        assert e.types == ("fact", "reply")
        assert e.unavailable["warning"] == "not_supported_by_host"
        assert e.unavailable["suggestion"] == "not_supported_by_schema"

    def test_host_without_observation_declaration_does_not_get_it(self):
        e = eff(host_supported=list(LEGACY_HUMAN_TYPES))
        assert "observation" not in e and e.unavailable["observation"] == "not_supported_by_host"

    def test_reply_requires_flag_host_and_principal(self):
        assert "reply" in eff()
        assert eff(allow_reply=False).unavailable["reply"] == "reply_not_permitted"
        assert eff(host_reply_drafts=False).unavailable["reply"] == "reply_not_permitted"
        assert eff(principal_present=False).unavailable["reply"] == "missing_principal"
        assert eff(principal_present=False).unavailable["question"] == "missing_principal"

    def test_correction_requires_flag_and_host(self):
        assert eff(host_corrections=False).unavailable["correction"] == "correction_not_permitted"
        assert eff(allow_correction=False).unavailable["correction"] == "correction_not_permitted"

    def test_flags_never_expand_allowed_types(self):
        """NEGATIVE CONTROL: allow_reply=True with reply absent from allowed_types
        must not make reply effective."""
        e = eff(allowed_types=["fact"], allow_reply=True)
        assert e.types == ("fact",) and e.unavailable["reply"] == "not_in_agent_allowed_types"

    def test_engine_helper_uses_legacy_contract_and_context(self):
        engine = AgentEngine(api_key="k")
        agent = dyn({"allowed_types": ["fact", "reply"], "allow_reply": True})
        engine.register_agent(agent)
        ctx = AgentContext(session_id="s", recent_segments=[], principal_id="p1",
                           insight_capabilities=HostInsightCapabilities(supported_types=list(HUMAN_WIRE_VALUES), reply_drafts=True))
        e = engine.effective_insight_types(agent, ctx)
        assert set(e.types) == set(LEGACY_HUMAN_TYPES)      # legacy contract wins for now
        assert engine.effective_insight_types(agent).types == e.types


# ---------------------------------------------------------------------------
# HostInsightCapabilities defaults and validation
# ---------------------------------------------------------------------------

class TestHostCapabilities:
    def test_safe_defaults(self):
        caps = HostInsightCapabilities()
        assert caps.supported_types == ["suggestion", "warning", "opportunity", "fact", "praise"]
        assert not (caps.reply_drafts or caps.text_questions or caps.corrections or caps.expanded_reading)
        assert caps.correction_agent_policy == "own_only" and caps.content_contracts == []
        assert AgentContext(session_id="s", recent_segments=[]).insight_capabilities == caps
        assert AgentContext(session_id="s", recent_segments=[]).principal_id is None

    @pytest.mark.parametrize("bad", [{"supported_types": ["error"]}, {"supported_types": ["briefing"]},
                                     {"content_contracts": ["long_form_v1"]},
                                     {"content_contracts": ["long_form_v1"], "max_content_chars": 0, "max_preview_chars": 10},
                                     {"unknown_flag": True}])
    def test_invalid_declarations_fail(self, bad):
        with pytest.raises(ValueError):
            HostInsightCapabilities(**bad)


# ---------------------------------------------------------------------------
# ITC-14.FW — trusted context extensions survive both phases
# ---------------------------------------------------------------------------

class Capture(BaseAgent):
    def __init__(self, name, emit_event=False, subscribed=None):
        super().__init__(AgentConfig(name=name, cooldown=0,
                                     trigger_types=[TriggerType.TURN_BASED, TriggerType.EVENT],
                                     subscribed_events=subscribed))
        self.seen = []
        self.emit_event = emit_event

    async def evaluate(self, context):
        self.seen.append((context.phase, context.principal_id, context.insight_capabilities.model_copy(deep=True)))
        resp = AgentResponse()
        if self.emit_event:
            from xubb_agents.core.models import Event
            resp.events.append(Event(name="ping", payload={}, source_agent=self.config.id, timestamp=1.0))
        return resp


class TestContextPropagation:
    def test_principal_and_capabilities_reach_phase1_and_phase2_unchanged(self):
        caps = HostInsightCapabilities(supported_types=list(HUMAN_WIRE_VALUES), reply_drafts=True, corrections=True)
        ctx = AgentContext(session_id="s", recent_segments=[TranscriptSegment(speaker="C", text="hi", timestamp=1.0)],
                           blackboard=Blackboard(), principal_id="principal-42", insight_capabilities=caps)
        engine = AgentEngine(api_key="k")
        p1 = Capture("p1", emit_event=True)
        p2 = Capture("p2", subscribed=["ping"])
        engine.register_agent(p1); engine.register_agent(p2)
        asyncio.run(engine.process_turn(ctx))
        phases = {phase: (pid, c) for agent in (p1, p2) for phase, pid, c in agent.seen}
        assert set(phases) == {1, 2}
        for phase, (pid, seen_caps) in phases.items():
            assert pid == "principal-42"
            assert seen_caps == caps

    def test_phase_copy_cannot_mutate_the_host_declaration(self):
        """NEGATIVE CONTROL: an agent mutating its phase copy must not alter the
        host-owned declaration on the live context (frozen per run)."""
        class Mutator(BaseAgent):
            def __init__(self):
                super().__init__(AgentConfig(name="m", trigger_types=[TriggerType.TURN_BASED]))
            async def evaluate(self, context):
                context.insight_capabilities.supported_types.append("reply")
                context.insight_capabilities.reply_drafts = True
                return AgentResponse()
        ctx = AgentContext(session_id="s", recent_segments=[], blackboard=Blackboard())
        engine = AgentEngine(api_key="k"); engine.register_agent(Mutator())
        asyncio.run(engine.process_turn(ctx))
        assert ctx.insight_capabilities == HostInsightCapabilities()


# ---------------------------------------------------------------------------
# ITC-03 groundwork (not registered): descriptors agree with instruction text
# ---------------------------------------------------------------------------

class TestDescriptorInstructionAgreement:
    SCHEMAS = Path(xubb_agents.__file__).parent / "library" / "schemas"

    @pytest.mark.parametrize("name", ["default", "default_v2", "v2_raw", "ui_control"])
    def test_descriptor_types_match_the_types_the_instruction_offers(self, name):
        data = json.loads((self.SCHEMAS / f"{name}.json").read_text(encoding="utf-8"))
        offered = set(re.findall(r'"(suggestion|warning|opportunity|fact|praise|observation|reply|correction|question|error)"',
                                 data["instruction"]))
        assert offered == set(data["descriptor"]["supported_insight_types"]), name
        assert "error" not in data["descriptor"]["supported_insight_types"]

    def test_shipped_descriptors_declare_their_contracts_honestly(self):
        """Typed adapters exist for exactly insight_v1 (typed-only), default_v2 and
        v2_raw; every other shipped schema is legacy-only. Legacy offerings never
        exceed the five legacy values; typed offerings are the nine purposes."""
        typed = {"insight_v1": ["typed_v1"], "default_v2": ["legacy_v2", "typed_v1"], "v2_raw": ["legacy_v2", "typed_v1"]}
        for path in self.SCHEMAS.glob("*.json"):
            d = json.loads(path.read_text(encoding="utf-8"))["descriptor"]
            assert d["supported_contracts"] == typed.get(path.stem, ["legacy_v2"]), path.name
            assert set(d["supported_insight_types"]) <= set(LEGACY_HUMAN_TYPES), path.name
            if path.stem in typed:
                assert tuple(d["typed_supported_insight_types"]) == HUMAN_WIRE_VALUES, path.name
                assert d["typed_adapter"] in ("insight_v1", "flat_v2", "root_v2"), path.name
