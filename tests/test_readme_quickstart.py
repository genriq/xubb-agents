"""README Quickstart drift-lock (public-release audit).

The README's copy-paste Quickstart once crashed on `insight['type']`: insights are
`AgentInsight` objects, not dicts, so subscripting raised `TypeError` on the very first
code a newcomer runs. This test extracts the actual ```python block from README.md and
executes it with the one network call (`process_turn`) stubbed, so a dict-subscript
regression in the README fails CI instead of greeting the next reader with a traceback.
No OpenAI key or network required.
"""

import re
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
