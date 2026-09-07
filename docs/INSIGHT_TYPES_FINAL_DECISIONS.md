# Final decisions for the engineering handoff

**Package:** XUBB-ITC-1 1.2.0 / Amendment 2  
**Status:** Recommended decisions incorporated into this proposed specification. No runtime implementation or working-tree verification.

## D-LR — Legacy rejection scope

Keep **insight-only rejection in legacy mode** for recoverable insight classification/gate/field errors. Commit only independently validated and authorized domain channels through the engine merge. Return an explicit `partial` acceptance status and a sanitized diagnostic; do not report the result as successful insight delivery or deliberate silence. A legacy result with no retained domain updates is rejected.

Malformed/truncated outer envelopes, invalid domain payloads, reserved/control-state writes, forged runtime ownership and failed authorization reject the **entire response**. Action-bearing data sidecars are not eligible for partial acceptance. No mode may mutate durable private memory while parsing. Valid legacy memory may change after the engine commits it; that is intentional and is not a pre-acceptance leak.

Typed mode remains whole-response atomic: an invalid candidate rejects all domain effects from that agent response. Preserve usage/failure telemetry in both modes. This distinction belongs in the compatibility inventory and test names.

**Required roadmap edit:** Keep LH-1's narrow compatibility scope, adding `partial` observability, independent state authorization, and fatal-envelope/domain exclusions. Do not restore coercion to OBSERVATION.

## D-CR — Missing confidence and default ranking

Choose **neutral treatment**, not "missing sorts below every provided value." Default insight ranking ignores confidence entirely and uses:

```text
(urgency_order, -agent_priority, stable_merge_order)
```

The stable order is captured from phase, registration index and candidate ordinal, not completion order. Both declared and undeclared confidence use this same total key. Confidence remains diagnostic/contextual data; a future confidence-aware ranking policy requires explicit comparability/calibration evidence and a separately specified total order.

Public confidence stays numeric for compatibility. The runtime derives `confidence_provided`; a false or absent/unknown flag means the numeric placeholder is not an interpretable model estimate. Updated hosts must not show it as certainty.

Do not implement "compare confidence if both have it, otherwise compare merge order" pairwise: it can cycle. A=.9/order3, B=unknown/order2, C=.1/order1 produces A<C, C<B, B<A in preference terms. A fixed tuple avoids that inconsistency.

**Required roadmap edit:** Replace CF-1 / LC-3's missing-last rule with the default comparator above. Leave existing Blackboard fact precedence unchanged.

## Two terminology corrections

1. `FORCE` is an execution trigger reflecting host intent. It is neither an authorization credential nor an isolated execution lane. All ordinary permissions and content-path checks still apply.
2. Ordinary outcome events are **host-reported evidence of exposure/adoption**. They do not prove actual human perception, successful action, or advice correctness. Keep grounding references separate from Evaluation/replay evidence.

## Scope and repository status

The user's pasted consolidation/amendment record was incorporated. This package does not claim to inspect or alter the engineering team's uncommitted working tree. Use an item-level cross-reference when adopting it; preserve SO-1, anchoring, topic/supersession, restraint, ordinary outcomes, delivery, session controls, budgets and Evaluation/replay.
