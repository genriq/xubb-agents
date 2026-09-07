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
