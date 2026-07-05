"""Registry-mutator concurrency + symmetry tests (public-release audit).

register_agent / unregister_agent / replace_agents all mutate the same three
structures (agents / _agent_index / _agent_meta) that a lock-free reader may be
traversing — a turn iterating self.agents, possibly on another thread while a vault
reload swaps agents (see the host's register_agents_from_vault). They must rebind
FRESH structures under the lock, never mutate in place. unregister_agent was also
missing entirely though the host relied on it (its test-agent cleanup called it).
These lock the fixed behavior. Contract: AGENT-REGISTRY-MUTATORS-CONSISTENT.
"""

import pytest

from xubb_agents.core.engine import AgentEngine
from xubb_agents.core.agent import BaseAgent, AgentConfig
from xubb_agents.core.models import AgentResponse


class _NoopAgent(BaseAgent):
    def __init__(self, agent_id, priority=0):
        super().__init__(AgentConfig(name=agent_id, id=agent_id, priority=priority))

    async def evaluate(self, context):  # pragma: no cover - never run here
        return AgentResponse()


@pytest.fixture
def engine():
    return AgentEngine(api_key="test_key")


def test_unregister_agent_removes_and_reports(engine):
    engine.register_agent(_NoopAgent("a"))
    engine.register_agent(_NoopAgent("b"))

    assert engine.unregister_agent("a") is True
    assert [a.config.id for a in engine.agents] == ["b"]
    assert "a" not in engine._agent_index
    # Indices/meta recomputed contiguously after removal.
    assert engine._agent_index["b"] == 0
    assert engine._agent_meta["b"] == (0, 0)


def test_unregister_unknown_returns_false(engine):
    engine.register_agent(_NoopAgent("a"))
    assert engine.unregister_agent("missing") is False
    assert len(engine.agents) == 1


def test_unregister_discards_warn_flag(engine):
    engine.register_agent(_NoopAgent("a"))
    engine._warned_subscriber_ids.add("a")
    engine.unregister_agent("a")
    assert "a" not in engine._warned_subscriber_ids


def test_register_rebinds_rather_than_mutating(engine):
    # A lock-free reader holding the old list must not observe the new agent appended
    # into it; register_agent rebinds a NEW list object instead of mutating in place.
    engine.register_agent(_NoopAgent("a"))
    old_list = engine.agents
    old_index = engine._agent_index
    engine.register_agent(_NoopAgent("b"))

    assert engine.agents is not old_list
    assert engine._agent_index is not old_index
    assert len(old_list) == 1  # the snapshot a concurrent reader held is intact
    assert [a.config.id for a in engine.agents] == ["a", "b"]


def test_unregister_rebinds_rather_than_mutating(engine):
    engine.register_agent(_NoopAgent("a"))
    engine.register_agent(_NoopAgent("b"))
    old_list = engine.agents
    engine.unregister_agent("a")

    assert engine.agents is not old_list
    assert len(old_list) == 2  # old snapshot untouched
