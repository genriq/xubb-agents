#!/usr/bin/env python3
"""tools/check_contracts.py - the accuracy gate (G1/G2/G3; DEVELOPMENT_PROCESS.md §4).

This is the artifact that turns the F-1 escape ("a documented contract with no
asserting test") into a day-one red build. It reads ``docs/CONTRACTS.yaml`` and
enforces, for every ``covered`` contract, that each named test:

  * exists / is collectible (no missing node),
  * is not skipped, and
  * passes on the current tree (G1 bijection + G3: the test must actually run).

``to_verify`` / ``uncovered`` / ``pending_v2.2`` entries are honest debt: they are
REPORTED (coverage %) but do not hard-fail the default gate, so the framework is
not red-built before the R1 back-fill lands. A ``debt_baseline`` in the registry
ratchets that debt: the gate fails if the debt COUNT grows beyond the baseline,
so debt can shrink but never silently accrete. ``--strict`` additionally requires
a passing test for EVERY entry - the P4 / L6 release gate (16/16).

A ``failing_probe`` entry is inverted: its probe must currently FAIL (it documents
an unimplemented rule); a probe that unexpectedly passes is itself a gate failure.

Design: the decision logic lives in :func:`evaluate`, a PURE function over a
``{test_ref: outcome}`` map, so it is fast and deterministic to unit-test. The CLI
(:func:`main`) obtains real outcomes from a JUnit report - either one it runs
itself, or one passed via ``--junit`` (so CI runs the suite exactly once). The gate
FAILS CLOSED: if trustworthy outcomes cannot be obtained, it errors red.

Usage:
    python tools/check_contracts.py [--strict] [--registry PATH] [--junit PATH]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import yaml  # type: ignore[import-untyped]

# -- status vocabulary (mirrors the CONTRACTS.yaml header) -----------------------
STATUS_COVERED = "covered"
STATUS_TO_VERIFY = "to_verify"
STATUS_FAILING_PROBE = "failing_probe"
STATUS_PENDING = "pending_v2.2"
STATUS_UNCOVERED = "uncovered"
VALID_STATUSES = {
    STATUS_COVERED,
    STATUS_TO_VERIFY,
    STATUS_FAILING_PROBE,
    STATUS_PENDING,
    STATUS_UNCOVERED,
}
# Statuses that are honest debt (reported, not a hard fail in default mode).
DEBT_STATUSES = {STATUS_TO_VERIFY, STATUS_UNCOVERED, STATUS_PENDING}
# Statuses that must name at least one test.
TEST_REQUIRED_STATUSES = {STATUS_COVERED, STATUS_TO_VERIFY, STATUS_FAILING_PROBE}

# Outcome vocabulary for a single test reference.
PASSED, FAILED, SKIPPED, MISSING = "passed", "failed", "skipped", "missing"


class GateError(Exception):
    """The gate cannot obtain trustworthy test outcomes; callers must fail closed."""


# -- data model ------------------------------------------------------------------
@dataclass
class Report:
    ok: bool = True
    hard_failures: List[Tuple[str, str, str]] = field(
        default_factory=list
    )  # (id, ref, reason)
    wellformed_errors: List[str] = field(default_factory=list)
    debt: List[str] = field(default_factory=list)
    covered: int = 0
    total: int = 0

    @property
    def coverage_pct(self) -> float:
        return 0.0 if self.total == 0 else round(100.0 * self.covered / self.total, 1)


def test_refs(contract: dict) -> List[str]:
    """Every test reference on a contract: any key starting with ``test`` whose
    value is a non-empty string other than the sentinel ``MISSING``."""
    refs = []
    for key, val in contract.items():
        if not key.startswith("test"):
            continue
        if isinstance(val, str) and val.strip() and val.strip() != "MISSING":
            refs.append(val.strip())
    return refs


# -- well-formedness (the registry itself must be valid) -------------------------
def validate_registry(registry: dict) -> List[str]:
    errors: List[str] = []
    contracts = registry.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        return ["registry has no `contracts` list"]
    seen_ids = set()
    for i, c in enumerate(contracts):
        where = c.get("id", f"<entry #{i}>") if isinstance(c, dict) else f"<entry #{i}>"
        if not isinstance(c, dict):
            errors.append(f"{where}: not a mapping")
            continue
        if not c.get("id"):
            errors.append(f"<entry #{i}>: missing `id`")
        elif c["id"] in seen_ids:
            errors.append(f"{where}: duplicate id")
        else:
            seen_ids.add(c["id"])
        if not c.get("statement"):
            errors.append(f"{where}: missing `statement`")
        if not c.get("source"):
            errors.append(f"{where}: missing `source`")
        status = c.get("status")
        if status not in VALID_STATUSES:
            errors.append(
                f"{where}: invalid status {status!r} (allowed: {sorted(VALID_STATUSES)})"
            )
        refs = test_refs(c)
        if status in TEST_REQUIRED_STATUSES and not refs:
            errors.append(f"{where}: status={status} but names no test")
        # A covered contract must name a node-level test (file-level bijection is
        # too weak to prove the RULE is asserted).
        if status == STATUS_COVERED:
            for r in refs:
                if "::" not in r:
                    errors.append(
                        f"{where}: covered contract names a file-level test {r!r}; "
                        f"require a node-level ref (file.py::Class::test)"
                    )
    return errors


# -- the pure decision core (unit-tested directly) -------------------------------
def evaluate(registry: dict, outcomes: Dict[str, str], strict: bool = False) -> Report:
    """Classify every contract against a resolved ``{test_ref: outcome}`` map.

    Hard failures (any -> red build):
      * registry not well-formed;
      * a ``covered`` contract whose named test is missing / skipped / failing;
      * a ``failing_probe`` whose probe is missing or unexpectedly passing;
      * the debt count exceeds ``debt_baseline`` (debt may shrink, never grow);
      * in ``strict`` mode, any debt entry without a passing test.
    """
    wf = validate_registry(registry)
    contracts = registry.get("contracts", []) if not wf else []
    rep = Report(wellformed_errors=wf, total=len(contracts))

    for c in contracts:
        status = c.get("status")
        refs = test_refs(c)
        if status == STATUS_COVERED:
            rep.covered += 1
            for r in refs:
                o = outcomes.get(r, MISSING)
                if o != PASSED:
                    rep.hard_failures.append((c["id"], r, o))
        elif status == STATUS_FAILING_PROBE:
            for r in refs:
                o = outcomes.get(r, MISSING)
                if o == PASSED:
                    rep.hard_failures.append((c["id"], r, "probe-unexpectedly-passing"))
                elif o == MISSING:
                    rep.hard_failures.append((c["id"], r, MISSING))
        elif status in DEBT_STATUSES:
            rep.debt.append(c["id"])
            if strict:
                if not refs or any(outcomes.get(r, MISSING) != PASSED for r in refs):
                    bad = [outcomes.get(r, MISSING) for r in refs] or ["no-test"]
                    rep.hard_failures.append((c["id"], "strict", ",".join(bad)))

    # Debt ratchet: debt may shrink but never grow past the recorded baseline.
    baseline = registry.get("debt_baseline")
    if isinstance(baseline, int) and len(rep.debt) > baseline:
        rep.hard_failures.append(
            ("DEBT-RATCHET", f"debt {len(rep.debt)} > baseline {baseline}", "debt-grew")
        )

    rep.ok = not rep.hard_failures and not rep.wellformed_errors
    return rep


# -- JUnit resolution (the impure half) ------------------------------------------
def ref_to_junit_key(ref: str) -> Tuple[str, Optional[str]]:
    """Map a registry node id to a JUnit (classname, name) key.

    ``tests/test_engine.py::TestMergeOrdering::test_x`` ->
        ("tests.test_engine.TestMergeOrdering", "test_x")
    ``tests/test_blackboard.py::test_x`` -> ("tests.test_blackboard", "test_x")
    ``tests/test_compatibility.py`` (file-level) -> ("tests.test_compatibility", None)
    """
    parts = ref.split("::")
    filepath = parts[0]
    module = filepath[:-3] if filepath.endswith(".py") else filepath
    module = module.replace("\\", "/").replace("/", ".")
    if len(parts) == 1:
        return (module, None)  # file-level
    classes = parts[1:-1]
    name = parts[-1]
    classname = ".".join([module] + classes)
    return (classname, name)


def _outcome_from_testcase(tc: ET.Element) -> str:
    if tc.find("error") is not None:
        return FAILED
    if tc.find("failure") is not None:
        return FAILED
    if tc.find("skipped") is not None:
        return SKIPPED
    return PASSED


def _aggregate(outcomes: List[str]) -> str:
    """Collapse the outcomes of a test's (possibly parametrized) cases into one:
    any failure -> failed; all skipped -> skipped; otherwise passed; none -> missing."""
    if not outcomes:
        return MISSING
    if FAILED in outcomes:
        return FAILED
    if all(o == SKIPPED for o in outcomes):
        return SKIPPED
    return PASSED


def parse_junit(junit_path: str) -> Dict[str, List[Tuple[str, str]]]:
    """JUnit XML -> {classname: [(name, outcome), ...]}. ``name`` may carry a
    ``[param]`` suffix for parametrized tests.

    Raises :class:`GateError` if the report is absent, empty, or unparseable - the
    gate must fail closed rather than silently pass when the suite did not run."""
    if not os.path.exists(junit_path) or os.path.getsize(junit_path) == 0:
        raise GateError(f"JUnit report not found or empty: {junit_path}")
    try:
        root = ET.parse(junit_path).getroot()
    except ET.ParseError as exc:
        raise GateError(f"JUnit report is not parseable ({junit_path}): {exc}")
    by_class: Dict[str, List[Tuple[str, str]]] = {}
    for tc in root.iter("testcase"):
        by_class.setdefault(tc.get("classname", ""), []).append(
            (tc.get("name", ""), _outcome_from_testcase(tc))
        )
    if not by_class:
        raise GateError(f"JUnit report contains no testcases: {junit_path}")
    return by_class


def resolve_outcomes(registry: dict, junit_path: str) -> Dict[str, str]:
    """Run every registry test-ref against a parsed JUnit report -> outcome map.

    Handles parametrized tests (``name`` vs ``name[param]``) and file-level refs
    (no ``::``), aggregating all matching cases so a covered contract passes only
    when *every* matching case passes."""
    by_class = parse_junit(junit_path)
    resolved: Dict[str, str] = {}
    for c in registry.get("contracts", []):
        for ref in test_refs(c):
            cls, name = ref_to_junit_key(ref)
            if name is not None:
                outs = [
                    o
                    for (n, o) in by_class.get(cls, [])
                    if n == name or n.startswith(name + "[")
                ]
            else:
                # file-level: every case in that module (classname == module or a class within it)
                outs = [
                    o
                    for k, lst in by_class.items()
                    if k == cls or k.startswith(cls + ".")
                    for (_, o) in lst
                ]
            resolved[ref] = _aggregate(outs)
    return resolved


def run_suite_junit(repo_root: str) -> Tuple[str, int]:
    """Run the test suite once, emit JUnit XML, return (path, pytest_returncode)."""
    fd, junit_path = tempfile.mkstemp(suffix=".xml", prefix="contract_gate_")
    os.close(fd)
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests",
        f"--junitxml={junit_path}",
        "-q",
        "--tb=no",
        "-p",
        "no:cacheprovider",
        "-o",
        "addopts=",
    ]
    proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
    return junit_path, proc.returncode


# -- CLI -------------------------------------------------------------------------
def repo_root_from_here() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_registry(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except FileNotFoundError:
        raise GateError(f"registry not found: {path}")
    except yaml.YAMLError as exc:
        raise GateError(f"registry is not valid YAML ({path}): {exc}")
    if not isinstance(data, dict):
        raise GateError(f"registry is not a mapping: {path}")
    return data


def format_report(rep: Report, strict: bool) -> str:
    # ASCII-only: this runs on Windows (cp1252 stdout) and Linux CI alike.
    bar = "-" * 64
    lines = [
        bar,
        f"  Contract gate  ({'STRICT' if strict else 'default'} mode)",
        bar,
        f"  contracts: {rep.total}   covered: {rep.covered}   "
        f"coverage: {rep.coverage_pct}%",
    ]
    if rep.debt:
        lines.append(f"  debt ({len(rep.debt)}): {', '.join(rep.debt)}")
    if rep.wellformed_errors:
        lines.append("  REGISTRY ERRORS:")
        for e in rep.wellformed_errors:
            lines.append(f"    [x] {e}")
    if rep.hard_failures:
        lines.append("  CONTRACT FAILURES:")
        for cid, ref, reason in rep.hard_failures:
            lines.append(f"    [x] {cid}: {ref} -> {reason}")
    lines.append(bar)
    lines.append("  RESULT: " + ("PASS" if rep.ok else "FAIL"))
    lines.append(bar)
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Xubb Agents contract gate (G1/G2/G3)."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also fail on any to_verify/uncovered (the 16/16 release gate).",
    )
    parser.add_argument("--registry", default=None, help="path to CONTRACTS.yaml")
    parser.add_argument(
        "--junit",
        default=None,
        help="consume an existing JUnit report instead of re-running the suite "
        "(use this in CI so the suite runs exactly once).",
    )
    args = parser.parse_args(argv)

    root = repo_root_from_here()
    registry_path = args.registry or os.path.join(root, "docs", "CONTRACTS.yaml")

    try:
        registry = load_registry(registry_path)
        if args.junit:
            outcomes = resolve_outcomes(registry, args.junit)
        else:
            junit, _rc = run_suite_junit(root)
            try:
                outcomes = resolve_outcomes(registry, junit)
            finally:
                if os.path.exists(junit):
                    os.remove(junit)
    except GateError as exc:
        print(
            f"{'-' * 64}\n  Contract gate: CANNOT RUN (fail closed)\n  [x] {exc}\n{'-' * 64}"
        )
        return 1

    rep = evaluate(registry, outcomes, strict=args.strict)
    print(format_report(rep, args.strict))
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
