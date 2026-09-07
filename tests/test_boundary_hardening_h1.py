"""H1 — enforcement and identity (audit of e3dfaf1: XA-01, XA-02, XA-03, XA-07).

Framework-scope contracts registered in docs/CONTRACTS.yaml:

  BOUNDARY-UNIFIED-ACCEPTANCE  one authoritative acceptance pipeline for EVERY producer
                               (DynamicAgent staging, custom BaseAgent subclasses,
                               callback-modified responses): the candidate projection of
                               every insight is re-run through the strict validator, the
                               domain channels of the OBJECT that would commit are
                               revalidated, engine-owned public fields can never be
                               producer-set, and typed atomicity / legacy partial
                               acceptance are preserved.
  ANSWER-VISIBILITY-SCOPED     per-agent answer visibility is applied to the invocation
                               view itself — direct context, template aliases, custom
                               agents and isolated content tasks — never only to a prompt
                               shortcut.
  INTERACTIVE-PRINCIPAL-IDENTITY  interactive operations (answers, corrections) require a
                               present, matching current principal; missing identity
                               disables the operation rather than acting as a wildcard.
  TYPED-FAILURES-ARE-DIAGNOSTICS  typed-mode execution failures produce diagnostics only;
                               the sanitized ERROR card remains a legacy-only surface.
"""
import asyncio
import json
import math

import pytest

from xubb_agents import AgentEngine, AgentContext, Blackboard, DynamicAgent, HostInsightCapabilities
from xubb_agents.core.agent import AgentConfig, BaseAgent
from xubb_agents.core.callbacks import AgentCallbackHandler
from xubb_agents.core.llm import LLMResult
from xubb_agents.core.models import (
    AgentResponse, InsightType, InsightConfig, TranscriptSegment, TriggerType, PriorInsightRecord,
    InsightReferenceContext, InsightAnswer, InsightContentRequest, ContentExecutionContext, Fact, Event,
    CorrectionPayload, EvidenceRef, QuestionPayload,
)
from xubb_agents.core.insight_validation import (
    validate_answers, validate_correction_target, effective_insight_types, HUMAN_WIRE_VALUES,
)

NINE = list(HUMAN_WIRE_VALUES)


class FakeLLM:
    def __init__(self, body):
        self.body = body
        self.calls = []

    async def generate(self, model=None, messages=None, **kwargs):
        self.calls.append({"model": model, "messages": messages, **kwargs})
        return LLMResult(parsed=self.body, finish_reason="stop", transport="json_object",
                         raw_bytes=len(json.dumps(self.body).encode("utf-8")),
                         usage={"prompt_tokens": 3, "completion_tokens": 3})


class FnAgent(BaseAgent):
    """A custom agent whose evaluate() is a plain function — the producer the
    engine cannot pre-validate."""

    def __init__(self, name, fn, allowed=("warning",), profile="general", priority=0):
        cfg = InsightConfig(allowed_types=list(allowed), allow_reply="reply" in allowed,
                            allow_question="question" in allowed, allow_correction="correction" in allowed,
                            analysis_profile=profile)
        super().__init__(AgentConfig(name=name, cooldown=0, priority=priority,
                                     trigger_types=[TriggerType.TURN_BASED], insight_config=cfg))
        self.fn = fn

    async def evaluate(self, context):
        return self.fn(self, context)


def caps(**over):
    base = dict(supported_types=NINE, reply_drafts=True, text_questions=True, corrections=True, answers_shared=False)
    base.update(over)
    return HostInsightCapabilities(**base)


def ctx(*, principal="p-A", prior=None, answers=None, capabilities=None, turn_count=2):
    return AgentContext(session_id="s", turn_count=turn_count, blackboard=Blackboard(), principal_id=principal,
                        recent_segments=[TranscriptSegment(speaker="CLIENT", text="Please explain the scope.", timestamp=2.0)],
                        insight_capabilities=capabilities or caps(),
                        insight_reference_context=InsightReferenceContext(prior_insights=prior or []),
                        insight_answers=answers or [])


