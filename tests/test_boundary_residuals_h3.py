"""H3 — the two residual boundary cases from the reassessment of 0f3cc32.

Framework-scope contracts registered in docs/CONTRACTS.yaml:

  CONTENT-VIEW-ANSWERS-VALIDATED  the isolated content task's frozen view carries only
                                  answers that pass the SAME validator as the live turn
                                  (this session, open question, present matching
                                  principal) before the per-agent visibility filter;
                                  invalid events surface as diagnostics on the result.
  NEGOTIATED-LIMITS-AT-BOUNDARY   the negotiated long_form_v1 ceilings (body chars,
                                  preview chars, formats) are re-applied at final
                                  acceptance to the object that would commit, so a
                                  callback that replaces an accepted body after staging
                                  cannot exceed the frozen policy.
"""
import asyncio
import json

import pytest

from xubb_agents import AgentEngine, AgentContext, Blackboard, DynamicAgent, HostInsightCapabilities
from xubb_agents.core.callbacks import AgentCallbackHandler
from xubb_agents.core.llm import LLMResult
from xubb_agents.core.models import (
    TranscriptSegment, InsightContentRequest, ContentExecutionContext, PriorInsightRecord,
    InsightReferenceContext, InsightAnswer,
)

from tests.test_long_form_c1 import CONTENT, OPERATOR, PROFILES, body, ctx as c1_ctx, host as c1_host


