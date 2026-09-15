# SPEC — Remove the `legacy_v2` insight contract

- **Status:** SHIPPED — merged as PR #41 (2026-09-13), released as 3.0.0, tagged `v3.0.0` at `d9a8b32`
- **Reviewed —** APPROVED round 3 (round 1: 3 majors + 1 minor; round 2 re-reported them after a failed patch wrote nothing; round 3 clean. Nothing contested — each finding was verified against the code before folding.)
- **Target release:** 3.0.0 (breaking)
- **Supersedes:** the contract-selection mechanism introduced with XUBB-ITC-1 §7.1

## 1. Summary

The library implements two insight contracts. `legacy_v2` is the original: a fixed five-value type vocabulary, a static per-schema instruction string, and an adapter that normalises a loosely-shaped model response. `typed_v1` (XUBB-ITC-1, shipped in 2.7.0; its reach across the shipped schemas extended in 2.8.0 — *corrected 2026-09-15, this line read "added in 2.8.0"*) replaced it: a nine-value vocabulary, an instruction composed per run from the run's effective permissions, and boundary validation that rejects what it did not ask for.

`typed_v1` was added **alongside** `legacy_v2` so embedders could migrate. That migration is complete. This release removes `legacy_v2`, the selection parameter that chose between them, and everything that exists only to serve the removed path.

This is a breaking change to a public API and is versioned as one.

## 2. What is removed

Measured on 2.8.1: 84 references across 7 modules, 5 test modules, 9 registry contracts, 1 schema.

### 2.1 `core/insight_validation.py`

- `INSIGHT_CONTRACTS` and `DEFAULT_INSIGHT_CONTRACT`.
- `LEGACY_HUMAN_TYPES` and `RESERVED_WIRE_VALUES` — with one vocabulary, no wire value is "recognised but reserved for the other contract". `HUMAN_WIRE_VALUES` becomes the only vocabulary.
- `normalize_legacy_type`, `validate_legacy_candidate`, `decide_legacy` and the legacy branches of `effective_insight_types` / `effective_types_for_run`.
- The `typed_contract_required` unavailability reason, which can no longer arise.

### 2.2 `core/engine.py`

- The `insight_contract` constructor parameter and the attribute it sets.
- The legacy branch of engine-boundary acceptance (§6.1 / §8.6, D-LR).
- The `partial_legacy_response` diagnostic code and its emission.
- The legacy-only error-card surface (H1 / XA-07), under which a framework-manufactured `error` insight reached the human channel.
- The legacy branch of `_validate_insight_config`, which accepted an agent whose schema declared only `legacy_v2`.

### 2.3 `library/dynamic.py`

- The static-instruction path: under `typed_v1` the schema's `instruction` string is not sent, so with one contract it is never sent and the `json_instruction` fallback is dead.
- The per-adapter legacy branches in `_normalize_typed` remain — they are adapter shape, not contract, and are **not** in scope (see §4).

### 2.4 Schemas

- `supported_contracts` is removed from all descriptors. A descriptor no longer declares which contract it supports, because there is one. `typed_adapter` remains and becomes required.
- **`custom1` is retired, and deleting the file is NOT how** (round 1, F1). `DynamicAgent._load_schema` falls back to `default.json` for any name it cannot find, logging a warning. So deleting `custom1.json` would not fail an agent still configured for it — it would **silently register that agent under `default`**, a different envelope with different channels, which is worse than either keeping it or breaking loudly.

  The removal is therefore: delete the file **and** reject the identifier explicitly, before the missing-file fallback is reached, with a named migration error saying `custom1` was removed in 3.0.0 and what to move to. The exception is scoped to that one identifier — the fallback's behaviour for every other unrecognised name is deliberately unchanged, because it is what lets an embedder's own schema name resolve sanely.

  Tested by a real registration attempt asserting the named error **and** that the registry was not mutated (registration is all-or-nothing, so a rejected batch must leave the previous registry serving).

### 2.5 The `_sync_state_to_legacy` bridge and the `memory_{agent_id}` channel

