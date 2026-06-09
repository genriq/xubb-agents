"""
Regression / coverage tests for `utils/tracing.py` (T-1, tracer half).

`StructuredLogTracer` shipped with ZERO test coverage. The D3 fix added v2
fields to the per-step trace (`variable_updates`, `events_emitted`,
`facts_count`, `queue_pushes`, `memory_updates_keys`). These tests:

1. Drive the tracer through a representative turn lifecycle
   (`on_turn_start` -> `on_agent_finish` -> `on_turn_end`) and assert the
   emitted trace carries those v2 fields with the documented shapes.
2. Assert the trace is JSON-serializable and that the `TURN_TRACE:`-prefixed
   log line parses back to the same dict.
3. Assert the emitted schema matches the keys `tools/debugger.html` consumes
   (`steps[]`, `final_state_updates`, `trigger`, insight fields, etc.).

It also documents a schema mismatch between what the tracer emits for
per-step `state_updates` (a dict) and what `debugger.html` consumes (a list
of keys) — flagged here as a finding for DBG-1; the debugger is NOT touched.

Fixtures are LOCAL to this file (no conftest edits). Nothing here hits the
network or the engine; we construct minimal model objects directly.
"""

import asyncio
import json
import re

import pytest

from xubb_agents.utils.tracing import StructuredLogTracer
from xubb_agents.core.models import (
    AgentContext,
    AgentResponse,
    AgentInsight,
    InsightType,
    TranscriptSegment,
    TriggerType,
    Event,
    Fact,
)


# ---------------------------------------------------------------------------
# Local helpers / fixtures
# ---------------------------------------------------------------------------

def run(coro):
    return asyncio.run(coro)


def make_context(**overrides):
    """A minimal-but-representative AgentContext for a turn start."""
    params = dict(
        session_id="sess_trace_1",
        recent_segments=[
            TranscriptSegment(speaker="USER", text="Hello", timestamp=1.0),
            TranscriptSegment(speaker="USER", text="What's the budget?", timestamp=42.0),
        ],
        shared_state={"legacy_key": "legacy_value"},
        trigger_type=TriggerType.EVENT,
        trigger_metadata={"event_name": "question_detected"},
        language_directive="en",
        user_context="Sales rep, goal: close deal",
        rag_docs=["doc chunk one", "doc chunk two"],
        turn_count=5,
        phase=2,
    )
    params.update(overrides)
    return AgentContext(**params)


def make_rich_response():
    """An AgentResponse exercising every v1 + v2 field the tracer reads."""
    return AgentResponse(
        source_agent_id="agent_test",
        insights=[
            AgentInsight(
                agent_id="agent_test",
                agent_name="Test Agent",
                type=InsightType.SUGGESTION,
                content="Ask about the timeline.",
                confidence=0.8,
                metadata={"zone": "A"},
            )
        ],
        state_updates={"memory_notes": "noted", "phase": "discovery"},
        variable_updates={"sentiment": 0.7, "topic": "pricing"},
        events=[
            Event(
                name="objection_raised",
                payload={"kind": "price"},
                source_agent="agent_test",
                timestamp=42.0,
            )
        ],
        facts=[
            Fact(
                type="budget",
                key="primary",
                value=50000,
                confidence=0.9,
                source_agent="agent_test",
                timestamp=42.0,
            ),
            Fact(
                type="timeline",
                value="Q3",
                confidence=0.6,
                source_agent="agent_test",
                timestamp=42.0,
            ),
        ],
        queue_pushes={"pending_questions": [{"text": "q1"}, {"text": "q2"}]},
        memory_updates={"counter": 4, "last_action": "suggested"},
        data={"ui_action": "highlight"},
        debug_info={"prompt_messages": [{"role": "user", "content": "hi"}]},
    )


def drive_turn(tracer, context, agent_name, response, *,
               agent_duration=0.05, turn_duration=0.12, final_response=None):
    """Run a full turn lifecycle through the tracer.

    Returns the live `current_trace` dict after `on_turn_end`.
    """
    final_response = final_response if final_response is not None else response

    async def _go():
        await tracer.on_turn_start(context)
        await tracer.on_agent_start(agent_name, context)
        await tracer.on_agent_finish(agent_name, response, agent_duration)
        await tracer.on_turn_end(final_response, turn_duration)

    run(_go())
    return tracer.current_trace


