# Changelog

All notable changes to the Xubb Agents Framework are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> Short codes like `F-1`, `WC-1`, or `INV-15` are spec item / invariant IDs — they trace an
> entry back to its section in the specs under [docs/](docs/) and to the contract registry
> ([docs/CONTRACTS.yaml](docs/CONTRACTS.yaml)).

---

## [Unreleased]

### Added — typed reach (docs/SPEC_V2_8_TYPED_REACH.md; contracts TYPED-ADAPTER-FLAT-V1,
TYPED-ADAPTER-ROOT-V2-SIDECAR, TYPED-UNSUPPORTED-SCHEMA-NAMED, EVIDENCE-COORDINATES-AND-CITATIONS,
ISOLATED-INSTRUCTION-RESULT-ONLY, URGENCY-PROVENANCE, CONTENT-RESULT-AFTER-RELEASE,
CORRECTABLE-TARGETS, DATA-BY-AGENT; INV-49…INV-55)

- **Every shipped schema either registers under `typed_v1` or says why not (TA-1…TA-3).**
  `default` gains the `flat_v1` typed adapter (candidate at the root plus its
  `memory_updates` channel); `ui_control` and `widget_control` gain `root_v2` with the
  sidecar — the state block is named by the mapping's `variable_updates_field`, the
  `ui_actions` block and its rule by the descriptor's new `sidecar_instruction`; the
  silence-only envelope of a sidecar-bearing schema keeps the sidecar (a widget
  controller may act without speaking). `custom1` stays legacy-only and fails typed
  registration with its `typed_unsupported_reason` and the six adapters named; declaring
  `typed_v1` without a `typed_adapter` is now a registration error. Legacy instructions
  and parse paths are byte-identical.
- **Evidence coordinates and citations on demand (EC-1).** Framework-built segment
  entries carry `source_index` (the position in the `recent_segments` list the host
  passed, before trimming) and the segment's `timestamp`; accepted segment references are
  stamped with `EvidenceRef.source_index` (engine-owned: a model- or producer-authored
  value rejects). `HostInsightCapabilities.evidence_citations=True` exposes the citation
  markers, the reference contract and the citable host ids on every typed run.
- **Result-only instruction on the isolated path (IC-1).** An isolated content task's
  prompt offers the insight envelope only — no domain channels, no sidecar, no
  scratchpad section — and says so; live turns are unchanged.
- **`AgentInsight.urgency_provided` (UP-1).** Engine-owned and staged like
  `confidence_provided`: true only for a valid explicit urgency; false for the agent
  default, the per-type fallback and unknown provenance; `None` on legacy emissions.
- **`await handle.result()` returns after the slot is released (CS-1).**
  `ContentTaskHandle.released` is the same point as an awaitable; a refused handle is
  released already. A host sequencing replacement can admit the next task the moment
  `result()` returns.
- **`PriorInsightRecord.correctable` (CT-1).** Host-set, default true; false removes the
  record from the offered targets and rejects a correction naming it
  (`target_not_correctable`); answers still validate against it.
- **`AgentResponse.data_by_agent` (DS-1).** Aggregated responses attribute each committed
  sidecar to its agent (copies); the merged `data` keeps its v2.7 shape.
- The clean-wheel smoke now also registers a `default`-schema agent under `typed_v1` and
  checks a widget sidecar's attribution from the installed wheel.

### Migration notes (unreleased)

Additive. New nullable keys — `AgentInsight.urgency_provided`, `EvidenceRef.source_index`,
`EvidenceCatalogEntry.source_index` / `timestamp`, `AgentResponse.data_by_agent`,
`HostInsightCapabilities.evidence_citations` (default off), `PriorInsightRecord.correctable`
(default true), `ContentTaskHandle.released` — none in `model_dump_legacy()`. Typed
prompts differ for `root_v2` schemas with a sidecar, on the isolated path, and when
`evidence_citations` is on; legacy prompts do not change. A typed batch containing
`default`, `ui_control` or `widget_control` agents now registers; one containing
`custom1` still fails, now by name.

## [2.7.0] - 2026-09-07

The insight contract (XUBB-ITC-1 1.2.0, gates G0–G3, C1, C2) and the three hardening
increments (H1–H3) driven by the independent audits of `e3dfaf1` and `0f3cc32`.
Cut from a green main: 884 tests, contract gate 79/79 strict, clean-wheel smoke.

**Verification reported per layer.** *Framework:* every framework-scope leaf is
implemented, registered and tested; the audited defects are closed and the audit's
regression suite runs verbatim in the suite. *Distribution:* the installed wheel is
exercised outside the checkout by CI. *Provider:* live acceptance of the generated
structured-output schema is **not** claimed. *Host / end-to-end:* every `.HOST` /
`.E2E` leaf still needs a version-identified conformance run; **none is claimed**.

### Migration notes (2.6 → 2.7)

The public API is additive and the legacy wire shape is preserved
(`AgentInsight.model_dump_legacy()`), but four behaviours tightened for existing
consumers on the default `legacy_v2` contract:

1. **Unknown insight types are rejected, never relabelled** (G0, D-LR). An agent whose
   schema emits a type outside the legacy five now produces a `partial` result
   (valid channels commit, insights dropped, diagnostics attached) instead of a
   coerced insight.
2. **Retained interactive records need a principal** (H1). A `PriorInsightRecord`
   without `principal_id` no longer matches any current principal for answers or
   corrections; hosts must record the principal on question/correction records.
3. **Content-policy numerics are strict** (H2). `"1000"` or `true` in a content profile
   or host limit fails at load time (`AgentConfigurationError`) instead of coercing.
4. **Framework ERROR cards** keep their legacy surface but are sanitized categories
   (never exception text); under `typed_v1` they are diagnostics only.

