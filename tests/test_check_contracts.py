"""Tests for tools/check_contracts.py — the accuracy gate (L0).

Each contract assertion carries its own negative-control (the inverse case that
MUST fail) — the negative-control rule, see docs/PROCESS.md. The pure :func:`evaluate` core
is exercised with synthetic ``{test_ref: outcome}`` maps so these tests are fast
and need no subprocess.
"""

import os
import sys

import pytest

# Import the tool as a top-level module regardless of packaging.
_TOOLS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"
)
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import check_contracts as cc  # noqa: E402


def _reg(*contracts):
    return {"schema_version": 1, "contracts": list(contracts)}


def _c(cid, status, test="tests/x.py::test_x", **extra):
    base = {"id": cid, "statement": "a rule", "source": ["x"], "status": status}
    if test is not None:
        base["test"] = test
    base.update(extra)
    return base


class TestGate:
    @pytest.mark.invariant
    def test_gate_fails_on_uncovered_contract(self):
        """A `covered` contract whose named test does not run is a hard failure;
        the same contract with a passing test passes (negative control)."""
        reg = _reg(_c("C1", cc.STATUS_COVERED, test="tests/a.py::t"))

        fail = cc.evaluate(reg, {"tests/a.py::t": cc.MISSING})
        assert fail.ok is False
        assert any(h[0] == "C1" for h in fail.hard_failures)

        # negative control: a real passing test → the gate must pass.
        ok = cc.evaluate(reg, {"tests/a.py::t": cc.PASSED})
        assert ok.ok is True
        assert ok.hard_failures == []

    @pytest.mark.invariant
    def test_contract_test_bijection(self):
        """A `covered` contract is satisfied ONLY by a passing test; skipped,
        failed, and missing all hard-fail (passing is the negative control)."""
        reg = _reg(_c("C1", cc.STATUS_COVERED, test="tests/a.py::t"))
        for bad in (cc.SKIPPED, cc.FAILED, cc.MISSING):
            r = cc.evaluate(reg, {"tests/a.py::t": bad})
            assert r.ok is False, f"{bad} should hard-fail a covered contract"
        good = cc.evaluate(reg, {"tests/a.py::t": cc.PASSED})
        assert good.ok is True

    def test_all_test_refs_must_pass(self):
        """Multi-test contracts (test/test_engine/test_unit) require ALL refs to pass."""
        reg = _reg(
            _c(
                "C1",
                cc.STATUS_COVERED,
                test="a::t",
                test_engine="b::t",
                test_unit="c::t",
            )
        )
        outcomes = {"a::t": cc.PASSED, "b::t": cc.PASSED, "c::t": cc.FAILED}
        assert cc.evaluate(reg, outcomes).ok is False
        outcomes["c::t"] = cc.PASSED
        assert cc.evaluate(reg, outcomes).ok is True


class TestDebtAndStrict:
    def test_debt_does_not_hard_fail_default_mode(self):
        """to_verify/uncovered are reported as debt, not a red build (so the
        framework isn't blocked before the R1 back-fill)."""
        reg = _reg(
            _c("OK", cc.STATUS_COVERED, test="p::t"),
            _c("DEBT", cc.STATUS_TO_VERIFY, test="q::t"),
            _c("UNC", cc.STATUS_UNCOVERED, test=None),  # no test → MISSING-style
        )
        # UNC has no test ref; to_verify points at a non-running test.
        r = cc.evaluate(reg, {"p::t": cc.PASSED, "q::t": cc.MISSING})
        assert r.ok is True
        assert set(r.debt) == {"DEBT", "UNC"}

    def test_strict_enforces_debt(self):
        """--strict turns every to_verify/uncovered into a hard requirement
        (the 16/16 release gate); a passing test is the negative control."""
        reg = _reg(_c("DEBT", cc.STATUS_TO_VERIFY, test="q::t"))
        assert cc.evaluate(reg, {"q::t": cc.MISSING}, strict=True).ok is False
        assert cc.evaluate(reg, {"q::t": cc.PASSED}, strict=True).ok is True

    def test_debt_ratchet(self):
        """Debt may shrink but never grow past the recorded baseline."""
        contracts = [
            _c("OK", cc.STATUS_COVERED, test="p::t"),
            _c("D1", cc.STATUS_TO_VERIFY, test="a::t"),
            _c("D2", cc.STATUS_TO_VERIFY, test="b::t"),
        ]
        outcomes = {"p::t": cc.PASSED}
        at_baseline = {"schema_version": 1, "debt_baseline": 2, "contracts": contracts}
        assert cc.evaluate(at_baseline, outcomes).ok is True  # 2 debt, baseline 2
        grew = {"schema_version": 1, "debt_baseline": 1, "contracts": contracts}
        rep = cc.evaluate(grew, outcomes)  # 2 debt, baseline 1 -> grew
        assert rep.ok is False
        assert any(h[0] == "DEBT-RATCHET" for h in rep.hard_failures)