**Not in scope, and not renamed either** (round 1, F4 — an earlier draft promised a rename in §6 and never specified one). Despite the name, `_sync_state_to_legacy` projects blackboard state into the `shared_state` dict that agent code reads (E-2); the `memory_{agent_id}` pattern is a variable-channel convention (E-3). Neither is bound to the insight contract. Both keep their names and behaviour here: renaming a method embedders may reference is a separate breaking change and does not belong in a release whose break is already stated precisely.

## 3. Behaviour after the change

- An engine is constructed with no contract argument. Insight handling is always the typed regime.
- `effective_insight_types` resolves the run's set from the agent's `insight_config`, the schema descriptor, the host declaration and the run's prerequisites — unchanged, minus the branch that short-circuited to the five legacy values.
- A schema whose descriptor declares no `typed_adapter` is refused at registration with a named reason. Previously such a schema could still register under `legacy_v2`.
- Registration remains all-or-nothing: one unacceptable agent rejects the batch.

## 4. Explicitly not in scope

- **Adapter shapes.** `insight_v1`, `flat_v2`, `flat_v1` and `root_v2` are envelope shapes, not contracts. All survive.
- **The five type values.** `fact`, `suggestion`, `warning`, `opportunity`, `praise` are not removed — they are five of the nine in the surviving vocabulary. What is removed is the regime that offered *only* those five.
- **`_sync_state_to_legacy` / `memory_{agent_id}`** — §2.5.
- **Any behaviour change to the typed path.** This release removes a path; it does not alter the surviving one. A diff that changes typed behaviour is out of scope and must be a separate change.

## 5. Breaking changes, and what an embedder does

| Before | After |
|---|---|
| `AgentEngine(..., insight_contract="typed_v1")` | `AgentEngine(...)` — the argument is removed, not ignored |
| `AgentEngine(...)` defaulting to `legacy_v2` | no default; the typed regime is the only regime |
| a schema descriptor declaring `supported_contracts` | the key is ignored if present and should be deleted |
| an agent on `custom1` | must move to a schema with a `typed_adapter` |
| a `partial_legacy_response` diagnostic | no longer emitted |

**The argument is removed rather than accepted-and-ignored.** An embedder passing `insight_contract="legacy_v2"` must fail loudly at construction: silently upgrading them to a different validation regime would change what their agents may emit without telling them. A `TypeError` from an unexpected keyword is the correct, obvious failure.

## 6. Registry

Nine contracts are bound to the removed path and are **retired**, each with its reason recorded in the coverage summary:

`ITC-05.FW-silence-preserves-state`, `ITC-06.FW-unknown-type-rejects-no-relabel`, `ITC-13.FW-one-rejection-callback-per-result`, `ITC-23.FW-error-provenance-sanitized`, `ITC-24.FW-legacy-partial-acceptance-no-parse-mutation`, `INSIGHT-CONTRACT-SELECTION`, `ITC-17.FW-reply-is-a-permissioned-draft`, `TYPED-FAILURES-ARE-DIAGNOSTICS`, `TYPED-UNSUPPORTED-SCHEMA-NAMED`.

Two corrections from round 1 (F2). **`INV-19-reasoning-config-explicit` is not in this list** — its rule is about `reasoning_effort` on a model config and has nothing to do with insight contracts; it was a false positive of the text sweep that produced the inventory, and its entry and test are untouched. **`ITC-23.FW-error-provenance-sanitized` is**, and was missed: its registered test requires one framework-manufactured ERROR insight in the final response, which §2.2 removes with the legacy-only error surface, and it carries legacy partial-acceptance assertions besides. Its surviving rules — a model-authored `error` type rejects as `type_not_allowed`, and a forged `_origin` provenance claim is dropped at the boundary — are preserved as typed diagnostic and forgery tests; only the error-card and partial-acceptance assertions go.