Everything under `typed_v1`, evidence, replies/questions/corrections, provider
structured outputs and long-form content is new in this release. Increment-by-increment
detail follows.


### Fixed — H3: two residual boundary cases (reassessment of `0f3cc32`)

- **Isolated content views carry validated answers only.** `start_content_request`
  now runs the same answer validator as the live turn (this session, open question,
  present matching principal) on the frozen view before the per-agent visibility
  filter; invalid events surface as diagnostics on the `ContentResult`. Previously an
  invalid answer for the agent's own question could reach an isolated prompt.
- **Negotiated limits are re-applied at final acceptance.** Staging hands the effective
  `long_form_v1` ceilings (body chars, preview chars, formats) to the engine with the
  other content values; the boundary re-checks the body, preview and format of the
  object that would commit. A finish callback can no longer grow an accepted body past
  the frozen policy. Contracts: CONTENT-VIEW-ANSWERS-VALIDATED, NEGOTIATED-LIMITS-AT-BOUNDARY
  (INV-47/48).

### Fixed — H2: content path and assurance (independent audit of `e3dfaf1`, findings XA-04/05/06/08)

- **Admission at the content entrypoint (XA-04).** `start_content_request` now refuses,
  before any snapshot copy, clone, task or model call: a non-typed engine
  (`typed_contract_required`), a non-isolatable agent, an agent without a content
  contract (`agent_has_no_content_contract`), and any request the negotiated policy
  rejects for THIS request (host capability, schema support, depth, execution
  declaration — evaluated through the agent's pure `content_admission` on a shallow
  view). A refusal is an immediate rejected `ContentResult` on a task-less handle.
- **Task lifecycle (XA-05).** Capacity is reserved synchronously at the entrypoint and
  released by the task's done-callback on every exit — completion, rejection,
  exception, cancellation while running, cancellation before the coroutine first ran.
  Completed handles leave the pending registry; their results stay readable; session
  closure revokes pending tasks only. The semaphore is gone; the bound is an explicit
  counter, described accurately: it limits content-task concurrency and reserves no
  live-provider capacity.
- **Prompt derived from the enabled contract (XA-06).** The forbidden-field rule is
  generated from the same effective descriptor as the requested fields, so a long-form
  run never forbids `preview` / `content_format` it just asked for. Citation markers,
  the evidence-reference contract and the host's citable ids are exposed whenever an
  enabled type needs an evidence basis — a permitted `correction` in the general
  profile included — so a general-profile DynamicAgent can now actually produce an
  acceptable correction (previously unreachable).
- **Strict primitives (XA-08).** `ContentProfile`, `AgentContentConfig.max_preview_chars`
  and the host's `max_content_chars` / `max_preview_chars` are strict at construction:
  `"1000"`, `True` and non-finite numbers are rejected through the real configuration
  path (`AgentConfigurationError`), never coerced.
- **Distribution evidence.** New CI job `wheel-smoke` builds the wheel, installs it into a
  fresh venv and runs `tools/wheel_smoke.py` from outside the checkout (typed live turn,
  custom-agent rejection, packaged artifacts, admitted content task). The script refuses
  a source-tree import unless explicitly allowed.
- The audit's regression file is adopted verbatim as
  `tests/test_audit_e3dfaf1_regressions.py` (assertions unchanged; 19/19 pass).
  Contracts: CONTENT-ENTRYPOINT-ADMISSION, CONTENT-TASK-LIFECYCLE,
  PROMPT-FIELDS-FROM-CONTRACT, CONTENT-CONFIG-STRICT-PRIMITIVES, DISTRIBUTION-CLEAN-WHEEL
  (INV-42…46).
- One existing G3 test narrowed its assertion: the correctable-messages listing still
  names own earlier messages only, while the new citable-evidence line may list other
  agents' insights as a BASIS (evidence, not correction authority).

### Fixed — H1: enforcement and identity (independent audit of `e3dfaf1`, findings XA-01/02/03/07)

The audit found that the strongest guarantees held on the DynamicAgent path but not
uniformly across every supported producer. H1 closes the four high-priority findings;
nothing in the design or the type vocabulary changes.

- **One acceptance pipeline for every producer (XA-01).** The engine boundary now re-runs
  the strict candidate validator on the producer-controlled projection of every insight —
  custom `BaseAgent` subclasses, DynamicAgent staging and callback-modified responses
  alike — so a `question` without its payload, a hypothesis without evidence, an empty
  body, a non-finite confidence, an unsupported urgency, an engine-owned key in metadata
  or an un-negotiated content field rejects the whole typed response whichever class
  produced it. Engine-owned public fields (`id`, `turn`, `contract_version`,
  `confidence_provided`, `content_contract`, `response_depth`, `content_request_id`,
  `source_snapshot_id`) can never be producer-set: trusted staging hands its
  runtime-derived values to the engine privately and the engine stamps them after
  validation. Reference authority comes from the invocation — host records plus the
  run's own snapshot held by the agent — never from a snapshot attached to the response.
- **Domain channels are revalidated on the object that commits (XA-01).** In both
  contracts the boundary shape-checks `events`, `variable_updates`, `queue_pushes`,
  `facts` (including confidence), `memory_updates`, `state_updates` and `data`, with
  reserved `sys.*` writes. A fatal domain error rejects the whole response; D-LR legacy
  partial acceptance for recoverable insight errors is preserved; typed atomicity holds.
- **Answer visibility is scoped on the invocation view (XA-02).** The engine builds a
  per-agent context whose `insight_answers` contain only the answers to that agent's
  own questions (or all, when the host authorised sharing) — for the live phases and for
  isolated content tasks — so the rule holds through direct access, template aliases
  of the full context and custom agents, not just the prompt shortcut.
