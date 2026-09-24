# SPEC — Provider projection alignment: per-run field availability, list-valued queues, exact citations

**Version:** 1.1 · 2026-09-24 · **Status:** DRAFT — spec review round 2 pending. Round 1: CHANGES_REQUIRED (F1, F2 major), both addressed in 1.1.
**Kind:** a focused, compatible repair of the per-run provider projection and the generated instructions (XUBB-ITC-1 §13.3). **Behaviour base:** v3.1.6 (`ebcf994`). On `main` (3.2.0) the modules this change touches are identical to 3.1.6 except `library/dynamic.py`, where 3.2.0 added the unknown-key warning stage; this change does not touch that code.

## 1. Problem

The per-run structured-output projection offers the model fields and value shapes that local validation always rejects for that run, and the generated instructions do not say where the conditional fields are forbidden. A strict provider therefore accepts, and the engine then rejects, responses that the run could never have had accepted. A downstream host's rehearsal, with production prompts and current models, observed rejections concentrated in exactly these classes:

| Diagnostic | Local rule (`core/insight_validation.py`) | Why the provider allowed it |
|---|---|---|
| `invalid_field` · `insight.validation_step` · `only_for_hypothesis` | `validation_step` only when `observation_kind` is `hypothesis` | the projection strips the candidate's `allOf` conditionals, so `validation_step` is `string \| null` on every type |
| `invalid_field` · `insight.observation_kind` · `subtype_on_non_observation` | `observation_kind` only on type `observation` | same stripping |
| `capability_unavailable` · `insight.observation_kind` · `consulting_profile_required` | `observation_kind` needs the consulting analysis profile | the projection never receives the analysis profile |
| `invalid_question_contract` · payload on a non-question | the `question` payload only on type `question` | same stripping (the contract's rule 6) |
| `invalid_domain_payload` · `queue_pushes.<name>` | every queue's value is a list | `queue_pushes` is projected as a generic map whose values may be any JSON value |
| `unknown_reference` | an evidence reference matches an exposed id exactly | the instructions ask the model to cite the ids shown, but not to copy them exactly; some models shorten `snap:<snapshot>:segment:<n>` |

Prompts that use the contract's field names as ordinary words ("implication", "validation step", "question") trigger the first four classes. They are a trigger, not the cause: the engine owns the output contract, so the engine is where a field's availability must be stated and, where the provider subset allows, enforced.

## 2. Mechanism at the current code

- `core/provider_schema.py`: `LOCAL_ONLY` includes `allOf`, `if`, `then`, `else` and `description`; `project()` drops them from the candidate. `compile_schema(full, content_extension, allowed_types, channels)` restricts the type enum and the channels, and has no analysis-profile input.
- `library/dynamic.py`, the json_schema branch of the call: `compile_schema(...)` is called with the effective types and the format's channels, and without the analysis profile.
- `library/dynamic.py`, the generated rules: for a consulting run the text says what each observation kind needs, not where the observation fields are forbidden; no run is told that the question payload is null outside a question.
- `library/contract/provider_response_contract.json`: `queue_pushes` is `map_entries_v1` with `json_value` values; local validation requires a list for each queue.
- `core/insight_validation.py`: references resolve by the exact `(kind, ref_id)` key against the invocation's reference context; the citation rule in `library/dynamic.py` says "cite the ids shown in [brackets] … never invent an id".

## 3. Changes

### 3.1 Field availability per run

For one run with effective types **T** and analysis profile **P**:

- the **observation fields** (`observation_kind`, `validation_step`) are *available* iff P is `consulting` and `observation` ∈ T;
- the **question payload** is available iff `question` ∈ T; the **correction payload** iff `correction` ∈ T.

`compile_schema` gains a keyword `analysis_profile: Optional[str] = None`.

- **`analysis_profile=None`** keeps today's generic projection, byte-identical: `compile_schema(full=True)` still equals the packaged `provider_agent_response.schema.json`.
- **With a profile** (the DynamicAgent always passes the run's effective profile), the candidate projection is specialised:
  - (a) an *unavailable* conditional field keeps its property, still required, with the schema `{"type": "null"}`;
  - (b) if no conditional field is available, the candidate is one closed object, as today, with (a) applied;
  - (c) if any conditional field is available, the candidate is an `anyOf` of closed branches, one per allowed shape. Each type t ∈ T gets one branch with type enum `[t]`, its own payload required and non-null (the question object for `question`, the correction object for `correction`), and every other conditional field null. When the observation fields are available, `observation` gets three branches instead of one: `observation_kind` null with `validation_step` null; `"implication"` with `validation_step` null; `"hypothesis"` with `validation_step` a non-null string;
  - (d) constraints outside the conservative subset (`minLength`, `pattern`, `minItems`) stay local-only, as today;
  - (e) every specialised projection passes `schema_issues`;
  - (f) **per-run superset:** every response that local validation accepts for this run remains representable in the run's specialised projection.

No `if`/`then`/`else` keyword is restored: the provider subset does not carry them, and `anyOf` of closed objects is already part of the subset the engine emits.

### 3.2 Instructions

The generated rules state the placement of every conditional field the run's projection exposes, in every structured-output mode (`strict`, `auto`, `json_object`), because `json_object` sends no schema:

- observation fields unavailable: "`observation_kind` and `validation_step` must be null.";
- observation fields available: "`observation_kind` is only for an observation, and is null on every other type. A hypothesis needs evidence_refs, a rationale and a validation_step; an implication needs evidence_refs and a rationale. validation_step is null unless the type is observation and observation_kind is hypothesis, so it is also null on an observation whose observation_kind is null. A check or pilot you recommend belongs in the content of a suggestion, not in validation_step.";
- `question` ∉ T: "`question` must be null."; `question` ∈ T: "`question` is null unless the type is question."; the same two forms for `correction`.

No rule tells the model to omit a field that the strict projection requires.

### 3.3 List-valued queues

The descriptor entry for `queue_pushes` gains a value-shape marker, `"map_value": "array"`. When a profile is given, `compile_schema` projects a channel so marked as a `map_entries_v1` map whose entry values are `{"type": "array", "items": {"$ref": "#/$defs/json_value"}}`. The codec is unchanged, decoding yields lists, and local validation is unchanged and still rejects a non-list. The other map channels (`variable_updates`, `memory_updates`, and the candidate's `metadata`) are unchanged: arbitrary values there stay arbitrary.

Because `json_object` sends no schema and the generated output-format example shows `queue_pushes` as `{}`, the generated rules also say, whenever the format offers `queue_pushes`: "Each queue in queue_pushes holds a list of items, for example {\"queue_name\": [\"item\"]}." The output-format example itself is unchanged.

### 3.4 Exact citations

The citation rule becomes: "Copy each id exactly as shown in the brackets, including its `snap:` prefix. A shortened or reconstructed id does not resolve, and the insight is rejected." Resolution is unchanged: exact match only, no prefix matching, no aliasing, no search of the wider transcript, no nearest-looking source. Engine-issued short aliases are out of scope here; they would be a separately bounded follow-up, if exact copying proves insufficient.

## 4. Non-goals

- Local validation is unchanged and authoritative. Nothing drops offending fields, coerces values, or relaxes an evidence or authorization check.
- The normalized contract, its version, `SCHEMA_VERSION` and the generic packaged projection are unchanged.
- No model change, no new type or capability, no alias resolution, no restoration of field descriptions, and no change to arbitration, acceptance statuses or diagnostic codes.

## 5. Compatibility and release

- Per run, the projection removes only shapes that local validation always rejects for that run (§3.1 (f)). A response that was accepted before is still producible.
- The instruction text and the wire schema change, so a host that digests prompts or schemas sees new digests. That is a new treatment, by design.
- The release line is the maintainer's choice. **Recommendation:** a **3.1.7** patch cut from `v3.1.6`, carrying only this change, for hosts pinned to 3.1.x; and the same change on `main` for **3.2.1**. The change applies to the same code on both lines.
- **Endpoint acceptance gates the tag (§13.3 and the G2 gate: "codec/local tests plus actual endpoint acceptance").** Offline completion (the suite, the contract and documentation gates) is not enablement evidence, because local lint and codec tests do not prove that a live endpoint accepts a generated schema, and an invalid-schema failure does not downgrade. A maintainer-run tool, `tools/check_provider_acceptance.py`, compiles a representative set of specialised projections and sends each, as a strict `response_format` with a minimal silence prompt, to named endpoint/model pairs. The set covers: general with `observation` ∈ T; consulting with `observation` ∈ T (the `anyOf` branches); `question` and `correction` ∈ T; with and without the content extension; every map channel, including the list-valued queue. For each pair and schema it records the schema's digest (sha256 of canonical JSON), whether the request was accepted, and whether the returned envelope validates against the schema it sent. It reads the key from the environment and never prints it. The release is not tagged until the check passes for the models the pinned hosts run, which the release PR names, with the report attached. A host's own rerun is additional evidence, not a substitute.

## 6. Acceptance criteria

Each item names rule-asserting tests. Each test carries a negative control, shown to fail against the unchanged code before the change lands.

1. **Specialisation.** For P = general with `observation` ∈ T, the observation fields are null-only. For P = consulting with `observation` ∈ T, the candidate is the `anyOf` of §3.1 (c). `question` and `correction` are null-only when absent from T, and required in their own branch when present. The default call still equals the packaged projection. Every projection passes the lint.
2. **Conformance,** using `jsonschema` (a dev dependency) against the specialised projection.
   - Rejected: a suggestion carrying `observation_kind: "implication"`; an observation carrying an observation kind under P = general; a suggestion carrying a `validation_step`; an implication carrying a `validation_step`; an observation whose `observation_kind` is null carrying a `validation_step`; a suggestion carrying a `question` payload; a queue whose value is a string.
   - Accepted: a consulting hypothesis observation with a `validation_step`; a suggestion with both observation fields null; a queue whose value is a list.
3. **Per-run superset.** Every packaged valid example whose shape is allowed for a run's (T, P) validates against that run's specialised projection.
4. **The real path,** through `DynamicAgent` and the engine with a fake provider.
   - The request's `response_format` carries the specialised schema for the agent's profile and effective types.
   - An envelope with a list-valued queue decodes and is accepted.
   - The invalid shapes of item 2, including the null-kind observation carrying a `validation_step`, returned by a provider that ignores the schema (`json_object`), are still rejected by local validation with the same codes as today.
5. **Instructions.** The generated rules carry the placement lines of §3.2 for each case, including that `validation_step` is null on an observation whose `observation_kind` is null; the queue line of §3.3 when the format offers `queue_pushes`; and the exact-copy citation rule of §3.4. No rule instructs omitting a required field.
6. **Probe.** A `tests/qa_probes/` probe records this escaped defect, driving the engine end to end.
7. **Endpoint acceptance tool.** `tools/check_provider_acceptance.py` exists and is tested offline, with a fake client: it compiles the representative set of §5, computes stable digests, and classifies accepted, rejected and schema-invalid responses. Running it against live endpoints is the maintainer's release step (§5); it is not part of the offline suite.
8. **Registry and gates.** `docs/CONTRACTS.yaml` entries for items 1–5, node-level. The suite, `tools/check_contracts.py --strict` and `tools/check_api_docs.py` all green. A `CHANGELOG.md` entry.

Predicted acceptance improvements are hypotheses until a host measures them in a fresh run.

## Reviewer notes

*(none yet)*