class FakeLLM:
    def __init__(self, body_):
        self.body, self.calls = body_, []

    async def generate(self, model=None, messages=None, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        return LLMResult(parsed=self.body, finish_reason="stop", transport="json_object",
                         raw_bytes=len(json.dumps(self.body).encode("utf-8")), usage={"prompt_tokens": 3, "completion_tokens": 3})


def content_agent(body_, text="Answers visible: {{ context.insight_answers|length }}"):
    a = DynamicAgent({"id": "lf", "name": "lf", "output_format": "insight_v1", "text": text,
                      "trigger_config": {"mode": "keyword", "keywords": ["zzz"], "cooldown": 0},
                      "insight_config": {"allowed_types": ["fact", "suggestion"], "content": CONTENT}})
    a.llm = FakeLLM(body_)
    return a


def engine(a, callbacks=None):
    e = AgentEngine(api_key="k", insight_contract="typed_v1", content_limits=OPERATOR, callbacks=callbacks or [])
    llm = a.llm; e.register_agent(a); a.llm = llm
    return e


def q_record(qid="q-1", agent_id="lf", principal="p", status="active", session="s"):
    return PriorInsightRecord(id=qid, session_id=session, principal_id=principal, agent_id=agent_id, type="question",
                              content="Who approves?", turn=1, status=status)


def answer(eid="e-1", qid="q-1", principal="p", status="answered"):
    return InsightAnswer(event_id=eid, question_insight_id=qid, principal_id=principal, status=status,
                         text="The sponsor." if status == "answered" else None)


def content_ctx(prior, answers, principal="p"):
    caps = HostInsightCapabilities(supported_types=["fact", "suggestion"], content_contracts=["long_form_v1"],
                                   content_formats=["plain_text", "markdown"], expanded_reading=True,
                                   max_content_chars=40000, max_preview_chars=280, answers_shared=False)
    return AgentContext(session_id="s", turn_count=2, blackboard=Blackboard(), principal_id=principal,
                        recent_segments=[TranscriptSegment(speaker="CLIENT", text="Explain the options.", timestamp=1.0)],
                        insight_capabilities=caps, insight_reference_context=InsightReferenceContext(prior_insights=prior),
                        insight_answers=answers,
                        content_execution_context=ContentExecutionContext(session_mode="active", execution_path="live_turn"))


def run_content(e, c):
    async def go():
        return await e.start_content_request(c, "lf", InsightContentRequest(depth="detailed", request_id="r")).result()
    return asyncio.run(go())


# ---------------------------------------------------------------------------
# CONTENT-VIEW-ANSWERS-VALIDATED
# ---------------------------------------------------------------------------

class TestIsolatedViewAnswers:
    def _visible(self, prior, answers, principal="p"):
        a = content_agent({"has_insight": False, "insight": None})
        e = engine(a)
        c = content_ctx(prior, answers, principal)
        r = run_content(e, c)
        line = next(l for l in a.llm.calls[0]["messages"][0]["content"].splitlines() if "Answers visible" in l)
        return r, int(line.split(":")[1]), c

    def test_control_valid_own_answer_is_visible(self):
        r, n, _ = self._visible([q_record()], [answer()])
        assert r.status == "silent" and n == 1 and r.diagnostics == []

    def test_wrong_principal_answer_for_own_question_is_excluded_with_a_diagnostic(self):
        r, n, c = self._visible([q_record()], [answer(principal="p-OTHER")])
        assert n == 0
        assert [(d.code, d.classification) for d in r.diagnostics] == [("invalid_input_reference", "principal_mismatch")]
        assert len(c.insight_answers) == 1                      # host list untouched

    def test_current_context_for_another_principal_sees_nothing(self):
        r, n, _ = self._visible([q_record()], [answer()], principal="p-B")
        assert n == 0 and r.diagnostics[0].classification == "principal_mismatch"

    @pytest.mark.parametrize("prior,ans,cls", [
        ([q_record(status="withdrawn")], [answer()], "question_withdrawn"),
        ([q_record(session="other")], [answer()], None),               # cross-session → code below
        ([], [answer()], "unknown_question"),
        ([q_record()], [answer(status="dismissed")], None),             # dismissed is valid: visible
    ])
    def test_open_question_in_this_session_is_required(self, prior, ans, cls):
        r, n, _ = self._visible(prior, ans)
        if cls is None and prior and prior[0].status == "active" and prior[0].session_id == "s":
            assert n == 1 and r.diagnostics == []                       # the dismissed control
        elif cls is None:
            assert n == 0 and r.diagnostics[0].code == "cross_session_reference"
        else:
            assert n == 0 and r.diagnostics[0].classification == cls

    def test_missing_current_principal_disables_answers_on_the_isolated_path(self):
        a = content_agent({"has_insight": False, "insight": None})
        e = engine(a)
        c = content_ctx([q_record()], [answer()], principal=None)
        r = run_content(e, c)
        assert r.diagnostics and r.diagnostics[0].code == "missing_principal"
        assert "Answers visible: 0" in a.llm.calls[0]["messages"][0]["content"]

    def test_live_and_isolated_paths_agree(self):
        """Same context, same validator: the live phase view and the frozen view
        expose the same answers to the same agent."""
        seen = {}
        a = content_agent({"has_insight": False, "insight": None})
        a.config.trigger_types = [__import__("xubb_agents.core.models", fromlist=["TriggerType"]).TriggerType.TURN_BASED]
        e = engine(a)
        c = content_ctx([q_record()], [answer(), answer(eid="bad", principal="p-OTHER")])
        asyncio.run(e.process_turn(c))
        live = next(l for l in a.llm.calls[-1]["messages"][0]["content"].splitlines() if "Answers visible" in l)
        r = run_content(e, c)
        iso = next(l for l in a.llm.calls[-1]["messages"][0]["content"].splitlines() if "Answers visible" in l)
        assert live == iso == "Answers visible: 1"


# ---------------------------------------------------------------------------
# NEGOTIATED-LIMITS-AT-BOUNDARY
# ---------------------------------------------------------------------------

class Mutate(AgentCallbackHandler):
    def __init__(self, fn):
        self.fn = fn

    async def on_agent_finish(self, agent_name, response, duration):
        if response is not None and response.insights:
            self.fn(response.insights[0])


def brief_agent(body_):
    from tests.test_long_form_c1 import agent as c1_agent
    return c1_agent(body_)


def live(a, callbacks):
    e = AgentEngine(api_key="k", insight_contract="typed_v1", content_limits=OPERATOR, callbacks=callbacks)
    llm = a.llm; e.register_agent(a); a.llm = llm
    return asyncio.run(e.process_turn(c1_ctx())), e


class TestNegotiatedLimitsAtBoundary:
    def test_control_untouched_brief_body_is_accepted_with_its_stamps(self):
        final, _ = live(brief_agent(body(preview="Short.")), [Mutate(lambda i: None)])
        ins = final.insights[0]
        assert final.acceptance_by_agent["lf"] == "accepted" and ins.response_depth == "brief" and ins.preview == "Short."

    def test_callback_grown_body_is_rejected_against_the_frozen_ceiling(self):
        final, _ = live(brief_agent(body()), [Mutate(lambda i: setattr(i, "content", "x" * (PROFILES["brief"]["max_content_chars"] + 1)))])
        assert final.insights == [] and final.acceptance_by_agent["lf"] == "rejected"
        d = next(d for d in final.diagnostics if d.code == "content_too_large")
        assert d.field_path == "insights[0].content"

    def test_callback_grown_preview_is_rejected(self):
        final, _ = live(brief_agent(body(preview="Short.")), [Mutate(lambda i: setattr(i, "preview", "p" * 281))])
        assert final.insights == [] and "preview_too_large" in [d.code for d in final.diagnostics]

    def test_callback_switched_format_is_rejected(self):
        a = brief_agent(body())
        a.config.insight_config.content.formats = ["plain_text"]
        final, _ = live(a, [Mutate(lambda i: setattr(i, "content_format", "markdown"))])
        assert final.insights == [] and "unsupported_content_format" in [d.code for d in final.diagnostics]

    def test_callback_body_within_the_ceiling_still_passes(self):
        """Control: mutation that stays inside the negotiated policy is not the concern."""
        final, _ = live(brief_agent(body()), [Mutate(lambda i: setattr(i, "content", "Revised but still brief."))])
        assert final.acceptance_by_agent["lf"] == "accepted" and final.insights[0].content == "Revised but still brief."

    def test_isolated_result_is_also_held_to_the_frozen_ceiling(self):
        long_ok = " ".join(["scope"] * 3000)
        b = body(content=long_ok, preview="Short.")
        a = content_agent(b, text="t")
        e = engine(a, callbacks=[Mutate(lambda i: setattr(i, "content", "x" * 40001))])
        # callbacks are not fired on the isolated path, so mutate at the boundary input instead:
        original = e._enforce_acceptance
        def tamper(agent, response, context=None):
            if response.insights:
                response.insights[0].content = "x" * 40001
            return original(agent, response, context)
        e._enforce_acceptance = tamper
        r = run_content(e, content_ctx([], []))
        assert r.status == "rejected" and "content_too_large" in [d.code for d in r.diagnostics]
