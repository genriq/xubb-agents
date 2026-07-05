# Contributing to xubb-agents

Thanks for your interest. This framework is **spec-driven**: its identity is a
contract-accuracy gate that keeps documentation from silently drifting out of sync with
the code. Contributions are expected to keep that gate green.

## Ground rules

1. **A behavioral change ships with its contract + test in the same PR.** If you change
   what the framework does, add or update the matching entry in
   [`docs/CONTRACTS.yaml`](docs/CONTRACTS.yaml) and a rule-asserting test that the entry
   names. See [`docs/PROCESS.md`](docs/PROCESS.md) for how the gate works — the F-1
   escape it exists to prevent, node-level bijection, the debt ratchet, and negative
   controls.
2. **The suite and the gate must pass.** CI runs the suite once and feeds the result to
   `tools/check_contracts.py`. Locally:
   ```bash
   pip install -e ".[dev]"
   pytest tests -q --junitxml=junit.xml
   python tools/check_contracts.py --junit junit.xml
   ```
3. **Docs are code.** READMEs and specs are held to the same accuracy bar as the code —
   the README quickstart is executed in CI. Don't document behavior that isn't there.
4. **Open an issue first for large or architectural changes.** Changes land spec-first;
   a short design discussion up front saves a rewrite.

## Reporting bugs and vulnerabilities

- Bugs and feature requests: open a [GitHub issue](https://github.com/genriq/xubb-agents/issues).
- Security vulnerabilities: **do not** open a public issue — follow [SECURITY.md](SECURITY.md).

## Style

- Target Python 3.11+.
- Match the surrounding code; keep comments load-bearing (explain *why*, not *what*).