def emitted_trace_from_caplog(caplog):
    """Parse the JSON payload out of the single TURN_TRACE: log line."""
    lines = [r.getMessage() for r in caplog.records]
    trace_lines = [l for l in lines if l.startswith("TURN_TRACE:")]
    assert len(trace_lines) == 1, f"expected exactly one TURN_TRACE line, got {trace_lines}"
    match = re.match(r"TURN_TRACE:\s*(\{.*\})\s*$", trace_lines[0], re.DOTALL)
    assert match, "TURN_TRACE line did not match the expected 'TURN_TRACE: {...}' shape"
    return json.loads(match.group(1))


# ---------------------------------------------------------------------------
# Lifecycle + v2 field presence
# ---------------------------------------------------------------------------

class TestTurnLifecycle:
    def test_turn_start_seeds_trace_header(self):
        tracer = StructuredLogTracer()
        ctx = make_context()
        run(tracer.on_turn_start(ctx))
        t = tracer.current_trace

        assert t["session_id"] == "sess_trace_1"
        # str-Enum serializes to its bare value, which is what the debugger reads.
        assert t["trigger"] == TriggerType.EVENT
        assert t["input_preview"] == "What's the budget?"
        assert t["speaker"] == "USER"
        assert t["initial_shared_state"] == {"legacy_key": "legacy_value"}
        assert len(t["transcript_history"]) == 2
        assert t["steps"] == []

    def test_agent_start_is_noop(self):
        """on_agent_start intentionally records nothing (volume control)."""
        tracer = StructuredLogTracer()
        ctx = make_context()
        run(tracer.on_turn_start(ctx))
        run(tracer.on_agent_start("agent_test", ctx))
        assert tracer.current_trace["steps"] == []

    def test_agent_finish_records_v2_fields(self):
        tracer = StructuredLogTracer()
        ctx = make_context()
        resp = make_rich_response()
        run(tracer.on_turn_start(ctx))
        run(tracer.on_agent_finish("agent_test", resp, 0.05))

        assert len(tracer.current_trace["steps"]) == 1
        step = tracer.current_trace["steps"][0]

        # D3 v2 fields — exact names + documented shapes.
        assert step["variable_updates"] == ["sentiment", "topic"]      # keys only
        assert step["events_emitted"] == ["objection_raised"]          # event names
        assert step["facts_count"] == 2                                # count
        assert step["queue_pushes"] == {"pending_questions": 2}        # name -> len
        assert sorted(step["memory_updates_keys"]) == ["counter", "last_action"]

    def test_agent_finish_records_insights_and_status(self):
        tracer = StructuredLogTracer()
        ctx = make_context()
        resp = make_rich_response()
        run(tracer.on_turn_start(ctx))
        run(tracer.on_agent_finish("agent_test", resp, 0.05))
        step = tracer.current_trace["steps"][0]

        assert step["agent"] == "agent_test"
        assert step["status"] == "success"
        assert step["latency_ms"] == 50.0
        assert step["insights"][0]["type"] == InsightType.SUGGESTION
        assert step["insights"][0]["content"] == "Ask about the timeline."
        assert step["insights"][0]["confidence"] == 0.8
        # v1 + sidecar fields still flow through.
        assert step["state_updates"] == {"memory_notes": "noted", "phase": "discovery"}
        assert step["data"] == {"ui_action": "highlight"}
        assert "debug_info" in step

    def test_agent_finish_no_response_marks_no_response(self):
        tracer = StructuredLogTracer()
        ctx = make_context()
        run(tracer.on_turn_start(ctx))
        run(tracer.on_agent_finish("silent_agent", None, 0.01))
        step = tracer.current_trace["steps"][0]
        assert step["status"] == "no_response"
        assert step["insights"] == []
        # v2 fields are omitted entirely when there's no response.
        for k in ("variable_updates", "events_emitted", "facts_count",
                  "queue_pushes", "memory_updates_keys"):
            assert k not in step

    def test_empty_response_omits_v2_fields(self):
        """A response with empty containers should not emit empty v2 keys."""
        tracer = StructuredLogTracer()
        ctx = make_context()
        run(tracer.on_turn_start(ctx))
        run(tracer.on_agent_finish("agent_test", AgentResponse(), 0.01))
        step = tracer.current_trace["steps"][0]
        assert step["status"] == "success"
        for k in ("variable_updates", "events_emitted", "facts_count",
                  "queue_pushes", "memory_updates_keys", "state_updates", "data"):
            assert k not in step

    def test_agent_error_records_error_step(self):
        tracer = StructuredLogTracer()
        ctx = make_context()
        run(tracer.on_turn_start(ctx))
        run(tracer.on_agent_error("boom_agent", ValueError("kaboom")))
        step = tracer.current_trace["steps"][0]
        assert step["status"] == "error"
        assert step["agent"] == "boom_agent"
        assert "kaboom" in step["error"]

    def test_turn_end_finalizes_trace(self):
        tracer = StructuredLogTracer()
        ctx = make_context()
        resp = make_rich_response()
        t = drive_turn(tracer, ctx, "agent_test", resp, turn_duration=0.12)

        assert t["total_latency_ms"] == 120.0
        assert t["final_insight_count"] == 1
        assert t["final_state_updates"] == {"memory_notes": "noted", "phase": "discovery"}


