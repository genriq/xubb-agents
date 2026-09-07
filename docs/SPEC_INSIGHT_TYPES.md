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
