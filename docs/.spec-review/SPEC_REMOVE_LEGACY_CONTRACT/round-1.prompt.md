You are an independent, skeptical technical reviewer. A different AI system wrote the specification below and will implement it if you approve. Your job is to find what would make that implementation fail, drift, or need rework — not to be agreeable.

## Verdict rules

- APPROVED only if there are zero blocker and zero major findings. Minor findings do not block approval.
- CHANGES_REQUIRED otherwise.
- Do not soften a blocker to major to be polite. Do not invent findings to look thorough. If the spec is good, approve it.

## Severity definitions

- blocker: implementation cannot start, or would produce the wrong thing. Examples: contradictory requirements, undefined core behaviour, missing acceptance criteria for the main flow, an assumption about an external system that is unverified and load-bearing.
- major: implementation can start but will very likely need rework. Examples: unhandled failure modes or edge cases on primary paths, ambiguous ownership of data or state, requirements that cannot be tested as written, scope that silently exceeds what the spec claims.
- minor: worth fixing, does not change what gets built. Wording, structure, nice-to-haves.

## What to check

1. Ambiguity: any requirement two competent engineers would implement differently.
2. Completeness: happy path, error paths, empty/first-run states, concurrency, migration or backwards-compatibility where relevant.
3. Testability: can each requirement be verified? Are acceptance criteria concrete?
4. Internal consistency: does any section contradict another, or the stated goals?
5. Unverified assumptions: dependencies on external systems, APIs, permissions, data availability, or vendor behaviour that the spec treats as given.
6. Scope honesty: does the spec do what it says, and only that? Flag hidden scope and flag gaps that are papered over rather than documented. A spec that explicitly lists a known gap as out of scope is fine; one that quietly ignores it is not.
7. Non-goals: are they stated, and do they actually rule out the tempting adjacent work?

## Conduct

- Read any context documents provided; judge the spec against them, not against generic best practice.
- Cite the section or line for every finding.
- One issue per finding. Do not bundle.
- In later rounds, reuse the same finding id for an issue that persists, list resolved ids in `resolved_from_previous_round`, and do not re-raise anything you previously accepted unless the spec changed in a way that reopens it.
- Do not modify any files. Do not run commands beyond reading files.
- Respond only with the JSON object matching the provided schema.

## Review round: 1

## Context document: PROCESS.md
```
# Quality Process

How this framework keeps its documented behavior true. Self-contained: everything
the registry, gate, and tests cite lives on this page.

## The problem this solves: the F-1 escape

The canonical failure mode of a documented system is a **contract with no
asserting test**: the docs promise a behavior, a test appears to cover it but
asserts only a happy path, and the behavior silently regresses. We call this an
F-1 escape, after the first defect that slipped through this way (a fact-precedence
rule that was documented, "tested," and wrong in production).

## The contract-accuracy gate

Every documented behavioral contract MUST have an entry in
[`CONTRACTS.yaml`](CONTRACTS.yaml) that names the test(s) asserting the RULE
(not just an example). [`tools/check_contracts.py`](../tools/check_contracts.py)
enforces it in CI:

- a `covered` contract whose named test is missing, skipped, or failing is a
  **red build**;
- test references must be **node-level** (`file::Class::test`), so a renamed test
  breaks loudly instead of rotting silently;
- honest debt (`to_verify`, `uncovered`, `pending`) is reported, and a **debt
  ratchet** (`debt_baseline`) fails the build if debt ever grows — it can shrink
  but never silently accrete;
- `--strict` requires a passing test for every entry: the full-coverage release
  gate.

The CI job and tooling refer to the gate's three checks by short names:

| Gate | Check |
|------|-------|
| **G1** | Registry ↔ test **bijection**: every `covered` contract names a test that exists at the node level (`file::Class::test`), so a renamed test breaks loudly instead of rotting silently. |
| **G2** | **No silent skips**: a named test that is missing or skipped hard-fails the gate — a collected-but-skipped test does not count as coverage. |
| **G3** | **Ran and passed**: the named test actually executed and passed in this build (verified against the JUnit report), and the **debt ratchet** holds (`--strict` is the full-coverage release gate). |

*(Definition note, 2026-08-19: an earlier revision of this table described G2 as `@pytest.mark.invariant` marker coverage — a check the gate never implemented. The table above matches `tools/check_contracts.py` exactly.)*

## Escaped-defect probes (`tests/qa_probes/`)

A defect that escapes to production earns a **probe**: a regression test that
drives the real engine end-to-end (not a unit in isolation), kept in
`tests/qa_probes/` as a permanent record of the escape. Probes are hard gates —
never deleted, never `xfail`-ed. PROBE-F1 (fact precedence) is the canonical
example.

## Negative controls

A test that can only pass proves nothing. Contract assertions carry their own
negative control: the inverse case that MUST fail (e.g., the gate's own tests
verify that a broken contract actually reds the build). If you cannot write the
failing case, you have not tested the rule.

## Rules for contributors

1. Document a behavior → register it in `CONTRACTS.yaml` with a rule-asserting
   test, in the same change.
2. Never weaken a `covered` entry to make a build pass; fix the code or amend
   the contract explicitly.
3. Fail closed: error paths in this framework return safe defaults and log,
   they do not guess (see `CONDITIONS-FAIL-CLOSED` for the archetype).
```

