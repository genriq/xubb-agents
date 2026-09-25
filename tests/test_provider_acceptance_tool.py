"""The endpoint-acceptance tool (tools/check_provider_acceptance.py), tested offline.

Running it against live endpoints is the maintainer's release step
(docs/SPEC_PROVIDER_PROJECTION_ALIGNMENT.md §5); what the suite checks is that it builds
the representative set the spec names, digests it stably, and classifies every outcome
honestly — a rejection, a refusal or an invalid envelope is never reported as a pass.
"""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

TOOL = Path(__file__).resolve().parent.parent / "tools" / "check_provider_acceptance.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("check_provider_acceptance_under_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tool = load_tool()

SILENCE = {"has_insight": False, "insight": None,
           "variable_updates": {"entries": []}, "queue_pushes": {"entries": []},
           "memory_updates": {"entries": []}, "facts": [], "events": [], "ui_actions": []}


def reply(body=None, refusal=None, raw=None):
    content = raw if raw is not None else (None if refusal else json.dumps(body))
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, refusal=refusal))])


class Rejected(Exception):
    status_code = 400
    code = "invalid_json_schema"


def test_the_representative_set_covers_the_shapes_the_spec_names():
    schemas = dict(tool.representative_schemas())
    assert set(schemas) == {"general-six", "general-six-content", "consulting-observation",
                            "consulting-observation-content", "consulting-all-nine"}
    consulting = schemas["consulting-observation"]
    assert "candidate_observation_hypothesis" in consulting["$defs"]           # the anyOf branches
    assert "candidate_question" in schemas["consulting-all-nine"]["$defs"]      # question granted
    assert "candidate_correction" in schemas["consulting-all-nine"]["$defs"]    # correction granted
    for name, schema in schemas.items():
        assert schema["properties"]["queue_pushes"] == {"$ref": "#/$defs/list_map"}, name   # list-valued queue
    assert "preview" in schemas["general-six-content"]["$defs"]["candidate"]["properties"]
    assert "preview" not in schemas["general-six"]["$defs"]["candidate"]["properties"]


def test_digests_are_stable_and_distinct():
    first = [tool.digest(s) for _, s in tool.representative_schemas()]
    again = [tool.digest(s) for _, s in tool.representative_schemas()]
    assert first == again and len(set(first)) == len(first)


def test_an_accepted_request_with_a_valid_envelope_passes():
    results = tool.check(["m1"], lambda **kw: reply(SILENCE))
    assert len(results) == 5 and tool.passed(results)
    assert all(r["accepted"] and r["envelope_valid"] is True and r["error"] is None for r in results)


@pytest.mark.parametrize("create,expect", [
    (lambda **kw: (_ for _ in ()).throw(Rejected("schema rejected")), "rejected"),
    (lambda **kw: reply(refusal="I can't help with that."), "refusal"),
    (lambda **kw: reply({"has_insight": "no"}), "invalid"),
    (lambda **kw: reply(raw="not json"), "invalid"),
], ids=["endpoint-rejects-the-schema", "refusal", "envelope-violates-the-schema", "not-json"])
def test_every_failure_is_reported_as_a_failure(create, expect):
    results = tool.check(["m1"], create)
    assert not tool.passed(results)
    row = results[0]
    if expect == "rejected":
        assert not row["accepted"] and "status=400" in row["error"] and "invalid_json_schema" in row["error"]
    elif expect == "refusal":
        assert not row["accepted"] and row["error"] == "refusal"
    else:
        assert row["accepted"] and row["envelope_valid"] is False
    assert "FAIL" in tool.render(results)


def test_the_request_is_strict_and_carries_the_schema_whose_digest_is_recorded():
    sent = []
    tool.check(["m1"], lambda **kw: sent.append(kw) or reply(SILENCE))
    for (name, schema), call in zip(tool.representative_schemas(), sent):
        fmt = call["response_format"]
        assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
        assert tool.digest(fmt["json_schema"]["schema"]) == tool.digest(schema), name


def test_without_a_key_the_tool_refuses_before_any_call(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert tool.main(["--model", "m1"]) == 2
    assert "OPENAI_API_KEY is not set" in capsys.readouterr().err
