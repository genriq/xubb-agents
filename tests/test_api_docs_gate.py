"""The API documentation gate, and the failures it exists to catch.

`tools/check_api_docs.py` is the half of the accuracy story `check_contracts.py`
never covered: the contract gate proves every documented *behaviour* names a
passing test, and stayed green for three releases while the API reference
described a two-year-old constructor.

A gate nobody has watched fail is a gate nobody should trust, so every check here
is exercised against a deliberately broken fixture tree — never against the real
docs, which the first test asserts are clean.

The three fixtures the 2026-09-15 design review asked for by name:

  * a new constructor parameter with no inventory entry           (A1)
  * a changed default not reflected in the generated facts        (A3)
  * `Event.id` present while `AgentInsight.id` is missing         (A1, qualified)

That last one is the reason the inventory records QUALIFIED names. A bare-name
check passes it — `id` does appear, under another class — which is exactly the
mistake that inflated the audit this work came from.
"""
import importlib
import io
import os
import shutil
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import api_surface            # noqa: E402
import check_api_docs         # noqa: E402


@pytest.fixture()
def docs(tmp_path, monkeypatch):
    """A copy of the real documentation tree the tests may break freely."""
    target = tmp_path / "docs"
    target.mkdir()
    (target / "api").mkdir()
    shutil.copy(REPO / "docs" / "api" / "inventory.yaml", target / "api" / "inventory.yaml")
    shutil.copy(REPO / "docs" / "API_REFERENCE.md", target / "API_REFERENCE.md")
    shutil.copy(REPO / "docs" / "DIAGNOSTICS.md", target / "DIAGNOSTICS.md")
    monkeypatch.setattr(api_surface, "INVENTORY", str(target / "api" / "inventory.yaml"))
    monkeypatch.setattr(api_surface, "REFERENCE", str(target / "API_REFERENCE.md"))
    return target


def run(capsys):
    code = check_api_docs.main([])
    return code, capsys.readouterr().out


def edit_inventory(docs, mutate):
    path = docs / "api" / "inventory.yaml"
    doc = yaml.safe_load(io.open(path, encoding="utf-8").read())
    mutate(doc)
    io.open(path, "w", encoding="utf-8", newline="\n").write(yaml.safe_dump(doc, sort_keys=False))


# ---------------------------------------------------------------------------
# The control: the shipped documentation passes
# ---------------------------------------------------------------------------

def test_the_shipped_documentation_passes_the_gate(capsys):
    code, out = run(capsys)
    assert code == 0, out
    assert "RESULT: PASS" in out


# ---------------------------------------------------------------------------
# A1 — a public member with no inventory entry
# ---------------------------------------------------------------------------

def test_a1_a_new_constructor_parameter_without_an_entry_fails(docs, capsys):
    """The named fixture: someone adds an engine parameter and ships it
    undocumented. Modelled by removing the entry, which is the same condition —
    a member the code has and the inventory does not."""
    edit_inventory(docs, lambda d: d["classes"]["AgentEngine"]["members"].remove(
        "AgentEngine.__init__.widget_payload_validator"))
    code, out = run(capsys)
    assert code == 1
    assert "A1 undeclared public member: AgentEngine.__init__.widget_payload_validator" in out


def test_a1_qualified_names_event_id_does_not_cover_agentinsight_id(docs, capsys):
    """`Event.id` stays declared while `AgentInsight.id` is dropped. A bare-name
    check sees `id` and passes; the gate must not."""
    edit_inventory(docs, lambda d: d["classes"]["AgentInsight"]["members"].remove("AgentInsight.id"))
    code, out = run(capsys)
    assert code == 1
    assert "A1 undeclared public member: AgentInsight.id" in out
    assert "Event.id" not in out, "Event.id is still declared and must not be implicated"


# ---------------------------------------------------------------------------
# A2 — an inventory entry the code no longer has
# ---------------------------------------------------------------------------

def test_a2_a_stale_inventory_entry_fails(docs, capsys):
    edit_inventory(docs, lambda d: d["classes"]["AgentEngine"]["members"].append(
        "AgentEngine.__init__.removed_in_some_refactor"))
    code, out = run(capsys)
    assert code == 1
    assert "A2 inventory names a member the code does not have" in out