## Context document: SPEC_INSIGHT_TYPES.md
```
# Xubb Agents — Insight Types, Validation, and Long-form Content Contract

**Specification ID:** XUBB-ITC-1  
**Specification version:** 1.2.0  
**Supersedes:** specification packages 1.0.0 and 1.1.0; applies Amendment 2 and final decisions D-LR / D-CR  
**Status:** PROPOSED — not implemented in the reviewed runtime  
**Design date:** September 6, 2026  
**Repository adoption:** September 7, 2026  
**Baseline:** Xubb v2.6.0, commit `f83fc5b1e3d39da176be0ef30f40eefdd9fe51bc`  
**Audience:** Product, framework engineering, agent authors, host integrators, and QA

> Support nine human-facing insight purposes. Keep operational diagnostics separate. Preserve the existing `"fact"` wire value through an `INFORMATION` alias. Add consulting analysis through validated observation subtypes, not more top-level types. Support short and extended content through a negotiated, length-independent content contract.
>
> This is the repository-adapted design specification, not a runtime release or certification. The Amendment 2 record is [SPEC_INSIGHT_TYPES_AMENDMENT_2.md](SPEC_INSIGHT_TYPES_AMENDMENT_2.md); final decisions are [INSIGHT_TYPES_FINAL_DECISIONS.md](INSIGHT_TYPES_FINAL_DECISIONS.md). See [INSIGHT_TYPES_ADOPTION.md](INSIGHT_TYPES_ADOPTION.md) for provenance, reference-package scope, and the item-level roadmap cross-reference. The engineering team's reported uncommitted working tree was not inspected.

## Contents

1. [Objective and design decisions](#1-objective-and-design-decisions)
2. [Baseline and scope](#2-baseline-and-scope)
3. [Normative vocabulary](#3-normative-vocabulary)
4. [Enum and wire compatibility](#4-enum-and-wire-compatibility)
5. [Classification rules](#5-classification-rules)
6. [Typed payload and provenance](#6-typed-payload-and-provenance)
7. [Permissions and host capabilities](#7-permissions-and-host-capabilities)
8. [Parsing, validation, and atomicity](#8-parsing-validation-and-atomicity)
9. [Reply contract](#9-reply-contract)
10. [Correction contract](#10-correction-contract)
11. [Question and response contract](#11-question-and-response-contract)
12. [Consulting profile](#12-consulting-profile)
13. [Schema and prompt integration](#13-schema-and-prompt-integration)
14. [Host delivery, diagnostics, and long-form content](#14-host-delivery-diagnostics-and-long-form-content)
15. [Migration and implementation sequence](#15-migration-and-implementation-sequence)
16. [Contracts and acceptance tests](#16-contracts-and-acceptance-tests)
17. [Definition of done](#17-definition-of-done)
18. [Deferred concepts](#18-deferred-concepts)
19. [Sources and reference package](#19-sources-and-reference-package)

## 1. Objective and design decisions

### 1.1 Objective

Make the purpose of a human-facing agent message explicit, consistently validated, and independent of the host's presentation choices. Agents may inform, interpret, recommend, warn, identify opportunities, reinforce behavior, draft speech, repair earlier errors, or request necessary input without overloading another category.

The type identifies the message's **primary communicative purpose**. It does not identify a UI surface, authorize an action, establish truth, or grant priority over the human's attention.

### 1.2 Design decisions

| Decision | Required target behavior |
|---|---|
| Human-facing vocabulary | INFORMATION, OBSERVATION, SUGGESTION, WARNING, OPPORTUNITY, PRAISE, REPLY, CORRECTION, QUESTION |
| Information naming | INFORMATION aliases FACT; retain the `fact` wire value and canonical FACT name |
| Extracted knowledge | Keep the separate Fact model and response.facts; no automatic conversion to or from visible insights |
| Operational errors | ERROR is retained only for framework-manufactured legacy diagnostics, never model authorship |
| Consulting | Validated hypothesis and implication observation subtypes with supporting evidence |
| Reply, question, correction | Explicit agent permission plus the relevant host capability and references |
| Unknown classifications | Reject, never guess or relabel |
| Urgency | Valid explicit value, then configured agent override, then documented type fallback |
| Legacy rejection | Insight-only rejection for recoverable insight errors; independently validated and authorized domain channels may commit with partial status |
| Typed rejection | Any invalid insight candidate rejects the whole agent response |
| Confidence | Numeric public value plus runtime-derived provenance; missing estimates do not affect default ranking |
| Long responses | Purpose is length-independent; complete content is preserved separately from optional preview |
| Test ownership | Framework, host, and end-to-end coverage are distinct claims |

### 1.3 Normative language and terms

MUST/MUST NOT are requirements. SHOULD/SHOULD NOT are recommendations whose exceptions must be documented. MAY denotes an option. Illustrative examples are not claims about actual clients, model capability, or implemented behavior.

**Principal:** the host-identified human being assisted. **Counterpart:** another participant. **Candidate:** an agent's proposed message before engine acceptance. **Emitted:** accepted and returned through the supported delivery interface. **Shown:** a host-reported observation, not an inference from emission. **Grounding evidence:** references supporting a claim; distinct from Evaluation/replay evidence of product effectiveness.

## 2. Baseline and scope

### 2.1 Baseline

The reviewed runtime has six InsightType values, separate facts and insights channels, raw-value speech gating, unknown-type fallback to suggestion, and model metadata assigned after insight construction. Its schema instructions offer different subsets. The runtime is not changed by adding this document. Pinned source references appear in section 19.

### 2.2 In scope

Vocabulary, definitions, the compatibility alias, per-agent allowed types, host capability checks, candidate validation, mappings, provenance, minimal correction/input contracts, diagnostics, consulting analysis, long-form content requirements, migration, and acceptance criteria.

Identity and history are included to the extent required for honest support of corrections, replies, and questions. The specification defines the comparator used by the separate ranking workstream and the admission boundary for isolated content requests; it does not implement those runtimes.

### 2.3 Out of scope

This document does not implement streaming, cancellation, attention budgets, global curation, ordinary-insight outcomes, evaluation/replay, cost limiting, transcription, a persistence backend, external actions, or a general multi-session engine. Fact precedence and engagement-record management are unchanged.

Until a separate session-runtime contract is implemented, the host serializes turns, maintains required reference/input history, and does not concurrently mutate an in-flight context.

### 2.4 Relationship to live assistance

Retire IT-1 through IT-6 in favor of this contract. Do not retire the remaining thesis work by a blanket pointer: preserve provider integration, anchoring, topic/general supersession, restraint, ordinary outcomes, delivery, timing, session controls, budgets, and Evaluation/replay. The item-level mapping is in INSIGHT_TYPES_ADOPTION.md.

## 3. Normative vocabulary

### 3.1 Definitions

| Preferred name | Wire value | Primary purpose | Example |
|---|---|---|---|
| INFORMATION | fact | Relevant information without an added interpretation or recommendation; not a claim of independent verification | The supplied scope includes one company code. |
| OBSERVATION | observation | Grounded interpretation, pattern, or synthesis improving awareness | The discussion has shifted from feasibility to process ownership. |
| SUGGESTION | suggestion | Recommended action, approach, or course of action | Validate source-data availability before confirming the design. |
| WARNING | warning | Material risk, adverse consequence, or constraint that could undermine an objective | The date depends on an approval that has not been scheduled. |
| OPPORTUNITY | opportunity | Favorable opening or potential benefit worth considering | A shared interface could reduce duplicated development. |
| PRAISE | praise | Recognition of specific effective behavior for reinforcement | You clarified the requirement before committing to an approach. |
| REPLY | reply | Optional wording for the principal to say or send to a counterpart | Before we commit, could we confirm who owns the approval? |
| CORRECTION | correction | Repair or withdrawal of earlier assistant information or guidance that was wrong, misleading, or unsupported | Correction: the date was proposed, not approved. |
| QUESTION | question | Assistant-to-principal request for information needed to assist appropriately | Are you authorized to agree to a scope change here? |

ERROR remains a tenth unique enum value for legacy operational diagnostics, not a tenth human-facing purpose. Not every agent may emit every type.

### 3.2 Knowledge versus communication

Creating/updating a Fact MUST NOT automatically emit an insight. Emitting informational content MUST NOT automatically create or modify a Fact. A fact can support any insight nature or none; an insight can cite multiple fact revisions. Neither the class name nor the insight label guarantees truth.

### 3.3 No surface or action semantics

Definitions and generated classification instructions MUST NOT encode panels, zones, colors, voices, or automatic interruptions. Host examples may demonstrate treatments only as host policy.

A type never authorizes sending, commitments, record mutation, or tools. FORCE is a host-issued execution trigger: neither an authorization credential nor an isolated lane. WARNING is not automatically high confidence; REPLY is not necessarily urgent; OBSERVATION is not necessarily passive.

## 4. Enum and wire compatibility

### 4.1 Target declaration

```python
from enum import Enum


class InsightType(str, Enum):
    SUGGESTION = "suggestion"
    WARNING = "warning"
    OPPORTUNITY = "opportunity"
    FACT = "fact"
    PRAISE = "praise"
    ERROR = "error"  # Legacy framework diagnostic only.

    INFORMATION = FACT  # Preferred name; existing canonical member retained.
    OBSERVATION = "observation"
    REPLY = "reply"
    CORRECTION = "correction"
    QUESTION = "question"


HUMAN_INSIGHT_TYPES = (
    InsightType.INFORMATION,
    InsightType.OBSERVATION,
    InsightType.SUGGESTION,
    InsightType.WARNING,
    InsightType.OPPORTUNITY,
    InsightType.PRAISE,
    InsightType.REPLY,
    InsightType.CORRECTION,
    InsightType.QUESTION,
)
```

### 4.2 Compatibility requirements

- INFORMATION is FACT by identity; both serialize as `fact`.
- INFORMATION.name remains FACT. Display labels come from an explicit label map, not `.name`.
- Iteration includes ten unique values including ERROR; `__members__` includes eleven names. Offering code uses the explicit human set and deduplicates wire values.
- Do not apply `@unique` to an intentionally aliased enum.
- Model-facing values are exact lowercase wire values. Configuration may resolve public names separately; model parsing must not use that configuration-only resolver.
- Changing the wire value to `information` is deferred to an explicitly versioned migration. Do not assume old consumers tolerate new enum values.

## 5. Classification rules

### 5.1 Primary-purpose order

This is prompt/evaluation guidance, not a keyword classifier:

1. Repairing the assistant's earlier message: CORRECTION with a target.
2. Requesting an answer from the principal: QUESTION.
3. Delivering proposed wording for a counterpart: REPLY.
4. Highlighting material adverse consequences: WARNING.
5. Identifying a favorable opening: OPPORTUNITY.
6. Recommending an action: SUGGESTION.
7. Reinforcing specific effective behavior: PRAISE.
8. Interpreting/synthesizing supplied evidence: OBSERVATION.
9. Otherwise conveying relevant supported information: INFORMATION.

If no type fits honestly, remain silent or report validation failure; do not force a label. Supporting rationale need not become another card. Multiple candidates do not authorize multiple displays.

### 5.2 Boundary examples

| Case | Classification |
|---|---|
| Who approves the change? — wording offered for the client | REPLY |
| The same words asked of the principal, expecting an answer | QUESTION |
| Ask who approves the change. | SUGGESTION |
| Budget changed from 100,000 to 60,000; both were correct at their respective times | INFORMATION, not self-correction |
| My earlier budget figure was wrong. | CORRECTION |
| Proposal and meeting notes contain different dates | OBSERVATION; disagreement does not establish which is correct |
| They are hiding their real objection — without evidence | Unsupported interpretation; do not present as established knowledge |
| Three-step recommended approach | SUGGESTION in step format |
| Draft wording repairing a client-facing statement | REPLY unless separately repairing prior assistant-to-principal assistance |
| Principal's statement conflicts with a supplied document; purpose is identifying discrepancy | OBSERVATION |
| Discrepancy creates material risk/unsupported commitment | WARNING |
| Supported datum supplied without added interpretation | INFORMATION |
| Wording for the principal to clarify the discrepancy | REPLY |

A direct request to the assistant can yield INFORMATION, OBSERVATION, SUGGESTION, or another suitable nature. FORCE identifies a trigger, not an audience or type.

## 6. Typed payload and provenance

### 6.1 Boundaries

Separate model-authored candidates from engine-emitted insights. Schema adapters normalize into a common candidate shape. Acceptance validates that shape and the trusted invocation context, stamps identity, and returns AgentInsight. Defaults for Python construction do not waive typed emission validation.

### 6.2 Fields

Existing AgentInsight fields remain, with negotiated additions:

| Field | Ownership and validation |
|---|---|
| id | Optional before acceptance; engine-minted, session-unique and nonempty on typed emitted insights |
| turn | Engine copies host turn_count; never model-authored |
| contract_version | Engine stamps typed_v1; absent/null for legacy |
| urgency | now/soon/whenever; resolve by section 6.6 |
| confidence_provided | Engine-derived Boolean on negotiated typed output only |
| observation_kind | hypothesis/implication/null; non-null only on consulting OBSERVATION |
| evidence_refs | List of exposed evidence references; no model-invented authority |
| rationale | Optional concise supporting explanation, not hidden chain of thought or execution trace |
| validation_step | Required nonempty text for a hypothesis |
| assumptions | Explicit conditions; empty does not establish that no assumptions exist |
| correction | Required only on CORRECTION |
| question | Required only on QUESTION |
| metadata | Dictionary for presentation extension; never grants permissions, identity, provenance, or validation status |
| preview | Optional plain-text summary/excerpt under long_form_v1 |
| content_format | plain_text/markdown under negotiated format support |
| content_contract | Engine stamps long_form_v1 only after negotiation |
| response_depth | Engine echoes selected writing depth; not proof of actual length or quality |
| content_request_id | Engine echoes host request correlation; not insight identity |
| source_snapshot_id | Engine stamps frozen snapshot identity for isolated content results |

Model-authored confidence is optional, internally numeric or null for not provided. Explicit null is the provider-schema spelling of omission, not a declared estimate. Typed mode rejects Booleans, numeric strings, nonfinite values, and values outside [0,1].

Public AgentInsight.confidence remains a finite non-null float. An explicit valid estimate emits that value with confidence_provided=true. Omission/null emits the historical placeholder 1.0 with confidence_provided=false. The placeholder MUST NOT be displayed as certainty or used in ranking. Model-authored confidence_provided is rejected, including attempts to confer provenance through metadata.

Old serializers omit new fields. An absent flag in an old record means unknown provenance, not true. Updated hosts must negotiate and honor the flag. Internal nullable candidates and numeric public serialization are deliberately separate boundaries. Fact.confidence and fact precedence are unchanged.

Normalized candidate schemas exclude engine fields: id, turn, contract_version, confidence_provided, content_contract, response_depth, content_request_id, source_snapshot_id. Revalidate an allowlisted serialized projection at acceptance; do not trust a previously validated mutable object.

### 6.3 Reference shapes

```python
class EvidenceRef:
    kind: Literal["segment", "document", "fact", "insight"]
    ref_id: str
    revision: Optional[str]

