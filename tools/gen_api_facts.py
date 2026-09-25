#!/usr/bin/env python3
"""Write the generated fact tables into docs/API_REFERENCE.md.

Each documented class owns a block in the reference delimited by

    <!-- GENERATED:AgentEngine -->
    ...table...
    <!-- /GENERATED:AgentEngine -->

Everything outside those markers is written by hand and this tool never touches
it. Everything inside is derived from the shipped code and must never be edited
by hand — ``tools/check_api_docs.py`` fails the build when it drifts.

    python tools/gen_api_facts.py            # rewrite the blocks in place
    python tools/gen_api_facts.py --check    # exit 1 if any block is stale
"""
from __future__ import annotations

import argparse
import io
import re
import sys

import api_surface
from api_surface import derive

MARK = "<!-- GENERATED:%s -->"
END = "<!-- /GENERATED:%s -->"


def _cell(text):
    return "—" if text in (None, "") else str(text).replace("|", "\\|")


def table_for(name, members):
    """The generated facts for one class, as markdown."""
    if not members:
        return "_No public members: this type is a marker or an alias._"

    kinds = {k["kind"] for _, k in members}
    rows = []
    if kinds == {"enum_member"}:
        rows.append("| Member | Wire value |")
        rows.append("|---|---|")
        for q, f in members:
            rows.append(f"| `{q.split('.', 1)[1]}` | `{f['value']}` |")
        return "\n".join(rows)

    fields = [(q, f) for q, f in members if f["kind"] in ("field", "parameter")]
    methods = [(q, f) for q, f in members if f["kind"] in ("method", "coroutine")]

    if fields:
        label = "Parameter" if fields[0][1]["kind"] == "parameter" else "Field"
        rows.append(f"| {label} | Type | Required | Default | Notes |")
        rows.append("|---|---|---|---|---|")
        for q, f in fields:
            short = q.split(".")[-1]
            note = "**excluded from serialization**" if f.get("excluded_from_serialization") else ""
            rows.append(f"| `{short}` | `{_cell(f['type'])}` | "
                        f"{'yes' if f['required'] else 'no'} | `{_cell(f['default'])}` | {_cell(note) if note else ''} |")
    if methods:
        if fields:
            rows.append("")
        rows.append("| Method | Signature |")
        rows.append("|---|---|")
        for q, f in methods:
            short = q.split(".", 1)[1]
            prefix = "async " if f["kind"] == "coroutine" else ""
            rows.append(f"| `{short}` | `{prefix}{short}{f['signature']}` |")
    return "\n".join(rows)


def render(text, surface):
    """Replace every generated block in ``text``. Missing blocks are reported."""
    missing = []
    for name, data in surface.items():
        start, end = MARK % name, END % name
        block = f"{start}\n{table_for(name, data['members'])}\n{end}"
        pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
        if not pattern.search(text):
            missing.append(name)
            continue
        text = pattern.sub(lambda _m, b=block: b, text, count=1)
    return text, missing


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if a block is stale; write nothing")
    args = ap.parse_args(argv)

    _doc, surface = derive()
    # Read from the module when called, never imported by name: the tests point
    # api_surface.REFERENCE at a scratch copy, and a name bound at import would
    # keep the real path and rewrite the tracked file.
    reference = api_surface.REFERENCE
    current = io.open(reference, encoding="utf-8").read()
    updated, missing = render(current, surface)

    if missing:
        print("ERROR: docs/API_REFERENCE.md has no generated block for: " + ", ".join(sorted(missing)))
        print("       add:  <!-- GENERATED:Name -->\\n<!-- /GENERATED:Name -->")
        return 1
    if args.check:
        if updated != current:
            print("ERROR: generated API facts are stale. Run: python tools/gen_api_facts.py")
            return 1
        print(f"generated API facts current ({len(surface)} classes)")
        return 0

    io.open(reference, "w", encoding="utf-8", newline="\n").write(updated)
    print(f"wrote generated facts for {len(surface)} classes into docs/API_REFERENCE.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