def engine(*agents, contract="typed_v1", callbacks=None):
    e = AgentEngine(api_key="k", insight_contract=contract, callbacks=callbacks or [])
    for a in agents:
        llm = getattr(a, "llm", None)
        e.register_agent(a)
        if isinstance(a, DynamicAgent):
            a.llm = llm
    return e


def turn(e, c=None):
    c = c or ctx()
    return asyncio.run(e.process_turn(c)), c


def codes(resp):
    return [d.code for d in resp.diagnostics]


def question_record(qid="q-1", agent_id="asker", principal="p-A"):
    return PriorInsightRecord(id=qid, session_id="s", principal_id=principal, agent_id=agent_id, type="question",
                              content="Who approves?", turn=1)


def answer(eid="e-1", qid="q-1", principal="p-A"):
    return InsightAnswer(event_id=eid, question_insight_id=qid, principal_id=principal, status="answered",
                         text="The sponsor approves.")


def prior(rid="i-1", agent_id="fixer", principal="p-A"):
    return PriorInsightRecord(id=rid, session_id="s", principal_id=principal, agent_id=agent_id, type="fact",
                              content="Approved earlier.", turn=1)


# ---------------------------------------------------------------------------
# BOUNDARY-UNIFIED-ACCEPTANCE
# ---------------------------------------------------------------------------

