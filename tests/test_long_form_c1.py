"""C1 — the negotiated long-form content contract ``long_form_v1`` (spec §14.4–§14.10).

Framework-scope leaves registered in docs/CONTRACTS.yaml:

  ITC-26.FW  extended content does not change an insight's purpose
  ITC-27.FW  the preview never replaces the canonical body or its identity
  ITC-28.FW  depth resolution and isolated/paused admission; FORCE is not isolation
  ITC-29.FW  exact character, preview and byte ceilings, never truncation
  ITC-30.FW  a parseable but incomplete generation is rejected
  ITC-33.FW  the extension requires explicit host + schema + agent support; fields are
             omitted from non-negotiated output and from the legacy projection
  ITC-35.FW  oversize or incomplete long-form output has no domain effects and no
             preview-only salvage
  CONTENT-POLICY-DERIVATION  the framework policy reproduces the 62 packaged fixtures

Reading behaviour, safe rendering and expand-without-generation (ITC-31/32/34) are
host conformance runs; the isolated active path is C2 and is refused here.
"""
import asyncio
import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from xubb_agents import AgentEngine, AgentConfigurationError, DynamicAgent, AgentContext, Blackboard, HostInsightCapabilities
from xubb_agents.core.content_contract import check_content_contract, execution_admission, completion_status_from
from xubb_agents.core.llm import LLMResult
from xubb_agents.core.models import (
    InsightType, TranscriptSegment, TriggerType, ContentExecutionContext, InsightContentRequest, AgentContentConfig,
)

from tests.test_typed_acceptance_g1 import envelope, cand, codes

FIXTURES = Path(__file__).parent / "fixtures" / "insight_contract_1.2.0"
NINE = ["fact", "observation", "suggestion", "warning", "opportunity", "praise", "reply", "correction", "question"]

PROFILES = {"brief": {"max_content_chars": 1200, "max_output_tokens": 1000, "llm_timeout_seconds": 10},
            "standard": {"max_content_chars": 8000, "max_output_tokens": 3500, "llm_timeout_seconds": 20},
            "detailed": {"max_content_chars": 40000, "max_output_tokens": 16000, "llm_timeout_seconds": 60}}
CONTENT = {"contract": "long_form_v1", "default_depth": "brief", "formats": ["plain_text", "markdown"],
           "max_preview_chars": 280, "profiles": PROFILES}
OPERATOR = {"max_response_bytes": 262144, "live_max_output_tokens": 1000, "live_max_timeout_seconds": 10}

LIVE = ContentExecutionContext(session_mode="active", execution_path="live_turn")
PAUSED = ContentExecutionContext(session_mode="paused", execution_path="offline_content", pause_declared=True)
POST = ContentExecutionContext(session_mode="post_session", execution_path="offline_content")
ISOLATED = ContentExecutionContext(session_mode="active", execution_path="isolated_content", request_id="r-1",
                                   source_snapshot_id="snap-1", holds_live_turn_lock=False,
                                   writes_live_blackboard=False, task_isolation_verified=True)


class ContentFake:
    """generate()-style fake carrying the trusted telemetry the contract needs."""

    def __init__(self, body, finish_reason="stop", raw_bytes=None):
        self.body = body
        self.finish_reason = finish_reason
        self.raw_bytes = raw_bytes
        self.calls = []

    async def generate(self, model=None, messages=None, **kwargs):
        self.calls.append({"model": model, "messages": messages, **kwargs})
        raw = json.dumps(self.body, ensure_ascii=False).encode("utf-8")
        return LLMResult(parsed=self.body, finish_reason=self.finish_reason, transport="json_object",
                         raw_bytes=len(raw) if self.raw_bytes is None else self.raw_bytes)


def host(**over):
    base = dict(supported_types=NINE, content_contracts=["long_form_v1"], content_formats=["plain_text", "markdown"],
                expanded_reading=True, max_content_chars=40000, max_preview_chars=280)
    base.update(over)
    return HostInsightCapabilities(**base)


