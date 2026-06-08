# Xubb Agents Framework v2.2
## Hardening & Production-Release Specification

**Version:** 2.2.0
**Status:** DRAFT — awaiting sign-off (no code written)
**Date:** June 8, 2026
**Process Tier:** **Tier 1** (contract change + silent-regression risk → master spec before code; see `process-development-workflow`)
**Scope:** One confirmed critical contract bug, four high-severity robustness gaps, a cluster of medium contract/robustness fixes, and code/doc hygiene — identified during a 5-agent comprehensive audit of v2.1.1.
**Compatibility:** One **deliberate behavioral contract correction** (fact conflict resolution, F-1) that may change which fact wins in consumers relying on the buggy v2.1.1 behavior. All other changes are additive or internal. See [Section 13: Migration Notes](#13-migration-notes).
**Baseline:** Audit performed against `main` @ `47f742d`; work branch `hardening/v2.2.0`.
**Provider decision (this release):** The LLM client remains **OpenAI / OpenAI-compatible** by explicit owner decision. v2.2 does **not** migrate to the Anthropic SDK; it documents OpenAI as the intended provider and removes the "Claude library" ambiguity from prose. (A future Anthropic adapter is out of scope.)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Framework Invariants (v2.2 additions)](#2-framework-invariants-v22-additions)
3. [Scope & Goals](#3-scope--goals)
4. [Issue Index](#4-issue-index)
5. [CRITICAL — Fact Conflict Resolution (F-1)](#5-critical--fact-conflict-resolution-f-1)
6. [HIGH-Severity Items](#6-high-severity-items)
7. [MEDIUM-Severity Items](#7-medium-severity-items)
8. [LOW / Hygiene Items](#8-low--hygiene-items)
9. [Documentation & Provider Items](#9-documentation--provider-items)
10. [Implementation Plan (Phased)](#10-implementation-plan-phased)
11. [Definition of Done (per phase)](#11-definition-of-done-per-phase)
12. [Testing Strategy](#12-testing-strategy)
13. [Migration Notes](#13-migration-notes)
14. [Rollback Plan](#14-rollback-plan)
15. [Release Gates & Success Metrics](#15-release-gates--success-metrics)
16. [Spec Amendment Procedure](#16-spec-amendment-procedure)
17. [Sign-off](#17-sign-off)
18. [Appendix A: Full Finding → Item Traceability](#appendix-a-full-finding--item-traceability)

---

## 1. Executive Summary

A 5-agent comprehensive review of v2.1.1 confirmed that the v2.1/v2.1.1 hardening was effective — **every** documented prior fix (B1–B12, NP1–NP16, D1–D3, T1) actually landed, and the suite passes 105/105. The review surfaced **one genuine critical contract bug that escaped all three prior specs**, plus a set of high/medium robustness and contract-consistency gaps that stand between v2.1.1 and a 16/10 production-grade bar.

### Headline Numbers

| Category | Critical | High | Medium | Low/Hygiene | Doc | Total |
|----------|----------|------|--------|-------------|-----|-------|
| Items | 1 | 4 | 13 | 9 | 6 | 33 |

### Impact Summary

- **1 critical contract bug (F-1):** `Blackboard.add_fact` resolves `(type, key)` conflicts by **confidence only**, silently inverting the documented "higher agent **priority** wins" rule (SPEC_V2 §6.5.4). **Empirically proven live:** a low-priority/conf-0.9 agent beats a high-priority/conf-0.5 agent on the same fact. A high-priority authoritative extractor (budget, stakeholders, timeline) can be silently overruled. No error, no log. **Silent-regression risk to `xubb_server`.**
- **4 high-severity gaps:** the LLM call site has no timeout/retry/`max_tokens` and collapses all failures to silent `None` (R-1); schemas without a `check_field` lose the "stay silent" contract and spam the HUD (A-1); the Phase-2 `trigger_type` mutation is not exception-safe and can permanently corrupt the host-reused context (E-1); the two most-recently-changed public surfaces — `DynamicAgent` and the tracer — have **zero** test coverage (T-1).
- **13 medium items:** memory write-side aliasing, three condition-evaluation traps (fail-open operator, truthy membership, mod-by-zero), three schema/parser drifts (`expiry` requested-but-dropped, `is_state_at_root` dead config, inconsistent v2 state-write path), wall-clock timestamps violating the session-relative convention, unvalidated LLM confidence, `sys.*` leakage, v1 dual-path drop, `update_api_key` races, and an O(n²) merge lookup.
- **Hygiene & docs:** Pydantic deprecation cleanup, debugger v2-field rendering, pytest config robustness, deflaking, and six documentation corrections including the OpenAI provider clarification.

### Guiding Principles for v2.2

1. **Fix the contract, then harden** — F-1 is the load-bearing fix; everything else is defense-in-depth.
2. **Test every fix** — each item ships with at least one regression test; F-1 ships test-first with an engine-level repro.
3. **Phase by risk** — infrastructure → critical → high → medium → hygiene/docs, each phase green before the next.
4. **No silent contract drift** — where code and docs disagree, fix code to match the documented contract unless the owner rules otherwise; record the decision.
5. **One behavioral change, loudly flagged** — F-1 changes which fact wins; consumers are notified in Migration Notes.

---

## 2. Framework Invariants (v2.2 additions)

These extend the v2.1 invariant set (INV-1 … INV-8). Each is currently violated and must hold post-release.

| ID | Invariant | Current Status |
|----|-----------|---------------|
| **INV-9** | Fact conflict resolution is **deterministic** and honors the documented precedence: higher agent **priority** wins; ties broken by **confidence**; remaining ties by **registration order**. | **Resolved** (F-1 — v2.2; `Fact.priority` + engine stamp + `(priority,confidence)` gate; guarded by PROBE-F1) |
| **INV-10** | Every external LLM call is **time-bounded** and fails with **typed, distinguishable** outcomes (timeout vs rate-limit vs auth vs server vs malformed), never an undifferentiated silent `None`. | **Violated** (R-1) |
| **INV-11** | An agent stays **silent** when its schema's gate says so. The **absence** of a gate field must never *force* speech; gate-less schemas default to a safe, documented policy. | **Violated** (A-1 — gate-less schemas always speak) |
| **INV-12** | Any engine mutation of **host-owned context** (`trigger_type`, `phase`, …) is **always restored**, even when the turn raises mid-phase. | **Violated** (E-1 — no `try/finally`) |
| **INV-8′** | INV-8 extended: agent memory values are copies on **write** as well as on read. A caller mutating an object it passed into `set_memory`/`update_memory` must not mutate blackboard state. | **Violated** (M-1 — write side stores references) |
| **INV-13** | Timestamps on `Event` and `Fact` follow the **single documented convention** (session-relative seconds). No code path emits wall-clock epoch where the model documents session-relative. | **Violated** (A-2 — `time.time()` in DynamicAgent) |

Post-release, all invariants (INV-1 … INV-13, INV-8′) must hold. A regression violating any invariant blocks the release.

---

## 3. Scope & Goals

**In scope:** `core/` (engine, blackboard, models, conditions, llm, agent, callbacks), `library/dynamic.py`, `library/schemas/*.json`, `utils/tracing.py`, `tools/debugger.html`, `tests/`, `pyproject.toml`, all `docs/*.md`, `README.md`, `CHANGELOG.md`, `__init__.py`.

**Out of scope (deferred / explicitly not done in v2.2):**
- Migrating the LLM client to the Anthropic SDK (owner chose OpenAI for now — DOC-1 documents this instead).
- Multi-provider abstraction layer.
- The `max_phases > 2` extensibility (E-7 resolves the dead knob by constraining, not by building Phase 3+).
- The B12 `state_field`/`variable_updates_field` double-write design beyond making the existing v2 schemas consistent (S-3).

**Non-goals:** No redesign of the phase model, blackboard data model (beyond the additive `Fact.priority` field), or public API surface beyond the additive/clarifying changes listed here.

---

## 4. Issue Index

Severity → item ID → one-line. Full detail in the referenced sections.

### CRITICAL
- **F-1** — Fact conflict resolution honors confidence only, not priority. (§5)

### HIGH
- **R-1** — LLM call site: no timeout/retry/`max_tokens`; all failures collapse to silent `None`. (§6.1)
- **A-1** — Schemas without `check_field` always emit insights (lose the "stay silent" contract). (§6.2)
- **E-1** — Phase-2 `trigger_type`/`phase` mutation not exception-safe. (§6.3)
- **T-1** — `DynamicAgent` and tracer have zero test coverage. (§6.4)

### MEDIUM
- **M-1** — Memory write side stores caller references (INV-8 half-enforced). (§7.1)
- **C-1** — Unknown condition operator fails **open** (returns `True`). (§7.2)
- **C-2** — `in`/`not_in`/`contains` use truthiness instead of `is None`. (§7.3)
- **C-3** — `mod` with `expected == 0` relies on a distant blanket `except`. (§7.4)
- **S-1** — `expiry` (and `action_label`) requested by schemas but never parsed. (§7.5)
- **S-2** — `is_state_at_root` is dead config in four schemas. (§7.6)
- **S-3** — v2 schemas write state inconsistently (legacy `state_updates` vs `variable_updates`). (§7.7)
- **A-2** — DynamicAgent stamps wall-clock timestamps; convention is session-relative. (§7.8)
- **A-3** — LLM-provided `confidence` passed unvalidated into `AgentInsight`. (§7.9)
- **E-2** — `sys.*` keys leak into legacy `shared_state` and round-trip into the NP13 warning path. (§7.10)
- **E-3** — v1 `state_updates` dropped when `variable_updates` co-present (loses legacy `memory_` writes). (§7.11)
- **E-4** — `update_api_key` races with in-flight turns and leaks the old client. (§7.12)
- **E-5** — `_merge_responses` priority lookup is O(agents × responses). (§7.13)

### LOW / HYGIENE
- **E-6** — `get_event_subscribers` warns every turn (log spam). (§8.1)
- **E-7** — `max_phases` accepts values it ignores (dead knob). (§8.2)
- **E-8** — `check_keyword_triggers` substring matching undocumented. (§8.3)
- **G-1** — Pydantic class-based `Config` → `ConfigDict` (kill deprecation warnings). (§8.4)
- **G-2** — Remove unused imports / minor dead code. (§8.5)
- **DBG-1** — `debugger.html` doesn't render v2 trace fields; `state_updates` shape mismatch. (§8.6)
- **T-2** — pytest config (`asyncio_mode`, markers) + package importability. (§8.7)
- **T-3** — `test_failed_agent_updates_discarded` under-asserts atomicity. (§8.8)
- **T-4** — Cooldown tests are wall-clock-dependent (deflake). (§8.9)

### DOCUMENTATION
- **DOC-1** — Document OpenAI as the intended provider; remove "Claude library" ambiguity. (§9.1)
- **DOC-2** — `EXECUTIVE_SUMMARY.md` footer version `2.1` → `2.2.0`. (§9.2)
- **DOC-3** — Remove stale `_sync_state_from_legacy` (NP16) reference. (§9.3)
- **DOC-4** — README install path references nonexistent `xubb_v6` root. (§9.4)
- **DOC-5** — `technical_spec_agents.md` tracer schema doesn't match emitted output. (§9.5)
- **DOC-6** — Version bump to 2.2.0 across `pyproject.toml`, `__init__.py`, README, CHANGELOG. (§9.6)

---

## 5. CRITICAL — Fact Conflict Resolution (F-1)

### 5.1 The documented contract (must hold)

`Fact` docstring (`core/models.py:47-50`), SPEC_V2 §6.5.4, README:720, `technical_spec_agents.md:293`:

> Facts are deduplicated by `(type, key)` (or by `type` alone when `key is None`). When duplicates exist:
> 1. **Higher agent priority wins.**
> 2. If equal priority, **higher confidence wins.**
> 3. If still equal, **later registration wins.**

### 5.2 The bug (confirmed live)

`core/blackboard.py:144-168` — `add_fact` gates replacement on **confidence only**:

```python
if existing:
    if fact.confidence >= existing.confidence:   # line 164 — priority never consulted
        self.facts.remove(existing); self.facts.append(fact)
```

`core/engine.py:478-480` merges facts in ascending-priority order and relies on the inline claim *"caller handles priority via merge order."* That claim is false: the confidence gate **rejects** the last (higher-priority) writer whenever its confidence is lower. The `Fact` model has **no `priority` field** (`core/models.py:44-56`), so `add_fact` is structurally unable to honor rule 1 as written.

**Empirical repro (proven against the running engine during audit):** Agent A `priority=1, confidence=0.9` and Agent B `priority=10, confidence=0.6` both emit `Fact(type="budget", key="primary")`. Merge applies A then B; `add_fact` sees `0.6 >= 0.9` → False → **B discarded. A (lower priority) wins.** Contract says B must win.

### 5.3 The fix (design)

Make the precedence **explicit and self-contained on the fact**, so resolution is correct regardless of call order, fully deterministic, and serialization-safe.

**(a) `core/models.py` — add an engine-populated precedence field to `Fact`:**

```python
class Fact(BaseModel):
    ...
    priority: int = Field(
        default=0,
        description="Engine-populated emitting-agent priority. Used for conflict "
                    "resolution (higher wins). Agents SHOULD NOT set this; the engine "
                    "stamps it at merge time. Hosts calling add_fact() directly own it.",
    )
```
Additive, defaulted → backward-compatible serialization (old payloads load with `priority=0`; new payloads carry it; old readers ignore it).

**(b) `core/engine.py` `_merge_responses` — stamp priority before dedup:**

```python
for fact in resp.facts:
    fact.priority = agent_priority   # provenance + makes add_fact self-sufficient
    blackboard.add_fact(fact)
```
(`agent_priority` is already resolved in the merge loop.)

**(c) `core/blackboard.py` `add_fact` — resolve by `(priority, confidence)` with registration order as the final tiebreaker:**

```python
if existing:
    # Replace iff the new fact is >= on (priority, confidence). Because add_fact is
    # called in registration order, full equality means the later registration wins.
    if (fact.priority, fact.confidence) >= (existing.priority, existing.confidence):
        self.facts.remove(existing)
        self.facts.append(fact)
else:
    self.facts.append(fact)
```

**Why this satisfies all three rules** (given engine merge order is ascending `(priority, index)` and `add_fact` is called in that order):
- Rule 1 (priority): higher `priority` ⇒ tuple strictly greater ⇒ replaces. ✓
- Rule 2 (confidence within equal priority): equal `priority`, higher `confidence` ⇒ tuple greater ⇒ replaces; lower `confidence` ⇒ tuple smaller ⇒ kept. ✓
- Rule 3 (registration order on full tie): equal `priority` **and** `confidence` ⇒ `>=` true ⇒ the later-called (later-registered) fact replaces. ✓

The rule is also correct for **direct host calls** to `add_fact` that set `priority` explicitly, and degrades to "confidence then call-order" when all priorities are the default `0` (the documented host-responsibility case).

**(d) Docstrings:** update `add_fact` (`blackboard.py:145-152`) and the `Fact` docstring to state the `(priority, confidence, registration-order)` rule and remove the false "higher confidence wins; caller handles priority via merge order" line. Clarify `key=None` = "type is a singleton; same resolution applies."

### 5.4 Tests (test-first — these must FAIL before the fix)

- **Unit (`test_blackboard.py`):**
  - higher `priority` + **lower** `confidence` replaces existing (the inversion repro).
  - equal `priority`, higher `confidence` replaces; lower `confidence` does not.
  - equal `priority` + equal `confidence`: later `add_fact` call wins.
  - `key=None` singleton resolution obeys the same rule.
- **Engine-level (`test_engine.py`):** two agents, `priority=10/conf=0.5` vs `priority=1/conf=0.9`, same `(type,key)` → high-priority value wins on the blackboard **and** in `final_response.facts`. (This is the empirical repro, promoted to a permanent regression test. Mirrors the existing `test_higher_priority_wins` which only covers `variable_updates`.)

### 5.5 Acceptance
INV-9 holds. The new engine-level test fails on `47f742d` and passes after F-1. `test_higher_priority_wins` remains green (variables unchanged).

---

## 6. HIGH-Severity Items

### 6.1 R-1 — LLM call-site resilience
`core/llm.py:37-49`. Add: explicit per-request **timeout** (default suited to a real-time copilot, configurable), bounded **retries with backoff** on transient (429/5xx/timeout), an output **`max_tokens`** cap, and **typed exception handling** that distinguishes rate-limit / auth / server / timeout / malformed-response so the caller (and the B4 cooldown) can react differently from "bad schema." Preserve the existing "never raise into the turn" contract, but surface the failure *class* (e.g., structured return or logged category) rather than an undifferentiated `None`. Honors **INV-10**.
**Tests:** monkeypatch the client to raise each typed error and a timeout; assert the call returns the documented sentinel/結果 without raising and logs the correct category; assert `max_tokens`/`timeout` are passed.

### 6.2 A-1 — Silence contract for gate-less schemas
`library/dynamic.py:291-300`. When a mapping has **no `check_field`** and no `root_key`, `should_speak` currently defaults to `True` whenever content is present — so a custom schema that omits a gate spams every turn. Fix: define and implement a **safe, documented default policy** for gate-less schemas, and **warn at load time** when a schema's instruction references a gate field that the mapping omits. Honors **INV-11**. (Note: `default_v2.json` already sets `check_field: has_insight` and is unaffected; this protects user-authored schemas, which the prompt guide explicitly invites.)
**Tests:** DynamicAgent with a gate-less schema returning content → respects the documented default (no unintended speech); load-time warning fires on gate-field/mapping mismatch.

### 6.3 E-1 — Phase-2 mutation exception safety
`core/engine.py:271-324`. Wrap the Phase-2 block so `context.trigger_type` and `context.phase` are restored in a `finally`, guaranteeing the host-owned context is never left in a corrupted `EVENT`/`phase=2` state when `_run_phase`/`_merge_responses` raises. Honors **INV-12**.
**Tests:** force a Phase-2 exception (mock `_run_phase` to raise); assert `context.trigger_type`/`context.phase` are restored and `on_chain_error` still fires.

### 6.4 T-1 — DynamicAgent + tracer coverage
Add the test files the v2.1.1 spec itself mandated but never shipped, plus tracer coverage:
- `test_dynamic_agent.py`: the B1 auto-add-`EVENT` behavior (`test_dynamic_agent_auto_adds_event_trigger_type`), prompt assembly order & no-leading-whitespace (`test_prompt_has_no_leading_whitespace`), gate/`should_speak` logic (incl. A-1), JSON parse of LLM output, sandboxed Jinja2 render, memory read/write path, confidence handling (A-3).
- `test_tracing.py`: assert the emitted trace contains the v2 fields (`variable_updates`, `events_emitted`, `facts_count`, `queue_pushes`, `memory_updates_keys`) and that the schema matches what `debugger.html` consumes (ties to DBG-1).
**Acceptance:** `DynamicAgent` and `utils/tracing.py` move from 0% to meaningful coverage; the spec-mandated test names exist.

---

## 7. MEDIUM-Severity Items

### 7.1 M-1 — Memory write-side copy
`core/blackboard.py:192-200`. `set_memory`/`update_memory` store caller references; reads deep-copy (B8) but writes don't. Deep-copy on write (or document a hard no-retain contract — implementation chooses deep-copy for symmetry). Honors **INV-8′**.
**Test:** mutate a nested object after `update_memory`; assert blackboard state is unchanged.

### 7.2 C-1 — Unknown operator fails closed
`core/conditions.py:204-206`. Unknown operator returns `True` (fail-**open**) — a typo'd operator fires the agent every turn, contradicting the module's stated fail-closed philosophy. Return `False` and keep the warning.
**Test:** rule with a bogus operator → evaluates `False`, warning logged.

### 7.3 C-2 — Membership operators use `is None`, not truthiness
`core/conditions.py:155-171`. `in`/`not_in`/`contains` treat any falsy `expected` (e.g. `0`, `""`) as "empty", taking the wrong branch. Guard on `expected is None`.
**Test:** `in` with `expected = 0` / `""` performs a real membership test.

### 7.4 C-3 — `mod` by zero
`core/conditions.py:197-208`. `expected == 0` raises `ZeroDivisionError`, caught only by the distant blanket `except` in `_evaluate_rule`. Add `ZeroDivisionError` to the local guard (and/or explicit `expected == 0` handling) so behavior is local and intentional.
**Test:** `mod` rule with `expected = 0` → `False`, no leak past the local guard.

### 7.5 S-1 — `expiry` / `action_label` requested but dropped
`library/schemas/*` instruct the model to return `expiry` (and `action_label`); `library/dynamic.py` and `core/agent.py:create_insight` never read them, so every insight gets the default. **Decision:** parse and pass them through to `create_insight` (preferred — honors the schema contract), OR remove them from the schema instructions. Implementation will **parse them through** unless the owner prefers removal.
**Test:** schema returning `expiry`/`action_label` → values reach the `AgentInsight`.

### 7.6 S-2 — `is_state_at_root` dead config
`is_state_at_root` appears in four schemas but is never read by the parser (which always reads `state_field` from root). **Decision:** remove the key from the schemas (it implies behavior that doesn't exist) — unless a real use case is identified, in which case implement it. Default: **remove**.
**Test:** schema-load test asserts no reliance on the removed key; existing schema-driven tests stay green.

### 7.7 S-3 — v2 state-write consistency
`v2_raw.json`, `ui_control.json`, `widget_control.json` route state only through the v1 `state_updates` path, while `default_v2.json` uses `variable_updates`. A v2-only host reading `variable_updates` misses updates from the former. Standardize all v2 schemas onto `variable_updates_field` (or normalize `state_updates → variable_updates` centrally and document it).
**Test:** each v2 schema's state updates land in `final_response.variable_updates` and on the blackboard.

### 7.8 A-2 — Session-relative timestamps
`library/dynamic.py:377,418` use `time.time()` (wall-clock epoch) while `Event.timestamp`/`Fact.timestamp` are documented as "seconds since session start." Thread a session-start reference (or session clock) into the agent and emit session-relative values. Honors **INV-13**.
**Test:** emitted `Event`/`Fact` timestamps are session-relative, not epoch.

### 7.9 A-3 — Clamp LLM confidence
`library/dynamic.py:319-326`. Model-supplied `confidence` is passed verbatim into `AgentInsight` (`ge=0, le=1`); a bad value (`1.5`, `"high"`) turns a good insight into an ERROR. Coerce to float, clamp to `[0,1]`, default `1.0` on failure.
**Test:** out-of-range / non-numeric confidence → clamped/defaulted, insight still valid.

### 7.10 E-2 — `sys.*` leak into legacy `shared_state`
`core/engine.py:599-600` copies all blackboard variables (incl. `sys.*`) into v1 `shared_state`; a v1 agent echoing it back trips the NP13 path. Exclude `sys.*` when syncing to legacy.
**Test:** after sync, `shared_state` contains no `sys.*` keys; v1 round-trip doesn't warn.

### 7.11 E-3 — v1 dual-path drop
`core/engine.py:493-503`. The legacy `state_updates` branch only runs when `variable_updates` is absent, so a hybrid response silently loses legacy `memory_` writes. Process `memory_` keys unconditionally; only skip the plain-var portion when v2 vars supersede.
**Test:** response with both `state_updates` (incl. `memory_x`) and `variable_updates` → the `memory_x` write is applied.

### 7.12 E-4 — `update_api_key` safety
`core/engine.py:71-76`. Document (and where feasible enforce) that it must not run concurrently with `process_turn`; close the previous `LLMClient`/session to avoid leaking the HTTP pool.
**Test:** old client `close()` invoked; doc/precondition asserted.

### 7.13 E-5 — Merge lookup O(n²)
`core/engine.py:439-445`. Replace the per-response linear `self.agents` scan with an O(1) lookup (store `priority` alongside index in `_agent_index` or a parallel map); log a warning when a response's `agent_id` is unresolvable (latent ordering bug). Pure internal optimization + observability.
**Test:** merge ordering unchanged (existing tests stay green); unresolvable `agent_id` logs a warning.

---

## 8. LOW / Hygiene Items

- **8.1 E-6** — `get_event_subscribers` (`engine.py:108-114`): warn-once per misconfigured agent id, not every turn.
- **8.2 E-7** — `max_phases` (`engine.py` ctor): constrain to `{1, 2}` (raise/clamp + document) rather than silently ignoring `>2`. No Phase 3+ is built.
- **8.3 E-8** — `check_keyword_triggers` (`engine.py:142`): document substring (not word-boundary) matching in the docstring.
- **8.4 G-1** — Replace class-based Pydantic `Config` with `ConfigDict` in `Blackboard`/`AgentContext` (kills the 2 deprecation warnings; readies for Pydantic v3). Verify `arbitrary_types_allowed` is still needed; drop if not.
- **8.5 G-2** — Remove unused imports / dead code surfaced in audit (e.g. unused `AgentInsight`/`InsightType` in `engine.py`); keep changes mechanical and behavior-free.
- **8.6 DBG-1** — `tools/debugger.html`: render the v2 trace fields (`variable_updates`, `events_emitted`, `facts_count`, `queue_pushes`, `memory_updates_keys`) and fix the `state_updates` shape assumption (dict vs key-list) to match `tracing.py`.
- **8.7 T-2** — Add `[tool.pytest.ini_options]` with `asyncio_mode` + registered markers; make the package importable independent of the checkout directory name (root `conftest.py` or `pip install -e .` guidance documented). The current green run depends on the dir being named `xubb_agents`.
- **8.8 T-3** — Strengthen `test_failed_agent_updates_discarded` (`test_engine.py:275-302`): have the failing agent attempt an observable write and assert it does **not** land (true atomicity assertion, not tautology).
- **8.9 T-4** — Deflake cooldown tests (`test_engine.py:402-594`): inject/monkeypatch the clock instead of relying on real `time.time()` margins.

---

## 9. Documentation & Provider Items

- **9.1 DOC-1** — **Provider clarification (owner decision: OpenAI for now).** Update README, `SPEC_V2.md` §4.5 cross-refs, and any "Claude library" framing to state the framework targets **OpenAI / OpenAI-compatible** endpoints (default model documented honestly). Note a future Anthropic adapter as out-of-scope. Update project memory (`project-xubb-agents`) to record the resolution so the ambiguity doesn't resurface.
- **9.2 DOC-2** — `docs/EXECUTIVE_SUMMARY.md` footer `Version: 2.1` → `2.2.0`; reconcile body version references.
- **9.3 DOC-3** — Remove/mark-resolved the `SPEC_V2_1_HARDENING.md` NP16 reference to `_sync_state_from_legacy` (method does not exist).
- **9.4 DOC-4** — `README.md:13` — drop the stale `xubb_v6` parent-root install instruction.
- **9.5 DOC-5** — `technical_spec_agents.md` §7.2: replace the aspirational tracer JSON with the **actual** emitted shape (or label it "target schema"), consistent with DBG-1.
- **9.6 DOC-6** — Version bump to **2.2.0** in `pyproject.toml`, `__init__.py` (`__version__`), README header, and a new `CHANGELOG.md` `[2.2.0]` section enumerating every item above.

---

## 10. Implementation Plan (Phased)

Each phase is a set of **atomic commits** on `hardening/v2.2.0`. A phase must be **green** (DoD met) before the next begins. Test-first where a regression repro is possible (always for F-1).

| Phase | Theme | Items | Rationale |
|-------|-------|-------|-----------|
| **0** | Test & build infrastructure | T-2, T-3, T-4 | Make the suite robust, deterministic, and dir-name-independent **first**, so every later fix is verifiable on solid ground. |
| **1** | CRITICAL contract | **F-1** | The load-bearing fix. Test-first: land the failing engine repro, then the model/blackboard/engine change. |
| **2** | HIGH robustness | R-1, A-1, E-1, T-1 | Resilience + silence contract + exception safety + the missing public-surface tests. |
| **3** | MEDIUM consistency | M-1, C-1, C-2, C-3, S-1, S-2, S-3, A-2, A-3, E-2, E-3, E-4, E-5 | Contract/robustness drift; grouped by subsystem (conditions, schemas, agent, engine, blackboard). |
| **4** | Hygiene, docs, release | E-6, E-7, E-8, G-1, G-2, DBG-1, DOC-1…6 | Deprecations, debugger, docs, version bump, CHANGELOG, finalize spec status → open PR. |

Commit message convention: `v2.2/<ITEM-ID>: <summary>` (e.g. `v2.2/F-1: honor agent priority in fact conflict resolution`). One item (or one tightly-coupled item cluster) per commit.

---

## 11. Definition of Done (per phase)

A phase is **Done** when **all** hold:

1. **Code:** every item in the phase implemented per its section.
2. **Tests:** each item has ≥1 regression test; for F-1, the engine-level repro demonstrably failed pre-fix and passes post-fix.
3. **Suite green:** `python -m pytest -q` passes with **zero** failures/errors and **no new warnings** (Phase 4 also drives the existing Pydantic warnings to zero via G-1).
4. **Invariants:** no invariant (INV-1…INV-13, INV-8′) regressed; invariants the phase targets now hold.
5. **Docs in lockstep:** any contract touched in the phase has its doc/docstring updated in the **same** phase (no deferred doc debt).
6. **CHANGELOG:** the `[2.2.0]` section updated with the phase's items (running, not end-loaded).
7. **Self-review:** diff reviewed for scope creep; no unrelated changes.

Release-level DoD (end of Phase 4): full suite green, coverage added for `DynamicAgent`/tracer, version consistently `2.2.0` everywhere, spec status flipped to **Implemented**, PR opened with description + full test output.

---

## 12. Testing Strategy

- **Test-first for F-1**: commit the failing engine repro before the fix; CI history proves the bug existed and is closed.
- **One regression test per item minimum**; integration-level where the bug is an interaction (F-1, E-1, E-3, S-3).
- **Determinism**: no wall-clock dependence (T-4); injected clocks for cooldown/timeouts.
- **Coverage floor**: `DynamicAgent` and `utils/tracing.py` move from 0 to meaningful coverage (T-1).
- **Target count**: v2.1.1 shipped 105 tests. v2.2 adds roughly **20–30** (F-1 ×5, R-1 ×3, A-1 ×2, E-1 ×2, T-1 DynamicAgent/tracer ×8–12, plus one per medium/hygiene item). Final count recorded at release.
- **No tautologies**: T-3 specifically converts an under-asserting test into a real atomicity check.
- **Regression envelope**: existing 105 tests must stay green at every phase boundary (only intentional contract changes — F-1 fact resolution — may alter an assertion, and that change is explicit and reviewed).

---

## 13. Migration Notes

**One behavioral change for consumers (`xubb_server` and other hosts):**

- **F-1 (fact conflict resolution):** Facts that collide on `(type, key)` now resolve by **priority first**, then confidence, then registration order — matching the always-documented contract. **Consumers that (knowingly or not) depended on the buggy v2.1.1 "highest-confidence-regardless-of-priority" behavior may see a different fact win.** This is a deliberate correction of a documented contract, not a new feature. **Action for hosts:** verify that agent `priority` values reflect intended authority for fact extraction; a high-priority extractor will now correctly override lower-priority agents even at lower confidence.

**Additive / non-breaking:**
- `Fact.priority` is a new defaulted field; serialized v2.1.1 facts load unchanged (`priority=0`).
- R-1 adds timeout/retry/`max_tokens` with conservative defaults; behavior under success is unchanged.
- A-1 changes only the **gate-less custom schema** path; shipped schemas (`default_v2` etc.) are unaffected.
- S-2 removes a key (`is_state_at_root`) that was never read — no behavior change.
- S-3 makes v2 schemas populate `variable_updates`; hosts already reading `variable_updates` gain previously-missing updates (strictly additive for correct v2 hosts).

**No host-integration breaking changes** beyond the F-1 resolution correction.

---

## 14. Rollback Plan

- **Granularity:** every item is one (or a tight cluster of) atomic commit(s) tagged `v2.2/<ITEM-ID>`; any single item is revertible via `git revert` without disturbing others.
- **Phase rollback:** a phase is a contiguous commit range; revert the range to drop the whole phase.
- **F-1 specific:** the `Fact.priority` field is additive and defaulted, so reverting F-1 (model + blackboard + engine commits) restores v2.1.1 fact behavior with no serialization migration. Reverting F-1 also reverts its tests.
- **Release rollback:** the branch is never merged to `main` until the release-level DoD passes and the PR is approved; `main` stays shippable throughout.
- **Forward-fix preference:** for issues found post-merge, prefer a forward fix on a new `hardening/v2.2.1` branch over reverting a landed contract correction.

---

## 15. Release Gates & Success Metrics

**Gates (all must pass to flip status to Implemented / open the release PR):**
1. Full suite green, zero failures/errors, zero deprecation warnings.
2. F-1 engine repro present and passing; `test_higher_priority_wins` still green.
3. `DynamicAgent` + tracer coverage present (T-1).
4. Version `2.2.0` consistent across `pyproject.toml`, `__init__.py`, README, CHANGELOG, this spec.
5. All INV-1…INV-13 + INV-8′ hold (checklist reviewed).
6. CHANGELOG `[2.2.0]` complete; Migration Notes (F-1) called out for hosts.

**Success metrics:**
- Zero silent fact-priority inversions (INV-9).
- LLM calls bounded; failure categories observable (INV-10).
- No gate-less-schema spam (INV-11).
- No context corruption on Phase-2 error (INV-12).
- Suite deterministic (no wall-clock flakiness) and dir-name-independent.

---

## 16. Spec Amendment Procedure

Per Tier-1 process: if implementation reveals a needed deviation (e.g., a better F-1 design, or an item that turns out to be larger than scoped):
1. **Pause** the affected item.
2. **Propose** the change here (and to the owner) with rationale.
3. **Sign-off** from the owner.
4. **Append** an "Amendment N" block to this section recording the change, date, and reason.
5. **Resume.**

No silent scope changes. Items may be **downgraded/deferred** to v2.2.1 only via an amendment with owner sign-off.

_(No amendments yet.)_

---

## 17. Sign-off

| Role | Name | Decision | Date |
|------|------|----------|------|
| Owner | @genriq | ☐ Approve spec → begin Phase 0 | — |
| Author | Claude (audit + spec) | Drafted | 2026-06-08 |

**This spec is DRAFT. No code will be written until the owner signs off (Tier-1 gate).** On approval, implementation proceeds Phase 0 → 4 on `hardening/v2.2.0`, each phase green before the next, ending in a PR.

---

## Appendix A: Full Finding → Item Traceability

Every finding from the 5-agent audit maps to exactly one v2.2 item (or is explicitly deferred).

| Audit finding | Source agent(s) | v2.2 Item | Disposition |
|---------------|-----------------|-----------|-------------|
| Fact priority inverted by confidence gate | All 5 (engine, state, docs, tests, +empirical) | **F-1** | Fix (critical) |
| LLM no timeout/retry/max_tokens, silent `None` | LLM | **R-1** | Fix (high) |
| Gate-less schema always speaks | LLM | **A-1** | Fix (high) |
| Phase-2 trigger_type not exception-safe | Engine | **E-1** | Fix (high) |
| Zero DynamicAgent/tracer tests | Tests, LLM | **T-1** | Fix (high) |
| Memory write-side aliasing (INV-8 half) | State | **M-1** | Fix (medium) |
| Unknown operator fail-open | State, Tests | **C-1** | Fix (medium) |
| Membership truthiness vs `is None` | State | **C-2** | Fix (medium) |
| `mod` by zero handling | State, Tests | **C-3** | Fix (medium) |
| `expiry`/`action_label` dropped | LLM | **S-1** | Fix (medium) |
| `is_state_at_root` dead config | LLM | **S-2** | Fix (remove) |
| v2 state-write inconsistency | LLM, Docs | **S-3** | Fix (medium) |
| Wall-clock timestamps | LLM | **A-2** | Fix (medium) |
| Unvalidated LLM confidence | LLM | **A-3** | Fix (medium) |
| `sys.*` leak into shared_state | Engine | **E-2** | Fix (medium) |
| v1 dual-path drop | Engine | **E-3** | Fix (medium) |
| `update_api_key` race/leak | Engine | **E-4** | Fix (medium) |
| Merge O(n²) lookup | Engine | **E-5** | Fix (medium) |
| Event-subscriber warn spam | Engine | **E-6** | Fix (low) |
| `max_phases` dead knob | Engine | **E-7** | Fix (low) |
| Keyword substring matching | Engine | **E-8** | Doc (low) |
| Pydantic class `Config` deprecation | Tests, State | **G-1** | Fix (hygiene) |
| Unused imports / dead code | Engine | **G-2** | Fix (hygiene) |
| Debugger missing v2 fields / shape | Tests | **DBG-1** | Fix (low) |
| pytest config / importability | Tests | **T-2** | Fix (infra) |
| Atomicity test under-asserts | Tests | **T-3** | Fix (infra) |
| Cooldown tests wall-clock-flaky | Tests | **T-4** | Fix (infra) |
| "Claude library" vs OpenAI code | LLM, Docs | **DOC-1** | Document (OpenAI) |
| EXEC_SUMMARY footer version | Docs | **DOC-2** | Doc fix |
| NP16 dead-code reference | Docs | **DOC-3** | Doc fix |
| README `xubb_v6` install path | Docs | **DOC-4** | Doc fix |
| Tracer schema doc mismatch | Docs, Tests | **DOC-5** | Doc fix |
| Version bump 2.2.0 | Docs | **DOC-6** | Release |
| Memory read-path disconnect (prior memory note) | (prior review) | — | **Deferred** to v2.2.1 — needs design (engine never syncs blackboard memory → `shared_state`); flagged, not scoped here. |
| Anthropic SDK migration | LLM | — | **Out of scope** (owner: OpenAI for now; DOC-1) |
| B12 double-write redesign | (prior spec) | partial via S-3 | Deferred beyond S-3 consistency |
