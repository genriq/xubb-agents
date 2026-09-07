"""H2 — content path and assurance (audit of e3dfaf1: XA-04, XA-05, XA-06, XA-08).

Framework-scope contracts registered in docs/CONTRACTS.yaml:

  CONTENT-ENTRYPOINT-ADMISSION   start_content_request admits a request — typed contract,
                                 isolatable agent, negotiated content contract for THIS
                                 request under the engine's own declaration, capacity —
                                 BEFORE any snapshot copy, clone, task or model call; a
                                 refusal is an immediate rejected result.
  CONTENT-TASK-LIFECYCLE         capacity is reserved at the entrypoint and released on
                                 every exit (completion, rejection, exception,
                                 cancellation — including before the coroutine first
                                 ran); completed handles leave the pending registry
                                 while their results and revocation rules stay intact.
  PROMPT-FIELDS-FROM-CONTRACT    the forbidden-field instruction and the citation
                                 instruction are derived from the enabled contract of the
                                 run: no rule forbids a requested field, and the citable
                                 ids are exposed whenever an enabled type needs evidence.
  CONTENT-CONFIG-STRICT-PRIMITIVES  content-policy numeric fields are strict at model
                                 construction: numeric strings and booleans are rejected
                                 through the real configuration path, before any
                                 downstream policy checker could see a coerced value.
"""
import asyncio
import json

import pytest
from pydantic import ValidationError

from xubb_agents import AgentEngine, AgentContext, Blackboard, DynamicAgent, HostInsightCapabilities
from xubb_agents.core.agent import AgentConfig, BaseAgent
from xubb_agents.core.engine import AgentConfigurationError
from xubb_agents.core.llm import LLMResult
from xubb_agents.core.models import (
    AgentResponse, InsightType, TranscriptSegment, TriggerType, InsightContentRequest, ContentExecutionContext,
    ContentProfile, AgentContentConfig, PriorInsightRecord, InsightReferenceContext,
)

from tests.test_long_form_c1 import CONTENT, OPERATOR
from tests.test_typed_acceptance_g1 import envelope, cand

LONG = " ".join(["scope"] * 3000)


