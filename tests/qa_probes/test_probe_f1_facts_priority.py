"""
QA Probe Registry — PROBE-F1: fact conflict resolution honors agent priority.

Origin:    v2.1.1 escaped defect (the "facts-vs-priority" contract bug). It survived
           SPEC_V2.1, SPEC_V2.1.1, and was only found by the v2.2 5-agent audit.
Contract:  FACT-PRECEDENCE (docs/CONTRACTS.yaml) / INV-9 (docs/SPEC_V2_2_HARDENING.md).
           On a (type, key) collision: higher agent PRIORITY wins; ties broken by
           higher confidence; remaining ties by later registration order.

This is the canonical escaped-defect probe (see docs/PROCESS.md) from
the QA-agent design proposal. It drives the REAL AgentEngine (the framework is the
system-under-test — the one valuable "dogfood" slice) rather than unit-testing add_fact
in isolation, because the bug lives in the engine-merge ↔ blackboard contract.

STATUS: ACTIVE (hard gate). F-1 landed in v2.2 (Fact.priority + engine stamps it +
add_fact resolves by (priority, confidence)), so this probe now passes and guards against
any future regression of the fact-priority contract.

DO NOT delete this probe and DO NOT re-add an xfail marker. If it starts failing, the
fact-priority contract (INV-9) has regressed — fix the code, not the probe.
"""

import time

import pytest

from xubb_agents.core.engine import AgentEngine
from xubb_agents.core.agent import BaseAgent, AgentConfig
from xubb_agents.core.models import (
    AgentContext, AgentResponse, TriggerType, TranscriptSegment, Fact,
)
from xubb_agents.core.blackboard import Blackboard


class _FactAgent(BaseAgent):
    """Minimal agent that emits one fact via a response function (mirrors the
    MockAgent pattern in tests/test_engine.py, kept local so the probe is self-contained
    and cannot be weakened by edits to the shared test helper)."""

    def __init__(self, name: str, priority: int, response_fn):
        super().__init__(AgentConfig(
            name=name,
            priority=priority,
            trigger_types=[TriggerType.TURN_BASED],
        ))
        self._response_fn = response_fn

    async def evaluate(self, context: AgentContext) -> AgentResponse:
        return self._response_fn()


def _context():
    bb = Blackboard()
    return AgentContext(
        session_id="probe_f1",
        recent_segments=[TranscriptSegment(speaker="USER", text="hi", timestamp=1.0)],
        blackboard=bb,
        turn_count=1,
    )


@pytest.mark.asyncio
async def test_probe_f1_higher_priority_fact_wins_over_higher_confidence():
    """A higher-PRIORITY agent's fact must win even at LOWER confidence (INV-9 rule 1).

    This is the exact inversion the audit proved live: a priority-10 / confidence-0.5
    authoritative extractor must override a priority-1 / confidence-0.9 noisy agent on
    the same (type, key). Confidence is only the tiebreaker WITHIN equal priority.
    """
    engine = AgentEngine(api_key="test_key")

    def emit_high():
        return AgentResponse(facts=[Fact(
            type="budget", key="primary", value="authoritative_high_priority",
            confidence=0.5, source_agent="authoritative", timestamp=time.time(),
        )])

    def emit_low():
        return AgentResponse(facts=[Fact(
            type="budget", key="primary", value="noisy_low_priority",
            confidence=0.9, source_agent="noisy", timestamp=time.time(),
        )])

    # Registration order is intentionally low-then-high to prove ordering does not rescue
    # the contract; only priority should decide the winner here.
    engine.register_agent(_FactAgent("noisy_low", priority=1, response_fn=emit_low))
    engine.register_agent(_FactAgent("authoritative_high", priority=10, response_fn=emit_high))

    ctx = _context()
    response = await engine.process_turn(ctx)

    winning = ctx.blackboard.get_fact("budget", "primary")
    assert winning is not None, "the fact should exist on the blackboard"
    assert winning.value == "authoritative_high_priority", (
        "INV-9 violated: higher-priority fact must win regardless of confidence "
        f"(got {winning.value!r} from a lower-priority/higher-confidence agent)"
    )

    # And the merged response must reflect the same winner.
    final_budget = [f for f in response.facts if f.type == "budget" and f.key == "primary"]
    assert any(f.value == "authoritative_high_priority" for f in final_budget), (
        "merged response.facts must carry the higher-priority value"
    )
