"""G2 part 2 — provider structured outputs (XUBB-ITC-1 §13.3, SO-1).

Framework-scope contracts registered in docs/CONTRACTS.yaml:

  PROVIDER-SCHEMA-DERIVATION   projections compile from the shipped authoritative contract,
                               equal the packaged projections, pass the subset lint, carry the
                               run's exact effective enum, and never an empty enum
  MAP-ENTRIES-CODEC            lossless map_entries_v1 round trips; malformed encodings reject
  STRUCTURED-OUTPUT-FALLBACK   strict never downgrades; auto downgrades once per capability key
                               only on an exact enabled evidence-backed signature; everything
                               else fails closed; json_object never sends a schema
  INV-24 (roadmap)             a strict request carries response_format.type == json_schema,
                               strict: true, and a closed enum equal to the effective set

No network: the OpenAI SDK object is replaced by a scripted fake; provider
acceptance of the generated schema remains a separate integration test.
"""
import asyncio
import json
import math
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator
from openai import APIStatusError

from xubb_agents import AgentEngine, AgentConfigurationError, DynamicAgent, AgentContext, Blackboard, HostInsightCapabilities
from xubb_agents.core.llm import LLMClient, ADAPTER_ID, ADAPTER_VERSION, ENDPOINT_FAMILY
from xubb_agents.core.provider_schema import (
    compile_schema, schema_issues, encode_value, decode_value, encode_response, decode_response,
    allow_schema_fallback, load_registry, CapabilityCache, response_format_for, FEATURE_JSON_SCHEMA,
    STRUCTURED_OUTPUT_MODES,
)
from xubb_agents.core.insight_validation import HUMAN_WIRE_VALUES, IMPLEMENTED_TYPED_TYPES
from xubb_agents.core.models import TranscriptSegment

from tests.test_typed_acceptance_g1 import envelope, cand, codes

FIXTURES = Path(__file__).parent / "fixtures" / "insight_contract_1.2.0"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Fakes for the SDK boundary
# ---------------------------------------------------------------------------

class FakeStatus(APIStatusError):
    def __init__(self, status_code=400, code="feature_not_supported", param="response_format.type", message="bad request"):
        Exception.__init__(self, message)
        self.status_code = status_code
        self.code = code
        self.param = param


def ok_response(body, refusal=None):
    usage = SimpleNamespace(prompt_tokens=11, completion_tokens=7, completion_tokens_details=None, prompt_tokens_details=None)
    msg = SimpleNamespace(content=None if refusal else json.dumps(body), refusal=refusal)
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=msg)], usage=usage)


class FakeCompletions:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_client(outcomes, **kw):
    llm = LLMClient(api_key="k", **kw)
    comp = FakeCompletions(outcomes)
    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=comp))
    return llm, comp


SYNTHETIC_SIGNATURE = {   # test-only; matches the REAL adapter identity so the policy can be exercised
    "adapter_id": ADAPTER_ID, "adapter_version": ADAPTER_VERSION, "endpoint_family": ENDPOINT_FAMILY,
    "http_status": 400, "code": "feature_not_supported", "param": "response_format.type",
    "feature": FEATURE_JSON_SCHEMA, "evidence_id": "TEST-SYNTHETIC-EVIDENCE",
}

NINE = list(HUMAN_WIRE_VALUES)
STRICT_ENVELOPE = {
    "has_insight": True,
    "insight": {"type": "warning", "content": "Approval is not scheduled.", "confidence": 0.7, "urgency": "now",
                "observation_kind": None, "evidence_refs": [], "rationale": None, "validation_step": None,
                "assumptions": [], "correction": None, "question": None,
                "metadata": {"entries": [{"key": "zone", "value": "A"}, {"key": "nested", "value": {"entries": [{"key": "k", "value": [1, None, "x"]}]}}]}},
    "events": [{"name": "approval_missing", "payload": {"entries": [{"key": "owner", "value": None}]}}],
    "variable_updates": {"entries": [{"key": "phase", "value": "risk"}]},
    "queue_pushes": {"entries": [{"key": "followups", "value": ["ask finance"]}]},
    "facts": [{"type": "approval", "key": "finance", "value": {"entries": [{"key": "status", "value": "unscheduled"}]}, "confidence": 0.6}],
    "memory_updates": {"entries": [{"key": "seen", "value": True}]},
    "state_updates": {"entries": []},
    "data": {"entries": []},
}


def typed_agent(schema="insight_v1", agent_id="typed"):
    return DynamicAgent({"id": agent_id, "name": agent_id, "text": "t", "output_format": schema,
                         "trigger_config": {"cooldown": 0}})


