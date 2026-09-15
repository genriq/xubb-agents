"""Every example in the guides that claims to run, runs.

The 2026-09-15 design review's tier-3 acceptance criterion was that extracted
recipes are *verified*, not relabelled: "revalidate each recipe before labeling
it current, with executable examples where it makes a runtime claim."

So a fenced ```python block preceded by `<!-- runnable -->` is executed here,
against the real engine with the provider substituted at its boundary. A block
without that marker is illustrative — a configuration fragment, a signature —
and is not executed.

If you add a runnable block to a guide, it runs in CI from that moment. If you
add one that cannot run, CI tells you before a reader finds out.
"""
import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from xubb_agents.core import engine as engine_module

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"

GUIDES = [
    DOCS / "DESIGN_GUIDE.md",
    DOCS / "guides" / "authoring-agents.md",
    DOCS / "guides" / "orchestration.md",
    DOCS / "guides" / "host-integration.md",
    DOCS / "guides" / "long-form-content.md",
]

RUNNABLE = re.compile(r"<!--\s*runnable\s*-->\s*\n```python\n(.*?)```", re.S)


class _FakeLLMClient:
    """The provider boundary. Everything above it is the real engine."""

    ENVELOPE = {"has_insight": True,
                "insight": {"type": "suggestion", "content": "A concrete next step.",
                            "confidence": 0.7, "urgency": "soon"}}

    def __init__(self, *args, **kwargs):
        self.calls = []

    async def generate(self, model=None, messages=None, **kwargs):
        from xubb_agents.core.llm import LLMResult
        self.calls.append({"model": model})
        raw = json.dumps(self.ENVELOPE).encode("utf-8")
        return LLMResult(parsed=self.ENVELOPE, finish_reason="stop", transport="json_object",
                         raw_bytes=len(raw), usage={"prompt_tokens": 3, "completion_tokens": 9})

    def close(self):
        pass


def _blocks():
    found = []
    for guide in GUIDES:
        assert guide.exists(), f"guide missing: {guide.relative_to(REPO)}"
        text = guide.read_text(encoding="utf-8")
        for i, code in enumerate(RUNNABLE.findall(text)):
            found.append(pytest.param(code, id=f"{guide.stem}-{i}"))
    return found


BLOCKS = _blocks()


def test_the_guides_carry_runnable_examples():
    """A guard on the guard: if the marker convention is renamed or the guides are
    moved, this suite would silently verify nothing."""
    assert len(BLOCKS) >= 4, (
        f"expected runnable examples across the guides, found {len(BLOCKS)} — "
        "has the <!-- runnable --> convention changed?")


@pytest.mark.parametrize("code", BLOCKS)
def test_guide_example_runs(code):
    with patch.object(engine_module, "LLMClient", _FakeLLMClient):
        exec(compile(code, "<guide example>", "exec"), {"__name__": "__guide__"})


@pytest.mark.parametrize("code", BLOCKS)
def test_guide_example_emits_no_engine_deprecation_warning(code, recwarn):
    """A current guide must not teach a deprecated practice — the same rule the
    README examples are held to."""
    with patch.object(engine_module, "LLMClient", _FakeLLMClient):
        exec(compile(code, "<guide example>", "exec"), {"__name__": "__guide__"})
    offenders = [str(w.message) for w in recwarn
                 if issubclass(w.category, DeprecationWarning)
                 and any(m in str(w.message)
                         for m in ("is deprecated since", "legacy root-presence envelope"))]
    assert offenders == [], offenders
