# Verbatim copy of the independent audit's proposed regression suite for commit
# e3dfaf114ea723bfeead6f640e07b75959a9572f (audit bundle README.md / AUDIT_SUMMARY.json,
# review date 2026-09-07; source sha256 f9409372b9475611c4f2fb37e107309d6ed370f3cb6db114610825e2c7a6f7ea).
# Assertions are unchanged. Adopted into the suite by hardening increments H1 (14 cases)
# and H2 (5 cases) as the acceptance gate for the audited defects.

"""Proposed contract regressions for xubb-agents e3dfaf1.

These tests were authored from the inspected source and syntax-checked, NOT run
against the repository in this audit environment. They assert the intended
contract, not the current buggy behavior, and may therefore fail on that commit.
They make no real model calls. Run from a checked-out repository with its dev
requirements installed; see README.md in this audit bundle.
"""
import asyncio
import json
import math
from typing import Callable

import pytest
from pydantic import ValidationError

from xubb_agents import AgentEngine, AgentContext, Blackboard, DynamicAgent
from xubb_agents.core.agent import AgentConfig, BaseAgent
from xubb_agents.core.llm import LLMResult
from xubb_agents.core.models import (
    AgentResponse, InsightType, InsightConfig, HostInsightCapabilities,
    TranscriptSegment, TriggerType, PriorInsightRecord, InsightReferenceContext,
    InsightAnswer, InsightContentRequest, ContentExecutionContext, ContentProfile,
)
from xubb_agents.core.insight_validation import validate_answers, validate_correction_target

HUMAN = ["fact", "observation", "suggestion", "warning", "opportunity", "praise",
         "reply", "correction", "question"]


class FunctionAgent(BaseAgent):
    def __init__(self, name: str, fn: Callable, allowed=("warning",), profile="general"):
        cfg = InsightConfig(
            allowed_types=list(allowed), allow_reply="reply" in allowed,
            allow_question="question" in allowed, allow_correction="correction" in allowed,
            analysis_profile=profile,
        )
        super().__init__(AgentConfig(name=name, cooldown=0,
                                   trigger_types=[TriggerType.TURN_BASED], insight_config=cfg))
        self.fn = fn

    async def evaluate(self, context):
        return self.fn(self, context)


def context(principal="principal-A", references=None, answers=None, capabilities=None):
    return AgentContext(
        session_id="audit-session", principal_id=principal, turn_count=2,
        recent_segments=[TranscriptSegment(speaker="client", text="Please explain the scope.", timestamp=2.0)],
        blackboard=Blackboard(),
        insight_capabilities=capabilities or HostInsightCapabilities(
            supported_types=HUMAN, reply_drafts=True, text_questions=True,
            corrections=True, answers_shared=False),
        insight_reference_context=references or InsightReferenceContext(),
        insight_answers=answers or [],
    )


def run_turn(agent, ctx=None):
    ctx = ctx or context()
    engine = AgentEngine(api_key="audit-not-a-real-key", insight_contract="typed_v1")
    engine.register_agent(agent)
    return asyncio.run(engine.process_turn(ctx)), ctx


def prior_question():
    return PriorInsightRecord(id="question-1", session_id="audit-session", principal_id="principal-A",
                              agent_id="owner", type="question", content="Who approves?", turn=1)


def valid_answer():
    return InsightAnswer(event_id="answer-1", question_insight_id="question-1", principal_id="principal-A",
                         status="answered", text="The executive sponsor approves.")


def test_control_valid_custom_warning_still_works():
    def result(a, c):
        return AgentResponse(insights=[a.create_insight("Check approval first.", type=InsightType.WARNING)])
    output, _ = run_turn(FunctionAgent("control", result))
    assert len(output.insights) == 1 and output.insights[0].id


def test_custom_question_without_payload_rejects_whole_response():
    def result(a, c):
        return AgentResponse(insights=[a.create_insight("Who approves?", type=InsightType.QUESTION)],
                             variable_updates={"should_not_commit": True})
    output, ctx = run_turn(FunctionAgent("missing_question", result, allowed=("question",)))
    assert output.insights == []
    assert output.acceptance_by_agent["missing_question"] == "rejected"
    assert ctx.blackboard.get_var("should_not_commit") is None


def test_custom_hypothesis_requires_evidence_and_validation_step():
    def result(a, c):
        insight = a.create_insight("Approval ownership may cause the delay.", type=InsightType.OBSERVATION)
        insight.observation_kind = "hypothesis"
        return AgentResponse(insights=[insight])
    output, _ = run_turn(FunctionAgent("hypothesis", result, allowed=("observation",), profile="consulting"))
    assert output.insights == []
    assert output.acceptance_by_agent["hypothesis"] == "rejected"


@pytest.mark.parametrize("field,value", [
    ("content", ""), ("confidence", math.nan), ("urgency", "asap"),
    ("metadata", {"origin": "framework"}),
    ("confidence_provided", True), ("content_contract", "long_form_v1"),
])
def test_engine_revalidates_mutated_custom_outputs(field, value):
    def result(a, c):
        insight = a.create_insight("Check approval first.", type=InsightType.WARNING)
        setattr(insight, field, value)  # Deliberately bypass construction-time validation.
        return AgentResponse(insights=[insight], variable_updates={"must_not_commit": 1})
    output, ctx = run_turn(FunctionAgent("mutated", result))
    assert output.insights == []
    assert output.acceptance_by_agent["mutated"] == "rejected"
    assert ctx.blackboard.get_var("must_not_commit") is None


