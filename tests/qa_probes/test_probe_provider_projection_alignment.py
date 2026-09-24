"""PROBE — the provider projection invited what local validation always rejects.

Escaped defect (docs/SPEC_PROVIDER_PROJECTION_ALIGNMENT.md): a downstream host's rehearsal
with production prompts saw most typed insights rejected with `only_for_hypothesis`,
`subtype_on_non_observation`, `consulting_profile_required`, a question payload on a
non-question, and scalar queue values. The strict schema the engine sent allowed every one
of those shapes, because the contract's conditional rules are local-only keywords and the
projection never knew the run's analysis profile.

A strict provider can only emit what the schema it receives allows. This probe stands in
for one at the SDK boundary: the fake completion returns the FIRST of the model's preferred
answers that validates against the schema the engine actually sent. The first preference is
the shape the rehearsal saw rejected; the second is its valid equivalent. Before the repair
the schema allowed the first, so the turn was rejected; after it, the schema refuses the
first and the valid second is accepted. Everything else is the real engine.
"""
import asyncio
from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator

from xubb_agents import AgentEngine, AgentContext, Blackboard, DynamicAgent, HostInsightCapabilities
from xubb_agents.core.insight_validation import HUMAN_WIRE_VALUES
from xubb_agents.core.models import TranscriptSegment

from tests.test_provider_schema_g2 import STRICT_ENVELOPE, make_client, ok_response

PLACEMENT_CODES = {"only_for_hypothesis", "subtype_on_non_observation", "consulting_profile_required",
                   "payload_on_non_question"}


class StrictDecoder:
    """The SDK's completion call, decoding the way a strict provider does: only an
    answer the received schema allows can come back."""

    def __init__(self, preferences):
        self.preferences = preferences
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        validator = Draft202012Validator(kwargs["response_format"]["json_schema"]["schema"])
        for body in self.preferences:
            if validator.is_valid(body):
                return ok_response(body)
        raise AssertionError("no preferred answer fits the schema the engine sent")


def wire(queue=None, **insight):
    body = deepcopy(STRICT_ENVELOPE)
    body["insight"].update(insight)
    if queue is not None:
        body["queue_pushes"] = queue
    return body


def turn(profile, allowed, preferences):
    llm, _ = make_client([ok_response(preferences[-1])], structured_outputs="strict")
    decoder = StrictDecoder(preferences)
    llm.client.chat.completions = decoder
    agent = DynamicAgent({"id": "a", "name": "a", "text": "You advise.", "output_format": "insight_v1",
                          "trigger_config": {"cooldown": 0},
                          "insight_config": {"analysis_profile": profile, "allowed_types": list(allowed)}})
    engine = AgentEngine(api_key="k", structured_outputs="strict")
    engine.register_agent(agent)
    agent.llm = llm
    ctx = AgentContext(session_id="s", turn_count=1, blackboard=Blackboard(), principal_id="p",
                       recent_segments=[TranscriptSegment(speaker="C", text="Can we keep Friday?", timestamp=1.0)],
                       insight_capabilities=HostInsightCapabilities(supported_types=list(HUMAN_WIRE_VALUES)))
    return asyncio.run(engine.process_turn(ctx))


SIX = ["fact", "observation", "suggestion", "warning", "opportunity", "praise"]
FOUR = ["fact", "observation", "suggestion", "warning"]


@pytest.mark.parametrize("profile,allowed,rejected_shape,valid_shape", [
    ("general", SIX,
     wire(type="suggestion", observation_kind="implication", validation_step="Pilot it first."),
     wire(type="suggestion")),
    ("consulting", FOUR,
     wire(type="warning", observation_kind="implication", rationale="r", validation_step="Pilot it first."),
     wire(type="warning")),
    ("consulting", FOUR,
     wire(type="observation", urgency="whenever", observation_kind=None, validation_step="Check it."),
     wire(type="observation", urgency="whenever")),
    ("general", SIX,
     wire(type="suggestion", question={"reason": "Need the owner.", "response_format": "text"}),
     wire(type="suggestion")),
    ("general", SIX,
     wire(type="suggestion", queue={"entries": [{"key": "next_move", "value": "ask for the workflow"}]}),
     wire(type="suggestion", queue={"entries": [{"key": "next_move", "value": ["ask for the workflow"]}]})),
], ids=["general-implication-and-step-on-suggestion", "consulting-implication-and-step-on-warning",
        "consulting-step-on-plain-observation", "question-payload-on-suggestion", "scalar-queue-value"])
def test_a_strict_provider_can_no_longer_emit_what_the_engine_rejects(profile, allowed, rejected_shape, valid_shape):
    final = turn(profile, allowed, [rejected_shape, valid_shape])
    assert final.acceptance_by_agent["a"] == "accepted", [(d.code, d.classification) for d in final.diagnostics]
    assert PLACEMENT_CODES.isdisjoint({d.classification for d in final.diagnostics})
    assert "invalid_domain_payload" not in {d.code for d in final.diagnostics}