class TestFailingProbe:
    def test_failing_probe_must_currently_fail(self):
        """A failing_probe documents an UNIMPLEMENTED rule: it must fail today.
        A probe that unexpectedly passes is itself a gate failure."""
        reg = _reg(_c("P", cc.STATUS_FAILING_PROBE, test="probe::t"))
        assert cc.evaluate(reg, {"probe::t": cc.FAILED}).ok is True
        assert (
            cc.evaluate(reg, {"probe::t": cc.PASSED}).ok is False
        )  # unexpectedly passing
        assert cc.evaluate(reg, {"probe::t": cc.MISSING}).ok is False  # probe vanished


class TestWellformed:
    def test_duplicate_id_is_an_error(self):
        reg = _reg(_c("DUP", cc.STATUS_COVERED), _c("DUP", cc.STATUS_COVERED))
        assert any("duplicate" in e for e in cc.validate_registry(reg))

    def test_invalid_status_is_an_error(self):
        reg = _reg(_c("X", "bogus_status"))
        assert any("invalid status" in e for e in cc.validate_registry(reg))

    def test_missing_statement_is_an_error(self):
        c = _c("X", cc.STATUS_COVERED)
        del c["statement"]
        assert any("missing `statement`" in e for e in cc.validate_registry(_reg(c)))

    def test_covered_without_test_is_an_error(self):
        reg = _reg(_c("X", cc.STATUS_COVERED, test=None))
        assert any("names no test" in e for e in cc.validate_registry(reg))

    def test_covered_file_level_ref_is_an_error(self):
        """A covered contract must name a node-level test; a bare file is too weak
        a bijection (a to_verify file-level ref is allowed - it is only debt)."""
        bad = _reg(_c("X", cc.STATUS_COVERED, test="tests/test_foo.py"))
        assert any("file-level" in e for e in cc.validate_registry(bad))
        ok = _reg(_c("Y", cc.STATUS_TO_VERIFY, test="tests/test_foo.py"))
        assert cc.validate_registry(ok) == []

    def test_wellformedness_blocks_evaluate(self):
        """A malformed registry hard-fails regardless of test outcomes."""
        reg = _reg(_c("DUP", cc.STATUS_COVERED), _c("DUP", cc.STATUS_COVERED))
        assert cc.evaluate(reg, {}).ok is False

    @pytest.mark.invariant
    def test_real_registry_is_wellformed(self):
        """The shipped docs/CONTRACTS.yaml must always be structurally valid."""
        root = cc.repo_root_from_here()
        reg = cc.load_registry(os.path.join(root, "docs", "CONTRACTS.yaml"))
        assert cc.validate_registry(reg) == []


class TestJunitMapping:
    def test_ref_to_junit_key_variants(self):
        assert cc.ref_to_junit_key(
            "tests/test_engine.py::TestMergeOrdering::test_x"
        ) == ("tests.test_engine.TestMergeOrdering", "test_x")
        assert cc.ref_to_junit_key("tests/test_blackboard.py::test_x") == (
            "tests.test_blackboard",
            "test_x",
        )
        assert cc.ref_to_junit_key("tests/test_compatibility.py") == (
            "tests.test_compatibility",
            None,
        )

    def test_aggregate_outcomes(self):
        assert cc._aggregate([]) == cc.MISSING
        assert cc._aggregate([cc.PASSED, cc.PASSED]) == cc.PASSED
        assert cc._aggregate([cc.PASSED, cc.FAILED]) == cc.FAILED
        assert cc._aggregate([cc.SKIPPED, cc.SKIPPED]) == cc.SKIPPED
        assert cc._aggregate([cc.PASSED, cc.SKIPPED]) == cc.PASSED

    def test_resolve_outcomes_handles_parametrized(self, tmp_path):
        """A parametrized test (name[param]) referenced by its base name resolves
        by aggregating every case — the INV-10 bug that the gate first caught."""
        junit = tmp_path / "j.xml"
        junit.write_text(
            "<testsuites><testsuite>"
            '<testcase classname="tests.test_llm" name="test_typed[exc0-timeout]"/>'
            '<testcase classname="tests.test_llm" name="test_typed[exc1-auth]"/>'
            "</testsuite></testsuites>",
            encoding="utf-8",
        )
        reg = _reg(_c("INV10", cc.STATUS_COVERED, test="tests/test_llm.py::test_typed"))
        outcomes = cc.resolve_outcomes(reg, str(junit))
        assert outcomes["tests/test_llm.py::test_typed"] == cc.PASSED
        assert cc.evaluate(reg, outcomes).ok is True


