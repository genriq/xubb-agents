# Contributing to xubb-agents

Thanks for your interest. This framework is **spec-driven**: its identity is a
contract-accuracy gate that keeps documentation from silently drifting out of sync with
the code. Contributions are expected to keep that gate green.

## Getting set up

```bash
# 1. Fork github.com/genriq/xubb-agents on GitHub, then:
git clone https://github.com/<your-username>/xubb-agents.git
cd xubb-agents
pip install -e ".[dev]"

# 2. Run the suite + contract gate (what CI runs):
pytest tests -q --junitxml=junit.xml
python tools/check_contracts.py --junit junit.xml
```

The test suite is **fully offline** — no OpenAI API key and no network access are
required; every LLM interaction is faked. (`tools/check_contracts.py` runs from a source
checkout, not from an installed copy.)

## Ground rules

1. **A behavioral change ships with its contract + test in the same PR.** If you change
   what the framework does, add or update the matching entry in
   [`docs/CONTRACTS.yaml`](docs/CONTRACTS.yaml) and a rule-asserting test that the entry
   names. See [`docs/PROCESS.md`](docs/PROCESS.md) for how the gate works — the F-1
   escape it exists to prevent, the G1/G2/G3 checks, the debt ratchet, and negative
   controls.
2. **The suite and the gate must pass.** CI runs the suite once and feeds the result to
   `tools/check_contracts.py` (see the commands above — they work from any checkout
   directory).
3. **Docs are code.** READMEs and specs are held to the same accuracy bar as the code —
   the README quickstart is executed in CI. Don't document behavior that isn't there.
4. **Open an issue first for large or architectural changes.** Changes land spec-first;
   a short design discussion up front saves a rewrite.

## Submitting a change

1. Create a branch on your fork (`feat/<topic>` or `fix/<topic>`).
2. Make the change, keeping the suite and gate green locally.
3. Add a `CHANGELOG.md` entry under `[Unreleased]` for anything user-visible.
4. Push to your fork and open a pull request — the
   [PR template](.github/PULL_REQUEST_TEMPLATE.md) walks through the checklist, and the
   `contract-gate` workflow runs automatically on the PR (it needs no secrets, so it
   passes for fork PRs).

## Reporting bugs and vulnerabilities

- Bugs and feature requests: open a [GitHub issue](https://github.com/genriq/xubb-agents/issues)
  — the issue forms ask for the version/repro details that make reports actionable.
- Security vulnerabilities: **do not** open a public issue — follow [SECURITY.md](SECURITY.md).

## Style

- Target Python 3.11+.
- Match the surrounding code; keep comments load-bearing (explain *why*, not *what*).

## Code of conduct

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
