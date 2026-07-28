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
| **G1** | Registry ↔ test **bijection**: every `covered` contract names a test that exists at the node level (`file::Class::test`). |
| **G2** | **Invariant marker coverage**: tests guarding a documented contract carry the `@pytest.mark.invariant` marker, so contract-asserting tests are identifiable and countable. |
| **G3** | The named test **actually ran and passed** in this build (verified against the JUnit report — a collected-but-skipped test does not count). |

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

## Rules for contributors

1. Document a behavior → register it in `CONTRACTS.yaml` with a rule-asserting
   test, in the same change.
2. Never weaken a `covered` entry to make a build pass; fix the code or amend
   the contract explicitly.
3. Fail closed: error paths in this framework return safe defaults and log,
   they do not guess (see `CONDITIONS-FAIL-CLOSED` for the archetype).