class CorrectionPayload:
    target_insight_id: str
    operation: Literal["replace", "withdraw"]
    reason: str

class QuestionPayload:
    reason: str
    response_format: Literal["text"]
```

These describe shapes, not complete implementations. Production models must reject extra keys, validate nonempty strings and configured limits, and enforce cross-field rules.

General observations may omit references but must remain grounded in the actual supplied context. Consulting hypotheses require evidence, rationale, and a validation step. Implications require evidence and rationale naming their premises. Corrections require their target and evidence supporting the repair; the target alone does not establish it was wrong. A host may select a stricter general policy explicitly.

Reference existence is mechanically testable; whether evidence supports the claim is a semantic requirement, not proved by schema validation or confidence.

### 6.4 Trusted reference context

The framework provides a read-only segment catalog from material actually exposed to each agent, after context selection. Hosts need not build an evidence service for general observations. Hosts provide supplemental document/fact references and retained history for cross-turn operations.

The context contains an evidence catalog of `(kind, ref_id, revision)` to bounded excerpt/provenance; prior emitted insight records with id/session/principal/agent/type/content/turn and active/superseded/withdrawn status; and correlated question-input records when enabled.

Reference identity comes from the trusted snapshot builder/host adapter. Source text remains untrusted content and gains no instruction authority. Model-writable metadata, variables, or sys keys are not authoritative catalogs.

Freeze and propagate the complete principal/capability/evidence/history/input snapshot through both phases. Do not advertise references to context trimmed out of the model input. Custom agents must obtain or declare their actual exposed context through the adapter.

Default IDs such as `snap:<opaque-id>:segment:2` identify an immutable invocation snapshot. They are not durable transcription-segment IDs across moving windows or revised transcripts. Do not deduplicate occurrences merely by identical text/speaker/timestamp. Cross-turn reference resolution requires retaining the snapshot/revision or stable host segment IDs plus revisions. Unavailable/pruned references reject; no guessing. Cross-session corrections are deferred.

### 6.5 Context extensions

Proposed host/runtime inputs are principal_id, insight_capabilities, insight_reference_context, insight_answers, content_execution_context, and insight_content_requests keyed by agent. They are not output mappings.

HostInsightCapabilities defaults to the five existing non-error wire types; reply_drafts, text_questions, corrections, and expanded_reading are false. Content contracts are absent by default; plain text is the default format. Enabling content requires positive body/preview limits. General OBSERVATION support must be explicitly declared.

Correction-agent policy defaults to own_only. An explicit allowlisted policy names agents authorized to repair other agents' insights while retaining all session/principal/evidence checks.

Typed integrations supply monotonically increasing turn_count and never concurrently mutate/reuse an in-flight context. This requirement is not an engine-owned session lock.

### 6.6 Urgency fallback and confidence ranking

Resolve valid explicit urgency first, then non-null configured agent default, then:

| Type | Fallback |
|---|---|
| warning, opportunity, reply, correction | now |
| suggestion, praise, question | soon |
| fact/information, observation | whenever |

Invalid explicit urgency rejects. Fallbacks are product priors, not intrinsic semantics or permission to bypass attention, repetition, authorization, or host capabilities. ERROR has no human-insight urgency policy.

**D-CR:** Default insight ranking ignores confidence for all candidates. The separate policy workstream uses `(urgency_order, -agent_priority, stable_merge_order)`, where now=0, soon=1, whenever=2 and stable_merge_order is `(phase, registration_index, candidate_ordinal)` captured for the turn, not arrival order.

Do not rank missing below an explicit zero, invent a substitute confidence, or compare confidence only when both values exist and otherwise order: that pairwise rule can cycle. Any future confidence-aware policy requires a deterministic total order and evidence of comparability/calibration. Blackboard fact precedence is unchanged.

## 7. Permissions and host capabilities

### 7.1 Configuration

`AgentEngine(insight_contract="legacy_v2")` remains the default compatibility path in the current major version. Upgraded examples explicitly select typed_v1. A future default change is a separate release decision.

Proposed per-agent insight_config:

```json
{
  "allowed_types": ["fact", "observation", "suggestion", "warning", "opportunity"],
  "allow_reply": false,
  "allow_question": false,
  "allow_correction": false,
  "analysis_profile": "consulting",
  "default_urgency": null
}
```

The default typed allowed set consists of the six ordinary purposes: information, observation, suggestion, warning, opportunity, praise. It remains subject to schema/host restrictions. `allowed_types=[]` means state-only, not all. The default analysis profile is general; consulting enables only the two named observation subtypes.

### 7.2 Effective capability intersection

Effective types are the intersection of framework human-facing types, agent allowed_types, schema supported_insight_types, host supported types, and additional permission/reference requirements.

| Type | Additional requirements |
|---|---|
| REPLY | allow_reply=true, included in allowed_types, explicit principal, host draft support, typed path |
| QUESTION | allow_question=true, included in allowed_types, explicit principal, correlated host text input, typed path |
| CORRECTION | allow_correction=true, included in allowed_types, trusted history and host correction handling, same-session/principal target, typed path |

Flags never implicitly expand allowed_types. Contradictory static configuration fails at registration. Missing run-specific capability/principal/reference removes the type for that run with a capability-unavailable diagnostic; state-only work may continue.

Requests advertise exactly the effective values. Engine acceptance enforces the same restrictions for DynamicAgent and custom BaseAgent outputs. FORCE, priority, urgency, confidence, and model-authored flags never bypass them. Unsupported special types are rejected, not converted to suggestions.

### 7.3 Empty sets

Use a silence-only envelope when state-only work remains useful; do not generate an empty JSON Schema enum. Skip insight-only agents with no effective type using no_supported_insight_types.

## 8. Parsing, validation, and atomicity

### 8.1 Acceptance sequence

Freeze trusted context; compute effective permissions; render exact instructions; invoke if eligible; parse without durable mutation; normalize the gate/candidates; validate fields, permissions, references, and type obligations; independently validate domain channels and write authority; accept/reject under the mode's rule; stamp IDs and emit/commit only through the supported engine path; preserve diagnostics and usage.

Long-form acceptance also requires a trusted complete-generation result and successful size/format/preview checks before commitment. Model-supplied runtime identities or acceptance flags reject.

### 8.2 Speech gates

Only an actual Boolean true authorizes speech in Boolean-gated schemas. False is valid silence and may coexist with valid domain updates. Strings, numbers, null, and a missing mandatory gate never authorize speech.

A declared root-presence adapter maps absent/null/empty object to silence and nonempty object to a candidate; other root types are invalid. Explicitly gate-less legacy adapters retain their declared rules, not raw truthiness.

New normalized envelopes reject false plus non-null candidate. Flat legacy schemas may contain unused placeholder fields on false; their declared adapter discards only those unused insight fields, not state.

### 8.3 Local validation

Typed mode rejects unknown/display/uppercase type values, disallowed types, invalid references, unexpected fields, invalid metadata, contradictory type-specific payloads, invalid confidence, and invalid explicit urgency. Missing permitted fields receive documented defaults.

Use strict primitive validation; exercise actual JSON and custom-agent paths. A constructor's prior validation does not replace acceptance-boundary revalidation.

### 8.4 Typed atomicity

Any invalid candidate makes the entire typed agent response noncommittable: no insights, facts, variables, events, queues, memory, or action-bearing sidecars commit. Valid silence is not rejection.

No contract mode may mutate durable private state while parsing. Typed reads use committed Blackboard memory rather than stale instance fallback. Commit permitted memory only through engine acceptance/merge. Usage and sanitized diagnostics remain even when domain effects are rejected.

One failed agent does not prevent other valid agents completing. Callback errors cannot release rejected content. Unresolved correction-bearing responses are held whole under section 10.3.

### 8.5 Diagnostics

Add a no-op on_insight_validation_error(issue) callback and a sanitized serializable diagnostics collection. The engine is the sole callback emitter, exactly one rejection notification per rejected execution result, with details grouped inside it. Different attempts remain separate events; this is not a durable exactly-once guarantee.

Issues contain an execution identifier, agent ID, error code, field path, and optionally a bounded raw classification. Do not include complete prompts, transcripts, raw exception bodies, or hidden reasoning by default.

Codes include invalid_gate, inconsistent_gate, unknown_type, type_not_allowed, invalid_field, invalid_metadata, invalid_confidence, invalid_urgency, missing_evidence, unknown_reference, cross_session_reference, missing_principal, capability_unavailable, invalid_correction_target, correction_conflict, invalid_question_contract, invalid_input_reference, no_supported_insight_types, invalid_domain_payload, reserved_state_write, partial_legacy_response, unsupported_structured_output, provider_schema_error, content_execution_not_allowed, invalid_content_execution_context, content_contract_unavailable, invalid_content_policy, unsupported_depth, unsupported_content_format, content_too_large, preview_too_large, response_too_large, content_extension_not_enabled, incomplete_generation, and completion_unknown.

### 8.6 Legacy partial acceptance — D-LR

Both modes reject unrecognized classifications without relabeling. Legacy preserves separately valid state through a narrow exception:

| Result | Insight disposition | Domain disposition/status |
|---|---|---|
| Valid allowed insight | Accept | Commit validated authorized channels; accepted |
| Valid silence | None | Commit valid channels; accepted_silent |
| Recoverable type/gate/insight-field error | Reject all insights from that result | Commit only independently valid authorized domain channels; partial if any remain, otherwise rejected |
| Unparseable/truncated envelope, invalid domain payload, reserved write, forged ownership, failed authorization | None | Reject whole; rejected |

Partial status is engine-derived, serializable, and distinguishable from successful delivery or deliberate silence. Diagnostics identify rejected fields and retained channel names, not sensitive values. A missing mandatory Boolean gate is an insight error, not permission to speak.

Action-bearing data sidecars are not eligible for partial acceptance; withhold and diagnose them. Retained facts, variables, queues, events, and memory remain untrusted proposals, not external-action authority or proof of exposure. Rejected output must not update shown/accepted-insight ledgers or last-delivered markers. If independent validation cannot be established, reject the whole result.

Stage all changes without private-state or durable Blackboard mutation. Valid legacy memory may change after commit; that is intentional, not a parsing leak. This exception never applies to typed responses, correction arbitration, or incomplete/oversized long-form generation. Model-authored ERROR or new privileged types cannot evade typed requirements through legacy mode.

## 9. Reply contract

REPLY is offered privately as a draft for possible use; the drafted text addresses a counterpart. It requires explicit permission, principal identity, and host draft support. It must not invent approvals, authority, prices, deadlines, or commitments unsupported by available evidence. That is a semantic quality obligation beyond schema validation.

The host distinguishes drafts from words actually spoken. Reading a draft privately to the principal does not establish that the principal used it. The type must not call send, messaging, conferencing, or counterpart text-to-speech actions. No WARNING_REPLY or similar combined types are introduced.

## 10. Correction contract

### 10.1 Targets

CORRECTION repairs earlier assistant assistance. Targets must resolve to a prior emitted, active, non-diagnostic insight in the same session and for the same principal, preceding the current turn and present in the trusted snapshot. The default policy allows repair of the agent's own output; cross-agent repair requires host authorization.

Unknown, self, same-turn, withdrawn/superseded, or cross-session targets reject. They do not become informational fallbacks.

### 10.2 Operations

Replace supplies the corrected account/guidance. Withdraw explicitly says not to rely on the earlier output and may have no replacement conclusion. Reason identifies the defect; supporting evidence establishes the basis. The old target alone is not proof it was wrong.

### 10.3 Whole-response holding and arbitration

Hold each unresolved correction-bearing response in full, including ordinary sibling insights and all domain effects. Independently validated unrelated responses may emit early only through a separately certified incremental path. Domain state stays phase-staged in the documented priority/registration merge order.

At phase close/deadline, discard incomplete/late results under the delivery contract and arbitrate the closed complete validated set. Order correction-bearing responses by descending agent priority then later registration. Greedily accept a whole response only if all its targets are unreserved, reserving all together. Otherwise reject it wholly with correction_conflict and reserve nothing. Duplicate targets within a response reject it. This prevents incompatible per-target winners for multi-target responses.

Targets accepted in an earlier phase of the same turn remain reserved; later responses cannot retroactively invalidate committed phase effects. There is at most one accepted correction per target per turn. This is deterministic authority ordering, not truth adjudication. High-stakes hosts should require confirmation of contested corrections.

The host applies correction publication and target-status changes coherently, preserving history and associating replacement/withdrawal. It updates the reference registry before the next serialized turn and never redisplays the target as current. Emission proves neither message was shown. Insight correction does not itself rewrite Facts or other engagement records.

## 11. Question and response contract

### 11.1 Questions

QUESTION is assistant-to-principal input, not proposed counterpart wording. Require explicit permission, principal identity, supported host text input, and a nonempty reason why information matters. The initial response format is text. The engine-issued insight ID is the correlation key; the model invents no second request ID. An unanswered question does not block unrelated processing.

### 11.2 Answer events

```python
class InsightAnswer:
    event_id: str
    question_insight_id: str
    principal_id: str
    status: Literal["answered", "dismissed"]
    text: Optional[str]
