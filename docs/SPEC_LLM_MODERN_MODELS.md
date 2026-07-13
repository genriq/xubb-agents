# Xubb Agents Framework v2.5 / v2.6
## Modern-Model Compatibility Specification (llm-modern-models)

**Version:** 2.5.0 (Release A) / 2.6.0 (Release B) — staged; see §10
**Status:** APPROVED — 2026-07-13 (owner @genriq; rulings D-1 hard-fail · D-2 two releases · D-3 defer · D-4 defer). Amendment 1 (spec-review findings) applied and ratified same day. **Phase 0 (QW-1..3) and Release A (WC-1, OB-1, OB-2, DOC-A) IMPLEMENTED** on `feature/v2.5-llm-modern-models` — suite green, contract gate 27/27. Release B (2.6.0) pending.
**Date:** July 13, 2026
**Process Tier:** **Tier 1** (contract change + config-schema change + silent-regression risk → spec approved before code; see docs/PROCESS.md)
**Scope:** Full compatibility with modern OpenAI models (GPT-5.x, GPT-5.6 sol/terra/luna, o-series) with **cheap-by-default two-lane economics**: whisper agents stay fast and near-free; reasoning is an explicit per-agent opt-in. Derived from a three-lens validation (API-facts vs OpenAI docs, codebase-fit audit, adversarial design review) of the 2026-07-13 modernization proposal.
**Compatibility:** Release A is **inert on the OpenAI-wire and `generate_json`-return surfaces, measured post-Phase-0** (Amendment 1 scopes this precisely; QW-1/QW-3 change prompt text as deliberate bug fixes, and new error categories / an additive `AgentResponse.usage` key are host-visible). Release B introduces **one deliberate load-time edge** (reasoning-model configs without explicit effort **hard-fail** per D-1 ruling; escape hatch `strict_reasoning_config=False`) plus additive config fields. See [Section 13: Migration Notes](#13-migration-notes).
**Baseline:** Validation performed against `main` @ `16832a2`; work branches `feature/v2.5-llm-modern-models` (Release A), `feature/v2.6-reasoning-config` (Release B).
**Design rulings (this spec, from validation):** (1) The framework **never mutates a payload it didn't validate** — no silent parameter injection; explicit config + loud load-time validation instead. (2) Model-name knowledge is **payload-advisory** — it never alters outbound kwargs (pinned by test); at load time its severity is per-rule (VL-1 rule 1 hard-fails per D-1, rule 5 errors, rules 2–4 warn-once) — OpenAI publishes no capability API and effort value-sets are per-model. (3) Cache-aware prompt reordering is **out of scope** (below the 1024-token cache floor; Jinja per-turn rendering defeats prefix stability; conflicts with documented prompt-order contracts). (4) Responses API (pro mode, `reasoning.context`, effort `max`) is **deferred** to a future deep-lane spec.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Framework Invariants (v2.5/v2.6 additions)](#2-framework-invariants-v25v26-additions)
3. [Scope & Goals](#3-scope--goals)
4. [Issue Index](#4-issue-index)
5. [Quick-Win Items (QW)](#5-quick-win-items-qw)
6. [Release A — Wire Compatibility & Observability](#6-release-a--wire-compatibility--observability)
7. [Release B — Reasoning Configuration & Engine Plumbing](#7-release-b--reasoning-configuration--engine-plumbing)
8. [Open Decisions](#8-open-decisions)
9. [Documentation Items](#9-documentation-items)
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

The framework's LLM layer (v2.4.0) is wired for the gpt-4o/4.1 generation: it hard-sends the
deprecated `max_tokens` wire parameter (rejected by every reasoning model), has no way to express
`reasoning_effort` (whose *omission* on gpt-5.5/5.6 silently buys `medium` reasoning — expensive
and incompatible with the 10s/1024-token real-time envelope), miscategorizes 4xx parameter
rejections as `server` errors, and cannot attribute cost. The production host currently runs
**gpt-4.1** — a sunset-track model (Azure EOL 2026-10-14) priced *above* every modern replacement
tier at or below gpt-5.6-luna; migration is a 40–90% cost **reduction**, not a spend increase.

This spec makes any OpenAI Chat Completions model a valid per-agent choice — current, legacy, and
future — with the cheap configuration as the well-lit path and every expensive configuration
explicit, validated at load time, and observable per call.

### Headline Numbers

| Category | Quick-Win | Release A (wire/observability) | Release B (reasoning/plumbing) | Doc | Total |
|----------|-----------|-------------------------------|--------------------------------|-----|-------|
| Items | 3 | 3 | 5 | 4 | 15 |

### Impact Summary

- **3 quick wins (QW-1..3):** a shipped schema (`ui_control.json`) violates JSON-mode's
  "must contain the word *json*" precondition (400 on every call for prompts that don't
  incidentally contain it); the default model string is hardcoded in two places; a latent
  prompt-assembly bug emits a blank joined section whenever `user_context` is set.
- **Release A (WC-1, OB-1, OB-2) — inert wire-compat + observability:** send
  `max_completion_tokens` on the wire (Python surface unchanged); split `misconfig` (4xx) out of
  the misleading `server` category and add `truncated` (starved/length-stopped output currently
  masquerades as `malformed`); return per-call usage + error category via a new result path that
  fixes the documented `last_error_category` shared-client race instead of cloning it.
- **Release B (RC-1..3, VL-1, EN-1) — explicit reasoning config:** per-agent `reasoning_effort`
  and a `model_params` passthrough dict (validated knowns + framework-ignorant rest); per-agent
  timeout/token budgets; load-time cross-validation at registration (effort × timeout × budget ×
  capability heuristics — **advisory table, never authoritative**); engine exposes
  timeout/retries/token-cap/`base_url` and **persists them across `update_api_key`** (today a key
  rotation would silently reset them to module defaults).
- **Explicitly rejected by validation:** silent injection of `reasoning_effort="none"` (value
  sets are per-model: original gpt-5 family takes `minimal`, o-series floors at `low`,
  `gpt-5-chat/-search/-codex/-pro` variants reject or restrict the parameter — blind injection
  converts working configs into silent 400-loops); authoritative prefix tables (refuted in both
  directions); cache-aware prompt reordering (zero measurable savings below the 1024-token cache
  floor; behavioral risk to every vault agent with no eval harness).

### Guiding Principles

1. **Never mutate the payload** — the framework sends what the operator configured, validates it
   loudly at load time, and categorizes rejections distinguishably. It does not guess on the wire.
2. **Cheap by default, expensive by declaration** — no configuration path silently increases
   latency or cost; every reasoning opt-in is explicit, per-agent, and cross-validated.
3. **Inert first** — Release A must produce zero behavior change for any working config before
   Release B's deliberate edges ship.
4. **Preserve the never-raise contract** — `generate_json` still returns dict-or-`None` into the
   turn; the taxonomy gets richer, the contract does not change shape.
5. **Sibling-safe** — new kwargs are passed only-when-configured so the simulator's
   `MockLLMClient` and in-repo strict-signature fakes keep working unmodified.

---

## 2. Framework Invariants (v2.5/v2.6 additions)

These extend INV-1 … INV-14 (+ INV-8′). Each must hold post-release; new entries land in
`docs/CONTRACTS.yaml` **in the same change** as their implementation (G1 gate; `debt_baseline: 0`
forbids `to_verify` stubs).

| ID | Invariant | Current Status |
|----|-----------|---------------|
| **INV-15** | The LLM wrapper sends **only operator-configured parameters** (plus the fixed wire essentials: model, messages, response_format, token cap, timeout). It never injects, rewrites, or omits a configured parameter based on model-name guessing. | New (Release B; enforced by RC-1/RC-2 design + test pinning the outbound kwargs) |
| **INV-16** | A parameter or model rejection (HTTP 4xx other than 401/429) is surfaced as **`misconfig`**, and a length-stopped/starved response as **`truncated`** — both distinguishable from `server`, `malformed`, and each other. | **Resolved** (OB-1 — v2.5; registered in CONTRACTS.yaml) |
| **INV-17** | Per-call telemetry (usage, error category, finish reason) is attributed to **the call that produced it**, immune to interleaving under `asyncio.gather` on the shared client. (`last_error_category` remains as a deprecated best-effort mirror.) | **Resolved** (OB-2 — v2.5; `LLMResult` path; registered in CONTRACTS.yaml) |
| **INV-18** | Engine-level LLM configuration (timeout, retries, token cap, `base_url`) **survives `update_api_key`**; key rotation never resets the client to module defaults. | Violated (`core/engine.py:195` rebuilds `LLMClient(api_key=...)` bare) — Release B / EN-1 |
| **INV-19** | Every agent config naming a model that **matches the reasoning heuristic** has an **explicit** `reasoning_effort`; a violation **hard-fails registration** (warns instead when `strict_reasoning_config=False`) — never silence. | New (Release B / VL-1; predicate is the testable heuristic match, per Amendment 1) |

Post-release, INV-1 … INV-19 (+ INV-8′) must all hold. A regression violating any invariant
blocks the release.

---

## 3. Scope & Goals

**In scope:** `core/llm.py`, `core/agent.py` (AgentConfig + default constant), `core/engine.py`
(ctor, `register_agent`/`replace_agents` validation hook, `update_api_key` persistence),
`core/models.py` (additive `AgentResponse.usage`),
`library/dynamic.py` (model_config parsing + pass-through + QW-3),
`library/schemas/ui_control.json`, `pyproject.toml` (SDK floor), `tests/`, `docs/CONTRACTS.yaml`,
affected docs (§9).

**Out of scope (deferred / explicitly not done here):**
- **Responses API** — `reasoning.mode: "pro"`, `reasoning.context`, explicit cache breakpoints,
  and `reasoning_effort: "max"` (unverified on Chat Completions; docs demonstrate it only via
  Responses). Future "deep lane" spec.
- **Cache-aware prompt reordering** — dropped per validation (prompts sit below the 1024-token
  cache floor; Jinja per-turn rendering makes prefixes volatile at token 0; conflicts with
  `test_prompt_includes_core_sections`, prompt_engineering_guide §ordering, and the PLAYBOOK
  `instructions_append` recency contract). Revisit only with a golden-replay eval harness.
- **Structured Outputs (`json_schema` strict)** — separable follow-up; would obsolete QW-1's
  precondition entirely.
- **Cost ceiling / kill-switch** — OB-2's telemetry is the prerequisite; the limiter is its own
  follow-up spec item (telemetry without a limiter is acknowledged as incomplete). The
  `usage_by_agent` aggregate on the merged `process_turn` response defers with it.
- **`on_llm_usage` callback hook** — deferred per D-3 ruling; `core/callbacks.py` untouched.
- **Azure OpenAI** (`AsyncAzureOpenAI`) and a multi-provider abstraction.
- **Model allowlist** (`allowed_models`) — see OPEN DECISION D-4.

**Non-goals:** No change to the phase model, blackboard, trigger system, prompt assembly order,
or the dict-or-`None` shape of `generate_json`. No default-model *value* change for existing
agents in this spec (QW-2 centralizes the constant; changing which model it names is a separate,
eval-gated decision).

---

## 4. Issue Index

Severity/phase → item ID → one-line. Full detail in the referenced sections.

### QUICK WIN (ship first, standalone)
- **QW-1** — `ui_control.json` instruction lacks the word "JSON"; json_object mode 400s. (§5.1)
- **QW-2** — Default model `"gpt-4o-mini"` hardcoded in two places → one framework constant. (§5.2)
- **QW-3** — `user_context` trailing `"\n\n"` yields a blank joined prompt section. (§5.3)

### RELEASE A — wire compatibility & observability (inert)
- **WC-1** — Wire kwarg `max_tokens` → `max_completion_tokens` (Python surface unchanged); SDK floor bump; legacy-wire opt-out. (§6.1)
- **OB-1** — Error taxonomy: 4xx → `misconfig`; `finish_reason=length` → `truncated`. (§6.2)
- **OB-2** — Per-call result path: usage + category attribution without the shared-client race; first-class `AgentResponse.usage`. (§6.3)

### RELEASE B — reasoning configuration & engine plumbing
- **RC-1** — Per-agent `reasoning_effort` in `model_config`, passed only-when-configured. (§7.1)
- **RC-2** — `model_params` passthrough dict (framework-ignorant, wire-shaped, documented). (§7.2)
- **RC-3** — Per-agent `timeout` / `max_tokens` plumbed from `model_config` through `generate_json`. (§7.3)
- **VL-1** — Load-time cross-validation at registration (capability heuristics advisory-only; effort × timeout × budget; temperature-on-reasoning trap). (§7.4)
- **EN-1** — Engine exposes timeout/retries/token-cap/`base_url`; config persists across `update_api_key`. (§7.5)

### DOCUMENTATION
- **DOC-7** — README + PLAYBOOK + technical_spec config tables & quoted code refreshed per item. (§9.1)
- **DOC-8** — CONTRACTS.yaml entries INV-15..19 + rule tests (same-change, G1). (§9.2)
- **DOC-9** — prompt_engineering_guide.md:45 corrects the false "separate user/assistant messages" transcript claim (pre-existing doc bug). (§9.3)
- **DOC-10** — Version bumps + CHANGELOG `[2.5.0]` / `[2.6.0]` sections. (§9.4)

---

## 5. Quick-Win Items (QW)

### 5.1 QW-1 — `ui_control.json` JSON-mode precondition
**Problem:** OpenAI JSON mode (`response_format={"type":"json_object"}`, hard-sent at
`core/llm.py:116`) requires the literal word "json" somewhere in the messages, else the API
returns 400. Every shipped schema instruction contains it **except**
`library/schemas/ui_control.json` ("IMPORTANT: You are a UI Controller… OUTPUT FORMAT: {…}" — no
"JSON"). Any `ui_control` agent whose authored prompt doesn't incidentally contain the word fails
every call.
**Fix:** Reword the instruction to name JSON explicitly (e.g. "OUTPUT FORMAT (a single JSON
object):"). No mapping change; A-1 gating unaffected (`root_key` present → early return,
`library/dynamic.py:218-219`).
**Tests:** New drift-lock in `tests/test_schemas.py`: every shipped schema's `instruction`
contains `"json"` case-insensitively. (Fails today on ui_control — test-first.)
**Acceptance:** Drift-lock green; existing schema tests green.

### 5.2 QW-2 — Single default-model constant
**Problem:** `"gpt-4o-mini"` is hardcoded at `core/agent.py:23` (AgentConfig default) and
`library/dynamic.py:119` (config-parse fallback). Two sites can drift.
**Fix:** `DEFAULT_MODEL = "gpt-4o-mini"` in `core/agent.py` (dynamic.py already imports from
`..core.agent` — no new import edge); both sites reference it; export from package `__init__.py`
for hosts. **Value unchanged** in this spec (README:525/895 + PLAYBOOK:1568/2949 stay true).
**Tests:** Assert both default paths resolve to the constant.
**Acceptance:** Grep of non-test `core/` + `library/` source for the literal outside the
constant definition: zero hits (docs/tests legitimately retain it).

### 5.3 QW-3 — `user_context` blank-section bug (latent, pre-existing)
**Problem:** `library/dynamic.py:388` builds `user_context_section = f"{context.user_context}\n\n"`,
then `parts` are joined with `"\n\n"` (`:404`) — a set `user_context` produces a blank joined
section, exactly what `test_prompt_has_no_leading_whitespace`'s blank-part sweep
(`tests/test_dynamic_agent.py:325-329`) exists to catch; it passes today only because the fixture
omits `user_context`.
**Fix:** Drop the trailing `"\n\n"` from the section (join supplies separation).
**Tests:** Extend the D1 blank-part test with a `user_context`-set case (test-first: fails on
baseline).
**Acceptance:** D1 sweep green with and without `user_context`.

---

## 6. Release A — Wire Compatibility & Observability

> **Release A contract: inert.** Every working v2.4.0 config produces byte-identical requests
> except the token-cap kwarg name, and identical `generate_json` results. Ships alone so any wire
> regression is unambiguously attributable.

### 6.1 WC-1 — `max_completion_tokens` on the wire
**Problem:** `core/llm.py:117` sends `max_tokens`, which every reasoning model (gpt-5 family,
o-series, gpt-5.6) rejects with 400. OpenAI designates `max_completion_tokens` as the successor,
accepted by current non-reasoning models too (empirically; not contractually guaranteed —
validation Claim 1 PARTIALLY-TRUE).
**Fix (three coupled parts):**
1. **Wire kwarg only:** `create(**{..., "max_completion_tokens": effective_max_tokens})`. The
   **Python parameter name `max_tokens` does not change** anywhere (`generate_json` signature,
   `LLMClient` ctor, config keys) — renaming it would break hosts (`docs/PLAYBOOK.md:3059-3061`),
   the pinned signature (`docs/technical_spec_agents.md:173`), and the simulator's
   `MockLLMClient` mirror.
2. **SDK floor:** `pyproject.toml` `openai>=1.0.0` → `openai>=1.60.0` (covers
   `max_completion_tokens` ~1.45+ and `reasoning_effort` ~1.59+ for Release B). On an old SDK the
   TypeError is swallowed into `category=unknown` and every call dies silently — the floor bump
   is not optional.
3. **Legacy-wire opt-out:** `LLMClient(wire_max_tokens_param="max_completion_tokens")` ctor knob
   (values: `"max_completion_tokens"` default | `"max_tokens"`) for old OpenAI-compatible proxies
   that predate the new kwarg (relevant once EN-1 opens `base_url`). Documented, not model-sniffed.
**Tests:** Update the two wire-kwarg pins (`tests/test_llm.py:233`, `:249`) to the new kwarg —
neither is gate-registered (CONTRACTS names only `test_typed_errors_return_none_and_log_category`),
but they land in the same commit; add an opt-out-mode test asserting the legacy kwarg.
**Acceptance:** Wire pin tests green both modes; suite green; no public-surface diff (verified
against `docs/technical_spec_agents.md:173` signature).

### 6.2 OB-1 — Error taxonomy: `misconfig` + `truncated`
**Problem:** (a) `APIStatusError` → `server` unconditionally (`core/llm.py:135-141`) — a 400
"unsupported parameter" reads as an outage and PLAYBOOK's category-keyed operational guidance
(`:3210, :3341, :3360`) pages the wrong direction. (b) `finish_reason` is never read; a
length-stopped response (`content=None` + `finish_reason="length"` — the exact signature of
reasoning-token starvation under a small cap) lands in `malformed` (`core/llm.py:156-171`).
**Fix:** In the `APIStatusError` handler: `status = getattr(e, "status_code", None)`;
`isinstance(status, int) and status < 500` → `misconfig`; **anything else (incl. missing/non-int
status) → `server`** — never `None < 500` inside the handler, which would raise into the turn
(401/429 never reach this handler — they raise their own subclasses). Before the
null-content/parse branch: `finish_reason = getattr(choice, "finish_reason", None)`; `"length"` →
category `truncated`, log includes the configured cap. **Check order: truncated → null-content →
parse.** Empty-choices stays `malformed` (no choice to read a finish_reason from). **Deliberate
inertness deviation (stated):** a length-stopped response whose partial content happens to parse
flips from success to `None`/`truncated` — a truncated JSON object is not a trustworthy whisper;
recorded as the one intentional `generate_json`-result change in Release A.
**Tests:** Extend the gate-registered `test_typed_errors_return_none_and_log_category`
(INV-10 node — extend, never shrink) with parametrized 400/422 → `misconfig` and 503 → `server`
cases; new truncated tests via a `_Choice` fake carrying `finish_reason="length"` with `content=None`
and with partial content. Existing 5xx fakes (`tests/test_llm.py:59,147,165`) stay green.
**Acceptance:** INV-16 holds; category docs updated in lockstep (§9.1); never-raise preserved.

### 6.3 OB-2 — Per-call result path + usage telemetry
**Problem:** `generate_json` returns only the parsed dict (`core/llm.py:174`); the SDK response
(with `.usage`, incl. reasoning/cached token details) is discarded, so cost is unobservable.
The obvious shortcut — a `client.last_usage` attribute — clones the **documented**
`last_error_category` race (agents run concurrently on one shared client via `asyncio.gather`,
`core/engine.py:574-582`; PLAYBOOK:3201): racy cost numbers are worse than mislabeled logs.
`debug_info` alone is insufficient for hosts: it is `exclude=True` (`core/models.py:150`) and
never survives pydantic serialization.
**Fix (design):**
1. New internal per-call result: `LLMResult` (frozen dataclass: `parsed: dict|None`,
   `error_category: str|None`, `usage: dict[str,int]|None` (plain ints:
   `prompt_tokens`, `completion_tokens`, `reasoning_tokens`, `cached_tokens`),
   `finish_reason: str|None`). New method `LLMClient.generate(...) -> LLMResult` holds the
   entire current body; `generate_json` becomes a thin delegate returning `result.parsed` —
   **public contract dict-or-`None` unchanged**.
2. `last_error_category` still set (deprecated best-effort mirror; docstring updated to say so).
3. **(Amended per review B-1)** `DynamicAgent` **duck-types** the client — `gen =
   getattr(self.llm, "generate", None)`; uses the `LLMResult` path when present, else falls back
   to `generate_json` (usage/category enrichment simply absent). Mirrors the `_close_llm_client`
   duck-typing house pattern; keeps every `generate_json`-only fake (`tests/test_schemas.py:75`,
   `tests/test_dynamic_agent.py:41`) and the simulator's `MockLLMClient` working unmodified.
   Regression test: a `generate_json`-only fake driven through `evaluate` still parses insights.
   When enriched, plain-int usage goes into `debug_info["usage"]` (tracer-safe: passthrough at
   `utils/tracing.py:83-84`; debugger reads only `.prompt_messages`/`.llm_output`) **and** into a
   new first-class additive field `AgentResponse.usage: Optional[Dict[str, int]] = None`.
   Usage extraction is fake-safe (`getattr(response, "usage", None)`, outside the parse-try) and
   flattens nested SDK details: `reasoning_tokens` ← `completion_tokens_details.reasoning_tokens`,
   `cached_tokens` ← `prompt_tokens_details.cached_tokens`; absent details → key omitted.
   `generate()` writes `self.last_error_category = result.error_category` **exactly once** before
   returning (None on success), so both entry points keep the deprecated mirror live.
   **Host billing channel (stated):** per-agent usage reaches hosts via `on_agent_finish` /
   the tracer / `AgentResponse.usage`; `_merge_responses` does NOT propagate usage into the
   aggregated `process_turn` return — a `usage_by_agent` aggregate is deferred to the
   cost-ceiling follow-up.
4. Callbacks: **no signature change** to existing hooks (mismatches are silently swallowed by the
   try/except at `core/agent.py:126-130`; INV-1/INV-7 pin current shapes). The `on_llm_usage`
   hook is **deferred per D-3 ruling** (no callbacks.py change in this spec).
**Tests (amended per review):** `generate()` returns correct `LLMResult` for
success/each-failure/truncated; **two named concurrency tests**: (i) *baseline mirror-race
repro* (test-first, fails on baseline) — two concurrent `generate_json` calls with
`asyncio.Event`-gated fake `create`s forcing A-fails-then-B-fails ordering, read
`last_error_category` after `gather`, observe it reports only B — pinning the INV-17 violation
the deprecated mirror retains; (ii) *per-call attribution* — same Event-gated harness against
`generate()`, asserting each returned `LLMResult.error_category` individually;
`AgentResponse.usage` serializes; duck-type fallback test (generate_json-only fake still yields
insights); simulator-shape guard: `debug_info` keys `prompt_messages`/`model`/`llm_output`
unchanged.
**Acceptance:** INV-17 holds; usage visible per agent in debug_info + `AgentResponse.usage`;
`generate_json` callers observe zero change.

---

## 7. Release B — Reasoning Configuration & Engine Plumbing

> **Release B contract: additive config, one deliberate load-time edge (VL-1, per D-1), zero
> wire change for agents that don't opt in.** Coordinated with xubb_server (README/CHANGELOG
> migration note).

### 7.1 RC-1 — Per-agent `reasoning_effort`
**Problem:** No way to express reasoning effort. Omission ≠ cheap: gpt-5.5/5.6 default to
`medium` (validated); gpt-5.1 defaults to `none`; value sets are per-model (`minimal` on original
gpt-5 family; `low` floor on o-series; rejected outright on `-chat`/`-search` variants and
o1-mini). **Validation REJECTED silent injection** — the framework cannot know the right value.
**Fix (amended per review):** **`AgentConfig` is the canonical storage** for all four Release B
fields (`reasoning_effort`, `timeout`, `max_tokens`, `model_params`), defaulted `None`/`{}`;
`DynamicAgent.__init__` parses `model_config.*` (house pattern `model_conf.get(...)`,
`library/dynamic.py:117-146`) **into the `AgentConfig` ctor** (like `model` today — no duplicate
instance attributes), so VL-1 has one generic read surface. `generate_json`/`generate` gain an
explicit `reasoning_effort: Optional[str] = None` parameter; `DynamicAgent` **omits** the kwarg
entirely when unconfigured — never passes `reasoning_effort=None` (protects strict-signature
fakes: `tests/test_schemas.py:75` `_FakeLLM`, simulator `MockLLMClient`). No value validation
against a model table (INV-15: operator-owned; a wrong value surfaces as a loud `misconfig` via
OB-1). **Custom-subclass contract (stated):** on a custom `BaseAgent` the config fields are a
*declaration consumed by validation*; the subclass owns forwarding
`self.config.reasoning_effort` (etc.) into its own `generate_json` calls — documented with a
PLAYBOOK snippet next to the direct-call pattern (PLAYBOOK:3007), closing the false-green trap
where VL-1 rule 1 passes but the wire never carries the effort.
**Tests:** Configured effort appears in outbound kwargs; unconfigured → kwarg **absent** (INV-15
pin); `_FakeLLM`-style strict mock unaffected when unconfigured.
**Acceptance:** INV-15 holds; effort flows config → wire verbatim; README/PLAYBOOK config tables
gain the row (same change, §9.1).

### 7.2 RC-2 — `model_params` passthrough
**Problem:** Every future API parameter (verbosity, future knobs) currently requires a framework
release; but teaching the framework each parameter's semantics is a maintenance treadmill.
**Fix (amended per review B-2):** `model_config.model_params: dict = {}` merged into
`call_kwargs` with **framework-owned keys winning defensively at the call site** (an unvalidated
path can never mutate wire essentials), and collisions **rejected in `DynamicAgent.__init__`**
(pure-config check — reachable even for direct-constructed agents that never pass engine
registration; registration re-checks for custom agents, VL-1 rule 5). Framework-owned set:
`model`, `messages`, `response_format`, **both token-cap spellings** (`max_tokens` and
`max_completion_tokens`, independent of the WC-1 wire mode), `timeout`, `reasoning_effort`.
Non-dict `model_params` → warn and treat as absent (house coercion pattern,
`library/dynamic.py:82-98`). Documented explicitly as **Chat Completions wire shape, not
transport-portable** (the Responses migration note lives with it).
**Tests:** Passthrough lands on the wire verbatim; collision with a framework key →
`__init__`-time error (both token spellings covered); non-dict coerced-with-warning; empty
default → zero wire diff; defensive call-site merge pinned (framework key survives a sneaky
post-init mutation of the dict).
**Acceptance:** INV-15 holds (nothing injected, everything declared); docs updated.

### 7.3 RC-3 — Per-agent `timeout` / `max_tokens`
**Problem:** `generate_json` already accepts per-call `timeout`/`max_tokens`
(`core/llm.py:92-94`) but `DynamicAgent` never passes them (`library/dynamic.py:417`) — reasoning
agents can't get the bigger budgets they need (OpenAI guidance: reserve ~25k output tokens at
real effort; the 1024 default starves them by construction — this is the WC-1×RC-1 interaction
VL-1 warns about).
**Fix:** `model_config.timeout: float | None` and `model_config.max_tokens: int | None` parsed
alongside RC-1 and passed only-when-configured. **Naming ruling:** one name end-to-end —
config `max_tokens` → param `max_tokens` → wire `max_completion_tokens` (wire name is internal;
avoids the three-name sprawl the audit flagged).
**Tests:** Configured values reach `create()`; unconfigured → client defaults (existing
`test_constructor_configures_resilience_params` stays green); fakes unaffected.
**Acceptance:** A deep-lane agent can declare `{model, reasoning_effort, timeout: 30,
max_tokens: 25000}` and the wire reflects exactly that.

### 7.4 VL-1 — Load-time cross-validation (payload-advisory, load-time enforcing)
**Problem:** The failure modes of Release B are configuration failure modes: effort without
budget (starved → billed-but-empty), reasoning-named model without effort (silent `medium` — the
expensive trap), temperature in `model_params` on a reasoning model (400), effort on a
non-reasoning model (400). All currently surface only at runtime as silent `None`s.
**Fix (amended per review B-2/B-3):** Validation hook in
`AgentEngine.register_agent`/`replace_agents` for the budget/heuristic rules — **not**
`DynamicAgent.__init__`, which cannot see the client's actual budgets (`self.llm` is `None` until
registration, `core/agent.py:56` / `core/engine.py:107`); rule 3 reads the fallback budgets from
`self.llm_client.timeout`/`.max_tokens` when per-agent values are unset. One shared capability
heuristic (single **module-level** table, monkeypatch-friendly: name-pattern → likely-reasoning,
with deny-suffixes `-chat`, `-search`, `-codex`, `-pro` plus an exact-name denylist (`o1-mini`);
**payload-advisory: never alters outbound kwargs** — INV-15). Rules read `agent.config` via
`getattr(..., None)` so custom `BaseAgent` subclasses validate generically (absent fields skip
rules 3–5 trivially). Warn-once discipline keyed by agent id (E-6 pattern,
`core/engine.py:94-95`; entry discarded on `unregister_agent`; `replace_agents` does not re-warn
a same-id re-registration — same as E-6). Rules:
1. Model matches reasoning heuristic AND no `reasoning_effort` → **hard-fail (D-1 ruling)**:
   raise `AgentConfigurationError` (new, `ValueError` subclass in `core/engine.py`, exported from
   the package) whose message includes the copy-pasteable fix; **warns instead** when the engine
   was constructed with `strict_reasoning_config=False`.
2. `reasoning_effort` set AND model matches a deny-suffix / non-reasoning shape → warn.
3. `reasoning_effort` beyond `low` AND (`timeout` unset-or-≤10s OR `max_tokens` unset-or-<4096)
   → warn naming the starved-output/billed-timeout consequence. **Thresholds normative** (>10s,
   ≥4096), amendable.
4. `model_params` contains `temperature`/`top_p` AND reasoning heuristic matches → warn.
5. `model_params` collides with a framework-owned key → **error**; the check itself is owned by
   RC-2 and runs in `DynamicAgent.__init__` (pure-config check); registration re-checks for
   custom agents.
**Hard-fail mechanics (stated):** `register_agent` validates **before any mutation** — on failure
the registry and the agent's `llm` are untouched. `replace_agents` **validates ALL incoming
agents first** (collecting every violation into one error), then builds, then rebinds — a vault
reload with one bad config is all-or-nothing and the old registry keeps serving.
`strict_reasoning_config: bool = True` is an `AgentEngine.__init__` kwarg, stored on the engine,
read by the hook, and added to the pinned-signature doc update.
**Tests:** caplog-asserting per warn rule (house pattern `tests/test_dynamic_agent.py:495-507`);
warn-once verified; zero warnings for a clean fast-lane config; hard-fail path: register raises
`AgentConfigurationError`; `replace_agents` all-or-nothing leaves the old registry serving;
`strict_reasoning_config=False` downgrades rule 1 to a warning and the agent registers.
**Acceptance:** INV-19 holds under the D-1 ruling; the table is provably **payload-advisory**
(a test pins that outbound kwargs are identical with the table emptied).

### 7.5 EN-1 — Engine LLM-config exposure + rotation persistence
**Problem:** `AgentEngine.__init__` builds `LLMClient(api_key=api_key)` with module defaults
(`core/engine.py:70`) — hosts can't set timeout/retries/cap/base_url without reaching into
internals. **The trap:** `update_api_key` rebuilds the client the same bare way
(`core/engine.py:195`), so once knobs exist, every key rotation (documented host flow,
PLAYBOOK:3148/3287) silently resets them — a proxy host flips back to api.openai.com mid-session.
**Fix (amended per review B-4):** Engine ctor gains `llm_timeout`, `llm_max_retries`,
`llm_max_tokens`, `llm_base_url`, **`llm_wire_max_tokens_param`** (closing the gap where the
WC-1 knob's only intended audience — proxy hosts using `AgentEngine` — couldn't reach it), and
`strict_reasoning_config` (VL-1) — all defaulted kwargs, compat-safe (every construction site
uses kwargs). **Stored-config structure (stated):** the engine builds
`self._llm_config: Dict[str, Any]` in `__init__` from the knobs **only-when-set** (so `LLMClient`
defaults keep applying otherwise); `update_api_key` does
`LLMClient(api_key=api_key, **self._llm_config)` — **ctor config is authoritative on rotation**;
a hand-swapped `engine.llm_client` is not preserved across rotation (documented). `LLMClient`
gains `base_url` (passed to `AsyncOpenAI` when set) and the WC-1 `wire_max_tokens_param` knob
(ctor-validated: unknown value → `ValueError`). E-4 close-path unchanged (`_close_llm_client`
duck-types; `core/engine.py:202-235`); the `update_api_key` docstring keeps the E-4 precondition
wording (`test_update_api_key_documents_concurrency_precondition` greps for it).
**Tests:** Ctor knobs reach the client (extend `test_constructor_configures_resilience_params`,
`tests/test_llm.py:272-295`; the `LLMClient.__new__` test helper at `tests/test_llm.py:110-131`
gains the new attributes — or `generate()` reads them via `getattr`-with-default, whichever lands,
stated in the PR); **rotation-persistence repro (test-first):** construct with non-default config
**including `llm_wire_max_tokens_param`** → `update_api_key` → assert the new client carries the
same config (fails on baseline); E-4 suite stays green.
**Acceptance:** INV-18 holds; pinned signature at `docs/technical_spec_agents.md:167-171`
updated; new CONTRACTS entry (§9.2).

---

## 8. Decisions (ruled 2026-07-13)

**All four decisions RULED by owner 2026-07-13** (recorded here and in §17; changing them
post-approval is an Amendment):

- **D-1 — VL-1 rule 1 severity: warn or hard-fail?** Validation's adversarial lens argued
  **hard-fail at load** (a reasoning-model config without effort is underspecified in a way that
  breaks the 10s/1024 envelope; failing at deploy beats silent `medium` in production). The
  codebase lens noted warn matches the A-1/E-6 house pattern and avoids a breaking edge.
  **RULED (owner, 2026-07-13): hard-fail as proposed**, with the engine escape hatch
  (`strict_reasoning_config: bool = True`).
- **D-2 — Ship Release A and Release B as separate PyPI releases (2.5.0 / 2.6.0)?**
  **RULED (owner, 2026-07-13): yes** — A is inert and independently revertible; B carries the
  D-1 edge.
- **D-3 — Add additive `on_llm_usage` no-op callback hook in Release A?**
  **RULED (owner, 2026-07-13): defer as proposed** — `AgentResponse.usage` + debug_info cover
  hosts; add the hook when the cost-ceiling follow-up needs a push channel.
- **D-4 — `allowed_models` allowlist (engine-level, hard-fail at registration)?**
  **RULED (owner, 2026-07-13): defer to the cost-ceiling follow-up as proposed.**

---

## 9. Documentation Items

- **9.1 DOC-7** — Per-item, same-change: README config table (`README.md:512-529`) +
  `AgentConfig` signature (`:889-905`) gain `reasoning_effort`/`timeout`/`max_tokens`/
  `model_params` rows; PLAYBOOK config table (`:1568`), quoted `generate_json` code
  (`:3030-3034`, `:3059-3061`), category list + operational guidance (`:3090-3099`, `:3210`,
  `:3341`, `:3360` — the `misconfig` split is the point: 4xx stops paging as "server spike");
  `docs/technical_spec_agents.md:164-176` pinned signatures; `core/llm.py:70-72` category
  comment.
- **9.2 DOC-8** — `docs/CONTRACTS.yaml`: INV-15..19 entries naming their rule tests (G1;
  `debt_baseline: 0` — no `to_verify`). Extend, never shrink, the INV-10 node's named test.
- **9.3 DOC-9** — `docs/prompt_engineering_guide.md:45` states the transcript goes as "separate
  user/assistant messages"; it is one user message (`library/dynamic.py:410-413`). Pre-existing
  doc bug; fix in Release A (doc-only).
- **9.4 DOC-10** — Version `2.5.0` (Release A) / `2.6.0` (Release B) across `pyproject.toml`,
  `__init__.py`, README header; CHANGELOG sections enumerating items; Release B section carries
  the Migration Note (§13).

---

## 10. Implementation Plan (Phased)

Each phase is a set of **atomic commits**; a phase must be **green** (DoD met) before the next.
Commit convention: `v2.5/<ITEM-ID>: <summary>` / `v2.6/<ITEM-ID>: <summary>`.

| Phase | Theme | Items | Parallelizable? | Rationale |
|-------|-------|-------|-----------------|-----------|
| **0** | Quick wins | QW-1, QW-2, QW-3 | **All three independent** (fan-out candidates) | Standalone bug fixes; zero coupling to the rest; shippable even if A/B stall. |
| **A1** | Wire compat | WC-1 (+ SDK floor) | Serial (single file focal point) | The inert wire change lands alone and first within A. |
| **A2** | Observability | OB-1, then OB-2 | OB-1 ∥ QW-*; **OB-2 after WC-1 & OB-1** (same function body moves into `generate()`) | Taxonomy first (small), then the result-path refactor absorbs it. |
| **A3** | Release A close | DOC-7 (A-scope), DOC-8 (INV-16/17), DOC-9, DOC-10 (2.5.0) | Doc items parallel | Gate: inert-release checks (§15) → PR → PyPI 2.5.0 (per D-2). |
| **B1** | Config surface | RC-1, RC-2, RC-3 | RC-1/RC-3 tightly coupled (one parse site); RC-2 after RC-1 | The additive per-agent surface, passed only-when-configured. |
| **B2** | Validation + engine | VL-1, EN-1 | **Independent of each other** (fan-out candidates); both after B1 | VL-1 needs RC fields to validate; EN-1 needs WC-1's client knob. |
| **B3** | Release B close | DOC-7 (B-scope), DOC-8 (INV-15/18/19), DOC-10 (2.6.0) | Doc items parallel | Gate: xubb_server migration note + D-1 policy verified → PR → PyPI 2.6.0. |

Serial constraints (process §3.1 dependency-layer fan-out): WC-1 → OB-2 → RC-* → {VL-1, EN-1}.
Everything in Phase 0 and OB-1 is fan-out-safe from the start. Doc items are formally split
per release — **DOC-7A/8A/10A** land in phase A3 and **DOC-7B/8B/10B** in B3 — preserving the
one-item-one-phase bijection.

---

## 11. Definition of Done (per phase)

A phase is **Done** when **all** hold:

1. **Code:** every item in the phase implemented per its section.
2. **Tests:** each item has ≥1 regression test; test-first items (QW-1, QW-3, OB-2 race repro,
   EN-1 rotation repro) demonstrably failed pre-fix.
3. **Suite green:** `python -m pytest -q` — zero failures/errors, zero new warnings.
4. **Invariants:** INV-1…14 (+8′) not regressed; the phase's new INVs hold and are registered in
   CONTRACTS.yaml **in the same phase** (G1; no `to_verify`).
5. **Inertness check (Release A phases only):** a captured-kwargs diff over the existing test
   fixture set shows the only wire delta is the token-cap kwarg name.
6. **Docs in lockstep:** every contract touched has its doc/docstring updated in the same phase.
7. **CHANGELOG:** running, not end-loaded.
8. **Sibling check (B phases):** simulator `MockLLMClient` + `tests/test_schemas.py::_FakeLLM`
   pass unmodified for unconfigured agents (only-when-configured guarantee).
9. **Self-review:** diff reviewed for scope creep.

Release-level DoD: suite green; version consistent; spec status advanced; PR with full test
output; `/trace-check` passes Appendix A.

---

## 12. Testing Strategy

- **Test-first** for every contract change with a constructible repro: QW-1 (drift-lock), QW-3
  (blank-section), OB-2 (concurrency attribution repro), EN-1 (rotation persistence repro).
- **Extend, never shrink, gate-registered tests:** OB-1 parametrizes into the INV-10 node
  (`test_typed_errors_return_none_and_log_category`).
- **Wire pinning:** a captured-kwargs assertion layer (existing style, `tests/test_llm.py:233`)
  pins: new token kwarg both modes (WC-1), effort present-iff-configured (RC-1/INV-15),
  passthrough verbatim (RC-2), per-agent budgets (RC-3), advisory-table-changes-nothing (VL-1).
- **Never-raise envelope:** every new failure path (misconfig, truncated) proves dict-or-`None`,
  no exception into the turn.
- **Sibling/fake safety:** explicit test that an unconfigured agent drives a strict-signature
  fake (`_FakeLLM` shape) successfully.
- **Eval gate (process, not pytest):** any future change to the *value* of `DEFAULT_MODEL` or to
  a shipped schema's effort guidance requires a simulator golden-replay comparison — recorded
  here as the standing rule; out of scope to build in this spec.
- **Target count:** TODO at implementation (~25–35 new tests: QW ×4, WC-1 ×3, OB-1 ×6, OB-2 ×6,
  RC ×6, VL-1 ×6, EN-1 ×4).

---

## 13. Migration Notes

**Release A (2.5.0) — no code change required; observable-surface changes below.**
- Wire kwarg rename is invisible to hosts (Python surface unchanged); old OpenAI-compatible
  proxies can pin `wire_max_tokens_param="max_tokens"` (direct `LLMClient` constructors only
  until 2.6.0 exposes it through the engine).
- **SDK floor:** hosts must have `openai>=1.60.0` (pip resolves automatically on upgrade).
- New error categories `misconfig`/`truncated` appear in logs and `last_error_category`; hosts
  keying alerts on `server` should re-route 4xx handling (this is a fix: those were
  misclassified). A length-stopped-but-parseable response now returns `None` (`truncated`)
  instead of a suspect partial parse — deliberate, see §6.2.
- `AgentResponse.usage` is additive-defaulted (`None`); serialized payloads gain exactly one key
  (strict-schema hosts take note).
- **Prompt-visible bug fixes (Phase 0):** the `ui_control` schema instruction now names JSON, and
  a set `user_context` no longer injects a blank prompt section — prompts change for affected
  agents; both are corrections.

**Release B (2.6.0) — one deliberate edge + additive config.**
- **Per D-1 ruling (hard-fail):** an agent config naming a reasoning-heuristic model without
  `reasoning_effort` fails at registration (`AgentConfigurationError`) with a copy-pasteable fix.
  Hosts audit vault configs before upgrading (one field per affected agent). Escape hatch:
  `strict_reasoning_config=False`.
- New optional `model_config` keys: `reasoning_effort`, `timeout`, `max_tokens`, `model_params`.
  Absent keys → wire behavior identical to 2.5.0.
- `update_api_key` now **preserves** engine LLM config — hosts that (buggily) relied on rotation
  resetting timeouts must set them explicitly.
- **Cost guidance for the host (xubb_server):** production baseline gpt-4.1 is sunset-track and
  premium-priced; recommended lanes — **every heuristic-matching model carries an explicit
  effort** (D-1 makes omission a load failure): fast: gpt-5.4-nano + `"none"` / gpt-5-nano +
  `"minimal"`; standard: gpt-5.4-mini or gpt-5.6-luna + `"none"`; deep (opt-in):
  gpt-5.6-terra/sol + `low`–`high` + `timeout≥30` + `max_tokens≥25000`. Effort **value validity
  is per-model** (e.g. original gpt-5 family: `minimal`, not `none`) — the framework passes
  values verbatim; a wrong pair surfaces as `misconfig`.

---

## 14. Rollback Plan

- **Granularity:** one item (or tight cluster) per atomic commit tagged `v2.5/<ID>` / `v2.6/<ID>`;
  any item reverts via `git revert` without disturbing others.
- **Release A rollback:** WC-1 reverts as its **atomic commit** (wire line + knob + kwarg-pin
  tests together — a lone wire-line revert leaves the pins red); after 2.6.0 ships, revert B
  first per the D-2 firewall. OB-1/OB-2 are internal (`generate()` delegate) — reverting restores
  the v2.4.0 body; `AgentResponse.usage` is additive-defaulted, no serialization migration.
- **Release B rollback:** all config fields are additive-defaulted; reverting RC/VL/EN restores
  2.5.0 behavior with configs still loading (unknown keys were already tolerated by
  `model_conf.get`). D-1 hard-fail reverts with VL-1.
- **Staged-release firewall (D-2):** 2.5.0 on PyPI is a stable fallback for hosts if 2.6.0 needs
  a pull; `main` stays shippable throughout (branch-per-release, PR gates).
- **Forward-fix preference** post-merge, per house rule.

---

## 15. Release Gates & Success Metrics

**Gates — Release A (2.5.0):**
1. Suite green, zero warnings; SDK floor bumped and CI green against it.
2. **Inertness proof (scope amended):** captured-kwargs diff over the fixture set, **baselined
   post-Phase-0**, = token-kwarg name only; plus an `AgentResponse`-serialization delta assertion
   (exactly one new key: `usage`). The truncated-beats-parseable deviation (§6.2) is the one
   allowed `generate_json`-result change.
3. INV-16/INV-17 CONTRACTS entries + named tests green; INV-10 node extended and green.
4. Version/CHANGELOG/docs consistent; `/trace-check` passes.

**Gates — Release B (2.6.0):**
1. Suite green; sibling check (simulator + strict fakes) green unmodified.
2. INV-15/18/19 CONTRACTS entries + named tests green; VL-1 advisory-only proof green.
3. EN-1 rotation-persistence repro green; E-4 suite green.
4. D-1 policy implemented as signed off; migration note published; xubb_server config audit done.

**Success metrics:**
- Any current OpenAI chat model is usable via config alone; a **new** model release requires
  zero framework changes (INV-15 + RC-2).
- Zero silent parameter injections (kwargs-pin tests).
- 4xx never reads as an outage; starvation never reads as bad JSON (INV-16).
- Cost attributable per agent per call (INV-17); the accidental-`medium` trap is unreachable
  without a load-time signal (INV-19).

---

## 16. Spec Amendment Procedure

Per Tier-1 process: pause the affected item → propose here + to owner with rationale → owner
sign-off → append "Amendment N" (date, reason) → resume. No silent scope changes; deferrals only
via amendment. Decisions (§8) resolved at sign-off count as the initial rulings, recorded in
the sign-off table.

### Amendment 1 — three-lens spec review findings applied (2026-07-13)

**Reason:** The owner approved the spec while a three-reviewer validation (citation accuracy /
consistency+process / implementability) was in flight, with findings directed to land via this
procedure. Citation review: 60 accurate, 2 imprecise ranges (fixed inline), 0 inaccurate.
The two design reviews converged on **4 blockers**, all resolved by inline amendment above;
resolutions were chosen to *preserve* the owner's ruled properties (Release A inertness, D-1
hard-fail) — none alters a ruling. **Sign-off:** applied under the standing approval; the owner
may veto any resolution here, which reverts to the pre-amendment text and pauses the item.

| # | Finding (reviewer) | Resolution (section amended) |
|---|---|---|
| A1-1 | **BLOCKER:** `DynamicAgent` switching to `generate()` breaks every `generate_json`-only fake incl. the simulator — falsifying Release A inertness | Duck-type `getattr(self.llm, "generate", None)` with `generate_json` fallback (house `_close_llm_client` pattern) + regression test (§6.3) |
| A1-2 | **BLOCKER:** VL-1 "advisory/warnings-only" text contradicted the D-1 hard-fail ruling; `model_params` collision check unreachable for direct-constructed agents | VL-1 reworded payload-advisory vs load-time-enforcing; collision check owned by RC-2 in `DynamicAgent.__init__` + defensive call-site merge + both token-cap spellings framework-owned (§7.2, §7.4, front-matter ruling 2) |
| A1-3 | **BLOCKER:** hard-fail mechanics unstated (exception type, registry atomicity, `strict_reasoning_config` owner) | `AgentConfigurationError` (ValueError subclass, exported); validate-before-mutate in `register_agent`; validate-all-then-rebind (all-or-nothing) in `replace_agents`; flag = engine ctor kwarg (§7.4, §7.5) |
| A1-4 | **BLOCKER:** `wire_max_tokens_param` unreachable via engine and missing from the rotation-persisted set — recreating the INV-18 bug class | `llm_wire_max_tokens_param` added to engine ctor + `self._llm_config` persisted set + rotation repro extended (§7.5) |
| A1-5 | SHOULD-FIX cluster (OB-1/OB-2): `None < 500` TypeError hazard; truncated-beats-parseable inertness deviation; `last_error_category` single write site; fake-safe usage extraction + flattening map; billing channel; named concurrency tests | All stated inline (§6.2, §6.3, §13, §15) |
| A1-6 | SHOULD-FIX cluster (RC/VL/EN): `AgentConfig` canonical for all four fields; custom-subclass declarative contract; warn-once keying/lifecycle; normative rule-3 thresholds; `_llm_config` structure + hand-swap semantics; wire-knob ctor validation | All stated inline (§7.1–§7.5) |
| A1-7 | Consistency cluster: inertness claim rescoped (wire + `generate_json`, post-Phase-0) with `AgentResponse` delta gate; D-1/D-3 language propagated (stale "OPEN/proposed" removed; callbacks.py out of scope); §13 lane guidance carries explicit efforts; WC-1 atomic-commit rollback; DOC-7/8/10 split A/B; Appendix A header relaxed | (front-matter, §3, §6.3, §8, §10, §13, §14, §15, Appendix A) |
| A1-8 | NITs: QW-1 drift-lock globs the schemas dir (implemented, commit `v2.5/QW-1` #2); QW-2 grep acceptance scoped to non-test source (implemented as specced); `o1-mini` = exact-name denylist; two citation ranges corrected (`technical_spec_agents.md:164-176`, `README.md:512-529`) | (§5.1 impl, §5.2, §7.4, §9.1) |

**Phase 0 status at amendment time:** QW-1/QW-2/QW-3 implemented test-first and committed
(`v2.5/QW-*`); full suite **287 green, zero warnings**.

---

## 17. Sign-off

| Role | Name | Decision | Date |
|------|------|----------|------|
| Owner | @genriq | D-1: hard-fail · D-2: two releases · D-3: defer · D-4: defer (rulings recorded; spec approval pending review) | 2026-07-13 |
| Owner | @genriq | ☑ **APPROVED** → Phase 0 begun | 2026-07-13 |
| Author | Claude (validation + spec) | Drafted | 2026-07-13 |

**This spec is DRAFT. No code will be written until the owner signs off (Tier-1 gate).** On
approval, implementation proceeds Phase 0 → A3 → B3, each phase green before the next, ending in
two PRs / releases (per D-2).

---

## Appendix A: Full Finding → Item Traceability

Every finding from the three-lens validation (API-facts / codebase-audit / design-review agents,
2026-07-13) maps to one item (or item pair) or an explicit disposition; DOC items are
process/release items with no originating finding. Test column filled at implementation;
`/trace-check` verifies.

| Validation finding | Source lens | Item | Test (named at impl) | Disposition |
|---|---|---|---|---|
| `ui_control.json` lacks "json"; json_object 400 | codebase | **QW-1** | TODO | Fix (quick win) |
| Default model hardcoded ×2 | codebase | **QW-2** | TODO | Fix (quick win) |
| `user_context` blank joined section | codebase | **QW-3** | TODO | Fix (latent bug) |
| `max_tokens` rejected by reasoning models | API-facts | **WC-1** | TODO | Fix (wire only) |
| SDK floor 1.0.0 too low → silent `unknown` death | codebase | **WC-1** | TODO | Fix (floor bump) |
| Old proxies reject `max_completion_tokens` | API-facts | **WC-1** | TODO | Opt-out knob |
| 4xx categorized as `server` | codebase | **OB-1** | TODO | Fix |
| Truncation lands in `malformed`; `finish_reason` unread | codebase+design | **OB-1** | TODO | Fix |
| `last_error_category` race under gather | codebase+design | **OB-2** | TODO | Fix (result path) |
| Usage discarded; `debug_info` exclude=True | codebase | **OB-2** | TODO | Fix (+first-class field) |
| Omitted effort = `medium` on 5.5/5.6 (not 5.1) | API-facts | **RC-1 + VL-1** | TODO | Explicit config + load signal |
| `"none"` not universal (minimal/low-floor/rejected) — injection REFUTED | API-facts | **RC-1** (design ruling 1) | TODO (kwargs pin) | Rejected: no injection |
| Prefix table refuted both directions; no capability API | API-facts | **VL-1** | TODO (advisory-only pin) | Demoted to advisory |
| Effort × timeout × budget starvation interaction | design | **VL-1** | TODO | Warn rules |
| `temperature` in passthrough on reasoning model | design | **VL-1** | TODO | Warn rule |
| Future params need framework releases | design | **RC-2** | TODO | Passthrough |
| Per-agent budgets never plumbed | codebase | **RC-3** | TODO | Fix |
| Strict-signature fakes (`_FakeLLM`, simulator) | codebase | **RC-1/RC-3** | TODO (sibling check) | Only-when-configured |
| `update_api_key` resets config incl. `base_url` | codebase | **EN-1** | TODO (repro) | Fix (persistence) |
| Engine doesn't expose LLM knobs / `base_url` | codebase+design | **EN-1** | TODO | Fix |
| Cache reordering: zero savings < 1024 floor; contract conflicts | design+codebase | — | — | **Dropped** (out of scope; §3) |
| `reasoning_effort: "max"` unverified on Chat Completions | API-facts | — | — | **Deferred** (Responses/deep-lane spec) |
| Pro mode / `reasoning.context` Responses-only | API-facts | — | — | **Deferred** (deep-lane spec) |
| Cost ceiling / kill-switch missing | design | — (D-4 adjacent) | — | **Deferred** (follow-up spec; OB-2 is prerequisite) |
| Golden-replay eval gate for model-default changes | design | §12 standing rule | — | Process rule recorded |
| `json_schema` strict recommended over json_object | API-facts | — | — | **Deferred** (separable follow-up) |
| prompt guide :45 transcript-shape doc bug | codebase | **DOC-9** | — | Doc fix |
| gpt-4.1 sunset-track; migration saves 40–90% | API-facts | §13 guidance | — | Host guidance (no default change here) |
