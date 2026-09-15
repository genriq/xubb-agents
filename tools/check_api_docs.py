#!/usr/bin/env python3
"""Documentation gate: the code, the declared inventory and the reference agree.

The contract-accuracy gate (``tools/check_contracts.py``) proves that every
documented *behavioural* contract names a passing test. It never covered the API
reference, which is why that reference drifted three releases behind while the
gate stayed green. This is the missing half.

Five checks, each with a deliberate failing fixture in
``tests/test_api_docs_gate.py`` — a check nobody has seen fail is a check nobody
should trust:

  A1  every public member of a declared class appears in the inventory
      (a new constructor parameter fails the build until someone declares it)
  A2  every inventory entry still exists in the code
      (a removed or renamed member fails loudly instead of rotting)
  A3  the generated fact blocks in the reference are current
      (a changed default fails until the tables are regenerated)
  A4  every declared class, constant and diagnostic code has a section to read,
      and every diagnostic carries a lifecycle status
  A5  a diagnostic with no emitter left in the source is documented as retired
      (removing registered vocabulary is a compatibility decision, not tidying)

A1 and A2 together are what keep the inventory honest. It is a hand-maintained
enumeration, and this repository has been burned by one of those before (3.1.2):
the difference is that this one is compared against reality in both directions on
every build.

    python tools/check_api_docs.py

Exit 0 = clean, 1 = documentation is wrong.
"""
from __future__ import annotations

import io
import os
import re
import sys

import api_surface
from api_surface import ROOT, derive


def _diagnostics_path():
    return os.path.join(os.path.dirname(api_surface.REFERENCE), "DIAGNOSTICS.md")


_DECLARATION = ("insight_validation.py", 55, 85)     # the DIAGNOSTIC_CODES tuple itself


def emits(code):
    """True when some path in src/ emits ``code`` — the tuple that declares the
    vocabulary does not count as an emitter."""
    needle = re.compile(r"[\"']" + re.escape(code) + r"[\"']")
    src = os.path.join(ROOT, "src")
    for base, _dirs, files in os.walk(src):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            path = os.path.join(base, fname)
            text = io.open(path, encoding="utf-8").read()
            for match in needle.finditer(text):
                line = text[:match.start()].count("\n") + 1
                decl_file, lo, hi = _DECLARATION
                if path.endswith(decl_file) and lo <= line <= hi:
                    continue
                return True
    return False


def _anchor_exists(text, name):
    return re.search(r"^#{2,4}\s+.*`?" + re.escape(name) + r"`?\s*$", text, re.M) is not None


def main(argv=None):
    problems = []
    doc, surface = derive()
    reference = io.open(api_surface.REFERENCE, encoding="utf-8").read()

    # ---- A1 / A2 -- inventory vs code, both directions --------------------
    for name, data in surface.items():
        declared = set(data["entry"].get("members") or [])
        actual = {q for q, _ in data["members"]}
        for missing in sorted(actual - declared):
            problems.append(f"A1 undeclared public member: {missing} "
                            f"(add it to docs/api/inventory.yaml, then explain it in the reference)")
        for stale in sorted(declared - actual):
            problems.append(f"A2 inventory names a member the code does not have: {stale}")

    # ---- A4 -- every declared name has somewhere to be read ---------------
    for name in surface:
        if not _anchor_exists(reference, name):
            problems.append(f"A4 no section for {name} in docs/API_REFERENCE.md")
    for const in (doc.get("constants") or {}):
        if const not in reference:
            problems.append(f"A4 constant {const} is declared but absent from the reference")

    # ---- A4 -- the diagnostic vocabulary ----------------------------------
    sys.path.insert(0, os.path.join(ROOT, "src"))
    from xubb_agents.core.insight_validation import DIAGNOSTIC_CODES
    DIAGNOSTICS = _diagnostics_path()
    if not os.path.exists(DIAGNOSTICS):
        problems.append("A4 docs/DIAGNOSTICS.md is missing")
    else:
        diagnostics = io.open(DIAGNOSTICS, encoding="utf-8").read()
        for code in DIAGNOSTIC_CODES:
            if not _anchor_exists(diagnostics, code):
                problems.append(f"A4 diagnostic {code} has no section in docs/DIAGNOSTICS.md")
                continue
            block = re.split(r"^#{2,4}\s+`?" + re.escape(code) + r"`?\s*$", diagnostics, flags=re.M)
            if len(block) > 1 and "**Status:**" not in block[1].split("\n###")[0]:
                problems.append(f"A4 diagnostic {code} has no lifecycle status")

    # ---- A5 -- a code with no emitter must be documented as retired -------
    #
    # A vocabulary entry outlives the path that emitted it (3.0.0 left two
    # behind). Removing one is a compatibility decision for hosts that branch on
    # it, so the rule is not "delete it" — the rule is "say so".
    if os.path.exists(DIAGNOSTICS):
        diagnostics = io.open(DIAGNOSTICS, encoding="utf-8").read()
        for code in DIAGNOSTIC_CODES:
            documented_retired = re.search(
                r"^#{2,4}\s+`?" + re.escape(code) + r"`?\s*$\n+\*\*Status:\*\*\s*\*?\*?retired",
                diagnostics, re.M) is not None
            if emits(code) and documented_retired:
                problems.append(f"A5 {code} is documented as retired but the source still emits it")
            elif not emits(code) and not documented_retired:
                problems.append(f"A5 {code} has no emitter in src/ and is not documented as retired")

    # ---- A3 -- generated blocks are current -------------------------------
    from gen_api_facts import render
    updated, missing = render(reference, surface)
    for name in missing:
        problems.append(f"A3 docs/API_REFERENCE.md has no generated block for {name}")
    if not missing and updated != reference:
        problems.append("A3 generated API facts are stale — run: python tools/gen_api_facts.py")

    line = "-" * 64
    print(line)
    print("  API documentation gate")
    print(line)
    members = sum(len(d["members"]) for d in surface.values())
    print(f"  classes: {len(surface)}   qualified members: {members}   "
          f"excluded (recorded): {len(doc.get('excluded') or {})}")
    if problems:
        print(f"  PROBLEMS: {len(problems)}")
        for p in problems[:40]:
            print(f"    [x] {p}")
        if len(problems) > 40:
            print(f"    ... and {len(problems) - 40} more")
        print(line)
        print("  RESULT: FAIL")
        print(line)
        return 1
    print(line)
    print("  RESULT: PASS")
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
