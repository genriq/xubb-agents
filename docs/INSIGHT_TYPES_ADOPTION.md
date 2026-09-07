# Insight contract 1.2.0 — repository adoption and roadmap cross-reference

**Date:** September 7, 2026  
**Scope:** Documentation and acceptance-ownership adoption only. No runtime behavior change.  
**Baseline inspected:** `f83fc5b1e3d39da176be0ef30f40eefdd9fe51bc`

## Entry points

- [Repository specification](SPEC_INSIGHT_TYPES.md)
- [Amendment 2 record](SPEC_INSIGHT_TYPES_AMENDMENT_2.md)
- [Final D-LR / D-CR decisions](INSIGHT_TYPES_FINAL_DECISIONS.md)
- [Acceptance ownership map](insight_contract_v1_2/CONTRACT_OWNERSHIP.json)

The specification is a repository-adapted edition of the design package, not a byte-identical replacement for the distributed Markdown. It preserves the nine-purpose vocabulary and final Amendment 2 decisions while using repository links and a consolidated requirements presentation. Runtime implementation and capability enablement remain gated work.

## Provenance and boundaries

The source was the conversation attachment `Xubb_Insight_Types_Specification_v1.2.zip`:

```text
archive SHA-256
891afe2e2255d9f5d7da629b145bb046324f28b196282377c4fac59d8f7f4de1

original packaged SPEC_INSIGHT_TYPES.md SHA-256
c834b75667069c3f4be91b6e6384f594acee72a5e9217416396b3f607d376ff2
```

The original archive's manifest verified before execution of its local checkers. The local check runner was rerun during this adoption and passed 71 schema fixtures, 62 content/admission fixtures, 59 amendment-policy fixtures, 48 provider projection/codec round trips, nine synthetic long-body round trips, 19 base consistency checks, and 77 amendment consistency/negative controls. These results belong to that separately supplied reference package, not to the runtime or the repository-adapted prose. Rerunning its report can change environment-dependent report hashes; the archive identity above remains the source of provenance.

The reference package's full schemas, compiler/codec, fixture datasets, reports, and executable host kit are **not imported by this documentation change**. The ownership map is included as structured data. The source archive remains a separate supplied artifact; this file does not invent a public download URL for it or claim that its executables are installed in Xubb.

The engineering team reported a revised live-assistance specification and an amendment record in its uncommitted working tree. Neither was present in the inspected remote main branch, and no open PR exposed those edits. They were not overwritten or reconstructed as though their exact bytes had been inspected. The cross-reference below records the required reconciliation when that work is committed.

## Item-level reconciliation

| Existing proposal item | Disposition under XUBB-ITC-1 1.2.0 |
|---|---|
| IT-1 through IT-6 | Retire in favor of the nine-purpose vocabulary, information alias, diagnostic separation, and strict validation contract. |
| SO-1 | Retain provider integration; derive projections from the authoritative contract, validate locally, and enable auto fallback only for verified exact signatures. |
| LH-1 | Apply D-LR: recoverable legacy insight-only rejection, independently validated/authorized domain retention, explicit partial status, fatal whole-response rejection, no parsing mutation. |
| UR-1 / INV-22 | Explicit valid urgency, then agent override, then versioned type fallback. Invalid explicit values reject; urgency never bypasses policy. |
| CF-1 | Runtime-derived confidence_provided with numeric public compatibility. Missing/unknown provenance is not certainty. |
| LC-1 identity | Consolidate under type-contract runtime identity and lifecycle requirements. |
| LC-1 anchoring | Retain as snapshot references to exposed context; durable cross-turn identity requires retained revisions/stable source IDs. |
| LC-2 topic / general supersession | Retain. Correcting an earlier error does not cover every ordinary replacement of outdated advice. |
| LC-3 restraint | Retain. Default rank key is urgency, negative agent priority, and stable merge order. Confidence is ignored for every candidate by default. |
| LC-4 ordinary insight outcomes | Retain. Question answers are not shown/dismissed/acted/spoken events. Host reports do not prove correctness or actual perception. |
| LC-5 diagnostics | Consolidate with framework-only sanitized error and validation diagnostics. |
| DL-1 delivery | Retain certified early insight delivery and phase-staged deterministic state commits. Raw callbacks are not a display API. Hold unresolved correction-bearing responses whole. |
| DL-2 deadlines | Retain closure/fencing and define the correction arbitration candidate set at close. Do not apply a short live-turn deadline as the content-task execution policy. |
| DL-3 through DL-5 | Retain supersession, session serialization, per-agent retry control, and their tests. |
| DL-6 / INV-37 | Retain isolated result-only content execution, frozen snapshot identity, task/capacity separation, closure, and currentness; otherwise explicit pause/post-session. |
| Timing / principal | Retain host-declared identity/roles and transcript-aware eligibility work. |
| Session state / budgets | Retain runtime ownership, persistence/isolation, resource admission and accounting work. |
| Evaluation / replay | Retain. Grounding references in this contract are not evidence that product outcomes improved. |

No blanket replacement of Workstreams A and B is approved. Implemented baseline contracts must not be weakened to make a new change pass.

## Decisions to pin in the pending roadmap

**Legacy:** Keep insight-only rejection for recoverable insight errors, with partial observability and independent domain authorization. Fatal envelope/domain/authorization failures reject whole. No mode may mutate durable state during parsing. Typed mode remains whole-response atomic.

**Ranking:** Replace missing-confidence-last and conditional pairwise comparison with `(urgency_order, -agent_priority, stable_merge_order)` for all candidates. Stable order is phase, registration index, candidate ordinal; never completion order. Fact precedence is unchanged.

**Terminology:** FORCE is a host execution trigger, not an authorization credential and not isolation. Outcomes are host-reported observations, not proof of advice correctness. Keep grounding and Evaluation concepts distinct.

## Test ownership and activation

The ownership map defines 35 parent requirements and 58 unique scoped leaves. It records responsibility, not implementation status. Framework leaves need real passing framework tests before any CONTRACTS.yaml coverage claim; host leaves need actual host/build results; end-to-end leaves need a clean installed wheel with the named host.

This change does not edit runtime InsightType, package version, model defaults, or the covered contract registry. The current runtime still has its existing six-member enum. Do not advertise the proposed new capabilities as usable merely because their design is now in the repository.

## Integration order

Use dependency gates, not automatic minor-version assignments. Close unsafe legacy parsing first. Develop vocabulary, typed acceptance, diagnostics and provider-schema derivation together. Enable grounded analysis and special interactions only when their required paths pass. Long-form storage/reading may proceed independently of live streaming; active extended generation requires real isolation or a declared pause. Built-wheel and host checks accompany each enabled capability.
