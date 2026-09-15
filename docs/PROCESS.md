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

## The documentation gate (`tools/check_api_docs.py`)

A second gate, added in 3.1.4, runs in the same CI job. The contract gate governs
**behaviour**; this one governs the **reference**, because a green contract registry
says nothing about whether a public member is documented at all.

| Gate | Check |
|------|-------|
| **A1** | Every public member of a declared class appears in `docs/api/inventory.yaml`. |
| **A2** | Every inventory entry still exists in the code — so a deleted member cannot linger as documentation. |
| **A3** | The `<!-- GENERATED:Name -->` fact blocks in the reference are current: signatures, defaults and requiredness are regenerated from the shipped code and must match. |
| **A4** | Every declared class, constant and diagnostic code has a section to read, and every diagnostic carries a lifecycle status. |
| **A5** | A diagnostic with no emitter left in `src/` is documented as retired — and one that *is* still emitted may not be documented as retired. |

A1 and A2 hold in both directions against a hand-maintained inventory, so widening
the public surface is a deliberate act with a documentation cost, not an accident.
Exclusions are recorded in the inventory rather than assumed.

## What a green gate proves — and what it does not

Both gates are narrow on purpose, and it is worth being exact about their reach,
because each has already been over-read once in this repository's own documents.

**The contract gate proves** that every rule registered in `CONTRACTS.yaml` names a
test that exists, ran, and passed in this build. It does **not** prove that the
registry is complete, that a registered test reaches the input path a user actually
supplies, or that any prose is true. A rule nobody registered is not covered by a
green gate; neither is a rule whose test pokes an attribute after construction when
the defect lives in the constructor. Two of the six defects found by the
post-implementation review of 3.1.0 were of exactly that shape, against a gate that
was green at the time.

**The documentation gate proves** that the declared public surface is present in the
reference and that the generated facts in it match the code. It does **not** prove
that a hand-written explanation is correct, current, or useful. A1–A5 cannot read a
paragraph. Purpose, ownership, lifecycle, units and failure behaviour are checked by
a person or not at all.

**What executes rather than being asserted about:** the runnable examples. Every
fenced block marked `<!-- runnable -->` in the guides, the README's two examples, and
the prompt guide's documented envelopes are run against the real engine in CI, with
only the provider boundary substituted (`GUIDE-RECIPES-VERIFIED`,
`README-EXAMPLES-NOT-DEPRECATED`, `PROMPT-GUIDE-ENVELOPES`). That is the only
mechanism here that tests a documented *claim* rather than a documented *name*, and
it is why a recipe labelled current is one that ran.

Generated documentation is accurate by construction only for the mechanical facts it
derives. Nothing in this repository licenses a broader claim than that.

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

## Releasing

There was no written release procedure until 2026-09-15, and the cost showed: nine
tagged versions — `v2.8.0` through `v3.1.5`, including the breaking `v3.0.0` — had
been tagged and pushed but never published as GitHub Releases. The repository's
Releases page therefore advertised **`v2.7.0` as Latest** while the library shipped
`3.1.6`, and the breaking change in between had no release page at all. Every step
below exists because it was missed.

**Every release, in order:**

1. **Version** — bump `pyproject.toml` and `src/xubb_agents/__init__.py` together.
   They must agree; a release is tagged on a commit that declares its own version.
2. **Changelog** — add the entry under its version heading with a date. The release
   notes are written from this, so it is the deliverable, not a summary of one.
3. **Gates** — the full suite, `tools/check_contracts.py --strict`, and
   `tools/check_api_docs.py`, all green. Record the numbers in the PR.
4. **Merge** the release PR (the owner merges; see `CONTRIBUTING.md`).
5. **Tag** the merge commit, annotated, `vX.Y.Z`. Verify the tag's commit declares
   that same version in both files before pushing it. Push the tag.
6. **Publish the GitHub Release** against that existing tag — never let the release
   form create or move a tag. Notes come from the changelog entry. Mark the newest
   stable version **Latest**, and only that one.
7. **Verify installation** from a clean checkout of the tag, using the method the
   README documents. A release page must not print an install command nobody ran.
   This repository installs from a checkout (`pip install -e .`); it does **not**
   publish to PyPI, and whether it should is a separate decision — until it is made,
   no release note may imply a `pip install xubb-agents` that does not exist.
8. **Pin documentation links** in the release notes to that release's tag
   (`/blob/vX.Y.Z/docs/...`), not to `main`. A release page is a historical record:
   links to `main` silently re-point as the docs change, so an old release ends up
   describing instructions that were never true for it.

**Retrospective releases.** If a version is published after the fact, say so in the
notes, name the date the record was created, and state that the tag is unchanged and
predates it. Do not backdate, and do not mark a retrospective release Latest.

## Rules for contributors

1. Document a behavior → register it in `CONTRACTS.yaml` with a rule-asserting
   test, in the same change.
2. Never weaken a `covered` entry to make a build pass; fix the code or amend
   the contract explicitly.
3. Fail closed: error paths in this framework return safe defaults and log,
   they do not guess (see `CONDITIONS-FAIL-CLOSED` for the archetype).