def ctx(*, execution=LIVE, request=None, capabilities=None, agent_id="lf"):
    return AgentContext(session_id="s", turn_count=1, blackboard=Blackboard(), principal_id="p",
                        recent_segments=[TranscriptSegment(speaker="CLIENT", text="Explain the options.", timestamp=1.0)],
                        insight_capabilities=capabilities or host(),
                        content_execution_context=execution,
                        insight_content_requests={agent_id: request} if request else {})


def agent(body, *, content=CONTENT, schema="insight_v1", agent_id="lf", finish_reason="stop", raw_bytes=None):
    cfg = {"id": agent_id, "name": agent_id, "text": "t", "output_format": schema, "trigger_config": {"cooldown": 0},
           "insight_config": {"allowed_types": ["fact", "suggestion", "warning"]}}
    if content is not None:
        cfg["insight_config"]["content"] = content
    a = DynamicAgent(cfg)
    a.llm = ContentFake(body, finish_reason, raw_bytes)
    return a


def engine(a, *, limits=OPERATOR, contract="typed_v1"):
    e = AgentEngine(api_key="k", insight_contract=contract, content_limits=limits)
    llm = a.llm
    e.register_agent(a)
    a.llm = llm
    return e


def turn(e, c=None, **kw):
    c = c or ctx()
    return asyncio.run(e.process_turn(c, **kw)), c


def body(content="A short, complete answer for the principal.", preview=None, fmt="plain_text", **over):
    b = cand(type="suggestion", content=content, urgency="soon")
    b["content_format"] = fmt
    if preview is not None:
        b["preview"] = preview
    b.update(over)
    return envelope(b)


# ---------------------------------------------------------------------------
# CONTENT-POLICY-DERIVATION — the packaged fixtures reproduce
# ---------------------------------------------------------------------------