class GatedFake:
    def __init__(self, body, gate=None, raise_exc=None):
        self.body, self.gate, self.raise_exc, self.calls = body, gate, raise_exc, []

    async def generate(self, model=None, messages=None, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        if self.gate is not None:
            await self.gate.wait()
        if self.raise_exc is not None:
            raise self.raise_exc
        return LLMResult(parsed=self.body, finish_reason="stop", transport="json_object",
                         raw_bytes=len(json.dumps(self.body).encode("utf-8")), usage={"prompt_tokens": 3, "completion_tokens": 9})


def host(**over):
    base = dict(supported_types=["fact", "suggestion", "warning", "correction"], corrections=True,
                content_contracts=["long_form_v1"], content_formats=["plain_text", "markdown"],
                expanded_reading=True, max_content_chars=40000, max_preview_chars=280)
    base.update(over)
    return HostInsightCapabilities(**base)


def live_ctx(capabilities=None, prior=None):
    return AgentContext(session_id="s", turn_count=2, blackboard=Blackboard(), principal_id="p",
                        recent_segments=[TranscriptSegment(speaker="CLIENT", text="Explain the options.", timestamp=1.0)],
                        insight_capabilities=capabilities or host(),
                        insight_reference_context=InsightReferenceContext(prior_insights=prior or []),
                        content_execution_context=ContentExecutionContext(session_mode="active", execution_path="live_turn"))


def agent(body, *, content=CONTENT, gate=None, raise_exc=None, agent_id="lf", allowed=("fact", "suggestion", "warning"),
          extra_cfg=None):
    cfg = {"allowed_types": list(allowed)}
    if content is not None:
        cfg["content"] = content
    cfg.update(extra_cfg or {})
    a = DynamicAgent({"id": agent_id, "name": agent_id, "text": "t", "output_format": "insight_v1",
                      "trigger_config": {"mode": "keyword", "keywords": ["zzz"], "cooldown": 0}, "insight_config": cfg})
    a.llm = GatedFake(body, gate, raise_exc)
    return a


def engine(*agents, limits=OPERATOR, contract="typed_v1"):
    e = AgentEngine(api_key="k", insight_contract=contract, content_limits=limits)
    for a in agents:
        llm = a.llm
        e.register_agent(a)
        a.llm = llm
    return e


def detailed():
    b = cand(type="suggestion", content=LONG, urgency="soon")
    b["preview"] = "Short."
    b["content_format"] = "plain_text"
    return envelope(b)


async def request(e, c, agent_id="lf", depth="detailed", rid=None):
    return await e.start_content_request(c, agent_id, InsightContentRequest(depth=depth, request_id=rid)).result()


# ---------------------------------------------------------------------------
# CONTENT-ENTRYPOINT-ADMISSION
# ---------------------------------------------------------------------------

class TestEntrypointAdmission:
    def test_control_negotiated_request_is_accepted(self):
        a = agent(detailed()); e = engine(a)
        r = asyncio.run(request(e, live_ctx(), rid="r-1"))
        assert r.status == "accepted" and r.insight.response_depth == "detailed" and len(a.llm.calls) == 1

    def test_agent_without_content_contract_is_refused_before_any_call(self):
        a = agent(detailed(), content=None); e = engine(a)
        r = asyncio.run(request(e, live_ctx()))
        assert r.status == "rejected" and r.insight is None and a.llm.calls == []
        assert r.diagnostics[0].code == "content_contract_unavailable"
        assert r.diagnostics[0].classification == "agent_has_no_content_contract"

    def test_legacy_engine_refuses_content_requests(self):
        a = DynamicAgent({"id": "lf", "name": "lf", "text": "t", "output_format": "default_v2",
                          "trigger_config": {"mode": "keyword", "keywords": ["zzz"], "cooldown": 0}})
        a.llm = GatedFake(detailed())
        e = engine(a, contract="legacy_v2")
        r = asyncio.run(request(e, live_ctx()))
        assert r.status == "rejected" and r.diagnostics[0].classification == "typed_contract_required" and a.llm.calls == []

    def test_host_without_the_contract_or_reading_capability_is_refused(self):
        a = agent(detailed()); e = engine(a)
        r = asyncio.run(request(e, live_ctx(capabilities=host(content_contracts=[]))))
        assert r.status == "rejected" and "content_contract_unavailable" in [d.code for d in r.diagnostics] and a.llm.calls == []
        r = asyncio.run(request(e, live_ctx(capabilities=host(expanded_reading=False))))
        assert r.status == "rejected" and a.llm.calls == []

    def test_unsupported_depth_is_refused_before_any_call(self):
        brief_only = dict(CONTENT, profiles={"brief": CONTENT["profiles"]["brief"]})
        a = agent(detailed(), content=brief_only); e = engine(a)
        r = asyncio.run(request(e, live_ctx(), depth="detailed"))
        assert r.status == "rejected" and "unsupported_depth" in [d.code for d in r.diagnostics] and a.llm.calls == []

    def test_schema_without_content_support_is_refused(self):
        a = agent(detailed()); e = engine(a)
        a.descriptor = dict(a.descriptor, supported_content_contracts=[])
        r = asyncio.run(request(e, live_ctx()))
        assert r.status == "rejected" and a.llm.calls == []

    def test_custom_agent_is_refused_at_the_entrypoint(self):
        class Custom(BaseAgent):
            def __init__(self):
                super().__init__(AgentConfig(name="custom", cooldown=0, trigger_types=[TriggerType.TURN_BASED]))
            async def evaluate(self, context):
                return AgentResponse()
        e = AgentEngine(api_key="k", insight_contract="typed_v1", content_limits=OPERATOR); e.register_agent(Custom())
        r = asyncio.run(request(e, live_ctx(), agent_id="custom"))
        assert r.status == "rejected" and r.diagnostics[0].classification == "agent_not_isolatable"

    def test_refusal_allocates_nothing(self):
        a = agent(detailed(), content=None); e = engine(a)
        async def go():
            h = e.start_content_request(live_ctx(), "lf", InsightContentRequest(depth="detailed"))
            assert h.task is None and h.publishable is False
            assert e._content_active == 0 and e._content_tasks == {}
            return await h.result()
        assert asyncio.run(go()).status == "rejected"


# ---------------------------------------------------------------------------
# CONTENT-TASK-LIFECYCLE
# ---------------------------------------------------------------------------

class TestTaskLifecycle:
    def test_capacity_is_reserved_before_allocation_and_released_after_completion(self):
        gate = asyncio.Event()
        a = agent(detailed(), gate=gate); e = engine(a, limits=dict(OPERATOR, max_concurrent_content_tasks=1))
        c = live_ctx()
        async def go():
            first = e.start_content_request(c, "lf", InsightContentRequest(depth="detailed"))
            assert e._content_active == 1
            second = e.start_content_request(c, "lf", InsightContentRequest(depth="detailed"))
            r2 = await second.result()
            assert r2.status == "rejected" and r2.diagnostics[0].classification == "provider_admission_exhausted"
            gate.set()
            r1 = await first.result()
            await asyncio.sleep(0)
            assert e._content_active == 0 and e._content_tasks == {}
            third = e.start_content_request(c, "lf", InsightContentRequest(depth="detailed"))
            return r1, await third.result()
        r1, r3 = asyncio.run(go())
        assert r1.status == "accepted" and r3.status == "accepted"

    @pytest.mark.parametrize("exit_kind", ["rejected_body", "exception", "cancelled_running", "cancelled_before_start"])
    def test_capacity_released_on_every_exit(self, exit_kind):
        gate = asyncio.Event()
        if exit_kind == "rejected_body":
            a = agent(envelope(cand(type="suggestion", content="x", urgency="soon")))   # too short → rejected
        elif exit_kind == "exception":
            a = agent(detailed(), raise_exc=RuntimeError("provider down"))
        else:
            a = agent(detailed(), gate=gate)
        e = engine(a, limits=dict(OPERATOR, max_concurrent_content_tasks=1))
        async def go():
            h = e.start_content_request(live_ctx(), "lf", InsightContentRequest(depth="detailed"))
            if exit_kind == "cancelled_running":
                await asyncio.sleep(0)
                h.cancel()
            elif exit_kind == "cancelled_before_start":
                h.cancel()          # the coroutine never ran: the done-callback still releases
            r = await h.result()
            await asyncio.sleep(0)
            return r
        r = asyncio.run(go())
        assert r.status in ("rejected", "cancelled") and r.insight is None
        assert e._content_active == 0 and e._content_tasks == {}

    def test_completed_handles_leave_the_registry_and_keep_their_results(self):
        a = agent(detailed()); e = engine(a, limits=dict(OPERATOR, max_concurrent_content_tasks=1))
        c = live_ctx()
        async def go():
            handles = []
            for n in range(12):
                h = e.start_content_request(c, "lf", InsightContentRequest(depth="detailed", request_id=f"r-{n}"))
                assert (await h.result()).status == "accepted"
                handles.append(h)
            await asyncio.sleep(0)
            assert e._content_tasks.get("s", []) == []
            # results remain readable through their handles after leaving the registry
            again = [await h.result() for h in handles]
            return again
        again = asyncio.run(go())
        assert [r.request_id for r in again] == [f"r-{n}" for n in range(12)]

    def test_session_closure_still_revokes_pending_tasks_only(self):
        gate = asyncio.Event()
        a = agent(detailed(), gate=gate); e = engine(a, limits=dict(OPERATOR, max_concurrent_content_tasks=2))
        c = live_ctx()
        async def go():
            done = e.start_content_request(c, "lf", InsightContentRequest(depth="detailed", request_id="done"))
            gate.set(); r_done = await done.result(); gate.clear()
            await asyncio.sleep(0)
            pending = e.start_content_request(c, "lf", InsightContentRequest(depth="detailed", request_id="pending"))
            await asyncio.sleep(0)
            n = e.close_session_content("s")
            r_pending = await pending.result()
            return r_done, n, r_pending
        r_done, n, r_pending = asyncio.run(go())
        assert r_done.status == "accepted" and n == 1 and r_pending.status == "cancelled"
        assert e._content_active == 0


# ---------------------------------------------------------------------------
# PROMPT-FIELDS-FROM-CONTRACT
# ---------------------------------------------------------------------------

class TestPromptFields:
    def _system(self, a, e, c):
        asyncio.run(request(e, c))
        return a.llm.calls[0]["messages"][0]["content"]

    def test_long_form_prompt_requests_and_never_forbids_preview_and_content_format(self):
        a = agent(detailed()); e = engine(a)
        system = self._system(a, e, live_ctx())
        assert '"preview"' in system and '"content_format"' in system
        forbid = next(line for line in system.splitlines() if "Never include fields you were not asked for" in line)
        assert "preview" not in forbid and "content_format" not in forbid
        assert "id, turn, contract_version, confidence_provided, origin" in forbid

    def test_base_contract_prompt_forbids_the_extension_fields(self):
        a = agent(envelope(cand(type="warning", content="Budget risk ahead.", urgency="now")), content=None)
        a.config.trigger_types = [TriggerType.TURN_BASED]
        e = engine(a)
        asyncio.run(e.process_turn(live_ctx()))
        system = a.llm.calls[0]["messages"][0]["content"]
        forbid = next(line for line in system.splitlines() if "Never include fields you were not asked for" in line)
        assert "preview" in forbid and "content_format" in forbid and '"preview"' not in system.split("RULES:")[0]

    def test_general_profile_correction_gets_citation_ids_and_instructions(self):
        body = envelope(cand(type="warning", content="Budget risk ahead.", urgency="now"))
        a = agent(body, content=None, allowed=("fact", "correction"), extra_cfg={"allow_correction": True})
        a.config.trigger_types = [TriggerType.TURN_BASED]
        e = engine(a)
        prior = [PriorInsightRecord(id="mine", session_id="s", principal_id="p", agent_id="lf", type="fact",
                                    content="Approved.", turn=1)]
        asyncio.run(e.process_turn(live_ctx(prior=prior)))
        system = a.llm.calls[0]["messages"][0]["content"]
        user = a.llm.calls[0]["messages"][1]["content"]
        assert "An evidence reference is" in system and "Cite the ids shown in [brackets]" in system
        assert "[snap:" in user                       # transcript lines carry citation markers
        assert "insight:mine" in system               # host record is citable as a basis

    def test_general_profile_without_evidence_needing_types_stays_uncited(self):
        """Control: no consulting, no correction → no citation contract, no markers."""
        a = agent(envelope(cand(type="warning", content="Budget risk ahead.", urgency="now")), content=None)
        a.config.trigger_types = [TriggerType.TURN_BASED]
        e = engine(a)
        asyncio.run(e.process_turn(live_ctx()))
        system = a.llm.calls[0]["messages"][0]["content"]
        user = a.llm.calls[0]["messages"][1]["content"]
        assert "An evidence reference is" not in system and "[snap:" not in user

    def test_general_profile_correction_citing_a_transcript_line_is_accepted_end_to_end(self):
        """The evidence the prompt exposes is the evidence the validator resolves."""
        class Capture(GatedFake):
            async def generate(self, model=None, messages=None, **kwargs):
                marker = messages[1]["content"].split("[", 1)[1].split("]", 1)[0]
                self.body = envelope(cand(type="correction", content="Correction: it was proposed, not approved.", urgency="now",
                                          correction={"target_insight_id": "mine", "operation": "replace", "reason": "No approval."},
                                          evidence_refs=[{"kind": "segment", "ref_id": marker, "revision": None}]))
                return await super().generate(model=model, messages=messages, **kwargs)
        a = agent(None, content=None, allowed=("fact", "correction"), extra_cfg={"allow_correction": True})
        a.config.trigger_types = [TriggerType.TURN_BASED]
        a.llm = Capture(None)
        e = engine(a)
        prior = [PriorInsightRecord(id="mine", session_id="s", principal_id="p", agent_id="lf", type="fact",
                                    content="Approved.", turn=1)]
        final = asyncio.run(e.process_turn(live_ctx(prior=prior)))
        assert [i.type for i in final.insights] == [InsightType.CORRECTION], [d.model_dump() for d in final.diagnostics]
        assert final.insights[0].evidence_refs[0].revision is not None


# ---------------------------------------------------------------------------
# CONTENT-CONFIG-STRICT-PRIMITIVES
# ---------------------------------------------------------------------------

class TestStrictPrimitives:
    @pytest.mark.parametrize("field,value", [
        ("max_output_tokens", "1000"), ("max_output_tokens", True), ("max_content_chars", "5000"),
        ("max_content_chars", False), ("llm_timeout_seconds", "5"), ("llm_timeout_seconds", True),
        ("llm_timeout_seconds", float("inf")),
    ])
    def test_profile_rejects_coercible_primitives(self, field, value):
        base = dict(max_content_chars=5000, max_output_tokens=1000, llm_timeout_seconds=5)
        base[field] = value
        with pytest.raises(ValidationError):
            ContentProfile(**base)

    def test_profile_accepts_real_numbers(self):
        p = ContentProfile(max_content_chars=5000, max_output_tokens=1000, llm_timeout_seconds=5)
        assert p.llm_timeout_seconds == 5.0
        assert ContentProfile(max_content_chars=5000, max_output_tokens=1000, llm_timeout_seconds=2.5).llm_timeout_seconds == 2.5

    @pytest.mark.parametrize("value", ["280", True])
    def test_preview_and_host_limits_are_strict(self, value):
        with pytest.raises(ValidationError):
            AgentContentConfig(max_preview_chars=value, profiles={"brief": {"max_content_chars": 1, "max_output_tokens": 1, "llm_timeout_seconds": 1}})
        with pytest.raises(ValidationError):
            HostInsightCapabilities(max_content_chars=value)
        with pytest.raises(ValidationError):
            HostInsightCapabilities(max_preview_chars=value)

    def test_real_agent_configuration_path_rejects_coerced_values(self):
        bad = dict(CONTENT, profiles={**CONTENT["profiles"], "brief": {"max_content_chars": "1200", "max_output_tokens": 1000, "llm_timeout_seconds": 10}})
        with pytest.raises(AgentConfigurationError):
            DynamicAgent({"id": "x", "name": "x", "text": "t", "output_format": "insight_v1",
                          "insight_config": {"allowed_types": ["fact"], "content": bad}})