- **Interactive operations require a present, matching principal (XA-03).** Answers are
  accepted only when the current principal is present and equals both the question's
  and the answer's principal; correction targets only when the current principal is
  present and equals the record's; correction capability, like reply and question, is
  unavailable without a principal (`missing_principal`). Missing identity is never a
  wildcard.
- **Typed failures are diagnostics only (XA-07).** An evaluation exception under
  `typed_v1` yields `invalid_envelope` / `agent_error:<ExceptionType>` and no insight;
  the sanitized ERROR card remains a `legacy_v2`-only surface.
- Contracts: BOUNDARY-UNIFIED-ACCEPTANCE, ANSWER-VISIBILITY-SCOPED,
  INTERACTIVE-PRINCIPAL-IDENTITY, TYPED-FAILURES-ARE-DIAGNOSTICS (INV-38…41). The
  audit's own regression file passes its 14 H1-scope cases unmodified; the 5 remaining
  cases are H2 scope.
- Behaviour change to note: a `PriorInsightRecord` without `principal_id` no longer
  matches any current principal for answers or corrections; hosts must record the
  principal on interactive records.

### Added — C2: isolated active-session extended generation (XUBB-ITC-1 §14.6.1, §14.9; DL-6)

The last contract gate. Extended content during an ACTIVE session now has a real
execution path instead of a refusal.

- **`AgentEngine.start_content_request(context, agent_id, request) → ContentTaskHandle`**
  runs one extended generation as its own task: a fresh agent instance cloned from its
  definition (custom `BaseAgent` instances are refused as shared mutable state), a frozen
  deep copy of the context (transcript, Blackboard snapshot, capabilities, references),
  and an **engine-issued** isolated declaration. A host-authored isolated declaration is
  still refused (`isolated_path_requires_engine_task`): a boolean never substitutes for
  the runtime.
- **Isolation by construction.** The task never enters the live turn path, never writes
  the live Blackboard or private memory, never bumps the live turn counter, never
  reserves correction targets, and fires no turn callbacks (no trace contamination).
  Live turns proceed concurrently on the same engine.
- **Result-only.** `ContentResult` carries the request id, the source snapshot id, the
  snapshot turn, status (`accepted | silent | rejected | cancelled`), the single insight
  (stamped with both ids), diagnostics and usage. Proposed domain effects, sidecars or
  interactive types reject the result; the host checks currentness against the snapshot
  before presenting it.
- **Bounded admission.** `content_limits.max_concurrent_content_tasks` (default 1);
  exhaustion rejects immediately (`provider_admission_exhausted`) rather than queueing.
  The bound limits content-task concurrency only; it does not reserve live-provider
  capacity for the live turn.
- **Closure.** `handle.cancel()` or `AgentEngine.close_session_content(session_id)`
  revokes publication: a cancelled or late result reports `cancelled` with usage and
  diagnostics retained and nothing published.
- Contract: CONTENT-ISOLATED-PATH (roadmap INV-37), with real concurrency tests.

### Added — C1: the long-form content contract `long_form_v1` (XUBB-ITC-1 §14.4–§14.10)

Under `typed_v1` an agent may opt into extended content. Type describes purpose, never
length; the default `legacy_v2` path is unchanged.

- **Negotiation.** `insight_config.content` (`AgentContentConfig`: contract, default
  depth, formats, preview limit, per-depth profiles with character cap, output-token cap
  and per-request timeout) + host `content_contracts` / `content_formats` /
  `expanded_reading` / limits + a schema adapter declaring the contract (`insight_v1`) +
  `AgentEngine(content_limits={...})` with a finite `max_response_bytes` and the live
  ceilings. A content block on a legacy engine or unsupporting schema fails registration;
  an unsupporting host rejects before any call.
- **Depth and admission before generation** (`core/content_contract.py`, the reference
  policy verbatim). Effective depth is the host's `insight_content_requests[agent]` or the
  agent's default. Admission runs against the host's trusted
  `AgentContext.content_execution_context`: in an active session only `brief` within the
  operator's live ceilings; `standard` / `detailed` need a declared pause or post-session
  execution; the isolated active path is refused until C2; no declaration →
  `invalid_content_execution_context`. FORCE is neither authorization nor isolation. The
  admitted profile's `max_output_tokens` and `llm_timeout_seconds` become the call budget.
- **Body, preview, limits, completion.** The complete body is `content`; `preview` is
  an optional plain-text entry point under the same id; limits are decoded code points
  (most restrictive of profile, host, operator) plus a UTF-8 byte ceiling on the transport
  body (`LLMResult.raw_bytes`); exactly the limit passes, one over rejects with nothing
  shortened. Only a complete generation (finish_reason `stop`) may emit; `length` is
  `incomplete_generation`, unreported is `completion_unknown`, model metadata cannot
  assert completeness. Rejections are atomic; a preview never salvages a body.
- **Output.** Negotiated insights carry `preview`, `content_format`,
  `content_contract="long_form_v1"`, `response_depth`, `content_request_id`,
  `source_snapshot_id`; non-negotiated output and `model_dump_legacy()` omit them. The
  generated instruction states the depth objective, limits, preview fidelity and formats;
  the provider projection includes the extension fields only when negotiated.
- Contracts: CONTENT-POLICY-DERIVATION (62 packaged fixtures reproduce),
  ITC-26/27/28/29/30/33/35 `.FW`. Reading retention, safe rendering and
  expand-without-generation (ITC-31/32/34) are host conformance runs; isolated
  active-session generation is C2.

### Added — G3 part 2: the correction lifecycle (XUBB-ITC-1 §10)

