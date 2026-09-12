# Xubb Agents Framework v2.8
## Typed Reach Specification (typed-reach)

**Version:** 2.8.0 (2.8.1: the envelope failure category, §5)
**Status:** IMPLEMENTED — merged as PR #37 (2026-09-12), released as 2.8.0, then 2.8.1 with `ENVELOPE-FAILURE-CATEGORY` (INV-56). Spec-first per [PROCESS.md](PROCESS.md): every item landed with a registered contract (`CONTRACTS.yaml`), a rule-asserting test and its negative control, in one change; suite 930, contract gate 88/88 strict, clean-wheel smoke.
**Date:** September 12, 2026
**Scope:** Make the typed contract (`insight_contract="typed_v1"`, XUBB-ITC-1 1.2.0) reachable for a host's *existing* schema catalog without changing that catalog, and give a host what it needs to ground, sequence and attribute typed output: adapters for every shipped schema, evidence coordinates, a result-only instruction on the isolated path, urgency provenance, a documented content-slot ordering, correctable-target control, and per-agent sidecar attribution.
**Compatibility:** Additive. The `legacy_v2` contract, every legacy instruction and every legacy parse path are untouched; new public keys are nullable and absent from `model_dump_legacy()`. One registration outcome changes under `typed_v1` only: `custom1` fails registration with a named message instead of the generic one (it failed before too). See [§5 Migration](#5-compatibility-and-migration).
**Ground:** [SPEC_INSIGHT_TYPES.md](SPEC_INSIGHT_TYPES.md) §6.3, §6.6, §7.2–7.3, §10.1, §13.1–13.4, §14.6.1; [SPEC_V3_LIVE_ASSISTANCE.md](SPEC_V3_LIVE_ASSISTANCE.md) UR-1, DL-6 and its gate table (this release lands between gate A and gate C: it widens gate A's reach and prepares gate L's host sequencing; it ships nothing of gates B2, C, D).

---

## Table of Contents

1. [Summary](#1-summary)
2. [Framework invariants (v2.8 additions)](#2-framework-invariants-v28-additions)
3. [Items](#3-items)
4. [Contracts and negative controls](#4-contracts-and-negative-controls)
5. [Compatibility and migration](#5-compatibility-and-migration)
6. [Definition of done](#6-definition-of-done)
7. [Out of scope](#7-out-of-scope)
8. [Appendix — cross-reference to the type contract](#appendix--cross-reference-to-the-type-contract)

---

## 1. Summary

v2.7 shipped the typed contract behind three adapters (`insight_v1`, `default_v2`, `v2_raw`). A host whose registered batch also contains `default`, `ui_control` or `widget_control` agents cannot switch the engine to `typed_v1`: registration is all-or-nothing, so one legacy-only schema keeps the whole batch on the legacy contract. The first job of this release is **reach**: every shipped schema either registers under `typed_v1` through a declared adapter, or fails registration with a message that names what to do instead — never silently, never by relabelling.

The second job is what a host needs once typed cards flow:

- **Coordinates for evidence.** A typed card's `evidence_refs` name snapshot positions (`snap:<execution>:segment:<ordinal>`), which index the *trimmed* window the agent saw. A host that keeps the list of segments it passed for that execution needs the position in *that* list, not the trimmed one. The engine now records it and stamps it on accepted references; a host that wants every typed card grounded can ask for citation markers on every run.
- **A result-only instruction on the isolated path.** Extended generation is result-only (§14.6.1): domain channels are rejected there. The generated instruction stopped inviting them.
- **Urgency provenance.** A host that ranks on urgency only when the model authored it needs to know whether it did. `urgency_provided` is engine-owned and staged exactly like `confidence_provided`.
- **A documented ordering for content-slot release.** A host that sequences replacement (cancel the old ask, await it, admit the new) must know that when `await handle.result()` returns, the capacity slot is free. It is now a stated guarantee with its own awaitable, not an accident of callback registration order.
- **Correctable targets.** A host may retain records it does not want corrected (an answered question, a record past its window). `PriorInsightRecord.correctable` removes such a record from the offered targets and rejects a correction that names it.
- **Per-agent sidecar attribution.** The merged `data` sidecar loses which agent contributed what; `data_by_agent` keeps it.

Nothing here infers urgency, outcomes or the principal (the standing non-goals of the live-assistance spec hold).

---

## 2. Framework invariants (v2.8 additions)

| Id | Invariant |
|---|---|
| **INV-49** | Under `typed_v1`, every shipped schema either declares a typed adapter and registers, or fails registration with a message naming the schema, the reason and the alternatives. No schema registers under `typed_v1` without a declared adapter; no legacy instruction or parse path changes. |
| **INV-50** | A framework-built segment reference resolves to the position of that segment in the `recent_segments` list the host passed for the execution, recorded before trimming; the engine stamps `source_index` on accepted segment references and rejects a model-authored one. The prompt's reference shape and the validator's accepted shape are identical. |
| **INV-51** | On the isolated content path the generated instruction offers the insight envelope only — no domain channel, no sidecar, no memory invitation — and the live-turn instruction is unchanged. |
| **INV-52** | `urgency_provided` is true only when the accepted candidate carried a valid explicit urgency; a resolved default or fallback yields false; a producer cannot author it; unknown provenance is false. |
| **INV-53** | `await handle.result()` returns only after the content task's capacity slot has been released; `handle.released` resolves at the same point. |
| **INV-54** | A retained record with `correctable=false` is never offered as a correction target and a correction naming it is rejected (`target_not_correctable`); answers keep validating against the record. |
| **INV-55** | On an aggregated response, `data_by_agent` attributes every committed sidecar to the agent that produced it; a rejected agent contributes to neither `data` nor `data_by_agent`. |

---

## 3. Items

### 3.1 TA-1 — `default`: the `flat_v1` typed adapter

**Problem.** `default.json` declares `supported_contracts: [legacy_v2]` only. Its legacy shape is flat: the candidate fields sit at the root next to `has_insight` and `memory_updates`.

**Change.** The descriptor gains `typed_adapter: "flat_v1"`, `typed_supported_insight_types` (the nine wire values), `supported_insight_fields` (the twelve normalized candidate fields, `correction` and `question` included), `supported_contracts: [legacy_v2, typed_v1]`, `supported_transports: [json_object]`. The legacy `instruction` and `mapping` are byte-identical to v2.7.

Under `typed_v1`:

- the generated instruction's body is `{ "has_insight": true | false, <candidate fields>, "memory_updates": { "key": "value" } }` — the candidate at the root plus the schema's one channel; the silence-only envelope (§7.3) is `{ "has_insight": false, "memory_updates": {} }`;
- normalization is the flat rule already used by `flat_v2`: the candidate is the root minus the schema's domain keys (`has_insight`, `memory_updates`); placeholder fields under a false gate are discarded; a true gate with no candidate is `inconsistent_gate`;
- the `memory_updates` channel stages through the existing memory alias (merged view, no direct write), as on the legacy path.

**Tests / contract.** `TYPED-ADAPTER-FLAT-V1`: a `default` agent registers under `typed_v1`; the instruction's OUTPUT FORMAT carries the candidate fields and `memory_updates` and nothing else; an accepted result yields a typed insight with engine-minted identity and the memory update staged; a false gate with placeholder fields is silence with the memory update kept; the legacy path's instruction and result for the same agent are unchanged. Negative control: remove `typed_adapter` from the descriptor → registration under `typed_v1` fails with the named message.

### 3.2 TA-2 — `ui_control` and `widget_control`: `root_v2` with the sidecar

**Problem.** Both schemas nest the candidate under `insight`, carry state in `state_snapshot` and an action-bearing sidecar in `ui_actions`; they declare `legacy_v2` only. The existing `root_v2` instruction hardcodes `state_snapshot` and knows nothing of a sidecar.

**Change.** Both descriptors gain `typed_adapter: "root_v2"`, the nine types, the twelve fields, both contracts, `supported_transports: [json_object]`, and a `sidecar_instruction` string: the schema's own description of its `ui_actions` block (the target widgets and actions the legacy instruction already names). The `root_v2` instruction now reads the mapping instead of assuming it: the state block is named by `variable_updates_field`; when the mapping declares a `data_field`, the body carries that block and the rules append the descriptor's `sidecar_instruction`. `v2_raw` (no `data_field`, `state_snapshot`) renders exactly as in v2.7.

The silence-only envelope for a sidecar-bearing `root_v2` schema is `{ "<state field>": {}, "<data field>": [] }` with the rule "do NOT include an insight object": a widget controller may still act while it has nothing to say (`widget_control` is UI-primary). Typed staging already carries the sidecar (`response.data[data_key]`); the isolated path already counts it as a domain effect and rejects it there (§14.6.1).

**Tests / contract.** `TYPED-ADAPTER-ROOT-V2-SIDECAR`: a `widget_control` agent registers under `typed_v1`; the instruction names `state_snapshot` and `ui_actions` from the mapping and includes the descriptor's sidecar instruction; an accepted result stages the insight and the sidecar; silence with `ui_actions` commits the sidecar; `v2_raw`'s instruction is unchanged. Negative control: a `data_field`-bearing mapping whose descriptor lacks `sidecar_instruction` renders no sidecar block (the block is generated from the descriptor, never assumed).

### 3.3 TA-3 — `custom1`: unsupported under `typed_v1`, by name

**Decision.** `custom1` is the example custom schema (a `content_presence` gate over `sales_tip`, a type in `risk_category`, state in `blackboard`). It has no typed projection: the typed candidate's normalized fields cannot be carried by that mapping without inventing one. Two rulings were possible — a `state_only` silence adapter (the agent registers and never speaks) or an explicit refusal. This release chooses **refusal**: a silence adapter would register an agent whose configuration is a mistake and hide it as silence; an operator who wants typed state-only work declares `allowed_types: []` on a typed adapter (§7.3), which is explicit.

**Change.** `custom1.json`'s descriptor gains `typed_unsupported_reason` (one sentence naming the missing projection and the alternatives). Registration under `typed_v1` fails with `AgentConfigurationError` whose message names the agent, the schema, the reason and the six typed adapters (`insight_v1`, `default_v2`, `v2_raw`, `default`, `ui_control`, `widget_control`). The generic message for any other legacy-only schema lists the same six. Legacy registration of `custom1` is unchanged.

**Tests / contract.** `TYPED-UNSUPPORTED-SCHEMA-NAMED`: the message names `custom1`, the reason and every typed adapter; nothing is registered (the registry is atomic); the same agent registers under `legacy_v2`. Negative control: a descriptor that declares `typed_v1` without an adapter is the generic (not the named) refusal.

### 3.4 EC-1 — Evidence coordinates and the citations capability

**Problem.** The per-agent snapshot catalog (G2) is built after trimming: `snap:<execution>:segment:<i>` is the i-th *exposed* segment. A host that persists the exact `recent_segments` list it passed for that execution cannot map `i` back to it without repeating the engine's trimming. Citation markers are exposed only when an enabled type needs a basis (consulting profile, permitted correction); a host that wants every typed card sourced has no switch.

**Change.**

- `HostInsightCapabilities.evidence_citations: bool = False`. When a host declares it, every typed run exposes the citation markers, the evidence-reference contract and the host's citable ids — the same material the consulting profile and a permitted correction already receive. The default keeps v2.7 behaviour.
- Framework-built segment entries in the `EvidenceSnapshot` carry `source_index` (the segment's index in `context.recent_segments` as the host passed it, before trimming) and `timestamp` (the segment's own session-relative timestamp, copied at snapshot time). The snapshot is bound to `(execution_id, agent_id)` as before.
- An accepted `EvidenceRef` of kind `segment` that resolved through the run's snapshot carries the engine-stamped `source_index`; every other kind carries `null`. The field is engine-owned: a candidate carrying it (root or metadata) is `invalid_field / engine_owned`; the boundary strips and re-stamps it from staging like the other engine-owned values. The reference shape the prompt teaches and the validator accepts stays `{kind, ref_id, revision}` — parity.
- `AgentInsight.model_dump_legacy()` is unaffected (references are typed-only).

**Tests / contract.** `EVIDENCE-COORDINATES-AND-CITATIONS`: with four segments and a two-turn window, references to the two exposed segments resolve and are stamped `source_index` 2 and 3, the snapshot entries carry the same indexes and timestamps; `evidence_citations=True` puts the markers, the contract line and the host ids into a general-profile run's prompt where `False` does not; a document reference is stamped `null`. Negative controls: a reference to an unexposed ordinal is `unknown_reference` (unchanged); a model-authored `source_index` rejects the whole response; a custom producer that sets `source_index` on a reference is rejected at the boundary as engine-owned.

### 3.5 IC-1 — Result-only instruction on the isolated path

**Problem.** The generated instruction offers `events`, `variable_updates`, `queue_pushes`, `facts`, `memory_updates` (and a sidecar) on every typed run, and the prompt carries the memory scratchpad section. On the isolated path any of them rejects the result (§14.6.1, result-only), so the instruction invites what the validator refuses.

**Change.** When the run's execution declaration is `execution_path: isolated_content`, the generated body carries the insight envelope only (`insight_v1`: `has_insight` and `insight`; flat adapters: `has_insight` and the candidate fields; `root_v2`: `insight`), the rules state that the request is result-only, and the memory scratchpad section is omitted from the prompt. The live-turn instruction is byte-identical to v2.7 (plus this release's adapter items).

**Tests / contract.** `ISOLATED-INSTRUCTION-RESULT-ONLY`: on an admitted content task the captured prompt's OUTPUT FORMAT has no domain-channel key and the prompt has no `[YOUR MEMORY / SCRATCHPAD]` section, while the live-turn prompt of the same agent has both (control). Negative control: the domain-effect rejection on the isolated path still holds when a model returns channels anyway (unchanged; proves the instruction is not the only guard).

### 3.6 UP-1 — `urgency_provided`

**Change.** `TypedCandidate.urgency_provided` is true iff the candidate carried a valid explicit `urgency`; a value resolved from the agent's `default_urgency` or the per-type fallback (§6.6, UR-1) yields false. Staging hands it to the engine privately with `confidence_provided`; the boundary stamps `AgentInsight.urgency_provided` (nullable; `None` on legacy emissions; `False` for a producer that bypassed staging — unknown provenance is never authorship). The key joins every engine-owned list (public fields, candidate keys, metadata keys, the forbidden list in the generated instruction). Default ranking stays confidence- and provenance-neutral (D-CR): the flag is information for the host, never a rank input here.

**Tests / contract.** `URGENCY-PROVENANCE`: explicit `"now"` → true; omitted with `default_urgency` → false; omitted without → false with the fallback value; a candidate carrying `urgency_provided` rejects; a custom producer setting it is rejected as engine-owned; the legacy projection has no such key. Negative control: an invalid explicit urgency still rejects (never defaulted to "provided").

### 3.7 CS-1 — Content-slot release before `result()` returns

**Problem.** Capacity is released by the task's done-callback (H2 / XA-05). `await handle.result()` awaits the task; whether the release ran first depends on callback registration order — true today, documented nowhere, and one refactor away from wrong.

**Change.** `ContentTaskHandle.released` is an awaitable (a future) that the engine resolves when it releases the slot; `result()` awaits the task's outcome **and then** `released` before returning, on every exit (completion, rejection, cancellation, exception). A task-less handle (entrypoint refusal) has `released` already resolved. Guarantee: when `await handle.result()` returns, `engine` can admit another content task within the bound.

**Tests / contract.** `CONTENT-RESULT-AFTER-RELEASE`: with `max_concurrent_content_tasks=1`, cancel a running task, `await handle.result()`, and admit a replacement immediately — accepted, not `provider_admission_exhausted`; `await handle.released` alone also observes a free slot; the same holds for a completed task and for a refused (task-less) handle. Negative control: awaiting `handle.task` directly, with the release callback deliberately registered after the awaiter, observes the slot still held — the hazard `result()` closes.

### 3.8 CT-1 — `PriorInsightRecord.correctable`

**Change.** `PriorInsightRecord.correctable: bool = True` (host-set). The generated instruction's "your earlier messages you may correct" listing excludes non-correctable records; `validate_correction_target` rejects a correction naming one with `invalid_correction_target / target_not_correctable` (checked after the record's status, before the principal and authority checks, so an ineligible target never depends on who asks). `validate_answers` ignores the flag: a question the host marked non-correctable still takes its answer.

**Tests / contract.** `CORRECTABLE-TARGETS`: a non-correctable own record is absent from the offered list; a correction naming it rejects with the classification; the same record with `correctable=True` is offered and accepted (control); an answer to a non-correctable question validates. Negative control: an unknown target is still `unknown_target` (the new check does not mask the old ones).

### 3.9 DS-1 — `data_by_agent`

**Change.** `AgentResponse.data_by_agent: Dict[str, Dict[str, Any]]` on aggregated responses: `agent_id → the agent's committed sidecar` (a copy of what `response.data` carried before merging). The merged `data` keeps its v2.7 shape (lists concatenated, scalars last-wins). Per-agent responses leave it empty, like `acceptance_by_agent`.

**Tests / contract.** `DATA-BY-AGENT`: two widget agents each contribute `ui_actions`; the merged sidecar carries both, `data_by_agent` attributes each to its agent; a rejected agent appears in neither. Negative control: mutating `data_by_agent[agent]` after the turn does not change `data` (copies, not aliases).

---

## 4. Contracts and negative controls

| Contract id | Invariant | Rule test (node-level in `CONTRACTS.yaml`) | Negative control |
|---|---|---|---|
| TYPED-ADAPTER-FLAT-V1 | INV-49 | `tests/test_typed_reach_2_8.py::TestFlatV1Adapter::…` | descriptor without `typed_adapter` fails registration by name |
| TYPED-ADAPTER-ROOT-V2-SIDECAR | INV-49 | `…::TestRootV2Sidecar::…` | no `sidecar_instruction` → no sidecar block |
| TYPED-UNSUPPORTED-SCHEMA-NAMED | INV-49 | `…::TestUnsupportedSchema::…` | adapter-less typed declaration → generic refusal |
| EVIDENCE-COORDINATES-AND-CITATIONS | INV-50 | `…::TestEvidenceCoordinates::…` | model-authored `source_index` rejects; unexposed ordinal rejects |
| ISOLATED-INSTRUCTION-RESULT-ONLY | INV-51 | `…::TestIsolatedInstruction::…` | channels returned anyway still reject (guard independent of the prompt) |
| URGENCY-PROVENANCE | INV-52 | `…::TestUrgencyProvenance::…` | invalid explicit urgency rejects; producer-set flag rejected |
| CONTENT-RESULT-AFTER-RELEASE | INV-53 | `…::TestContentSlotOrdering::…` | awaiting the task directly with a late-registered release observes the slot held |
| CORRECTABLE-TARGETS | INV-54 | `…::TestCorrectableTargets::…` | unknown target still `unknown_target` |
| DATA-BY-AGENT | INV-55 | `…::TestDataByAgent::…` | copies, not aliases |

Every entry is `covered` in the same change; `debt_baseline` stays 0; `tools/check_contracts.py --strict` is the release gate.

---

## 5. Compatibility and migration

- **Legacy contract:** untouched. Every legacy `instruction` string, `mapping` and parse path is byte-identical; the G0 suite runs unchanged.
- **New public keys, all nullable and typed-only:** `AgentInsight.urgency_provided`, `EvidenceRef.source_index`; `EvidenceCatalogEntry.source_index` and `timestamp` on framework-built segment entries; `AgentResponse.data_by_agent` (empty dict by default); `HostInsightCapabilities.evidence_citations` (default `False`); `PriorInsightRecord.correctable` (default `True`); `ContentTaskHandle.released`. `model_dump_legacy()` carries none of them. Consumers that reject unknown keys keep using the legacy projection (§14.10).
- **Descriptors:** `default`, `ui_control`, `widget_control` declare `typed_v1`; `custom1` declares `typed_unsupported_reason`. The set of typed adapters is six.
- **Registration under `typed_v1`:** a batch containing `default`, `ui_control` or `widget_control` agents now registers; a batch containing `custom1` still fails, now with the named message. The all-or-nothing rule is unchanged.
- **Prompts under `typed_v1`:** `root_v2` schemas with a sidecar gain the sidecar block; the isolated path loses the channel invitations and the scratchpad section; `evidence_citations=True` adds the citation material to every typed run. Hosts pinning byte-stable typed prompts should expect these diffs; legacy prompts do not change.
- **Reference package:** `docs/reference/insight_types_1.2.0/` is the 1.2.0 contract artifact and is not modified; the engine-owned key lists in code are the authority for `urgency_provided` and `source_index`.
- **2.8.1 amendment (2026-09-12, ENVELOPE-FAILURE-CATEGORY, INV-56):** the `invalid_envelope` diagnostic's classification is the model client's failure category (`timeout`, `rate_limit`, `server`, `refusal`, `malformed`, `truncated`, `auth`, `misconfig`, `not_initialized`, `unknown`) when the client reported one, `none` otherwise; a non-object body keeps its type name. A host reading `code:classification` per execution and agent can exclude transport failures and still count refusals. Additive: one classification string.

---

## 6. Definition of done

- Every contract of §4 `covered`; `tools/check_contracts.py --strict` green; debt 0; every negative control present and named in the registry.
- The full suite green on 3.11–3.13 (CI matrix); the README quickstart test unchanged.
- `tools/wheel_smoke.py` extended: a `default`-schema agent registered under `typed_v1` produces a typed insight from the installed wheel, and a `widget_control` sidecar is attributed in `data_by_agent`.
- CHANGELOG `[2.8.0]` lists every edge explicitly (adapters, coordinates, isolated instruction, provenance, slot ordering, correctable, attribution) with the migration notes of §5; `docs/README.md`, `technical_spec_agents.md`, `prompt_engineering_guide.md` (the adapter table), `EXECUTIVE_SUMMARY.md` and the README's "What's New" updated in the release change; version bumped in `pyproject.toml` and `__init__.py`; `SECURITY.md` and the bug-report template name 2.8.
- This spec's status set to IMPLEMENTED with the merge reference.

---

## 7. Out of scope

Everything the live-assistance roadmap assigns to later gates: streaming (`stream_turn`), the turn deadline, supersession, the session turn lock, the restraint policy and outcome channel, the recorder and replay, session-state relocation, the window budget, the prompt-layout flip. An Anthropic adapter, the Responses API, tools. Inferring urgency, outcomes or the principal.

---

## Appendix — cross-reference to the type contract

| Item | XUBB-ITC-1 (SPEC_INSIGHT_TYPES.md) | Live-assistance roadmap |
|---|---|---|
| TA-1, TA-2, TA-3 | §13.1 descriptors ("default, custom1, ui_control, and widget_control remain legacy unless separately certified" — TA-1/2 certify three; TA-3 rules the fourth), §13.2 mappings, §7.3 empty sets | gate A reach |
| EC-1 | §6.3 reference shapes, §6.4 trusted reference context, §13.4 prompt guidance (reference availability) | — |
| IC-1 | §14.6.1 result-only isolated content | DL-6 |
| UP-1 | §6.6 urgency fallback (the resolution order is unchanged; only its provenance is surfaced), §6.2 engine-owned fields | UR-1, CF-1 pattern |
| CS-1 | §14.6.1 task ownership, §14.7 completion | DL-6 |
| CT-1 | §10.1 targets, §11.3 consumption | — |
| DS-1 | §14.3 diagnostics and attribution | — |
