# Changelog

All notable changes to the Xubb Agents Framework are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

Public-release hardening. One additive API (`unregister_agent`); no breaking changes.

### Added

- **`AgentEngine.unregister_agent(agent_id) -> bool`** — remove a single agent by id,
  symmetric with `register_agent`. It was missing entirely although a host relied on it
  (the Prompt Studio "test agent" cleanup called it, hitting `AttributeError`). Rebinds
  the registry under the lock and recomputes indices. Contract:
  `AGENT-REGISTRY-MUTATORS-CONSISTENT`.
- `SECURITY.md` — a private vulnerability-disclosure policy, a supported-versions table,
  and the security model (the Jinja2 template-source trust boundary, and the rule that
  agent output is untrusted and must be escaped by the host).
- `docs/README.md` — an index for the documentation tree.
- README badges (contract-gate, license, Python), a one-line pitch, and a **no-key
  offline Quickstart** variant. Both README code blocks are drift-locked by
  `tests/test_readme_quickstart.py`, which executes them in CI.
- `pyproject.toml` Changelog / Bug Tracker / Security URLs, plus discovery keywords and
  classifiers (`Framework :: AsyncIO`, AI topic).
- `CONTRIBUTING.md` (promoted from the README section) and a
  `.github/PULL_REQUEST_TEMPLATE.md` with a contract-checklist.

### Changed

- Copyright and package author set to `genriq` (LICENSE + `pyproject.toml`).
- Minimum Python raised to **3.11**; dropped the untested 3.8–3.10 classifiers so the
  metadata matches what CI actually exercises.
- `AgentContext.blackboard` is now typed `Optional[Blackboard]` (was `Optional[Any]`)
  via a `TYPE_CHECKING` forward reference, restoring static checking on the hottest field.
- Added missing return annotations (`register_agent`/`update_api_key -> None`,
  `check_keyword_triggers -> List[Tuple[BaseAgent, str]]`).
- Softened the `[2.1.0]` security note: "SSTI vulnerability eliminated" → sandboxing as
  defense-in-depth, with untrusted template source called out as a trust boundary.
- Removed self-referential "12/10 Architecture" comments from `library/dynamic.py`.
- Trimmed `docs/EXECUTIVE_SUMMARY.md` to a developer-facing Overview: kept the
  architecture, concepts, and use-case content; dropped the pitch-deck framing.

### Removed

- `docs/PUBLIC_RELEASE_READINESS.md` — an internal pre-launch audit artifact, not
  documentation for the public tree.

### Fixed

- **`register_agent` now mutates the registry lock-safely.** It appended/assigned in
  place while `replace_agents` (called from the vault-reload callback thread) rebinds
  under a lock, so the two could race. `register_agent` now uses the same
  rebind-under-lock discipline; a lock-free reader always sees a complete registry.