def test_answer_not_exposed_through_unrelated_agent_context():
    seen = []
    def read(a, c):
        seen.extend(x.event_id for x in c.insight_answers)
        return AgentResponse()
    ctx = context(references=InsightReferenceContext(prior_insights=[prior_question()]),
                  answers=[valid_answer()])
    run_turn(FunctionAgent("unrelated", read, allowed=()), ctx)
    assert seen == [], "answers_shared=False must apply to the context, not just a prompt shortcut"


def test_answer_principal_must_match_current_principal_too():
    accepted, issues = validate_answers([valid_answer()], [prior_question()],
                                        "audit-session", "principal-B")
    assert accepted == []
    assert issues


def test_control_answer_for_same_principal_is_accepted():
    accepted, issues = validate_answers([valid_answer()], [prior_question()],
                                        "audit-session", "principal-A")
    assert len(accepted) == 1 and issues == []


def test_correction_cannot_claim_same_principal_when_current_identity_missing():
    record = PriorInsightRecord(id="old-1", session_id="audit-session", principal_id="principal-A",
                                agent_id="owner", type="fact", content="Previously stated approval.", turn=1)
    issue = validate_correction_target(
        {"target_insight_id": "old-1", "operation": "withdraw", "reason": "Unsupported."},
        prior_insights=[record], session_id="audit-session", principal_id=None,
        turn_count=2, agent_id="owner")
    assert issue is not None


def test_typed_exception_uses_diagnostics_not_human_insight_channel():
    def fail(a, c):
        raise ValueError("synthetic-audit-error")
    output, _ = run_turn(FunctionAgent("failed", fail))
    assert output.insights == []
    assert output.acceptance_by_agent["failed"] == "rejected"


class FakeLLM:
    def __init__(self, body):
        self.body = body
        self.calls = []
    async def generate(self, model=None, messages=None, **kwargs):
        self.calls.append({"model": model, "messages": messages, **kwargs})
        return LLMResult(parsed=self.body, finish_reason="stop", transport="json_object",
                         raw_bytes=len(json.dumps(self.body).encode("utf-8")),
                         usage={"prompt_tokens": 10, "completion_tokens": 10})


def ordinary_candidate():
    return {"has_insight": True, "insight": {
        "type": "suggestion", "content": "Review the scope before committing.",
        "confidence": 0.8, "urgency": "soon",
    }}


def test_content_entrypoint_requires_negotiated_content_contract_before_call():
    a = DynamicAgent({"id": "no-content", "name": "no-content", "text": "Observe.",
                      "output_format": "insight_v1", "trigger_config": {"cooldown": 0}})
    fake = FakeLLM(ordinary_candidate())
    engine = AgentEngine(api_key="audit-not-a-real-key", insight_contract="typed_v1")
    engine.register_agent(a)
    a.llm = fake
    async def go():
        return await engine.start_content_request(
            context(), a.config.id, InsightContentRequest(depth="detailed", request_id="not-negotiated")
        ).result()
    outcome = asyncio.run(go())
    assert outcome.status == "rejected"
    assert fake.calls == []


def content_setup():
    config = {
        "contract": "long_form_v1", "default_depth": "brief", "formats": ["plain_text"],
        "max_preview_chars": 100,
        "profiles": {
            "brief": {"max_content_chars": 1000, "max_output_tokens": 500, "llm_timeout_seconds": 1},
            "detailed": {"max_content_chars": 10000, "max_output_tokens": 2000, "llm_timeout_seconds": 5},
        },
    }
    a = DynamicAgent({"id": "content", "name": "content", "text": "Observe.",
                      "output_format": "insight_v1", "trigger_config": {"cooldown": 0},
                      "insight_config": {"allowed_types": ["suggestion"], "content": config}})
    fake = FakeLLM(ordinary_candidate())
    caps = HostInsightCapabilities(supported_types=["suggestion"], content_contracts=["long_form_v1"],
                                  content_formats=["plain_text"], expanded_reading=True,
                                  max_content_chars=10000, max_preview_chars=100)
    limits = {"max_response_bytes": 100000, "live_max_output_tokens": 500,
              "live_max_timeout_seconds": 1, "max_concurrent_content_tasks": 1}
    engine = AgentEngine(api_key="audit-not-a-real-key", insight_contract="typed_v1", content_limits=limits)
    engine.register_agent(a)
    a.llm = fake
    ctx = context(capabilities=caps)
    ctx.content_execution_context = ContentExecutionContext(session_mode="active", execution_path="live_turn")
    return engine, a, fake, ctx


def test_content_task_registry_does_not_accumulate_completed_handles():
    engine, agent, fake, ctx = content_setup()
    async def go():
        for n in range(12):
            outcome = await engine.start_content_request(
                ctx, agent.config.id, InsightContentRequest(depth="detailed", request_id=f"request-{n}")
            ).result()
            assert outcome.status == "accepted", outcome.model_dump()
        await asyncio.sleep(0)  # Allow scheduled cleanup callbacks to execute.
        retained = list(engine._content_tasks.get(ctx.session_id, []))
        assert not retained, "Completed tasks should leave the pending-task registry; history is separate"
    asyncio.run(go())


def test_long_form_prompt_does_not_forbid_its_own_requested_fields():
    engine, agent, fake, ctx = content_setup()
    async def go():
        return await engine.start_content_request(
            ctx, agent.config.id, InsightContentRequest(depth="detailed", request_id="prompt-check")
        ).result()
    result = asyncio.run(go())
    assert result.status == "accepted"
    prompt = fake.calls[0]["messages"][0]["content"]
    assert '"preview"' in prompt and '"content_format"' in prompt
    assert "no id, turn, preview, content_format" not in prompt


@pytest.mark.parametrize("value", ["1000", True])
def test_content_profile_numeric_fields_are_strict_before_coercion(value):
    with pytest.raises(ValidationError):
        ContentProfile(max_content_chars=5000, max_output_tokens=value, llm_timeout_seconds=5)
