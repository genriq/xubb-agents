# Changelog

All notable changes to the Xubb Agents Framework are documented here.

---

## [2.2.0] - 2026-06-08

Production-hardening release driven by the v2.2 5-agent audit: 1 critical contract bug,
4 high-severity gaps, 13 medium fixes, an additive memory-persistence fix (MR-1), plus
test-infra, hygiene, and a full documentation refresh. Suite 105 → 224, zero warnings.
See [SPEC_V2_2_HARDENING.md](docs/SPEC_V2_2_HARDENING.md).

### Bug Fixes

- **F-1** (CRITICAL): Fact conflict resolution now honors agent **priority** (INV-9).
  `Blackboard.add_fact` previously resolved `(type, key)` collisions by confidence only,
  silently inverting the documented "higher priority wins" rule (SPEC_V2 §6.5.4) — a
  high-priority extractor could be overruled by a lower-priority/higher-confidence agent.
  Added `Fact.priority` (engine-stamped); `add_fact` now resolves by
  `(priority, confidence)` with later registration breaking full ties.
  **Migration:** consumers relying on the buggy confidence-only behavior may see a
  different fact win — verify agent `priority` reflects intended extraction authority.
  Guarded permanently by `PROBE-F1` (`tests/qa_probes/`).
- **C-1**: condition evaluation now fails **closed** on an unknown/typo'd operator
  (was fail-open → fired every turn).
- **C-2**: `in`/`not_in` membership operators guard on `expected is None` instead of
  truthiness, so a legitimately-falsy expected (`0`, `""`) runs a real membership test.
- **C-3**: `mod` operator handles `expected == 0` locally (returns False, no
  `ZeroDivisionError` leak).
- **S-1**: `DynamicAgent` now parses `expiry`/`action_label` from LLM output and passes
  them through to `AgentInsight` (previously requested by schemas but silently dropped).
- **A-2** (INV-13): `Event`/`Fact` timestamps emitted by `DynamicAgent` are now
  session-relative (derived from the conversation window) instead of wall-clock epoch.
- **A-3**: model-supplied `confidence` is coerced to float and clamped to [0,1] before
  building the insight (a bad value no longer turns a good insight into an ERROR).
- **E-2**: `sys.*` keys are excluded when syncing blackboard variables to the v1
  `shared_state` (no longer trips the reserved-key warning on v1 round-trip).
- **E-3**: legacy `state_updates` `memory_` writes are applied even when
  `variable_updates` is also present (hybrid v1/v2 responses no longer drop them).
