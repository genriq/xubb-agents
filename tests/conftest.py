"""
Pytest fixtures for xubb_agents tests.
"""

import pytest
import time
from pathlib import Path
from xubb_agents.core.models import (
    AgentContext, TranscriptSegment, TriggerType, Event, Fact
)
from xubb_agents.core.blackboard import Blackboard

#: The tracked API reference. The suite reads it and never writes it; only
#: ``python tools/gen_api_facts.py``, run by hand, may change it.
_API_REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "API_REFERENCE.md"


def _api_reference_bytes():
    return _API_REFERENCE.read_bytes() if _API_REFERENCE.exists() else None


@pytest.fixture(autouse=True)
def _no_test_changes_the_real_api_reference(request):
    """Fail, by name, any test that changes docs/API_REFERENCE.md.

    It runs around every test and its function-scoped fixtures; collection and
    wider-scoped fixtures are outside its reach. A test did change the file
    until 2026-09-25: the generator bound the real path at import, so the
    idempotence test rewrote it, and every run on a CRLF checkout left it
    modified.
    """
    before = _api_reference_bytes()
    yield
    if _api_reference_bytes() != before:
        pytest.fail(
            f"{request.node.nodeid} changed the tracked docs/API_REFERENCE.md. Tests work on a "
            "scratch copy (the docs fixture in tests/test_api_docs_gate.py). Restore the file "
            "with: git checkout -- docs/API_REFERENCE.md",
            pytrace=False,
        )


@pytest.fixture
def sample_blackboard():
    """Create a sample Blackboard with test data."""
    bb = Blackboard()
    bb.set_var("phase", "discovery")
    bb.set_var("sentiment", 0.7)
    bb.set_var("turn_count", 5)
    bb.push_queue("pending_questions", {"text": "What is pricing?", "speaker": "CUSTOMER"})
    bb.add_fact(Fact(
        type="budget",
        key="primary",
        value=50000,
        confidence=0.9,
        source_agent="extractor",
        timestamp=time.time()
    ))
    bb.update_memory("test_agent", {"counter": 3, "last_action": "greeting"})
    return bb


@pytest.fixture
def sample_context(sample_blackboard):
    """Create a sample AgentContext."""
    return AgentContext(
        session_id="test_session_123",
        recent_segments=[
            TranscriptSegment(speaker="CUSTOMER", text="Hello", timestamp=1.0),
            TranscriptSegment(speaker="AGENT", text="Hi there!", timestamp=2.0),
            TranscriptSegment(speaker="CUSTOMER", text="What's the price?", timestamp=3.0),
        ],
        shared_state={"legacy_key": "legacy_value"},
        blackboard=sample_blackboard,
        trigger_type=TriggerType.TURN_BASED,
        turn_count=5,
        phase=1
    )


@pytest.fixture
def sample_event():
    """Create a sample Event."""
    return Event(
        name="question_detected",
        payload={"question": "What is pricing?", "speaker": "CUSTOMER"},
        source_agent="question_extractor",
        timestamp=time.time()
    )


@pytest.fixture
def sample_fact():
    """Create a sample Fact."""
    return Fact(
        type="budget",
        key="primary",
        value=50000,
        confidence=0.9,
        source_agent="fact_extractor",
        timestamp=time.time()
    )
