#!/usr/bin/env python3
"""Endpoint acceptance for the specialised provider projections.

docs/SPEC_PROVIDER_PROJECTION_ALIGNMENT.md §5; docs/SPEC_INSIGHT_TYPES.md §13.3 and the G2
gate ("codec/local tests plus actual endpoint acceptance"). Local lint and codec tests do
not prove that a live endpoint accepts a generated schema, and an invalid-schema failure
never downgrades. So before a release tag the maintainer runs this against the models the
pinned hosts use, and attaches the report to the release PR.

    python tools/check_provider_acceptance.py --model gpt-4.1 --model gpt-5.4-mini [--out report.json]

For each model and each representative projection it sends one strict request with a
minimal silence prompt, and records the schema's digest (sha256 of canonical JSON), whether
the endpoint accepted the request, and whether the returned envelope validates against the
schema that was sent. It reads OPENAI_API_KEY (and OPENAI_BASE_URL when set) from the
environment and never prints either.

Exit 0: every request accepted and every envelope valid. 1: any failure. 2: usage.
This tool is not part of the offline suite; its classification logic is tested offline
(tests/test_provider_acceptance_tool.py) with a fake client.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from xubb_agents.core.insight_validation import HUMAN_WIRE_VALUES  # noqa: E402
from xubb_agents.core.provider_schema import compile_schema, response_format_for  # noqa: E402

SIX = ["fact", "observation", "suggestion", "warning", "opportunity", "praise"]
CONSULTING = ["fact", "observation", "suggestion", "warning"]

#: The representative set of §5: general and consulting runs, the observation-kind branches,
#: question and correction granted, with and without the content extension, and every map
#: channel (the list-valued queue included, because every projection here is full).
REPRESENTATIVE: Tuple[Tuple[str, Dict[str, Any]], ...] = (
    ("general-six", {"allowed_types": SIX, "analysis_profile": "general", "content_extension": False}),
    ("general-six-content", {"allowed_types": SIX, "analysis_profile": "general", "content_extension": True}),
    ("consulting-observation", {"allowed_types": CONSULTING, "analysis_profile": "consulting",
                                "content_extension": False}),
    ("consulting-observation-content", {"allowed_types": CONSULTING, "analysis_profile": "consulting",
                                        "content_extension": True}),
    ("consulting-all-nine", {"allowed_types": list(HUMAN_WIRE_VALUES), "analysis_profile": "consulting",
                             "content_extension": False}),
)

SILENCE_PROMPT = [
    {"role": "system", "content": "Nothing in this conversation needs the principal's attention. "
                                  "Return has_insight false and insight null, with every channel empty."},
    {"role": "user", "content": "Nothing new."},
]


def representative_schemas() -> List[Tuple[str, Dict[str, Any]]]:
    return [(name, compile_schema(full=True, **kwargs)) for name, kwargs in REPRESENTATIVE]


def digest(schema: Dict[str, Any]) -> str:
    """sha256 of the canonical JSON: sorted keys, no whitespace."""
    canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def envelope_valid(schema: Dict[str, Any], content: Optional[str]) -> Optional[bool]:
    """Whether the returned content is JSON that validates against the schema sent.
    None when jsonschema (a dev dependency) is not installed."""
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        return None
    try:
        body = json.loads(content or "")
    except (TypeError, ValueError):
        return False
    return Draft202012Validator(schema).is_valid(body)


def check(models: List[str], create: Callable[..., Any]) -> List[Dict[str, Any]]:
    """One strict request per (model, schema); ``create`` is the SDK's completion call."""
    results = []
    for model in models:
        for name, schema in representative_schemas():
            row: Dict[str, Any] = {"model": model, "schema": name, "digest": digest(schema),
                                   "accepted": False, "envelope_valid": None, "error": None}
            try:
                response = create(model=model, messages=SILENCE_PROMPT, response_format=response_format_for(schema))
                message = response.choices[0].message
                if getattr(message, "refusal", None):
                    row["error"] = "refusal"
                else:
                    row["accepted"] = True
                    row["envelope_valid"] = envelope_valid(schema, message.content)
            except Exception as exc:  # noqa: BLE001 - every failure is reported, none is retried
                status = getattr(exc, "status_code", None)
                code = getattr(exc, "code", None)
                row["error"] = f"{type(exc).__name__} status={status} code={code}: {str(exc)[:200]}"
            results.append(row)
    return results


def passed(results: List[Dict[str, Any]]) -> bool:
    return bool(results) and all(r["accepted"] and r["envelope_valid"] is not False for r in results)


def render(results: List[Dict[str, Any]]) -> str:
    lines = ["| model | schema | digest | accepted | envelope valid | error |", "|---|---|---|---|---|---|"]
    for r in results:
        valid = "not checked" if r["envelope_valid"] is None else ("yes" if r["envelope_valid"] else "NO")
        lines.append(f"| {r['model']} | {r['schema']} | {r['digest'][:16]} | {'yes' if r['accepted'] else 'NO'} "
                     f"| {valid} | {r['error'] or ''} |")
    lines.append("")
    lines.append("RESULT: " + ("PASS" if passed(results) else "FAIL"))
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", action="append", required=True, help="a model the pinned hosts run (repeat)")
    parser.add_argument("--out", help="also write the results as JSON to this file")
    args = parser.parse_args(argv)
    if not os.environ.get("OPENAI_API_KEY"):
        print("check_provider_acceptance: OPENAI_API_KEY is not set in the environment", file=sys.stderr)
        return 2
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], base_url=os.environ.get("OPENAI_BASE_URL") or None)
    results = check(args.model, client.chat.completions.create)
    print(render(results))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2)
    return 0 if passed(results) else 1


if __name__ == "__main__":
    sys.exit(main())
