# Changelog

All notable changes to the Xubb Agents Framework are documented here.

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
