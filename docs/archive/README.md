# Archived Specifications

These specs are **historical**, superseded by the shipped specs in
[`docs/`](../README.md): [`SPEC_LLM_MODERN_MODELS.md`](../SPEC_LLM_MODERN_MODELS.md)
(current release spec, v2.5/v2.6) and [`SPEC_V2_2_HARDENING.md`](../SPEC_V2_2_HARDENING.md)
(v2.2 hardening).

> ⚠️ **Do not treat the code/pseudocode in these documents as a reference for current
> behavior.** Reference implementations here predate later contract corrections and may
> directly contradict the shipped code. In particular, `SPEC_V2.md` §6.5.4 shows the old
> confidence-only fact-resolution that the v2.2 **F-1** fix corrected. For the live,
> machine-checkable contract use [`docs/CONTRACTS.yaml`](../CONTRACTS.yaml) and the
> [CHANGELOG](../../CHANGELOG.md).

| Spec | Release | Status |
|------|---------|--------|
| `SPEC_V2.md` | v2.0.3 | Archived — full v2.0 design/architecture reference |
| `SPEC_V2_1_HARDENING.md` | v2.1.0 | Archived — superseded by v2.2 |
| `SPEC_V2_1_1_BUGFIX.md` | v2.1.1 | Archived — superseded by v2.2 (note: its provisional INV-9/INV-10 numbering was reassigned in v2.2) |

Kept for per-release provenance and design rationale. The **current** spec lineage and
invariant numbering (INV-1 … INV-19) live in `SPEC_V2_2_HARDENING.md` (INV-1 … INV-14),
`SPEC_LLM_MODERN_MODELS.md` (INV-15 … INV-19), and `CONTRACTS.yaml`.