# ---------------------------------------------------------------------------
# A3 — generated facts that no longer match the code
# ---------------------------------------------------------------------------

def test_a3_a_changed_default_fails_until_the_tables_are_regenerated(docs, capsys):
    """The named fixture. Editing a generated default by hand is indistinguishable
    from the code's default changing underneath a stale table."""
    path = docs / "API_REFERENCE.md"
    text = io.open(path, encoding="utf-8").read()
    assert "| `max_phases` | `int` | no | `2` |" in text
    io.open(path, "w", encoding="utf-8", newline="\n").write(
        text.replace("| `max_phases` | `int` | no | `2` |", "| `max_phases` | `int` | no | `7` |"))
    code, out = run(capsys)
    assert code == 1
    assert "A3 generated API facts are stale" in out


def test_a3_a_missing_generated_block_fails(docs, capsys):
    path = docs / "API_REFERENCE.md"
    text = io.open(path, encoding="utf-8").read()
    io.open(path, "w", encoding="utf-8", newline="\n").write(
        text.replace("<!-- GENERATED:Fact -->", "<!-- GENERATED:Fact-removed -->", 1))
    code, out = run(capsys)
    assert code == 1
    assert "A3 docs/API_REFERENCE.md has no generated block for Fact" in out


# ---------------------------------------------------------------------------
# A4 — nowhere to read it
# ---------------------------------------------------------------------------

def test_a4_a_class_with_no_section_fails(docs, capsys):
    path = docs / "API_REFERENCE.md"
    text = io.open(path, encoding="utf-8").read()
    io.open(path, "w", encoding="utf-8", newline="\n").write(text.replace("### Fact\n", "### (removed)\n", 1))
    code, out = run(capsys)
    assert code == 1
    assert "A4 no section for Fact" in out


def test_a4_a_diagnostic_without_a_lifecycle_status_fails(docs, capsys):
    path = docs / "DIAGNOSTICS.md"
    text = io.open(path, encoding="utf-8").read()
    io.open(path, "w", encoding="utf-8", newline="\n").write(
        text.replace("### `invalid_gate`\n\n**Status:** active",
                     "### `invalid_gate`\n\nno status here", 1))
    code, out = run(capsys)
    assert code == 1
    assert "A4 diagnostic invalid_gate has no lifecycle status" in out


def test_a4_a_missing_diagnostics_page_fails(docs, capsys):
    os.remove(docs / "DIAGNOSTICS.md")
    code, out = run(capsys)
    assert code == 1
    assert "A4 docs/DIAGNOSTICS.md is missing" in out


# ---------------------------------------------------------------------------
# A5 — vocabulary that outlived its emitter
# ---------------------------------------------------------------------------

def test_a5_an_unemitted_code_must_be_documented_as_retired(docs, capsys):
    """`partial_legacy_response` has had no emitter since 3.0.0. Documenting it
    as active is the failure: the rule is not "delete the code", it is "say so"."""
    path = docs / "DIAGNOSTICS.md"
    text = io.open(path, encoding="utf-8").read()
    io.open(path, "w", encoding="utf-8", newline="\n").write(
        text.replace("### `partial_legacy_response`\n\n**Status:** **retired",
                     "### `partial_legacy_response`\n\n**Status:** active — **retired", 1))
    code, out = run(capsys)
    assert code == 1
    assert "A5 partial_legacy_response has no emitter" in out


def test_a5_knows_which_codes_the_source_still_emits(capsys):
    """NEGATIVE CONTROL for A5: the emitter scan must distinguish. If it reported
    everything as dead, the check above would pass for the wrong reason."""
    assert check_api_docs.emits("invalid_gate") is True
    assert check_api_docs.emits("undeclared_channel") is True
    assert check_api_docs.emits("partial_legacy_response") is False
    assert check_api_docs.emits("no_supported_insight_types") is False


# ---------------------------------------------------------------------------
# The generator is the only thing that writes generated blocks
# ---------------------------------------------------------------------------

def test_the_generator_is_idempotent(docs):
    gen = importlib.import_module("gen_api_facts")
    assert gen.main([]) == 0
    once = io.open(docs / "API_REFERENCE.md", encoding="utf-8").read()
    assert gen.main([]) == 0
    assert io.open(docs / "API_REFERENCE.md", encoding="utf-8").read() == once