- **Legacy memory path no longer aliases live agent state.** The default-format memory
  update assigned the live `self.private_state` dict into the response by reference, so a
  tracer capturing the response (or the next turn's mutation) altered already-emitted
  data. It now emits a copy.
- **Background LLM-client close no longer fire-and-forgets.** `update_api_key`'s async
  client close is now referenced (not GC'd mid-flight) and its failures are logged.
- **README Quickstart crashed on its last line.** It iterated `response.insights` as
  dicts (`insight['type']`) but they are `AgentInsight` objects — a `TypeError` on the
  first code a newcomer runs. Now uses attribute access, drift-locked in CI.

### Security

- **Jinja2 sandbox floor raised to `>=3.1.6`.** Prompt templates render through
  `SandboxedEnvironment`; the sandbox is only as strong as the installed patch level.
  The old `>=3.1.0` floor permitted versions with published sandbox escapes
  (CVE-2024-56201, CVE-2024-56326 — fixed in 3.1.5; CVE-2025-27516 — fixed in 3.1.6).
- **`tools/debugger.html` hardened against DOM XSS.** The metadata pane rendered
  LLM-emitted, transcript-derived content through a `v-html` sink without escaping.
  Values are now HTML-escaped before syntax highlighting.

---

## [2.3.0] - Unreleased

### Added

- **`AgentEngine.replace_agents(agents)`** — atomic full-registry swap for hot
  reloads. Rebuilds the registry and rebinds it LAST, so a concurrent turn never
  observes a half-cleared registry (the unsafe `clear()` + register-loop pattern
  this replaces could drop every agent mid-turn). Contract:
  `AGENT-REGISTRY-ATOMIC-SWAP`.
- **Contract gate (`tools/check_contracts.py`)** — the contract-accuracy gate
  (see `docs/PROCESS.md`). Reads `docs/CONTRACTS.yaml` and hard-fails the
  build for any `covered` contract whose named test is missing, skipped, or failing, and
  for any malformed registry entry; `to_verify`/`uncovered` are reported as debt (not a
  red build) so the framework is not blocked before the bijection back-fill. `--strict`
  additionally requires a passing test for every entry (the full-coverage release gate).
  Production-grade behavior: **fails closed** (`GateError`) when the suite did not run /
  the JUnit report is absent, empty, or unparseable — never a silent pass; a **debt
  ratchet** (`debt_baseline`) fails the build if debt grows, so it can shrink but never
  silently accrete; **node-level bijection** is required for `covered` (file-level refs
  rejected); parametrized tests are aggregated (all-pass → pass, any-fail → fail).
  Decision logic is a pure `evaluate()` over a `{test_ref: outcome}` map for fast,
  deterministic unit tests; the CLI accepts `--junit PATH` so CI runs the suite once.
- **CI workflow (`.github/workflows/contract-gate.yml`)** — runs the suite once (JUnit)
  and feeds the gate via `--junit`, making the Contract Registry an enforced gate rather
  than an advisory doc, with no double execution.
- Four self-covering registry entries (`REGISTRY-WELLFORMED`, `GATE-INFRASTRUCTURE`,
  `CONTRACT-BIJECTION`, `RELEASE-GATE-CI`); the gate guards its own contracts.
- `pyyaml` dev dependency; black/mypy clean under the tool versions pinned at authoring time.

### Fixed

- **Interval trigger mode was inoperative** — `trigger_config.trigger_interval`
  was never parsed into `AgentConfig.trigger_interval`, so an interval-mode
  agent defined via host config could never fire (hosts gate on
  `if interval and ...`). Now parsed and int-coerced; non-numeric or
  non-positive values are warned and treated as absent. Migration note:
  interval-mode configs that previously did nothing WILL start firing.
  Contract: `INTERVAL-CONFIG-PARSED`.
- **Unknown condition `mode` fails closed (C-4)** — an unrecognized mode string
  ("and", "or", "ALL") in `trigger_conditions` fell through to `return True`,
  silently un-gating the agent. It now warns and returns `False`, matching the
  unknown-operator behavior (C-1). Contract: `CONDITIONS-FAIL-CLOSED`.

### Tests / registry

- Contract registry certified to **24/24 covered, debt 0** (blackboard,
  engine/tracing, config-parsing, fail-closed evaluation, and bounded-cascade
  contracts all name passing, rule-asserting tests). Two previously-tested
  behaviors gained registry entries: `CONDITIONS-FAIL-CLOSED` and
  `CASCADE-SINGLE-HOP`. Packaging drift-locks added (`tests/test_packaging.py`).

### Packaging

- **Built wheels now include `library/schemas/*.json`** — the old package-data
  glob was non-recursive, so pip-installed copies shipped without the schemas
  and silently degraded every v2 output format to the emergency fallback
  schema. Explicit `"xubb_agents.library" = ["schemas/*.json"]` package-data
  plus a drift-lock test.
- Version bumped to **2.3.0** (new public API ⇒ minor bump). The `v2.2.0` tag
  is cut retroactively at the 2026-06-08 release commit.

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

See [SPEC_V2_1_1_BUGFIX.md](docs/archive/SPEC_V2_1_1_BUGFIX.md) for full details.

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

See [SPEC_V2_1_HARDENING.md](docs/archive/SPEC_V2_1_HARDENING.md) for full details.

### Security

- Jinja2 templates now render through `SandboxedEnvironment`, mitigating SSTI. The sandbox
  is defense-in-depth, not a guarantee: untrusted template *source* remains a trust boundary
  and its safety depends on the installed Jinja2 patch level (floored at `>=3.1.6`).

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

See [SPEC_V2.md](docs/archive/SPEC_V2.md) for full details.

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
