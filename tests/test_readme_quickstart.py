"""README Quickstart drift-lock (public-release audit).

The README's copy-paste Quickstart once crashed on `insight['type']`: insights are
`AgentInsight` objects, not dicts, so subscripting raised `TypeError` on the very first
code a newcomer runs. This test extracts the actual ```python block from README.md and
executes it with the one network call (`process_turn`) stubbed, so a dict-subscript
regression in the README fails CI instead of greeting the next reader with a traceback.
No OpenAI key or network required.
"""

import re
import warnings
from pathlib import Path
from unittest.mock import patch

import xubb_agents
from xubb_agents.core.models import AgentInsight, AgentResponse, InsightType

REPO_ROOT = Path(__file__).resolve().parent.parent
README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def _extract_quickstart_block() -> str:
    """The first fenced ```python block under the Quickstart heading."""
    match = re.search(r"##\s*Quickstart.*?```python\n(.*?)```", README, re.S)
    assert match, "Quickstart python block not found in README.md"
    return match.group(1)


def _extract_offline_block() -> str:
    """The fenced ```python block under the 'Run it offline' subheading."""
    match = re.search(r"###\s*Run it offline.*?```python\n(.*?)```", README, re.S)
    assert match, "Offline Quickstart python block not found in README.md"
    return match.group(1)


def test_readme_quickstart_runs_offline(capsys):
    code = _extract_quickstart_block()

    async def _fake_process_turn(self, context, *args, **kwargs):
        # Stub the single OpenAI call so the block runs with no key and no network.
        return AgentResponse(
            source_agent_id="echo-coach",
            insights=[
                AgentInsight(
                    agent_id="echo-coach",
                    agent_name="Echo Coach",
                    type=InsightType.SUGGESTION,
                    content="Acknowledge the budget concern before pitching.",
                    confidence=0.8,
                )
            ],
        )

    with patch.object(xubb_agents.AgentEngine, "process_turn", _fake_process_turn):
        # A dict-subscript regression (insight['type']) would raise TypeError here.
        exec(compile(code, "<README quickstart>", "exec"), {"__name__": "__readme__"})

    out = capsys.readouterr().out
    assert "[suggestion]" in out, (
        "Quickstart did not render the insight via attribute access "
        f"(insight.type.value / insight.content); captured stdout: {out!r}"
    )


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
    async def _fake_process_turn(self, context, *args, **kwargs):
        return AgentResponse(source_agent_id="echo-coach", insights=[])

    code = _extract_quickstart_block()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with patch.object(xubb_agents.AgentEngine, "process_turn", _fake_process_turn):
            exec(compile(code, "<README quickstart>", "exec"), {"__name__": "__readme__"})
    return caught


def test_readme_quickstart_emits_no_engine_deprecation_warning():
    """The flagship example sets `output_format` explicitly, so it inherits
    nothing deprecated."""
    found = _engine_deprecations(_run_quickstart_capturing_warnings())
    assert found == [], (
        "the README Quickstart teaches a deprecated practice; a newcomer's first "
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