class TestPackagedFixtures:
    def test_all_62_content_fixtures_reproduce(self):
        schema = json.loads((FIXTURES / "normalized_insight.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        fixtures = json.loads((FIXTURES / "content_contract_fixtures.json").read_text(encoding="utf-8"))["fixtures"]
        assert len(fixtures) == 62
        failures = []
        for f in fixtures:
            env = f["envelope"]
            shape_ok = validator.is_valid(env)
            before = deepcopy(env)
            transport = f.get("serialized_response_fixture")
            result = check_content_contract(env, f["configuration"], request=f["request"], execution=f["execution"],
                                            serialized_response=transport.encode("utf-8") if transport is not None else None)
            passed = shape_ok and result["accepted"] == f["expected_accepted"]
            if f.get("expected_code"):
                passed = passed and f["expected_code"] in result["codes"]
            if "expected_depth" in f:
                passed = passed and result.get("effective_depth") == f["expected_depth"]
            preserved = env == before
            if result["accepted"] and env["insight"] is not None and result.get("mode") == "long_form_v1":
                preserved = preserved and result["canonical_content"] == env["insight"]["content"]
            if not (passed and preserved):
                failures.append((f["id"], result["codes"], f.get("expected_code")))
        assert failures == []

    def test_admission_reference_rules(self):
        profile = PROFILES["detailed"]
        assert execution_admission("detailed", profile, PAUSED.model_dump(), OPERATOR)["accepted"]
        assert execution_admission("detailed", profile, LIVE.model_dump(), OPERATOR)["code"] == "content_execution_not_allowed"
        assert execution_admission("brief", PROFILES["brief"], LIVE.model_dump(), OPERATOR)["accepted"]
        assert execution_admission("brief", PROFILES["brief"], LIVE.model_dump(), {})["code"] == "invalid_content_execution_context"
        assert execution_admission("brief", PROFILES["brief"], None, OPERATOR)["code"] == "invalid_content_execution_context"
        no_pause = ContentExecutionContext(session_mode="paused", execution_path="offline_content").model_dump()
        assert execution_admission("brief", PROFILES["brief"], no_pause, OPERATOR)["code"] == "content_execution_not_allowed"
        assert execution_admission("standard", PROFILES["standard"], ISOLATED.model_dump(), OPERATOR, candidate_type="correction")["code"] == "content_execution_not_allowed"
        assert execution_admission("standard", PROFILES["standard"], ISOLATED.model_dump(), OPERATOR, domain_effects_present=True)["code"] == "content_execution_not_allowed"

    def test_completion_status_from_telemetry(self):
        assert completion_status_from("stop", None) == "complete"
        assert completion_status_from("length", None) == "incomplete"
        assert completion_status_from(None, "truncated") == "incomplete"
        assert completion_status_from(None, "timeout") == "failed"
        assert completion_status_from(None, None) == "unknown"


# ---------------------------------------------------------------------------
# ITC-33.FW — negotiation
# ---------------------------------------------------------------------------

class TestNegotiation:
    def test_content_block_requires_typed_contract_and_a_supporting_schema(self):
        with pytest.raises(AgentConfigurationError, match="requires insight_contract='typed_v1'"):
            AgentEngine(api_key="k").register_agent(agent(body(), schema="default_v2"))
        with pytest.raises(AgentConfigurationError, match="does not support content contract"):
            AgentEngine(api_key="k", insight_contract="typed_v1").register_agent(agent(body(), schema="default_v2"))

    def test_host_without_the_contract_makes_no_call(self):
        a = agent(body())
        final, _ = turn(engine(a), ctx(capabilities=host(content_contracts=[])))
        assert final.acceptance_by_agent["lf"] == "rejected" and "content_contract_unavailable" in codes(final)
        assert a.llm.calls == []
        a2 = agent(body())
        final, _ = turn(engine(a2), ctx(capabilities=host(expanded_reading=False)))
        assert "content_contract_unavailable" in codes(final) and a2.llm.calls == []

    def test_missing_operator_byte_limit_is_invalid_policy(self):
        a = agent(body())
        final, _ = turn(engine(a, limits={"live_max_output_tokens": 1000, "live_max_timeout_seconds": 10}))
        assert "invalid_content_policy" in codes(final) and a.llm.calls == []

    def test_negotiated_output_carries_extension_fields_non_negotiated_does_not(self):
        a = agent(body(preview="Short version."))
        final, _ = turn(engine(a))
        ins = final.insights[0]
        assert ins.content_contract == "long_form_v1" and ins.response_depth == "brief"
        assert ins.preview == "Short version." and ins.content_format == "plain_text"
        assert not ({"preview", "content_format", "content_contract", "response_depth"} & set(ins.model_dump_legacy()))
        plain = agent(envelope(cand(type="suggestion", urgency="soon")), content=None)
        final, _ = turn(engine(plain))
        p = final.insights[0]
        assert p.content_contract is None and p.preview is None and p.content_format is None and p.response_depth is None

    def test_unnegotiated_extension_fields_still_reject(self):
        plain = agent(body(preview="x"), content=None)
        final, _ = turn(engine(plain))
        assert "content_extension_not_enabled" in codes(final) and final.insights == []

    def test_prompt_and_provider_schema_reflect_the_plan(self):
        a = agent(body())
        engine(a)
        turn(engine(a))
        call = a.llm.calls[-1]
        system = call["messages"][0]["content"]
        assert "Response depth for this run: brief" in system and "at most 1200 characters" in system
        assert '"preview"' in system and '"content_format": "plain_text" | "markdown"' in system
        assert "preview" in call["response_schema"]["$defs"]["candidate"]["properties"]
        assert call["max_tokens"] == 1000 and call["timeout"] == 10


# ---------------------------------------------------------------------------
# ITC-28.FW — depth resolution and admission
# ---------------------------------------------------------------------------

class TestDepthAndAdmission:
    def test_brief_default_in_live_session(self):
        final, _ = turn(engine(agent(body())))
        assert final.acceptance_by_agent["lf"] == "accepted" and final.insights[0].response_depth == "brief"

    def test_extended_depth_in_live_session_is_refused_before_the_call(self):
        a = agent(body())
        final, _ = turn(engine(a), ctx(request=InsightContentRequest(depth="detailed", request_id="host-1")))
        assert "content_execution_not_allowed" in codes(final) and a.llm.calls == []

    def test_force_is_not_isolation(self):
        """NEGATIVE CONTROL: FORCE is an execution trigger, not authorization or a lane."""
        a = agent(body())
        final, _ = turn(engine(a), ctx(request=InsightContentRequest(depth="detailed")), trigger_type=TriggerType.FORCE)
        assert "content_execution_not_allowed" in codes(final) and a.llm.calls == []

    def test_declared_pause_admits_detailed_with_its_own_budget(self):
        long_body = " ".join(["scope"] * 5000)
        a = agent(body(content=long_body, preview="Synthetic size probe."))
        final, _ = turn(engine(a), ctx(execution=PAUSED, request=InsightContentRequest(depth="detailed", request_id="host-1")))
        ins = final.insights[0]
        assert ins.response_depth == "detailed" and ins.content_request_id == "host-1" and ins.content == long_body
        assert a.llm.calls[-1]["max_tokens"] == 16000 and a.llm.calls[-1]["timeout"] == 60

    def test_pause_must_be_declared_and_post_session_is_fine(self):
        undeclared = ContentExecutionContext(session_mode="paused", execution_path="offline_content")
        a = agent(body())
        final, _ = turn(engine(a), ctx(execution=undeclared, request=InsightContentRequest(depth="standard")))
        assert "content_execution_not_allowed" in codes(final)
        b = agent(body())
        final, _ = turn(engine(b), ctx(execution=POST, request=InsightContentRequest(depth="standard")))
        assert final.acceptance_by_agent["lf"] == "accepted" and final.insights[0].response_depth == "standard"

    def test_missing_execution_context_rejects(self):
        a = agent(body())
        final, _ = turn(engine(a), ctx(execution=None))
        assert "invalid_content_execution_context" in codes(final) and a.llm.calls == []

    def test_host_declared_isolated_path_is_refused(self):
        """A declaration of isolation is not the engine's isolated task (C2)."""
        a = agent(body())
        final, _ = turn(engine(a), ctx(execution=ISOLATED, request=InsightContentRequest(depth="standard", request_id="r-1")))
        d = next(d for d in final.diagnostics if d.code == "content_execution_not_allowed")
        assert d.classification == "isolated_path_requires_engine_task" and a.llm.calls == []

    def test_unsupported_depth_and_brief_profile_evasion(self):
        only_brief = dict(CONTENT, profiles={"brief": PROFILES["brief"]})
        a = agent(body(), content=only_brief)
        final, _ = turn(engine(a), ctx(execution=PAUSED, request=InsightContentRequest(depth="detailed")))
        assert "unsupported_depth" in codes(final)
        fat_brief = dict(CONTENT, profiles={"brief": {"max_content_chars": 40000, "max_output_tokens": 16000, "llm_timeout_seconds": 60}})
        b = agent(body(), content=fat_brief)
        final, _ = turn(engine(b))
        assert "content_execution_not_allowed" in codes(final) and b.llm.calls == []


# ---------------------------------------------------------------------------
# ITC-26 / ITC-27 / ITC-29 / ITC-30 / ITC-35
# ---------------------------------------------------------------------------

class TestBodyPreviewAndLimits:
    def test_length_does_not_change_the_type(self):
        long_body = "Option A: keep the date. " * 300     # ~7,500 chars
        a = agent(body(content=long_body))
        final, _ = turn(engine(a), ctx(execution=PAUSED, request=InsightContentRequest(depth="standard")))
        assert final.insights[0].type is InsightType.SUGGESTION and len(final.insights[0].content) == len(long_body)

    def test_preview_never_replaces_the_body_and_shares_its_identity(self):
        a = agent(body(content="Full body. " * 50, preview="Preview only."))
        final, _ = turn(engine(a))
        ins = final.insights[0]
        assert ins.content.startswith("Full body.") and ins.preview == "Preview only." and len(final.insights) == 1
        dumped = json.loads(ins.model_dump_json())
        assert dumped["content"] == ins.content and dumped["preview"] == "Preview only." and dumped["id"] == ins.id

    def test_exact_character_boundaries_never_truncate(self):
        ok = agent(body(content="x" * 1200))
        final, _ = turn(engine(ok))
        assert len(final.insights[0].content) == 1200
        over = agent(body(content="x" * 1201, preview="fine"), agent_id="lf")
        final, c = turn(engine(over))
        assert final.insights == [] and "content_too_large" in codes(final)
        p_ok = agent(body(preview="p" * 280))
        final, _ = turn(engine(p_ok))
        assert final.insights[0].preview == "p" * 280
        p_over = agent(body(preview="p" * 281))
        final, _ = turn(engine(p_over))
        assert final.insights == [] and "preview_too_large" in codes(final)

    def test_byte_ceiling_uses_transport_bytes(self):
        a = agent(body(), raw_bytes=101)
        final, _ = turn(engine(a, limits=dict(OPERATOR, max_response_bytes=100)))
        assert final.insights == [] and "response_too_large" in codes(final)

    def test_unsupported_and_negotiated_formats(self):
        bad = agent(body(fmt="html"))
        final, _ = turn(engine(bad))
        assert "unsupported_content_format" in codes(final) and final.insights == []
        md = agent(body(fmt="markdown", content="# Heading\n\nBody."))
        final, _ = turn(engine(md))
        assert final.insights[0].content_format == "markdown"
        plain_host = agent(body(fmt="markdown"))
        final, _ = turn(engine(plain_host), ctx(capabilities=host(content_formats=["plain_text"])))
        assert "unsupported_content_format" in codes(final)

    def test_parseable_but_incomplete_generation_is_rejected(self):
        """NEGATIVE CONTROL for 'it parsed, so it is complete'."""
        a = agent(body(), finish_reason="length")
        final, _ = turn(engine(a))
        assert final.insights == [] and "incomplete_generation" in codes(final)
        b = agent(body(), finish_reason=None)
        final, _ = turn(engine(b))
        assert final.insights == [] and "completion_unknown" in codes(final)

    def test_model_cannot_assert_completeness(self):
        a = agent(body(metadata={"complete": True}), finish_reason="length")
        final, _ = turn(engine(a))
        assert "incomplete_generation" in codes(final) and final.insights == []

    def test_oversize_or_incomplete_has_no_domain_effects_and_no_preview_salvage(self):
        oversize = agent(body(content="x" * 5000, preview="A perfectly good preview."))
        oversize.llm.body = envelope(dict(oversize.llm.body["insight"]), facts=[{"type": "budget", "key": "p", "value": 1, "confidence": 0.5}],
                                     variable_updates={"phase": "x"})
        final, c = turn(engine(oversize))
        assert final.acceptance_by_agent["lf"] == "rejected" and final.insights == []
        assert not c.blackboard.has_fact("budget", "p") and c.blackboard.get_var("phase") is None
        incomplete = agent(body(preview="Good preview."), finish_reason="length")
        incomplete.llm.body = envelope(dict(incomplete.llm.body["insight"]), facts=[{"type": "budget", "key": "p", "value": 1, "confidence": 0.5}])
        final, c = turn(engine(incomplete))
        assert final.insights == [] and not c.blackboard.has_fact("budget", "p")

    def test_valid_silence_still_commits_under_the_extension(self):
        silent = agent(envelope(facts=[{"type": "budget", "key": "p", "value": 1, "confidence": 0.5}]))
        final, c = turn(engine(silent))
        assert final.acceptance_by_agent["lf"] == "accepted_silent" and c.blackboard.has_fact("budget", "p")


class TestConfigModels:
    def test_content_config_validation(self):
        with pytest.raises(ValueError):
            AgentContentConfig(default_depth="detailed", max_preview_chars=280, profiles={"brief": PROFILES["brief"]})
        with pytest.raises(ValueError):
            AgentContentConfig(max_preview_chars=0, profiles={"brief": PROFILES["brief"]})
        with pytest.raises(ValueError):
            AgentContentConfig(max_preview_chars=280, profiles={"brief": dict(PROFILES["brief"], max_output_tokens=0)})
        with pytest.raises(ValueError):
            ContentExecutionContext(session_mode="live", execution_path="live_turn")