**Retire is not the same as delete the behaviour.** Several of these state a rule that still holds for the surviving path but is worded as a contrast between the two regimes — for example, that an unknown type is rejected rather than silently relabelled. Where the rule survives, it is **restated without the contrast and re-registered under its existing id**, keeping its test. Where the rule existed only because two regimes did, it is retired outright. The spec's build must classify each of the nine explicitly and say which of the two it is; a retirement that silently drops a live rule is the failure this section exists to prevent.

Twelve further entries use the word "legacy" without depending on the path; their statements are reworded and their ids and tests are untouched.

The debt ratchet (`debt_baseline`) must not grow. Registry count moves from 89 by however many of the nine are retired outright.

## 7. Test plan

1. **The contract gate, strict.** `tools/check_contracts.py --strict` against the JUnit report: G1 bijection, G2 no silent skips, G3 ran-and-passed. Full coverage is the release gate.
2. **The surviving path is unchanged.** Every typed test passes untouched. A test that had to be *edited* to keep passing is a signal that typed behaviour moved, which §4 forbids — each such edit is justified in the commit message or reverted.
3. **Negative controls**, per `docs/PROCESS.md`: for each retired-but-restated contract, the inverse case that must fail. Specifically, a schema with no `typed_adapter` must be refused at registration and the refusal must name it; an unknown type must still reject without relabelling.
4. **Construction fails loudly.** `AgentEngine(insight_contract="legacy_v2")` raises, and the test asserts it rather than asserting silence.
5. **Probes.** `tests/qa_probes/` are permanent hard gates: never deleted, never `xfail`-ed, per `docs/PROCESS.md`. Round 1 (F3) rejected an earlier clause here that allowed retiring a probe whose defect had become structurally impossible — that is not this spec's to grant, and a probe's value is precisely that it outlives the reasoning which says it cannot fire. Every probe keeps its identity and its regression assertions, rewritten against the typed path where it drove the legacy one. If a probe genuinely cannot be expressed after this change, that is a finding to raise, not a deletion to make, and it would need its own amendment to `PROCESS.md`.
6. **Wheel smoke.** `tools/wheel_smoke.py` against the built artifact.

## 8. Risks

- **A live rule retired by accident** (§6). Mitigated by requiring each of the nine to be classified explicitly, and by the negative controls in §7.3.
- **Typed behaviour drifting under cover of a deletion.** Mitigated by §4 and by §7.2: an edited typed test is a red flag, not a routine consequence.
- **A schema in the wild with no `typed_adapter`.** It stops registering. This is intended and is the point of §5's loud failure, but it is a real break and the CHANGELOG must say so in those words.

## 9. Not a goal

Reducing line count. The measure of this change is that one regime governs insight validation, not that a number went down. A deletion that leaves the surviving path harder to reason about has failed even if it removes more lines.

## 10. Review chain

- **Round 1** — CHANGES_REQUIRED: 3 majors, 1 minor.
  - **F1** — deleting `custom1.json` would not break an agent configured for it: `_load_schema` falls back to `default.json` for any missing file, so the agent would silently register under a different envelope. The single most valuable finding of the round, and the same fallback behaviour that had already caused a mis-specified rule elsewhere. §2.4 now requires an explicit rejection before the fallback, scoped to that one identifier.
  - **F2** — the inventory named `INV-19-reasoning-config-explicit`, which is about `reasoning_effort` and unrelated (a false positive of the text sweep), and omitted `ITC-23.FW-error-provenance-sanitized`, whose test requires the framework-manufactured ERROR insight that §2.2 removes. Both corrected in §6.
  - **F3** — §7 allowed retiring a probe whose defect had become structurally impossible, contradicting `PROCESS.md`, under which probes are permanent. The exception is gone.
  - **F4** — §2.5 promised a rename in §6 that §6 never specified and §4 excluded. The names stay.
- **Round 2** — CHANGES_REQUIRED, the same four. Not a disagreement: the patch applying them aborted on a mismatched anchor before writing, so the reviewer read the unchanged file. Recorded rather than quietly re-rolled, because a round that reports "nothing changed" is evidence about the process, not noise.
- **Round 3** — **APPROVED**, 0 findings.