class TestUnifiedBoundary:
    def test_control_valid_custom_insight_is_accepted_and_stamped(self):
        def ok(a, c):
            return AgentResponse(insights=[a.create_insight("Check approval first.", type=InsightType.WARNING)],
                                 variable_updates={"phase": "x"})
        final, c = turn(engine(FnAgent("custom", ok)))
        ins = final.insights[0]
        assert ins.id and ins.turn == 2 and ins.contract_version == "typed_v1" and ins.urgency == "now"
        assert ins.confidence_provided is False and c.blackboard.get_var("phase") == "x"

    def test_custom_question_without_payload_rejects_whole_response(self):
        def bad(a, c):
            return AgentResponse(insights=[a.create_insight("Who approves?", type=InsightType.QUESTION)],
                                 variable_updates={"must_not_commit": True})
        final, c = turn(engine(FnAgent("q", bad, allowed=("question",))))
        assert final.insights == [] and final.acceptance_by_agent["q"] == "rejected"
        assert "invalid_question_contract" in codes(final) and c.blackboard.get_var("must_not_commit") is None

    def test_custom_hypothesis_needs_evidence_rationale_and_validation_step(self):
        def bad(a, c):
            ins = a.create_insight("Ownership may cause the delay.", type=InsightType.OBSERVATION)
            ins.observation_kind = "hypothesis"
            return AgentResponse(insights=[ins])
        final, _ = turn(engine(FnAgent("h", bad, allowed=("observation",), profile="consulting")))
        assert final.insights == [] and "missing_evidence" in codes(final)

    @pytest.mark.parametrize("field,value,code", [
        ("content", "", "invalid_field"), ("content", "   ", "invalid_field"),
        ("confidence", math.nan, "invalid_confidence"), ("confidence", 1.5, "invalid_confidence"),
        ("urgency", "asap", "invalid_urgency"),
        ("metadata", {"origin": "framework"}, "invalid_metadata"),
        ("metadata", "not-a-dict", "invalid_metadata"),
        ("evidence_refs", [{"kind": "segment", "ref_id": "snap:x:segment:0"}], "unknown_reference"),
        ("preview", "Short.", "content_extension_not_enabled"),
        ("content_format", "markdown", "content_extension_not_enabled"),
        ("type", "briefing", "unknown_type"),
    ])
    def test_mutated_custom_output_is_revalidated(self, field, value, code):
        def bad(a, c):
            ins = a.create_insight("Check approval first.", type=InsightType.WARNING)
            object.__setattr__(ins, field, value) if field == "type" else setattr(ins, field, value)
            return AgentResponse(insights=[ins], variable_updates={"must_not_commit": 1})
        final, c = turn(engine(FnAgent("m", bad)))
        assert final.insights == [] and final.acceptance_by_agent["m"] == "rejected"
        assert code in codes(final), codes(final)
        assert c.blackboard.get_var("must_not_commit") is None

    @pytest.mark.parametrize("field,value", [
        ("id", "mine"), ("turn", 9), ("contract_version", "typed_v1"), ("confidence_provided", True),
        ("content_contract", "long_form_v1"), ("response_depth", "detailed"),
        ("content_request_id", "r"), ("source_snapshot_id", "snap"),
    ])
    def test_engine_owned_public_fields_cannot_be_producer_set(self, field, value):
        def forge(a, c):
            ins = a.create_insight("Check approval first.", type=InsightType.WARNING)
            setattr(ins, field, value)
            return AgentResponse(insights=[ins])
        final, _ = turn(engine(FnAgent("f", forge)))
        assert final.insights == []
        assert any(d.code == "invalid_field" and d.classification == "engine_owned" and d.field_path.endswith(field)
                   for d in final.diagnostics)

    def test_finish_callback_mutation_is_caught_for_dynamic_agents_too(self):
        """The callback sees the response BEFORE the boundary; what it leaves
        behind is what gets validated — not the version staging validated."""
        class Tamper(AgentCallbackHandler):
            async def on_agent_finish(self, agent_name, response, duration):
                if response is not None and response.insights:
                    response.insights[0].content = ""
                    response.insights[0].confidence_provided = True
                    response.variable_updates["sys.turn_count"] = 99
        a = DynamicAgent({"id": "d", "name": "d", "text": "t", "output_format": "insight_v1", "trigger_config": {"cooldown": 0},
                          "insight_config": {"allowed_types": ["warning"]}})
        a.llm = FakeLLM({"has_insight": True, "insight": {"type": "warning", "content": "Budget risk ahead.",
                                                          "confidence": 0.7, "urgency": "now"}})
        final, c = turn(engine(a, callbacks=[Tamper()]))
        assert final.insights == [] and final.acceptance_by_agent["d"] == "rejected"
        assert "reserved_state_write" in codes(final)
        assert c.blackboard.get_var("sys.turn_count") == 2

    def test_staged_provenance_and_content_fields_survive_the_unified_boundary(self):
        """Control: DynamicAgent-staged runtime values are handed over privately
        and stamped by the engine — never producer-set public fields."""
        a = DynamicAgent({"id": "d", "name": "d", "text": "t", "output_format": "insight_v1", "trigger_config": {"cooldown": 0},
                          "insight_config": {"allowed_types": ["warning"]}})
        a.llm = FakeLLM({"has_insight": True, "insight": {"type": "warning", "content": "Budget risk ahead.", "urgency": "now"}})
        final, _ = turn(engine(a))
        ins = final.insights[0]
        # D-CR: missing confidence → placeholder 1.0 + provided False (not an estimate)
        assert ins.confidence_provided is False and ins.confidence == 1.0 and ins.id and ins.contract_version == "typed_v1"
        assert getattr(ins, "_staged", None) is None

    @pytest.mark.parametrize("mutate,code", [
        (lambda r: r.facts.append({"type": "budget", "key": "p", "value": 1}), "invalid_domain_payload"),
        (lambda r: r.facts.append(Fact.model_construct(type="budget", key="p", value=1, confidence=float("nan"),
                                                       source_agent="x", timestamp=1.0)), "invalid_domain_payload"),
        (lambda r: r.events.append({"name": "ping"}), "invalid_domain_payload"),
        (lambda r: r.variable_updates.update({"sys.phase": 1}), "reserved_state_write"),
        (lambda r: r.variable_updates.update({3: "x"}), "invalid_domain_payload"),
        (lambda r: r.queue_pushes.update({"q": "not-a-list"}), "invalid_domain_payload"),
        (lambda r: setattr(r, "data", ["not", "a", "dict"]), "invalid_domain_payload"),
    ])
    def test_domain_channels_are_revalidated_on_the_object_that_commits(self, mutate, code):
        def produce(a, c):
            r = AgentResponse(insights=[a.create_insight("Check approval first.", type=InsightType.WARNING)],
                              variable_updates={"good": 1})
            mutate(r)
            return r
        final, c = turn(engine(FnAgent("dom", produce)))
        assert final.acceptance_by_agent["dom"] == "rejected" and final.insights == []
        assert code in codes(final) and c.blackboard.get_var("good") is None

    def test_legacy_keeps_partial_acceptance_for_recoverable_insight_errors(self):
        """NEGATIVE CONTROL for scope creep: D-LR is untouched — a bad insight
        on legacy drops the insights and keeps valid channels (partial); a fatal
        domain error still rejects whole."""
        def recoverable(a, c):
            return AgentResponse(insights=[a.create_insight("Who approves?", type=InsightType.QUESTION)],
                                 variable_updates={"kept": 1})
        final, c = turn(engine(FnAgent("l1", recoverable), contract="legacy_v2"), ctx(capabilities=None))
        assert final.acceptance_by_agent["l1"] == "partial" and c.blackboard.get_var("kept") == 1

        def fatal(a, c):
            r = AgentResponse(insights=[a.create_insight("Budget risk", type=InsightType.WARNING)],
                              variable_updates={"kept": 1})
            r.facts.append({"type": "budget"})
            return r
        final, c = turn(engine(FnAgent("l2", fatal), contract="legacy_v2"), ctx(capabilities=None))
        assert final.acceptance_by_agent["l2"] == "rejected" and c.blackboard.get_var("kept") is None

    def test_reference_authority_comes_from_the_invocation_not_the_response(self):
        """A producer cannot vouch for its own evidence by attaching a snapshot."""
        from xubb_agents.core.models import EvidenceSnapshot, EvidenceCatalogEntry
        def vouch(a, c):
            ins = a.create_insight("Ownership may cause the delay.", type=InsightType.OBSERVATION)
            ins.observation_kind = "hypothesis"; ins.rationale = "Because."; ins.validation_step = "Ask."
            ins.evidence_refs = [EvidenceRef(kind="segment", ref_id="snap:forged:segment:0")]
            r = AgentResponse(insights=[ins])
            r.evidence_snapshot = EvidenceSnapshot(snapshot_id="forged", agent_id="v", entries=[
                EvidenceCatalogEntry(kind="segment", ref_id="snap:forged:segment:0", revision=None, excerpt="x")])
            return r
        final, _ = turn(engine(FnAgent("v", vouch, allowed=("observation",), profile="consulting")))
        assert final.insights == [] and "unknown_reference" in codes(final)
        assert "v" not in final.evidence_snapshots_by_agent

    def test_host_records_still_resolve_for_custom_agents(self):
        """Control: a custom agent citing a HOST-supplied record is accepted."""
        from xubb_agents.core.models import EvidenceCatalogEntry
        def cite(a, c):
            ins = a.create_insight("Ownership may cause the delay.", type=InsightType.OBSERVATION)
            ins.observation_kind = "hypothesis"; ins.rationale = "Minutes."; ins.validation_step = "Ask the sponsor."
            ins.evidence_refs = [EvidenceRef(kind="document", ref_id="minutes-3", revision="1")]
            return AgentResponse(insights=[ins])
        c = ctx()
        c.insight_reference_context = InsightReferenceContext(evidence=[
            EvidenceCatalogEntry(kind="document", ref_id="minutes-3", revision="1", excerpt="…", session_id="s")])
        final, _ = turn(engine(FnAgent("c", cite, allowed=("observation",), profile="consulting")), c)
        assert len(final.insights) == 1 and final.insights[0].evidence_refs[0].revision == "1"


