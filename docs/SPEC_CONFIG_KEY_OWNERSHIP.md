# SPEC — Declared ownership for agent configuration keys

- **Status:** APPROVED — **3.2.0 warning stage SHIPPED** (PR #57, released as 3.2.0, tagged `v3.2.0` at `98b65b6`). The **4.0.0 refusal stage remains to build**: both specs land it in the same release, alongside the deprecated-format removal and `output_format` becoming required.
- **Reviewed by Codex —** APPROVED round 2 (round 1: one blocker, F1 — §7's "nothing is refused" contradicted §4, which listed three blocks that already refuse, so the same input had two dispositions. Fixed by scoping the warning window to the two newly closed blocks, stating that nothing which refuses today starts warning, and splitting the release matrix by block. Round 2 clean. Nothing contested.)
- **Target releases:** **3.2.0** (warn) and **4.0.0** (refuse). Both numbers published by 3.2.0.
- **Baseline:** 3.1.2, commit `88c85696c5f4687f0428788b9a09b071ea51f032`
- **Relates to:** `SPEC_OUTPUT_FORMAT_CONSOLIDATION.md` §9, §17.1 — this is the same defect class one layer out

## 1. Summary

Two rounds of post-implementation review of 3.1.x found the same defect each time: **a setting accepted at construction, silently discarded, never mentioned again.** Both rounds were repaired inside the output-format contract. The class is not confined to it.

`DynamicAgent` reads a fixed set of configuration keys and ignores everything else. For the top-level dictionary that is correct — hosts legitimately carry their own fields there. For `model_config` and `trigger_config`, which the engine owns outright, it is the same defect: an operator writes a setting, the engine drops it, and nothing says so.

This spec makes ownership **declared** rather than implied: every configuration block the engine reads is either *closed* (unknown key refused) or *open* (unknown keys are the host's business and pass through untouched). It also closes the sharpest single case — a misspelt `output_format` **key**, which today silently inherits the implicit default.

It does not police the host's catalogue, and it does not add a second list of "the keys that matter": §6 is explicit that a hand-maintained enumeration is what failed in 3.1.1.

## 2. Verified baseline

Probed against 3.1.2 `88c8569`, and measured against the maintained catalogue (105 records, SHA-256 begins `d25fad7d75389dc7`).

| Case | Today |
|---|---|
| `{"invented_top_level": …}` | **accepted silently** |
| `{"model_config": {"temperture": 0.9}}` | **accepted silently** |
| `{"trigger_config": {"keyord": "x"}}` | **accepted silently** |
| `{"output_fromat": "insight_v1"}` | **accepted silently** — the agent inherits the implicit default |
| `{"insight_config": {"allowed_tpyes": […]}}` | refused (pydantic `extra="forbid"`) |

`insight_config` is the one block already closed, and it shows the target behaviour exists and is liveable.

### 2.1 What the engine actually reads

| Block | Keys read |
|---|---|
| top level | `id`, `name`, `text`, `output_format`, `model`, `model_config`, `trigger_config`, `trigger_conditions`, `insight_config`, `mapping`, `descriptor`, `priority`, `include_context`, `context_turns` |
| `model_config` | `model`, `context_turns`, `reasoning_effort`, `timeout`, `max_tokens`, `model_params` |
| `trigger_config` | `mode`, `cooldown`, `keywords`, `silence_threshold`, `subscribed_events`, `trigger_interval`, `priority` |

### 2.2 What the catalogue supplies that the engine never reads

| Key | Records | Assessment |
|---|---|---|
| `type` (top level) | 105 / 105 | Host-owned. Legitimate. |
| `description` (top level) | 70 / 105 | Host-owned. Legitimate. |
| `model_config.output` | 43 / 105 | Host-owned data **inside an engine-owned block** (§5.2). Subkeys: `format` (39), `schema` (35), `target_widget` (2). |
| `model_config.temperature` | 16 / 105 | **A live defect.** See below. |
| `trigger_config.*` | 0 | No drift. Closing it is free today. |

**The `temperature` finding.** Sixteen agents carry `model_config.temperature`. The engine reads only `model_config.model_params`, so **that sampling temperature has never reached a model.** It is not a refused setting — `temperature` is not in `FRAMEWORK_OWNED_PARAMS`, and `model_params` exists precisely to pass it through. Someone configured a real behaviour, on sixteen agents, and got silence. This is the cost of the defect class stated concretely, and it is why warning is not enough on its own.

## 3. The rule

Every configuration block the engine reads carries a declared **ownership**:

- **closed** — the engine owns the namespace. A key it does not read is a configuration error, named, with the closest engine key offered as a hint.
- **open** — the namespace is shared with the host. Keys the engine does not read pass through untouched and are never inspected.

Declared, never inferred: a block's ownership is a property of the block, written down once, not deduced from what happens to be in it.

## 4. Closed blocks

Five blocks are closed. **Three already are, and this spec does not touch them**; two become closed here. The distinction decides what happens in 3.2.0 (§7), so it is drawn once, here, and every later section refers back to it.

| Block | Closed since | This spec |
|---|---|---|
| `insight_config` | 2.7 (pydantic `extra="forbid"`) | unchanged — **keeps refusing at 3.2.0** |
| `mapping` | 3.1.2 (`override_violations`) | unchanged — **keeps refusing at 3.2.0** |
| `descriptor` | 3.1.2 (`override_violations`) | unchanged — **keeps refusing at 3.2.0** |
| `model_config` | — | **newly closed**: warns in 3.2.0, refuses in 4.0.0 |
| `trigger_config` | — | **newly closed**: warns in 3.2.0, refuses in 4.0.0 |

Every other existing refusal is likewise untouched, including the `model_params` × `FRAMEWORK_OWNED_PARAMS` collision, which raises today and continues to raise at 3.2.0. **Nothing that refuses today starts warning instead.** The warning window of §7 is a grace period for behaviour this spec introduces, never a relaxation of behaviour that exists.

The value of writing the rule down is the last column: the next block added to the engine inherits a decision rather than an accident.

## 5. The open block, and the two things that live in it

### 5.1 The top level stays open

105 of 105 records carry `type` and 70 carry `description`. A host catalogue is not the engine's business, and a blanket refusal would reject every maintained configuration. The top level is **open** and stays open.

### 5.2 `model_config.output` is host data in an engine block

43 records carry it, with subkeys `format`, `schema` and `target_widget`. Closing `model_config` refuses it, so it moves — to the top level, which is open, or wherever the host prefers.

Worth naming while it moves: **`model_config.output.format` is a second output configuration, on 39 records, parallel to `output_format` on 12.** That is the two-sources-of-truth problem `SPEC_OUTPUT_FORMAT_CONSOLIDATION` just spent two releases ending, one layer up, and the engine cannot see it. The engine's only obligation here is to stop pretending the key is its own. Reconciling the host's copy is host work, flagged in §7 and out of scope for this spec (§10).

### 5.3 The misspelt key

An open top level means `output_fromat` is accepted and the agent inherits the implicit default. That is **F6's twin**: F6 was a typo in the *value* silently re-homing an agent into a different envelope, and only the value case was repaired.

The fix is not to police the open namespace. It is to remove the silence underneath it: **in 4.0.0, `output_format` becomes required** rather than defaulting to `insight_v1`.

This costs nothing that is not already owed. `SPEC_OUTPUT_FORMAT_CONSOLIDATION` §8.2 and the migration note already require every configuration to set `output_format` explicitly before 4.0.0; the migration tool already reports the 93 that do not. Making the key required at that release turns a misspelt key from silence into `output_format is required`, and the error names the closest unread top-level key as a hint when there is one. **This amends §8.2 of that spec**, which said the implicit default *changes to* `insight_v1` at 4.0.0; it is removed instead.

A hint is a hint: it appears in an error message and never selects behaviour.

## 6. Derivation, not enumeration

The 3.1.1 repair failed because it walked a hand-maintained list of "the structural keys" and everything outside the list kept the old behaviour. A list of read keys would fail the same way the first time someone adds a `model_config` field.

So the declared key set is **conformance-tested against the code that reads it**: a test parses `library/dynamic.py` for `model_conf.get(...)` and `trigger_conf.get(...)` and asserts the declared set equals the read set exactly, in both directions. Adding a read without declaring it, or declaring a key nothing reads, fails the build.

Where that parse cannot reach — a key read through a variable, say — the test fails loudly rather than skipping, and the reader is refactored or the exception is recorded in the declaration with its reason.

## 7. Migration

**3.2.0 — warn, for the two newly closed blocks only.** An unknown key in `model_config` or `trigger_config` logs a warning naming the agent, the block, the key, the closest engine key and the removal version. Nothing that refuses today changes: `insight_config`, `mapping`, `descriptor` and the `model_params` collision check all keep raising exactly as they do at 3.1.2 (§4). `output_format` keeps its implicit default. The migration tool reports unknown keys in the two newly closed blocks per agent, alongside the format work it already reports.

**4.0.0 — refuse.** `model_config` and `trigger_config` join the other three: an unknown key raises `AgentConfigurationError`. `output_format` becomes required. Both land in the release that already removes the deprecated format names, so an operator has one breaking release to plan for, not two.

So each input has exactly one disposition per release:

| Input | 3.1.2 | 3.2.0 | 4.0.0 |
|---|---|---|---|
| unknown key in `model_config` / `trigger_config` | accepted, silent | accepted, **warns** | **raises** |
| unknown key in `insight_config` / `mapping` / `descriptor` | raises | raises | raises |
| `model_params` × framework-owned collision | raises | raises | raises |
| unknown key at the top level | accepted, silent | accepted, silent | accepted, silent |
| `output_format` omitted | implicit default | implicit default | **raises** |

Concrete work for the maintained catalogue, all reportable by the tool:

| Change | Records |
|---|---|
| `model_config.temperature` → `model_config.model_params.temperature` — a real behaviour change: the value starts reaching the model | 16 |
| `model_config.output` → out of the engine's block | 43 |
| set `output_format` explicitly | 93 (already owed) |

The `temperature` move is the one to read twice. It is not cosmetic: sixteen agents begin sampling at a temperature they have never actually used, and their output will change. The migration note must say so in those words, and the operator should decide per agent whether the value was ever right — a setting nobody could observe is a setting nobody has tuned. For a reasoning-capable model the existing rule-4 warning then applies, because those models reject sampling parameters.

## 8. Test plan

Every changed behavioural contract gets a registry entry naming a rule-asserting test and its negative control. Everything through the real construction and registration path — the lesson of §17's R2, where every test poked an attribute instead.

The matrix is split by block **and** release, so no input has two expected dispositions. The disposition table in §7 is the specification; this is how each cell is asserted.

| Evidence | Passing condition |
|---|---|
| Newly closed blocks, 3.2.0 | An unknown key in `model_config` or `trigger_config` **constructs and registers**, and emits one warning naming agent, block, key, closest engine key and removal version. Parametrized per block. |
| Newly closed blocks, 4.0.0 | The same inputs raise `AgentConfigurationError` at construction, naming block, key and suggestion. Parametrized per block, asserted against the 4.0.0 behaviour switch. |
| Already-closed blocks, unchanged | An unknown key in `insight_config`, `mapping` or `descriptor` raises at **3.2.0** exactly as at 3.1.2. This is the regression guard for F1: the warning window must not relax an existing refusal. |
| Reserved collisions, unchanged | `model_params` carrying a `FRAMEWORK_OWNED_PARAMS` key raises at 3.2.0. |
| Open block passes through | `type`, `description` and an invented top-level key construct and register unchanged, at every release. The negative control for the refusals above: a rule that rejects everything is not a fix. |
| Declaration matches the code | The conformance parse of `dynamic.py` equals the declared key sets, both directions. Negative control: a declared-but-unread key fails it. |
| `output_format` required | At the 4.0.0 behaviour, an omitted key raises; `output_fromat` raises naming `output_format` and offering the unread key as a hint. Negative control: an explicit valid value registers, at every release. |
| Migration tool | Reports unknown keys in the two newly closed blocks per agent; `--write` leaves them alone (they need a person); the `temperature` move is reported as a behaviour change, not a rename. |
| Existing behaviour | Full suite, `--strict` gate, permanent probes, README quickstart, clean-wheel smoke. |

## 9. Ownership

- **Framework:** the ownership declaration, the conformance parse, the refusals and warnings, the `output_format` requirement, tool support, tests, registry.
- **Host:** moving `model_config.output` out of the engine's block, deciding the 16 `temperature` values, and reconciling `model_config.output.format` with `output_format` (§5.2) — which the engine cannot see and will not guess.
- **Documentation:** README configuration table, the authoring guide, the migration note, CHANGELOG.

## 10. Not in scope

- Policing or renaming host-owned keys. The top level stays open.
- Reconciling `model_config.output.format` with `output_format`. Named in §5.2 because it is worth knowing; it is host work.
- Any change to what the engine *does* with the keys it already reads.
- Live-provider certification. The `temperature` change alters real requests, and that is an integration concern, reported separately.

## 11. Risks

1. **59 records break at 4.0.0 if nobody migrates.** Mitigated by a full warning release, tool reporting, and landing in the breaking release the catalogue must already be prepared for.
2. **The `temperature` move changes model behaviour** on 16 agents, which is the point and also the hazard. Mitigated by reporting it as a behaviour change rather than a rename, so it is reviewed per agent rather than applied in bulk.
3. **The near-miss hint could mislead.** Mitigated by keeping it a hint in an error string; it never selects a key, a format or a behaviour.
4. **A future reader adds a `model_config` key and forgets the declaration.** That is the failure this spec is most likely to suffer, and §6 is the answer: the build fails, rather than the key quietly becoming refused.

## 12. Review chain

- Independent review: `spec-review` (Codex), rounds recorded in `docs/.spec-review/SPEC_CONFIG_KEY_OWNERSHIP/`.
- Implementation follows the repository's spec-first process: a registry entry with a rule-asserting test and a negative control for every changed contract; the gate green at `--strict`; permanent probes never skipped.