The last interactive purpose becomes available under `typed_v1`; all nine purposes are
now implemented on the typed path.

- **CORRECTION** needs `allow_correction`, membership, host `corrections` and a retained
  history snapshot this run (`insight_reference_context.prior_insights`; otherwise
  `capability_unavailable` / `missing_history`).
- **Target validation at the engine boundary** (DynamicAgent and custom agents alike):
  the target must be a previously emitted human-facing insight from an earlier turn, in
  this session, still `active`, for the same principal; same-turn and cross-session
  targets are deferred (rejected). Authority is own-agent output unless the host's
  `correction_agent_policy="allowlisted"` names the agent in `correction_agent_ids`;
  nothing in the payload or metadata widens it. A separate evidence basis is required
  and must resolve. Violations reject the whole response; a failed correction never
  becomes another card.
- **Whole-response arbitration at phase close** (`_arbitrate_corrections`), before
  anything from the phase commits: correction-bearing responses are ordered by
  descending priority then later registration (never arrival); a response is accepted
  only when all its targets are unreserved and reserves them together; otherwise it is
  rejected whole with `correction_conflict` (no sibling insight, state, event, memory or
  sidecar commits; one callback). Duplicate targets in one response reject it. Earlier-
  phase reservations stand; reservations reset each turn.
- The generated instruction lists the agent's own correctable earlier messages and the
  self-repair rule.
- Contracts: ITC-18.FW, ITC-20.FW. Host delivery (ITC-19 and the `.HOST` leaves) is a
  conformance run, not claimed. Deadline closure of the arbitration set arrives with the
  delivery workstream.

### Added — G3 part 1: reply drafts and correlated questions (XUBB-ITC-1 §9, §11)

Two of the three interactive purposes become available under `typed_v1`, each behind
its permission intersection. The correction lifecycle is G3 part 2.

- **REPLY** is emitted as a draft when `allow_reply` + `reply` in `allowed_types` +
  host `reply_drafts` + an explicit `principal_id` all hold; anything less is
  `type_not_allowed` / `capability_unavailable`. The engine invokes nothing for a draft;
  the generated instruction states the draft rule and the no-invented-commitments rule.
- **QUESTION** needs `allow_question` + membership + host `text_questions` + principal +
  a `question.reason`; the engine-assigned insight id is the answer correlation key.
- **Answer channel.** `AgentContext.insight_answers` (`InsightAnswer`: event id,
  question id, principal, `answered` with text or `dismissed` without) is validated
  once per turn against the retained question records (same session, active, same
  principal); invalid events are dropped with engine diagnostics; duplicate or
  conflicting event ids within a batch reject. Validated answers reach only the
  originating agent — an `[ANSWERS FROM THE PRINCIPAL]` prompt section and
  `{{ insight_answers }}` — unless the host sets `HostInsightCapabilities.answers_shared`.
  A dismissal is presented as not an answer and not consent. Answers are data: they
  change no permission or identity, and receiving one schedules nothing.
- Contracts: ITC-17.FW, ITC-21.FW, ITC-22.FW. Host leaves (draft distinction, input
  UI, open/closed tracking, durable idempotency) are conformance runs, not claimed.

### Added — G2 part 2: provider structured outputs (XUBB-ITC-1 §13.3, SO-1)

Typed runs on the `insight_v1` schema can now ask the provider to enforce the
contract on the wire. Local validation is unchanged and still mandatory.

- **`AgentEngine(structured_outputs="strict" | "auto" | "json_object")`** (default
  `auto`), an independent transport control passed to the `LLMClient` and preserved
  across key rotation (EN-1/INV-18). `fallback_signatures=[...]` lets an operator enable
  evidence-backed downgrade signatures; the shipped registry
  (`library/contract/provider_capability_registry.json`) enables none.
- **Derived provider projection** (`core/provider_schema.py`): compiled per run from the
  shipped authoritative contract, restricted to the effective type set, closed objects,
  every property required, optionals nullable, content-extension keys omitted until
  negotiated; linted before any call (a failing schema is `provider_schema_error`, no
  call made). Equals the packaged projections.
- **`map_entries_v1` codec** for open-ended dictionaries in the full domain envelope
  (`metadata`, `variable_updates`, `queue_pushes`, `memory_updates`, `state_updates`,
  `data`, fact values, event payloads); decoded losslessly before local validation; a
  malformed encoding is a fatal `invalid_domain_payload`.
- **Wire (INV-24).** A strict request carries `response_format.type == "json_schema"`,
  `strict: true` and the effective enum; `json_object` mode never sends a schema.
- **Fail-closed fallback (A2-4).** `strict` never downgrades. `auto` downgrades once per
  capability key (endpoint, model, adapter, adapter version, schema version) only on a
  400 the adapter classifies as unsupported-capability for the `json_schema` feature
  that exactly matches an enabled signature with an evidence id; recorded on the client
  and reported as an `unsupported_structured_output` diagnostic. Otherwise the response
  is rejected with that diagnostic. Message text never matches.
- **Refusals** are their own `refusal` category (billed, not malformed, never evidence
  of unsupported schemas).
- Typed adapters declare `supported_transports`: `insight_v1` supports `json_schema`;
  `default_v2` / `v2_raw` stay on `json_object`. `strict` with a `json_object`-only
  adapter fails at registration.
- Contracts: PROVIDER-SCHEMA-DERIVATION, MAP-ENTRIES-CODEC, STRUCTURED-OUTPUT-FALLBACK.
  Contract artifacts ship in `xubb_agents/library/contract/` (package-data added).
  **Not claimed:** live provider acceptance of the generated schema (integration test).

### Added — G2 part 1: per-agent snapshot evidence catalog (XUBB-ITC-1 §6.3–§6.4)

