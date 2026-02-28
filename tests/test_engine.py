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
    AgentContext, AgentConfigOverride, AgentResponse, AgentInsight, InsightType,
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


# =========================================================================
# FORCE Trigger Tests
# =========================================================================

class TestForceTrigger:
    """Test FORCE trigger bypass mechanics."""

    @pytest.mark.asyncio
    async def test_force_bypasses_trigger_type_mismatch(self, engine, sample_context):
        """FORCE should run a KEYWORD-only agent (trigger_type mismatch bypass)."""
        agent = MockAgent("keyword_only")
        agent.config.trigger_types = [TriggerType.KEYWORD]  # Not TURN_BASED or FORCE
        engine.register_agent(agent)

        response = await engine.process_turn(
            sample_context, trigger_type=TriggerType.FORCE
        )

        assert agent.call_count == 1

    @pytest.mark.asyncio
    async def test_force_bypasses_cooldown(self, engine, sample_context):
        """FORCE should run even when agent is in cooldown."""
        agent = MockAgent("cooldown_test")
        agent.config.cooldown = 9999  # Very long cooldown
        agent.last_run_time = time.time()  # Just ran
        engine.register_agent(agent)

        response = await engine.process_turn(
            sample_context, trigger_type=TriggerType.FORCE
        )

        assert agent.call_count == 1

    @pytest.mark.asyncio
    async def test_force_bypasses_trigger_conditions(self, engine, sample_context):
        """FORCE should bypass failing trigger_conditions."""
        agent = MockAgent(
            "conditional",
            trigger_conditions={
                "mode": "all",
                "rules": [{"var": "phase", "op": "eq", "value": "closing"}]
            }
        )
        engine.register_agent(agent)

        # Phase is "discovery" (set in fixture), condition requires "closing"
        response = await engine.process_turn(
            sample_context, trigger_type=TriggerType.FORCE
        )

        assert agent.call_count == 1

    @pytest.mark.asyncio
    async def test_force_does_not_bypass_allow_list(self, engine, sample_context):
        """FORCE does NOT bypass allow-list (host filter is authoritative)."""
        agent1 = MockAgent("allowed")
        agent2 = MockAgent("not_allowed")
        engine.register_agent(agent1)
        engine.register_agent(agent2)

        response = await engine.process_turn(
            sample_context,
            trigger_type=TriggerType.FORCE,
            allowed_agent_ids=[agent1.config.id]
        )

        assert agent1.call_count == 1
        assert agent2.call_count == 0

    @pytest.mark.asyncio
    async def test_force_updates_last_run_time(self, engine, sample_context):
        """FORCE runs still update last_run_time."""
        agent = MockAgent("timestamp_test")
        assert agent.last_run_time == 0.0
        engine.register_agent(agent)

        before = time.time()
        await engine.process_turn(
            sample_context, trigger_type=TriggerType.FORCE
        )

        assert agent.last_run_time >= before

    @pytest.mark.asyncio
    async def test_force_back_to_back(self, engine):
        """Two FORCE calls in quick succession should both succeed."""
        agent = MockAgent("back_to_back")
        agent.config.cooldown = 9999
        engine.register_agent(agent)

        bb = Blackboard()
        ctx1 = AgentContext(
            session_id="s1",
            recent_segments=[TranscriptSegment(speaker="USER", text="Hi", timestamp=1.0)],
            blackboard=bb, turn_count=1
        )
        ctx2 = AgentContext(
            session_id="s1",
            recent_segments=[TranscriptSegment(speaker="USER", text="Hi again", timestamp=2.0)],
            blackboard=bb, turn_count=2
        )

        await engine.process_turn(ctx1, trigger_type=TriggerType.FORCE)
        await engine.process_turn(ctx2, trigger_type=TriggerType.FORCE)

        assert agent.call_count == 2


# =========================================================================
# Override Tests
# =========================================================================