```

Host-supplied AgentContext.insight_answers defaults to empty. Answered requires nonempty text; dismissed requires null. Targets must be emitted questions in the same session/principal context. The host tracks open/closed state; responding after closure requires explicit reopening.

The host owns durable event idempotency. Reusing an event ID with different content is an integration error. The engine also rejects duplicates/conflicts within an input batch; no cross-process exactly-once claim is made.

### 11.3 Consumption

By default, validated answers reach only the originating agent through the typed context and insight_answers template variable; sharing requires host authorization. Text remains untrusted and cannot overwrite principal identity or permissions. Receipt schedules no automatic model call. The host may target a later run through the existing allow-list. Absence, dismissal, elapsed time, and model guesses are not consent or factual answers.

## 12. Consulting profile

### 12.1 Defaults

Enable information, observation, suggestion, warning, and opportunity; disable praise by default in senior-consultant/client meetings. Special types remain permissioned. A host can label SUGGESTION as Recommendation without changing its wire value.

### 12.2 Hypothesis

Use OBSERVATION with observation_kind=hypothesis. Require at least one exposed evidence reference, a rationale, and a validation step. State assumptions explicitly. Example: approval ownership may explain delays more than system capacity; validate by comparing approval wait and processing time. Repetition does not promote a hypothesis to a Fact.

### 12.3 Implication

Use OBSERVATION with observation_kind=implication, evidence, and rationale naming premises. Keep conditional premises explicit: if reconciliation must be transaction-level, an aggregate file may be insufficient. Use WARNING when the primary job is material risk. Do not invent cost/schedule estimates as established consequences.

### 12.4 Engagement records

Requirements, assumptions, decisions, commitments, and action items are domain records; storing them does not require a card. Recommendations are not client decisions; pending approvals are not completed approvals. Finding/hypothesis/implication/recommendation can be one candidate with supporting detail, not four interruptions.

## 13. Schema and prompt integration

### 13.1 Descriptors

Versioned schema descriptors declare supported_insight_types, supported_insight_fields, gate_mode (boolean/root_presence/state_only), supported_contracts, and supported_content_contracts. Descriptor, prompt, normalization, and validator must agree. Legacy retains declared shapes/offerings; typed requests advertise the effective set without contradictory old literal lists.

Requesting a type whose required fields cannot be mapped fails registration. Do not drop question/correction payloads or downgrade their type.

### 13.2 Mappings

Add mappings for urgency, observation_kind, evidence_refs, rationale, validation_step, assumptions, correction, question, and negotiated preview/content_format. Engine identity, provenance, completion, and request stamps are never model-output mappings.

A normalized insight_v1 Boolean-gated schema is the preferred direct shape. State-producing adapters normalize their insight component into that contract. default_v2 and v2_raw are the initial existing-format typed adapters; default, custom1, ui_control, and widget_control remain legacy unless separately certified. Selecting typed mode without an adapter fails early with an actionable alternative.

### 13.3 Provider enforcement and derivation

SO-1 remains a first-class deliverable. insight_contract selects local semantics; structured_outputs=strict/auto/json_object selects transport independently. Provider structure proves neither authority nor grounding nor exposure.

Derive provider schemas from one authoritative local contract and a versioned full-response descriptor. Provider objects have required properties and closed objects; optional values use nullability. Retain local cross-field, semantic, length, permission, and reference checks. Equivalence means exact vocabulary and lossless normalization with explicit local-only constraints, not that every provider-valid object is locally acceptable.

Open dictionaries use recursive map_entries_v1: a map contains an entries array of key/value records, with nested scalars, arrays, and maps represented explicitly. Reject duplicate keys, nonfinite values, invalid envelopes, and unauthorized writes after decoding. Include state_updates, variable_updates, queue_pushes, facts, events, memory_updates, and data in full-response projections; do not delete channels to achieve a strict schema. Metadata uses closed transport encoding and returns to an ordinary local dictionary. Source identity and timestamps remain engine-owned.

Preflight lint checks schema and effective types, including valid silence-only schemas. Refusals, filtering, token-limit termination, transport failures, malformed output, and unknown completion have distinct handling. Refusal is not evidence that structured output is unsupported.

Only auto may downgrade once after an approved exact unsupported-capability signature matches. The signature identifies adapter/version, endpoint family, HTTP status, structured error code, parameter path, feature, and evidence/fixture ID. HTTP 400, a generic misconfig category, or message-substring guessing is insufficient. Invalid schema, authentication, unknown model, context/rate limits, refusals, and unknown errors do not qualify.

No production signature is enabled until a documented or captured sanitized positive fixture supports it. Disabled synthetic signatures may test the matcher but are not production evidence. An operator may explicitly select json_object for a known endpoint; strict never downgrades. Auto retry retains the same local contract and is accounted for under time/cost admission. Downgrade caching is keyed by endpoint/model/adapter/schema version and invalidated when those change, never global shared-client state.

Local schema lint and codec tests do not prove live provider acceptance. Actual endpoint tests and early transport byte/depth limits are implementation requirements.

### 13.4 Prompt guidance

Generated instructions explain exact effective purposes/wire values, information versus interpretation, reference availability, silence, and special-type rules. Explain that fact is the information wire spelling. Do not claim every useful observation deserves display, type implies urgency, or confidence proves truth. Detailed requests must not inherit contradictory short-HUD-only instructions. Include section 5 boundary examples and enabled consulting rules.

## 14. Host delivery, diagnostics, and long-form content

### 14.1 Delivery boundary

Only accepted final AgentResponse.insights, or a separately certified incremental interface, are display-eligible. Raw per-agent callbacks are evaluation telemetry, not permission to display unvalidated/unmerged content. Host selection, interruption, and narration remain subject to its attention policy. Handle every declared supported type without relabeling.

### 14.2 Identity and history

Stamp IDs at acceptance and preserve them through policy/serialization. Archive records needed for questions/corrections before the next turn. Retention is explicit and bounded; preserve IDs and revisions. Missing history makes dependent capabilities unavailable or rejects their candidates. Never promise indefinite repair from a lossy ring.

### 14.3 Diagnostics

Use sanitized diagnostics plus appropriate callbacks. Runtime provenance must distinguish manufactured diagnostics from model output; metadata.origin=framework is not proof. During migration a framework ERROR may carry a safe category such as agent_error, never raw exception text. Protect detailed debugging separately, not in ordinary insight metadata. Exclude diagnostics from conversational counts; model-authored error is rejected in every mode.

### 14.4 Length-independent content contract

An insight MAY contain brief or extended content. Its type describes purpose, not length. Preserve the complete accepted body and provide suitable reading behavior; do not force long content into transient notifications.

long_form_v1 is an optional extension of typed_v1, not a new type or streaming implementation. Engine, adapter, and host must explicitly support it. All nine purposes remain length-independent while their permissions/lifecycles still apply. Detailed requests do not justify filler or unsupported claims. Enforce finite negotiated limits, not a universal word ceiling.

### 14.5 Canonical content, previews, formats

The complete body belongs in content. Rationale remains concise explanation, not overflow storage. Preview is optional plain text within its limit, faithful to the same body; it cannot add claims, conceal material qualifications, promote hypotheses to facts, or turn a draft into recorded speech. Faithfulness needs semantic evaluation. Use null when no safe useful preview exists.

The host can show preview first but must provide full content under the same insight ID. Never overwrite canonical content, silently truncate storage/export, or count expansion as another insight. Preview exposure does not prove the body was opened or read. Host-generated excerpts must be labeled.

Formats are plain_text or markdown; missing normalizes to plain_text. Advertise only supported formats and reject unsupported explicit values. Portable Markdown supports paragraphs, headings, emphasis, lists, quotations, code spans/fences, and untrusted links. Hosts must sanitize or escape, execute neither code nor raw HTML, and fetch no remote resources merely because content requests them. Inert-text fallback preserves the canonical string. Exact styling is host-owned.

### 14.6 Depth, limits, and generation settings

Configure content independently of type/urgency. A host may override an agent's default through InsightContentRequest(depth=brief/standard/detailed, request_id=optional). Unknown depth, missing profiles, invalid numeric settings, and incompatible formats fail before invocation; no silent downgrade. FORCE does not imply detailed output or bypass checks.

Illustrative—not mandatory—profiles are brief: 1,200 content characters / 1,000 output tokens / 10-second per-request timeout; standard: 8,000 / 3,500 / 20 seconds; detailed: 40,000 / 16,000 / 60 seconds. An example preview limit is 280 characters and response byte limit 262,144. These are configuration examples, not model capacity or latency claims.

Effective content and preview limits are minima of host/agent/operator limits. Count decoded Unicode code points including whitespace and formatting, separately from a UTF-8 whole-response byte ceiling. Requested depth is a writing objective, not a minimum length or quality certification. Output-token caps cover the complete provider envelope and provider-specific accounting, not content alone. No universal character/token ratio is assumed. Per-request timeout is not an end-to-end deadline; retries and processing remain relevant.

#### 14.6.1 Active-session execution admission

Standard/detailed generation is extended; a brief label cannot conceal larger-than-live budgets. During an active session, extended work requires isolated_content with a frozen snapshot, explicit request ID and snapshot ID, separate task ownership, no live-turn lock, no direct live Blackboard/private-memory writes, and admission that preserves live-lane provider capacity. Do not share mutable agent instances or a single trace buffer across these paths.

Without verified isolation, extended work runs only during an explicitly declared pause or post-session operation. A short live-turn deadline is not a substitute for a content task's own budget. FORCE is not isolation.

Trusted ContentExecutionContext declares session_mode (active/paused/post_session), execution_path (live_turn/isolated_content/offline_content), request_id, source_snapshot_id, holds_live_turn_lock, writes_live_blackboard, pause_declared, and task_isolation_verified. Host declarations require adapter validation; they are not model metadata. Paused mode requires explicit pause. Active isolation requires IDs, false lock/write flags, and verified isolation. Missing context rejects extended execution.

Active isolated content is result-only: reject proposed nonempty state/fact/event/queue/memory/action channels, rather than applying or silently dropping them. Any later domain change enters a fresh serialized transaction against current state. Return request/snapshot identity without mutating live sys.turn_count or reserving correction targets. Ordinary types and permissioned reply drafts are eligible; corrections/questions remain disabled on this active isolated path until a serialized interactive commit design exists. They retain long-content support in properly paused/post-session integrations.

Cancellation/session end closes publication permission. Preserve usage/diagnostics without late publication or live writes. The host checks currentness before publishing aged-snapshot results. Local declaration checks do not prove actual task isolation; concurrency integration tests must.

### 14.7 Completion and failure

Adapters supply trusted complete/incomplete/failed/unknown completion status through runtime telemetry. Complete means normal termination with the whole response available for validation, not truth or full task coverage.

Only complete plus successful validation emits extended insight content. Length-limited, interrupted, or cancelled output rejects even when JSON parses. Unknown completion rejects. Model metadata.complete cannot override. Oversized body/preview/envelope rejects with the relevant diagnostic and preserved usage; never silently shorten. A valid preview cannot salvage a rejected/incomplete body. Typed whole-response atomicity applies.

Enforce transport limits as early as possible; checking after unbounded allocation is not memory protection. An explicit retry or smaller-depth request is a new accounted execution, not hidden concatenation or overwriting the failed attempt. No partial fragments are represented as accepted insights by this contract.

### 14.8 Reading, retention, and currentness

Display expiry is neither deletion authority nor factual validity. Expanded hosts preserve full content throughout active reading and declared session retention, except explicit deletion or declared security/retention requirements. Transient expiry must not collapse an active view, erase content, reset scroll, or steal focus.

Normal updates must not replace the body under the reader. Corrections are marked and linked; old content remains historical rather than silently current. Privacy deletion is represented as unavailability, not text substitution. Retained content keeps stale/superseded/withdrawn status; retained replies remain drafts. Copy/export includes the complete body and its status/context, not merely the preview. No indefinite retention promise is made.

### 14.9 Expansion versus new generation

Opening an already accepted body must make no model call or consume new generation budget. Elaboration is a separate, explicit, correlated request supplied with appropriate evidence/history.

Progressively rendering an already complete accepted string is allowed; it is not token streaming. Display of unvalidated fragments, speculative corrections, or partial replies requires a separate certified streaming contract. No automatic narration of entire detailed answers, counterpart sending, answers on the principal's behalf, or engagement commitments arise from long-form content. Unattended live behavior should remain brief.

### 14.10 Negotiated rollout

Without long_form_v1, omit preview, content_format, content_contract, response_depth, content_request_id, and source_snapshot_id from old strict-consumer output; do not assume null keys are compatible. Explicit unnegotiated extension fields reject. With negotiation, absent preview/format normalize to null/plain_text; runtime stamps selected depth and identities. A long string passing a schema is not proof of host/generation support.

### 14.11 Consulting example

One detailed SUGGESTION can contain assumptions, alternatives, implications, recommendations, and validation steps with a short preview. It does not become separate plan/summary/long-response types. Synthetic 5,000-word probes test size and exact preservation only, not good advice, latency, or rendering.

## 15. Migration and implementation sequence

### 15.1 Compatibility inventory

| Change | Edge |
|---|---|
| INFORMATION alias | Python-additive; fact wire and canonical name retained |
| Four new purposes | Closed-enum consumers need explicit upgrades |
| New optional fields | Strict wire consumers still require negotiation |
| Confidence provenance | Numeric field retained; negotiated runtime flag; old omission means unknown |
| Strict gates and unknown rejection | Immediate hardening; legacy partial versus typed whole-response behavior explicit |
| No parse-time durable mutation | Mandatory in both modes; state commits only after acceptance |
| ERROR ownership/content | Framework-only, sanitized diagnostic; no exception-prose API |
| Identity/interactions | New host obligations; unsupported capabilities remain disabled |
| Future information wire/default flip | Separate versioned migration |
| Long-form fields and limits | Negotiated only; no silent truncation |
| Reading lifecycle | Host conformance requirement |
| Active extended generation | Isolation or explicit pause/post-session, not FORCE |

### 15.2 Dependency gates

These names are local to this specification, not automatic runtime versions.

| Gate | Scope | Proof before enablement |
|---|---|---|
| G0 Legacy safety | Gate/type hardening, D-LR, no precommit mutation | Real-engine preservation/fatal-rejection and built-wheel regression |
| G1 Typed foundation | Vocabulary, capability intersection, typed atomicity, diagnostics, identity, provenance | Built-in/custom-agent framework tests |
| G2 Provider/evidence | Derived schemas, verified-signature fallback, exposed-context catalogs | Codec/local tests plus actual endpoint acceptance and reference tests |
| G3 Grounded/interacting assistance | Consulting, drafts, corrections, questions | Framework, specific-host conformance, and end-to-end proof |
| C1 Content/reading | Preview/body, completion, limits, reading | Framework and host proof; independent of streaming |
| C2 Active isolated generation | Snapshot, tasks/capacity, no live lock/write, closure/currentness | Concurrency/failure integration; otherwise paused/post-session only |
| R Adoption of each capability | Docs, migration, wheel flow, owner sign-off | Accompanies each gate, not one final release |

Develop provider enforcement and typed acceptance from the same authority. Interactive capabilities remain unavailable before lifecycle implementation. C1 may precede C2. Ordinary outcomes, restraint, delivery, session controls, budgets, and Evaluation remain separate roadmap deliverables.

### 15.3 Implementation map

Models: enum, typed payload, reference/input shapes, diagnostics, context extensions. Agent/DynamicAgent: helper compatibility, staged parsing, mappings, actual exposed context, no precommit durable state. Engine: capability intersection, context propagation, acceptance, IDs, diagnostics ownership, arbitration. New insight_validation module: pure shape/cross-field/capability/reference rules. Client/adapters: schema projection, completion status, early transport bounds. Host: history, input, safe reading/rendering, currentness. Docs/tests: migration and scoped contracts. These are proposed changes, not existing modules or coverage.

## 16. Contracts and acceptance tests

The 35 ITC IDs are parent requirements, not claims of 35 framework-certified contracts. Each test leaf has exactly one owner/scope: framework, host, or end_to_end. Compound requirements use .FW/.HOST/.E2E leaves. ITC-25 is an installed-wheel end-to-end requirement, not a source-checkout packaging assertion.

Only implemented framework leaves with actual passing rule-asserting tests and negative controls may be marked covered in CONTRACTS.yaml. Host tests identify the actual host version/build. A reference adapter self-test cannot certify another host. End-to-end tests run the installed framework with the named host.

| ID | Required assertion | Negative control |
|---|---|---|
| ITC-01 | Exactly nine unique offered human values; no ERROR | Offer ERROR or duplicate alias |
| ITC-02 | Alias identity, canonical name, fact serialization | Change wire to information |
| ITC-03 | Descriptor/prompt/provider/local effective vocabulary agrees | Advertise a disallowed value |
| ITC-04 | Only Boolean true authorizes speech | Truthy string false speaks |
| ITC-05 | Valid silence preserves valid domain updates | Reject all silence |
| ITC-06 | Unknown/display/uppercase values reject without relabeling | Suggestion/observation fallback |
| ITC-07 | Capability intersection; FORCE cannot bypass | Disabled reply on FORCE |
| ITC-08 | Empty allowed set is valid state-only processing | Empty list means all |
| ITC-09 | Runtime unique IDs preserved through delivery | Model identity or reminting |
| ITC-10 | Strict confidence fields, derived flag, neutral ranking | Invalid value becomes certainty |
| ITC-11 | Explicit/agent/type urgency precedence | Override authored urgency by type |
| ITC-12 | Typed rejection leaves no domain/private effects | Parsing mutation survives |
| ITC-13 | One correlated diagnostic per rejected execution | Duplicate parser/engine callbacks |
| ITC-14 | Full trusted context propagated through both phases | Drop a new context field |
| ITC-15 | References resolve only to exposed retained revisions | Accept fabricated/pruned evidence |
| ITC-16 | General references optional; subtype support required | Unsupported hypothesis fields accepted |
| ITC-17 | Permissioned drafts without external execution | Draft automatically sent |
| ITC-18 | Prior active same-session/principal correction targets | Unknown target relabeled |
| ITC-19 | Coherent correction/history/currentness | Delete history or show stale target as current |
| ITC-20 | Whole-response hold, deterministic multi-target arbitration | Sibling insight emitted before losing conflict |
| ITC-21 | Supported input path and correlated answer | Passive host question/foreign principal answer |
| ITC-22 | Input idempotency with conflicts rejected | Same logical answer applied twice |
| ITC-23 | Framework-only sanitized diagnostics | Model origin metadata bypass |
| ITC-24 | Explicit legacy partial and negotiated typed edges | Universal unknown-key tolerance assumed |
| ITC-25 | Clean installed-wheel reference integration | Editable checkout substituted |
| ITC-26 | Length does not change nature | Long suggestion becomes summary type |
| ITC-27 | Canonical body/ID preserved through expand/export | Preview-only export |
| ITC-28 | Frozen depth/profile and isolated/paused admission | FORCE treated as isolation |
| ITC-29 | Exact Unicode/preview/UTF-8 boundary validation | Silent slicing or wrong units |
| ITC-30 | Trusted complete result required; usage retained | Parseable truncated JSON accepted |
| ITC-31 | Reading survives expiry without focus/scroll reset | Timer closes active view |
| ITC-32 | Supported format with inert safe rendering | Execute raw HTML/fetch remote resources |
| ITC-33 | Explicit host/adapter content negotiation | Arbitrary text rendering implies support |
| ITC-34 | Open makes no call; elaboration separate | Expand silently bills new generation |
| ITC-35 | Incomplete/oversize body has no domain effects | Commit state or salvage preview first |

Grep/schema tests supplement, not replace, actual engine behavior. Host obligations such as draft distinction, rendering, reading, and input handling require separate conformance. The reference package's ownership map provides scoped leaf IDs; importing a fixture never marks its corresponding runtime requirement covered.

### 16.1 Semantic evaluation

Maintain independently reviewed examples across all nine purposes and ambiguous boundaries. Use conversation prefixes only, never future turns. Resolve product/engineering definition disagreements before model evaluation. Deterministic acceptance fixtures must pass; model-specific quality thresholds require a separately declared plan. Shape tests are not semantic accuracy scores.

## 17. Definition of done

All enabled purposes, schemas, agents, and host capabilities must agree. Unknown/invalid output cannot silently become advice or an observation. General observations work without a host evidence service; consulting and correction evidence remain validated. Replies/questions/corrections satisfy complete lifecycle contracts. Legacy partial acceptance is observable, fatal failures commit nothing, and no path mutates durable memory while parsing.

Confidence provenance and confidence-neutral default ranking pass actual implementation tests without changing Fact precedence. Long-form content is complete, preserved, negotiated, and safe; active extended execution cannot hold or write the live session path. Otherwise it stays paused/post-session only.

Each enabled capability has version-identified framework/host/end-to-end tests, including a built-wheel flow with ordinary information, grounded observation, draft, correction, question/answer, and malformed rejection. The long-body/incomplete-generation probe runs through the real framework and host before runtime claims. Documentation, schema instructions, API guide, CHANGELOG, and examples agree. Product signs off semantics; engineering behavior; host integration delivery and correlation.

No reference-package result certifies production acceptance. Completion of this specification does not establish improved human outcomes or completion of unrelated roadmap work.

## 18. Deferred concepts

Summary/recap/briefing/checklist/plan/comparison are formats over appropriate purposes. Explanation is supporting rationale or requested information/observation. Answer is a relation to a request. Reminder is a relation and due condition. Decisions/assumptions/requirements/commitments/actions are domain records. Supportive coaching is a separately justified application extension. Urgent/alert/panel labels are not purposes.

Do not recreate a second unvalidated taxonomy in metadata. New typed extensions require explicit scope and tests; the global vocabulary is frozen for this scope until repeated examples and distinct behavior justify expansion.

## 19. Sources and reference package

This repository edition adapts the approved 1.2.0 design package into repository documentation; it is not a byte-identical copy of the distributed Markdown or an import of all companion executables. Provenance and package hashes are recorded in INSIGHT_TYPES_ADOPTION.md. No runtime is changed by this documentation adoption.

Pinned baseline sources:

- [Models](https://github.com/genriq/xubb-agents/blob/f83fc5b1e3d39da176be0ef30f40eefdd9fe51bc/src/xubb_agents/core/models.py)
- [DynamicAgent](https://github.com/genriq/xubb-agents/blob/f83fc5b1e3d39da176be0ef30f40eefdd9fe51bc/src/xubb_agents/library/dynamic.py)
- [Default schema](https://github.com/genriq/xubb-agents/blob/f83fc5b1e3d39da176be0ef30f40eefdd9fe51bc/src/xubb_agents/library/schemas/default.json)
- [Default v2 schema](https://github.com/genriq/xubb-agents/blob/f83fc5b1e3d39da176be0ef30f40eefdd9fe51bc/src/xubb_agents/library/schemas/default_v2.json)
- [Engine](https://github.com/genriq/xubb-agents/blob/f83fc5b1e3d39da176be0ef30f40eefdd9fe51bc/src/xubb_agents/core/engine.py)
- [Callbacks](https://github.com/genriq/xubb-agents/blob/f83fc5b1e3d39da176be0ef30f40eefdd9fe51bc/src/xubb_agents/core/callbacks.py)
- [Quality process](https://github.com/genriq/xubb-agents/blob/f83fc5b1e3d39da176be0ef30f40eefdd9fe51bc/docs/PROCESS.md)

Technical references retained from the design package: [Python enum aliases](https://docs.python.org/3.11/howto/enum.html), [Pydantic strict validation](https://docs.pydantic.dev/latest/concepts/strict_mode/), [provider structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [provider error classes](https://developers.openai.com/api/docs/guides/error-codes), and [stable sorting](https://docs.python.org/3/howto/sorting.html).

The separately distributed reference package includes normalized/public schemas, provider compiler and codecs, a disabled-by-default fallback registry, local fixtures/checkers, host conformance interface, ownership map, illustrative content profiles, a detailed consulting example, implementation checklist, validation report, provenance, and manifest. Its local results are not production coverage. Actual implementation must be validated against both the normative contract and the scoped tests before support is advertised.
```