Under `typed_v1` evidence references now resolve, which unlocks consulting hypotheses
and implications. The `legacy_v2` path is unchanged.

- **Framework-built snapshot catalog.** For every typed invocation, after context
  trimming, the agent's exposed transcript window and RAG documents become catalog
  entries `snap:<id>:segment:<n>` / `snap:<id>:document:<n>` (one per occurrence,
  never deduplicated; sources copied). The snapshot id is the invocation's execution
  id; it is not a durable identity across windows.
- **Host reference context.** `AgentContext.insight_reference_context`
  (`InsightReferenceContext`: `evidence` catalog entries, `prior_insights` records)
  joins the catalog for the session; frozen per run and propagated through both
  phases. Entries owned by another session resolve to `cross_session_reference`.
- **Resolution rules.** A reference resolves only to a catalog entry at its revision:
  a null revision resolves to the current one and is filled on the emitted insight;
  a stated revision must match exactly; anything nothing exposed is
  `unknown_reference`. Hypotheses need evidence + rationale + validation step;
  implications need evidence + rationale; general observations need nothing.
- **Citation contract in the prompt** (consulting profile only): transcript lines and
  documents carry their reference ids in brackets, the instruction states the
  reference shape and lists host-supplied ids, and asks the model never to invent one.
- **Retention aid.** `AgentResponse.evidence_snapshot` (per agent) and
  `evidence_snapshots_by_agent` (aggregate) return the immutable invocation view so a
  host that wants durable cross-turn references can retain it.
- Contracts: ITC-15.FW, ITC-16.FW registered; ITC-14.FW amended.

### Added — G1 part 2: typed acceptance, `insight_contract="typed_v1"` (XUBB-ITC-1 §6, §8, §13; D-CR)

`typed_v1` is now selectable. The default `legacy_v2` path is unchanged.

- **Strict local validation of the normalized candidate** (`core/insight_validation.py`,
  `validate_typed_candidate`): exact wire-value types in the run's effective set;
  unknown keys and every engine-owned key (`id`, `turn`, `contract_version`,
  `confidence_provided`, `acceptance_status`, `source_snapshot_id`, …) rejected at the
  root and in `metadata`; strict confidence input; urgency precedence (explicit →
  `default_urgency` → per-type fallback, invalid explicit rejects); consulting subtype
  rules; interactive payload shapes; content-extension fields rejected until negotiated.
  Agreement with the packaged JSON Schema is pinned on all 71 shape fixtures.
- **Typed atomicity (§8.4).** A malformed or inconsistent gate, any invalid candidate,
  or an invalid domain payload rejects the whole agent response; usage and diagnostics
  survive; valid silence still commits. One `on_insight_validation_error` per result.
- **Engine-minted identity.** Accepted typed insights get a session-unique `id`, the
  host's `turn`, `contract_version="typed_v1"`, a resolved `urgency`, and runtime-derived
  `confidence_provided` (omitted/null → placeholder `1.0` + `false`; a custom agent that
  did not declare provenance → `false`). Producers cannot supply identity.
- **D-CR ranking helpers.** `rank_key` / `rank_candidates` use
  `(urgency_order, -agent_priority, stable_merge_order)` and ignore confidence for every
  candidate; the engine stamps `merge_order = (phase, agent index, ordinal)` on merged
  insights. No ranking stage is applied yet (LC-3 roadmap).
- **Generated typed instruction (§13.1).** Under `typed_v1` the model is sent an exact
  allowed-value instruction built from the effective set; the schema's static legacy
  enum is not sent; an empty set yields a silence-only envelope.
- **Typed adapters and schema.** New `insight_v1` schema (typed-only normalized
  envelope). `default_v2` (`flat_v2` adapter) and `v2_raw` (`root_v2` adapter) declare
  `typed_v1`; other schemas fail registration under `typed_v1`, and `insight_v1` fails
  under `legacy_v2`. Descriptors gain `typed_adapter`, `typed_supported_insight_types`,
  `supported_insight_fields`.
- **Availability in this release.** Typed acceptance implements the six ordinary
  purposes. `reply`, `correction` and `question` remain unavailable
  (`not_implemented_in_this_release`) until G3; evidence references are unresolvable
  (`unknown_reference`) until the per-agent catalog lands at G2, so consulting
  subtypes cannot yet be emitted; `preview`/`content_format` reject until C1.
- **`AgentInsight` typed fields** (all default/None on legacy emissions): `id`, `turn`,
  `contract_version`, `urgency`, `confidence_provided`, `observation_kind`,
  `evidence_refs`, `rationale`, `validation_step`, `assumptions`, `correction`,
  `question`; `model_dump_legacy()` projects the v2.6 wire shape; `merge_order` property.
- Eight contracts registered: ITC-03/07/08/09/10/11/12 `.FW`, TYPED-SCHEMA-DERIVATION;
  INSIGHT-CONTRACT-SELECTION amended. Package fixtures (manifest-verified) under
  `tests/fixtures/insight_contract_1.2.0/`; `jsonschema` added to the dev extras.

### Added — G1 part 1: vocabulary, alias, contract selection (XUBB-ITC-1 §3–§4, §7)

Inert on the wire: no behaviour of the default `legacy_v2` path changes.

- **`InsightType` gains the nine-purpose vocabulary.** New members `OBSERVATION`,
  `REPLY`, `CORRECTION`, `QUESTION`; `INFORMATION` is an alias of `FACT` (same member,
  wire value stays `"fact"`, `.name` stays `"FACT"`, no `@unique`). `HUMAN_INSIGHT_TYPES`
  is the canonical nine-tuple type-offering code must use; `INSIGHT_TYPE_LABELS` is the
  explicit display map. On the legacy path the four new values remain
  `type_not_allowed` (G0) — the enum members exist; the capabilities do not yet.
