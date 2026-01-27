"""
Integration tests for AgentEngine.
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

from xubb_agents.core.engine import AgentEngine
from xubb_agents.core.agent import BaseAgent, AgentConfig
from xubb_agents.core.models import (
    AgentContext, AgentResponse, AgentInsight, InsightType, 
    TriggerType, TranscriptSegment, Event, Fact
)
from xubb_agents.core.blackboard import Blackboard


class MockAgent(BaseAgent):
    """A mock agent for testing."""
    
    def __init__(self, name: str, priority: int = 0, 
                 subscribed_events: list = None,
                 trigger_conditions: dict = None,
                 response_fn=None):
        config = AgentConfig(
            name=name,
            priority=priority,
            trigger_types=[TriggerType.TURN_BASED, TriggerType.EVENT],
            subscribed_events=subscribed_events,
            trigger_conditions=trigger_conditions
        )
        super().__init__(config)
        self.response_fn = response_fn
        self.call_count = 0
    
    async def evaluate(self, context: AgentContext) -> AgentResponse:
        self.call_count += 1
        if self.response_fn:
            return self.response_fn(context, self)
        return AgentResponse()


@pytest.fixture
def engine():
    return AgentEngine(api_key="test_key")


@pytest.fixture
def sample_context():
    bb = Blackboard()
    bb.set_var("phase", "discovery")
    return AgentContext(
        session_id="test_session",
        recent_segments=[
            TranscriptSegment(speaker="USER", text="Hello", timestamp=1.0)
        ],
        blackboard=bb,
        turn_count=1
    )


class TestEngineBasics:
    """Test basic engine functionality."""
    
    def test_register_agent(self, engine):
        agent = MockAgent("test_agent")
        engine.register_agent(agent)
        
        assert len(engine.agents) == 1
        assert agent.llm is not None  # LLM should be injected
    
    def test_get_agents_by_trigger_type(self, engine):
        agent1 = MockAgent("agent1")
        agent2 = MockAgent("agent2")
        engine.register_agent(agent1)
        engine.register_agent(agent2)
        
        agents = engine.get_agents_by_trigger_type(TriggerType.TURN_BASED)
        assert len(agents) == 2
    
    def test_get_event_subscribers(self, engine):
        agent1 = MockAgent("agent1", subscribed_events=["question_detected"])
        agent2 = MockAgent("agent2", subscribed_events=["objection_raised"])
        agent3 = MockAgent("agent3")  # No subscriptions
        
        engine.register_agent(agent1)
        engine.register_agent(agent2)
        engine.register_agent(agent3)
        
        subscribers = engine.get_event_subscribers(["question_detected"])
        assert len(subscribers) == 1
        assert subscribers[0].config.name == "agent1"


class TestProcessTurn:
    """Test process_turn execution."""
    
    @pytest.mark.asyncio
    async def test_basic_turn(self, engine, sample_context):
        agent = MockAgent("test_agent")
        engine.register_agent(agent)
        
        response = await engine.process_turn(sample_context)
        
        assert agent.call_count == 1
        assert isinstance(response, AgentResponse)
    
    @pytest.mark.asyncio
    async def test_sys_variables_set(self, engine, sample_context):
        """Engine should set sys.* variables."""
        agent = MockAgent("test_agent")
        engine.register_agent(agent)
        
        await engine.process_turn(sample_context)
        
        bb = sample_context.blackboard
        assert bb.get_var("sys.turn_count") == 1
        assert bb.get_var("sys.session_id") == "test_session"
    
    @pytest.mark.asyncio
    async def test_allowed_agent_ids_filter(self, engine, sample_context):
        agent1 = MockAgent("agent1")
        agent2 = MockAgent("agent2")
        engine.register_agent(agent1)
        engine.register_agent(agent2)
        
        # Only allow agent1
        await engine.process_turn(
            sample_context, 
            allowed_agent_ids=[agent1.config.id]
        )
        
        assert agent1.call_count == 1
        assert agent2.call_count == 0
    
    @pytest.mark.asyncio
    async def test_trigger_conditions_evaluated(self, engine, sample_context):
        """Agents with failing conditions should be skipped."""
        # Agent with condition that will fail
        agent = MockAgent(
            "conditional_agent",
            trigger_conditions={
                "mode": "all",
                "rules": [{"var": "phase", "op": "eq", "value": "closing"}]
            }
        )
        engine.register_agent(agent)
        
        # Phase is "discovery", condition requires "closing"
        await engine.process_turn(sample_context)
        
        assert agent.call_count == 0  # Should not run


class TestMultiPhaseExecution:
    """Test multi-phase execution with events."""
    
    @pytest.mark.asyncio
    async def test_phase2_triggered_by_events(self, engine, sample_context):
        """Events emitted in Phase 1 should trigger Phase 2."""
        
        def emit_event(context, agent):
            return AgentResponse(
                events=[Event(
                    name="question_detected",
                    payload={"question": "What is pricing?"},
                    source_agent=agent.config.id,
                    timestamp=time.time()
                )]
            )
        
        # Phase 1 agent emits event
        emitter = MockAgent("emitter", response_fn=emit_event)
        
        # Phase 2 agent subscribes to event
        subscriber = MockAgent(
            "subscriber", 
            subscribed_events=["question_detected"]
        )
        
        engine.register_agent(emitter)
        engine.register_agent(subscriber)
        
        await engine.process_turn(sample_context)
        
        assert emitter.call_count == 1
        assert subscriber.call_count == 1  # Should run in Phase 2
    
    @pytest.mark.asyncio
    async def test_phase2_events_not_dispatched(self, engine, sample_context):
        """Events from Phase 2 are recorded but not dispatched."""
        
        def emit_event_phase1(context, agent):
            return AgentResponse(
                events=[Event(
                    name="event1",
                    payload={},
                    source_agent=agent.config.id,
                    timestamp=time.time()
                )]
            )
        
        def emit_event_phase2(context, agent):
            return AgentResponse(
                events=[Event(
                    name="event2",
                    payload={},
                    source_agent=agent.config.id,
                    timestamp=time.time()
                )]
            )
        
        emitter = MockAgent("emitter", response_fn=emit_event_phase1)
        subscriber = MockAgent(
            "subscriber",
            subscribed_events=["event1"],
            response_fn=emit_event_phase2
        )
        # This agent would be triggered by event2 if Phase 3 existed
        would_be_triggered = MockAgent(
            "would_be",
            subscribed_events=["event2"]
        )
        
        engine.register_agent(emitter)
        engine.register_agent(subscriber)
        engine.register_agent(would_be_triggered)
        
        response = await engine.process_turn(sample_context)
        
        # event2 should be in response (recorded)
        assert any(e.name == "event2" for e in response.events)
        
        # But would_be should NOT have been called (no Phase 3)
        assert would_be_triggered.call_count == 0


class TestMergeOrdering:
    """Test deterministic merge ordering."""
    
    @pytest.mark.asyncio
    async def test_higher_priority_wins(self, engine, sample_context):
        """Higher priority agents should win (write last)."""
        
        def set_phase_low(context, agent):
            return AgentResponse(
                variable_updates={"phase": "low_priority_value"}
            )
        
        def set_phase_high(context, agent):
            return AgentResponse(
                variable_updates={"phase": "high_priority_value"}
            )
        
        low_agent = MockAgent("low", priority=1, response_fn=set_phase_low)
        high_agent = MockAgent("high", priority=10, response_fn=set_phase_high)
        
        engine.register_agent(low_agent)
        engine.register_agent(high_agent)
        
        response = await engine.process_turn(sample_context)
        
        # High priority should win
        assert response.variable_updates["phase"] == "high_priority_value"
        assert sample_context.blackboard.get_var("phase") == "high_priority_value"


class TestAtomicFailure:
    """Test that failed agents have updates discarded."""
    
    @pytest.mark.asyncio
    async def test_failed_agent_updates_discarded(self, engine, sample_context):
        """If an agent fails, its updates should not be applied."""
        
        def succeed(context, agent):
            return AgentResponse(
                variable_updates={"success_key": "success_value"}
            )
        
        def fail(context, agent):
            raise Exception("Agent failed!")
        
        success_agent = MockAgent("success", response_fn=succeed)
        fail_agent = MockAgent("fail", response_fn=fail)
        
        engine.register_agent(success_agent)
        engine.register_agent(fail_agent)
        
        response = await engine.process_turn(sample_context)
        
        # Success agent's updates should be applied
        assert sample_context.blackboard.get_var("success_key") == "success_value"
        
        # No ERROR insight from the fail_agent in response
        # (errors are handled by BaseAgent.process, not engine)


class TestV1Compatibility:
    """Test backward compatibility with v1 patterns."""
    
    @pytest.mark.asyncio
    async def test_shared_state_synced_to_blackboard(self, engine, sample_context):
        """shared_state should be synced from blackboard.variables."""
        sample_context.blackboard.set_var("new_key", "new_value")
        
        # Create a mock agent that reads shared_state
        received_state = {}
        
        def capture_state(context, agent):
            received_state.update(context.shared_state)
            return AgentResponse()
        
        agent = MockAgent("test", response_fn=capture_state)
        engine.register_agent(agent)
        
        await engine.process_turn(sample_context)
        
        # Agent should have seen the blackboard variable in shared_state
        assert received_state.get("new_key") == "new_value"
    
    @pytest.mark.asyncio
    async def test_state_updates_mapped_to_variable_updates(self, engine, sample_context):
        """Legacy state_updates should be mapped to variable_updates."""
        
        def use_legacy_state_updates(context, agent):
            resp = AgentResponse()
            resp.state_updates = {"legacy_key": "legacy_value"}
            return resp
        
        agent = MockAgent("legacy", response_fn=use_legacy_state_updates)
        engine.register_agent(agent)
        
        response = await engine.process_turn(sample_context)
        
        # state_updates should be preserved in response
        assert response.state_updates.get("legacy_key") == "legacy_value"


class TestSnapshotIsolation:
    """Test that agents see consistent snapshot within a phase."""
    
    @pytest.mark.asyncio
    async def test_agents_see_snapshot(self, engine, sample_context):
        """All agents in a phase should see the same initial state."""
        
        seen_values = []
        
        def capture_and_modify(context, agent):
            # Capture what we see
            seen_values.append(context.blackboard.get_var("counter"))
            # Try to modify (should not affect other agents in same phase)
            return AgentResponse(
                variable_updates={"counter": (context.blackboard.get_var("counter") or 0) + 1}
            )
        
        sample_context.blackboard.set_var("counter", 0)
        
        agent1 = MockAgent("agent1", response_fn=capture_and_modify)
        agent2 = MockAgent("agent2", response_fn=capture_and_modify)
        
        engine.register_agent(agent1)
        engine.register_agent(agent2)
        
        await engine.process_turn(sample_context)
        
        # Both agents should have seen 0 (the snapshot value)
        assert seen_values == [0, 0]
        
        # Final value depends on merge order (both wrote 1, last wins)
        # Since both have same priority, registration order determines winner
        assert sample_context.blackboard.get_var("counter") == 1