## Context document: SPEC_INSIGHT_TYPES_AMENDMENT_2.md
```
# XUBB-ITC-1 — Amendment 2, consolidated ruling record

**Applies to:** specification package 1.1.0.  
**Produced package:** 1.2.0.  
**Date:** September 6, 2026.  
**Status:** Proposed contract with recorded design rulings; no Xubb runtime implementation.  
**Source:** Engineering review and consolidation text supplied in the design conversation, reconciled with the final D-LR and D-CR decisions in [INSIGHT_TYPES_FINAL_DECISIONS.md](INSIGHT_TYPES_FINAL_DECISIONS.md). The reported uncommitted repository edits were not inspected.

FW = framework engineering; HOST = adopting host team; PROD = product. Local reference checks do not certify a provider, Xubb, or any actual host. This repository adoption does not mark any unimplemented contract covered.

## A2-1 — Legacy unknown types: reject, do not relabel

**Review proposal:** Unknown legacy classifications become observations.  
**Ruling:** Reject unknown/disallowed classifications and malformed speech gates in both modes. An unknown label does not establish an observation's meaning. Typed mode rejects the whole response. Final decision **D-LR retains legacy insight-only rejection** for recoverable insight errors, but only independently validated/authorized domain updates commit. Record `partial` status; action-bearing sidecars do not pass via partial acceptance. Invalid outer/domain/authorization results reject whole. Remove parse-time durable-state mutation in the same patch.  
**Affected:** Sections 8.2, 8.4, 8.6; ITC-04, ITC-06, ITC-12, ITC-24; roadmap LH-1.  
**Owner:** FW.

## A2-2 — Urgency: per-type prior, not type semantics

**Review proposal:** Type defaults under an agent override.  
**Ruling:** Valid explicit value → configured agent override → framework per-type fallback. Invalid explicit values reject. Default table is versioned in section 6.6: warning/opportunity/reply/correction now; suggestion/praise/question soon; information/observation whenever. These are fallback product priors, never permission to override attention, repetition or capability policy.  
**Affected:** Sections 6.2, 6.6, 8.3; ITC-11; roadmap UR-1 / INV-22.  
**Owner:** FW with PROD ownership of fallback policy.

## A2-3 — Evidence: simple observations without an evidence-service prerequisite

**Review proposal:** Optional general evidence and default framework segment catalog.  
**Ruling:** Accepted. References remain mandatory for consulting hypotheses/implications and self-correction. Generate catalog references only after agent-specific context selection, for material actually exposed to the model. Snapshot references identify the immutable invocation view, not durable transcription identities. Retain snapshots/revisions or use explicit stable host IDs for cross-turn references; missing/pruned evidence never licenses a guess.  
**Affected:** Sections 6.3–6.5, 12; ITC-14–16; LC-1 anchors.  
**Owner:** FW (current-run catalog); HOST (durable history/revisions).

## A2-4 — Provider structured outputs as a first-class deliverable

**Review proposal:** Strict-compatible projection with closed metadata.  
**Ruling:** Accepted and extended to the full response envelope. Generate schemas from the authoritative local contract plus domain descriptor. Use explicit `map_entries_v1` for otherwise open dictionaries; do not omit domain updates to make a schema strict. Retain local cross-field, permission, evidence and completion checks. Ship structural projections and codec fixtures, but do not claim live provider acceptance.  
**Fallback:** Only auto + passing lint + one unused downgrade attempt + an exact approved adapter error signature qualifies. The production signature registry is intentionally empty because no captured provider error was supplied or verified. A disabled synthetic signature tests the policy. Unknown/configuration errors fail closed; explicit operator JSON-only configuration remains possible. Do not invent a universal provider error code.  
**Affected:** Section 13.3; ITC-03, ITC-24; SO-1 / INV-24.  
**Owner:** FW.

## A2-5 — Correction means assistant self-repair

**Review proposal:** Keep self-repair and classify all principal misstatements as warnings.  
**Ruling:** Retain self-repair. Classify principal misstatements by primary purpose: discrepancy → observation; material risk/unsupported commitment → warning; supported datum → information; proposed clarifying wording → reply. Four explicit review fixtures are included in the specification package, without claiming a model classification test.  
**Affected:** Sections 5.2, 10.1; ITC-18 and semantic review set.  
**Owner:** PROD (labels), FW (instructions).

## A2-6 — Separate framework, host and end-to-end proof

**Review proposal:** Split host UI contracts from the framework gate.  
**Ruling:** Accepted. Keep 35 parent requirements; assign each test leaf one scope in the package's CONTRACT_OWNERSHIP.json. Compound obligations use .FW/.HOST/.E2E suffixes. ITC-25 is end-to-end rather than simultaneously claimed in two groups. No parent requirement is automatically framework-covered. The package supplies an executable adapter kit plus observation procedure; only an in-memory positive self-test and deliberately broken negative control have been exercised. Host runs must identify the actual host version/build and evidence.  
**Affected:** Section 16, implementation checklist, host kit, ownership map.  
**Owner:** FW (kit/interfaces), HOST (actual conformance), FW+HOST (integration).

## A2-7 — Hold correction-bearing responses whole

**Review proposal:** Buffer corrections only, stream other messages.  
**Ruling:** Hold every unresolved correction-bearing response in full, including ordinary sibling insights and all domain effects. Close the eligible set at phase completion/deadline, discard incomplete results, then greedily reserve all targets per response in deterministic priority/registration order. Losing responses reserve nothing and commit nothing. This also specifies multi-target conflicts rather than selecting incompatible per-target winners. Unrelated insights may be delivered only through a certified incremental path; domain state remains phase-staged in documented merge order.  
**Affected:** Sections 8.4, 10.3, 14.1; ITC-12, ITC-20; DL-1/DL-2.  
**Owner:** FW.

## A2-8 — Long-form execution: isolate or explicitly pause

**Review proposal:** Deadline dependency, or FORCE-only detailed generation.  
**Ruling:** Preserve the content/reading contract independently. During an active session, extended generation needs a separately owned task with a frozen snapshot, no live-turn lock or direct live-state writes, correlated result identity and resource admission. FORCE is not that lane. Standard/detailed profiles are extended; a brief label cannot hide larger budgets. Without isolation, pause explicitly or run post-session. Isolated active content is result-only; corrections/questions await a separately serialized interactive commit design and are not enabled on that path in this release. A short live deadline does not replace a content task's own deadline.  
**Affected:** Sections 14.6.1, 14.9; ITC-28, ITC-34, ITC-35; DL-6 / INV-37.  
**Owner:** FW (task/path), HOST (pause, currentness, presentation).

## A2-9 — Confidence compatibility and final neutral ranking decision

**Review proposal:** Keep the numeric public field and add declaration provenance.  
**Ruling:** Accepted. Internally preserve missing confidence. Serialize numeric confidence plus runtime-derived `confidence_provided` on negotiated typed output; missing becomes the legacy numeric placeholder with false, never displayed as an estimate. Absent flags in old records mean unknown provenance. Model output cannot author the flag. **D-CR replaces the missing-last proposal:** default insight ranking ignores confidence, using urgency/priority/stable order for all candidates. Avoid pairwise conditional comparison; a future calibrated policy is separate. Fact precedence is unchanged.  
**Affected:** Sections 6.2, 6.6, 15.1; ITC-10, ITC-24; CF-1 / LC-3.  
**Owner:** FW; HOST (presentation).

## Previously acknowledged corrections to the package

Legacy preservation was too broad; safe compatibility needs narrow, observable partial acceptance. Long-form generation lacked a scheduling restriction; body size/reading support alone does not protect the live path. Both are corrected above.

## Terminology

Grounding references are not Evaluation/replay results. Host-reported shown/acted/spoken events are not proof of correctness or direct proof of human perception. FORCE is a host execution trigger, not permission by itself and not execution isolation.

## Consolidation boundary

Retire IT-1…IT-6 in favor of this contract, but preserve SO-1; LC-1 anchoring; LC-2 topic/general supersession; LC-3 restraint; LC-4 ordinary outcomes; delivery/timing/session/budget work; and Evaluation/replay. Consolidate identity and diagnostics explicitly. Self-correction does not subsume all supersession; question answers do not subsume ordinary outcomes.

## Package work completed versus implementation work remaining

Applied to specification package 1.2.0: version/header/schema/fixture updates, D-LR/D-CR wording, public-confidence shape, urgency resolution, general evidence adjustment, provider projections and fallback registry contract, classification examples, correction buffering/arbitration rules, isolated-content admission, owner split, host kit interface, updated checkers, changelog, provenance and checksums.

Not completed or claimed: production provider signature verification, real provider acceptance, actual legacy/typed engine code, concurrency/cancellation, durable reference storage, host rendering, real host conformance, built-wheel integration, product-quality evaluation, or access to the reported uncommitted working tree. Those are gated implementation deliverables, not residual ambiguity in the two decisions.
```

