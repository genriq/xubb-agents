# Xubb Agents Framework v2.1.1
## Bugfix & Polish Specification

**Version:** 2.1.1
**Status:** Locked (Rev 4)
**Date:** March 19, 2026
**Scope:** Bugs, test gaps, and performance waste identified during comprehensive v2.1 code review
**Compatibility:** No schema or breaking framework API changes. Fixes are internal behavioral normalizations plus additive model/observability improvements.
**Baseline:** Audit performed against commit `4afd2a9` (current `main`, post-v2.1 hardening)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Framework Invariants](#2-framework-invariants)
3. [Scope & Goals](#3-scope--goals)
4. [Release Classification](#4-release-classification)
5. [Medium-Severity Bugs](#5-medium-severity-bugs)
6. [Low-Severity Bugs](#6-low-severity-bugs)
7. [Performance & Code Quality](#7-performance--code-quality)
8. [Test Gaps](#8-test-gaps)
9. [Implementation Plan](#9-implementation-plan)
10. [Testing Strategy](#10-testing-strategy)
11. [Migration Notes](#11-migration-notes)
12. [Release Gates & Success Metrics](#12-release-gates--success-metrics)
13. [Appendix A: Full Issue Index](#appendix-a-full-issue-index)

---

## 1. Executive Summary

A comprehensive review of the v2.1 codebase — including all source files, tests, schemas, and documentation — identified **4 bugs**, **3 performance/quality issues**, and **1 test gap** that reduce correctness, waste resources, or mask real behavior.

### Headline Numbers

| Category | Medium | Low | Total |
|----------|--------|-----|-------|
| Bugs | 3 | 1 | 4 |
| Performance/Quality | 1 Medium | 2 Low | 3 |
| Test Gaps | 1 Medium | — | 1 |
| **Total** | **5** | **3** | **8** |

No critical or high-severity issues were found — v2.1 hardening was effective.

### Impact Summary

- **3 medium bugs** cause silent subscriber skips (B1), stale state in the Phase 2 event path (B2), and an observability contract gap where `on_chain_error` never fires (B5).
- **1 medium performance issue** wastes measurable input characters per LLM call across every agent evaluation (D1).
- **1 medium test gap** masks incorrect Phase 2 subscriber behavior via coincidental cooldown timing (T1).

### Guiding Principles for v2.1.1

1. **Surgical fixes** — no refactoring, no new features, no architecture changes.
2. **Every fix gets a regression test** — no exceptions.
3. **Additive over breaking** — where a fix touches host-visible response fields, prefer adding a new field over changing an existing one.
4. **Performance improvements are measured** — prompt size reductions are verified empirically before/after, not estimated.

---

## 2. Framework Invariants

These invariants were established in v2.1 ([SPEC_V2_1_HARDENING.md §2](SPEC_V2_1_HARDENING.md#2-framework-invariants)). The bugs in this spec violate or weaken three of them.

| ID | Invariant | Status in v2.1.1 |
|----|-----------|-------------------|
| **INV-2** | Snapshot state is **immutable** from the perspective of peer agents in the same phase. | **Weakened** (B2 — Phase 2 snapshot does not reflect merged post-Phase-1 state for the v1 `shared_state` compatibility path. v2 agents reading `blackboard.variables` are unaffected.) |
| **INV-9** *(new)* | An agent selected for execution in a phase must **actually execute or be reported as skipped**. Silent no-ops violate observability. | **Violated** (B1 — Phase 2 subscribers silently return `None` from `process()`) |
| **INV-10** *(new)* | The `on_chain_error` callback fires when the engine's top-level `process_turn` encounters an unrecoverable error. | **Violated** (B5 — callback defined but never called) |

All other v2.1 invariants (INV-1 through INV-8) remain intact.

---

## 3. Scope & Goals

### 3.1 In Scope

| Area | What Changes |
|------|-------------|
| Phase 2 subscriber selection | Validate `TriggerType.EVENT` before scheduling |
| Phase 2 v1 compatibility | Re-sync `shared_state` before Phase 2 execution |
| Prompt construction | Eliminate leading whitespace waste |
| Jinja2 environment | Move to class-level singleton |
| Tracer | Capture v2 response fields |
| `on_chain_error` | Wire into engine top-level error path |
| `final_response` | Add `memory_updates_by_agent` field (additive) |
| Test suite | Fix `test_phase2_triggered_by_events` to test actual event behavior |

### 3.2 Out of Scope

| Area | Rationale |
|------|-----------|
| `AgentConfig` → Pydantic | Deferred to v2.2 per SPEC_V2_1_HARDENING §10.3 |
| `collections.deque` for queues | Deferred to v2.2 per SPEC_V2_1_HARDENING §12 |
| `default.json` `"message"` → `"content"` rename | Would break existing v1 agents |
| Differentiated retry policies | v2.2 concern per SPEC_V2_1_HARDENING §6.2 |

---

## 4. Release Classification

### 4.1 Must Land in v2.1.1

These issues cause silent incorrect behavior or waste measurable resources.

| ID | Issue | Invariant |
|----|-------|-----------|
| B1 | Phase 2 subscribers without `TriggerType.EVENT` silently skip | INV-9 |
| B2 | Phase 2 v1 agents see stale `shared_state` | INV-2 |
| B5 | `on_chain_error` callback never fires | INV-10 |
| D1 | Prompt leading whitespace wastes measurable input characters per call | — |
| T1 | `test_phase2_triggered_by_events` passes via cooldown coincidence | — |

### 4.2 Should Land in v2.1.1

These improve correctness and observability but are not silent-failure risks.

| ID | Issue |
|----|-------|
| B4 | `final_response.memory_updates` is flat/lossy (additive fix) |
| D2 | `SandboxedEnvironment` created per call |
| D3 | Tracer doesn't capture v2 fields |

---

## 5. Medium-Severity Bugs

### 5.1 B1 — Phase 2 Subscribers Silently Skip Without `TriggerType.EVENT`

**File:** `core/engine.py` lines 94–101, 250–256
**Invariant:** INV-9

#### Problem

`get_event_subscribers()` selects agents by checking `subscribed_events` only:

```python
def get_event_subscribers(self, event_names: List[str]) -> List[BaseAgent]:
    subscribers = []
    for agent in self.agents:
        subscribed = getattr(agent.config, 'subscribed_events', None) or []
        if any(event_name in subscribed for event_name in event_names):
            subscribers.append(agent)
    return subscribers
```

It does **not** verify that the agent has `TriggerType.EVENT` in its `trigger_types`. The agent passes eligibility, is scheduled for Phase 2, but `BaseAgent.process()` checks `context.trigger_type not in self.config.trigger_types` and silently returns `None`.

```
Config: subscribed_events=["question_detected"], trigger_types=[TriggerType.TURN_BASED]
Engine: Selects agent as Phase 2 subscriber ✓
Engine: Sets context.trigger_type = TriggerType.EVENT ✓
Agent:  process() → EVENT not in [TURN_BASED] → return None (silent skip)
Result: No callback, no log, no on_agent_skipped — agent vanishes
```

#### Impact

- **Configuration trap**: An agent with `subscribed_events` but without `TriggerType.EVENT` appears to work (no crash) but never fires on events. This is a common setup mistake when using DynamicAgent with `mode: "turn_based"` and adding `subscribed_events` as an afterthought.
- **Observability hole**: No `on_agent_skipped` callback fires for the silent return, because the skip happens inside `process()`, not during the engine's eligibility check.

#### Why This Wasn't Caught

All tests use `MockAgent` which defaults to `trigger_types=[TriggerType.TURN_BASED, TriggerType.EVENT]`, so the mismatch never occurs in the test suite.

#### Design Decision: Where to Fix

| Option | Approach | Tradeoff |
|--------|----------|----------|
| A. Fix in `get_event_subscribers` | Filter out agents without `TriggerType.EVENT` | Engine enforces; `on_agent_skipped` fires correctly |
| B. Fix in `process()` | Remove the redundant trigger-type check | Agent trusts engine; but breaks defense-in-depth |
| C. Fix in `DynamicAgent` parser | Auto-add `TriggerType.EVENT` when `subscribed_events` is non-empty | Fixes DynamicAgent only; custom BaseAgent subclasses still affected |

**Decision: Option A + C (complementary).** The engine is the source of truth for routing (Option A). Additionally, DynamicAgent applies a convenience normalization (Option C) so that configuration-driven agents get correct defaults without requiring users to remember the `TriggerType.EVENT` requirement. These are independent, layered fixes — the engine guard is authoritative; the DynamicAgent normalization is a usability convenience.

#### Required Fix

**Step 1 — `engine.py` (`get_event_subscribers`) — authoritative engine-level guard:**

```python
def get_event_subscribers(self, event_names: List[str]) -> List[BaseAgent]:
    """Get agents subscribed to any of the given events (v2).

    Only returns agents that have TriggerType.EVENT in their trigger_types.
    Agents with subscribed_events but without EVENT trigger type are
    configuration errors — they are excluded from routing and a warning
    is logged. This is a configuration-time exclusion, not a runtime skip.
    """
    subscribers = []
    for agent in self.agents:
        subscribed = getattr(agent.config, 'subscribed_events', None) or []
        if any(event_name in subscribed for event_name in event_names):
            if TriggerType.EVENT in agent.config.trigger_types:
                subscribers.append(agent)
            else:
                logger.warning(
                    f"Agent '{agent.config.name}' has subscribed_events "
                    f"{subscribed} but TriggerType.EVENT is not in "
                    f"trigger_types {agent.config.trigger_types}. "
                    f"Skipping for Phase 2."
                )
    return subscribers
```

**Step 2 — `library/dynamic.py` (`__init__` trigger parsing) — DynamicAgent convenience normalization:**

When `subscribed_events` is non-empty and `TriggerType.EVENT` is not already present in `trigger_types`, auto-add it. This applies **only to DynamicAgent** — custom `BaseAgent` subclasses are not auto-modified and must set their own trigger types correctly. The engine-level guard (Step 1) catches any misconfigured custom agents.

```python
# After trigger_types parsing (line ~53):
if subscribed_events and TriggerType.EVENT not in trigger_types:
    trigger_types.append(TriggerType.EVENT)
```

#### Test

```python
def test_subscriber_without_event_trigger_type_is_excluded(self, engine, sample_context):
    """Subscriber with subscribed_events but no TriggerType.EVENT should be excluded."""
    def emit_event(context, agent):
        return AgentResponse(
            events=[Event(
                name="test_event", payload={},
                source_agent=agent.config.id, timestamp=time.time()
            )]
        )

    emitter = MockAgent("emitter", response_fn=emit_event)

    # Subscriber has subscribed_events but only TURN_BASED trigger type
    misconfigured = MockAgent(
        "misconfigured",
        subscribed_events=["test_event"],
        trigger_types=[TriggerType.TURN_BASED]  # No EVENT
    )

    engine.register_agent(emitter)
    engine.register_agent(misconfigured)

    await engine.process_turn(sample_context)

    # Validates exclusion from Phase 2: misconfigured ran once (Phase 1,
    # TURN_BASED) but was not selected for Phase 2 despite subscribed_events.
    assert misconfigured.call_count == 1

def test_dynamic_agent_auto_adds_event_trigger_type():
    """DynamicAgent with subscribed_events should auto-add TriggerType.EVENT."""
    config = {
        "name": "Auto Event",
        "text": "test",
        "trigger_config": {
            "mode": "turn_based",
            "subscribed_events": ["question_detected"]
        }
    }
    agent = DynamicAgent(config)
    assert TriggerType.EVENT in agent.config.trigger_types
    assert TriggerType.TURN_BASED in agent.config.trigger_types
```

---

### 5.2 B2 — Phase 2 v1 Agents See Stale `shared_state`

**File:** `core/engine.py` line 177
**Invariant:** INV-2

#### Problem

`_sync_state_to_legacy()` runs once at the top of `process_turn()`, before Phase 1. After Phase 1 merges update the blackboard (via `_merge_responses`), the blackboard's `variables` dict reflects the merged state, but `context.shared_state` is never re-synced.

```
Turn start:
  blackboard.variables = {"phase": "discovery"}
  _sync_state_to_legacy() → context.shared_state = {"phase": "discovery"}

Phase 1:
  Agent sets variable_updates={"phase": "closing"}
  _merge_responses → blackboard.variables = {"phase": "closing"}
  context.shared_state still = {"phase": "discovery"}  ← STALE

Phase 2:
  _run_phase creates snapshot with shared_state=deepcopy(context.shared_state)
  Phase 2 agents reading context.shared_state["phase"] see "discovery"
  Phase 2 agents reading context.blackboard.variables["phase"] see "closing"
```

#### Impact

- v1 agents running in Phase 2 (via event subscriptions) see stale `shared_state`.
- v2 agents reading `blackboard.variables` are unaffected (they see the correct post-Phase-1 state).
- Impact is low in practice because v1 agents rarely subscribe to events, but it violates the v1 compatibility contract and could cause subtle bugs in hybrid v1/v2 deployments.

#### Required Fix

Re-sync `shared_state` from the blackboard before Phase 2 execution.

```python
# engine.py, after Phase 1 merge, before Phase 2 execution (~line 241):
if all_events and self.max_phases >= 2:
    # Re-sync shared_state for v1 agents in Phase 2
    self._sync_state_to_legacy(context)
    ...
```

This is a one-line addition. The cost is negligible — `_sync_state_to_legacy` is a dict `.update()` call.

#### Test

```python
@pytest.mark.asyncio
async def test_phase2_agents_see_updated_shared_state(self, engine, sample_context):
    """Phase 2 agents should see Phase 1's state updates in shared_state."""

    def emit_and_update(context, agent):
        return AgentResponse(
            variable_updates={"phase": "closing"},
            events=[Event(
                name="phase_changed", payload={},
                source_agent=agent.config.id, timestamp=time.time()
            )]
        )

    captured_state = {}

    def capture_shared_state(context, agent):
        captured_state["phase"] = context.shared_state.get("phase")
        return AgentResponse()

    emitter = MockAgent("emitter", response_fn=emit_and_update)
    subscriber = MockAgent(
        "subscriber",
        subscribed_events=["phase_changed"],
        response_fn=capture_shared_state,
        trigger_types=[TriggerType.EVENT]
    )
    subscriber.config.cooldown = 0

    engine.register_agent(emitter)
    engine.register_agent(subscriber)

    sample_context.blackboard.set_var("phase", "discovery")
    await engine.process_turn(sample_context)

    # Phase 2 subscriber should see the Phase 1 update
    assert captured_state["phase"] == "closing"
```

---

### 5.3 B5 — `on_chain_error` Callback Never Fires

**File:** `core/engine.py` — `process_turn()` method
**Invariant:** INV-10

#### Problem

`on_chain_error` is defined on `AgentCallbackHandler` and documented in both specs, but `process_turn()` has no top-level try/except that invokes it. If the engine itself errors (e.g., during blackboard setup, sync, or finalization), the error propagates to the host with no callback notification.

This is not merely cosmetic. `on_chain_error` is the documented observability hook for engine-level failures. Production deployments that wire alerting or telemetry through callback handlers have a blind spot: agent-level errors fire `on_agent_error`, but an engine-level error (e.g., a crash during `_merge_responses` or `_sync_state_to_legacy`) produces no callback at all. The host receives an exception but the callback-driven monitoring pipeline sees nothing.

#### Required Fix

Wrap the `process_turn` body in a try/except that fires `on_chain_error` before re-raising:

```python
async def process_turn(self, context, ...) -> AgentResponse:
    try:
        # ... existing implementation ...
        return final_response
    except Exception as e:
        for cb in self.callbacks:
            try:
                await cb.on_chain_error(e)
            except Exception as cb_err:
                logger.error(f"Callback error on_chain_error: {cb_err}")
        raise  # Always re-raise — the host must see the error
```

**Note:** The `raise` is mandatory. `on_chain_error` is for observability, not error recovery. The host must receive the original exception.

#### Test

```python
@pytest.mark.asyncio
async def test_on_chain_error_fires_on_engine_failure(self):
    """on_chain_error should fire when process_turn itself errors."""

    class ErrorTracker(AgentCallbackHandler):
        def __init__(self):
            self.errors = []
        async def on_chain_error(self, error):
            self.errors.append(error)

    tracker = ErrorTracker()
    engine = AgentEngine(api_key="test", callbacks=[tracker])

    # Create a context that will cause engine to fail
    # (e.g., by patching _get_eligible_agents to raise)
    with patch.object(engine, '_get_eligible_agents', side_effect=RuntimeError("engine boom")):
        with pytest.raises(RuntimeError, match="engine boom"):
            await engine.process_turn(sample_context)

    assert len(tracker.errors) == 1
    assert str(tracker.errors[0]) == "engine boom"
```

---

## 6. Low-Severity Bugs

### 6.1 B4 — `final_response.memory_updates` Loses Agent Attribution

**File:** `core/engine.py` line 452

#### Problem

```python
if resp.memory_updates and agent_id:
    blackboard.update_memory(agent_id, resp.memory_updates)
    final_response.memory_updates.update(resp.memory_updates)  # flat merge
```

If Agent A sends `memory_updates={"counter": 1}` and Agent B sends `memory_updates={"counter": 5}`, the blackboard correctly stores per-agent memory, but `final_response.memory_updates` is a flat dict — Agent B's value overwrites Agent A's.

#### Impact

- Only affects consumers reading `final_response.memory_updates` directly (telemetry, host-side logging).
- The **blackboard** memory is correctly per-agent — this is a response-level reporting issue.

#### Design Decision: Additive Over Breaking

| Option | Approach | Tradeoff |
|--------|----------|----------|
| A. Change `memory_updates` shape | Key existing field by agent_id | Host-visible breaking change — consumers must update parsers |
| B. Add `memory_updates_by_agent` | New additive field alongside existing flat field | No breaking change; consumers can migrate at their own pace |

**Decision: Option B.** For a patch release, additive is safer. The existing `memory_updates` flat dict continues to work as before (last-write-wins). A new `memory_updates_by_agent` field provides the per-agent keyed view. Consumers adopt the new field when ready.

#### Required Fix

Add a `memory_updates_by_agent` field to the final response without changing the existing `memory_updates` behavior:

```python
if resp.memory_updates and agent_id:
    blackboard.update_memory(agent_id, resp.memory_updates)
    # Existing flat merge (backward compatible, last-write-wins)
    final_response.memory_updates.update(resp.memory_updates)
    # New per-agent keyed field (additive)
    if not hasattr(final_response, 'memory_updates_by_agent'):
        final_response.memory_updates_by_agent = {}
    if agent_id not in final_response.memory_updates_by_agent:
        final_response.memory_updates_by_agent[agent_id] = {}
    final_response.memory_updates_by_agent[agent_id].update(resp.memory_updates)
```

The `memory_updates_by_agent` field should also be added to the `AgentResponse` model with a default of `{}`. This field is intended for aggregated final responses from `process_turn()`; individual agent responses may leave it empty.

#### Test

```python
@pytest.mark.asyncio
async def test_memory_updates_by_agent_preserves_attribution(self, engine, sample_context):
    """memory_updates_by_agent should be keyed by agent_id."""

    def mem_a(context, agent):
        return AgentResponse(memory_updates={"counter": 1})

    def mem_b(context, agent):
        return AgentResponse(memory_updates={"counter": 5})

    agent_a = MockAgent("agent_a", response_fn=mem_a)
    agent_b = MockAgent("agent_b", response_fn=mem_b)
    engine.register_agent(agent_a)
    engine.register_agent(agent_b)

    response = await engine.process_turn(sample_context)

    # New additive field preserves per-agent attribution
    assert response.memory_updates_by_agent["agent_a"]["counter"] == 1
    assert response.memory_updates_by_agent["agent_b"]["counter"] == 5

    # Existing flat field still works (last-write-wins, backward compatible)
    assert "counter" in response.memory_updates
```

---

## 7. Performance & Code Quality

### 7.1 D1 — Prompt Leading Whitespace Wastes Measurable Input Per Call

**File:** `library/dynamic.py` lines 229–239
**Severity:** Medium (measurable cost at scale)

#### Problem

```python
        full_system_prompt = f"""
        {user_context_section}
        {language_section}
        {rendered_system_prompt}

        [YOUR MEMORY / SCRATCHPAD]
        {current_memory}
        {rag_section}
        {trigger_context}
        {self.json_instruction}
        """
```

The `f"""..."""` is inside a doubly-indented method. Every line of the prompt begins with 8 spaces of structural whitespace that serves no purpose for the LLM. For a typical prompt with 30–50 non-empty lines, this adds 240–400 wasted characters per call.

#### Impact

The exact token overhead depends on the tokenizer and prompt content. Rather than estimate, the fix should be verified empirically:

- **Before/after measurement**: Run a representative prompt through the tokenizer and compare token counts.
- **Expected savings**: Hundreds of wasted input characters eliminated per call. Across multiple agents per turn and many turns per session, the cumulative savings are material.

The fix also eliminates empty `\n\n` blocks for missing optional sections (context, RAG, trigger), which further reduces prompt noise.

#### Required Fix

Build the prompt as a list and join, eliminating structural whitespace:

```python
parts = []
if user_context_section:
    parts.append(user_context_section)
if language_section:
    parts.append(language_section)
parts.append(rendered_system_prompt)
parts.append(f"[YOUR MEMORY / SCRATCHPAD]\n{current_memory}")
if rag_section:
    parts.append(rag_section)
if trigger_context:
    parts.append(trigger_context)
if self.json_instruction:
    parts.append(self.json_instruction)

full_system_prompt = "\n\n".join(parts)
```

#### Test

```python
def test_prompt_has_no_leading_whitespace():
    """System prompt should not have structural leading whitespace."""
    config = {"name": "test", "text": "You are a test agent."}
    agent = DynamicAgent(config)
    # ... build a context and call evaluate ...
    # Assert the system message doesn't start with spaces
    system_msg = messages[0]["content"]
    for line in system_msg.split("\n"):
        if line.strip():  # non-empty lines
            assert not line.startswith("        "), f"Line has structural whitespace: {repr(line[:20])}"
```

---

### 7.2 D2 — `SandboxedEnvironment` Created Per Evaluation Call

**File:** `library/dynamic.py` line 190

#### Problem

```python
async def evaluate(self, context):
    ...
    _jinja_env = SandboxedEnvironment()  # new instance per call
    template = _jinja_env.from_string(self.system_prompt)
```

`SandboxedEnvironment()` creates a new Jinja2 environment with fresh parser, compiler, and sandbox configuration on every evaluation. Under typical load (5 agents × 10 turns/min), this creates 50 environment objects per minute, adding avoidable object churn and small per-call overhead.

#### Required Fix

Move to a class-level attribute:

```python
class DynamicAgent(BaseAgent):
    _jinja_env = SandboxedEnvironment()

    async def evaluate(self, context):
        ...
        template = self._jinja_env.from_string(self.system_prompt)
```

A shared environment is appropriate here because the environment configuration is immutable in this use case and templates are instantiated per call via `from_string()`. The `template.render()` call operates on the per-call template instance, not on shared mutable state.

---

### 7.3 D3 — Tracer Doesn't Capture v2 Response Fields

**File:** `utils/tracing.py` lines 48–68

#### Problem

`on_agent_finish` captures `state_updates`, `data`, and `debug_info`, but does not capture `variable_updates`, `events`, `facts`, `queue_pushes`, or `memory_updates`. The trace output is v1-shaped and missing the v2 data that is now the primary response path.

#### Required Fix

```python
async def on_agent_finish(self, agent_name, response, duration):
    step_info = {
        "agent": agent_name,
        "latency_ms": round(duration * 1000, 2),
        "status": "success" if response else "no_response",
        "insights": []
    }

    if response:
        step_info["insights"] = [
            {"type": i.type, "content": i.content, "confidence": i.confidence, "metadata": i.metadata}
            for i in response.insights
        ]
        # v1 fields
        if response.state_updates:
            step_info["state_updates"] = response.state_updates
        # v2 fields
        if response.variable_updates:
            step_info["variable_updates"] = list(response.variable_updates.keys())
        if response.events:
            step_info["events_emitted"] = [e.name for e in response.events]
        if response.facts:
            step_info["facts_count"] = len(response.facts)
        if response.queue_pushes:
            step_info["queue_pushes"] = {k: len(v) for k, v in response.queue_pushes.items()}
        if response.memory_updates:
            step_info["memory_updates_keys"] = list(response.memory_updates.keys())
        # Sidecar + debug
        if response.data:
            step_info["data"] = response.data
        if response.debug_info:
            step_info["debug_info"] = response.debug_info

    self.current_trace["steps"].append(step_info)
```

**Note:** v2 fields are logged in summary form (keys, counts, names) rather than full values, to keep trace volume manageable. Full payloads are available in `debug_info` for agents that set it.

---

## 8. Test Gaps

### 8.1 T1 — `test_phase2_triggered_by_events` Passes Via Cooldown Coincidence

**File:** `tests/test_engine.py` lines 161–189

#### Problem

```python
emitter = MockAgent("emitter", response_fn=emit_event)
subscriber = MockAgent(
    "subscriber",
    subscribed_events=["question_detected"]
)
# MockAgent defaults: trigger_types=[TURN_BASED, EVENT], cooldown=10

await engine.process_turn(sample_context)

assert emitter.call_count == 1
assert subscriber.call_count == 1  # ← passes, but for the wrong reason
```

The subscriber has `trigger_types=[TURN_BASED, EVENT]`. It runs in Phase 1 (TURN_BASED), setting `last_run_time`. When Phase 2 selects it as an event subscriber, `process()` checks cooldown: `(now - last_run_time) < 10` → True → returns None. The assert passes because cooldown blocks the Phase 2 run, not because the test correctly isolates Phase 2 behavior.

**If `subscriber` had `cooldown=0`, it would run twice and the test would fail with `call_count == 2`.**

#### Impact

- The test appears to validate event-triggered Phase 2, but it's actually testing cooldown.
- Any refactor to cooldown logic could break this test for the wrong reason.
- The test doesn't validate that the subscriber ran *because of* the event.

#### Required Fix

Make the subscriber `EVENT`-only so it doesn't run in Phase 1:

```python
subscriber = MockAgent(
    "subscriber",
    subscribed_events=["question_detected"],
    trigger_types=[TriggerType.EVENT]  # EVENT-only: runs in Phase 2 only
)
subscriber.config.cooldown = 0  # Explicit: cooldown is not the gating mechanism

await engine.process_turn(sample_context)

assert emitter.call_count == 1
assert subscriber.call_count == 1  # Now correctly tests Phase 2 event triggering
```

---

## 9. Implementation Plan

### 9.1 PR Grouping

All fixes are grouped into **two PRs** by subsystem dependency.

#### PR 1: Engine & Phase 2 Correctness (B1, B2, B4, B5, T1)

| Fix | File | Lines Changed (est.) |
|-----|------|---------------------|
| B1: Filter `get_event_subscribers` by `TriggerType.EVENT` | `core/engine.py` | +8 |
| B1: Auto-add EVENT to DynamicAgent trigger_types (convenience) | `library/dynamic.py` | +3 |
| B2: Re-sync `shared_state` before Phase 2 | `core/engine.py` | +2 |
| B4: Add `memory_updates_by_agent` field (additive) | `core/engine.py`, `core/models.py` | +6 |
| B5: Wire `on_chain_error` into `process_turn` | `core/engine.py` | +8 |
| T1: Fix `test_phase2_triggered_by_events` | `tests/test_engine.py` | +3, −2 |
| New tests for B1, B2, B4, B5 | `tests/test_engine.py` | +80 |

#### PR 2: Performance & Observability (D1, D2, D3)

| Fix | File | Lines Changed (est.) |
|-----|------|---------------------|
| D1: Eliminate prompt whitespace | `library/dynamic.py` | +15, −12 |
| D2: Class-level `SandboxedEnvironment` | `library/dynamic.py` | +2, −1 |
| D3: Add v2 fields to tracer | `utils/tracing.py` | +12, −0 |

### 9.2 Implementation Order

```
PR 1 (Engine)   ──── merge ──── PR 2 (Perf)
```

PR 2 has no dependency on PR 1 and can be developed in parallel, but should merge after PR 1 to keep the commit history clean.

---

## 10. Testing Strategy

### 10.1 New Tests Required

| ID | Test | Validates |
|----|------|-----------|
| B1-T1 | Subscriber without `TriggerType.EVENT` is excluded from Phase 2 | B1 |
| B1-T2 | DynamicAgent auto-adds EVENT when `subscribed_events` is non-empty | B1 |
| B2-T1 | Phase 2 agents see Phase 1 updates in `shared_state` | B2 |
| B4-T1 | `memory_updates_by_agent` is keyed by agent_id | B4 |
| B5-T1 | `on_chain_error` fires when engine errors | B5 |
| T1-T1 | `test_phase2_triggered_by_events` uses EVENT-only subscriber | T1 |
| D1-T1 | System prompt has no structural leading whitespace | D1 |

### 10.2 Existing Tests

All 96 existing tests must continue to pass. The only permitted modification to an existing test is `test_phase2_triggered_by_events` (T1), to correct its false-positive design.

### 10.3 Regression Envelope

| Metric | v2.1 Baseline | v2.1.1 Threshold |
|--------|---------------|------------------|
| Test count | 96 | ≥ 103 (96 + 7 new) |
| Test pass rate | 100% | 100% |
| Test execution time | < 1s | < 1.5s |

---

## 11. Migration Notes

### 11.1 Host-Facing Behavioral Changes

| Change | Impact | Action Required |
|--------|--------|-----------------|
| New `memory_updates_by_agent` field on `AgentResponse` | **Additive** — new field, existing `memory_updates` unchanged | Consumers can adopt `memory_updates_by_agent` for per-agent attribution. The existing flat `memory_updates` field continues to work as before (last-write-wins). |
| DynamicAgent auto-adds `TriggerType.EVENT` when `subscribed_events` is set | **DynamicAgent convenience only** — agents with `subscribed_events` will now actually run in Phase 2. Custom `BaseAgent` subclasses are not auto-modified. | If any DynamicAgent was relying on the broken behavior (having `subscribed_events` but NOT running on events), remove the `subscribed_events` field. |
| `on_chain_error` now fires on engine errors | New callback invocation | No action required unless a callback's `on_chain_error` has side effects (it was never called before, so existing implementations are untested). |
| System prompts have less whitespace | LLM sees slightly different prompt formatting | No action required. LLM behavior should not change meaningfully. |

### 11.2 Backward Compatibility

All changes are backward compatible:
- `get_event_subscribers` returns a **subset** of what it previously returned (excluding misconfigured agents). Agents that were silently skipping now don't even enter the Phase 2 pipeline.
- The `memory_updates_by_agent` field is **additive**. The existing `memory_updates` flat dict is unchanged. No consumer must update.
- The DynamicAgent convenience normalization applies **only to DynamicAgent**. Custom `BaseAgent` subclasses are not modified. The engine-level guard catches any remaining misconfigured agents regardless of subclass.
- The new `on_chain_error` invocation is a **new callback call** that never fired before. Existing callback implementations have no-op defaults.

---

## 12. Release Gates & Success Metrics

### 12.1 Release Gates

| Gate | Criteria |
|------|----------|
| **Tests pass** | ≥ 103 tests, 100% pass rate |
| **No new warnings** | `pytest -W error::DeprecationWarning` passes (excluding pydantic v2 deprecation) |
| **Backward compat** | All existing tests pass; only permitted modification is T1 (false-positive correction) |
| **Additive verification** | `memory_updates` field shape is unchanged; `memory_updates_by_agent` is a new additive field; existing consumers of `memory_updates` remain unaffected |
| **Prompt size verified** | Before/after token count measured on a representative prompt; reduction confirmed empirically |
| **Trace schema verified** | Tracer output for a v2 agent response includes `variable_updates`, `events_emitted`, `facts_count`, `queue_pushes`, and `memory_updates_keys` fields |
| **No Phase 2 regressions** | Existing approved Phase 2 event subscribers continue to run correctly |

### 12.2 Success Metrics

| Metric | How to Measure | Target |
|--------|---------------|--------|
| Phase 2 correctness | New test B1-T1 passes | Phase 2 subscribers must have EVENT trigger type |
| Prompt size reduction | Tokenize a representative prompt before/after D1 | Measurable reduction in input characters; no structural whitespace |
| Trace completeness | Inspect tracer output for v2 fields | `variable_updates`, `events_emitted`, `facts_count`, `queue_pushes`, `memory_updates_keys` present in trace |
| `on_chain_error` | Test B5-T1 passes | Callback fires on engine error |
| Memory attribution | Test B4-T1 passes | `memory_updates_by_agent` contains per-agent keyed data |

---

## Appendix A: Full Issue Index

| ID | Severity | Type | File | One-liner | Invariant |
|----|----------|------|------|-----------|-----------|
| B1 | Medium | Bug | `core/engine.py` | Phase 2 subscribers without `TriggerType.EVENT` silently skip | INV-9 |
| B2 | Medium | Bug | `core/engine.py` | Phase 2 v1 agents see stale `shared_state` | INV-2 |
| B5 | Medium | Bug | `core/engine.py` | `on_chain_error` callback never fires | INV-10 |
| B4 | Low | Bug | `core/engine.py` | `final_response.memory_updates` is flat/lossy (additive fix) | — |
| D1 | Medium | Perf | `library/dynamic.py` | Prompt whitespace wastes measurable input per call | — |
| D2 | Low | Perf | `library/dynamic.py` | `SandboxedEnvironment` created per call | — |
| D3 | Low | Quality | `utils/tracing.py` | Tracer missing v2 response fields | — |
| T1 | Medium | Test | `tests/test_engine.py` | Phase 2 test passes via cooldown coincidence | — |