- **M-1** (INV-8'): `set_memory`/`update_memory` deep-copy on write, closing the
  write-side aliasing gap (memory is now copied in both directions).

### Changed

- **S-2**: removed the dead `is_state_at_root` key from all schemas (never read by the
  parser).
- **S-3**: v2 schemas (`v2_raw`, `ui_control`, `widget_control`) route state through
  `variable_updates_field` for consistency with `default_v2` (v2-only hosts now see their
  state updates in `variable_updates`).
- **E-4**: `update_api_key` closes the previous LLM client's session (no pool leak) and
  documents the no-concurrent-`process_turn` precondition.

- **R-1** (INV-10): the LLM call site (`core/llm.py`) is now resilient — explicit
  request timeout, bounded retries with backoff (429/5xx/timeout), `max_tokens` cap, and
  typed exception handling that logs a distinct failure category (timeout / rate_limit /
  auth / server / malformed) via `last_error_category`. The never-raise / return-`None`
  contract is preserved (callers unaffected).
- **A-1** (INV-11): gate-less + rootless schemas now default to **silence** (a schema must
  opt in via `speak_without_gate: true` to speak on content alone); a load-time warning
  fires when a schema's instruction references a gate field but the mapping omits
  `check_field`. Shipped schemas (all gated or root-keyed) are unaffected.
- **E-1** (INV-12): the Phase-2 execution block now restores `context.trigger_type` and
  `context.phase` via `try/finally`, so a Phase-2 exception can no longer leave the
  host-reused context corrupted as `EVENT`/`phase=2`.

### Performance

- **E-5**: `_merge_responses` resolves agent priority via an O(1) `_agent_meta` lookup
  instead of an O(agents × responses) linear scan; unresolvable agent ids log a warning.

- **MR-1** (INV-14, Amendment 1): cross-turn agent memory now survives even when the host
  re-instantiates agents per turn. Memory is stored on the blackboard but `DynamicAgent`
  reads it from `shared_state["memory_<id>"]`; `_sync_state_to_legacy` now populates those
  keys from `blackboard.memory` (deep-copied) before agents run. **Migration:** hosts that
  manually wrote `shared_state["memory_<id>"]` should write via `blackboard.update_memory`.
- **E-6**: misconfigured event-subscriber warning is now emitted once per agent, not every turn.
- **DBG-1**: `tools/debugger.html` now renders per-step `state_updates` as a dict (was a
  no-op `.length` guard) and displays the v2 trace fields (`variable_updates`,
  `events_emitted`, `facts_count`, `queue_pushes`, `memory_updates_keys`).

### Changed

- **S-2**: removed the dead `is_state_at_root` key from all schemas (never read by the parser).
- **S-3**: v2 schemas (`v2_raw`, `ui_control`, `widget_control`) route state through
  `variable_updates_field` for consistency with `default_v2`.
- **E-4**: `update_api_key` closes the previous LLM client's session and documents the
  no-concurrent-`process_turn` precondition.
- **E-7**: `max_phases` now only accepts `1` or `2`; other values are clamped with a warning.
- **G-1**: migrated the deprecated class-based Pydantic `Config` to `ConfigDict` on
  `Blackboard`/`AgentContext` — eliminates the `PydanticDeprecatedSince20` warnings (suite
  now runs with **zero warnings**).
- **G-2**: removed unused imports (`AgentInsight`/`InsightType` in `core/engine.py`); the
  tracked `__pycache__` bytecode is now untracked.
- **E-8**: documented that `check_keyword_triggers` uses case-insensitive substring matching.

### Performance

- **E-5**: `_merge_responses` resolves agent priority via an O(1) `_agent_meta` lookup
  instead of an O(agents × responses) linear scan; unresolvable agent ids log a warning.

### Tests & tooling

- **T-1**: first coverage for `DynamicAgent` (incl. spec-mandated auto-add-`EVENT` and
  prompt-no-leading-whitespace) and the tracer; resilience tests for `core/llm.py`.
- **T-2**: added `[tool.pytest.ini_options]` (`asyncio_mode`, registered markers, `pythonpath`)
  and a repo-root `conftest.py` so the suite is importable independent of the checkout
  directory name (previously the green suite depended on the dir being named `xubb_agents`).
- **T-3**: strengthened the atomic-discard test (INV-6) — a failed agent now attempts an
  observable write that must not persist (was tautological).
- **T-4**: cooldown tests use a frozen clock for deterministic elapsed time (no wall-clock flakiness).
- Suite 105 → **224**, zero warnings.

### Documentation

- **DOC-1**: documented OpenAI / OpenAI-compatible as the intended provider (Anthropic adapter
  out of scope); removed "Claude library" ambiguity.
- **DOC-2**: version → 2.2.0 across README, EXECUTIVE_SUMMARY, technical spec, prompt guide,
  `pyproject.toml`, `__init__.py`.
- **DOC-3**: withdrew the stale NP16 `_sync_state_from_legacy` reference in SPEC_V2_1_HARDENING.
- **DOC-4**: removed the stale `xubb_v6` install path from the README.
- **DOC-5**: replaced the aspirational tracer-schema example with the actual emitted shape.
- Full accuracy sweep of README + docs against the v2.2 code (Fact `priority`, MR-1/M-1
  memory, R-1 resilience, A-1 silence gate, condition fail-closed, session-relative timestamps).

---

## [2.1.1] - 2026-03-19

Bugfix release: 4 bug fixes, 3 defense-in-depth improvements, 1 test correction.

See [SPEC_V2_1_1_BUGFIX.md](docs/SPEC_V2_1_1_BUGFIX.md) for full details.

### Bug Fixes

- **B1**: `get_event_subscribers()` now validates `TriggerType.EVENT` — agents with `subscribed_events` but missing `EVENT` trigger type are excluded with a warning
- **B2**: `_sync_state_to_legacy()` runs before Phase 2 — v1 agents in Phase 2 now see correct `shared_state`
- **B4**: Added `memory_updates_by_agent` field on `AgentResponse` — per-agent keyed memory available on aggregated responses (additive, `memory_updates` unchanged)
- **B5**: `process_turn` wrapped for `on_chain_error` — callback now fires on unhandled exceptions

### Improvements

- **D1**: Prompt whitespace elimination in `DynamicAgent` — no blank sections when optional context is absent
- **D2**: Class-level `SandboxedEnvironment` in `DynamicAgent` — single Jinja2 env instance instead of per-call allocation
- **D3**: v2 fields added to `StructuredLogTracer` — traces now include events, facts, queues, variables, memory

### Convenience

- `DynamicAgent` auto-adds `TriggerType.EVENT` when `subscribed_events` is set

### Test Fixes

- **T1**: Fixed false-positive subscriber test — subscriber agent now correctly uses `TriggerType.EVENT` with `cooldown=0`

---

## [2.1.0] - 2026-03-18

Hardening release: no new features, only bug fixes and production-grade improvements.

See [SPEC_V2_1_HARDENING.md](docs/SPEC_V2_1_HARDENING.md) for full details.

### Security

- Jinja2 templates now sandboxed (`SandboxedEnvironment`) — SSTI vulnerability eliminated

### Bug Fixes

- `source_agent_id` field on `AgentResponse` — reliable agent identity (no more insight-based inference)
- `get_memory()` returns deep copy — snapshot isolation enforced
- `to_dict()` returns deep copies — no mutable reference leaks
- Callbacks fire exactly once per agent (previously fired 2x due to engine + agent duplication)
- Cooldown enforced after errors — prevents runaway retries on persistent failures

### Additions

- `on_phase_start`, `on_phase_end`, `on_agent_skipped` callbacks added
- `AgentCallbackHandler` is no longer `ABC` — subclasses don't need to implement anything
- `sys.*` write protection on Blackboard — warns on non-engine writes to reserved keys

---

## [2.0.0] - 2026-01-27

Major release: structured Blackboard, event-driven agent coordination, multi-phase execution.

See [SPEC_V2.md](docs/SPEC_V2.md) for full details.

### Added

- Structured Blackboard with 5 typed containers (Variables, Events, Queues, Facts, Memory)
- Event-driven pub/sub agent coordination
- Blackboard-aware trigger conditions with 14 operators
- Multi-phase execution (Phase 1: normal agents, Phase 2: event-triggered agents)
- `TriggerType.EVENT` for agent-to-agent coordination
- `DynamicAgent` with Jinja2 templating and pluggable output schemas
- `ConditionEvaluator` for trigger preconditions
- Priority-based merge ordering (ascending, last-write-wins)

### Removed

- Response caching (replaced by cooldowns + trigger conditions)

### Compatibility

- 100% backward compatible with v1.0 agents
- `shared_state` auto-mapped to `blackboard.variables`
- `state_updates` auto-mapped to `variable_updates`

---

## [1.0.0] - 2025

Initial release: parallel agent execution with flat shared state.