# ---------------------------------------------------------------------------
# JSON-serializability + the Golden Log Line
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_turn_end_emits_parseable_turn_trace_line(self, caplog):
        tracer = StructuredLogTracer()
        ctx = make_context()
        resp = make_rich_response()
        with caplog.at_level("INFO", logger="AgentTracer"):
            drive_turn(tracer, ctx, "agent_test", resp)

        parsed = emitted_trace_from_caplog(caplog)
        # Round-trips cleanly and matches the live trace dict.
        assert parsed["session_id"] == "sess_trace_1"
        assert parsed["steps"][0]["facts_count"] == 2
        assert parsed["steps"][0]["events_emitted"] == ["objection_raised"]

    def test_full_trace_is_json_serializable(self):
        tracer = StructuredLogTracer()
        ctx = make_context()
        resp = make_rich_response()
        t = drive_turn(tracer, ctx, "agent_test", resp)
        # default=str is the tracer's safety net; assert the trace serializes
        # even WITHOUT it, i.e. it's natively JSON-clean.
        json.dumps(t)  # must not raise

    def test_trigger_serializes_to_bare_string(self, caplog):
        """debugger.html's triggerClass map keys on bare 'event'/'turn_based'."""
        tracer = StructuredLogTracer()
        ctx = make_context(trigger_type=TriggerType.EVENT)
        resp = make_rich_response()
        with caplog.at_level("INFO", logger="AgentTracer"):
            drive_turn(tracer, ctx, "agent_test", resp)
        parsed = emitted_trace_from_caplog(caplog)
        # Must be the bare value, NOT "TriggerType.EVENT".
        assert parsed["trigger"] == "event"
        assert isinstance(parsed["trigger"], str)

    def test_insight_type_enum_serializes_to_bare_string(self, caplog):
        """debugger.html lowercases insight.type against a bare-string map."""
        tracer = StructuredLogTracer()
        ctx = make_context()
        resp = make_rich_response()
        with caplog.at_level("INFO", logger="AgentTracer"):
            drive_turn(tracer, ctx, "agent_test", resp)
        parsed = emitted_trace_from_caplog(caplog)
        assert parsed["steps"][0]["insights"][0]["type"] == "suggestion"


# ---------------------------------------------------------------------------
# Schema compatibility with tools/debugger.html
# ---------------------------------------------------------------------------

