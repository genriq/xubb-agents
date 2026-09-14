#!/usr/bin/env python3
"""Inventory and migrate agent configurations onto the supported output formats.

Offline and read-only by default. It never touches a database — it reads agent
configuration JSON and tells you, per agent, what moving to 3.1.0's supported
formats costs, separating what it can rewrite mechanically from what a person
must decide.

    # inventory a catalogue or a directory of configs
    python tools/migrate_output_formats.py prompts.json
    python tools/migrate_output_formats.py config/agents/

    # show the rewritten configuration without touching anything
    python tools/migrate_output_formats.py prompts.json --dry-run

    # apply only the mechanical part (setting output_format explicitly)
    python tools/migrate_output_formats.py prompts.json --write

Accepted inputs: a JSON array of agent configs, an object with a "prompts" or
"agents" array, a single agent config object, or a directory of any of those.

Exit codes: 0 nothing to do · 1 migration work remains · 2 bad input.

See docs/MIGRATION_OUTPUT_FORMATS.md.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from xubb_agents.core.output_format import (  # noqa: E402
    REMOVED_FORMATS, RETIRED_MAPPING_KEYS, STRUCTURAL_MAPPING_KEYS,
    all_formats, deprecated_names, implicit_default, removal_release, resolve, supported_names,
)

#: Envelope vocabulary that, appearing in a handwritten prompt body, means the
#: agent was told a shape by hand. The tool cannot rewrite prose — it flags it.
HANDWRITTEN_MARKERS = (
    "has_insight", "state_snapshot", "ui_actions", "memory_updates", "variable_updates",
    "queue_pushes", '"insight"', "speak_without_gate", '"message"',
)

TARGETS = {fid: (spec.deprecation or {}).get("replacement", fid) for fid, spec in all_formats().items()}


def load_configs(path, documents=None):
    """Every agent config under ``path``, as (source path, config) pairs.

    ``documents`` (source path -> parsed JSON document) collects the whole
    document each config came from, so ``--write`` can save the file back with
    the config objects it mutated in place.
    """
    out = []
    if os.path.isdir(path):
        for root, _dirs, files in os.walk(path):
            for name in sorted(files):
                if name.endswith(".json"):
                    out.extend(load_configs(os.path.join(root, name), documents))
        return out
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if documents is not None:
        documents[path] = data
    if isinstance(data, dict):
        for key in ("prompts", "agents", "configs"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected an agent config, a list of them, or an object with a "
                         f"'prompts'/'agents'/'configs' array")
    for item in data:
        if isinstance(item, dict) and ("text" in item or "output_format" in item or "trigger_config" in item):
            out.append((path, item))
    return out


def inspect(config):
    """What this agent needs. Returns a dict the report and --write both read."""
    agent_id = config.get("id") or config.get("name") or "(unnamed)"
    explicit = "output_format" in config
    raw = config.get("output_format", implicit_default())
    manual = []
    current = None

    if explicit and (raw is None or not isinstance(raw, str) or not raw.strip()):
        manual.append(f"output_format is {raw!r}; 3.1.0 refuses it — omit the key or name a format")
    elif isinstance(raw, str) and raw.strip() in REMOVED_FORMATS:
        manual.append(f"'{raw}' was removed in an earlier release; pick a supported format")
    else:
        try:
            current = resolve(raw).id
        except Exception as exc:                       # unknown name
            manual.append(str(exc).split(".")[0])

    target = TARGETS.get(current, "insight_v1") if current else "insight_v1"

    text = config.get("text") or ""
    hits = sorted({m.strip('"') for m in HANDWRITTEN_MARKERS if m in text})
    if hits:
        manual.append("the prompt body names envelope fields by hand (" + ", ".join(hits) +
                      "); rewrite it for the new envelope or delete those lines — the "
                      "framework generates the envelope instruction itself")

    mapping = config.get("mapping") or {}
    for key in RETIRED_MAPPING_KEYS:
        if key in mapping:
            manual.append(f"mapping['{key}'] is refused at registration in 3.1.0")
    overrides = [k for k in STRUCTURAL_MAPPING_KEYS if k in mapping]
    if overrides:
        manual.append("structural mapping override(s) " + ", ".join(overrides) +
                      " are refused at registration; move to a format whose contract is that shape")

    if target == "widget_control":
        manual.append("the HOST must declare this agent's widgets per run "
                      "(AgentContext.widget_capabilities); with none declared no action is authorized")
        if current == "widget_control":
            manual.append("its wire shape moves to the canonical envelope (has_insight + nested "
                          "insight); the legacy shape is accepted until " + removal_release())

    mechanical = (current is not None and (not explicit or current != target))
    return {"id": agent_id, "explicit": explicit, "current": current, "target": target,
            "mechanical": mechanical, "manual": manual}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("path", help="agent config JSON file, catalogue, or directory")
    ap.add_argument("--dry-run", action="store_true", help="print the rewritten configuration, change nothing")
    ap.add_argument("--write", action="store_true", help="apply the mechanical rewrite in place")
    args = ap.parse_args(argv)

    documents = {}
    try:
        pairs = load_configs(args.path, documents)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2
    if not pairs:
        print(f"No agent configurations found under {args.path}")
        return 2

    rows = [(src, cfg, inspect(cfg)) for src, cfg in pairs]
    implicit = [r for _, _, r in rows if not r["explicit"]]
    needs_manual = [r for _, _, r in rows if r["manual"]]
    mechanical = [r for _, _, r in rows if r["mechanical"] and not r["manual"]]

    print(f"{len(rows)} agent configuration(s) under {args.path}")
    print(f"  supported formats: {', '.join(supported_names())}")
    print(f"  deprecated (removed in {removal_release()}): {', '.join(deprecated_names())}\n")

    width = max(len(r["id"]) for _, _, r in rows)
    for _src, _cfg, r in rows:
        current = r["current"] or "?"
        marker = "  (implicit)" if not r["explicit"] else ""
        state = "manual" if r["manual"] else ("rewrite" if r["mechanical"] else "ok")
        print(f"  [{state:7}] {r['id']:<{width}}  {current}{marker} -> {r['target']}")
        for note in r["manual"]:
            print(f"              - {note}")

    print(f"\nSummary: {len(mechanical)} mechanical, {len(needs_manual)} need a decision, "
          f"{len(implicit)} inherit the implicit default ('{implicit_default()}') and MUST set "
          f"output_format explicitly before {removal_release()}.")

    if args.dry_run or args.write:
        touched = {}
        for src, cfg, r in rows:
            if r["current"] is None:
                continue
            cfg["output_format"] = r["target"]
            touched.setdefault(src, []).append(cfg)
        if args.dry_run:
            print("\n--- dry run: rewritten configurations ---")
            for _src, cfg, r in rows:
                if r["current"] is not None:
                    print(json.dumps({k: cfg[k] for k in ("id", "output_format") if k in cfg}))
            print("(the mechanical rewrite sets output_format only; nothing else is touched)")
        else:
            # `documents[src]` is the parsed document the mutated configs live
            # inside, so writing it back carries exactly the change above and
            # nothing else.
            for src in touched:
                _write_back(src, documents[src])
            print(f"\nWrote output_format into {len(touched)} file(s). "
                  f"The items listed as 'manual' above are unchanged and still need a decision.")

    return 1 if (needs_manual or mechanical or implicit) else 0


def _write_back(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