## Working root
You are running with read access from: /c/p911_projects/dev/xubb-agents
Read files under it when a finding depends on what the code or other repos actually do. Prefer verifying over assuming.

## Directory tree of the working root (depth 3, vendor/build dirs omitted)
```
.
.claude
.claude/worktrees
.claude/worktrees/wizardly-shamir-4b9f91
.github
.github/ISSUE_TEMPLATE
.github/ISSUE_TEMPLATE/bug_report.yml
.github/ISSUE_TEMPLATE/config.yml
.github/ISSUE_TEMPLATE/feature_request.yml
.github/PULL_REQUEST_TEMPLATE.md
.github/workflows
.github/workflows/contract-gate.yml
.gitignore
.pytest_cache
.pytest_cache/.gitignore
.pytest_cache/CACHEDIR.TAG
.pytest_cache/README.md
.pytest_cache/v
.pytest_cache/v/cache
.spec-review-context
CHANGELOG.md
CODE_OF_CONDUCT.md
CONTRIBUTING.md
LICENSE
README.md
SECURITY.md
docs
docs/CONTRACTS.yaml
docs/EXECUTIVE_SUMMARY.md
docs/INSIGHT_TYPES_ADOPTION.md
docs/INSIGHT_TYPES_FINAL_DECISIONS.md
docs/PLAYBOOK.md
docs/PROCESS.md
docs/README.md
docs/SPEC_INSIGHT_TYPES.md
docs/SPEC_INSIGHT_TYPES_AMENDMENT_2.md
docs/SPEC_LLM_MODERN_MODELS.md
docs/SPEC_REMOVE_LEGACY_CONTRACT.md
docs/SPEC_V2_2_HARDENING.md
docs/SPEC_V2_8_TYPED_REACH.md
docs/SPEC_V3_LIVE_ASSISTANCE.md
docs/archive
docs/archive/README.md
docs/archive/SPEC_V2.md
docs/archive/SPEC_V2_1_1_BUGFIX.md
docs/archive/SPEC_V2_1_HARDENING.md
docs/insight_contract_v1_2
docs/insight_contract_v1_2/CONTRACT_OWNERSHIP.json
docs/prompt_engineering_guide.md
docs/reference
docs/reference/insight_types_1.2.0
docs/technical_spec_agents.md
junit.xml
pyproject.toml
src
src/xubb_agents
src/xubb_agents.egg-info
src/xubb_agents.egg-info/PKG-INFO
src/xubb_agents.egg-info/SOURCES.txt
src/xubb_agents.egg-info/dependency_links.txt
src/xubb_agents.egg-info/requires.txt
src/xubb_agents.egg-info/top_level.txt
src/xubb_agents/__init__.py
src/xubb_agents/core
src/xubb_agents/library
src/xubb_agents/py.typed
src/xubb_agents/utils
tests
tests/__init__.py
tests/conftest.py
tests/fixtures
tests/fixtures/insight_contract_1.2.0
tests/qa_probes
tests/qa_probes/__init__.py
tests/qa_probes/test_probe_f1_facts_priority.py
tests/test_audit_e3dfaf1_regressions.py
tests/test_blackboard.py
tests/test_boundary_hardening_h1.py
tests/test_boundary_residuals_h3.py
tests/test_check_contracts.py
tests/test_compatibility.py
tests/test_conditions.py
tests/test_content_assurance_h2.py
tests/test_corrections_g3.py
tests/test_dynamic_agent.py
tests/test_engine.py
tests/test_envelope_failure_category.py
tests/test_evidence_catalog_g2.py
tests/test_insight_validation.py
tests/test_insight_vocabulary_g1.py
tests/test_isolated_content_c2.py
tests/test_legacy_acceptance_g0.py
tests/test_llm.py
tests/test_long_form_c1.py
tests/test_packaging.py
tests/test_provider_schema_g2.py
tests/test_readme_quickstart.py
tests/test_reasoning_validation.py
tests/test_registry_mutators.py
tests/test_reply_question_g3.py
tests/test_schemas.py
tests/test_tracing.py
tests/test_typed_acceptance_g1.py
tests/test_typed_reach_2_8.py
tests/test_wheel_smoke_script.py
tools
tools/check_contracts.py
tools/debugger.html
tools/wheel_smoke.py
```

