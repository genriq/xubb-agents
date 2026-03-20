# Xubb Agents Framework v2.1
## Hardening & Production-Release Specification

**Version:** 2.1.0
**Status:** Draft — Team Review (Rev 4)
**Date:** March 19, 2026
**Scope:** Bug fixes, safety hardening, and production-grade patterns identified during comprehensive code audit
**Compatibility:** No intended schema or host-integration breaking changes; some incorrect or unsafe behaviors are intentionally normalized (see [Section 15: Migration Notes](#15-migration-notes))
**Baseline:** Audit performed against commit `2cc66aa` (current `main`)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Framework Invariants](#2-framework-invariants)
3. [Scope & Goals](#3-scope--goals)
4. [Release Classification](#4-release-classification)
5. [Critical Bugs](#5-critical-bugs)
6. [High-Severity Bugs](#6-high-severity-bugs)
7. [Medium-Severity Bugs](#7-medium-severity-bugs)
8. [Low-Severity Bugs](#8-low-severity-bugs)
9. [Security Hardening](#9-security-hardening)
10. [Design & Architecture Improvements](#10-design--architecture-improvements)
11. [Robustness & Observability](#11-robustness--observability)
12. [Code Hygiene & Performance](#12-code-hygiene--performance)
13. [Implementation Plan](#13-implementation-plan)
14. [Testing Strategy](#14-testing-strategy)
15. [Migration Notes](#15-migration-notes)
16. [Release Gates, Rollout Plan & Success Metrics](#16-release-gates-rollout-plan--success-metrics)
17. [Performance & Regression Envelope](#17-performance--regression-envelope)
18. [Signoff & Ownership](#18-signoff--ownership)
19. [Appendix A: Full Issue Index](#appendix-a-full-issue-index)

---

## 1. Executive Summary

A comprehensive audit of the Xubb Agents v2.0 codebase identified **12 bugs** and **16 non-production-grade patterns** across the framework's core engine, agent lifecycle, blackboard, dynamic agent, callback system, and tracing infrastructure.

### Headline Numbers

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
| Bugs | 1 | 4 | 4 | 3 | 12 |
| Non-production patterns | — | 2 | 5 | 9 | 16 |
| **Total** | **1** | **6** | **9** | **12** | **28** |

### Impact Summary

- **1 critical bug** will crash any application that registers a callback handler.
- **4 high-severity bugs** cause silent data loss, runaway API costs, and muted agents.
- **1 security issue** (Jinja2 SSTI) allows arbitrary code execution if agent configs come from untrusted sources.
- **Several isolation violations** break the snapshot-per-phase contract that the spec guarantees.

### Guiding Principles for v2.1

1. **Fix bugs, don't redesign** — surgical fixes scoped to the identified issues.
2. **Test every fix** — each issue gets at least one regression test.
3. **Ship incrementally** — fixes are grouped into independent PRs by subsystem.
4. **Measure the fix** — every change has observable success criteria.

---

## 2. Framework Invariants

These are the non-negotiable behavioral contracts that v2.1 must preserve or restore. Every fix in this spec is traceable to one or more violated invariants.

| ID | Invariant | Current Status |
|----|-----------|---------------|
| **INV-1** | Each agent lifecycle callback (`on_agent_start`, `on_agent_finish`, `on_agent_error`) fires **at most once** per actual execution attempt. | **Violated** (B2 — fires twice) |
| **INV-2** | Snapshot state is **immutable** from the perspective of peer agents in the same phase. No agent can observe another agent's writes within the same phase. | **Violated** (B7, B8, NP5) |
| **INV-3** | Agent identity is **explicit and always available**, never inferred from optional payload content. | **Violated** (B5/NP6 — inferred from insights) |
| **INV-4** | Reserved system keys (`sys.*`) are **engine-governed**. Unauthorized writes are **detected and flagged** (v2.1: warning; v2.2: hard error). | **Violated** (NP13 — no detection or enforcement) |
| **INV-5** | Serialization for observability must **never crash turn processing**. A tracing failure must not prevent insight delivery. | **Violated** (NP9 — `json.dumps` can crash) |
| **INV-6** | Error handling must **degrade gracefully** without silent state corruption. A failed agent must not produce orphaned side effects. | **Violated** (B3, B4 — stale callback data, no cooldown) |
| **INV-7** | The callback handler base class must define **all methods the engine calls**. Subclasses must not crash on any lifecycle event. | **Violated** (B1 — missing methods) |
| **INV-8** | Agent memory values returned by the Blackboard are **copies**, not mutable references to internal state. | **Violated** (B8, B11) |

### Callback Failure Isolation Policy

Callback failures are **non-fatal observability failures**. They must be logged and isolated, and must **never** abort turn processing, suppress agent output, or corrupt framework state. If a callback raises during any lifecycle event (`on_agent_start`, `on_agent_finish`, `on_phase_start`, etc.), the engine must:
1. Log the error at `ERROR` level with the callback class name and exception.
2. Continue processing the current turn as if the callback had returned normally.
3. Not retry the failed callback within the same turn.

This policy is already partially implemented (engine wraps callback calls in `try/except`), but is now formally specified as a framework contract.

Post-release, all invariants must hold. If any regression violates an invariant, the release is blocked.

---

## 3. Scope & Goals

### 3.1 In Scope

| Area | What Changes |
|------|-------------|
| Callback system | Add missing methods, eliminate duplicate firing |
| Agent lifecycle | Fix cooldown-after-error, error-path response, response identity |
| Response merging | Fix agent identity resolution, add `source_agent_id` |
| Snapshot isolation | Fix `shared_state` shallow copy, `get_memory` mutable ref, `to_dict` ref leak |
| DynamicAgent | Fix `check_field` lookup, private_state mutation, Jinja2 sandboxing, prompt whitespace |
| Blackboard | Fix `clear_queue` phantom entries, `sys.*` write protection |
| Tracing | Fix serialization crash, shared_state capture by reference |
| Models | Fix mutable literal defaults on `AgentResponse` |
| Code hygiene | Remove dead code, dev comments, misplaced imports |

### 3.2 Out of Scope

| Area | Rationale |
|------|-----------|
| New features (RAG v2, new trigger types) | Separate spec |
| Performance optimization (async batching, connection pooling) | Separate spec |
| CI/CD pipeline setup | Operational concern, not framework code |
| Schema redesign | Current schema system works; only the `default_v2.json` double-write is fixed |
| `AgentConfig` → Pydantic migration | Recommended but scoped for v2.2 (breaking change risk) |
| `collections.deque` for queues (NP14) | **Explicitly deferred to v2.2.** Requires serialization format changes and performance profiling to justify. Queue sizes in current deployments do not warrant the migration cost. |

---

## 4. Release Classification

Issues are classified into three tiers for release discipline.

### 4.1 Release Blockers — Must land in v2.1

These issues cause crashes, silent data loss, or security vulnerabilities. The release **cannot ship** without them.

| ID | Issue | Invariant |
|----|-------|-----------|
| B1 | Missing callback methods — runtime crash | INV-7 |
| B2 | Duplicate callback firing | INV-1 |
| B4 | No cooldown after error — runaway retries | INV-6 |
| B5 / NP6 | Memory updates dropped for insight-less responses | INV-3 |
| B6 | `check_field` reads wrong object with `root_key` | — |
| NP1 | Unsandboxed Jinja2 — SSTI risk | — |
| B7 | `shared_state` shallow copy breaks isolation | INV-2 |
| B8 | `get_memory` returns mutable internal ref | INV-2, INV-8 |
| B11 | `to_dict` shares mutable refs with live state | INV-8 |

### 4.2 Should Land in v2.1

These improve correctness and robustness but are not crash/security risks.

| ID | Issue |
|----|-------|
| B3 | `on_agent_finish` gets `None` on error path |
| NP5 | `private_state` mutated from snapshot data |
| NP9 | `json.dumps` crashes on non-serializable types |
| NP10 | `shared_state` captured by ref, not snapshot |
| NP7 | No `choices` empty check |
| NP2 | Mutable literal defaults on `AgentResponse` |
| B9 | Fire-and-forget task with silent exception loss |
| B10 | `clear_queue` creates phantom entries |
| NP13 | No `sys.*` write protection |

### 4.3 Can Defer to v2.2

These are improvements that carry low risk if deferred.

| ID | Issue | Rationale |
|----|-------|-----------|
| NP3 | `AgentConfig` bypasses Pydantic validation | Breaking change risk |
| NP12 | Verbose/fragile trigger parsing | Cosmetic, works correctly |
| NP14 | O(n) queue pop | Requires serialization changes; deferred pending profiling |
| NP15 | Dev journal comments in production code | Cosmetic |
| NP16 | `_sync_state_from_legacy` dead code | No runtime impact |
| NP11 | Excessive whitespace in prompts | Token cost, not correctness |
| B12 | `default_v2.json` double-write | Harmless redundancy |
| NP8 | `import json` inside function | Cosmetic |

---

## 5. Critical Bugs

### 5.1 B1 — Missing Callback Methods Crash at Runtime

**File:** `core/callbacks.py`
**Triggered from:** `core/engine.py` lines 213, 233, 264, 285
**Invariant:** INV-7

#### Problem

The engine calls `on_phase_start(phase_num, agent_names)`, `on_phase_end(phase_num, event_names)`, and `on_agent_skipped(agent_name, reason)` on callback handlers during every turn. `AgentCallbackHandler` does not define these methods. Any registered callback — including the framework's own `StructuredLogTracer` — will raise `AttributeError` the moment Phase 1 begins.

`on_agent_skipped` is guarded by `hasattr` (engine.py:524), so it won't crash, but the phase callbacks are called directly with no guard.

#### Current Code

```python
# callbacks.py — MISSING: on_phase_start, on_phase_end, on_agent_skipped
class AgentCallbackHandler(ABC):
    async def on_turn_start(self, context): pass
    async def on_turn_end(self, response, duration): pass
    async def on_agent_start(self, agent_name, context): pass
    async def on_agent_finish(self, agent_name, response, duration): pass
    async def on_agent_error(self, agent_name, error): pass
    async def on_chain_error(self, error): pass
```

```python
# engine.py:213 — crashes with AttributeError
await cb.on_phase_start(1, [a.config.name for a in phase1_agents])
```

#### Required Fix

Add three no-op default implementations to `AgentCallbackHandler`:

```python
async def on_phase_start(self, phase: int, agent_names: List[str]) -> None:
    """Called when an execution phase begins."""
    pass

async def on_phase_end(self, phase: int, event_names: List[str]) -> None:
    """Called when an execution phase completes."""
    pass

async def on_agent_skipped(self, agent_name: str, reason: str) -> None:
    """Called when an agent is skipped during eligibility checks."""
    pass
```

#### Test

```python
class MinimalCallback(AgentCallbackHandler):
    pass  # Should work with no overrides

# Must not raise when engine processes a turn with this callback
```

---

## 6. High-Severity Bugs

### 6.1 B2 — Duplicate Callback Firing

**Files:** `core/engine.py` lines 354-400, `core/agent.py` lines 101-140
**Invariant:** INV-1

#### Problem

The engine fires `on_agent_start` in `_run_phase` (line 358), then passes `callbacks=self.callbacks` to `agent.process()`, which fires `on_agent_start` again (line 105). The same duplication occurs for `on_agent_finish` (engine line 386 + agent line 138) and `on_agent_error` (engine line 399 + agent line 121).

Every callback fires **twice** per agent per turn.

#### Impact

- Telemetry, metrics, and billing counters are doubled.
- `StructuredLogTracer` records two steps per agent in the trace JSON.
- Any callback with side effects (webhooks, database writes) executes twice.

#### Required Fix

**Remove callback firing from `_run_phase` and `_run_agent_safe` in the engine.** The agent's `process()` method already fires callbacks at the correct lifecycle points (after cooldown check passes, and with proper error/success distinction). The engine should not duplicate this.

Specifically, remove:
- Engine `_run_phase` lines 355-360 (`on_agent_start` loop)
- Engine `_run_agent_safe` lines 383-388 (`on_agent_finish` loop)
- Engine `_run_agent_safe` lines 396-401 (`on_agent_error` loop)

**Rationale:** The agent's `process()` method fires callbacks _after_ the cooldown check, so `on_agent_start` only fires when the agent actually runs. The engine's pre-firing happens before cooldown is checked, which is semantically wrong — it reports agents as "started" when they may be about to skip due to cooldown.

#### Test

```python
class CountingCallback(AgentCallbackHandler):
    def __init__(self):
        self.start_count = 0
        self.finish_count = 0
        self.error_count = 0
    async def on_agent_start(self, name, ctx):
        self.start_count += 1
    async def on_agent_finish(self, name, resp, dur):
        self.finish_count += 1
    async def on_agent_error(self, name, err):
        self.error_count += 1

# After process_turn with 1 agent:
assert callback.start_count == 1   # NOT 2
assert callback.finish_count == 1  # NOT 2
```

---

### 6.2 B4 — No Cooldown After Agent Error

**File:** `core/agent.py` lines 113-114
**Invariant:** INV-6

#### Problem

```python
try:
    response = await self.evaluate(context)
    self.last_run_time = now  # only set on success
    return response
except Exception as e:
    # last_run_time NOT updated
    return AgentResponse(insights=[error_insight])
```

When `evaluate()` raises, `last_run_time` is never updated. On the next turn, the cooldown check passes immediately, and the agent fires again. A persistent error (bad prompt, API outage, malformed schema) causes the agent to run every single turn with no throttling.

#### Impact

- Unbounded LLM API costs during outages.
- UI flooded with ERROR insights every turn.
- Other agents may be starved of resources.

#### Cooldown Policy Design Decision

The cooldown must apply uniformly to all execution outcomes. Rationale:

| Failure Mode | Should cooldown apply? | Reasoning |
|--------------|----------------------|-----------|
| LLM API timeout | **Yes** | Retrying immediately during an outage makes it worse. |
| LLM content filtering / safety refusal | **Yes** | The prompt hasn't changed; retrying next turn won't help. |
| Malformed schema / parse error | **Yes** | Permanent until config is fixed; retrying wastes API calls. |
| Transient network error | **Yes** | The next turn (seconds later) is soon enough to retry. |
| Evaluation logic exception | **Yes** | Bug in agent code; retrying immediately is pointless. |

**Decision:** A single, uniform cooldown policy for all outcomes. The agent always goes on cooldown after an execution attempt, whether it succeeds, fails, or is filtered.

**Why not differentiated retry policies?** At the framework's current abstraction level, the engine cannot distinguish transient from permanent failures without agent cooperation. Adding retry categories (retriable, permanent, rate-limited) is a v2.2 concern that requires:
- Error classification enum on `AgentResponse`
- Per-category cooldown multipliers on `AgentConfig`
- Exponential backoff for retriable failures

For v2.1, the uniform policy is safe, simple, and eliminates the runaway-cost risk.

#### Required Fix

Move `self.last_run_time = now` to execute unconditionally after any execution attempt:

```python
try:
    response = await self.evaluate(context)
    return response
finally:
    self.last_run_time = now  # Always update, success or failure
```

#### Test

```python
# Agent that always raises
class FailingAgent(BaseAgent):
    async def evaluate(self, ctx): raise RuntimeError("boom")

agent = FailingAgent(AgentConfig(name="fail", cooldown=30))
await agent.process(context)  # First call — runs, fails
result = await agent.process(context)  # Second call — should be cooldown-skipped
assert result is None  # Cooldown active
```

---

### 6.3 B5 — Memory Updates Silently Dropped for Insight-Less Responses

**File:** `core/engine.py` lines 424-480
**Invariant:** INV-3

#### Problem

`_merge_responses` identifies the source agent via `resp.insights[0].agent_id`. If a response has no insights (e.g., a "silent worker" agent that only updates state), `agent_id` stays `None`:

```python
agent_id = None
if resp.insights:
    agent_id = resp.insights[0].agent_id  # only set when insights exist
```

Downstream, memory updates are guarded by:
```python
if resp.memory_updates and agent_id:  # agent_id is None -> skipped
    blackboard.update_memory(agent_id, resp.memory_updates)
```

Additionally, `agent_priority` defaults to `0` and `agent_index` defaults to `0`, breaking deterministic merge ordering for all insight-less responses.

#### Impact

- Any agent that returns `variable_updates`, `facts`, `queue_pushes`, or `memory_updates` without insights will have its **memory updates silently discarded**.
- Priority-based merge ordering is broken for these responses.

#### Required Fix

Add a `source_agent_id` field to `AgentResponse` and populate it at creation time. Use it for identity resolution in `_merge_responses`.

**Step 1 — `models.py`:**
```python
class AgentResponse(BaseModel):
    source_agent_id: Optional[str] = Field(
        default=None, description="Agent that produced this response (set by framework)"
    )
    ...
```

**Step 2 — `agent.py` (`process` method):**
```python
response = await self.evaluate(context)
if response:
    response.source_agent_id = self.config.id
return response
```

Also stamp it on error responses:
```python
except Exception as e:
    error_response = AgentResponse(
        source_agent_id=self.config.id,
        insights=[self.create_insight(...)]
    )
    return error_response
```

**Step 3 — `engine.py` (`_merge_responses`):**
```python
for resp in responses:
    agent_id = resp.source_agent_id  # direct, no inference needed
    # Fallback for v1 compat (responses without source_agent_id)
    if not agent_id and resp.insights:
        agent_id = resp.insights[0].agent_id
    ...
```

#### Test

```python
# Agent that returns only memory updates, no insights
class SilentWorker(BaseAgent):
    async def evaluate(self, ctx):
        return AgentResponse(
            memory_updates={"last_seen": "something"},
            variable_updates={"counter": 1}
        )

# After process_turn:
assert blackboard.get_memory("silent_worker") == {"last_seen": "something"}
assert blackboard.get_var("counter") == 1
```

---

### 6.4 B6 — `check_field` Reads From Wrong Object When `root_key` Is Set

**File:** `library/dynamic.py` line 284

#### Problem

```python
root_data = result.get(self.mapping["root_key"], {})  # line 273 — unwraps correctly
...
should_speak = result.get(check_field, False)  # line 284 — reads from `result`, not `root_data`
```

For schemas with `root_key` (like `v2_raw` where `root_key: "insight"`), the `check_field` is looked up in the outer envelope instead of the unwrapped `root_data`. The field is never found in the envelope, so `should_speak` defaults to `False`, silently muting the agent.

This bug is currently masked because `v2_raw.json` doesn't define a `check_field` (it uses the empty-`root_data` fallback path on line 288). But any schema that combines `root_key` + `check_field` is broken.

#### Required Fix

```python
# Before (line 284):
should_speak = result.get(check_field, False)

# After:
should_speak = root_data.get(check_field, False)
```

#### Test

```python
# Schema with root_key + check_field
schema = {"root_key": "insight", "check_field": "has_insight", "content_field": "message"}
# LLM returns: {"insight": {"has_insight": true, "message": "...", "type": "suggestion"}}
# Agent should NOT be muted
```

---

## 7. Medium-Severity Bugs

### 7.1 B3 — `on_agent_finish` Receives `None` Response on Error Path

**File:** `core/agent.py` lines 111-140
**Invariant:** INV-6

#### Problem

```python
response = None
try:
    response = await self.evaluate(context)
    self.last_run_time = now
    return response
except Exception as e:
    return AgentResponse(insights=[...])  # NOT assigned to `response`
finally:
    await cb.on_agent_finish(self.config.name, response, duration)  # response is None
```

The error `AgentResponse` (with the ERROR insight) is returned from the `except` block but never written back to the `response` variable. The `finally` block sends `response=None` to `on_agent_finish`.

#### Required Fix

Assign the error response to `response` before returning:

```python
except Exception as e:
    response = AgentResponse(insights=[...])
    return response
```

---

### 7.2 B7 — `shared_state` Shallow Copy Breaks Snapshot Isolation

**File:** `core/engine.py` line 340
**Invariant:** INV-2

#### Problem

```python
phase_context = AgentContext(
    shared_state=context.shared_state.copy(),  # shallow copy
    blackboard=snapshot,                        # deep copy (correct)
    ...
)
```

`.copy()` on a dict is shallow. If any values are mutable (nested dicts, lists), concurrent agents in the same phase share references to those nested objects. One agent mutating a nested value affects all others.

#### Required Fix

```python
from copy import deepcopy
shared_state=deepcopy(context.shared_state),
```

---

### 7.3 B8 — `get_memory` Returns Mutable Internal Reference

**File:** `core/blackboard.py` line 181
**Invariant:** INV-2, INV-8

#### Problem

```python
def get_memory(self, agent_id: str) -> Dict[str, Any]:
    return self.memory.get(agent_id, {})
```

When `agent_id` exists, this returns a direct reference to the internal dict. Callers can mutate it without going through `update_memory`/`set_memory`. During phase execution, if an agent stashes this reference and mutates it, the mutation leaks into the snapshot, violating phase isolation.

#### Design Decision: Shallow Copy vs Deep Copy

**Decision: `deepcopy`.** The framework does not constrain memory values to be flat. The spec allows `Dict[str, Any]`, meaning nested dicts and lists are valid. A shallow copy would still leak nested references. The cost of `deepcopy` on typical memory dicts (estimated 5-20 keys, flat or one level deep based on current test/dev workloads) is expected to be negligible — sub-microsecond.

**Contract:** From v2.1 forward, `get_memory` returns a **deep copy**. Callers must use `update_memory` to persist changes.

#### Required Fix

```python
def get_memory(self, agent_id: str) -> Dict[str, Any]:
    return deepcopy(self.memory.get(agent_id, {}))
```

---

### 7.4 B11 — `to_dict` Shares Mutable References With Live Blackboard

**File:** `core/blackboard.py` lines 220-228
**Invariant:** INV-8

#### Problem

```python
def to_dict(self) -> Dict[str, Any]:
    return {
        "events": [e.model_dump() for e in self.events],   # safe (new dicts)
        "variables": self.variables,                         # shared reference
        "queues": self.queues,                               # shared reference
        "facts": [f.model_dump() for f in self.facts],       # safe
        "memory": self.memory                                # shared reference
    }
```

Any consumer that mutates the serialized output will corrupt the live Blackboard.

#### Required Fix

```python
def to_dict(self) -> Dict[str, Any]:
    return {
        "events": [e.model_dump() for e in self.events],
        "variables": deepcopy(self.variables),
        "queues": deepcopy(self.queues),
        "facts": [f.model_dump() for f in self.facts],
        "memory": deepcopy(self.memory)
    }
```

---

## 8. Low-Severity Bugs

### 8.1 B9 — Fire-and-Forget `asyncio.create_task` in Sync Method

**File:** `core/engine.py` lines 525-526

#### Problem

```python
# _get_eligible_agents is a sync method
asyncio.create_task(
    cb.on_agent_skipped(agent.config.name, reason)
)
```

The task is fire-and-forget: exceptions inside it produce "Task exception was never retrieved" warnings. The task may outlive the turn.

#### Required Fix

Make `_get_eligible_agents` async and directly `await` the callback:

```python
async def _get_eligible_agents(self, ...):
    ...
    if hasattr(cb, 'on_agent_skipped'):
        await cb.on_agent_skipped(agent.config.name, reason)
```

Update the call site in `process_turn` to `await self._get_eligible_agents(...)`.

---

### 8.2 B10 — `clear_queue` Creates Phantom Entries

**File:** `core/blackboard.py` lines 123-125

#### Problem

```python
def clear_queue(self, queue_name: str) -> None:
    self.queues[queue_name] = []  # Creates key if it didn't exist
```

After `clear_queue("nonexistent")`, `has_queue("nonexistent")` returns `True`.

#### Required Fix

```python
def clear_queue(self, queue_name: str) -> None:
    if queue_name in self.queues:
        self.queues[queue_name] = []
```

---

### 8.3 B12 — `default_v2.json` Double-Writes Through Both State Paths

**File:** `library/schemas/default_v2.json`

#### Problem

Both `state_field` and `variable_updates_field` map to `"variable_updates"`. This causes the same LLM output to be written to both `response.state_updates` (v1 path) and `response.variable_updates` (v2 path).

#### Required Fix

Set `state_field` to `null` in `default_v2.json` so the v2 path is the sole owner:

```json
{
  "variable_updates_field": "variable_updates",
  "state_field": null
}
```

---

## 9. Security Hardening

### 9.1 NP1 — Unsandboxed Jinja2 Templates (SSTI Risk)

**File:** `library/dynamic.py` line 190
**Severity:** High (if agent configs come from untrusted sources)

#### Problem

```python
from jinja2 import Template
template = Template(self.system_prompt)
rendered_system_prompt = template.render(
    state=context.shared_state,
    blackboard=context.blackboard,
    context=context,
    ...
)
```

`jinja2.Template` uses the default `Environment` with no sandboxing. If `self.system_prompt` originates from a database, API, or any user-controllable input, an attacker can inject Jinja2 expressions that access Python internals:

```
{{ config.__class__.__init__.__globals__['os'].system('rm -rf /') }}
```

This is a well-known Server-Side Template Injection (SSTI) vulnerability.

#### Threat Model

| Config Source | Risk |
|---------------|------|
| Hardcoded in code | None |
| Loaded from admin-only database | Low (insider threat) |
| Loaded from API/user input | **Critical** (RCE) |
| Loaded from third-party integration | **High** |

In production, Xubb agent configs are likely stored in a database and managed via an admin UI — making this at minimum a privilege escalation vector.

#### Required Fix

Replace raw `Template` with `SandboxedEnvironment`:

```python
from jinja2.sandbox import SandboxedEnvironment

_jinja_env = SandboxedEnvironment()

# In evaluate():
template = _jinja_env.from_string(self.system_prompt)
rendered_system_prompt = template.render(...)
```

`SandboxedEnvironment` blocks access to dangerous attributes (`__class__`, `__globals__`, etc.) while preserving all template rendering functionality used by the framework.

#### Template Rendering Constraints

In addition to sandboxing, the following operational constraints apply to template rendering in v2.1:

| Constraint | Policy |
|------------|--------|
| **Sandbox mode** | `SandboxedEnvironment` with default restrictions. No custom `unsafe` overrides. |
| **Render timeout** | Not enforced at framework level (Jinja2 rendering is synchronous and sub-millisecond for typical templates). If templates grow complex, host should set process-level timeouts. |
| **Template complexity** | No framework-level limit. Templates exceeding 10KB should be flagged in config review. |
| **Template versioning** | Out of scope for the framework. Host applications should version and audit-log template changes. |

#### Test

```python
def test_jinja2_ssti_blocked():
    malicious_prompt = "{{ ''.__class__.__mro__[1].__subclasses__() }}"
    agent = DynamicAgent({"name": "test", "text": malicious_prompt})
    # Should either raise SecurityError or render safely, NOT execute
```

---

### 9.2 NP13 — No `sys.*` Write Protection

**File:** `core/blackboard.py` lines 71-77
**Invariant:** INV-4

#### Problem

The docstring says `sys.*` keys are reserved for engine use, but `set_var` doesn't enforce this. Any agent or host code can overwrite `sys.turn_count`, `sys.session_id`, or `sys.trigger_type`, corrupting engine-managed state.

#### Required Fix

Add a warning (not an error, for backward compatibility) when non-engine code writes to `sys.*`:

```python
def set_var(self, key: str, value: Any, _engine_internal: bool = False) -> None:
    if key.startswith("sys.") and not _engine_internal:
        import logging
        logging.getLogger("Blackboard").warning(
            f"Writing to reserved key '{key}'. sys.* keys are engine-managed."
        )
    self.variables[key] = value
```

Engine calls updated to pass `_engine_internal=True`. In v2.2, consider making this a hard error.

---

### 9.3 Config Provenance & Audit (Recommendations for Host)

The framework does not manage config storage — that is the host's responsibility. However, the following recommendations should be communicated to host integrators:

| Concern | Recommendation |
|---------|---------------|
| **Config source classification** | Hosts should classify config sources as `trusted` (code, signed configs) or `untrusted` (database, API, user input). Untrusted sources require Jinja2 sandboxing (enforced by framework in v2.1) plus host-level input validation. |
| **Template audit trail** | Hosts managing agent configs via admin UI should log: who changed the template, when, diff from previous version. |
| **Config approval model** | For production deployments, template changes should require review before activation. The framework does not enforce this; host CI/CD pipelines should. |
| **Sensitive data in templates** | Templates receive `shared_state`, `blackboard`, `user_context`, and `rag_docs` as render context. Hosts should ensure these do not contain credentials, PII, or secrets that could leak into LLM prompts. |

---

## 10. Design & Architecture Improvements

### 10.1 NP6 — Add `source_agent_id` to `AgentResponse`

See [Section 6.3 (B5)](#63-b5--memory-updates-silently-dropped-for-insight-less-responses) for the full fix. This is the root cause of B5 and a fragile design pattern.

**Current:** Agent identity is inferred from `resp.insights[0].agent_id`.
**Required:** Explicit `source_agent_id` field stamped by the framework.

---

### 10.2 NP5 — `DynamicAgent.evaluate` Mutates `self.private_state` From Snapshot Data

**File:** `library/dynamic.py` lines 155-160
**Invariant:** INV-2

#### Problem

```python
persistent_memory = context.shared_state.get(mem_key, {})
if persistent_memory and isinstance(persistent_memory, dict):
    self.private_state.update(persistent_memory)  # mutates agent-level state
```

`self.private_state` lives on the agent object, not the snapshot. During multi-phase execution:
1. Phase 1 agents evaluate against a snapshot.
2. The engine merges state, which may include memory writes.
3. Phase 2 agents receive a new snapshot, but `self.private_state` already contains Phase 1's merged data (leaking through the agent object).

This violates the snapshot isolation contract.

#### Required Fix

Use a local copy within `evaluate`:

```python
# Build working memory for this evaluation (do not mutate self.private_state here)
working_memory = dict(self.private_state)
persistent_memory = context.shared_state.get(mem_key, {})
if persistent_memory and isinstance(persistent_memory, dict):
    working_memory.update(persistent_memory)

current_memory = json.dumps(working_memory, indent=2)
```

Update `self.private_state` only when building the response (line 351, 437), which is the agent's declared output — not a side effect of reading context.

---

### 10.3 NP3 — `AgentConfig` Bypasses Pydantic Validation

**File:** `core/agent.py` line 25
**Deferred to:** v2.2

#### Problem

Every data structure in the framework uses Pydantic `BaseModel` for validation — except `AgentConfig`, which is a plain class. Invalid types, negative cooldowns, empty names, and duplicate IDs are silently accepted.

#### Recommendation (v2.2)

This is flagged for a future release because converting `AgentConfig` to a `BaseModel` may break subclasses or host code that relies on the current `__init__` signature. For v2.1, add defensive assertions:

```python
def __init__(self, name: str, ...):
    assert name and isinstance(name, str), "AgentConfig.name must be a non-empty string"
    assert cooldown >= 0, "AgentConfig.cooldown must be non-negative"
    assert priority >= 0, "AgentConfig.priority must be non-negative"
    ...
```

---

### 10.4 NP4 — `AgentCallbackHandler` Is `ABC` With No Abstract Methods

**File:** `core/callbacks.py` line 5

#### Problem

```python
class AgentCallbackHandler(ABC):
    # All methods are concrete no-ops
```

The `ABC` base signals that subclasses must implement something, but all methods are concrete. Any subclass is valid even if it overrides nothing.

#### Required Fix

Remove `ABC`. This is a mixin/protocol, not an abstract class:

```python
class AgentCallbackHandler:
    """Base callback handler. Override the methods you care about."""
```

---

## 11. Robustness & Observability

### 11.1 NP9 — `StructuredLogTracer` Crashes on Non-Serializable Types

**File:** `utils/tracing.py` line 84
**Invariant:** INV-5

#### Problem

```python
log_line = f"TURN_TRACE: {json.dumps(self.current_trace)}"
```

`current_trace` includes `context.shared_state`, `response.data`, and `response.debug_info` — all `Dict[str, Any]`. A single non-JSON-serializable value (datetime, Pydantic model, bytes) crashes the entire trace serialization.

#### Required Fix

```python
log_line = f"TURN_TRACE: {json.dumps(self.current_trace, default=str)}"
```

---

### 11.2 NP10 — Tracer Captures `shared_state` by Reference, Not Snapshot

**File:** `utils/tracing.py` line 29

#### Problem

```python
"initial_shared_state": context.shared_state,  # reference to live dict
```

By the time `on_turn_end` serializes the trace, `shared_state` has been mutated by the engine. The "initial" state in the trace will contain the final state.

#### Required Fix

```python
"initial_shared_state": deepcopy(context.shared_state),
```

---

### 11.3 NP7 — `LLMClient.generate_json` Doesn't Guard Empty `choices`

**File:** `core/llm.py` line 42

#### Problem

```python
content = response.choices[0].message.content
```

If the OpenAI API returns empty `choices` (content filtering, safety block), this raises `IndexError`. The outer `try/except` catches it but logs "LLM Generation failed: list index out of range" — misleading.

#### Required Fix

```python
if not response.choices:
    logger.warning("LLM returned empty choices (content may have been filtered)")
    return None
content = response.choices[0].message.content
```

---

### 11.4 NP2 — Mutable Literal Defaults on `AgentResponse`

**File:** `core/models.py` lines 128-130

#### Problem

```python
insights: List[AgentInsight] = []
state_updates: Dict[str, Any] = {}
```

All other fields use `Field(default_factory=...)`. These two use mutable literals. Safe on Pydantic v2 (which copies defaults), but inconsistent and fragile.

#### Required Fix

```python
insights: List[AgentInsight] = Field(default_factory=list)
state_updates: Dict[str, Any] = Field(default_factory=dict)
```

---

## 12. Code Hygiene & Performance

### 12.1 NP11 — Excessive Whitespace in Prompts Wastes Tokens

**File:** `library/dynamic.py` lines 228-238

#### Problem

```python
full_system_prompt = f"""
        {user_context_section}
        {language_section}
        {rendered_system_prompt}
        ...
"""
```

The f-string is indented inside the method body, injecting ~8 spaces of leading whitespace per line. Over thousands of LLM calls, this adds up to significant wasted tokens.

#### Required Fix

Use `textwrap.dedent` or left-align the f-string content. Trim leading/trailing whitespace:

```python
full_system_prompt = "\n".join(filter(None, [
    user_context_section.strip(),
    language_section.strip(),
    rendered_system_prompt,
    "[YOUR MEMORY / SCRATCHPAD]",
    current_memory,
    rag_section.strip(),
    trigger_context.strip(),
    self.json_instruction,
])).strip()
```

---

### 12.2 NP8 — `import json` Inside Function

**File:** `core/llm.py` line 43

Move `import json` to the top of the file alongside the other imports.

---

### 12.3 NP12 — Verbose Trigger Type Parsing (Deferred to v2.2)

**File:** `library/dynamic.py` lines 26-53

Two near-identical blocks (string vs list) with no handling for invalid mode values. Replace with a lookup dict. Deferred because it is cosmetic and the current code is functionally correct.

---

### 12.4 NP14 — O(n) Queue Pop (Deferred to v2.2)

**File:** `core/blackboard.py` line 110

`list.pop(0)` is O(n). For high-volume queues, this becomes a bottleneck.

**Deferred.** Migrating to `collections.deque` requires:
1. Serialization format changes in `to_dict` / `from_dict` (deque is not JSON-serializable).
2. `deepcopy` behavior validation (deque copies differently than list).
3. Performance profiling to confirm queue sizes in practice justify the migration.

Current queue sizes observed in test and dev workloads are small (estimated < 50 items). The O(n) cost is expected to be sub-microsecond at these sizes. Revisit if production profiling shows queue operations as a bottleneck.

---

### 12.5 NP15 — Development Comments in Production Code (Deferred to v2.2)

**File:** `core/agent.py` lines 9-23

Lines 9-23 contain stream-of-consciousness design notes. Remove them. Deferred because no runtime impact.

---

### 12.6 NP16 — Dead Code: `_sync_state_from_legacy` (Deferred to v2.2)

**File:** `core/engine.py` lines 596-605

`_sync_state_from_legacy` is defined but never called. Remove it to avoid confusion. Deferred because no runtime impact.

---

## 13. Implementation Plan

### 13.1 PR Grouping

Fixes are grouped into independent PRs by subsystem for isolated review and rollback.

| PR | Scope | Issues | Risk | Classification |
|----|-------|--------|------|----------------|
| **PR1: Callback System** | `callbacks.py`, `engine.py`, `agent.py` | B1, B2, B3, NP4 | Medium (touches execution path) | Blocker |
| **PR2: Agent Lifecycle** | `agent.py`, `models.py` | B4, B5/NP6, NP2 | Medium (adds field to response model) | Blocker |
| **PR3: Snapshot Isolation** | `engine.py`, `blackboard.py` | B7, B8, B11 | Low (defensive copies) | Blocker |
| **PR4: DynamicAgent Fixes** | `dynamic.py`, schemas | B6, NP1, NP5 | Medium (touches prompt path + security) | Blocker |
| **PR5: Robustness** | `tracing.py`, `llm.py` | NP7, NP9, NP10 | Low (observability only) | Should-land |
| **PR6: Cleanup** | `blackboard.py`, `engine.py`, `agent.py`, `llm.py` | B9, B10, B12, NP8, NP13 | Low (minor fixes) | Should-land |

### 13.2 PR Exit Criteria

Every PR must satisfy **all** of the following before merge:

| Gate | Criteria |
|------|----------|
| **Regression tests** | All new regression tests pass. All existing tests pass without modification. |
| **Callback count** | No change in callback firing count except the intended B2 deduplication (2x → 1x). Verified by `CountingCallback` test. |
| **Schema compatibility** | All existing schema files (`default.json`, `v2_raw.json`, `custom1.json`, `ui_control.json`, `widget_control.json`) produce identical functional output for identical LLM responses, allowing documented additive metadata fields. Verified by fixture-based tests. |
| **Trace format** | `StructuredLogTracer` output remains parseable by `tools/debugger.html`. No field removals, no type changes on existing fields. New fields are additive only. |
| **Latency** | Per-turn latency does not increase by more than 5% (measured as p95 across test suite). The `deepcopy` additions are expected to add < 0.1ms per turn. |
| **Token consumption** | No PR may increase token consumption per turn. Verified by comparing prompt character counts before/after on a fixed test prompt. (NP11, if included in a future PR, must demonstrate reduction.) |
| **Invariants** | All framework invariants (Section 2) hold after the PR. Verified by invariant-specific tests. |

### 13.3 Sequencing

```
Week 1:  PR1 (Callback System) → PR2 (Agent Lifecycle)
Week 2:  PR3 (Snapshot Isolation) → PR4 (DynamicAgent Fixes)
Week 3:  PR5 (Robustness) → PR6 (Cleanup)
Tag:     v2.1.0
```

PR1 must land first — it unblocks basic callback functionality. PR2 should follow immediately as it fixes silent data loss. PR3 and PR4 can be parallelized. PR5 and PR6 can land in any order.

---

## 14. Testing Strategy

### 14.1 New Regression Tests

Each fix must include at least one regression test. Below is the minimum set:

| Issue | Test Description | File |
|-------|-----------------|------|
| B1 | Minimal callback subclass survives `process_turn` | `test_engine.py` |
| B2 | Callback fires exactly once per agent per turn | `test_engine.py` |
| B3 | `on_agent_finish` receives error response, not `None` | `test_engine.py` |
| B4 | Failed agent respects cooldown on next turn | `test_engine.py` |
| B5 | Insight-less response preserves memory updates | `test_engine.py` |
| B6 | Schema with `root_key` + `check_field` produces insight | `test_dynamic.py` (new) |
| B7 | Concurrent agents can't see each other's `shared_state` mutations | `test_engine.py` |
| B8 | Mutating `get_memory` result doesn't affect blackboard | `test_blackboard.py` |
| B11 | Mutating `to_dict` result doesn't affect blackboard | `test_blackboard.py` |
| NP1 | SSTI payload is blocked by sandbox | `test_dynamic.py` (new) |
| NP5 | `private_state` not mutated by snapshot reads across phases | `test_dynamic.py` (new) |
| NP9 | Tracer doesn't crash on non-serializable state | `test_tracing.py` (new) |

### 14.2 Integration & Chaos Tests

Beyond unit-level regression tests, the following integration and adversarial tests are required:

| Test | Description | File |
|------|-------------|------|
| **Multi-agent multi-phase full flow** | 3+ agents across Phase 1 and Phase 2. Verify: insights merged correctly, priority ordering holds, events dispatched, Phase 2 agents fire, memory updates preserved for all agents including insight-less ones. | `test_engine.py` |
| **Silent worker full lifecycle** | A single agent that returns only `memory_updates` + `variable_updates` (no insights) through the complete process_turn → merge → finalize flow. Verify identity, priority, and all state updates applied. | `test_engine.py` |
| **Phase isolation under concurrent mutation** | Two agents in the same phase. Agent A mutates a nested value in `shared_state`. Agent B must not see the mutation. Same test for `blackboard.get_memory()`. | `test_engine.py` |
| **Partial LLM outage simulation** | 3 agents, 1 returns normally, 1 raises `TimeoutError`, 1 raises `ValueError`. Verify: successful agent's insights delivered, failed agents on cooldown, no state corruption from failed agents. | `test_engine.py` |
| **Malformed LLM output** | `generate_json` returns `None`, empty dict, dict missing expected keys, dict with wrong types. Verify: DynamicAgent handles all gracefully, returns empty or partial response, no crash. | `test_dynamic.py` |
| **Callback exception isolation** | Callback handler raises `RuntimeError` in `on_agent_finish`. Verify: turn processing completes, insights delivered, no cascade failure. | `test_engine.py` |
| **Tracer with large/exotic payload** | `shared_state` containing datetime objects, Pydantic models, nested dicts 5 levels deep, binary data. Verify: tracer serializes without crash. | `test_tracing.py` |
| **Trace schema shape validation** | Capture `StructuredLogTracer` output from an integration test. Assert required top-level keys (`session_id`, `trigger`, `steps`, `total_latency_ms`, `final_insight_count`), step-level keys (`agent`, `latency_ms`, `status`), and correct types. No field removals from v2.0 baseline. Used as automated release gate. | `test_tracing.py` |
| **Backward compatibility fixture** | Run a real v2.0-style agent config (from existing test fixtures) through the full v2.1 engine. Verify: identical behavior to v2.0 for all existing test cases. | `test_compatibility.py` |
| **Back-to-back error recovery** | Agent fails 3 turns in a row, then succeeds on turn 4 (after cooldown). Verify: cooldown enforced each time, recovery works cleanly, no stale state from prior errors. | `test_engine.py` |

### 14.3 Existing Test Coverage

The existing test suite (`test_engine.py`, `test_blackboard.py`, `test_conditions.py`, `test_compatibility.py`) is comprehensive for v2.0 functionality. **No existing tests should break from v2.1 changes** — if they do, it indicates a backward compatibility violation and the PR must be rejected.

### 14.4 New Test Files

| File | Purpose |
|------|---------|
| `tests/test_dynamic.py` | DynamicAgent-specific tests (schema parsing, Jinja2 safety, response building, malformed output handling) |
| `tests/test_tracing.py` | StructuredLogTracer edge cases (serialization, reference capture, exotic payloads) |

---

## 15. Migration Notes

### 15.1 Compatibility Posture

**No intended schema or host-integration breaking changes.** Some incorrect or unsafe behaviors are intentionally normalized. Specifically:

| Behavior Change | v2.0 | v2.1 | Impact |
|----------------|------|------|--------|
| Callback firing count | 2x per agent | 1x per agent | Telemetry dashboards showing callback counts will see a 50% drop. This is correct behavior, not a regression. Downstream systems (metrics, webhooks) that relied on the doubled count must be updated. |
| `get_memory` return value | Mutable reference to internal dict | Deep copy | Code that mutated the returned dict as a shortcut for `update_memory` will silently stop persisting changes. This is a **correctness fix**. Use `update_memory` explicitly. |
| `to_dict` return value | Shared references | Deep copies | Code that mutated the serialized output to update Blackboard state will silently stop working. This is a **correctness fix**. |
| Jinja2 template rendering | Unsandboxed | Sandboxed | Templates that access Python internals (`__class__`, `__globals__`, `__mro__`) will raise `SecurityError`. All documented template patterns (`{{ blackboard.variables.key }}`, `{{ state.key }}`, `{{ memory.key }}`) continue to work. **Host teams should audit existing templates before deploying v2.1.** |
| `_get_eligible_agents` | Sync method | Async method | Internal-only change. No host API impact. Subclasses of `AgentEngine` that override this method must update the signature. |

### 15.2 For Host Applications (xubb_server, etc.)

| Change | Host Impact |
|--------|-------------|
| New `source_agent_id` field on `AgentResponse` | New optional field, defaults to `None`. Existing code ignoring it is unaffected. |
| Callback methods added to `AgentCallbackHandler` | Default no-ops. Existing subclasses work unchanged. |

### 15.3 For Agent Config Authors

| Change | Impact |
|--------|--------|
| `default_v2.json` `state_field` set to `null` | Agents using `default_v2` schema will stop double-writing state. If host code relied on `response.state_updates` from v2 agents, switch to `response.variable_updates`. |
| Jinja2 sandboxing | **Audit existing templates before deploy.** All documented patterns continue to work. |

### 15.4 Version Bumping

- Framework version: `2.0.0` → `2.1.0`
- Spec version: `2.0.3` → `2.1.0`

---

## 16. Release Gates, Rollout Plan & Success Metrics

### 16.1 Release Gates

The v2.1.0 tag **cannot** be cut until all of the following are satisfied:

| Gate | Criteria | Verified By |
|------|----------|-------------|
| **All blocker PRs merged** | PR1, PR2, PR3, PR4 landed on `main` | Git log |
| **Full test suite green** | All existing + new tests pass. No existing tests may be weakened or removed to accommodate regressions. Test updates are acceptable only when they reflect intended normalized behavior explicitly documented in Section 15. | CI (`pytest --tb=short`) |
| **Invariant tests pass** | Dedicated tests for each invariant in Section 2 all pass. | CI (tagged `@invariant`) |
| **No new warnings** | Zero new `DeprecationWarning` or `RuntimeWarning` in test output. | CI (pytest `-W error::DeprecationWarning`) |
| **Trace format validated** | `StructuredLogTracer` output from integration tests passes automated JSON schema fixture test (verifying required fields, types, no field removals). Optional: manual load-test in `tools/debugger.html` as secondary confirmation. | CI (`test_tracing.py::test_trace_schema_shape`) |
| **Template audit complete** | All approved production agent templates (in repo and in xubb_server config) tested against `SandboxedEnvironment`. | Checklist signed off by config owner |
| **Performance envelope met** | Latency and token consumption within bounds defined in Section 17. | Benchmark suite |

### 16.2 Rollout Strategy

| Phase | Environment | Duration | What Ships | Gate to Advance |
|-------|------------|----------|-----------|----------------|
| **Phase 1** | Dev / staging | 3 days | All 6 PRs | All automated tests pass. Manual smoke test of full conversation flow. |
| **Phase 2** | Internal dogfood (xubb_server internal) | 5 days | v2.1.0-rc1 | 48h of clean operation. No `AttributeError`, no duplicate callbacks in traces, no silent memory loss. |
| **Phase 3** | Production canary (10% of sessions) | 5 days | v2.1.0-rc2 | Error rate equal or lower than v2.0 baseline. Callback counts halved (expected). Token usage reduced or stable. |
| **Phase 4** | Production (100%) | — | v2.1.0 | Canary metrics hold for 48h. |

### 16.3 Rollback Triggers

Automatic rollback to v2.0.0 if any of the following occur during canary or production:

| Trigger | Threshold | Detection |
|---------|-----------|-----------|
| **Agent crash rate** | Any increase above v2.0 baseline | Error logging / APM |
| **AttributeError in callback path** | Any occurrence | Log monitoring (`AttributeError.*callback`) |
| **Turn processing latency** | p95 increase > 20% vs v2.0 baseline | APM / metrics dashboard |
| **Insight delivery rate** | Drop > 5% vs v2.0 baseline | Application metrics |
| **Template rendering failure** | `SecurityError` rate exceeds 1% of turns over a 1h window, **or** any `SecurityError` on a template that passed the pre-deploy audit (Section 16.1). Isolated failures on un-audited templates should be quarantined (disable the affected agent config) and investigated before triggering full rollback. | Log monitoring + config audit trail |

**Rollback procedure:** Revert the framework package version to `2.0.0`. No database migrations or config changes are required — v2.1 is purely a code change. The new `source_agent_id` field on `AgentResponse` defaults to `None`, so v2.0 consumers ignore it.

### 16.4 Feature Flag Guidance

The v2.1 changes are primarily bug fixes and do not introduce new behavior that warrants feature flags. However, two changes have behavioral side effects that hosts may want to gate:

| Change | Flag Recommendation | Rationale |
|--------|-------------------|-----------|
| **Jinja2 sandboxing** (NP1) | Optional: `XUBB_JINJA_SANDBOX=true/false` environment variable, defaulting to `true`. | Allows emergency bypass if a legitimate template is blocked by the sandbox. The flag should be temporary and removed in v2.2. |
| **Callback deduplication** (B2) | No flag needed. | The duplicate firing was always a bug. Downstream systems must adapt. |

### 16.5 Post-Deploy Validation Checklist

After v2.1.0 reaches 100% production:

- [ ] Callback `on_agent_start` count in traces matches agent count (not 2x).
- [ ] Callback `on_phase_start` / `on_phase_end` appear in traces (new events, previously crashed).
- [ ] Zero `AttributeError` in callback code paths for 48h.
- [ ] Zero `TypeError` from tracer serialization for 48h.
- [ ] Silent worker agents (no insights) have their memory updates persisted. Verify via blackboard inspection.
- [ ] Error-rate agents (persistent LLM failures) respect cooldown. Verify via trace log timing.
- [ ] Token consumption per turn is equal or lower than v2.0 (no v2.1 change should increase prompts).
- [ ] All approved production agent templates render without `SecurityError`.

### 16.6 Success Metrics

Quantitative targets that prove v2.1 achieved its goals:

| Metric | Baseline (v2.0) | Target (v2.1) | Measurement |
|--------|-----------------|---------------|-------------|
| `AttributeError` in phase callbacks | Crash on every turn with callbacks | **Zero** | Log monitoring, 7-day window |
| Callback events per agent per turn | 2 (duplicated) | **1** | Trace log analysis |
| Tracer serialization failures | Unknown (uncaught `TypeError`) | **Zero** | Log monitoring (`TURN_TRACE` parse failures) |
| Silent memory update loss | 100% (all dropped) | **Zero** | Regression test suite + production spot checks |
| Cooldown-bypassed error retries | Unbounded (every turn) | **Zero** (cooldown enforced) | Trace log timing analysis |
| SSTI-capable template paths | 1 (unsandboxed `Template()`) | **Zero** | Code audit + `SecurityError` test |
| Prompt token regression | 0 (no change expected in v2.1) | **0** (no increase from v2.1 changes) | Prompt char count comparison on fixed test prompt, before and after each PR. NP11 whitespace reduction deferred to v2.2. |

---

## 17. Performance & Regression Envelope

v2.1 is a hardening release, not a performance release. All changes must stay within the following guardrails. If any bound is exceeded, the change must be justified in the PR description and approved by the team.

| Metric | Acceptable Delta | Notes |
|--------|-----------------|-------|
| **Per-turn latency (p95)** | ≤ +5% | The `deepcopy` additions (B7, B8, B11) are estimated to add < 0.1ms based on typical blackboard sizes in test workloads. The callback deduplication (B2) should reduce latency slightly. Must be verified by benchmark. |
| **Per-turn memory allocation** | ≤ +10% | Deep copies allocate more, but the objects are small (blackboard state). |
| **Log volume per turn** | ≤ +20% | New `on_phase_start`/`on_phase_end` callbacks add log lines. Offset by removing duplicate callback logs. |
| **Token consumption per turn** | ≤ 0% (must not increase) | No v2.1 change affects prompt content. NP11 (whitespace reduction) is deferred to v2.2. Verify no accidental prompt growth from Jinja2 sandbox or other fixes. |
| **Test suite execution time** | ≤ +30% | New test files add coverage. Acceptable growth for hardening. |

### How to Measure

- **Latency & memory:** Run `pytest --benchmark` (add `pytest-benchmark` to dev deps) on a fixed set of integration tests before and after each PR. Compare p50, p95, p99.
- **Token consumption:** Capture `response.debug_info["prompt_messages"]` from a DynamicAgent test, count characters in system prompt before and after each PR. Confirm no growth.
- **Log volume:** Count log lines per `process_turn` in integration test output.

---

## 18. Signoff & Ownership

This release touches framework semantics, host telemetry, template behavior, and operational rollout. Each area has a designated owner responsible for reviewing the relevant PRs and signing off before the v2.1.0 tag is cut.

| Area | Owner | Responsibility | Signs Off On |
|------|-------|---------------|-------------|
| **Framework core** | Framework lead | Reviews PR1 (callbacks), PR2 (lifecycle), PR3 (isolation). Confirms invariants hold. | All blocker PRs |
| **DynamicAgent & templates** | Agent config owner | Reviews PR4 (DynamicAgent fixes). Audits all existing templates against `SandboxedEnvironment` before deploy. | PR4 + template audit checklist |
| **Host integration** | Host/server lead | Validates that xubb_server (or other consumers) handle behavioral changes (callback dedup, `get_memory` copy semantics, `source_agent_id` field). Updates downstream metrics/dashboards if needed. | Migration compatibility |
| **Observability** | Observability / on-call lead | Reviews PR5 (tracing/LLM robustness). Confirms trace format fixture test covers debugger.html requirements. Validates success metrics tooling is in place. | PR5 + metrics dashboards |
| **QA** | QA lead | Runs full test suite + integration/chaos tests (Section 14.2). Confirms performance envelope (Section 17). Executes post-deploy validation checklist (Section 16.5). | Test results + benchmark report |
| **Release** | Release manager | Confirms all release gates (Section 16.1) are met. Coordinates rollout phases. Owns rollback decision during canary. | v2.1.0 tag |

### Signoff Checklist

All signatures required before the v2.1.0 tag is cut:

- [ ] Framework lead: Blocker PRs reviewed and approved
- [ ] Agent config owner: Template audit complete, PR4 approved
- [ ] Host/server lead: Migration impact assessed, downstream updates planned
- [ ] Observability lead: Metrics tooling confirmed, PR5 approved
- [ ] QA lead: Full test suite + benchmarks green
- [ ] Release manager: All gates met, rollout plan confirmed

---

## Appendix A: Full Issue Index

| ID | Severity | Category | File | One-Liner | Classification |
|----|----------|----------|------|-----------|----------------|
| B1 | Critical | Bug | `callbacks.py` | Missing `on_phase_start`/`on_phase_end` — runtime crash | Blocker |
| B2 | High | Bug | `engine.py` + `agent.py` | All callbacks fire twice per agent | Blocker |
| B4 | High | Bug | `agent.py` | No cooldown after error — runaway retries | Blocker |
| B5 | High | Bug | `engine.py` | Memory updates dropped for insight-less responses | Blocker |
| B6 | High | Bug | `dynamic.py` | `check_field` reads wrong object with `root_key` | Blocker |
| NP1 | High | Security | `dynamic.py` | Unsandboxed Jinja2 → SSTI risk | Blocker |
| NP6 | High | Design | `engine.py` + `models.py` | No `source_agent_id` — fragile identity inference | Blocker |
| B7 | Medium | Bug | `engine.py` | `shared_state` shallow copy breaks isolation | Blocker |
| B8 | Medium | Bug | `blackboard.py` | `get_memory` returns mutable internal ref | Blocker |
| B11 | Medium | Bug | `blackboard.py` | `to_dict` shares mutable refs with live state | Blocker |
| B3 | Medium | Bug | `agent.py` | `on_agent_finish` gets `None` on error path | Should-land |
| NP5 | Medium | Design | `dynamic.py` | `private_state` mutated from snapshot data | Should-land |
| NP9 | Medium | Robustness | `tracing.py` | `json.dumps` crashes on non-serializable types | Should-land |
| NP10 | Medium | Robustness | `tracing.py` | `shared_state` captured by ref, not snapshot | Should-land |
| NP13 | Low | Safety | `blackboard.py` | No `sys.*` write protection | Should-land |
| NP2 | Low | Fragility | `models.py` | Mutable literal defaults on `AgentResponse` | Should-land |
| NP7 | Low | Robustness | `llm.py` | No `choices` empty check | Should-land |
| B9 | Low | Bug | `engine.py` | Fire-and-forget task with silent exception loss | Should-land |
| B10 | Low | Bug | `blackboard.py` | `clear_queue` creates phantom entries | Should-land |
| NP11 | Medium | Cost | `dynamic.py` | Excessive whitespace in prompts wastes tokens | Defer v2.2 |
| B12 | Low | Bug | `default_v2.json` | Double-write through both state paths | Defer v2.2 |
| NP3 | Medium | Design | `agent.py` | `AgentConfig` bypasses Pydantic validation | Defer v2.2 |
| NP4 | Low | Design | `callbacks.py` | `ABC` with no abstract methods | Should-land |
| NP8 | Low | Hygiene | `llm.py` | `import json` inside function | Defer v2.2 |
| NP12 | Low | Maintainability | `dynamic.py` | Verbose/fragile trigger parsing | Defer v2.2 |
| NP14 | Low | Performance | `blackboard.py` | O(n) queue pop | Defer v2.2 |
| NP15 | Low | Hygiene | `agent.py` | Dev journal comments in production code | Defer v2.2 |
| NP16 | Low | Dead code | `engine.py` | `_sync_state_from_legacy` never called | Defer v2.2 |

---

*End of specification.*