class TestDebuggerSchemaCompat:
    """Assert the emitted trace carries the top-level + step keys the
    debugger UI reads. (Reference: tools/debugger.html.)"""

    def _emit(self, caplog):
        tracer = StructuredLogTracer()
        ctx = make_context()
        resp = make_rich_response()
        with caplog.at_level("INFO", logger="AgentTracer"):
            drive_turn(tracer, ctx, "agent_test", resp)
        return emitted_trace_from_caplog(caplog)

    def test_top_level_keys_present(self, caplog):
        t = self._emit(caplog)
        # Keys read directly by debugger.html templates.
        for key in (
            "timestamp_start", "trigger", "input_preview", "speaker",
            "trigger_metadata", "user_context", "language_directive",
            "initial_shared_state", "rag_docs", "transcript_history",
            "total_latency_ms", "session_id", "final_state_updates", "steps",
        ):
            assert key in t, f"debugger consumes trace.{key} but it is missing"

    def test_transcript_history_shape(self, caplog):
        t = self._emit(caplog)
        seg = t["transcript_history"][0]
        # debugger reads seg.speaker / seg.text
        assert "speaker" in seg and "text" in seg

    def test_step_keys_present(self, caplog):
        t = self._emit(caplog)
        step = t["steps"][0]
        for key in ("agent", "latency_ms", "status", "insights"):
            assert key in step, f"debugger consumes step.{key} but it is missing"

    def test_insight_keys_present(self, caplog):
        t = self._emit(caplog)
        insight = t["steps"][0]["insights"][0]
        # debugger reads insight.type / insight.confidence / insight.content / insight.metadata
        for key in ("type", "confidence", "content", "metadata"):
            assert key in insight, f"debugger consumes insight.{key} but it is missing"

    def test_final_state_updates_is_dict_for_debugger(self, caplog):
        """debugger iterates final_state_updates as (val, key) — a dict. OK."""
        t = self._emit(caplog)
        assert isinstance(t["final_state_updates"], dict)

    def test_dbg1_debugger_renders_step_state_updates_as_dict(self):
        """DBG-1 (RESOLVED): tools/debugger.html now renders the per-step
        trace correctly against the shape the tracer actually emits.

        The tracer emits per-step `state_updates` as a DICT
        (`response.state_updates`). The debugger previously rendered it as a
        LIST of keys (`v-for="key in step.state_updates"` guarded by
        `step.state_updates.length`); a JS object has no `.length`, so that
        block silently rendered nothing. DBG-1 fixes the debugger to iterate
        the dict (`v-for="(val, key) in step.state_updates"` guarded by
        `Object.keys(...).length`) and to render the v2 per-step fields.

        This test (a) confirms the tracer still emits `state_updates` as a
        dict, and (b) asserts the debugger template no longer uses the buggy
        `.length` guard on `step.state_updates` and now references every v2
        per-step field name the tracer emits.
        """
        import pathlib

        # (a) Tracer-side: per-step state_updates remains a dict.
        tracer = StructuredLogTracer()
        ctx = make_context()
        resp = make_rich_response()
        run(tracer.on_turn_start(ctx))
        run(tracer.on_agent_finish("agent_test", resp, 0.05))
        step = tracer.current_trace["steps"][0]
        assert isinstance(step["state_updates"], dict)

        # (b) Debugger-side: assert the template matches the emitted shape.
        debugger = (
            pathlib.Path(__file__).resolve().parent.parent
            / "tools" / "debugger.html"
        )
        html = debugger.read_text(encoding="utf-8")

        # The buggy list-shape guard on step.state_updates must be gone.
        assert "step.state_updates.length" not in html, (
            "debugger still guards step.state_updates with .length (dict has no "
            ".length) -> the DBG-1 shape mismatch is unresolved"
        )
        # The per-step state_updates dict must be iterated as (val, key).
        assert 'v-for="(val, key) in step.state_updates"' in html

        # All v2 per-step fields the tracer emits must be referenced by the UI.
        for field in (
            "step.variable_updates",
            "step.events_emitted",
            "step.facts_count",
            "step.queue_pushes",
            "step.memory_updates_keys",
        ):
            assert field in html, (
                f"debugger does not render {field}, but the tracer emits it"
            )