class TestAgentConfigOverrides:
    """Test agent_config_overrides mechanics."""

    @pytest.mark.asyncio
    async def test_cooldown_modifier_negative(self, engine):
        """Negative cooldown modifier speeds up agent (floor at 5s)."""
        agent = MockAgent("fast_agent")
        agent.config.cooldown = 60  # Base 60s
        engine.register_agent(agent)

        overrides = {agent.config.id: AgentConfigOverride(cooldown_modifier=-55)}

        bb = Blackboard()
        # First call - sets last_run_time
        ctx1 = AgentContext(
            session_id="s1",
            recent_segments=[TranscriptSegment(speaker="USER", text="Hi", timestamp=1.0)],
            blackboard=bb, turn_count=1,
            agent_config_overrides=overrides
        )
        await engine.process_turn(ctx1)
        assert agent.call_count == 1

        # Second call after 6s (> floor 5s, < base 60s) — should run with modifier
        agent.last_run_time = time.time() - 6  # Simulate 6s elapsed
        ctx2 = AgentContext(
            session_id="s1",
            recent_segments=[TranscriptSegment(speaker="USER", text="Update", timestamp=7.0)],
            blackboard=bb, turn_count=2,
            agent_config_overrides=overrides
        )
        await engine.process_turn(ctx2)
        assert agent.call_count == 2  # Ran because effective=5, 6>5

    @pytest.mark.asyncio
    async def test_cooldown_modifier_floor_at_5(self, engine):
        """Cooldown floor is 5s even with extreme negative modifier."""
        agent = MockAgent("floor_test")
        agent.config.cooldown = 10
        engine.register_agent(agent)

        overrides = {agent.config.id: AgentConfigOverride(cooldown_modifier=-100)}

        bb = Blackboard()
        ctx = AgentContext(
            session_id="s1",
            recent_segments=[TranscriptSegment(speaker="USER", text="Hi", timestamp=1.0)],
            blackboard=bb, turn_count=1,
            agent_config_overrides=overrides
        )
        await engine.process_turn(ctx)
        assert agent.call_count == 1

        # Set last_run_time to 3s ago (< floor 5s)
        agent.last_run_time = time.time() - 3
        ctx2 = AgentContext(
            session_id="s1",
            recent_segments=[TranscriptSegment(speaker="USER", text="Again", timestamp=4.0)],
            blackboard=bb, turn_count=2,
            agent_config_overrides=overrides
        )
        await engine.process_turn(ctx2)
        assert agent.call_count == 1  # Blocked by 5s floor

    @pytest.mark.asyncio
    async def test_override_no_cross_contamination(self, engine):
        """Overrides for agent A should not affect agent B."""
        agent_a = MockAgent("agent_a")
        agent_a.config.cooldown = 60
        agent_b = MockAgent("agent_b")
        agent_b.config.cooldown = 60
        engine.register_agent(agent_a)
        engine.register_agent(agent_b)

        # Only agent_a gets the fast override
        overrides = {agent_a.config.id: AgentConfigOverride(cooldown_modifier=-55)}

        bb = Blackboard()
        ctx = AgentContext(
            session_id="s1",
            recent_segments=[TranscriptSegment(speaker="USER", text="Hi", timestamp=1.0)],
            blackboard=bb, turn_count=1,
            agent_config_overrides=overrides
        )
        await engine.process_turn(ctx)
        assert agent_a.call_count == 1
        assert agent_b.call_count == 1

        # After 6s, agent_a (effective=5s) should run, agent_b (base=60s) should not
        agent_a.last_run_time = time.time() - 6
        agent_b.last_run_time = time.time() - 6

        ctx2 = AgentContext(
            session_id="s1",
            recent_segments=[TranscriptSegment(speaker="USER", text="Update", timestamp=7.0)],
            blackboard=bb, turn_count=2,
            agent_config_overrides=overrides
        )
        await engine.process_turn(ctx2)
        assert agent_a.call_count == 2  # Ran (effective cooldown=5, 6>5)
        assert agent_b.call_count == 1  # Blocked (base cooldown=60, 6<60)

    @pytest.mark.asyncio
    async def test_overrides_propagated_through_run_phase(self, engine, sample_context):
        """agent_config_overrides should survive into phase context snapshot."""
        overrides = {"test_agent": AgentConfigOverride(instructions_append="Extra info")}
        sample_context.agent_config_overrides = overrides

        received_overrides = {}

        def capture_overrides(context, agent):
            received_overrides.update(context.agent_config_overrides)
            return AgentResponse()

        agent = MockAgent("test_agent", response_fn=capture_overrides)
        engine.register_agent(agent)

        await engine.process_turn(sample_context)

        assert "test_agent" in received_overrides
        assert received_overrides["test_agent"].instructions_append == "Extra info"

    @pytest.mark.asyncio
    async def test_overrides_survive_into_phase2(self, engine, sample_context):
        """Overrides propagated into Phase 2 for event-triggered agents."""
        overrides = {"subscriber": AgentConfigOverride(cooldown_modifier=-5)}
        sample_context.agent_config_overrides = overrides

        received_overrides = {}

        def emit_event(context, agent):
            return AgentResponse(
                events=[Event(
                    name="test_event", payload={},
                    source_agent=agent.config.id, timestamp=time.time()
                )]
            )

        def capture_overrides_phase2(context, agent):
            received_overrides.update(context.agent_config_overrides)
            return AgentResponse()

        emitter = MockAgent("emitter", response_fn=emit_event)
        subscriber = MockAgent(
            "subscriber",
            subscribed_events=["test_event"],
            response_fn=capture_overrides_phase2
        )
        engine.register_agent(emitter)
        engine.register_agent(subscriber)

        await engine.process_turn(sample_context)

        assert "subscriber" in received_overrides
        assert received_overrides["subscriber"].cooldown_modifier == -5

    @pytest.mark.asyncio
    async def test_force_debug_log_when_no_override(self, engine, sample_context):
        """FORCE with overrides dict non-empty + agent missing → debug log (no crash)."""
        # Override for a different agent
        overrides = {"other_agent": AgentConfigOverride(cooldown_modifier=-5)}
        sample_context.agent_config_overrides = overrides

        agent = MockAgent("this_agent")
        engine.register_agent(agent)

        # Should log debug but still run
        response = await engine.process_turn(
            sample_context, trigger_type=TriggerType.FORCE
        )
        assert agent.call_count == 1

    def test_override_extra_forbid_rejects_typos(self):
        """AgentConfigOverride with extra='forbid' rejects unknown fields."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            AgentConfigOverride(cooldown_modifer=-5)  # typo: modifer vs modifier
