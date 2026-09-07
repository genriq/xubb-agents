# Documentation

## Current runtime and quality process

| Doc | What it is |
|-----|-----------|
| [PLAYBOOK.md](PLAYBOOK.md) | The deep guide: how to design and compose agents well — doctrine, patterns, anti-patterns, and a golden-path build. |
| [technical_spec_agents.md](technical_spec_agents.md) | Data models and implementation reference. |
| [prompt_engineering_guide.md](prompt_engineering_guide.md) | Writing effective agent prompts. |
| [SPEC_LLM_MODERN_MODELS.md](SPEC_LLM_MODERN_MODELS.md) | The current release spec (v2.5/v2.6 modern-model compatibility; invariants INV-15…INV-19). |
| [SPEC_V2_2_HARDENING.md](SPEC_V2_2_HARDENING.md) | The v2.2 hardening spec (invariants INV-1…INV-14). |
| [PROCESS.md](PROCESS.md) | How every documented contract stays true: the CI-enforced contract-accuracy gate. |
| [CONTRACTS.yaml](CONTRACTS.yaml) | The machine-checked contract registry the gate reads. |
| [EXECUTIVE_SUMMARY.md](EXECUTIVE_SUMMARY.md) | High-level overview: the model, the architecture, and use cases. |
| [archive/](archive/) | Superseded specs, kept for provenance (see the folder's own README). |

## Insight contract — specification 1.2.0

These documents describe the agreed design direction. **Implementation status:** gate **G0 (legacy safety)** is implemented in this tree — declared gates, unknown-type rejection, D-LR partial acceptance, sanitized diagnostics, no parse-time mutation — and registered as framework contracts ITC-04/05/06/13/23/24 `.FW`. Every later gate (nine-purpose enum, `typed_v1`, provider schemas, evidence, interactions, long-form) is staged, not shipped, and there is no Xubb package-version bump. Existing runtime/API documentation above remains authoritative for what is shipped.

| Doc | What it is |
|-----|-----------|
| [SPEC_V3_LIVE_ASSISTANCE.md](SPEC_V3_LIVE_ASSISTANCE.md) | **PROPOSED** — the live-assistance roadmap the contract sits inside: insight lifecycle, delivery, timing & principal, session state & budgets, evaluation (invariants INV-20…INV-37), cross-referenced item by item to the type contract (Appendix C). |
| [reference/insight_types_1.2.0/](reference/insight_types_1.2.0/) | Packaged reference artifacts, manifest-verified: local and provider JSON schemas, response contract, fallback-signature registry, host conformance kit procedure, provenance. Reference material, not runtime. |
| [SPEC_INSIGHT_TYPES.md](SPEC_INSIGHT_TYPES.md) | Consolidated repository edition: nine human-facing purposes, typed/legacy validation, consulting subtypes, permissioned interactions, and long-form content/execution requirements. |
| [SPEC_INSIGHT_TYPES_AMENDMENT_2.md](SPEC_INSIGHT_TYPES_AMENDMENT_2.md) | Nine engineering-review amendments and the final reconciled rulings. |
| [INSIGHT_TYPES_FINAL_DECISIONS.md](INSIGHT_TYPES_FINAL_DECISIONS.md) | Exact D-LR legacy partial-rejection and D-CR confidence-neutral ranking decisions. |
| [INSIGHT_TYPES_ADOPTION.md](INSIGHT_TYPES_ADOPTION.md) | Source-package provenance, adoption scope, and item-level cross-reference preserving the separate live-assistance roadmap. |
| [Contract ownership](insight_contract_v1_2/CONTRACT_OWNERSHIP.json) | 35 proposed parent requirements mapped to 58 framework/host/end-to-end leaves; no implementation coverage is claimed. |

The full reference-code and fixture ZIP remains a separately supplied design artifact; this documentation adoption does not claim to import those executables or certify Xubb/host/provider behavior. See the adoption note for source hashes and validation boundaries.

New here? Start with the [README](../README.md) quickstart, then read the [PLAYBOOK](PLAYBOOK.md).