# ---------------------------------------------------------------------------
# ANSWER-VISIBILITY-SCOPED
# ---------------------------------------------------------------------------

class TestAnswerVisibility:
    def _seen(self, shared, asker_id="asker"):
        seen = {}
        def make(name):
            def read(a, c):
                seen[name] = [x.event_id for x in c.insight_answers]
                return AgentResponse()
            return read
        asker = FnAgent("asker", make("asker"), allowed=())
        other = FnAgent("other", make("other"), allowed=())
        c = ctx(prior=[question_record(agent_id=asker_id)], answers=[answer()], capabilities=caps(answers_shared=shared))
        turn(engine(asker, other), c)
        return seen, c

    def test_unrelated_custom_agent_sees_nothing_and_the_asker_sees_its_answer(self):
        seen, c = self._seen(shared=False)
        assert seen == {"asker": ["e-1"], "other": []}
        assert [a.event_id for a in c.insight_answers] == ["e-1"]     # host list untouched

    def test_host_authorised_sharing_exposes_to_all(self):
        seen, _ = self._seen(shared=True)
        assert seen == {"asker": ["e-1"], "other": ["e-1"]}

    def test_template_alias_of_the_full_context_is_scoped_too(self):
        a = DynamicAgent({"id": "tpl", "name": "tpl", "output_format": "insight_v1", "trigger_config": {"cooldown": 0},
                          "text": "Answers visible: {{ context.insight_answers|length }} / {{ insight_answers|length }}",
                          "insight_config": {"allowed_types": ["fact"]}})
        a.llm = FakeLLM({"has_insight": False, "insight": None})
        turn(engine(a), ctx(prior=[question_record(agent_id="someone-else")], answers=[answer()]))
        system = a.llm.calls[0]["messages"][0]["content"]
        assert "Answers visible: 0 / 0" in system

    def test_isolated_content_task_view_is_scoped(self):
        seen = {}
        from tests.test_long_form_c1 import CONTENT, OPERATOR
        a = DynamicAgent({"id": "lf", "name": "lf", "output_format": "insight_v1", "trigger_config": {"cooldown": 0},
                          "text": "Answers visible: {{ context.insight_answers|length }}",
                          "insight_config": {"allowed_types": ["fact"], "content": CONTENT}})
        a.llm = FakeLLM({"has_insight": False, "insight": None})
        e = AgentEngine(api_key="k", insight_contract="typed_v1", content_limits=OPERATOR)
        llm = a.llm; e.register_agent(a); a.llm = llm
        c = ctx(prior=[question_record(agent_id="someone-else")], answers=[answer()],
                capabilities=caps(content_contracts=["long_form_v1"], content_formats=["plain_text", "markdown"],
                                  expanded_reading=True, max_content_chars=40000, max_preview_chars=280))
        c.content_execution_context = ContentExecutionContext(session_mode="active", execution_path="live_turn")

        async def go():
            return await e.start_content_request(c, "lf", InsightContentRequest(depth="detailed", request_id="r")).result()
        result = asyncio.run(go())
        assert result.status == "silent"
        assert "Answers visible: 0" in a.llm.calls[0]["messages"][0]["content"]


