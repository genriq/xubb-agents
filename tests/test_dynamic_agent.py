"""
Regression tests for DynamicAgent v2.2 hardening items.

Covers:
- S-1: `expiry` / `action_label` requested by schemas but never parsed.
- A-2: Event/Fact timestamps must be session-relative (INV-13), not wall-clock.
- A-3: LLM-supplied `confidence` must be coerced/clamped to [0,1] before it
       reaches AgentInsight (ge=0, le=1), defaulting to 1.0 on failure.

Fixtures are LOCAL to this file (no conftest edits). The LLM is mocked so no
network is hit.
"""

import asyncio
import time

import pytest

from xubb_agents.library.dynamic import DynamicAgent
from xubb_agents.core.models import (
    AgentContext,
    TranscriptSegment,
    TriggerType,
)


# ---------------------------------------------------------------------------
# Local test helpers / fixtures
# ---------------------------------------------------------------------------

class FakeLLM:
    """Minimal stand-in for the engine-injected LLM client.

    `generate_json` returns a pre-canned dict, mimicking a parsed JSON response.
    """

    def __init__(self, result):
        self._result = result
        self.calls = []

    async def generate_json(self, model=None, messages=None, **kwargs):
        self.calls.append({"model": model, "messages": messages})
        return self._result


def make_agent(result, *, output_format="default_v2", config_extra=None):
    """Build a DynamicAgent with a fake LLM that returns `result`."""
    config = {
        "id": "agent_test",
        "name": "Test Agent",
        "text": "You are a test agent.",
        "output_format": output_format,
        "trigger_config": {"cooldown": 0},
    }
    if config_extra:
        config.update(config_extra)
    agent = DynamicAgent(config)
    agent.llm = FakeLLM(result)
    return agent


def make_context(segments=None, **overrides):
    """Build a minimal AgentContext.

    Segment timestamps are session-relative seconds (the documented convention).
    """
    if segments is None:
        segments = [
            TranscriptSegment(speaker="USER", text="Hello", timestamp=1.0),
            TranscriptSegment(speaker="USER", text="What's the budget?", timestamp=42.0),
        ]
    params = dict(
        session_id="sess_1",
        recent_segments=segments,
        trigger_type=TriggerType.TURN_BASED,
    )
    params.update(overrides)
    return AgentContext(**params)


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# A-3 — confidence coercion / clamping
# ---------------------------------------------------------------------------

class TestConfidenceCoercion:
    def test_coerce_confidence_clamps_above_one(self):
        assert DynamicAgent._coerce_confidence(1.5) == 1.0

    def test_coerce_confidence_clamps_below_zero(self):
        assert DynamicAgent._coerce_confidence(-0.3) == 0.0

    def test_coerce_confidence_non_numeric_defaults_to_one(self):
        assert DynamicAgent._coerce_confidence("high") == 1.0

    def test_coerce_confidence_none_defaults_to_one(self):
        assert DynamicAgent._coerce_confidence(None) == 1.0

    def test_coerce_confidence_numeric_string_passes(self):
        assert DynamicAgent._coerce_confidence("0.42") == pytest.approx(0.42)

    def test_coerce_confidence_in_range_unchanged(self):
        assert DynamicAgent._coerce_confidence(0.73) == pytest.approx(0.73)

    def test_out_of_range_confidence_yields_valid_insight(self):
        """The headline A-3 regression: 1.5 must NOT produce a validation ERROR."""
        result = {"has_insight": True, "content": "Budget looks tight", "confidence": 1.5}
        agent = make_agent(result)
        resp = run(agent.evaluate(make_context()))
        assert len(resp.insights) == 1
        insight = resp.insights[0]
        assert insight.confidence == 1.0
        # Not an ERROR insight — the good insight survived.
        assert insight.content == "Budget looks tight"

    def test_string_confidence_yields_valid_insight(self):
        result = {"has_insight": True, "content": "Note this", "confidence": "very high"}
        agent = make_agent(result)
        resp = run(agent.evaluate(make_context()))
        assert len(resp.insights) == 1
        assert resp.insights[0].confidence == 1.0


# ---------------------------------------------------------------------------
# S-1 — expiry / action_label parse-through
# ---------------------------------------------------------------------------

