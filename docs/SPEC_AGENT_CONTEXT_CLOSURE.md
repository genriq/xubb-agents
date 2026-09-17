# SPEC — Closing `AgentContext` to unknown keys

- **Status:** APPROVED — **3.2.0 warning stage SHIPPED** (PR #57, released as 3.2.0, tagged `v3.2.0` at `98b65b6`). The **4.0.0 refusal stage remains to build**: both specs land it in the same release, alongside the deprecated-format removal and `output_format` becoming required.
- **Reviewed by Codex —** APPROVED round 1 (0 blockers, 0 majors, 3 minors), and re-reviewed after fixing them: round 2 APPROVED with one new minor (a stale paragraph in §6 still describing the phase path the way §4 had just stopped describing it), round 3 APPROVED clean, 0 findings. All four findings fixed; nothing contested.
- **Target releases:** **3.2.0** (warn) and **4.0.0** (refuse). Both numbers published by 3.2.0.
- **Baseline:** 3.1.6, commit `ebcf994ca496730e3ec288aa18287b724f9f6ebe`
- **Relates to:** `SPEC_CONFIG_KEY_OWNERSHIP.md` — the same rule, applied to the other input surface. That spec declares ownership for the keys of an *agent configuration*; this one declares it for the keys of a *run's context*. It supplies the staging precedent and this spec follows it deliberately.

## 1. Summary

`SPEC_CONFIG_KEY_OWNERSHIP` states the rule: every input block the engine reads is either **closed** (an unknown key is refused) or **open** (unknown keys are the caller's business and pass through untouched), and which one it is must be *declared* rather than left to whichever default a model happened to get.

That spec applied the rule to agent configuration. It did not reach `AgentContext`, and `AgentContext` is the surface where the same defect costs most, because it carries the capability and identity declarations that decide what an agent is allowed to do for the whole run.

Twenty input models in `core/models.py` refuse unknown keys today. `AgentContext` does not. A caller who misspells a context keyword gets a `AgentContext` that constructs cleanly, keeps the default for the field they meant to set, and runs — with a capability quietly withdrawn.

This spec closes it, on the same two-stage schedule the ownership spec uses: **warn in 3.2.0, refuse in 4.0.0**, both numbers published by 3.2.0.

## 2. Verified baseline

Probed against 3.1.6 `ebcf994`.

**The policy split.** Of the pydantic models exported from `core/models.py`, **20 declare `extra="forbid"`** — including every declaration a caller nests *inside* `AgentContext`:

> `AgentConfigOverride`, `AgentContentConfig`, `ContentExecutionContext`, `ContentProfile`, `ContentResult`, `CorrectionPayload`, `EvidenceCatalogEntry`, `EvidenceRef`, `EvidenceSnapshot`, `HostInsightCapabilities`, `HostWidgetCapabilities`, `InsightAnswer`, `InsightConfig`, `InsightContentRequest`, `InsightDiagnostic`, `InsightReferenceContext`, `PriorInsightRecord`, `QuestionPayload`, `WidgetActionDeclaration`, `WidgetDeclaration`

`AgentContext` itself carries only `ConfigDict(arbitrary_types_allowed=True)`, so it takes pydantic's default and **ignores** unknown keys. A caller is refused for `insight_capabilities={"supported_tpyes": [...]}` and accepted for `insight_capabilties={...}`. The inner model is stricter than the outer one that holds it.

**What the silence costs.** Two measured cases, each a single transposed letter:

| Construction | `AgentContext` result | Run result |
|---|---|---|
| `widget_capabilties=<declaration>` | accepted; `widget_capabilities` keeps its empty default | every UI action refused — `unauthorized_ui_action`, classification `no_widgets_declared`; agent **rejected** |
| `principl_id="…"` | accepted; `principal_id` stays `None` | reply, question and correction withdrawn for the run — `capability_unavailable` |

Both fail closed, which is correct. Neither says *why*. The caller declared a capability, the engine never saw the declaration, and the resulting refusal is indistinguishable from a caller who declared nothing — which is the one reading that is false.

**Why the diagnostic is not enough.** Both cases do surface per-agent as `rejected` with a diagnostic, so a caller reading `acceptance_by_agent` is not blind. But the diagnostic describes the *consequence* (an action was not authorized), not the *cause* (a keyword was misspelt), and the merged `acceptance_status` still reads `accepted`. Nothing in the engine's output distinguishes "declared nothing" from "declared it, spelt it wrong".

## 3. The rule

Unchanged from `SPEC_CONFIG_KEY_OWNERSHIP` §3, restated for this surface:

> Every input the engine accepts is either read, or declared foreign. There is no third category in which a value is accepted, silently discarded, and never mentioned again.

`AgentContext` is **closed**. Its fields are the engine's own vocabulary; there is no host-owned namespace inside it, and no caller has a legitimate reason to attach one. This is unlike the top level of an agent configuration, which stays open because it genuinely carries host fields (`type`, `description`) that are not the engine's business.

## 4. Detection, not enumeration

The allowed names are **derived from the model declaration**. There is no second, hand-written list of field names anywhere in the implementation or the tests.

This is the lesson of the 3.1.1 → 3.1.2 repair: the first fix enumerated the keys it policed, and the enumeration was the bug — a key nobody listed was a key nobody checked. A derived set cannot fall behind the model it describes.

Detection must run **before validation discards extras**, and must cover every supported public entry point that builds an `AgentContext` from caller data — the constructor, `model_validate` and `model_validate_json`.

`model_copy(update=…)` is a trusted internal operation, not a validation entry point, and is deliberately **not** covered. `model_copy` does not validate, so an unknown key in an `update` mapping stays unchecked at both stages; the engine uses it at `engine.py:1095` to derive a narrowed view from an already-validated context. External input is validated once, at the boundary where it enters. Its key and field propagation is tested directly (§6) rather than through the validation boundary.

Note what this means for the engine's own two-phase path: the second-phase context at `engine.py:998` is built through the **constructor**, with explicit keyword arguments, not through `model_copy` or `model_construct` — neither of which the engine calls to build a phase context. Closure therefore applies to the engine's internal construction as well, on every two-phase turn. That is intended: the engine passes real field names, and the internal path exercising the same rule as the external one is a guarantee, not a hazard.

## 5. Migration

**3.2.0 — warn.** An unknown key on `AgentContext` logs one warning naming the model, the key, the refusal target `4.0.0`, and the closest real field when one is close enough to be useful. Behaviour is otherwise **exactly** as it is at 3.1.6: the key is still ignored, the field the caller meant still keeps its default, and no value is repaired.

A hint is a hint. `principl_id` does not populate `principal_id`; `widget_capabilties` does not populate `widget_capabilities`. Repairing a misspelt key would guess at intent, and a guess here silently grants a capability the caller did not successfully declare — a strictly worse failure than the one this spec is fixing.

The warning is emitted once per unknown key per validation, through the engine's established warning mechanism, under its normal runtime configuration. Nested validation must not multiply it into duplicate notices for the same key. The supplied **value is never logged** and the context is never serialized into the message: this model carries principal identity and host capability declarations.

A construction-time warning is not an `AgentResponse` diagnostic. It concerns the caller's code, not the model's output, and it is raised before any agent runs.

**3.2.0 relaxes nothing.** Every input that raises at 3.1.6 still raises: malformed values for known fields, and unknown keys in the already-closed nested models, which continue to refuse exactly as they do today. The warning window is a grace period for behaviour this spec introduces — never a downgrade of behaviour that exists.

**4.0.0 — refuse.** `AgentContext` declares `extra="forbid"`. An unknown key fails validation, before any provider call, and the error names the offending field. `arbitrary_types_allowed=True` is preserved. `Blackboard` is itself a pydantic model and so does not depend on that setting; it is asserted separately (§6) because the setting is what keeps the model open to non-pydantic values, and closing the model must not quietly remove it.

| Input | 3.1.6 | 3.2.0 | 4.0.0 |
|---|---|---|---|
| unknown key on `AgentContext` | accepted, silent | accepted, **warns** | **raises** |
| unknown key in a nested declaration | raises | raises | raises |
| malformed value, known field | raises | raises | raises |
| correctly spelt fields | accepted | accepted, no new warning | accepted |

4.0.0 already removes the deprecated output formats and closes `model_config` / `trigger_config`. This joins that release deliberately, so an operator has **one** breaking release to plan for rather than two.

## 6. Test plan

Registered contracts, each with the negative control that must fail when the rule is removed:

| Rule | Test | Negative control |
|---|---|---|
| Unknown key warns at the warning stage, naming key and target | parametrized over both measured misspellings | remove detection; the warning must disappear and the test fail |
| A hint never repairs | `principl_id` → `principal_id` stays `None`; `widget_capabilties` → `widget_capabilities` stays empty | populate the nearest field; the test must fail |
| Allowed names are derived | add a field to `AgentContext`; no test or implementation list needs editing | hard-code a name list; the new field must be reported unknown and fail |
| Every public entry point is covered | constructor, `model_validate`, `model_validate_json` | cover only the constructor; the others must fail |
| One notice per key per validation | assert the count, with a context whose nested models also validate | remove deduplication; the count must exceed one |
| No value or context in the message | assert the supplied value is absent from the warning text | interpolate the value; the test must fail |
| The warning stage relaxes nothing | `insight_capabilities={"supported_tpyes": […]}` still **raises** at 3.2.0 | downgrade it to a warning; the test must fail |
| Closure refuses before any provider call | 4.0.0: unknown key raises; provider call count is zero | allow the run; the count must be non-zero |
| Closure preserves the trusted fields | `principal_id`, `insight_capabilities`, `widget_capabilities`, `insight_answers`, `insight_reference_context` all survive construction **and** the engine's internal phase copies | drop one in the copy; the test must fail |
| Closure preserves `Blackboard` acceptance | a `Blackboard` still constructs and reaches the agent | reject it; the test must fail |
| `arbitrary_types_allowed` stays enabled | assert the setting directly on `AgentContext.model_config` | remove the setting; the test must fail |

The phase row is the one to read twice, and §4 says why: the engine's second-phase context at `engine.py:998` is built through the **constructor**, so closure applies to it. The test must therefore drive `process_turn` through **both phases** and assert the trusted fields as the agents actually observe them in phase 2 — not merely that a context object can be constructed. A field that survives construction but is dropped on the way to the second phase is the failure this row exists to catch.

Separately, and not through the validation boundary: `model_copy(update=…)` at `engine.py:1095` is asserted directly for key and field propagation, because it does not validate at either stage.

## 7. Ownership

Engine. The change is to `core/models.py` and the warning path; no host code is required at either stage, and 3.2.0 is not a required intermediate installation for anyone. A caller that already validates its own keyword arguments before constructing an `AgentContext` will see no warnings and needs no change at 4.0.0 — a stricter caller-side guard is compatible with both stages and should not be weakened to produce warning traffic.

## 8. Not in scope

`AgentContext` is closed here. The rule requires the other surfaces to be *declared*, not necessarily closed in this spec, and the measurement above names them: among models a caller constructs, `Blackboard`, `TranscriptSegment`, `Event` and `Fact` also ignore unknown keys.

They are deliberately left on their current `extra="ignore"` behaviour for now, with a reason rather than by omission — and note that this is **not** *open* as §1 defines it. An open block passes unknown keys through untouched; `ignore` discards them. These models are neither closed nor open: they retain a legacy default, and their closure is deferred. Why: they are content models rather than capability declarations, a mistyped key in one of them does not withdraw a permission for the run, and `Event` and `Fact` are also produced by the engine and round-tripped, so closing them has a compatibility surface this spec has not measured. A later spec may close them; until then their disposition is *declared deferred*, which is a decision rather than an oversight, but it is not a claim that discarding a caller's key there is correct.

Reporting the cause of a refusal in the engine's output — so a run can distinguish "declared nothing" from "declared it, spelt it wrong" — is also out of scope. The warning stage addresses this at the caller's boundary, which is where the mistake is.

## 9. Risks

**A caller relying on the current tolerance.** A caller that deliberately attaches its own bookkeeping to `AgentContext` breaks at 4.0.0. This is the change's point, and the 3.2.0 warning window exists to find those callers before the break. The migration note must say plainly that attaching foreign keys to the context is no longer supported and name the alternative: keep that data in the caller's own structures, alongside the context rather than inside it.

**A warning nobody sees.** A warning emitted through a mechanism the caller has silenced buys nothing, and the failure then arrives at 4.0.0 with no notice. This is why the warning uses the engine's established mechanism under normal runtime configuration, and why the migration note, not the warning alone, carries the announcement.

## 10. Review chain

Three rounds, records in `.spec-review/SPEC_AGENT_CONTEXT_CLOSURE/`.

**Round 1 — APPROVED, 3 minors.** All three were factual corrections to how the spec described the code, and all three were reproduced against `ebcf994` before being fixed:

- **F1** — the spec said the engine derives phase contexts with `model_copy`/`model_construct`. It does not: `engine.py:998` uses the **constructor**, and the engine calls `model_construct` nowhere. This mattered beyond wording — it means closure applies to the engine's own internal phase construction on every two-phase turn, which §4 now states as a guarantee rather than leaving as an unexamined side effect.
- **F2** — "a `Blackboard` still passes" was offered as the control for removing `arbitrary_types_allowed`. `Blackboard` is itself a pydantic model (`blackboard.py:25`), so it would pass either way and the control could never fail. Split into two rows: `Blackboard` acceptance as a compatibility assertion, and the setting asserted directly.
- **F3** — §8 called the deferred models "declared open", contradicting §1's definition of open as *passing unknown keys through untouched*. `extra="ignore"` discards them. They are neither open nor closed; §8 now says so and calls the disposition *deferred*.

**Round 2 — APPROVED, 1 minor.** F1: §4 had been corrected but the paragraph under §6's table still described the old, wrong mechanism. Fixed, and strengthened per the reviewer's suggestion: the test must drive `process_turn` through **both phases** and assert the trusted fields as phase-2 agents observe them, rather than asserting that a context can be constructed.

**Round 3 — APPROVED, 0 findings.**
