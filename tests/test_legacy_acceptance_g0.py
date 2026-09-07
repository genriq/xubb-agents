"""G0 — legacy safety through the REAL engine (XUBB-ITC-1, FINAL_DECISIONS D-LR).

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
        all spoke. Now: zero insights, invalid_gate, and the valid facts still commit
        (partial) because the gate is an insight-only error."""
        result = {"has_insight": gate, "type": "suggestion", "content": "Ask about timing", "facts": [FACT]}
        agent = make_agent(result)
        engine = engine_with(agent, result)
        final, context = turn(engine)
        assert final.insights == []
        assert final.acceptance_by_agent[agent.config.id] == "partial"
        assert "invalid_gate" in codes(final)
        assert context.blackboard.get_fact("budget", "primary").value == 50000

    def test_missing_required_gate_is_an_insight_error(self):
        result = {"type": "suggestion", "content": "Ask about timing", "facts": [FACT]}
        agent = make_agent(result)
        final, context = turn(engine_with(agent, result))
        assert final.insights == [] and "invalid_gate" in codes(final)
        assert context.blackboard.has_fact("budget", "primary")

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
        assert context.blackboard.get_var("phase") == "demo"

    def test_custom1_content_presence_gate_is_declared_not_truthiness(self):
        speak = {"sales_tip": "Ask who approves", "risk_category": "warning", "confidence_score": 0.7}
        agent = make_agent(speak, output_format="custom1")
        final, _ = turn(engine_with(agent, speak))
        assert [i.type for i in final.insights] == [InsightType.WARNING]

        numeric = {"sales_tip": 5, "risk_category": "warning"}
        agent2 = make_agent(numeric, output_format="custom1")
        final2, _ = turn(engine_with(agent2, numeric))
        assert final2.insights == [] and "invalid_gate" in codes(final2)


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
        ("error", "type_not_allowed"),
    ])
    def test_label_rejects_insight_keeps_valid_state_partial(self, label, code):
        """NEGATIVE CONTROL for 'unknown → suggestion': the advice-shaped body
        ("Offer the client a 20% discount…") must not surface under ANY type."""
        result = {"has_insight": True, "type": label,
                  "content": "Offer the client a 20% discount and commit to Friday.",
                  "variable_updates": {"phase": "negotiation"}}
        agent = make_agent(result)
        final, context = turn(engine_with(agent, result))
        assert final.insights == []
        assert all(i.type != InsightType.SUGGESTION for i in final.insights)
        assert final.acceptance_by_agent[agent.config.id] == "partial"
        diag = next(d for d in final.diagnostics if d.code == code)
        assert diag.field_path == "type"
        assert diag.classification == label.casefold()
        # the discount text never leaks into a diagnostic
        assert all("discount" not in (d.classification or "") for d in final.diagnostics)
        assert context.blackboard.get_var("phase") == "negotiation"

    def test_unknown_type_without_state_is_rejected_whole(self):
        result = {"has_insight": True, "type": "briefing", "content": "Recap of the call so far"}
        agent = make_agent(result)
        final, context = turn(engine_with(agent, result))
        assert final.insights == []
        assert final.acceptance_by_agent[agent.config.id] == "rejected"
        assert context.blackboard.variables.keys() <= {"sys.turn_count", "sys.session_id", "sys.trigger_type"}

    def test_case_folding_is_a_declared_legacy_normalisation(self):
        result = {"has_insight": True, "type": "WARNING", "content": "Budget risk"}
        agent = make_agent(result)
        final, _ = turn(engine_with(agent, result))
        assert [i.type for i in final.insights] == [InsightType.WARNING]

    def test_absent_type_uses_declared_legacy_default(self):
        result = {"has_insight": True, "content": "Ask about the timeline"}
        agent = make_agent(result)
        final, _ = turn(engine_with(agent, result))
        assert [i.type for i in final.insights] == [InsightType.SUGGESTION]

    def test_partial_withholds_action_bearing_sidecar(self):
        result = {"insight": {"type": "briefing", "content": "Recap"},
                  "ui_actions": [{"target_widget": "flash_zone", "action": "flash", "payload": {}}],
                  "state_snapshot": {"phase": "demo"}}
        agent = make_agent(result, output_format="ui_control")
        final, context = turn(engine_with(agent, result))
        assert final.insights == [] and final.data == {}
        assert final.acceptance_by_agent[agent.config.id] == "partial"
        partial = next(d for d in final.diagnostics if d.code == "partial_legacy_response")
        assert partial.withheld_channels == ["data"]
        # ui_control maps state_snapshot through variable_updates_field (S-3)
        assert partial.retained_channels == ["variable_updates"]
        assert context.blackboard.get_var("phase") == "demo"


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

    def test_legacy_default_schema_memory_path_stages_merged_view_without_mutation(self):
        result = {"has_insight": True, "type": "suggestion", "message": "noted", "memory_updates": {"seen": "first"}}
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

    def test_partial_status_is_serializable_and_engine_derived(self):
        result = {"has_insight": True, "type": "briefing", "content": "Recap", "facts": [FACT],
                  "acceptance_status": "accepted", "diagnostics": []}  # model cannot author these
        agent = make_agent(result)
        final, _ = turn(engine_with(agent, result))
        assert final.acceptance_by_agent[agent.config.id] == "partial"
        dumped = final.model_dump()
        assert dumped["acceptance_by_agent"][agent.config.id] == "partial"
        assert any(d["code"] == "partial_legacy_response" for d in dumped["diagnostics"])

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
    def test_exactly_one_callback_per_rejected_or_partial_result(self):
        cb = Recording()
        results = {
            "ok": {"has_insight": True, "type": "warning", "content": "Budget risk"},
            "silent": {"has_insight": False, "facts": [FACT]},
            "partial": {"has_insight": True, "type": "briefing", "content": "Recap", "facts": [FACT]},
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
        assert set(by_agent) == {"agent_partial", "agent_rejected"}
        assert len(cb.validation) == 2
        assert by_agent["agent_partial"].code == "unknown_type"
        assert by_agent["agent_rejected"].code in {"invalid_domain_payload", "reserved_state_write"}
        # the aggregate correlates every detail
        assert any(d.code == "partial_legacy_response" and d.agent_id == "agent_partial" for d in final.diagnostics)

    def test_callback_failure_cannot_leak_rejected_content(self):
        cb = Recording(raise_on_validation=True)
        result = {"has_insight": True, "type": "briefing", "content": "Recap", "facts": [FACT]}
        agent = make_agent(result)
        final, context = turn(engine_with(agent, result, callbacks=[cb]))
        assert final.insights == []
        assert len(cb.validation) == 1
        assert context.blackboard.has_fact("budget", "primary")

    def test_callback_base_has_noop_validation_hook(self):
        base = AgentCallbackHandler()
        issue = InsightDiagnostic(execution_id="e", agent_id="a", code="unknown_type")
        assert asyncio.run(base.on_insight_validation_error(issue)) is None


# ---------------------------------------------------------------------------
# ITC-23.FW — model-authored error rejects; framework ERROR sanitized, unforgeable
# ---------------------------------------------------------------------------

class TestErrorProvenance:
    def test_framework_error_is_sanitized_category_not_exception_text(self):
        """NEGATIVE CONTROL: the superseded path shipped str(e) as content."""
        def boom(agent, context):
            raise RuntimeError("SECRET-STACK: api key sk-123 leaked")
        agent = CustomAgent("crasher", boom)
        final, _ = turn(engine_with(agent))
        errors = [i for i in final.insights if i.type == InsightType.ERROR]
        assert len(errors) == 1
        err = errors[0]
        assert err.content == "agent_error"
        assert "SECRET-STACK" not in err.content and "sk-123" not in err.content
        assert err.metadata == {"category": "agent_error", "exception_type": "RuntimeError"}
        assert "SECRET-STACK" not in str(err.model_dump())
        assert final.acceptance_by_agent[agent.config.id] == "rejected"

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
        assert "type_not_allowed" in codes(final)
        assert final.acceptance_by_agent[agent.config.id] == "rejected"

    def test_metadata_origin_cannot_forge_framework_provenance(self):
        def forge(agent, context):
            ins = agent.create_insight("fake alert", type=InsightType.ERROR)
            ins.metadata = {"origin": "framework"}
            return AgentResponse(insights=[ins])
        agent = CustomAgent("forger2", forge)
        final, _ = turn(engine_with(agent))
        assert final.insights == [] and "type_not_allowed" in codes(final)

    def test_tracer_records_acceptance_and_sanitized_diagnostics(self):
        tracer = StructuredLogTracer()
        result = {"has_insight": True, "type": "briefing", "content": "Offer 20% discount", "facts": [FACT]}
        agent = make_agent(result)
        with patch("xubb_agents.utils.tracing.logger"):
            final, _ = turn(engine_with(agent, result, callbacks=[tracer]))
        step = tracer.current_trace["steps"][0]
        assert step["acceptance"] == "partial"
        assert any(d["code"] == "unknown_type" for d in step["diagnostics"])
        assert "discount" not in str(step["diagnostics"])