- **`AgentEngine(insight_contract="legacy_v2" | "typed_v1")`.** Default `legacy_v2`.
  `typed_v1` **fails closed** with `AgentConfigurationError` until typed acceptance
  lands (G1 part 2); any other value is a `ValueError`.
- **Per-agent `insight_config`** (`allowed_types`, `allow_reply` / `allow_question` /
  `allow_correction`, `analysis_profile`, `default_urgency`), typed with `extra="forbid"`;
  `allowed_types=[]` is state-only. Malformed blocks fail `DynamicAgent` construction;
  a flag/membership contradiction fails `register_agent` / `replace_agents` before any
  mutation (all-or-nothing, VL-1 pattern). Also accepted on `AgentConfig` for custom agents.
- **Trusted host inputs on `AgentContext`:** `principal_id` and `insight_capabilities`
  (`HostInsightCapabilities`, safe defaults: the five legacy values, all interactive
  capabilities off). Frozen per run and propagated through Phase 1 and Phase 2 copies.
- **`AgentEngine.effective_insight_types(agent, context)`** — the §7.2 intersection
  (framework ∩ agent ∩ schema ∩ host ∩ permission prerequisites) with a reason for every
  absent value. Under `legacy_v2` it returns the host-safe five; typed enforcement uses
  it at G1 part 2.
- Five contracts registered: ITC-01.FW, ITC-02.FW, ITC-14.FW, INSIGHT-CONTRACT-SELECTION,
  INSIGHT-CONFIG-LOAD-TIME.

### Changed — G0 legacy safety (XUBB-ITC-1 §8, FINAL_DECISIONS D-LR)

The insight contract's first dependency gate. Applies on the default `legacy_v2`
path to every agent; `typed_v1` (whole-response atomic rejection, the nine-purpose
vocabulary) lands at G1. Behavioural edges, all deliberate:

- **Gates are declared, never truthiness.** A Boolean gate speaks only on an actual
  `true`; `"true"`, `"false"`, `1`, `null` and a *missing* required gate are
  `invalid_gate` (the result never speaks; the malformed gate is reported).
  Presence-gated schemas (`v2_raw`, `ui_control`, `widget_control`) reject a
  non-object root instead of treating it as empty. `custom1` declares a
  `content_presence` gate. Each shipped schema now carries a versioned `descriptor`
  (`gate_mode`, `supported_insight_types`, `supported_contracts`).
- **Unknown insight types are rejected, never relabelled.** The parser no longer maps
  an unrecognised type to `SUGGESTION`. An unknown label is `unknown_type`; `error`
  and the future wire values `observation` / `reply` / `correction` / `question` are
  `type_not_allowed` on the legacy path. Case-folding (`"WARNING"`) and the absent-type
  default (`suggestion`) remain as declared legacy normalisations.
- **Legacy partial acceptance (D-LR).** A recoverable insight error rejects all
  insights from that result but commits its independently validated, authorized
  domain channels with an explicit `partial` status; action-bearing `data` sidecars
  are withheld. Invalid domain payloads (e.g. `"facts": "none"`), agent-proposed
  `sys.*` writes (`reserved_state_write`) and unparseable envelopes reject the whole
  response. Previously malformed channels were silently ignored and `sys.*` writes
  warned-and-applied (INV-4 amended: host writes still warn; agent writes reject).
- **No parse-time durable mutation.** `DynamicAgent` never touches `private_state`
  while parsing; memory becomes durable only through the engine merge (INV-14 sync).
  Hosts that evaluated agents outside an engine and relied on in-process
  `private_state` accumulation must run turns through `AgentEngine`.
- **Framework ERROR insights are sanitized.** Content is the category `agent_error`
  plus the exception class name in metadata; the exception text is only in the
  non-serializing `debug_info`. Provenance is runtime-established: an agent-authored
  `ERROR` insight is dropped at the engine boundary.

### Added — G0

- `AgentResponse.acceptance_status` (`accepted | accepted_silent | partial | rejected`),
  `AgentResponse.diagnostics` (sanitized `InsightDiagnostic` rows: execution id, agent,
  code, field path, bounded classification, retained/withheld channels),
  `AgentResponse.execution_id`, and `acceptance_by_agent` on the aggregated turn response.
- `AgentCallbackHandler.on_insight_validation_error(issue)` — fired by the engine exactly
  once per partial/rejected execution result.
- `core/insight_validation.py` — pure gate / type / domain-channel validators and the
  D-LR decision table, reused by `DynamicAgent` and the engine boundary check.
- `StructuredLogTracer` steps carry `acceptance` and `diagnostics`.
- Docs: the packaged reference artifacts (local/provider JSON schemas, response
  contract, fallback-signature registry, host-kit procedure, provenance, manifest)
  under `docs/reference/insight_types_1.2.0/`, alongside the contract documents merged
  in PR #22; the live-assistance roadmap `docs/SPEC_V3_LIVE_ASSISTANCE.md` with its
  item-level cross-reference to the contract. Six new framework contracts
  (ITC-04/05/06/13/23/24 `.FW`) registered and INV-4 amended; host and end-to-end
  leaves are not claimed.

### Changed

- **`src/` layout.** The package moved from repo-root to `src/xubb_agents/`; `pip install -e .`
  and `pytest` now work from a checkout with **any** directory name (previously the checkout
  had to be named `xubb_agents` or test collection failed). Wheels additionally ship a
  `py.typed` marker, and packaging metadata migrated to PEP 639.
- The all-or-nothing bulk-reload rejection message now reads
  `Agent reload rejected (...)` (was `Vault reload rejected (...)`).

### Added

