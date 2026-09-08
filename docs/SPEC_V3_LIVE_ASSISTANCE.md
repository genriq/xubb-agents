# Xubb Agents Framework v2.7 → v3.0
## Live-Assistance Specification (live-assistance)

**Version:** staged by dependency gate — G0 (immediate patch) · A (vocabulary & typed acceptance) · B1 (grounding & permissioned interactions) · B2 (restraint) · C (delivery) · L (long-form) · D (session & evaluation); version numbers are chosen per gate, see §13
**Status:** **PROPOSED** — 2026-09-06, revised the same day after the maintainer's Amendment 2 rulings on the XUBB-ITC-1 package (see [SPEC_INSIGHT_TYPES_AMENDMENT_2.md](SPEC_INSIGHT_TYPES_AMENDMENT_2.md)). Nothing here is implemented. The vocabulary and validation design now lives in **XUBB-ITC-1 1.2.0** ("the type contract": [SPEC_INSIGHT_TYPES.md](SPEC_INSIGHT_TYPES.md), [INSIGHT_TYPES_FINAL_DECISIONS.md](INSIGHT_TYPES_FINAL_DECISIONS.md), adoption note [INSIGHT_TYPES_ADOPTION.md](INSIGHT_TYPES_ADOPTION.md)); this spec keeps the workstreams the type contract explicitly excludes and cross-references it item by item (Appendix C, consistent with the adoption note's reconciliation table). Items IT-1…IT-6 are retired here. **Gate G0 of the contract is implemented in this tree** (see §6.2).
**Date:** September 6, 2026
**Scope:** Move the framework's thesis — *agents help a human during a live conversation by surfacing rare, earned, well-timed insights* — out of prose and into code, contracts and evidence. Six workstreams: enforceable vocabulary, insight lifecycle, delivery, timing & principal, session state & budgets, evidence. Derived from a full read of the source at `main f83fc5b` (≈3,200 lines), the documentation set, the test suite (315 tests, 30/30 contracts) and one real session on the desktop host.
**Terminology:** "the host" is whatever application embeds this library; "the desktop host" is xubb-user, which drove the observed failures. "The principal" is the human the swarm assists; "the counterpart" is whoever they are talking to. "Nature" = what an insight is; "urgency" = when it must be seen; "outcome" = what the principal did with it.
**Compatibility:** G0 carries one deliberate edge in the default legacy mode: unrecognised types and malformed gates are rejected with a diagnostic instead of being coerced into advice or speech. A, B1, B2 and L are additive. C introduces an engine-owned per-session turn lock (hosts that already serialize turns are unaffected). D relocates per-session runtime state onto the Blackboard, which changes where cooldowns live but not what they do. Every new model field has a default, so existing wire consumers see new keys and nothing else. See §16.
**Design rulings requested (§11):** D-1 REPLY as a thesis stance · D-2 strict structured outputs default · D-3 restraint policy default · D-4 overlapping-turn behaviour · D-5 prompt-order amendment · D-6 keyword word-boundary default · D-7 multi-session engine · D-8 INFORMATION alias · D-9 version numbering.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [The Thesis as Testable Claims](#2-the-thesis-as-testable-claims)
3. [Evidence (E1 — read from the framework at main f83fc5b)](#3-evidence-e1--read-from-the-framework-at-main-f83fc5b)
4. [Framework Invariants (v2.7–v3.0 additions)](#4-framework-invariants-v27v30-additions)
5. [Issue Index](#5-issue-index)
6. [Workstream A — Enforceable Vocabulary](#6-workstream-a--enforceable-vocabulary)
7. [Workstream B — Insight Lifecycle](#7-workstream-b--insight-lifecycle)
8. [Workstream C — Delivery](#8-workstream-c--delivery)
9. [Workstream D — Timing & Principal](#9-workstream-d--timing--principal)
10. [Workstream E — Session State, Budgets & Thinking-Model Hygiene](#10-workstream-e--session-state-budgets--thinking-model-hygiene)
11. [Workstream F — Evaluation](#11-workstream-f--evaluation)
12. [Decisions Requested](#12-decisions-requested)
13. [Implementation Plan (Dependency Gates)](#13-implementation-plan-dependency-gates)
14. [Definition of Done (per release)](#14-definition-of-done-per-release)
15. [Testing Strategy & Negative Controls](#15-testing-strategy--negative-controls)
16. [Migration Notes](#16-migration-notes)
17. [Out of Scope / Non-Goals](#17-out-of-scope--non-goals)
18. [Appendix A — How the Desktop Host Consumes This](#appendix-a--how-the-desktop-host-consumes-this)
19. [Appendix B — Finding → Item Traceability](#appendix-b--finding--item-traceability)
20. [Appendix C — Item-level Cross-reference to the Type Contract](#appendix-c--item-level-cross-reference-to-the-type-contract-xubb-itc-1-v110--amendment-2)

---

## 1. Executive Summary

The Playbook states the thesis three times in the same words: a swarm of cheap observers surfaces *ephemeral, earned* insights; restraint is the product; silence is the default. The framework's mechanics are excellent and are guarded by a contract gate with zero debt. But every mechanism that makes an insight rare and earned **beyond the model's own gate** is documented as host glue: identity, de-duplication, ranking, attention budgeting, curation, keyword and silence detection, turn serialization, persistence. The Playbook ships a 200-line reference curator for hosts to copy. The desktop host copied it. A thesis whose central claims are implemented by every adopter is not being tested by the framework; it is being restated by it.

Three structural limits sit underneath the observed failures:

1. **The output vocabulary is prose, enforced by coercion.** The client requests `json_object`, not a schema; the model is told the type enum in an instruction string and writes whatever it likes; the parser coerces the result, silently and toward advice. Every coercion helper in `dynamic.py` exists because of this.
2. **Insights have no lifecycle.** No id, no turn, no anchor to the segment that prompted them, no supersession, no ranking key, no record of what the human did with them. "Earned" cannot be measured because nothing comes back.
3. **Delivery is batch.** A turn returns when its slowest agent returns, after Phase 2. Two-lane economics exist in configuration and not in delivery: a 30-second deep-lane agent delays every whisper from the same turn by 30 seconds. There is no streaming, no deadline, no cancellation of a stale turn.

Behind them: the engine cannot gate an LLM call on anything it can see in the transcript; it does not know who the principal is; cooldowns and private memory live on agent instances, which forces one engine per session and leaves persistence incomplete; there is no token budget, no cost ceiling, and no way to replay a recorded session offline to measure any of the above.

### Headline

| | |
|---|---|
| Workstreams | 6 (A–F) |
| Items | 29 here (SO-1, LH-1, UR-1, CF-1, LC-1…5, DL-1…6, TP-1…4, SS-1…5, EV-1…4) plus the type contract's 35 ITC contracts |
| New invariants | INV-20 … INV-48 (29; INV-38…48 added by the H1/H2/H3 hardening) |
| New models | `Urgency`, `AnchorRef`, `InsightOutcome`, `TurnEvent`, `SessionBudget` |
| New public API | `stream_turn`, `record_outcome`, `InsightPolicy`, `SessionRecorder`, `replay` |
| Gates | G0, A, B1, B2, C, L, D — dependency-ordered, versions chosen per gate (§13) |
| Behavioural edges | 3 (G0 legacy rejection of unknown types; C turn lock; D state relocation), each with an escape hatch or migration note |

### Guiding principles

1. **The thesis lives in code or it does not exist.** Anything the Playbook currently marks `[HOST GLUE]` and that is *about restraint, timing or accountability* becomes framework-owned, opt-in, with a passthrough default.
2. **Types name natures, never surfaces.** The model says what a thing is and when it matters; the host's table says where it goes.
3. **Never guess toward advice.** An unknown is the passive nature, recorded, logged once.
4. **Nothing is dropped invisibly.** Every suppression, deadline drop, cancellation and budget skip fires a callback with a reason.
5. **The framework never infers the human.** Who the principal is and what they did are host-declared facts, never guessed from strings.
6. **Additive, validated, instructable.** New vocabulary is an enum member the wire schema can enforce, not a key in a free dict.
7. **Claims get contracts.** Each thesis claim in §2 maps to at least one registered invariant with a negative control, and to at least one replay metric.

---

## 2. The Thesis as Testable Claims

The framework's purpose, restated as claims a test or a replay can falsify. Each claim names the workstream that makes it enforceable and the invariant(s) that pin it.

| Id | Claim | Enforced by | Pinned by |
|---|---|---|---|
| T-1 | **Restraint.** Over a session, the number of insights shown is bounded and every silence is a decision, not an accident. | B (policy, attention budget), A (gate integrity) | INV-26, INV-24 |
| T-2 | **Earned.** An insight is shown at most once per topic per window unless urgency demands it; repetition is structural, not a prompt instruction. | B (topic key, repetition suppression) | INV-25, INV-26 |
| T-3 | **Timely.** An insight carries when it must be seen, is anchored to what prompted it, and reaches the host as soon as its agent finishes — never behind a slower agent. | A (urgency), B (anchor), C (streaming, deadline) | INV-22, INV-28, INV-29 |
| T-4 | **Accountable.** The framework knows whether the principal saw, dismissed or acted on an insight, and agents can read that. | B (outcome channel) | INV-27 |
| T-5 | **Principal-aware.** The framework knows who it assists and never speaks for them by accident. | D (principal, roles), A (REPLY as an explicit nature) | INV-31, INV-20 |
| T-6 | **Measurable.** Any recorded session can be replayed offline and yield time-to-first-insight, insights per minute, repetition rate, acceptance rate and cost per minute. | F (recorder, replay, metrics) | INV-36 |

---

## 3. Evidence (E1 — read from the framework at main f83fc5b)

| Fact | Where |
|---|---|
| `InsightType` = suggestion, warning, opportunity, fact, praise, error — six members; comments name UI zones | `src/xubb_agents/core/models.py:13–19` |
| `AgentInsight` has no id, turn, anchor, urgency, topic or supersession field | `src/xubb_agents/core/models.py:125–135` |
| `TranscriptSegment.speaker` is a free string; `AgentContext.user_context` is free text; no principal | `models.py:71`, `models.py:108` |
| LLM requests use `response_format={"type": "json_object"}`; no schema on the wire | `src/xubb_agents/core/llm.py:242` |
| Unknown type → `InsightType.SUGGESTION`, silently | `src/xubb_agents/library/dynamic.py:596–599` |
| Gate check is truthiness of the raw value: the string `"false"` speaks | `dynamic.py:577` |
| Metadata extraction assigns the raw value (may be a non-dict; overwrites anything set earlier) | `dynamic.py:625–630` |
| Agent private memory mutated at parse time, before the engine decides to keep the response | `dynamic.py:731` (and `:643`) |
| Transcript rendered as `speaker: text`; timestamps and `is_final` unused | `dynamic.py:409` |
| Context window counted in segments (`context_turns`, default 6); RAG injected whole; no token accounting anywhere in `src/` | `dynamic.py:191`, `dynamic.py:440` |
| Memory scratchpad injected into the system prompt ahead of RAG, trigger and JSON instruction — prefix changes every turn | `dynamic.py:464–474` |
| Phase runs `asyncio.gather`; the turn returns after Phase 2; no streaming, deadline or cancellation | `src/xubb_agents/core/engine.py:766`, `engine.py:724` |
| Engine-level `max_retries` only (default 2) with a 10 s default timeout; no per-agent retry setting | `llm.py:45–47`, `llm.py:105` |
| Reasoning capability inferred from a name-prefix tuple (`gpt-5`, `o1`, `o3`, `o4`) | `engine.py:59–63` |
| No handling of `reasoning_content` or embedded thought tags before `json.loads` | `llm.py` (absent) |
| Conditions read only `var` / `fact` / `queue` / `memory` / `meta`; nothing from the transcript or `trigger_metadata` | `src/xubb_agents/core/conditions.py:85–125`; Playbook anti-pattern ":1139" |
| Keyword matching is case-insensitive substring; host-invoked | `engine.py:471–501` |
| Cooldown is wall-clock on the agent instance; private state on the instance | `src/xubb_agents/core/agent.py:145`, `agent.py:75` |
| Blackboard serializes fully, but cooldowns and instance state are not in it | `src/xubb_agents/core/blackboard.py:243–254` |
| ERROR insights carry raw exception text as content | `agent.py:131–142` |
| Usage telemetry per call exists; per-turn aggregate and any limiter are deferred | `models.py` (`AgentResponse.usage` comment); `docs/SPEC_LLM_MODERN_MODELS.md` §"Out of scope" |
| Zero tests for cancellation, overlapping turns, multi-session isolation, latency, growth, or the Jinja sandbox | `tests/` (grep) |
| Playbook marks insight curation, identity, cross-turn dedup, keyword/silence detection, turn serialization and persistence as `[HOST GLUE]` | `docs/PLAYBOOK.md` :2311, :4904, :4196, :909, :3343, :3279 |

Observed on the desktop host (one session, 2026-09-06): a summarizer's recap typed SUGGESTION on the guidance panel; a how-to typed FACT reaching no surface; a proposed reply with no honest type; a host-side curator re-implementing identity, dedup and ranking.

---

## 4. Framework Invariants (v2.7–v3.0 additions)

Registered in `CONTRACTS.yaml` with rule-asserting tests and negative controls, per `PROCESS.md`. INV-20…23 are carried from the `insight-types` proposal, revised.

| Id | Statement | Release |
|---|---|---|
| **INV-20** | **Natures, not surfaces.** Every `InsightType` member names what an insight is; no member, docstring or shipped schema instruction names a host surface. *(Test: denylist of surface words over the enum and all `schemas/*.json` instructions. Negative control: the current `models.py` comment "Zone A" fails.)* | A |
| **INV-21** | **Unknown classifications are rejected, never relabelled.** In legacy mode an unrecognised type, a model-authored `error`, or a new wire value outside the typed path rejects the insight with a sanitised diagnostic; state channels still commit. In typed mode the whole response rejects (type contract §8.4). No mode maps an unknown to SUGGESTION, OBSERVATION or any other human-facing purpose. *(Negative controls: the pre-change SUGGESTION fallback and the `"false"`-speaks gate must both fail.)* | G0 |
| **INV-22** | **Urgency is declared, not inferred from valence.** `AgentInsight.urgency ∈ {now, soon, whenever}` is always populated by precedence: valid explicit value, then agent override, then framework per-type fallback (§6.3). An invalid explicit value rejects. Urgency never bypasses permissions or the policy stage. | A |
| **INV-23** | **The knowledge object and the information card have different names.** Docs and schema instructions say "extracted fact" for `Fact` and "information card" for `InsightType.FACT`; no sentence uses "fact" for both. *(Doc lint; negative control: current spec §4.3 fails.)* | A |
| **INV-24** | **Strict schema on the wire when enabled.** With structured outputs in `strict` mode, every LLM request carries `response_format.type == "json_schema"` with `strict: true`, and the schema's enum fields are closed (the type field lists exactly the framework's members offered by that schema). *(Test: fake client captures kwargs. Negative control: `json_object` mode must fail the assertion.)* | A |
| **INV-25** | **Insight identity.** Every insight leaving `process_turn`/`stream_turn` carries a non-empty `id` unique within the session and the `turn` it was produced in; the id is unchanged by any policy stage. | A |
| **INV-26** | **Policy is observable and passthrough by default.** With no `InsightPolicy` configured, the insights returned equal the insights merged. With a policy, every insight it withholds fires `on_insight_suppressed(insight, reason)` exactly once. | B2 |
| **INV-27** | **Outcomes are host-reported, never inferred.** The engine writes an `InsightOutcome` only via `record_outcome`; no code path derives an outcome from expiry, a later turn, or model output. | B1 |
| **INV-28** | **No write after close.** When a turn closes by deadline or supersession, results from agents that finish afterwards are dropped whole: no insight is returned, no Blackboard container is written, and the drop fires `on_agent_skipped(name, "late")`. | C |
| **INV-29** | **Stream/batch equivalence.** For the same context, agents, fake LLM and policy, the multiset of insights yielded by `stream_turn` equals the list returned by `process_turn`, and the Blackboard end state is identical. | C |
| **INV-30** | **One turn per session at a time.** The engine serializes turns per `session_id`; an overlapping call either waits or supersedes per configuration, never interleaves. | C |
| **INV-31** | **The principal is explicit.** `AgentContext.principal_speaker` is host-declared; the framework never infers it from speaker strings, and every place that uses it degrades to today's behaviour when it is absent. | B1 |
| **INV-32** | **New condition sources fail closed.** `segment`, `trigger` and `agent` sources return `False` on a missing key, a type mismatch, or an invalid regex (compiled once, warned once). | B2 |
| **INV-33** | **Budget exhaustion is a skip with a reason.** When a `SessionBudget` is exhausted, eligible agents are skipped with `on_agent_skipped(name, "budget_exhausted")` and `sys.budget_exhausted` is set; the engine never stops silently and never manufactures an insight about it. | C |
| **INV-34** | **Reasoning text never reaches the parser.** Content is stripped of `<think>…</think>` blocks and `reasoning_content` is ignored before `json.loads`; the parsed dict never contains reasoning text. | G0 |
| **INV-35** | **Runtime state survives rehydration.** After `Blackboard.to_dict()` → `from_dict()`, an agent's cooldown and private memory are what they were; a turn on the rehydrated board respects them. | D |
| **INV-36** | **Replay determinism.** Replaying a recording with its recorded LLM outputs, under passthrough policy, reproduces the recorded insights and Blackboard end state exactly. | D |
| **INV-37** | **Content requests are isolated.** An extended-generation request never acquires the live-turn lock and never writes the live Blackboard; its result carries request and snapshot identity. A live turn started during a content request completes within its own deadline. | C |
| **INV-38** | **One acceptance boundary.** Every producer's response — DynamicAgent, custom agent, callback-modified — passes the same candidate and domain revalidation at the engine boundary; engine-owned fields are never producer-set. (H1, audit XA-01) | — |
| **INV-39** | **Answer visibility is scoped on the invocation view.** An agent's context contains only the answers to its own questions unless the host authorised sharing, through every access path. (H1, audit XA-02) | — |
| **INV-40** | **Interactive identity is present and matching.** Answers and corrections require a present current principal equal to the record's; missing identity disables, never wildcards. (H1, audit XA-03) | — |
| **INV-41** | **Typed failures are diagnostics.** Under typed_v1 an evaluation failure never enters the insight channel; the ERROR card is legacy-only. (H1, audit XA-07) | — |
| **INV-42** | **Content admission precedes allocation.** A content request is refused before any snapshot copy, clone, task or model call unless the contract is negotiated for that request. (H2, audit XA-04) | — |
| **INV-43** | **Content capacity is released on every exit.** Reserved at the entrypoint, released by the task's done-callback; completed handles leave the pending registry. (H2, audit XA-05) | — |
| **INV-44** | **Prompt fields come from the enabled contract.** No generated rule forbids a requested field; citable evidence is exposed whenever an enabled type needs it. (H2, audit XA-06) | — |
| **INV-45** | **Content-policy primitives are strict at construction.** Numeric strings, booleans and non-finite numbers never reach a policy checker coerced. (H2, audit XA-08) | — |
| **INV-46** | **The delivery artifact is exercised.** CI runs the installed wheel from outside the checkout. (H2) | — |
| **INV-47** | **Isolated views carry validated answers only.** The content task's frozen view passes the live turn's answer validator before scoping. (H3) | — |
| **INV-48** | **Negotiated limits hold at final acceptance.** Body, preview and format are re-checked against the frozen long-form ceilings on the object that commits. (H3) | — |

---

## 5. Issue Index

### Workstream A — Enforceable vocabulary (gate A)

| Id | Item | Size |
|---|---|---|
| SO-1 | Provider structured outputs derived from the type contract's authoritative schema; local validation stays mandatory | M |
| LH-1 | Legacy hardening patch: reject unrecognised types and malformed gates in legacy mode; remove parse-time private-state mutation | S |
| UR-1 | Urgency fallback precedence: explicit valid value → agent override → framework per-type fallback | S |
| CF-1 | `confidence_provided` runtime flag; legacy numeric shape preserved; ranking, tracing and display honour the flag | S |
| ~~IT-1…IT-6~~ | **Retired.** Vocabulary, alias, REPLY/QUESTION/CORRECTION permissions, typed rejection, ERROR sanitisation and Fact/INFORMATION naming are specified by the type contract (ITC-01…ITC-11, ITC-23) | — |

### Workstream B — Insight lifecycle (gates A, B1, B2)

| Id | Item | Size |
|---|---|---|
| LC-1 | Identity and anchoring: `id`, `turn`, `created_at`, `anchor: AnchorRef` | S |
| LC-2 | `topic` and `supersedes` — agent-declared continuity | S |
| LC-3 | `InsightPolicy` stage after merge: repetition suppression, attention budget, ranking; `on_insight_suppressed` | M |
| LC-4 | Outcome channel: `InsightOutcome`, `engine.record_outcome`, `sys.outcomes`, per-agent outcome counts readable by conditions and prompts | M |
| LC-5 | ERROR off the card path: diagnostic category, never raw exception text | S |

### Workstream C — Delivery (gate C)

| Id | Item | Size |
|---|---|---|
| DL-1 | `stream_turn`: insights delivered as agents are accepted; state committed at phase end in today's priority order; correction-bearing responses held whole until arbitration | M |
| DL-2 | `turn_deadline`: close the turn on time with what has arrived; late results dropped whole; the deadline also closes the correction-arbitration set | S–M |
| DL-3 | Supersession: a new turn on the same session cancels the in-flight one (opt-in, ruling D-4) | M |
| DL-4 | Engine-owned per-session turn lock (replaces the host's `asyncio.Lock` recipe) | S |
| DL-5 | Per-agent `max_retries`; VL-1 rule 6 warns when effort > low and retries > 0 | S |
| DL-6 | Isolated content-request path for extended generation: frozen snapshot, no live-turn lock, no live Blackboard writes, result tagged with snapshot identity | M |

### Workstream D — Timing & principal (gates B1, B2)

| Id | Item | Size |
|---|---|---|
| TP-1 | `principal_speaker` and `speaker_roles` on `AgentContext`; role tags in the rendered transcript; `{{ principal }}`; `sys.principal_speaker` | S |
| TP-2 | Condition sources `segment`, `trigger`, `agent`; operator `matches` (regex) | M |
| TP-3 | Engine tracks `sys.agent.<id>.last_spoke_turn`; `meta.turns_since_spoke` | S |
| TP-4 | Word-boundary keyword matching (`word_boundary=True`, ruling D-6); optional timestamps in the rendered transcript | S |

### Workstream E — Session state, budgets & thinking-model hygiene (gates G0, C, D)

| Id | Item | Size |
|---|---|---|
| SS-1 | Runtime state on the Blackboard: `sys.agent.<id>.last_run_at`, private memory; stateless agent definitions; multi-session engine (ruling D-7) | M |
| SS-2 | Token-budgeted context window and RAG cap (`context_tokens`, `rag_max_tokens`; chars/4 estimate, no new dependency) | S–M |
| SS-3 | `SessionBudget` cost ceiling; `usage_by_agent` on the merged response (closes the deferred OB-2 follow-up) | M |
| SS-4 | Thinking-model hygiene: strip thought tags / ignore `reasoning_content`; provider-neutral `thinking` field mapped to `reasoning_effort` | S |
| SS-5 | Prompt-order amendment: dynamic sections (memory, RAG, trigger) after static ones, for cache-prefix stability (ruling D-5) | S |

### Workstream F — Evaluation (gate F)

*Renamed from "Evidence" to avoid the clash with the type contract's evidence references, which ground a claim. This workstream measures effectiveness; it does not ground claims.*

| Id | Item | Size |
|---|---|---|
| EV-1 | `SessionRecorder` callback: JSONL of context snapshot, raw per-agent LLM output, merged response, outcomes | S–M |
| EV-2 | `xubb_agents.eval.replay`: run a recording against agent configs with recorded or live LLM outputs | M |
| EV-3 | Thesis metrics computed by the harness and registered as contracts of the harness | S–M |
| EV-4 | Documentation: Known Limitations page; prompt guide lists 6 schemas and current model policy; Playbook curator marked framework-provided; Fact/INFORMATION wording per the type contract | S |

---

## 6. Workstream A — Enforceable Vocabulary

The vocabulary itself (nine human-facing purposes, the `INFORMATION` alias, framework-only `ERROR`, typed rejection of unknown values, capability intersection for REPLY / QUESTION / CORRECTION, consulting subtypes) is specified by the type contract and is not restated here. This section keeps the four items the maintainer ruled belong to the framework beside that contract.

### 6.1 SO-1 — Provider structured outputs

**Problem.** `llm.py:242` requests `json_object`. The model is told the enum in prose and writes whatever it likes; the parser then coerces or, under the type contract, rejects. Preventing malformed generation is preferable to rejecting it afterwards.

**Change.**

- One authoritative contract per schema family, from which **both** the provider strict schema and the local validator derive. A test detects disagreement between the two.
- The provider schema must fit the provider's supported subset: all properties required, closed objects, no unsupported composition keywords. Open-ended domain dictionaries (variables, memory, metadata) get an explicit encoding (for example a list of key/value pairs) rather than being dropped to obtain a valid strict schema.
- Engine knob `structured_outputs: strict | json_object | auto`. Under `auto`, fallback to `json_object` happens **only for a recognised unsupported-capability response** (the provider names `response_format` as the rejected parameter), never for an arbitrary 4xx. An unrecognised failure stays a `misconfig` diagnostic. Fallback never weakens local validation or widens the allowed type set.
- Refusals are handled as a distinct outcome, not as malformed JSON.
- The prose instruction is still appended; the fallback path needs it.

**Tests / contract.** INV-24. Fake client captures kwargs per mode; derivation test (strict schema and local validator agree on every fixture in the type contract's `examples.json`); fallback fires on the recognised error and not on another 400.

### 6.2 LH-1 — Legacy hardening patch (immediate)

> **Status: IMPLEMENTED at gate G0 in this tree** per FINAL_DECISIONS D-LR — with one refinement over the text below: rejection scope is *insight-only for recoverable insight errors* (independently validated, authorized channels commit with an explicit `partial` status; action-bearing sidecars withheld), and *whole-response* for fatal rows (invalid domain payload, reserved-state write, unparseable envelope). See `docs/SPEC_INSIGHT_TYPES.md` §8.6, `core/insight_validation.py`, and contracts ITC-04/05/06/13/23/24 `.FW`.

**Problem.** The type contract's typed mode rejects unknown values, but legacy mode, the default in the current major, "preserves legacy coercions". That keeps the silent-to-advice failure alive for every existing host until it migrates. Relabelling an unknown as OBSERVATION was rejected in Amendment 2: `type: "briefing"` with content that commits to a discount is still advice, and it may introduce a type the legacy host does not support.

**Change.** In legacy mode:

- An unrecognised type, a model-authored `error`, or any of the four new wire values without the typed path **rejects the insight** with a sanitised diagnostic (`unknown_type` / `type_not_allowed`). The response's state channels still commit. Rejection scope is insight-only in legacy mode precisely because legacy hosts rely on state channels; typed mode keeps whole-response rejection.
- The gate accepts only Boolean `true`. `"false"`, numbers, null and a missing gate are silent (`invalid_gate` diagnostic when the value is present and not Boolean).
- `DynamicAgent` no longer mutates `private_state` at parse time (`dynamic.py:731`, `:643`); memory becomes durable only through the engine merge. This ships in the same patch so an insight-only rejection cannot leave previously mutated instance state behind.
- One diagnostic per rejected insight via `on_insight_validation_error` and `AgentResponse.diagnostics` (the type contract's §8.5 surface), so legacy hosts observe the rejection without adopting typed mode.

**Tests / contract.** INV-21 (revised): rejection, never relabelling. Negative controls: the pre-change SUGGESTION fallback and the pre-change `"false"`-speaks behaviour must both fail.

### 6.3 UR-1 — Urgency fallback precedence

**Change.** `AgentInsight.urgency` in {now, soon, whenever}, resolved in this order: a valid explicit model value, then the agent's configured `default_urgency` when set, then the framework's documented per-type fallback.

| Type | Framework fallback |
|---|---|
| warning, opportunity, reply, correction | now |
| suggestion, praise, question | soon |
| information, observation | whenever |

The fallback is a prior for omissions, not a type semantic: an explicitly authored warning about a later risk may be `soon` or `whenever`. An invalid explicit value is rejected under both modes (legacy: insight-only), never silently defaulted. Urgency does not bypass permissions, repetition control or attention limits (LC-3). Under a strict provider schema that requires non-null urgency, defaults apply only on custom-agent and fallback paths.

**Tests / contract.** INV-22 (revised precedence); invalid explicit value rejects; absent with mapping falls back, no warning.

### 6.4 CF-1 — `confidence_provided`

**Change (per FINAL_DECISIONS D-CR).** The public `AgentInsight.confidence` stays a non-null float. The runtime computes `confidence_provided: bool` at acceptance; the model cannot assert it. When `false` the numeric value is the historical placeholder `1.0`, is not an estimate, and must not be displayed as one. **Default ranking ignores confidence for every candidate** (the earlier "missing sorts below provided" rule is withdrawn): LC-3 sorts by the fixed total key `(urgency_order, -agent_priority, stable_merge_order)` where `stable_merge_order = (phase, registered-agent index captured for the turn, candidate ordinal)`, never completion order. No pairwise "compare confidence when both have it" comparator — it is non-transitive. The tracer records the flag; legacy serialisers omit it where their wire contract requires.

**Tests / contract.** Flag never model-authored; ranking is confidence-neutral and permutation-stable; tracer carries the flag; legacy serialisation unchanged when the flag is omitted. Lands at gate A (typed foundation).

---

## 7. Workstream B — Insight Lifecycle

### 7.1 LC-1 — Identity and anchoring

**Problem.** `AgentInsight` has no id; the Playbook tells hosts to hash `agent_id + content + turn` at render time (":4904"). Nothing records which segment an insight responds to, so relevance decay cannot be judged and the outcome channel (LC-4) has nothing to key on.

**Change.** Additive fields on `AgentInsight`, all populated by the engine at merge time (agents never set them; `create_insight` leaves them empty):

```python
id: str                       # engine-minted, unique within the session (uuid4 hex)
turn: int                     # context.turn_count at production
created_at: float             # session-relative seconds (A-2 convention)
anchor: Optional[AnchorRef]   # what prompted it

class AnchorRef(BaseModel):
    segment_index: int        # index into context.recent_segments at production
    timestamp: float          # that segment's timestamp
    speaker: str
```

The anchor defaults to the last segment of the context at production; agents may override via mapping `anchor_field` (an integer offset from the end, model-authorable, coerced fail-closed).

**Tests / contract.** INV-25. Ids unique across a 200-insight fixture; unchanged through LC-3; `turn` equals `context.turn_count`; anchor defaults to the last segment.

### 7.2 LC-2 — `topic` and `supersedes`

**Problem.** Cross-turn de-duplication is a prompt instruction ("do not repeat yourself") plus a memory pattern; the structural alternative is `[HOST GLUE]` (Playbook ":4196", ":4416").

**Change.** `topic: Optional[str]` — an agent-declared continuity key (mapping `topic_field`, default `"topic"`; listed in `json_schema` as nullable string). `supersedes: Optional[str]` — the id of an earlier insight this one replaces; the engine validates it names an id from this session (else dropped to `None`, warned once). Prompt guide teaches: "topic is the thing you are talking about, not the words you used."

**Tests / contract.** Round-trip; unknown `supersedes` cleared and warned; both absent → `None`.

### 7.3 LC-3 — `InsightPolicy`

**Problem.** Restraint beyond the model's gate is host code. The framework's thesis is unenforceable by the framework.

**Change.** An engine-level stage after `_merge_responses` and before return/yield:

```python
class InsightPolicy(Protocol):
    def apply(self, insights: list[AgentInsight], ctx: PolicyContext) -> PolicyResult: ...

class PassthroughPolicy      # default — returns everything, in merge order (INV-26)
class RestraintPolicy:
    repetition_window_turns: int = 6     # same (agent_id, topic) within the window → suppressed
    repetition_override: set[Urgency] = {"now"}   # urgencies that bypass the window
    attention_budget_per_turn: Optional[int] = None   # keep top-K after ranking
    rank_key = (urgency_rank, agent_priority desc, confidence desc, merge order)
```

`PolicyContext` gives the policy the Blackboard (read-only snapshot), the session's recent insight ledger (`sys.insights.recent`, a bounded ring the engine maintains), and outcomes (LC-4). Every withheld insight fires `on_insight_suppressed(insight, reason)` with reason ∈ {`repetition`, `attention_budget`, `superseded`, `policy:<custom>`}. Suppressed insights still count as "spoke" for cooldown purposes (the agent did run) but **not** for `last_spoke_turn` (TP-3), so gating on "I have been quiet" reflects what the human saw.

**Compatibility.** Default passthrough; hosts with their own curator keep it. Ruling D-3 asks whether `RestraintPolicy` should become the default at gate D.

**Tests / contract.** INV-26. Passthrough equality; each suppression reason fires once; `now` bypasses repetition; ranking is total and deterministic (property test over shuffled inputs); negative control: a policy that drops without firing the callback must fail.

### 7.4 LC-4 — Outcome channel

**Problem.** The only human→agent signal is FORCE. The Playbook concedes the missed-moment metric "needs ground truth the framework cannot supply" (":5111"). "Earned" cannot be measured; agents cannot adapt to a person; replay has no labels.

**Change.**

```python
class InsightOutcome(BaseModel):
    insight_id: str
    outcome: Literal["shown", "dismissed", "acted", "spoken", "expired", "contradicted"]
    timestamp: float                      # session-relative
    note: Optional[str] = None            # host-supplied, never interpreted

engine.record_outcome(context, outcome)   # sync; validates insight_id is known this session
```

Storage: `sys.outcomes` (bounded ring, default 200) and per-agent counters `sys.agent.<id>.outcomes = {"shown": n, "acted": n, ...}`. Readable by conditions via the new `agent` source (TP-2: `{"agent": "self.outcomes.dismissed", "op": "lt", "value": 3}`) and by prompts via `{{ outcomes }}` (own agent's counters) in Jinja. The engine never writes an outcome itself (INV-27): expiry is a host observation, not an engine inference.

**Tests / contract.** INV-27. Unknown id rejected with `ValueError`; ring bounded; counters correct; no engine path writes `sys.outcomes` (grep-style structural test plus behavioural: a full turn with expiring insights leaves `sys.outcomes` empty).

### 7.5 LC-5 — ERROR off the card path

**Problem.** `agent.py:131–142` ships `str(e)` as insight content. Internals reach the UI; SECURITY.md tells hosts to treat output as untrusted, but the framework itself produces the untrusted text.

**Change.** ERROR content becomes the failure category (`"agent_error"`, or the LLM error category when known: `timeout`, `rate_limit`, …); the exception text moves to `metadata["detail"]` and `debug_info`. `on_agent_error` is unchanged.

**Tests / contract.** Content never contains the exception message; detail present in metadata; tracer still records the error.

---

## 8. Workstream C — Delivery

### 8.1 DL-1 — `stream_turn`

**Problem.** `engine.py:766` gathers; `engine.py:724` returns after Phase 2. A deep-lane agent with a 30 s budget delays every whisper from the same turn by 30 s. The Playbook's own formula admits this (":3096"). The two-lane pattern is configuration-only; delivery is single-lane. Callbacks fire per agent, but insights there are unmerged, unranked and facts are unstamped.

**Change.**

```python
async def stream_turn(self, context, *, allowed_agent_ids=None, trigger_type=..., trigger_metadata=None,
                      turn_deadline: Optional[float] = None) -> AsyncIterator[TurnEvent]

class TurnEvent(BaseModel):
    kind: Literal["insight", "agent_done", "phase_end", "turn_end", "dropped"]
    insight: Optional[AgentInsight]        # kind == "insight": policy-applied, id-minted, anchored
    agent_id: Optional[str]
    phase: Optional[int]
    response: Optional[AgentResponse]      # kind == "turn_end": the full merged response, as process_turn returns today
    reason: Optional[str]                  # kind == "dropped": "late" | "cancelled" | "budget_exhausted"
```

Semantics: agents run via `asyncio.as_completed`; each completion is merged **incrementally** in registration/priority order into the Blackboard using the existing `_merge_responses` logic applied per response, then run through the policy with the insights produced so far in this turn, and yielded. Facts are stamped at that moment. Phase 2 begins when Phase 1 completes (unchanged one-hop semantics). `process_turn` becomes `[e async for e in stream_turn(...)][-1].response` — one implementation, two surfaces.

**Delivery versus commit.** Local validation is complete when an agent's response arrives, so acceptance is decided per response on arrival. *Delivery* of accepted insights is immediate; *commit* of the response's state channels (variables, queues, facts, memory, data sidecar) is deferred to phase end and applied in today's ascending-priority, registration-order merge. This preserves every documented merge semantic (last-writer-wins by priority, ordered queue and sidecar appends, INV-9 fact resolution) without waiting for the slowest agent to deliver an insight. Facts are stamped at commit; the policy stage (LC-3) reads the phase snapshot.

**Correction-bearing responses are held whole.** A response that contains a CORRECTION is not delivered or committed until the phase's correction arbitration completes (type contract §10.3), because whole-response atomicity forbids showing its other insights and then rejecting it as the arbitration loser. Responses without corrections are unaffected. A turn deadline (DL-2) closes the set of correction candidates eligible for arbitration; a correction arriving after the close is dropped whole under INV-28.

**Tests / contract.** INV-29 (stream/batch equivalence over a fixture with mixed priorities and same-key writes, arrivals shuffled by a fake with per-agent latencies); every yielded insight has an id and anchor; `turn_end` response equals `process_turn`'s.

### 8.2 DL-2 — `turn_deadline`

**Change.** `turn_deadline` (seconds, per call; engine default `None`) closes the turn when reached: pending agent tasks are cancelled, `turn_end` is yielded with what arrived, and each unfinished agent yields `dropped(reason="late")` and fires `on_agent_skipped(name, "late")`. A cancelled agent's `last_run_time` still updates (B4 discipline: it ran). INV-28: nothing from a late agent touches the Blackboard.

**Tests / contract.** Fake with one 5 s agent and a 0.2 s deadline: fast insights yielded, slow agent dropped, Blackboard has no trace of it, wall-clock under 1 s (the suite's first latency assertion).

### 8.3 DL-3 — Supersession

**Change.** Engine option `overlapping_turns: Literal["wait", "supersede"]` (default per ruling D-4). Under `supersede`, a new `stream_turn`/`process_turn` on a `session_id` with a turn in flight cancels the in-flight one; its pending agents are dropped with reason `cancelled` (INV-28 applies), and its stream ends with `turn_end` carrying the partial response. Under `wait`, the new call queues behind the lock (DL-4).

**Tests / contract.** Two overlapping turns, both modes; the superseded turn never writes after cancellation; the new turn sees a consistent Blackboard.

### 8.4 DL-4 — Session turn lock

**Change.** `asyncio.Lock` per `session_id`, engine-owned (weak dict, evicted with the session). Replaces the Playbook recipe (":3343"). A host lock outside remains harmless. INV-30.

**Tests / contract.** Overlap test asserts no interleaving of `sys.*` writes or `clear_events`; negative control: with the lock disabled (test-only flag) the interleaving test must fail.

### 8.5 DL-5 — Per-agent `max_retries`

**Problem.** Retries are engine-wide (default 2). A timed-out 30 s reasoning call retries twice: up to 90 s and three server-side generations, billed. Rule 3 warns about timeout, not retries.

**Change.** `model_config.max_retries` (coerced like `timeout`), forwarded per call via `client.with_options(max_retries=...)`. Framework never injects a default (INV-15). **VL-1 rule 6:** effort above low with effective retries > 0 → warn-once ("a retried reasoning call is billed per attempt").

**Tests / contract.** Kwarg captured by fake; rule 6 fires and is silent for low effort; negative control per VL-1 pattern.

---

### 8.6 DL-6 — Isolated content-request path

**Problem.** The type contract's `long_form_v1` permits configurations (illustratively 60 s per request, 16,000 output tokens) that would run inside the live observer batch. FORCE is a permission condition, not an execution path: a FORCE turn still holds the session lock and gathers with everything else, so live turns queue behind it. A short turn deadline is not a fix either; it would cancel every long answer before completion.

**Change.** Extended generation during an active session runs on a separate path:

- `engine.request_content(context, agent_id, InsightContentRequest)` reads a **frozen snapshot** of the Blackboard and transcript, runs outside the per-session turn lock, and never writes to the live Blackboard. Its result carries the request id and the snapshot identity (turn, segment count) so the host can flag potentially outdated context.
- Its output is delivered through the typed delivery interface with `content_contract` and `response_depth` stamped, and is subject to the content contract's completion and size checks; it is not merged into a live turn.
- Until this path exists, `detailed` and `standard` depth are restricted to paused or post-session use, or to a mode that explicitly pauses live assistance. The engine refuses a content request on a session with live turns enabled unless the host has declared the pause.

**Tests / contract.** INV-37: a content request never acquires the live lock or writes the live board; a live turn started during a content request completes within its own deadline. Negative control: routing the request through `process_turn` must fail the isolation assertion.

---

## 9. Workstream D — Timing & Principal

### 9.1 TP-1 — Principal and roles

**Problem.** `speaker` is a free string; `user_context` is free text. The engine cannot tell who it assists. REPLY (type contract §9), interruption awareness, and acceptance metrics all need it. The type contract's `principal_id` says *who* the human is; `principal_speaker` says *which transcript speaker* they are. Both are host-declared.

**Change.** `AgentContext.principal_speaker: Optional[str]`; `AgentContext.speaker_roles: Dict[str, str]` (speaker → free role label, e.g. `"counterpart"`, `"third_party"`). When set: `DynamicAgent` renders `speaker [principal]: text` / `speaker [counterpart]: text`; Jinja exposes `{{ principal }}` and `{{ speaker_roles }}`; the engine sets `sys.principal_speaker`. When absent, rendering and variables are exactly today's (INV-31).

**Tests / contract.** INV-31: no code path assigns `principal_speaker` except the host; rendering byte-identical when absent.

### 9.2 TP-2 — Transcript-aware conditions

**Problem.** `conditions.py:85–125` reads only Blackboard containers and four meta keys. A config cannot say "only when the counterpart spoke, more than eight words, and it looks like a question". The cheapest cost lever in a copilot is missing; the Playbook lists it as an anti-pattern to avoid (":1139") rather than a gap.

**Change.** Three sources and one operator:

| Source | Keys | Example |
|---|---|---|
| `segment` | `speaker`, `text`, `word_count`, `is_principal`, `is_final`, `timestamp` — of the **last** segment; `segment_offset: -N` selects earlier ones | `{"segment": "is_principal", "op": "eq", "value": false}` |
| `trigger` | any key of `trigger_metadata`, plus `type` | `{"trigger": "silence_duration", "op": "gte", "value": 8}` — closes the ":1139" gap |
| `agent` | `self.turns_since_spoke`, `self.last_run_at`, `self.outcomes.<kind>`, `<other_id>.turns_since_spoke` | `{"agent": "self.turns_since_spoke", "op": "gte", "value": 3}` |
| operator `matches` | regex over a string value; compiled once per rule and cached; invalid pattern → `False`, warned once | `{"segment": "text", "op": "matches", "value": "\\?\\s*$"}` |

All fail closed (INV-32). Word count is whitespace tokens.

**Tests / contract.** INV-32; each source × representative operators; bad regex; missing key; negative control: a rule that would fire on a `None` value must not.

### 9.3 TP-3 — `last_spoke_turn`

**Change.** When an insight from agent X survives policy in turn N, the engine sets `sys.agent.X.last_spoke_turn = N`. `meta.turns_since_spoke` is derived per agent at eligibility time. Suppressed insights do not count (LC-3).

### 9.4 TP-4 — Keyword word boundaries; transcript timestamps

**Change.** `check_keyword_triggers(text, allowed_agent_ids=None, word_boundary=False)`; `True` uses `\b`-anchored, case-insensitive matching. Default per ruling D-6. `DynamicAgent` option `render_timestamps: bool = False` prefixes `[t+12.4s]` per line when set (helps silence/pace reasoning; off by default to keep prompts byte-stable).

---

## 10. Workstream E — Session State, Budgets & Thinking-Model Hygiene

### 10.1 SS-1 — Runtime state on the Blackboard

**Problem.** `agent.py:145` keeps cooldown as wall-clock on the instance; `agent.py:75` keeps private memory there too (with MR-1 syncing a copy through the Blackboard). Consequences: one engine per session is mandatory (Playbook ":3277"); `to_dict` misses cooldowns, so a rehydrated session fires everything at once; `dynamic.py:731` mutates the instance before the engine has decided to keep the response.

**Change.**

- `sys.agent.<id>.last_run_at` on the Blackboard is the cooldown source of truth; the instance field becomes a per-turn cache. Clock domain: `AgentContext.session_clock: Optional[float]` (session-relative now) when the host provides it, else wall-clock as today — same domain for read and write.
- Private memory: `DynamicAgent` stops mutating `self.private_state` at parse time; memory reaches the Blackboard only through the engine's merge (which already does this). `private_state` remains for custom subclasses but is documented as ephemeral.
- With state off the instance, an `AgentEngine` can serve many sessions: registry shared, everything per-session on the context's Blackboard. Ruling D-7 decides whether gate D documents the multi-session engine as supported or only relocates state.

**Tests / contract.** INV-35: `to_dict`/`from_dict` then a turn respects cooldown; multi-session isolation test (two contexts, one engine, cooldown and memory do not leak) — the suite's first.

### 10.2 SS-2 — Token-budgeted window

**Change.** `model_config.context_tokens: Optional[int]` — when set, the transcript window is trimmed from the oldest segment until `len(text)/4 ≤ budget` (no tokenizer dependency; documented as an estimate). `rag_max_tokens` caps the RAG block the same way (oldest docs dropped last; each doc truncated only if alone it exceeds the cap). `context_turns` continues to apply first. Nothing changes when unset.

### 10.3 SS-3 — `SessionBudget`

**Problem.** Usage telemetry landed in 2.5; the limiter was deferred and the spec calls that incomplete. Thinking models multiply the exposure; truncated reasoning bills with no output.

**Change.**

```python
class SessionBudget(BaseModel):
    max_total_tokens: Optional[int] = None        # prompt + completion + reasoning, per session
    max_calls_per_turn: Optional[int] = None
    max_cost_units: Optional[float] = None        # host-supplied per-model rates: engine.set_rates({model: (in, out)})
```

`AgentEngine(budget=...)`. Accounting from `LLMResult.usage` into `sys.usage.total` and `sys.usage.by_agent`; `AgentResponse.usage_by_agent` populated on the merged response (the deferred OB-2 aggregate). When exhausted: eligible agents skipped with reason `budget_exhausted`, `sys.budget_exhausted = true`, callback per skip (INV-33). FORCE bypasses the budget (the human asked). Reset is host-owned (`engine.reset_budget(context)`).

**Tests / contract.** INV-33; FORCE bypass; aggregate equals the sum of per-agent usage.

### 10.4 SS-4 — Thinking-model hygiene

**Change.**

- `LLMClient`: before `json.loads`, strip `<think>…</think>` (and `<thinking>`) blocks from content; ignore `message.reasoning_content` if present. INV-34. Open reasoning models via vLLM/Ollama/DeepSeek endpoints stop failing every turn as `malformed`.
- Provider-neutral `model_config.thinking: Optional[Literal["off","low","medium","high"]]`, mapped today to `reasoning_effort` (`off`→`none`/`minimal` by model family per the existing VL-1 heuristics table; `low`→`low`; …). `reasoning_effort` remains and wins when both are set. This is the seam an Anthropic adapter (out of scope) would plug into.

### 10.5 SS-5 — Prompt-order amendment (ruling D-5)

**Problem.** `dynamic.py:464–474` places the memory scratchpad before RAG, trigger and the JSON instruction. Memory changes every turn, so the cacheable prefix ends at the system prompt. The modern-models spec ruled cache-aware reordering out of scope, citing the 1024-token floor and Jinja rendering; the floor argument weakens as prompts grow with roles, outcomes and schema instructions.

**Change.** Static sections first (user context, language, rendered system prompt, JSON instruction), dynamic sections last (memory, RAG, trigger). Documented prompt-order contract in the prompt guide amended in the same change; `test_dynamic_agent.py::TestPromptAssembly` updated. Behind an engine flag `prompt_layout: "v2" | "v3"` for one gate, default `v2` at gate C and `v3` at gate D.

---

## 11. Workstream F — Evaluation

### 11.1 EV-1 — `SessionRecorder`

**Change.** `xubb_agents.utils.recording.SessionRecorder(AgentCallbackHandler)` writes one JSONL record per turn: the `AgentContext` (segments, blackboard `to_dict`, trigger, principal), per-agent `debug_info.llm_output` and `usage`, the merged response, policy suppressions, and outcomes recorded since the previous turn. Privacy note mirrors `StructuredLogTracer`'s. `record_outcome` appends to the current turn's record.

### 11.2 EV-2 — `replay`

**Change.** `xubb_agents.eval.replay(recording, agents, *, llm="recorded" | LLMClient, policy=None) -> ReplayReport`. `"recorded"` feeds each agent its recorded raw output (a fake keyed by `(turn, agent_id)`), so a vocabulary, policy or condition change can be evaluated with zero LLM calls; a live client re-runs the prompts. INV-36 pins determinism under passthrough.

### 11.3 EV-3 — Thesis metrics

Computed by `ReplayReport` from a recording; registered as contracts **of the harness** (fixture recordings with known values; negative-control fixtures built to violate each):

| Metric | Definition | Claim |
|---|---|---|
| `time_to_first_insight_ms` | per turn, first yielded insight minus turn start (from the stream) | T-3 |
| `insights_per_minute` | surviving insights / conversation minutes | T-1 |
| `repetition_rate` | insights with the same `(agent_id, topic)` as one in the prior window / surviving insights | T-2 |
| `suppression_rate` | suppressed / merged | T-1 |
| `acceptance_rate` | `acted` + `spoken` / `shown` (requires outcomes) | T-4 |
| `cost_per_minute` | total tokens (or cost units) / conversation minutes | T-1 |

The eval gate the modern-models spec asked for ("any change to `DEFAULT_MODEL` needs a golden-replay harness") becomes runnable.

### 11.4 EV-4 — Documentation

- New `docs/LIMITATIONS.md` (the only current list is `technical_spec_agents.md` §"Current Limitations", unlinked from `.github/`); linked from the issue templates.
- Prompt guide: six schemas (adds `custom1`, `ui_control`); model-policy section that the Playbook's "§9" cross-reference actually points at; examples move off `gpt-4o`; Fact/FACT wording (INV-23); the two-question type rule (below).
- Playbook: the `InsightCurator` reference marked "now framework-provided (LC-3); keep a host curator only for surface routing"; `[HOST GLUE]` items closed by this spec annotated.
- Technical spec §4.3: natures table without zone words (INV-20); §4.5 "an extracted fact".

**The rule for prompt authors ("choose the type by two questions").** Must the principal act or speak in the next ten seconds? A risk → `warning`. A moment to seize → `opportunity`. Words to say to the counterpart → `reply`. Ordinary advice or a question to ask → `suggestion`. "Keep doing that" → `praise`. If not, it is information: one short datum → `fact`; a neutral reading of what is happening → `observation`. Length is the host's problem; the type says what it is.

---

## 12. Decisions Requested

| Id | Decision | Options | Recommendation |
|---|---|---|---|
| **D-1** | REPLY as a nature, and the stance it implies | — | **Settled by the type contract** (§7.2, §9): member exists; available only through `allow_reply`, host draft support, explicit principal identity, and the typed contract; a draft never authorises sending or speaking |
| **D-2** | Structured-outputs default | `auto` / `json_object` / `strict` | **`auto`** at gate A; `strict` at gate D for schemas derived from the authoritative contract |
| **D-3** | Policy default | passthrough / `RestraintPolicy` | **passthrough** through gate C; revisit at gate D with replay evidence (EV-3) |
| **D-4** | Overlapping turns | `wait` / `supersede` | **`wait`** (matches today's host lock); `supersede` documented as the live-copilot setting |
| **D-5** | Prompt-order amendment (contradicts the modern-models ruling 3) | adopt with flag / reject | **adopt with flag**; default flips at gate D |
| **D-6** | Keyword word-boundary default | `False` (E-8 preserved) / `True` | **`False`** at gate B2, **`True`** at gate D with a CHANGELOG edge |
| **D-7** | Multi-session engine | document as supported at gate D / relocate state only | **supported**, gated on the isolation test (SS-1) |
| **D-8** | `INFORMATION` alias for FACT | — | **Settled by the type contract** (§4): alias adopted now, `"fact"` stays on the wire, `.name` stays `FACT`, labels come from an explicit map, no `@unique`; the wire rename is a separately versioned migration |
| **D-9** | Numbering | per gate / fixed minor-version plan | **Settled by Amendment 2**: dependency gates, versions chosen per gate after its compatibility inventory; the state relocation, layout flip and strict default warrant a major bump when gate D ships |

---

## 13. Implementation Plan (Dependency Gates)

Milestones are ordered by dependency, not assigned to minor versions; the maintainer chooses version numbers after reviewing each gate's compatibility inventory. Built-wheel and host-conformance tests accompany each enabled capability rather than waiting for a final adoption milestone.

| Gate | Contents | Opens when |
|---|---|---|
| **G0 — Immediate patch** | LH-1 (legacy hardening, parse-time mutation removed), SS-4 thought-tag strip, DL-5 per-agent retries, sandbox test | Nothing; ships first |
| **A — Vocabulary & typed acceptance** | Type contract M1 + M2; SO-1; UR-1; CF-1; identity (LC-1) | G0 merged |
| **B1 — Grounding & permissioned interactions** | Type contract M3 + M4 (evidence adapters, REPLY, QUESTION, CORRECTION); TP-1 principal; LC-2; LC-4 outcomes | A; each type stays unavailable until its host path passes conformance |
| **B2 — Restraint** | LC-3 policy stage; TP-2, TP-3, TP-4 conditions and timing; EV-1 recorder | A |
| **C — Delivery** | DL-1…DL-4; SS-3 budget; DL-6 isolated content path | B1 (corrections) and B2 (policy) |
| **L — Long-form** | Type contract M5 storage/reading/preview/completion (does not wait for C); extended generation during a live session waits for DL-6 or a declared pause | A for storage; C for live generation |
| **D — Session & evaluation** | SS-1 state relocation; SS-2 window budget; SS-5 layout flip; EV-2 replay; EV-3 metrics; multi-session support (D-7) | C |

Ordering rationale: G0 closes the unsafe legacy path before anything else is discussed. A must precede everything because every later item's vocabulary has to be enforceable. B1 and B2 are independent of each other. C depends on both because streaming needs a policy to run insights through and an arbitration rule for corrections. L's storage half is deliberately decoupled from C; only live extended generation is gated. D is last because state relocation has the widest blast radius and the replay harness is what proves the rest.

---

## 14. Definition of Done (per release)

**Every gate.** Contract gate 30 + new INVs at `covered`, debt 0; every new invariant has a negative control; CHANGELOG lists edges explicitly; docs updated in the same PR; the README quickstart test still passes; built-wheel smoke and the host conformance kit run for each capability the gate enables, not at the end.

**G0.** INV-21 (revised), INV-34 registered. Legacy rejection of unknown types and malformed gates; parse-time mutation removed; sandbox test lands.

**A.** INV-20, INV-22, INV-24, INV-25 registered. Type contract M1 + M2 framework contracts registered (ITC-01…ITC-13 framework group). Strict schemas derived from the authoritative contract for `default_v2` and `v2_raw`; derivation test green; fake-client suite covers all three modes.

**B1.** INV-27, INV-31 registered. Type contract M3 + M4 framework contracts; each of REPLY, QUESTION, CORRECTION stays unavailable until its host conformance run passes.

**B2.** INV-26, INV-32 registered. `RestraintPolicy` property-tested. Recorder produces a fixture recording used by gate D.

**C.** INV-28, INV-29, INV-30, INV-33, INV-37 registered. First latency assertion in the suite (DL-2). Stream/batch equivalence over shuffled arrivals. Correction-bearing responses held whole under arbitration.

**L.** Type contract M5 framework contracts (ITC-26…ITC-30, ITC-33, ITC-35); host conformance kit covers ITC-31, ITC-32, ITC-34. Live extended generation enabled only once DL-6 is registered or the host declares a pause.

**D.** INV-35, INV-36 registered. Multi-session isolation test. EV-3 metrics with positive and negative fixtures. `LIMITATIONS.md` current.

---

## 15. Testing Strategy & Negative Controls

| Area | Rule test | Negative control |
|---|---|---|
| SO-1 wire | fake captures `response_format.type == "json_schema"`, `strict: true`, closed enum | `json_object` mode fails the same assertion |
| LH-1 legacy rejection | `"briefing"` rejects the insight with `unknown_type`; state channels still commit; `"false"` gate is silent; no parse-time mutation | old SUGGESTION fallback and `"false"`-speaks both fail |
| UR-1 urgency | explicit valid wins; agent override next; per-type fallback last; absent → fallback, no warn | invalid explicit value silently defaulted must fail |
| CF-1 confidence | flag runtime-computed; not-provided ranks below provided; tracer carries it | model-asserted flag must be ignored |
| LC-1 ids | unique over 200; stable through policy | a policy that re-mints ids fails |
| LC-3 policy | passthrough equality; each reason fires once; `now` bypasses | drop-without-callback fails |
| LC-4 outcomes | only `record_outcome` writes; ring bounded | an engine path writing `sys.outcomes` fails a structural grep test and a behavioural expiry test |
| DL-1/2 stream | equivalence over shuffled latencies; deadline drops late whole; wall-clock bound | remove the deadline: the same test exceeds the bound |
| DL-4 lock | no interleaving of `sys.*` / `clear_events` | lock disabled → interleaving observed |
| TP-2 conditions | each source × ops; bad regex fail closed | a `None` value that would compare truthy must not fire |
| SS-1 state | rehydrate → cooldown respected; two sessions isolated | shared-instance state (pre-change) leaks |
| SS-3 budget | skips with reason; FORCE bypass; aggregate = Σ | exhaustion with no callback fails |
| SS-4 strip | thought block never in parsed dict | pre-change: `malformed` |
| EV-2 replay | recorded → identical insights and board | mutate one recorded output → diff detected |
| Untested-today gaps | cancellation, overlapping turns, multi-session, latency, growth (snapshot cost over 500 turns), Jinja sandbox `SecurityError` | each gets a first asserting test at the gate that touches its area; the sandbox test lands at G0 as hygiene |

---

## 16. Migration Notes

- **Hosts casting `type` to their own enum** see `observation` and `reply` as unknown → fall back to their passive default (the desktop host already does).
- **New wire keys** on `AgentInsight`: `id`, `turn`, `created_at`, `anchor`, `urgency`, `topic`, `supersedes`. All present, all defaulted. `AgentResponse.usage_by_agent` appears on merged responses.
- **Hosts with their own curator** keep it; policy is passthrough until they opt in. When they adopt `RestraintPolicy`, their curator reduces to surface routing (Appendix A).
- **Hosts with their own turn lock** keep it; the engine lock is per session and compatible. Hosts that relied on overlapping turns "working" were racing `sys.*` and `clear_events`; `wait` is the safe default, `supersede` the copilot setting.
- **Custom `BaseAgent` subclasses** are unaffected by SO-1 (they own their calls); LC-1 fields are engine-minted so they need no change; SS-1 asks them to read cooldown via the provided helper rather than `self.last_run_time` if they override `process`.
- **Legacy rejection (G0).** Hosts on the default legacy mode will see rejected insights with an `unknown_type` or `invalid_gate` diagnostic where they previously received a coerced SUGGESTION or a spoken `"false"` gate. State channels still commit. Observe the diagnostics through the new callback or `AgentResponse.diagnostics`.
- **Persistence.** After gate D, `to_dict()` carries everything; hosts that persisted cooldowns separately can drop that code.
- **Prompt layout** flips at gate D; hosts pinning byte-stable prompts set `prompt_layout="v2"`.

---

## 17. Out of Scope / Non-Goals

- An Anthropic adapter and multi-provider abstraction (standing ruling; SS-4's `thinking` field is the seam, not the adapter).
- The Responses API, tool/function calling, MCP.
- Phase 3+ cascades (E-7 constrained by design; DL-1 keeps one hop).
- A UI, transcription, or a persistence backend.
- Changing the default model value (eval-gated by the modern-models spec; EV-2 makes that gate runnable but does not exercise it).
- Inferring the principal, inferring outcomes, or inferring urgency from content. All three stay host- or model-declared (INV-27, INV-31, INV-22).

---

## Appendix A — How the Desktop Host Consumes This

The host's table is one place, versioned with the host. The framework supplies natures, urgency, ids, anchors and outcomes; the host supplies surfaces.

| Nature | Urgency | Desktop surface | Treatment | Outcome the host reports |
|---|---|---|---|---|
| warning | now | guidance panel | pre-empts; spoken assertively | shown → acted / dismissed |
| opportunity | now | guidance panel | ahead of ordinary advice | shown → acted / dismissed |
| reply | now | answer area | opens at once, complete, spoken | shown → spoken / dismissed |
| suggestion, praise | soon | guidance panel | waits its turn; reading floor | shown → acted / expired |
| fact | whenever | readings + a settled row | counted and listed | shown |
| observation | whenever | card list only | a settled row; never the panel | shown |
| error | — | system banner | category, never the text | — |

At gate B2 the host's `insight_curator.py` keeps the right-hand columns and deletes identity minting, repetition suppression and ranking. At gate C the host consumes `stream_turn` and stops waiting for the deep lane, and requests detailed content through the isolated path instead of a FORCE turn. At gate D the host's recorded sessions replay against every prompt change before it ships.

---

## Appendix B — Finding → Item Traceability

| Finding (source) | Item(s) |
|---|---|
| Recap coerced to SUGGESTION (desktop session; `dynamic.py:596`) | LH-1, SO-1; type contract OBSERVATION |
| Reply has no type (desktop session) | Type contract REPLY (§9) |
| Urgency welded to valence (`models.py:13`) | UR-1 |
| Fact/FACT collision (spec §4.3/§4.5) | Type contract INFORMATION alias (§4); EV-4 |
| `json_object` on the wire (`llm.py:242`) | SO-1 |
| Gate truthiness `"false"` (`dynamic.py:577`) | SO-1 (strict boolean) |
| Metadata assign/non-dict (`dynamic.py:625`) | LH-1; type contract §8.3 (`invalid_metadata`) |
| No insight id / host mints (Playbook :4904) | LC-1 |
| Cross-turn dedup as prompt hack (Playbook :4196) | LC-2, LC-3 |
| Curator is host glue (Playbook :2311, :3763) | LC-3 |
| Missed-moment needs ground truth (Playbook :5111) | LC-4, EV-3 |
| ERROR ships exception text (`agent.py:131`) | LC-5 |
| Gather + return after Phase 2 (`engine.py:766`, `:724`) | DL-1, DL-2 |
| Overlap unsafe; host lock recipe (Playbook :3343) | DL-3, DL-4 |
| Engine-wide retries on reasoning calls (`llm.py:105`) | DL-5 |
| No principal (`models.py:71`, `:108`) | TP-1 |
| Conditions blind to transcript/trigger (Playbook :1139) | TP-2 |
| Substring keywords (E-8, `engine.py:501`) | TP-4 |
| Cooldown/memory on instance; engine per session (Playbook :3277) | SS-1 |
| Parse-time memory mutation (`dynamic.py:731`) | SS-1 |
| Segment-counted window, whole RAG (`dynamic.py:191`, `:440`) | SS-2 |
| Telemetry without limiter (modern-models spec) | SS-3 |
| Thought tags → malformed (`llm.py`) | SS-4 |
| Memory before static sections (`dynamic.py:468`) | SS-5 |
| No replay harness (modern-models spec :131) | EV-1, EV-2, EV-3 |
| Prompt guide lists 4 of 6 schemas; §9 cross-ref wrong | EV-4 |
| Zero tests: cancellation, overlap, multi-session, latency, growth, sandbox | §15 last row |

---

## Appendix C — Item-level Cross-reference to the Type Contract (XUBB-ITC-1 v1.1.0 + Amendment 2)

The type contract answers: *what is this message, is it allowed, and does it satisfy its declared contract?* This spec answers: *should it reach the human, is it still useful, and what happened after delivery?* Neither supersedes the other; the table makes the boundary enforceable during planning.

| This spec | Disposition | Type contract |
|---|---|---|
| IT-1…IT-6 | **Retired.** Replaced in full. | §3–§5, §8.6, §14.3; ITC-01…ITC-11, ITC-23 |
| SO-1 | **Retained**, aligned to the authoritative schema; provider schema and local validator derive from one contract | §13.3 (local strictness); Amendment 2 ruling A2-4 |
| LH-1 | **New**, from Amendment 2 ruling A2-1 | §8.6 (legacy mode) |
| UR-1 | **New**, from Amendment 2 ruling A2-2 | §6.2 `urgency`, §8.3 |
| CF-1 | **New**, from Amendment 2 ruling A2-9 | §6.2 `confidence` |
| LC-1 identity | **Consolidated**: engine-minted `id`, `turn`, `contract_version` per the type contract | §6.2, §14.2; ITC-09 |
| LC-1 anchor | **Retained** as the framework-generated *snapshot* reference (segment index, timestamp, speaker of the immutable window). Not a durable cross-turn identity; durable references need retained revisions or stable segment ids | §6.4 evidence catalog; Amendment 2 ruling A2-3 |
| LC-2 topic / supersedes | **Retained.** Replacing outdated advice is not the same act as correcting an earlier error | §10 CORRECTION (self-repair only) |
| LC-3 policy | **Retained.** Out of the type contract's scope by design | §14.1 (host controls selection) |
| LC-4 outcomes | **Retained.** Question answers are not an outcome channel; an `acted` or `spoken` event proves exposure and adoption, not correctness | §11 `insight_answers` |
| LC-5 diagnostics | **Consolidated** under the type contract's diagnostic contract | §8.5, §14.3; ITC-13, ITC-23 |
| DL-1…DL-5 | **Retained**, with correction-bearing responses held whole and state committed at phase end | §10.3; Amendment 2 ruling A2-7 |
| DL-6 | **New**, from Amendment 2 ruling A2-8 | §14.6–§14.9 `long_form_v1` |
| TP-1 principal | **Retained**; `principal_speaker` complements the type contract's `principal_id` (which transcript speaker the human is, versus who the human is) | §6.5 `principal_id` |
| TP-2…TP-4 | **Retained** | — |
| SS-1…SS-5 | **Retained**; SS-1 must honour "no parse-time mutation" (already in LH-1) | §8.4 |
| EV-1…EV-4 | **Retained** (renamed Evaluation) | §16.1 semantic review is complementary |
| Contract registry | Framework contracts only; host conformance kit and end-to-end suite are separate deliverables | §16; Amendment 2 ruling A2-6 |