# ---------------------------------------------------------------------------
# INTERACTIVE-PRINCIPAL-IDENTITY
# ---------------------------------------------------------------------------

class TestPrincipalIdentity:
    def test_answer_requires_current_principal_to_match_question_and_answer(self):
        ok, issues = validate_answers([answer()], [question_record()], "s", "p-A")
        assert len(ok) == 1 and issues == []
        ok, issues = validate_answers([answer()], [question_record()], "s", "p-B")       # current ≠ question
        assert ok == [] and issues[0].classification == "principal_mismatch"
        ok, issues = validate_answers([answer(principal="p-B")], [question_record()], "s", "p-A")   # answer ≠ current
        assert ok == [] and issues[0].classification == "principal_mismatch"
        ok, issues = validate_answers([answer()], [question_record()], "s", None)        # missing identity
        assert ok == [] and issues[0].code == "missing_principal"
        ok, issues = validate_answers([answer()], [question_record(principal=None)], "s", "p-A")   # unowned record
        assert ok == [] and issues[0].classification == "principal_mismatch"

    def test_correction_requires_present_matching_principal(self):
        common = dict(prior_insights=[prior()], session_id="s", turn_count=2, agent_id="fixer")
        payload = {"target_insight_id": "i-1", "operation": "withdraw", "reason": "Unsupported."}
        assert validate_correction_target(payload, principal_id="p-A", **common) is None
        assert validate_correction_target(payload, principal_id=None, **common).code == "missing_principal"
        assert validate_correction_target(payload, principal_id="p-B", **common).classification == "principal_mismatch"
        unowned = dict(common, prior_insights=[prior(principal=None)])
        assert validate_correction_target(payload, principal_id="p-A", **unowned).classification == "principal_mismatch"

    def test_correction_capability_needs_a_principal_like_reply_and_question(self):
        base = dict(contract="typed_v1", allowed_types=NINE, allow_reply=True, allow_question=True, allow_correction=True,
                    schema_supported=None, host_supported=NINE, host_reply_drafts=True, host_text_questions=True,
                    host_corrections=True)
        assert "correction" in effective_insight_types(**base, principal_present=True)
        e = effective_insight_types(**base, principal_present=False)
        assert e.unavailable["correction"] == "missing_principal" and e.diagnostic_code_for("correction") == "capability_unavailable"

    def test_engine_rejects_a_correction_without_current_identity(self):
        def fix(a, c):
            ins = a.create_insight("Correction: it was proposed, not approved.", type=InsightType.CORRECTION)
            ins.correction = CorrectionPayload(target_insight_id="i-1", operation="replace", reason="Minutes show no approval.")
            ins.evidence_refs = [EvidenceRef(kind="insight", ref_id="i-1")]
            return AgentResponse(insights=[ins], variable_updates={"x": 1})
        final, c = turn(engine(FnAgent("fixer", fix, allowed=("fact", "correction"))), ctx(prior=[prior()], principal=None))
        assert final.insights == [] and c.blackboard.get_var("x") is None
        assert any(d.code == "capability_unavailable" and d.classification.endswith("missing_principal")
                   for d in final.diagnostics)

    def test_engine_accepts_a_correction_under_the_matching_principal(self):
        def fix(a, c):
            ins = a.create_insight("Correction: it was proposed, not approved.", type=InsightType.CORRECTION)
            ins.correction = CorrectionPayload(target_insight_id="i-1", operation="replace", reason="Minutes show no approval.")
            ins.evidence_refs = [EvidenceRef(kind="insight", ref_id="i-1")]
            return AgentResponse(insights=[ins])
        final, _ = turn(engine(FnAgent("fixer", fix, allowed=("fact", "correction"))), ctx(prior=[prior()]))
        assert [i.type for i in final.insights] == [InsightType.CORRECTION]


