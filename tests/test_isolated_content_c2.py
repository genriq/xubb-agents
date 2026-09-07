"""C2 — isolated active-session extended generation (spec §14.6.1, §14.9; roadmap DL-6 / INV-37).

Framework-scope contract registered in docs/CONTRACTS.yaml:

  CONTENT-ISOLATED-PATH  an engine-owned content task runs on a fresh agent instance over a
                         frozen snapshot under an engine-issued declaration; it never touches
                         the live turn path, Blackboard, private memory, turn counter or
                         correction reservations; it is result-only; admission is bounded;
                         cancellation and session closure revoke publication; a host-authored
                         isolated declaration is refused.

Real concurrency: live turns run on the same engine while a content task is parked on an
event, then the task is cancelled or completes late.
"""
import asyncio
import json

import pytest

from xubb_agents import AgentEngine, DynamicAgent, AgentContext, Blackboard, HostInsightCapabilities
from xubb_agents.core.agent import AgentConfig, BaseAgent
from xubb_agents.core.llm import LLMResult
from xubb_agents.core.models import (
    AgentResponse, InsightType, TranscriptSegment, TriggerType, ContentExecutionContext, InsightContentRequest,
    ContentResult,
)

from tests.test_long_form_c1 import CONTENT, OPERATOR, PROFILES, host, body, ctx as c1_ctx
from tests.test_typed_acceptance_g1 import envelope, cand, codes

NINE = ["fact", "observation", "suggestion", "warning", "opportunity", "praise", "reply", "correction", "question"]
LONG = " ".join(["scope"] * 3000)


class GatedFake:
    """generate() parks on an event so a live turn can interleave; returns telemetry."""

    def __init__(self, bodies, gate=None):
        self.bodies = list(bodies) if isinstance(bodies, list) else [bodies]
        self.gate = gate
        self.calls = []

    async def generate(self, model=None, messages=None, **kwargs):
        self.calls.append(kwargs)
        if self.gate is not None:
            await self.gate.wait()
        b = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        return LLMResult(parsed=b, finish_reason="stop", transport="json_object",
                         raw_bytes=len(json.dumps(b).encode("utf-8")), usage={"prompt_tokens": 3, "completion_tokens": 9})


def agent(body_, gate=None, agent_id="lf", allowed=("fact", "suggestion", "warning"), trigger=None):
    a = DynamicAgent({"id": agent_id, "name": agent_id, "text": "t", "output_format": "insight_v1",
                      "trigger_config": trigger or {"cooldown": 0},
                      "insight_config": {"allowed_types": list(allowed), "content": CONTENT}})
    a.llm = GatedFake(body_, gate)
    return a


def engine(*agents, limits=OPERATOR, **kw):
    e = AgentEngine(api_key="k", insight_contract="typed_v1", content_limits=limits, **kw)
    for a in agents:
        llm = a.llm
        e.register_agent(a)
        a.llm = llm
    return e


def live_ctx(turn_count=1):
    return AgentContext(session_id="s", turn_count=turn_count, blackboard=Blackboard(), principal_id="p",
                        recent_segments=[TranscriptSegment(speaker="CLIENT", text="Explain the options.", timestamp=1.0)],
                        insight_capabilities=host(),
                        content_execution_context=ContentExecutionContext(session_mode="active", execution_path="live_turn"))


def detailed(body_text=LONG):
    return body(content=body_text, preview="Short.")


def run_content(e, c, agent_id="lf", request=None):
    """start_content_request needs a running loop (it owns an asyncio.Task)."""
    async def go():
        return await e.start_content_request(c, agent_id, request or InsightContentRequest(depth="detailed")).result()
    return asyncio.run(go())


# ---------------------------------------------------------------------------
# Engine-issued isolated path
# ---------------------------------------------------------------------------