- Community files for public contribution: `CODE_OF_CONDUCT.md`, issue forms
  (bug/feature), a fork-based contribution flow in `CONTRIBUTING.md`, and a CI matrix
  over Python 3.11–3.13.

### Fixed

- **Post-2.6.0 documentation sweep** — six stale spots the release DOC items
  didn't enumerate: `EXECUTIVE_SUMMARY.md` still said 2.4.0 (×2) and only named
  gpt-4o-era models; `technical_spec_agents.md` header said 2.4.0; the docs
  index still called SPEC_V2_2 "the current release spec"; PLAYBOOK Gate 3
  quoted the pre-OB-2 `evaluate()` call verbatim; the prompt guide's
  reliability checklist recommended "gpt-4o for complex reasoning" (now
  actively misleading — deep lane = reasoning model + explicit effort +
  budgets); README gained a "What's New in v2.5 / v2.6" section above the v2.2
  one.

---

## [2.6.0] - 2026-07-13

Per-agent reasoning configuration (Release B of `docs/SPEC_LLM_MODERN_MODELS.md`).
Additive config surface + **one deliberate load-time edge** (see Breaking below).
The two-lane pattern is now first-class: fast whisper agents pin effort off;
deep analysis agents opt into reasoning with validated budgets.

### Added

- **Per-agent LLM-call config on `AgentConfig` / `model_config`** (RC-1/RC-3,
  INV-15): `reasoning_effort`, `timeout`, `max_tokens` — forwarded by
  `DynamicAgent` **only when set** (the framework never injects a parameter the
  operator didn't write; omission leaves the model's own default; strict-
  signature fakes and downstream test doubles stay compatible). On custom `BaseAgent`
  subclasses the fields are a *declaration* consumed by validation — the
  subclass owns forwarding them into its own calls (PLAYBOOK snippet).
- **`model_config.model_params`** (RC-2): verbatim Chat-Completions passthrough
  for parameters the framework doesn't model (e.g. `verbosity`). Framework-owned
  keys (`model`, `messages`, `response_format`, both token-cap spellings,
  `timeout`, `reasoning_effort`) are rejected at load with
  `AgentConfigurationError`; the call-site merge is defensive regardless
  (framework keys always win). Documented as wire-shaped, not transport-portable.
- **Load-time validation at registration** (VL-1, INV-19): an ADVISORY
  model-name heuristic (payload-advisory — provably never alters outbound
  kwargs) drives warn-once signals: effort on a non-reasoning shape, deep
  effort with starved budgets (`timeout <= 10s` / `max_tokens < 4096` — billed
  timeouts/truncation), `temperature`/`top_p` on reasoning models.
- **`AgentEngine` LLM knobs** (EN-1, INV-18): `llm_timeout`, `llm_max_retries`,
  `llm_max_tokens`, `llm_base_url` (OpenAI-compatible endpoints, first-class),
  `llm_wire_max_tokens_param`, `strict_reasoning_config`. The resolved set is
  stored and **reused by `update_api_key`** — key rotation no longer silently
  resets the client to module defaults (previously it rebuilt bare).
- **`xubb_agents.AgentConfigurationError`** — the load-time config failure type.

### Breaking (deliberate, per spec D-1 ruling)

- **A model matching the reasoning heuristic without an explicit
  `reasoning_effort` now hard-fails registration** with a copy-pasteable fix
  (the API default — often `medium` — silently blows the real-time envelope
  and multiplies cost). One config field per affected agent. Escape hatch:
  `AgentEngine(strict_reasoning_config=False)` downgrades to a warning.
  `replace_agents` is all-or-nothing: one bad config rejects the whole bulk
  reload and the old registry keeps serving.

### Migration (hosts)

- Audit your agent configs before upgrading: every agent on a `gpt-5*` / `o1|o3|o4*`
  model needs `model_config.reasoning_effort` (`"none"` for 5.1+/5.6 mainline,
  `"minimal"` for the original gpt-5 family, `"low"` for o-series). Effort
  value validity is per-model; a wrong pair surfaces as `misconfig`.
- Recommended lanes: fast = gpt-5.4-nano + `"none"` (or gpt-5-nano +
  `"minimal"`); standard = gpt-5.4-mini / gpt-5.6-luna + `"none"`; deep
  (opt-in) = gpt-5.6-terra/sol + `low`–`high` + `timeout >= 30` +
  `max_tokens >= 25000`.
- Hosts that relied on `update_api_key` resetting LLM settings (unlikely;
  previously a bug) must now set them explicitly.

---

## [2.5.0] - 2026-07-13

Modern-model wire compatibility + observability (Release A of
`docs/SPEC_LLM_MODERN_MODELS.md`). Inert on the OpenAI-wire and
`generate_json`-return surfaces for every working config (one deliberate
deviation noted below); reasoning *configuration* (per-agent `reasoning_effort`
etc.) lands in 2.6.0.

### Added

- **`LLMClient.generate() -> LLMResult`** (OB-2, INV-17): per-call result object
  (`parsed`, `error_category`, `usage`, `finish_reason`) — attribution-safe under
  concurrent agents on the shared client, where the old `last_error_category`
  attribute can only report the last writer (it remains as a deprecated
  best-effort mirror with a single write site). `generate_json` is now a thin
  delegate; its dict-or-`None` never-raise contract is unchanged.
- **Token-usage telemetry** (OB-2): plain-int usage (`prompt_tokens`,
  `completion_tokens`, plus `reasoning_tokens`/`cached_tokens` when reported)
  flattened from the SDK response — populated even on billed failures
  (`truncated`/`malformed`). Surfaced on the new first-class
  **`AgentResponse.usage`** field (additive, default `None`; `debug_info` is
  `exclude=True` and never serializes) and in `debug_info["usage"]` for the tracer.
  `DynamicAgent` duck-types the client (`generate()` when present,
  `generate_json` fallback), so `generate_json`-only fakes and downstream
  test doubles keep working unmodified.
