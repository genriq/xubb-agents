# Public Release Readiness

**Status:** audit applied 2026-07-04 (5-auditor sweep: dead code, docs, secrets +
full git history, internal references, packaging). Every criterion below is
VERIFIED, not asserted. Two owner decisions remain at the bottom.

## Verified criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | No secrets in working tree | ✅ | Credential-shape greps (api keys, tokens, `sk-`, `AKIA`, `ghp_`, private keys) across all tracked files: only placeholders (`"your-openai-key"`) |
| 2 | No secrets in git history | ✅ | Pickaxe over all 53 commits (`-S` for key shapes, hardcoded assignments, deleted files, binary blobs string-scanned): zero real credentials |
| 3 | No dead code | ✅ | Zero TODO/FIXME/HACK; zero commented-out blocks; unused imports removed (engine `Fact`, callbacks `Dict/Any`, models `TYPE_CHECKING`); debug-only `elif` branch removed (agent.py); every public method now consumed AND tested (keyword-query test added) |
| 4 | No IDE/local cruft tracked | ✅ | `.code-workspace` untracked; `.gitignore` covers caches, `.claude/`, `.mypy_cache/`, `.benchmarks/` |
| 5 | Self-contained docs (no private references) | ✅ | All `DEVELOPMENT_PROCESS.md` / private-memory / internal program-numbering citations replaced with the public [PROCESS.md](PROCESS.md) or self-contained prose; personal email replaced with `@genriq` at tree tip |
| 6 | Working install | ✅ | Wheel built and inspected: all 6 `library/schemas/*.json` ship (was BROKEN — silent degradation to fallback schema); drift-locked by `tests/test_packaging.py` |
| 7 | Version identity | ✅ | `2.3.0` consistent across pyproject / `__init__` / README / specs (locked by test); semver-correct minor bump (`replace_agents` is new API) |
| 8 | README serves an external reader | ✅ | Copy-paste-runnable quickstart (construction verified against the real API), Python/deps stated, `replace_agents` in the API reference, zone taxonomy explained, contribution posture stated |
| 9 | CHANGELOG current | ✅ | `[2.3.0]` covers everything on main since 2.2.0: contract gate, `replace_agents`, interval fix, fail-closed mode fix, certification, packaging fix |
| 10 | Maturity signal consistent | ✅ | "Beta — production-hardened" everywhere (matches the PyPI `4 - Beta` classifier) |
| 11 | Quality gates green | ✅ | Suite 267 passed; contract gate 24/24 covered, debt ratchet at 0 |
| 12 | Honest marketing | ✅ | "first open framework" dropped; body-language claim replaced with a text-feasible example; ecosystem table labeled "planned" |

## Accepted (known, deliberate)

- `conftest.py` ships inside the wheel (it is a root-level module of the
  package; setuptools' exclude-package-data cannot remove real modules).
  Harmless: it only affects pytest collection when testing an installed copy.
- Local `black`/`mypy` (current versions) flag pre-existing style/typing drift,
  byte-identical on main vs this branch (verified against a pristine archive);
  CI gates are pytest + the contract gate, which are green. A tool-version pin
  or a cleanup pass is future work, not a release blocker.
- `tools/debugger.html` loads Vue/Tailwind/FontAwesome from public CDNs without
  SRI pins. Header now marks it dev-only.
- `docs/archive/` ships internal-era specs verbatim as history (its README says
  so). They reference the consuming product by name, which is intentional.

## Owner decisions (before flipping the repo public)

1. **Git history identity.** All 53 commits are authored `genriq
   <enriquegil@gmail.com>`; historical blobs also contain the other personal
   email (removed at tip) and AI-assistance commit trailers. Options:
   (a) publish as-is (the handle matches github.com/genriq; the email publishes
   with every push anyway unless GitHub's private-email setting is on), or
   (b) publish a fresh squashed initial commit — cleanest narrative, also
   drops historical `.pyc`/egg-info bloat, loses blame history.
2. **Tags.** After the open PRs merge: `git tag v2.2.0 <2026-06-08 release
   commit>` and `git tag v2.3.0 <post-merge main>`, push both. (Baseline
   candidate identified by the audit: the 06-08 release/closeout commit.)

## Re-audit rule

Any future change that touches packaging, docs structure, or adds a dependency
re-runs the relevant table row before the next tag.