class TestExpiryActionLabel:
    def test_v2_raw_expiry_reaches_insight(self):
        """v2_raw schema instructs the model to return `expiry`; it must land."""
        result = {
            "insight": {
                "type": "warning",
                "content": "Time-sensitive",
                "confidence": 0.8,
                "expiry": 30,
            }
        }
        agent = make_agent(result, output_format="v2_raw")
        resp = run(agent.evaluate(make_context()))
        assert len(resp.insights) == 1
        assert resp.insights[0].expiry == 30

    def test_action_label_reaches_insight(self):
        result = {
            "has_insight": True,
            "content": "Consider this",
            "action_label": "Apply",
        }
        agent = make_agent(result)
        resp = run(agent.evaluate(make_context()))
        assert len(resp.insights) == 1
        assert resp.insights[0].action_label == "Apply"

    def test_missing_expiry_uses_model_default(self):
        """No expiry supplied → AgentInsight default (15) stands."""
        result = {"has_insight": True, "content": "Plain insight"}
        agent = make_agent(result)
        resp = run(agent.evaluate(make_context()))
        assert len(resp.insights) == 1
        assert resp.insights[0].expiry == 15
        assert resp.insights[0].action_label is None

    def test_bad_expiry_does_not_crash_insight(self):
        """Non-numeric / non-positive expiry falls back to the default, never crashes."""
        result = {
            "insight": {
                "type": "suggestion",
                "content": "Resilient",
                "expiry": "soon",
            }
        }
        agent = make_agent(result, output_format="v2_raw")
        resp = run(agent.evaluate(make_context()))
        assert len(resp.insights) == 1
        assert resp.insights[0].expiry == 15  # default applied

    def test_coerce_expiry_helpers(self):
        assert DynamicAgent._coerce_expiry(None) is None
        assert DynamicAgent._coerce_expiry("soon") is None
        assert DynamicAgent._coerce_expiry(0) is None
        assert DynamicAgent._coerce_expiry(-5) is None
        assert DynamicAgent._coerce_expiry("20") == 20
        assert DynamicAgent._coerce_expiry(12.7) == 12

    def test_coerce_action_label_helpers(self):
        assert DynamicAgent._coerce_action_label(None) is None
        assert DynamicAgent._coerce_action_label("   ") is None
        assert DynamicAgent._coerce_action_label("  Go  ") == "Go"


# ---------------------------------------------------------------------------
# A-2 — session-relative timestamps (INV-13)
# ---------------------------------------------------------------------------

class TestSessionRelativeTimestamps:
    def test_event_timestamp_is_session_relative_not_epoch(self):
        result = {
            "has_insight": False,
            "events": [{"name": "question_detected", "payload": {}}],
        }
        agent = make_agent(result)
        # Latest segment timestamp = 42.0 → that's "now" in session-relative seconds.
        resp = run(agent.evaluate(make_context()))
        assert len(resp.events) == 1
        ts = resp.events[0].timestamp
        assert ts == 42.0
        # Definitely not a wall-clock epoch.
        assert ts < 1_000_000_000

    def test_fact_timestamp_is_session_relative_not_epoch(self):
        result = {
            "has_insight": False,
            "facts": [{"type": "budget", "key": "primary", "value": 50000, "confidence": 0.9}],
        }
        agent = make_agent(result)
        resp = run(agent.evaluate(make_context()))
        assert len(resp.facts) == 1
        ts = resp.facts[0].timestamp
        assert ts == 42.0
        assert ts < 1_000_000_000

    def test_no_segments_falls_back_to_zero_not_epoch(self):
        """Documented A-2 limitation: empty window → 0.0, never wall-clock."""
        result = {
            "has_insight": False,
            "events": [{"name": "tick", "payload": {}}],
        }
        agent = make_agent(result)
        before = time.time()
        resp = run(agent.evaluate(make_context(segments=[])))
        assert len(resp.events) == 1
        ts = resp.events[0].timestamp
        assert ts == 0.0
        # Crucially, it is NOT an epoch close to wall-clock.
        assert ts < before

    def test_session_now_uses_max_segment_timestamp(self):
        ctx = make_context(segments=[
            TranscriptSegment(speaker="USER", text="a", timestamp=5.0),
            TranscriptSegment(speaker="USER", text="b", timestamp=3.0),
            TranscriptSegment(speaker="USER", text="c", timestamp=9.5),
        ])
        agent = make_agent({"has_insight": False})
        assert agent._session_now(ctx) == 9.5