- **Error categories `misconfig` and `truncated`** (OB-1, INV-16): a 4xx
  parameter/model rejection is `misconfig` (an operator problem — previously
  miscategorized as `server`, paging the outage runbook); a length-stopped
  response (`finish_reason="length"` — the starved-reasoning signature) is
  `truncated` (previously masqueraded as `malformed`). Missing/non-int
  status_code falls to `server`. Contracts:
  `INV-16-error-taxonomy-misconfig-truncated`, `INV-17-per-call-attribution`.
- **`LLMClient(wire_max_tokens_param=...)`** (WC-1): legacy opt-out for old
  OpenAI-compatible proxies (`"max_tokens"`); ctor-validated.

### Changed

- **The token cap ships on the wire as `max_completion_tokens`** (WC-1) — the
  successor kwarg, required by reasoning models (gpt-5.x, o-series) and accepted
  by current non-reasoning models. The Python parameter name (`max_tokens`)
  does not change anywhere. Old configs keep working; reasoning models stop
  400-ing on the framework's requests.
- **openai SDK floor raised to `>=1.60.0`** — older SDKs TypeError on the new
  kwarg, and the never-raise wrapper would swallow every call into
  `category=unknown` (silent agent death).
- **Deliberate deviation:** a length-stopped response whose partial content
  happens to parse now returns `None` (`truncated`) instead of the parsed
  fragment — a truncated JSON object is not a trustworthy whisper.

### Fixed

- **`ui_control.json` violated JSON mode's precondition** (QW-1): its
  instruction never contained the word "json", so
  `response_format={"type":"json_object"}` 400s for any agent whose own prompt
  doesn't contain it. Reworded; a drift-lock test (globbed over
  `library/schemas/*.json`) pins every shipped schema.
- **`user_context` created a blank prompt section** (QW-3): the section carried
  a trailing `"\n\n"` and the joiner added another — exactly the D1
  blank-section bloat the sweep exists to catch; its fixture just never set
  `user_context`. Now covered both ways.
- **Default model hardcoded in two places** (QW-2): now a single framework
  constant `xubb_agents.DEFAULT_MODEL` (value unchanged: `gpt-4o-mini`;
  changing the value is a separate, eval-gated decision).
- `docs/prompt_engineering_guide.md` wrongly said the transcript is sent as
  separate user/assistant messages; it is one `### TRANSCRIPT:` user message.

### Fixed (carried from post-2.4.0 unreleased)

- **Contract-gate CI was red** (so the "every contract is CI-gated" claim was fragile).
  The repo root *is* the `xubb_agents` package, and pytest names it after the checkout
  directory; GitHub's default `xubb-agents` (hyphen) checkout is not a valid module name,
  so collection failed with "attempted relative import with no known parent package".
  CI now checks out into `xubb_agents` (`actions/checkout` `path:` + a job
  `working-directory`); the dir-name requirement is documented in CONTRIBUTING and the
  pytest config. Local `git clone` + `pytest` needs the same dir name.
- `tools/debugger.html`: fixed a malformed tag — a stylesheet `<link>` was closed with
  `</script>` (introduced with the SRI pinning).
- `SECURITY.md` supported-versions table still listed `2.3.x` after the 2.4.0 bump;
  corrected to `2.4.x`. Also dropped a stale "(v2.3+)" qualifier from a spec heading.

---

## [2.4.0] - 2026-07-05

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
- Moved the README table of contents to the top and expanded it to cover all major
  sections (anchors verified).

### Removed

- `docs/PUBLIC_RELEASE_READINESS.md` — an internal pre-launch audit artifact, not
  documentation for the public tree.

### Fixed

- **`register_agent` now mutates the registry lock-safely.** It appended/assigned in
  place while `replace_agents` (called from the host's config-reload thread) rebinds
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
- **`StructuredLogTracer` privacy documented.** Its docstring now warns that the trace
  includes full transcript history / shared state / raw agent output (potential PII) and
  is emitted at INFO — attach it behind a dedicated, access-controlled logger rather than
  general INFO aggregation. "Production-ready" warranty wording dropped.
- **`tools/debugger.html` CDN assets pinned + SRI.** Vue and Font Awesome are now
  version-pinned with `integrity` hashes; Tailwind (play CDN) is documented as
  unhashable and dev-only.

---

## [2.3.0] - 2026-07-04

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

Production-hardening release driven by the v2.2 comprehensive audit: 1 critical contract bug,
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

[Unreleased]: https://github.com/genriq/xubb-agents/compare/v2.7.0...HEAD
[2.7.0]: https://github.com/genriq/xubb-agents/compare/v2.6.0...v2.7.0
[2.6.0]: https://github.com/genriq/xubb-agents/compare/v2.5.0...v2.6.0
[2.5.0]: https://github.com/genriq/xubb-agents/compare/v2.4.0...v2.5.0
[2.4.0]: https://github.com/genriq/xubb-agents/compare/v2.3.0...v2.4.0
[2.3.0]: https://github.com/genriq/xubb-agents/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/genriq/xubb-agents/releases/tag/v2.2.0
[2.1.1]: https://github.com/genriq/xubb-agents/blob/main/CHANGELOG.md
[2.1.0]: https://github.com/genriq/xubb-agents/blob/main/CHANGELOG.md
[2.0.0]: https://github.com/genriq/xubb-agents/blob/main/CHANGELOG.md
[1.0.0]: https://github.com/genriq/xubb-agents/blob/main/CHANGELOG.md