def typed_engine(agent, llm, **kw):
    engine = AgentEngine(api_key="k", insight_contract="typed_v1", **kw)
    engine.register_agent(agent)
    agent.llm = llm
    return engine


def tctx():
    return AgentContext(session_id="s", turn_count=1, blackboard=Blackboard(), principal_id="p",
                        recent_segments=[TranscriptSegment(speaker="C", text="Can we keep Friday?", timestamp=1.0)],
                        insight_capabilities=HostInsightCapabilities(supported_types=NINE))


def turn(engine, ctx=None):
    ctx = ctx or tctx()
    return asyncio.run(engine.process_turn(ctx)), ctx


# ---------------------------------------------------------------------------
# PROVIDER-SCHEMA-DERIVATION
# ---------------------------------------------------------------------------

class TestProjection:
    def test_compiled_projections_equal_the_packaged_ones(self):
        assert compile_schema(full=False) == load("provider_insight.schema.json")
        assert compile_schema(full=True) == load("provider_agent_response.schema.json")

    def test_projections_pass_the_subset_lint(self):
        for full in (False, True):
            schema = compile_schema(full=full, content_extension=False, allowed_types=list(IMPLEMENTED_TYPED_TYPES))
            assert schema_issues(schema) == []
            Draft202012Validator.check_schema(schema)

    def test_enum_is_exactly_the_effective_set_and_engine_owned_keys_absent(self):
        schema = compile_schema(full=True, content_extension=False, allowed_types=["fact", "warning"])
        candidate = schema["$defs"]["candidate"]
        assert candidate["properties"]["type"]["enum"] == ["fact", "warning"]
        assert candidate["additionalProperties"] is False
        assert set(candidate["required"]) == set(candidate["properties"])
        assert "preview" not in candidate["properties"] and "content_format" not in candidate["properties"]
        assert not ({"id", "turn", "confidence_provided"} & set(candidate["properties"]))

    def test_empty_effective_set_is_silence_only_never_an_empty_enum(self):
        schema = compile_schema(full=True, allowed_types=[])
        assert schema["properties"]["insight"] == {"type": "null"}
        assert schema["properties"]["has_insight"]["enum"] == [False]
        assert schema_issues(schema) == []

    def test_invalid_effective_types_reject(self):
        with pytest.raises(ValueError, match="invalid_effective_types"):
            compile_schema(allowed_types=["fact", "briefing"])
        with pytest.raises(ValueError, match="invalid_effective_types"):
            compile_schema(allowed_types=["fact", "fact"])

    def test_lint_detects_open_objects_and_local_keywords(self):
        assert any("not closed" in i for i in schema_issues({"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}))
        assert any("local-only" in i for i in schema_issues({"type": "string", "minLength": 1}))
        assert any("empty enum" in i for i in schema_issues({"type": "string", "enum": []}))

    def test_shipped_registry_enables_no_production_signature(self):
        registry = load_registry()
        assert registry["enabled_signatures"] == []
        assert registry["disabled_synthetic_example"]["evidence_id"] == "SYNTHETIC-NOT-A-PROVIDER-RESPONSE"


# ---------------------------------------------------------------------------
# MAP-ENTRIES-CODEC
# ---------------------------------------------------------------------------

class TestCodec:
    def test_round_trip_preserves_scalars_arrays_nulls_and_nested_maps(self):
        value = {"budget": {"currency": "USD", "amount": 60000}, "approval": None,
                 "items": [True, None, 3.5, "value", {"deep": {"er": []}}], "empty": {}}
        wire = encode_value(value)
        assert wire["entries"][0] == {"key": "budget", "value": {"entries": [{"key": "currency", "value": "USD"}, {"key": "amount", "value": 60000}]}}
        assert decode_value(wire) == value

    @pytest.mark.parametrize("bad,code", [
        ({"entries": [{"key": "x", "value": 1}, {"key": "x", "value": 2}]}, "duplicate_map_key"),
        ({"key": "x"}, "invalid_map_encoding"),
        ({"entries": [{"key": 1, "value": 1}]}, "invalid_map_entry"),
        ({"entries": [{"key": "x"}]}, "invalid_map_entry"),
        ({"entries": "nope"}, "invalid_map_encoding"),
    ])
    def test_malformed_encodings_reject(self, bad, code):
        with pytest.raises(ValueError, match=code):
            decode_value(bad)

    def test_non_finite_and_depth_reject(self):
        with pytest.raises(ValueError, match="nonfinite_json"):
            encode_value({"x": math.nan})
        with pytest.raises(ValueError, match="nonfinite_json"):
            decode_value({"entries": [{"key": "x", "value": math.inf}]})
        deep = {}
        for _ in range(40):
            deep = {"d": deep}
        with pytest.raises(ValueError, match="map_depth_limit"):
            encode_value(deep)

    def test_packaged_positive_examples_round_trip_through_both_projections(self):
        """Mirrors the package's provider round-trip checks: every valid shape fixture,
        enriched with nested maps and full domain channels, validates against the
        compiled projection and decodes back to itself."""
        examples = [f for f in load("examples.json")["fixtures"] if f["expected_valid"]]
        for full in (False, True):
            validator = Draft202012Validator(compile_schema(full=full))
            for f in examples:
                data = deepcopy(f["envelope"])
                if data["insight"] is not None:
                    data["insight"]["metadata"] = {"nested": {"items": [True, None, 3.5, "value"]}, "entries": "ordinary key preserved"}
                if full:
                    for n in ["state_updates", "variable_updates", "queue_pushes", "memory_updates", "data"]:
                        data[n] = {}
                    data["variable_updates"] = {"budget": {"currency": "USD", "amount": 60000}, "approval": None}
                    data["queue_pushes"] = {"pending": [{"question": "Who approves?"}]}
                    data["facts"] = [{"type": "budget", "key": "primary", "value": {"amount": 60000}, "confidence": .8}]
                    data["events"] = [{"name": "budget_changed", "payload": {"prior": None, "current": 60000}}]
                wire = encode_response(data, full=full)
                assert validator.is_valid(wire), (f["id"], full)
                expected = deepcopy(data)
                if expected["insight"] is not None:
                    expected["insight"].setdefault("preview", None)
                    expected["insight"].setdefault("content_format", "plain_text")
                assert decode_response(wire, full=full) == expected, (f["id"], full)


# ---------------------------------------------------------------------------
# STRUCTURED-OUTPUT-FALLBACK — policy function against the packaged fixtures
# ---------------------------------------------------------------------------

class TestFallbackPolicy:
    def test_packaged_fallback_fixtures_reproduce(self):
        fixtures = [f for f in load("amendment_fixtures.json")["fixtures"] if f["operation"] == "allow_schema_fallback"]
        assert len(fixtures) == 13
        for f in fixtures:
            args = dict(f["args"])
            failure, registry = args.pop("failure"), args.pop("registry")
            assert allow_schema_fallback(failure, registry, **args) == f["expected"], f["id"]

    def test_capability_cache_is_keyed_by_identity(self):
        cache = CapabilityCache()
        k1 = CapabilityCache.key("https://a", "m1", "openai", "1.2")
        k2 = CapabilityCache.key("https://a", "m2", "openai", "1.2")
        cache.record_downgrade(k1, SYNTHETIC_SIGNATURE)
        assert cache.is_downgraded(k1) and not cache.is_downgraded(k2)
        assert cache.downgraded[k1]["evidence_id"] == "TEST-SYNTHETIC-EVIDENCE"


# ---------------------------------------------------------------------------
# Wire behaviour of the LLM client (INV-24 and the fallback policy end to end)
# ---------------------------------------------------------------------------

class TestClientTransport:
    SCHEMA = compile_schema(full=True, content_extension=False, allowed_types=["fact", "warning"])

    def test_strict_request_carries_json_schema_with_closed_enum(self):
        llm, comp = make_client([ok_response(STRICT_ENVELOPE)], structured_outputs="strict")
        result = asyncio.run(llm.generate("m", [], response_schema=self.SCHEMA))
        rf = comp.calls[0]["response_format"]
        assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True
        assert rf["json_schema"]["schema"]["$defs"]["candidate"]["properties"]["type"]["enum"] == ["fact", "warning"]
        assert rf == response_format_for(self.SCHEMA)
        assert result.transport == "json_schema" and result.parsed["has_insight"] is True

    def test_json_object_mode_never_sends_a_schema(self):
        """NEGATIVE CONTROL for INV-24: json_object mode must not carry the schema."""
        llm, comp = make_client([ok_response({"has_insight": False})], structured_outputs="json_object")
        result = asyncio.run(llm.generate("m", [], response_schema=self.SCHEMA))
        assert comp.calls[0]["response_format"] == {"type": "json_object"} and result.transport == "json_object"

    def test_no_schema_means_json_object_regardless_of_mode(self):
        llm, comp = make_client([ok_response({"has_insight": False})], structured_outputs="strict")
        asyncio.run(llm.generate("m", []))
        assert comp.calls[0]["response_format"] == {"type": "json_object"}

    def test_auto_with_empty_registry_fails_closed(self):
        llm, comp = make_client([FakeStatus()], structured_outputs="auto")
        result = asyncio.run(llm.generate("m", [], response_schema=self.SCHEMA))
        assert len(comp.calls) == 1 and result.parsed is None and result.error_category == "misconfig"
        assert result.failure["category"] == "unsupported_capability" and result.downgraded is False
        assert not llm.capability_cache.downgraded

    def test_auto_with_enabled_signature_downgrades_once_and_caches(self):
        llm, comp = make_client([FakeStatus(), ok_response({"has_insight": False}), ok_response({"has_insight": False})],
                                structured_outputs="auto", fallback_signatures=[SYNTHETIC_SIGNATURE])
        first = asyncio.run(llm.generate("m", [], response_schema=self.SCHEMA))
        assert first.downgraded is True and first.transport == "json_object" and first.parsed == {"has_insight": False}
        assert [c["response_format"]["type"] for c in comp.calls] == ["json_schema", "json_object"]
        second = asyncio.run(llm.generate("m", [], response_schema=self.SCHEMA))
        assert second.downgraded is False and second.transport == "json_object"
        assert [c["response_format"]["type"] for c in comp.calls] == ["json_schema", "json_object", "json_object"]
        key = CapabilityCache.key(None, "m", ADAPTER_ID, ADAPTER_VERSION)
        assert llm.capability_cache.is_downgraded(key)
        # a different model is a different key: strict is attempted again
        asyncio.run(llm.generate("other-model", [], response_schema=self.SCHEMA))
        assert comp.calls[-1]["response_format"]["type"] == "json_schema"

    def test_strict_never_downgrades_even_with_enabled_signature(self):
        llm, comp = make_client([FakeStatus()], structured_outputs="strict", fallback_signatures=[SYNTHETIC_SIGNATURE])
        result = asyncio.run(llm.generate("m", [], response_schema=self.SCHEMA))
        assert len(comp.calls) == 1 and result.downgraded is False and result.parsed is None

    @pytest.mark.parametrize("exc", [
        FakeStatus(code="invalid_json_schema"),
        FakeStatus(param="model", code="feature_not_supported"),
        FakeStatus(status_code=404, code="model_not_found"),
    ])
    def test_other_failures_never_downgrade(self, exc):
        llm, comp = make_client([exc], structured_outputs="auto", fallback_signatures=[SYNTHETIC_SIGNATURE])
        result = asyncio.run(llm.generate("m", [], response_schema=self.SCHEMA))
        assert len(comp.calls) == 1 and result.downgraded is False

    def test_lint_failure_blocks_fallback(self):
        llm, comp = make_client([FakeStatus()], structured_outputs="auto", fallback_signatures=[SYNTHETIC_SIGNATURE])
        result = asyncio.run(llm.generate("m", [], response_schema=self.SCHEMA, schema_lint_passed=False))
        assert len(comp.calls) == 1 and result.downgraded is False

    def test_refusal_is_its_own_category_with_usage(self):
        llm, _ = make_client([ok_response(None, refusal="I cannot help with that.")], structured_outputs="strict")
        result = asyncio.run(llm.generate("m", [], response_schema=self.SCHEMA))
        assert result.error_category == "refusal" and result.parsed is None
        assert result.usage == {"prompt_tokens": 11, "completion_tokens": 7}

    def test_invalid_mode_rejected(self):
        with pytest.raises(ValueError):
            LLMClient(api_key="k", structured_outputs="always")
        assert STRUCTURED_OUTPUT_MODES == ("strict", "auto", "json_object")


# ---------------------------------------------------------------------------
# Through the engine: strict transport, decoding, atomic rejection, gating
# ---------------------------------------------------------------------------

class TestEngineStrictTransport:
    def test_strict_envelope_is_decoded_and_staged(self):
        llm, comp = make_client([ok_response(STRICT_ENVELOPE)], structured_outputs="strict")
        agent = typed_agent()
        final, ctx = turn(typed_engine(agent, llm, structured_outputs="strict"))
        assert final.acceptance_by_agent["typed"] == "accepted"
        ins = final.insights[0]
        assert ins.type.value == "warning" and ins.metadata == {"zone": "A", "nested": {"k": [1, None, "x"]}}
        assert ctx.blackboard.get_var("phase") == "risk"
        assert ctx.blackboard.get_fact("approval", "finance").value == {"status": "unscheduled"}
        assert ctx.blackboard.get_memory("typed") == {"seen": True} and ctx.blackboard.queue_length("followups") == 1
        assert [e.name for e in final.events] == ["approval_missing"] and final.events[0].payload == {"owner": None}
        rf = comp.calls[0]["response_format"]
        assert rf["type"] == "json_schema"
        assert rf["json_schema"]["schema"]["$defs"]["candidate"]["properties"]["type"]["enum"] == list(IMPLEMENTED_TYPED_TYPES)

    def test_malformed_map_encoding_rejects_whole_response(self):
        bad = deepcopy(STRICT_ENVELOPE)
        bad["variable_updates"] = {"entries": [{"key": "phase", "value": "a"}, {"key": "phase", "value": "b"}]}
        llm, _ = make_client([ok_response(bad)], structured_outputs="strict")
        final, ctx = turn(typed_engine(typed_agent(), llm, structured_outputs="strict"))
        assert final.acceptance_by_agent["typed"] == "rejected" and final.insights == []
        d = next(d for d in final.diagnostics if d.code == "invalid_domain_payload")
        assert d.classification == "duplicate_map_key"
        assert ctx.blackboard.get_var("phase") is None

    def test_auto_fail_closed_is_observable_on_the_response(self):
        llm, comp = make_client([FakeStatus()], structured_outputs="auto")
        final, _ = turn(typed_engine(typed_agent(), llm, structured_outputs="auto"))
        assert final.acceptance_by_agent["typed"] == "rejected"
        assert {"invalid_envelope", "unsupported_structured_output"} <= set(codes(final))
        d = next(d for d in final.diagnostics if d.code == "unsupported_structured_output")
        assert d.classification.startswith("fail_closed:feature_not_supported")
        assert len(comp.calls) == 1

    def test_auto_downgrade_is_recorded_on_the_response_and_reused(self):
        body = {"has_insight": True, "insight": cand()}
        llm, comp = make_client([FakeStatus(), ok_response(body), ok_response(body)],
                                structured_outputs="auto", fallback_signatures=[SYNTHETIC_SIGNATURE])
        engine = typed_engine(typed_agent(), llm, structured_outputs="auto", fallback_signatures=[SYNTHETIC_SIGNATURE])
        final, _ = turn(engine)
        assert final.acceptance_by_agent["typed"] == "accepted"
        d = next(d for d in final.diagnostics if d.code == "unsupported_structured_output")
        assert d.classification.startswith("downgraded:")
        final2, _ = turn(engine)
        assert final2.acceptance_by_agent["typed"] == "accepted" and "unsupported_structured_output" not in codes(final2)
        assert [c["response_format"]["type"] for c in comp.calls] == ["json_schema", "json_object", "json_object"]

    def test_flat_adapter_stays_on_json_object_under_auto(self):
        body = {"has_insight": True, **cand()}
        llm, comp = make_client([ok_response(body)], structured_outputs="auto")
        final, _ = turn(typed_engine(typed_agent("default_v2"), llm, structured_outputs="auto"))
        assert final.acceptance_by_agent["typed"] == "accepted"
        assert comp.calls[0]["response_format"] == {"type": "json_object"}

    def test_strict_mode_requires_a_json_schema_adapter_at_registration(self):
        engine = AgentEngine(api_key="k", insight_contract="typed_v1", structured_outputs="strict")
        with pytest.raises(AgentConfigurationError, match="structured_outputs='strict' requires"):
            engine.register_agent(typed_agent("default_v2"))
        assert engine.agents == []

    def test_engine_knobs_reach_the_client_and_survive_key_rotation(self):
        engine = AgentEngine(api_key="k", insight_contract="typed_v1", structured_outputs="strict",
                             fallback_signatures=[SYNTHETIC_SIGNATURE])
        assert engine.llm_client.structured_outputs == "strict"
        assert engine.llm_client.fallback_registry["enabled_signatures"] == [SYNTHETIC_SIGNATURE]
        engine.update_api_key("k2")
        assert engine.llm_client.structured_outputs == "strict"
        assert engine.llm_client.fallback_registry["enabled_signatures"] == [SYNTHETIC_SIGNATURE]
        assert AgentEngine(api_key="k")._llm_config == {}   # EN-1: default mode is not recorded

    def test_refusal_rejects_and_keeps_usage(self):
        llm, _ = make_client([ok_response(None, refusal="No.")], structured_outputs="strict")
        agent = typed_agent()
        final, _ = turn(typed_engine(agent, llm, structured_outputs="strict"))
        assert final.acceptance_by_agent["typed"] == "rejected" and "invalid_envelope" in codes(final)
        from tests.test_dynamic_agent import run
        resp = run(agent.evaluate(tctx()))
        assert resp.usage == {"prompt_tokens": 11, "completion_tokens": 7}