# ---------------------------------------------------------------------------
# TYPED-FAILURES-ARE-DIAGNOSTICS
# ---------------------------------------------------------------------------

class TestTypedFailures:
    def test_typed_exception_is_a_diagnostic_not_an_insight(self):
        def boom(a, c):
            raise ValueError("SECRET-STACK sk-123")
        final, _ = turn(engine(FnAgent("failed", boom)))
        assert final.insights == [] and final.acceptance_by_agent["failed"] == "rejected"
        d = next(d for d in final.diagnostics if d.code == "invalid_envelope")
        assert d.classification == "agent_error:ValueError" and "SECRET" not in final.model_dump_json()

    def test_every_typed_insight_has_a_human_facing_type_and_identity(self):
        def mixed(a, c):
            return AgentResponse(insights=[a.create_insight("Budget risk ahead.", type=InsightType.WARNING)])
        final, _ = turn(engine(FnAgent("ok", mixed)))
        assert all(i.type.value in HUMAN_WIRE_VALUES and i.id and i.turn == 2 for i in final.insights)

    def test_legacy_error_card_surface_is_unchanged(self):
        """NEGATIVE CONTROL: the sanitized ERROR card remains on the legacy path."""
        def boom(a, c):
            raise RuntimeError("x")
        final, _ = turn(engine(FnAgent("failed", boom), contract="legacy_v2"), ctx(capabilities=None))
        errors = [i for i in final.insights if i.type is InsightType.ERROR]
        assert len(errors) == 1 and errors[0].content == "agent_error"
        assert final.acceptance_by_agent["failed"] == "rejected"

    def test_forged_framework_error_on_an_accepted_typed_result_is_rejected(self):
        def forge(a, c):
            ins = a.create_insight("fake alert", type=InsightType.ERROR)
            ins._origin = "framework"
            return AgentResponse(insights=[ins])
        final, _ = turn(engine(FnAgent("forger", forge)))
        assert final.insights == [] and final.acceptance_by_agent["forger"] == "rejected"
