"""README example drift-lock (public-release audit).

The README's copy-paste example once crashed on `insight['type']`: insights are
`AgentInsight` objects, not dicts, so subscripting raised `TypeError` on the very first
code a newcomer runs. These tests extract the actual ```python blocks from README.md and
execute them, so a regression in the README fails CI instead of greeting the next reader
with a traceback. No OpenAI key or network required.

**What is substituted, and why it matters** (2026-09-15 design review, SS5). The earlier
version replaced `AgentEngine.process_turn` wholesale, which proved the block constructed
and printed but bypassed the engine entirely — generation, parsing, validation and
acceptance never ran, so the test could not have caught a README example that produces an
envelope the engine rejects. The substitution is now at the **provider boundary**: a fake
`LLMClient` returns a canned envelope and the real engine path runs end to end.

The offline example needs no substitution at all and is executed verbatim.
"""

import json
import re
import warnings
from pathlib import Path
from unittest.mock import patch

import xubb_agents
from xubb_agents.core import engine as engine_module

REPO_ROOT = Path(__file__).resolve().parent.parent
README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def _extract_quickstart_block() -> str:
    """The fenced ```python block under 'With a model' — the LLM-backed example."""
    match = re.search(r"##\s*With a model.*?```python\n(.*?)```", README, re.S)
    assert match, "'With a model' python block not found in README.md"
    return match.group(1)


def _extract_offline_block() -> str:
    """The fenced ```python block under 'Run it now' — the no-key example."""
    match = re.search(r"##\s*Run it now.*?```python\n(.*?)```", README, re.S)
    assert match, "'Run it now' python block not found in README.md"
    return match.group(1)


class _FakeLLMClient:
    """Stands in for the provider at the boundary the engine actually calls.

    Everything above it — the generated instruction, the envelope the model
    'returns', parsing, validation, the acceptance boundary and the merge — is
    the real engine.
    """

    ENVELOPE = {"has_insight": True,
                "insight": {"type": "suggestion",
                            "content": "Acknowledge the budget concern before pitching.",
                            "confidence": 0.8, "urgency": "soon"}}

    def __init__(self, *args, **kwargs):
        self.calls = []

    async def generate(self, model=None, messages=None, **kwargs):
        from xubb_agents.core.llm import LLMResult
        self.calls.append({"model": model, "messages": messages, **kwargs})
        raw = json.dumps(self.ENVELOPE).encode("utf-8")
        return LLMResult(parsed=self.ENVELOPE, finish_reason="stop", transport="json_object",
                         raw_bytes=len(raw), usage={"prompt_tokens": 3, "completion_tokens": 9})

    def close(self):
        pass


def test_readme_model_example_runs_through_the_real_engine(capsys):
    """The LLM-backed example, with only the provider substituted.

    A dict-subscript regression (insight['type']) raises TypeError here — and so
    would an example whose configuration the engine refuses, which the previous
    whole-method stub could not see.
    """
    code = _extract_quickstart_block()
    with patch.object(engine_module, "LLMClient", _FakeLLMClient):
        exec(compile(code, "<README with-a-model>", "exec"), {"__name__": "__readme__"})

    out = capsys.readouterr().out
    assert "[suggestion]" in out, (
        "the example did not render the insight via attribute access "
        f"(insight.type.value / insight.content); captured stdout: {out!r}")
    assert "acceptance: accepted" in out, (
        f"the real engine did not accept the example's envelope; stdout: {out!r}")


def test_the_model_example_really_exercises_the_engine(capsys):
    """NEGATIVE CONTROL for the substitution. If the engine were still stubbed out,
    an envelope it must reject would sail through. Feed it one and require the
    engine to refuse it — that is only possible if the real path runs."""
    class RefusedClient(_FakeLLMClient):
        ENVELOPE = {"has_insight": True, "insight": {"type": "not_a_real_purpose",
                                                     "content": "x"}}

    code = _extract_quickstart_block()
    with patch.object(engine_module, "LLMClient", RefusedClient):
        exec(compile(code, "<README with-a-model>", "exec"), {"__name__": "__readme__"})
    out = capsys.readouterr().out
    # The MERGED turn response still reads "accepted" - one rejected agent does not
    # fail the turn (see docs/DIAGNOSTICS.md, per-agent aggregation). What proves the
    # engine ran is that the invalid insight never reached the output.
    assert "[suggestion]" not in out, (
        f"an invalid insight type was published — validation is being bypassed; stdout: {out!r}")
    assert "(silent" in out, f"expected the example to report silence; stdout: {out!r}"


def test_readme_offline_quickstart_runs(capsys):
    # The "Run it offline" block promises real output with no key and no network.
    # Execute it verbatim, unpatched, to keep that promise honest.
    code = _extract_offline_block()
    exec(compile(code, "<README offline quickstart>", "exec"), {"__name__": "__readme__"})

    out = capsys.readouterr().out
    assert "[suggestion]" in out, f"offline quickstart produced no insight; captured stdout: {out!r}"


# ---------------------------------------------------------------------------
# Design-review requirement (2026-09-15): a CURRENT runnable example must not
# teach a practice the engine deprecates. The flagship Quickstart inherited the
# deprecated `default` output format, so the first code a newcomer copied warned
# at them — and CI was green, because nothing asserted otherwise.
#
# Scope note: this asserts on the engine's OWN deprecation warnings, matched by
# the markers below, not on every DeprecationWarning in the process. A warning
# from a dependency is not this repository's example teaching bad practice.
# ---------------------------------------------------------------------------

#: Substrings that identify a deprecation warning this library raised. Kept
#: explicit so a dependency's DeprecationWarning cannot fail the suite, and so a
#: new engine deprecation must be added here deliberately.
ENGINE_DEPRECATION_MARKERS = ("is deprecated since", "legacy root-presence envelope")


def _engine_deprecations(caught):
    return [str(w.message) for w in caught
            if issubclass(w.category, DeprecationWarning)
            and any(m in str(w.message) for m in ENGINE_DEPRECATION_MARKERS)]


def _run_quickstart_capturing_warnings():
    code = _extract_quickstart_block()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with patch.object(engine_module, "LLMClient", _FakeLLMClient):
            exec(compile(code, "<README with-a-model>", "exec"), {"__name__": "__readme__"})
    return caught


def test_readme_model_example_emits_no_engine_deprecation_warning():
    """The flagship example sets `output_format` explicitly, so it inherits
    nothing deprecated."""
    found = _engine_deprecations(_run_quickstart_capturing_warnings())
    assert found == [], (
        "the README example teaches a deprecated practice; a newcomer's first "
        f"copy-paste warns at them: {found}")


def test_readme_offline_example_emits_no_engine_deprecation_warning():
    code = _extract_offline_block()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        exec(compile(code, "<README offline quickstart>", "exec"), {"__name__": "__readme__"})
    assert _engine_deprecations(caught) == []


def test_control_the_detector_catches_a_deprecated_example():
    """NEGATIVE CONTROL. Two tests above pass if the detector simply never fires,
    so prove it fires: the configuration the Quickstart used to carry — no
    `output_format`, inheriting the deprecated default — must be caught.

    This is also the shape a DELIBERATELY historical example would be tested in:
    assert the expected warning rather than forbidding all of them.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        xubb_agents.DynamicAgent({"id": "legacy-example", "name": "legacy-example",
                                  "text": "t", "trigger_config": {"cooldown": 0}})
    found = _engine_deprecations(caught)
    assert len(found) == 1 and "output_format 'default' is deprecated" in found[0], found
