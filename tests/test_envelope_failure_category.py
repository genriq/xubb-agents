"""v2.8.1 — ENVELOPE-FAILURE-CATEGORY (INV-56): when no JSON object arrives, the agent's
``invalid_envelope`` diagnostic carries the model client's failure category as its
classification, so a host can tell a provider transport failure from a refusal or a
malformed body per execution and per agent from the diagnostics alone.
"""
import asyncio

import pytest

from xubb_agents import AgentEngine, DynamicAgent, AgentContext, Blackboard, HostInsightCapabilities
from xubb_agents.core.llm import LLMResult
from xubb_agents.core.models import TranscriptSegment

from tests.test_dynamic_agent import FakeLLM, make_context, run

CATEGORIES = ["timeout", "rate_limit", "server", "refusal", "malformed", "truncated", "auth", "misconfig",
              "not_initialized", "unknown"]


class FailingClient:
    """generate()-style client whose call fails with one reported category."""

    def __init__(self, category):
        self.category = category

    async def generate(self, model=None, messages=None, **kw):
        return LLMResult(parsed=None, error_category=self.category, usage={"prompt_tokens": 3, "completion_tokens": 0})


class ScalarClient:
    """generate()-style client returning a body that is not an object."""

    async def generate(self, model=None, messages=None, **kw):
        return LLMResult(parsed=["not", "an", "object"], finish_reason="stop", transport="json_object")


def agent(client, schema="default_v2", agent_id="a"):
    a = DynamicAgent({"id": agent_id, "name": agent_id, "text": "t", "output_format": schema, "trigger_config": {"cooldown": 0}})
    a.llm = client
    return a


def diagnostics_of(response):
    return [(d.code, d.classification, d.agent_id) for d in response.diagnostics]


class TestEnvelopeFailureCategory:
    @pytest.mark.parametrize("category", CATEGORIES)
    def test_each_client_category_is_the_diagnostic_classification(self, category):
        resp = run(agent(FailingClient(category)).evaluate(make_context()))
        assert resp.acceptance_status == "rejected" and resp.insights == []
        assert ("invalid_envelope", category, "a") in diagnostics_of(resp)

    def test_typed_contract_carries_it_to_the_merged_response(self):
        """Per execution and per agent: two agents, two categories, one merged response."""
        engine = AgentEngine(api_key="k", insight_contract="typed_v1", structured_outputs="json_object")
        timed_out, refused = agent(FailingClient("timeout"), "insight_v1", "slow"), agent(FailingClient("refusal"), "insight_v1", "shy")
        for a in (timed_out, refused):
            client = a.llm
            engine.register_agent(a)
            a.llm = client
        ctx = AgentContext(session_id="s", turn_count=1, blackboard=Blackboard(), principal_id="p",
                           insight_capabilities=HostInsightCapabilities(supported_types=["warning", "suggestion"]),
                           recent_segments=[TranscriptSegment(speaker="CLIENT", text="Can we keep the date?", timestamp=1.0)])
        final = asyncio.run(engine.process_turn(ctx))
        labels = {(d.agent_id, d.code, d.classification) for d in final.diagnostics}
        assert ("slow", "invalid_envelope", "timeout") in labels and ("shy", "invalid_envelope", "refusal") in labels
        assert final.acceptance_by_agent == {"slow": "rejected", "shy": "rejected"}
        execution_ids = {d.execution_id for d in final.diagnostics if d.code == "invalid_envelope"}
        assert len(execution_ids) == 2      # one execution per agent, each attributable

    def test_no_reported_category_is_none(self):
        """A duck-typed client without generate() reports nothing: the classification stays "none"."""
        resp = run(agent(FakeLLM(None)).evaluate(make_context()))
        assert ("invalid_envelope", "none", "a") in diagnostics_of(resp)

    def test_control_non_object_body_keeps_its_type_name(self):
        """NEGATIVE CONTROL: a body that arrived but is not an object is classified by its type, never by a category."""
        resp = run(agent(ScalarClient()).evaluate(make_context()))
        assert ("invalid_envelope", "list", "a") in diagnostics_of(resp)