class TestIsolatedPath:
    def test_detailed_content_runs_outside_the_live_turn_and_is_result_only(self):
        a = agent(detailed())
        e = engine(a)
        c = live_ctx(turn_count=4)

        async def run():
            handle = e.start_content_request(c, "lf", InsightContentRequest(depth="detailed", request_id="host-7"))
            return await handle.result(), handle
        result, handle = asyncio.run(run())
        assert isinstance(result, ContentResult) and result.status == "accepted"
        assert result.request_id == "host-7" and result.source_snapshot_id == handle.source_snapshot_id
        ins = result.insight
        assert ins.type is InsightType.SUGGESTION and ins.content == LONG and ins.response_depth == "detailed"
        assert ins.content_request_id == "host-7" and ins.source_snapshot_id == result.source_snapshot_id
        assert ins.id and ins.turn == 4 and ins.contract_version == "typed_v1"
        assert result.usage == {"prompt_tokens": 3, "completion_tokens": 9}
        # one generation happened (the client is shared by design); the LIVE context was never touched
        assert len(a.llm.calls) == 1 and result.snapshot_turn == 4
        assert c.blackboard.variables == {} and c.content_execution_context.execution_path == "live_turn"

    def test_fresh_instance_no_shared_state_and_live_agent_unused(self):
        a = agent(detailed())
        a.private_state["seed"] = "live-only"
        e = engine(a)
        result = run_content(e, live_ctx())
        assert result.status == "accepted"
        assert getattr(a, "_last_snapshot", None) is None    # the twin did the work, not the live instance
        assert a.private_state == {"seed": "live-only"}

    def test_host_authored_isolated_declaration_is_refused(self):
        """NEGATIVE CONTROL: a declaration of isolation is not the isolated path."""
        a = agent(detailed())
        e = engine(a)
        declared = ContentExecutionContext(session_mode="active", execution_path="isolated_content", request_id="r",
                                           source_snapshot_id="snap", holds_live_turn_lock=False,
                                           writes_live_blackboard=False, task_isolation_verified=True)
        c = c1_ctx(execution=declared, request=InsightContentRequest(depth="detailed", request_id="r"), capabilities=host())
        final = asyncio.run(e.process_turn(c))
        d = next(d for d in final.diagnostics if d.code == "content_execution_not_allowed")
        assert d.classification == "isolated_path_requires_engine_task" and a.llm.calls == []

    def test_domain_effects_on_the_isolated_path_reject_the_result(self):
        with_effects = envelope(dict(detailed()["insight"]), facts=[{"type": "budget", "key": "p", "value": 1, "confidence": 0.5}],
                                variable_updates={"phase": "x"})
        a = agent(with_effects)
        e = engine(a)
        c = live_ctx()
        result = run_content(e, c)
        assert result.status == "rejected" and result.insight is None
        assert "content_execution_not_allowed" in [d.code for d in result.diagnostics]
        assert c.blackboard.variables == {} and not c.blackboard.has_fact("budget", "p")

    def test_interactive_types_stay_off_the_isolated_path(self):
        q = cand(type="question", content="Are you authorised?", urgency="soon",
                 question={"reason": "Need authority.", "response_format": "text"})
        q["content_format"] = "plain_text"
        a = agent(envelope(q), allowed=("fact", "question"))
        a.config.insight_config.allow_question = True
        e = AgentEngine(api_key="k", insight_contract="typed_v1", content_limits=OPERATOR)
        llm = a.llm; e.register_agent(a); a.llm = llm
        c = live_ctx(); c.insight_capabilities.text_questions = True
        result = run_content(e, c)
        assert result.status == "rejected" and result.insight is None
        assert any(d.classification in ("interactive_type_on_isolated_path", "correction_not_permitted", "question_not_permitted")
                   or d.code == "content_execution_not_allowed" for d in result.diagnostics)

    def test_custom_agent_is_not_isolatable(self):
        class Custom(BaseAgent):
            def __init__(self):
                super().__init__(AgentConfig(name="custom", cooldown=0, trigger_types=[TriggerType.TURN_BASED]))
            async def evaluate(self, context):
                return AgentResponse()
        e = AgentEngine(api_key="k", insight_contract="typed_v1", content_limits=OPERATOR)
        e.register_agent(Custom())
        result = run_content(e, live_ctx(), "custom")
        assert result.status == "rejected" and result.diagnostics[0].classification == "agent_not_isolatable"

    def test_unknown_agent_raises(self):
        e = engine(agent(detailed()))
        with pytest.raises(ValueError):
            run_content(e, live_ctx(), "nope")


# ---------------------------------------------------------------------------
# Concurrency, admission, cancellation, closure
# ---------------------------------------------------------------------------

