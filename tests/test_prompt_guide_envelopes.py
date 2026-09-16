"""The prompt guide's documented envelopes are fed to the real engine.

Design review, 2026-09-15, finding 3: the guide told a current reader to write
`default_v2` for anything that also writes the Blackboard — a format removed in
4.0.0 — and its worked example and field reference described that flat envelope
rather than the canonical one. A superseded banner at the top did not stop the
instruction at the bottom.

Correcting the prose is not enough on its own: nothing would have caught the
error, and nothing would catch the next one. So the guide's §4 examples are
executed. A JSON block under "The `insight_v1` Schema" is an envelope the guide
tells a model to emit, so the engine must accept it — anything the engine would
refuse, or that inherits a deprecated format, fails the build here.

Only the provider boundary is substituted; parsing, validation, the acceptance
boundary and the merge are the real engine.
"""

import asyncio
import json
import re
import warnings
from pathlib import Path
from unittest.mock import patch

from xubb_agents import AgentContext, Blackboard, DynamicAgent
from xubb_agents.core import engine as engine_module
from xubb_agents.core.engine import AgentEngine

REPO_ROOT = Path(__file__).resolve().parent.parent
GUIDE = (REPO_ROOT / "docs" / "prompt_engineering_guide.md").read_text(encoding="utf-8")

#: Reused from the README drift-lock: warnings this library itself raises.
ENGINE_DEPRECATION_MARKERS = ("is deprecated since", "legacy root-presence envelope")


def _documented_envelopes():
    """Every ```json block under the current schema section of §4."""
    section = re.search(
        r"### The `insight_v1` Schema\n(.*?)\n### Field Reference", GUIDE, re.S)
    assert section, "the `insight_v1` schema section is missing from the prompt guide"
    blocks = re.findall(r"```json\n(.*?)```", section.group(1), re.S)
    assert blocks, "the `insight_v1` schema section carries no json example"
    return [json.loads(b) for b in blocks]


class _FakeLLMClient:
    """Returns one canned envelope at the boundary the engine actually calls."""

    ENVELOPE = {}

    def __init__(self, *args, **kwargs):
        pass

    async def generate(self, model=None, messages=None, **kwargs):
        from xubb_agents.core.llm import LLMResult
        raw = json.dumps(self.ENVELOPE).encode("utf-8")
        return LLMResult(parsed=self.ENVELOPE, finish_reason="stop",
                         transport="json_object", raw_bytes=len(raw),
                         usage={"prompt_tokens": 3, "completion_tokens": 9})

    def close(self):
        pass


def _run(envelope, output_format="insight_v1"):
    """Push one envelope through the real engine; return (response, warnings)."""
    client = type("_Client", (_FakeLLMClient,), {"ENVELOPE": envelope})
    agent = DynamicAgent({
        "id": "guide_agent",
        "name": "Guide agent",
        "text": "You are documented in the prompt engineering guide.",
        "output_format": output_format,
    })
    context = AgentContext(session_id="guide", recent_segments=[], blackboard=Blackboard())
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with patch.object(engine_module, "LLMClient", client):
            engine = AgentEngine(api_key="test-key")
            engine.register_agent(agent)
            response = asyncio.run(engine.process_turn(context))
    deprecations = [str(w.message) for w in caught
                    if issubclass(w.category, DeprecationWarning)
                    and any(m in str(w.message) for m in ENGINE_DEPRECATION_MARKERS)]
    return response, deprecations


def test_the_guide_documents_a_spoken_and_a_silent_envelope():
    """CONTROL for the extractor: if the section stopped carrying examples, or the
    heading were renamed, the two tests below would pass vacuously."""
    envelopes = _documented_envelopes()
    assert len(envelopes) >= 2, f"expected a spoken and a silent example, got {envelopes}"
    assert any(e.get("has_insight") is True for e in envelopes), "no spoken example"
    assert any(e.get("has_insight") is False for e in envelopes), "no silent example"


def test_every_documented_envelope_is_accepted_by_the_engine():
    for envelope in _documented_envelopes():
        response, _ = _run(envelope)
        status = response.acceptance_by_agent.get("guide_agent")
        # AgentResponse carries `diagnostics` (a flat list carrying agent_id), not a
        # `diagnostics_by_agent` mapping — an earlier draft of this message assumed the
        # latter, which would have raised AttributeError instead of reporting the cause
        # on the one path that matters.
        codes = [d.code for d in (response.diagnostics or [])
                 if getattr(d, "agent_id", None) == "guide_agent"]
        assert status != "rejected", (
            f"the prompt guide documents an envelope the engine rejects: "
            f"{json.dumps(envelope)} -> {status} ({codes})")


def test_the_documented_spoken_envelope_actually_publishes_an_insight():
    spoken = [e for e in _documented_envelopes() if e.get("has_insight") is True]
    for envelope in spoken:
        response, _ = _run(envelope)
        assert response.insights, (
            f"a documented spoken envelope produced no insight: {json.dumps(envelope)}")


def test_the_documented_silent_envelope_still_commits_state():
    """The guide says silence "may still write state". Hold it to that."""
    silent = [e for e in _documented_envelopes()
              if e.get("has_insight") is False and e.get("variable_updates")]
    assert silent, "the guide's silent example no longer demonstrates a state write"
    for envelope in silent:
        response, _ = _run(envelope)
        assert response.acceptance_by_agent.get("guide_agent") == "accepted_silent"
        for key, value in envelope["variable_updates"].items():
            assert response.variable_updates.get(key) == value, (
                f"the guide promises a silent turn still writes state, but {key} "
                f"did not reach the response: {dict(response.variable_updates)}")


def test_the_documented_envelopes_teach_no_deprecated_format():
    for envelope in _documented_envelopes():
        _, deprecations = _run(envelope)
        assert deprecations == [], (
            f"the guide's example warns at the reader who copies it: {deprecations}")


def test_control_a_flat_envelope_is_refused_under_insight_v1():
    """NEGATIVE CONTROL. The tests above pass if the engine accepts everything.
    The flat shape the guide used to document — insight fields at the top level,
    which is `default_v2` — must NOT be accepted as `insight_v1`, or this file
    proves nothing about the envelope actually being correct."""
    flat = {"has_insight": True, "type": "suggestion",
            "content": "Brief advice here.", "confidence": 0.85}
    response, _ = _run(flat)
    assert response.acceptance_by_agent.get("guide_agent") == "rejected", (
        "a flat default_v2-shaped envelope was not rejected as insight_v1 — the "
        "envelope distinction this guide now documents is not actually enforced; "
        f"got {dict(response.acceptance_by_agent)}")
    assert not response.insights