## The specification under review: SPEC_REMOVE_LEGACY_CONTRACT.md
```markdown
# SPEC — Remove the `legacy_v2` insight contract

- **Status:** DRAFT — under review
- **Target release:** 3.0.0 (breaking)
- **Supersedes:** the contract-selection mechanism introduced with XUBB-ITC-1 §7.1

## 1. Summary

The library implements two insight contracts. `legacy_v2` is the original: a fixed five-value type vocabulary, a static per-schema instruction string, and an adapter that normalises a loosely-shaped model response. `typed_v1` (XUBB-ITC-1, added in 2.8.0) replaced it: a nine-value vocabulary, an instruction composed per run from the run's effective permissions, and boundary validation that rejects what it did not ask for.

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
- **`custom1.json` is deleted.** It declares `legacy_v2` only and carries a `typed_unsupported_reason`; with the contract gone it could never register, so shipping it would be shipping a schema guaranteed to fail.

### 2.5 The `_sync_state_to_legacy` bridge and the `memory_{agent_id}` channel

**Not in scope.** Despite the name, `_sync_state_to_legacy` projects blackboard state into the `shared_state` dict that agent code reads (E-2); the `memory_{agent_id}` pattern is a variable-channel convention (E-3). Neither is bound to the insight contract. They are renamed in §6, not removed.

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

`INV-19-reasoning-config-explicit`, `ITC-05.FW-silence-preserves-state`, `ITC-06.FW-unknown-type-rejects-no-relabel`, `ITC-13.FW-one-rejection-callback-per-result`, `ITC-24.FW-legacy-partial-acceptance-no-parse-mutation`, `INSIGHT-CONTRACT-SELECTION`, `ITC-17.FW-reply-is-a-permissioned-draft`, `TYPED-FAILURES-ARE-DIAGNOSTICS`, `TYPED-UNSUPPORTED-SCHEMA-NAMED`.

**Retire is not the same as delete the behaviour.** Several of these state a rule that still holds for the surviving path but is worded as a contrast between the two regimes — for example, that an unknown type is rejected rather than silently relabelled. Where the rule survives, it is **restated without the contrast and re-registered under its existing id**, keeping its test. Where the rule existed only because two regimes did, it is retired outright. The spec's build must classify each of the nine explicitly and say which of the two it is; a retirement that silently drops a live rule is the failure this section exists to prevent.

Twelve further entries use the word "legacy" without depending on the path; their statements are reworded and their ids and tests are untouched.

The debt ratchet (`debt_baseline`) must not grow. Registry count moves from 89 by however many of the nine are retired outright.

## 7. Test plan

1. **The contract gate, strict.** `tools/check_contracts.py --strict` against the JUnit report: G1 bijection, G2 no silent skips, G3 ran-and-passed. Full coverage is the release gate.
2. **The surviving path is unchanged.** Every typed test passes untouched. A test that had to be *edited* to keep passing is a signal that typed behaviour moved, which §4 forbids — each such edit is justified in the commit message or reverted.
3. **Negative controls**, per `docs/PROCESS.md`: for each retired-but-restated contract, the inverse case that must fail. Specifically, a schema with no `typed_adapter` must be refused at registration and the refusal must name it; an unknown type must still reject without relabelling.
4. **Construction fails loudly.** `AgentEngine(insight_contract="legacy_v2")` raises, and the test asserts it rather than asserting silence.
5. **Probes.** `tests/qa_probes/` are hard gates and are neither deleted nor `xfail`-ed. Any probe that exercises the legacy path is rewritten against the typed path if its defect can still occur, and retired with a written reason only if the defect is structurally impossible now.
6. **Wheel smoke.** `tools/wheel_smoke.py` against the built artifact.

## 8. Risks

- **A live rule retired by accident** (§6). Mitigated by requiring each of the nine to be classified explicitly, and by the negative controls in §7.3.
- **Typed behaviour drifting under cover of a deletion.** Mitigated by §4 and by §7.2: an edited typed test is a red flag, not a routine consequence.
- **A schema in the wild with no `typed_adapter`.** It stops registering. This is intended and is the point of §5's loud failure, but it is a real break and the CHANGELOG must say so in those words.

## 9. Not a goal

Reducing line count. The measure of this change is that one regime governs insight validation, not that a number went down. A deletion that leaves the surviving path harder to reason about has failed even if it removes more lines.
```