class TestFailClosed:
    """The gate must error red (never silently pass) when the suite did not run."""

    def test_missing_junit_raises(self, tmp_path):
        with pytest.raises(cc.GateError):
            cc.parse_junit(str(tmp_path / "nope.xml"))

    def test_empty_junit_raises(self, tmp_path):
        p = tmp_path / "e.xml"
        p.write_text("", encoding="utf-8")
        with pytest.raises(cc.GateError):
            cc.parse_junit(str(p))

    def test_garbage_junit_raises(self, tmp_path):
        p = tmp_path / "g.xml"
        p.write_text("not xml at all", encoding="utf-8")
        with pytest.raises(cc.GateError):
            cc.parse_junit(str(p))

    def test_no_testcases_raises(self, tmp_path):
        p = tmp_path / "n.xml"
        p.write_text(
            "<testsuites><testsuite></testsuite></testsuites>", encoding="utf-8"
        )
        with pytest.raises(cc.GateError):
            cc.parse_junit(str(p))


def _write_reg(path, *, status, test, baseline=None):
    lines = ["schema_version: 1"]
    if baseline is not None:
        lines.append(f"debt_baseline: {baseline}")
    lines += [
        "contracts:",
        "  - id: C1",
        "    statement: a rule",
        "    source: [x]",
        f'    test: "{test}"',
        f"    status: {status}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_junit(path, outcome):
    body = '<testsuites><testsuite><testcase classname="tests.t" name="x"'
    if outcome == "passed":
        body += "/>"
    elif outcome == "failed":
        body += "><failure>boom</failure></testcase>"
    elif outcome == "skipped":
        body += "><skipped/></testcase>"
    body += "</testsuite></testsuites>"
    path.write_text(body, encoding="utf-8")


class TestCLI:
    """End-to-end: main() against a fixture registry + JUnit (no subprocess)."""

    def test_cli_passes_on_good_registry(self, tmp_path, capsys):
        reg, junit = tmp_path / "c.yaml", tmp_path / "j.xml"
        _write_reg(reg, status="covered", test="tests/t.py::x")
        _write_junit(junit, "passed")
        rc = cc.main(["--registry", str(reg), "--junit", str(junit)])
        assert rc == 0
        assert "PASS" in capsys.readouterr().out

    def test_cli_fails_on_broken_contract(self, tmp_path):
        reg, junit = tmp_path / "c.yaml", tmp_path / "j.xml"
        _write_reg(reg, status="covered", test="tests/t.py::x")
        _write_junit(junit, "failed")
        assert cc.main(["--registry", str(reg), "--junit", str(junit)]) == 1

    def test_cli_fails_closed_on_missing_junit(self, tmp_path, capsys):
        reg = tmp_path / "c.yaml"
        _write_reg(reg, status="covered", test="tests/t.py::x")
        rc = cc.main(["--registry", str(reg), "--junit", str(tmp_path / "absent.xml")])
        assert rc == 1
        assert "CANNOT RUN" in capsys.readouterr().out


class TestReleaseGateCI:
    @pytest.mark.invariant
    def test_ci_workflow_exists_and_invokes_gate(self):
        """P4-RELEASE-GATE-CI: a CI workflow runs the gate so drift blocks merge."""
        root = cc.repo_root_from_here()
        wf = os.path.join(root, ".github", "workflows", "contract-gate.yml")
        assert os.path.exists(wf), "contract-gate.yml missing"
        with open(wf, "r", encoding="utf-8") as fh:
            body = fh.read()
        assert "check_contracts.py" in body