class TestConcurrencyAndClosure:
    def test_live_turns_proceed_while_a_content_task_is_parked_and_never_see_its_state(self):
        gate = asyncio.Event()
        # on-demand only: a keyword trigger that never fires on the live turn (content is host-requested)
        slow = agent(detailed(), gate=gate, agent_id="lf", trigger={"mode": "keyword", "keywords": ["zzz"], "cooldown": 0})
        quick = DynamicAgent({"id": "q", "name": "q", "text": "t", "output_format": "insight_v1", "trigger_config": {"cooldown": 0}})
        quick.llm = GatedFake(envelope(cand(type="warning", content="Budget risk", urgency="now"), variable_updates={"phase": "live"}))
        e = engine(slow, quick)
        c = live_ctx(turn_count=1)

        async def run():
            handle = e.start_content_request(c, "lf", InsightContentRequest(depth="detailed", request_id="r-1"))
            await asyncio.sleep(0)                       # let the task start and park
            final = await asyncio.wait_for(e.process_turn(c), timeout=2)   # live turn must not wait on it
            assert c.blackboard.get_var("phase") == "live"
            assert c.blackboard.get_var("sys.turn_count") == 1
            assert handle.task is not None and not handle.task.done()
            gate.set()
            result = await handle.result()
            return final, result
        final, result = asyncio.run(run())
        assert final.acceptance_by_agent["q"] == "accepted"
        assert result.status == "accepted" and result.insight.content == LONG
        # the content task neither bumped the live turn nor touched the live board
        assert c.blackboard.get_var("sys.turn_count") == 1 and c.blackboard.variables.get("phase") == "live"

    def test_admission_is_bounded(self):
        gate = asyncio.Event()
        a = agent(detailed(), gate=gate)
        e = engine(a, limits=dict(OPERATOR, max_concurrent_content_tasks=1))
        c = live_ctx()

        async def run():
            first = e.start_content_request(c, "lf", InsightContentRequest(depth="detailed"))
            await asyncio.sleep(0)
            second = e.start_content_request(c, "lf", InsightContentRequest(depth="detailed"))
            r2 = await second.result()
            gate.set()
            r1 = await first.result()
            return r1, r2
        r1, r2 = asyncio.run(run())
        assert r1.status == "accepted"
        assert r2.status == "rejected" and r2.diagnostics[0].classification == "provider_admission_exhausted"

    def test_invalid_admission_bound_rejected(self):
        with pytest.raises(ValueError):
            AgentEngine(api_key="k", content_limits={"max_concurrent_content_tasks": 0})

    def test_cancellation_revokes_publication_mid_generation(self):
        gate = asyncio.Event()
        a = agent(detailed(), gate=gate)
        e = engine(a)

        async def run():
            handle = e.start_content_request(live_ctx(), "lf", InsightContentRequest(depth="detailed"))
            await asyncio.sleep(0)
            handle.cancel()
            return await handle.result()
        result = asyncio.run(run())
        assert result.status == "cancelled" and result.insight is None
        assert result.diagnostics[0].code == "content_execution_not_allowed"

    def test_late_result_after_revocation_is_not_published_but_keeps_usage(self):
        gate = asyncio.Event()
        a = agent(detailed(), gate=gate)
        e = engine(a)

        async def run():
            handle = e.start_content_request(live_ctx(), "lf", InsightContentRequest(depth="detailed"))
            await asyncio.sleep(0)
            handle.publishable = False       # revoked without cancelling the task: generation finishes
            gate.set()
            return await handle.result()
        result = asyncio.run(run())
        assert result.status == "cancelled" and result.insight is None
        assert result.usage == {"prompt_tokens": 3, "completion_tokens": 9}
        assert any(d.classification == "publication_revoked" for d in result.diagnostics)

    def test_session_closure_cancels_every_pending_task(self):
        gate = asyncio.Event()
        a = agent(detailed(), gate=gate)
        e = engine(a, limits=dict(OPERATOR, max_concurrent_content_tasks=3))

        async def run():
            handles = [e.start_content_request(live_ctx(), "lf", InsightContentRequest(depth="detailed")) for _ in range(2)]
            await asyncio.sleep(0)
            n = e.close_session_content("s")
            results = [await h.result() for h in handles]
            return n, results
        n, results = asyncio.run(run())
        assert n == 2 and all(r.status == "cancelled" and r.insight is None for r in results)

    def test_incomplete_generation_on_the_isolated_path_is_rejected(self):
        class LengthFake(GatedFake):
            async def generate(self, model=None, messages=None, **kwargs):
                r = await super().generate(model=model, messages=messages, **kwargs)
                return LLMResult(parsed=r.parsed, finish_reason="length", transport="json_object", raw_bytes=r.raw_bytes, usage=r.usage)
        a = agent(detailed()); a.llm = LengthFake(detailed())
        e = engine(a)
        result = run_content(e, live_ctx())
        assert result.status == "rejected" and "incomplete_generation" in [d.code for d in result.diagnostics]
        assert result.usage is not None

    def test_result_is_serializable_and_never_merged(self):
        a = agent(detailed())
        e = engine(a)
        c = live_ctx()
        result = run_content(e, c)
        dumped = json.loads(result.model_dump_json())
        assert dumped["status"] == "accepted" and dumped["insight"]["source_snapshot_id"] == result.source_snapshot_id
        assert c.blackboard.facts == [] and c.blackboard.memory == {}
