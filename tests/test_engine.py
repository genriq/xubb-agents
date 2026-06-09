"""
Integration tests for AgentEngine.
"""

import pytest
import asyncio
import time
import logging
from unittest.mock import AsyncMock, MagicMock, patch

from xubb_agents.core.engine import AgentEngine
from xubb_agents.core.agent import BaseAgent, AgentConfig
from xubb_agents.core.models import (
    AgentContext, AgentConfigOverride, AgentResponse, AgentInsight, InsightType,
    TriggerType, TranscriptSegment, Event, Fact
)
from xubb_agents.core.blackboard import Blackboard

# T-4: a fixed "now" for deterministic cooldown-elapsed arithmetic (see frozen_clock fixture).
FROZEN_NOW = 10_000.0


class MockAgent(BaseAgent):
    """A mock agent for testing."""
    
    def __init__(self, name: str, priority: int = 0,
                 subscribed_events: list = None,
                 trigger_conditions: dict = None,
                 response_fn=None,
                 trigger_types: list = None):
        config = AgentConfig(
            name=name,
            priority=priority,
            trigger_types=trigger_types or [TriggerType.TURN_BASED, TriggerType.EVENT],
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
        
        # Phase 2 agent subscribes to event (EVENT-only: runs in Phase 2 only)
        subscriber = MockAgent(
            "subscriber",
            subscribed_events=["question_detected"],
            trigger_types=[TriggerType.EVENT]
        )
        subscriber.config.cooldown = 0  # Explicit: cooldown is not the gating mechanism

        engine.register_agent(emitter)
        engine.register_agent(subscriber)

        await engine.process_turn(sample_context)

        assert emitter.call_count == 1
        assert subscriber.call_count == 1  # Correctly tests Phase 2 event triggering
    
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
            response_fn=emit_event_phase2,
            trigger_types=[TriggerType.EVENT]
        )
        # This agent would be triggered by event2 if Phase 3 existed
        # EVENT-only so it doesn't run in Phase 1 as TURN_BASED
        would_be_triggered = MockAgent(
            "would_be",
            subscribed_events=["event2"],
            trigger_types=[TriggerType.EVENT]
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

    @pytest.mark.asyncio
    async def test_priority_beats_confidence_on_facts(self, engine, sample_context):
        """F-1 / INV-9: a higher-priority agent's fact wins even at lower confidence.

        Mirror of test_higher_priority_wins but for the facts merge path — the exact
        case that silently inverted before F-1. The engine must stamp the emitting agent's
        priority so Blackboard.add_fact resolves the (type, key) conflict by priority first.
        """
        def emit_high(context, agent):
            return AgentResponse(facts=[Fact(
                type="budget", key="primary", value="authoritative_high_priority",
                confidence=0.5, source_agent="high", timestamp=time.time(),
            )])

        def emit_low(context, agent):
            return AgentResponse(facts=[Fact(
                type="budget", key="primary", value="noisy_low_priority",
                confidence=0.9, source_agent="low", timestamp=time.time(),
            )])

        engine.register_agent(MockAgent("low", priority=1, response_fn=emit_low))
        engine.register_agent(MockAgent("high", priority=10, response_fn=emit_high))

        response = await engine.process_turn(sample_context)

        won = sample_context.blackboard.get_fact("budget", "primary")
        assert won is not None
        assert won.value == "authoritative_high_priority"
        assert any(
            f.type == "budget" and f.key == "primary"
            and f.value == "authoritative_high_priority"
            for f in response.facts
        )


class TestAtomicFailure:
    """Test that failed agents have updates discarded."""
    
    @pytest.mark.asyncio
    async def test_failed_agent_updates_discarded(self, engine, sample_context):
        """T-3 / INV-6: a failed agent's writes must NOT persist (atomic discard).

        Strengthened from the original (which only checked the *success* agent and so
        would pass even if a failed agent leaked state). The fail agent now performs an
        observable write against its snapshot BEFORE raising; that write must not reach
        the real blackboard — proving both atomic-discard-on-failure and snapshot
        isolation, the invariant this test names.
        """
        def succeed(context, agent):
            return AgentResponse(variable_updates={"success_key": "success_value"})

        def fail(context, agent):
            # Observable side effect on the snapshot, then fail. Must be discarded.
            context.blackboard.set_var("fail_key", "should_not_persist")
            raise Exception("Agent failed!")

        success_agent = MockAgent("success", response_fn=succeed)
        fail_agent = MockAgent("fail", response_fn=fail)

        engine.register_agent(success_agent)
        engine.register_agent(fail_agent)

        await engine.process_turn(sample_context)

        # The success agent's updates ARE applied...
        assert sample_context.blackboard.get_var("success_key") == "success_value"
        # ...but the failed agent's write is discarded (never reaches the real blackboard).
        assert sample_context.blackboard.get_var("fail_key") is None


class TestV22Closeout:
    """Phase 0/4 closeout: MR-1 memory sync, E-6 warn-once, E-7 max_phases clamp."""

    @pytest.mark.asyncio
    async def test_mr1_blackboard_memory_synced_to_shared_state(self, engine, sample_context):
        """MR-1: blackboard memory is synced into shared_state['memory_<id>'] before
        agents run, so cross-turn memory survives even when the agent instance is not
        reused (the read-path only looked at shared_state)."""
        sample_context.blackboard.update_memory("agent_x", {"counter": 7})
        captured = {}

        def capture(context, agent):
            captured["mem"] = context.shared_state.get("memory_agent_x")
            return AgentResponse()

        engine.register_agent(MockAgent("reader", response_fn=capture))
        await engine.process_turn(sample_context)
        assert captured["mem"] == {"counter": 7}

    @pytest.mark.asyncio
    async def test_mr1_synced_memory_is_a_copy(self, engine, sample_context):
        """MR-1 respects INV-8: the synced memory is a copy, not the blackboard's object."""
        sample_context.blackboard.update_memory("agent_x", {"nested": [1, 2]})

        def mutate(context, agent):
            context.shared_state["memory_agent_x"]["nested"].append(999)
            return AgentResponse()

        engine.register_agent(MockAgent("mutator", response_fn=mutate))
        await engine.process_turn(sample_context)
        assert sample_context.blackboard.get_memory("agent_x")["nested"] == [1, 2]

    def test_e6_subscriber_misconfig_warns_once(self, engine, caplog):
        """E-6: a subscriber missing TriggerType.EVENT warns once, not every call."""
        bad = MockAgent("bad", subscribed_events=["evt"],
                        trigger_types=[TriggerType.TURN_BASED])
        engine.register_agent(bad)
        with caplog.at_level(logging.WARNING, logger="AgentEngine"):
            for _ in range(3):
                engine.get_event_subscribers(["evt"])
        warns = [r for r in caplog.records
                 if "subscribed_events" in r.getMessage() and "bad" in r.getMessage()]
        assert len(warns) == 1

    def test_e7_max_phases_clamped(self):
        """E-7: unsupported max_phases is clamped to a supported value."""
        assert AgentEngine(api_key="k", max_phases=5).max_phases == 2
        assert AgentEngine(api_key="k", max_phases=0).max_phases == 1
        assert AgentEngine(api_key="k", max_phases=1).max_phases == 1
        assert AgentEngine(api_key="k", max_phases=2).max_phases == 2


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

    @pytest.fixture(autouse=True)
    def frozen_clock(self):
        """T-4: freeze the cooldown clock so elapsed time is exact and deterministic
        (no dependence on real wall-clock margins between setting last_run_time and the
        cooldown check). BaseAgent reads `time.time()` for `now`."""
        with patch("xubb_agents.core.agent.time.time", return_value=FROZEN_NOW):
            yield

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
        agent.last_run_time = FROZEN_NOW - 6  # exactly 6s elapsed (deterministic)
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
        agent.last_run_time = FROZEN_NOW - 3
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
        agent_a.last_run_time = FROZEN_NOW - 6
        agent_b.last_run_time = FROZEN_NOW - 6

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


# =========================================================================
# v2.1.1 Bugfix Regression Tests
# =========================================================================

class TestB1SubscriberTriggerTypeGuard:
    """B1: Phase 2 subscribers must have TriggerType.EVENT."""

    @pytest.mark.asyncio
    async def test_subscriber_without_event_trigger_type_is_excluded(self, engine, sample_context):
        """Subscriber with subscribed_events but no TriggerType.EVENT should be excluded from Phase 2."""
        def emit_event(context, agent):
            return AgentResponse(
                events=[Event(
                    name="test_event", payload={},
                    source_agent=agent.config.id, timestamp=time.time()
                )]
            )

        emitter = MockAgent("emitter", response_fn=emit_event)

        # Subscriber has subscribed_events but only TURN_BASED trigger type
        misconfigured = MockAgent(
            "misconfigured",
            subscribed_events=["test_event"],
            trigger_types=[TriggerType.TURN_BASED]  # No EVENT
        )

        engine.register_agent(emitter)
        engine.register_agent(misconfigured)

        await engine.process_turn(sample_context)

        # Validates exclusion from Phase 2: misconfigured ran once (Phase 1,
        # TURN_BASED) but was not selected for Phase 2 despite subscribed_events.
        assert misconfigured.call_count == 1

    @pytest.mark.asyncio
    async def test_subscriber_with_event_trigger_type_runs_in_phase2(self, engine, sample_context):
        """Correctly configured subscriber (EVENT in trigger_types) should run in Phase 2."""
        def emit_event(context, agent):
            return AgentResponse(
                events=[Event(
                    name="test_event", payload={},
                    source_agent=agent.config.id, timestamp=time.time()
                )]
            )

        emitter = MockAgent("emitter", response_fn=emit_event)
        subscriber = MockAgent(
            "subscriber",
            subscribed_events=["test_event"],
            trigger_types=[TriggerType.EVENT]
        )
        subscriber.config.cooldown = 0

        engine.register_agent(emitter)
        engine.register_agent(subscriber)

        await engine.process_turn(sample_context)

        assert emitter.call_count == 1
        assert subscriber.call_count == 1  # Ran in Phase 2

    def test_get_event_subscribers_filters_by_trigger_type(self, engine):
        """get_event_subscribers should only return agents with TriggerType.EVENT."""
        correct = MockAgent("correct", subscribed_events=["evt"],
                           trigger_types=[TriggerType.EVENT])
        misconfigured = MockAgent("misconfigured", subscribed_events=["evt"],
                                  trigger_types=[TriggerType.TURN_BASED])
        no_sub = MockAgent("no_sub")

        engine.register_agent(correct)
        engine.register_agent(misconfigured)
        engine.register_agent(no_sub)

        subscribers = engine.get_event_subscribers(["evt"])
        assert len(subscribers) == 1
        assert subscribers[0].config.name == "correct"


class TestB2Phase2SharedStateSync:
    """B2: Phase 2 v1 agents should see post-Phase-1 shared_state."""

    @pytest.mark.asyncio
    async def test_phase2_agents_see_updated_shared_state(self, engine, sample_context):
        """Phase 2 agents should see Phase 1's state updates in shared_state."""
        def emit_and_update(context, agent):
            return AgentResponse(
                variable_updates={"phase": "closing"},
                events=[Event(
                    name="phase_changed", payload={},
                    source_agent=agent.config.id, timestamp=time.time()
                )]
            )

        captured_state = {}

        def capture_shared_state(context, agent):
            captured_state["phase"] = context.shared_state.get("phase")
            return AgentResponse()

        emitter = MockAgent("emitter", response_fn=emit_and_update)
        subscriber = MockAgent(
            "subscriber",
            subscribed_events=["phase_changed"],
            response_fn=capture_shared_state,
            trigger_types=[TriggerType.EVENT]
        )
        subscriber.config.cooldown = 0

        engine.register_agent(emitter)
        engine.register_agent(subscriber)

        sample_context.blackboard.set_var("phase", "discovery")
        await engine.process_turn(sample_context)

        # Phase 2 subscriber should see the Phase 1 update
        assert captured_state["phase"] == "closing"


class TestB4MemoryUpdatesByAgent:
    """B4: memory_updates_by_agent should preserve per-agent attribution."""

    @pytest.mark.asyncio
    async def test_memory_updates_by_agent_preserves_attribution(self, engine, sample_context):
        """memory_updates_by_agent should be keyed by agent_id."""
        def mem_a(context, agent):
            return AgentResponse(memory_updates={"counter": 1})

        def mem_b(context, agent):
            return AgentResponse(memory_updates={"counter": 5})

        agent_a = MockAgent("agent_a", response_fn=mem_a)
        agent_b = MockAgent("agent_b", response_fn=mem_b)
        engine.register_agent(agent_a)
        engine.register_agent(agent_b)

        response = await engine.process_turn(sample_context)

        # New additive field preserves per-agent attribution
        assert response.memory_updates_by_agent[agent_a.config.id]["counter"] == 1
        assert response.memory_updates_by_agent[agent_b.config.id]["counter"] == 5

        # Existing flat field still works (last-write-wins, backward compatible)
        assert "counter" in response.memory_updates

    @pytest.mark.asyncio
    async def test_memory_updates_flat_field_unchanged(self, engine, sample_context):
        """Existing memory_updates flat dict should still work (backward compat)."""
        def mem_single(context, agent):
            return AgentResponse(memory_updates={"key": "value"})

        agent = MockAgent("single", response_fn=mem_single)
        engine.register_agent(agent)

        response = await engine.process_turn(sample_context)

        assert response.memory_updates["key"] == "value"


class TestB5OnChainError:
    """B5: on_chain_error should fire when engine errors."""

    @pytest.mark.asyncio
    async def test_on_chain_error_fires_on_engine_failure(self, engine, sample_context):
        """on_chain_error should fire when process_turn itself errors."""
        from xubb_agents.core.callbacks import AgentCallbackHandler

        class ErrorTracker(AgentCallbackHandler):
            def __init__(self):
                self.errors = []
            async def on_chain_error(self, error):
                self.errors.append(error)

        tracker = ErrorTracker()
        engine.callbacks = [tracker]

        with patch.object(engine, '_get_eligible_agents', side_effect=RuntimeError("engine boom")):
            with pytest.raises(RuntimeError, match="engine boom"):
                await engine.process_turn(sample_context)

        assert len(tracker.errors) == 1
        assert str(tracker.errors[0]) == "engine boom"

    @pytest.mark.asyncio
    async def test_on_chain_error_still_raises_to_host(self, engine, sample_context):
        """on_chain_error is observability only — the exception must still propagate."""
        from xubb_agents.core.callbacks import AgentCallbackHandler

        class SilentTracker(AgentCallbackHandler):
            async def on_chain_error(self, error):
                pass  # Swallow in callback — should NOT prevent re-raise

        engine.callbacks = [SilentTracker()]

        with patch.object(engine, '_get_eligible_agents', side_effect=ValueError("must propagate")):
            with pytest.raises(ValueError, match="must propagate"):
                await engine.process_turn(sample_context)

    @pytest.mark.asyncio
    async def test_on_chain_error_callback_failure_does_not_mask_original(self, engine, sample_context):
        """If on_chain_error itself errors, the original exception still propagates."""
        from xubb_agents.core.callbacks import AgentCallbackHandler

        class BrokenTracker(AgentCallbackHandler):
            async def on_chain_error(self, error):
                raise RuntimeError("callback crashed")

        engine.callbacks = [BrokenTracker()]

        with patch.object(engine, '_get_eligible_agents', side_effect=ValueError("original error")):
            with pytest.raises(ValueError, match="original error"):
                await engine.process_turn(sample_context)


class TestE2SysLeakIntoLegacy:
    """E-2: sys.* blackboard vars must not leak into legacy shared_state."""

    @pytest.mark.asyncio
    async def test_sys_keys_excluded_from_shared_state(self, engine, sample_context):
        """After sync, shared_state contains no sys.* keys but keeps normal vars."""
        captured = {}

        def capture_state(context, agent):
            captured.update(context.shared_state)
            return AgentResponse()

        agent = MockAgent("reader", response_fn=capture_state)
        engine.register_agent(agent)

        sample_context.blackboard.set_var("user_var", "visible")
        await engine.process_turn(sample_context)

        # The engine stamps sys.* vars (e.g. sys.turn_count) on the blackboard...
        assert sample_context.blackboard.get_var("sys.turn_count") == 1
        # ...but a v1 agent reading shared_state must never see them (E-2).
        assert not any(k.startswith("sys.") for k in captured), \
            f"sys.* leaked into shared_state: {[k for k in captured if k.startswith('sys.')]}"
        # Normal variables still flow through.
        assert captured.get("user_var") == "visible"

    @pytest.mark.asyncio
    async def test_v1_roundtrip_does_not_trip_sys_warning(self, engine, sample_context):
        """A v1 agent echoing shared_state back as state_updates must not warn (NP13)."""
        def echo_shared_state(context, agent):
            resp = AgentResponse()
            # Simulate a v1 agent blindly writing back everything it read.
            resp.state_updates = dict(context.shared_state)
            return resp

        agent = MockAgent("echo", response_fn=echo_shared_state)
        engine.register_agent(agent)

        with patch("xubb_agents.core.blackboard._bb_logger") as mock_log:
            await engine.process_turn(sample_context)

        sys_warnings = [
            c for c in mock_log.warning.call_args_list
            if "sys." in str(c)
        ]
        assert not sys_warnings, f"Unexpected sys.* warnings on v1 round-trip: {sys_warnings}"


class TestE3V1DualPathDrop:
    """E-3: legacy memory_ writes must survive a hybrid state_updates+variable_updates response."""

    @pytest.mark.asyncio
    async def test_memory_write_survives_hybrid_response(self, engine, sample_context):
        """A response with BOTH state_updates (incl. memory_x) and variable_updates
        must still apply the legacy memory_x write (E-3)."""
        target_agent_id = "mem_target"

        def hybrid(context, agent):
            resp = AgentResponse(variable_updates={"v2_var": "v2_value"})
            resp.state_updates = {
                f"memory_{target_agent_id}": {"legacy_mem_key": "legacy_mem_value"},
                "plain_var": "should_be_skipped",
            }
            return resp

        agent = MockAgent("hybrid", response_fn=hybrid)
        engine.register_agent(agent)

        await engine.process_turn(sample_context)

        # The legacy memory_ write is applied unconditionally.
        mem = sample_context.blackboard.get_memory(target_agent_id)
        assert mem.get("legacy_mem_key") == "legacy_mem_value"
        # The v2 variable still landed.
        assert sample_context.blackboard.get_var("v2_var") == "v2_value"
        # The plain legacy var is correctly superseded by v2 (not applied).
        assert sample_context.blackboard.get_var("plain_var") is None

    @pytest.mark.asyncio
    async def test_legacy_only_plain_var_still_applies(self, engine, sample_context):
        """Regression guard: with no variable_updates, plain legacy vars still map through."""
        def legacy_only(context, agent):
            resp = AgentResponse()
            resp.state_updates = {"plain_var": "applied"}
            return resp

        agent = MockAgent("legacy", response_fn=legacy_only)
        engine.register_agent(agent)

        await engine.process_turn(sample_context)
        assert sample_context.blackboard.get_var("plain_var") == "applied"


class TestE4UpdateApiKey:
    """E-4: update_api_key closes the previous client and documents its precondition."""

    def test_update_api_key_closes_previous_client(self, engine):
        """The previous LLMClient's underlying session is closed on swap."""
        closed = {"called": False}

        class FakeUnderlying:
            def close(self):
                closed["called"] = True

        # Replace the engine's current client's underlying session with a probe.
        engine.llm_client.client = FakeUnderlying()
        old_client = engine.llm_client

        engine.update_api_key("new_test_key")

        assert closed["called"] is True
        # The client reference was actually swapped.
        assert engine.llm_client is not old_client

    def test_update_api_key_swaps_client_and_reinjects(self, engine):
        """After update, a new client is installed and re-injected into agents."""
        agent = MockAgent("a")
        engine.register_agent(agent)
        old_client = engine.llm_client

        engine.update_api_key("another_key")

        assert engine.llm_client is not old_client
        assert agent.llm is engine.llm_client

    def test_update_api_key_handles_no_close_gracefully(self, engine):
        """A client whose underlying session lacks close() must not raise."""
        engine.llm_client.client = object()  # no close attribute
        # Should not raise.
        engine.update_api_key("k")

    def test_close_llm_client_swallows_close_errors(self, engine):
        """Best-effort close: an exception from close() is swallowed, not propagated."""
        class Boom:
            def close(self):
                raise RuntimeError("close failed")

        class Wrapper:
            client = Boom()

        # Must not raise.
        AgentEngine._close_llm_client(Wrapper())

    def test_update_api_key_documents_concurrency_precondition(self):
        """The E-4 docstring must state the no-concurrent-process_turn precondition."""
        doc = AgentEngine.update_api_key.__doc__ or ""
        assert "process_turn" in doc
        assert "concurrency" in doc.lower() or "concurrent" in doc.lower()


class TestE5MergeLookup:
    """E-5: merge priority lookup is O(1) and warns on unresolvable agent_id."""

    @pytest.mark.asyncio
    async def test_merge_ordering_unchanged_with_o1_lookup(self, engine, sample_context):
        """Existing higher-priority-wins ordering must hold via the O(1) lookup."""
        def low(context, agent):
            return AgentResponse(variable_updates={"k": "low"})

        def high(context, agent):
            return AgentResponse(variable_updates={"k": "high"})

        engine.register_agent(MockAgent("low", priority=1, response_fn=low))
        engine.register_agent(MockAgent("high", priority=10, response_fn=high))

        response = await engine.process_turn(sample_context)
        assert response.variable_updates["k"] == "high"
        assert sample_context.blackboard.get_var("k") == "high"

    def test_agent_meta_populated_at_register_time(self, engine):
        """_agent_meta caches (priority, registration-order) for O(1) merge lookup."""
        a = MockAgent("a", priority=3)
        b = MockAgent("b", priority=7)
        engine.register_agent(a)
        engine.register_agent(b)

        assert engine._agent_meta[a.config.id] == (3, 0)
        assert engine._agent_meta[b.config.id] == (7, 1)

    def test_unresolvable_agent_id_logs_warning(self, engine, sample_context):
        """A response whose source_agent_id is not registered logs a warning and
        defaults to priority/order 0 (latent ordering bug observability)."""
        blackboard = sample_context.blackboard
        final = AgentResponse()
        orphan = AgentResponse(
            source_agent_id="ghost_agent",
            variable_updates={"orphan_var": "value"},
        )

        with patch("xubb_agents.core.engine.logger") as mock_log:
            engine._merge_responses([orphan], blackboard, final)

        assert any(
            "ghost_agent" in str(c) for c in mock_log.warning.call_args_list
        ), "Expected a warning naming the unresolvable agent_id"
        # The update is still applied (graceful degradation).
        assert blackboard.get_var("orphan_var") == "value"


class TestE1Phase2ExceptionSafety:
    """E-1 / INV-12: a Phase-2 exception must never leave the host-owned context
    corrupted in an EVENT/phase=2 state, and on_chain_error (B5) must still fire."""

    @pytest.mark.asyncio
    async def test_phase2_exception_restores_context_and_fires_on_chain_error(
        self, engine, sample_context
    ):
        """If _run_phase raises during Phase 2, context.trigger_type and
        context.phase are restored to their pre-turn values and the error
        still propagates / on_chain_error still fires."""
        from xubb_agents.core.callbacks import AgentCallbackHandler

        # Phase 1 agent emits an event so Phase 2 is entered.
        def emit_event(context, agent):
            return AgentResponse(
                events=[Event(
                    name="question_detected",
                    payload={},
                    source_agent=agent.config.id,
                    timestamp=time.time()
                )]
            )

        emitter = MockAgent("emitter", response_fn=emit_event)
        subscriber = MockAgent(
            "subscriber",
            subscribed_events=["question_detected"],
            trigger_types=[TriggerType.EVENT],
        )
        subscriber.config.cooldown = 0

        engine.register_agent(emitter)
        engine.register_agent(subscriber)

        class ErrorTracker(AgentCallbackHandler):
            def __init__(self):
                self.errors = []
            async def on_chain_error(self, error):
                self.errors.append(error)

        tracker = ErrorTracker()
        engine.callbacks = [tracker]

        # Capture the pre-turn host-owned context values. process_turn mutates
        # trigger_type to TURN_BASED for Phase 1; the contract is that whatever
        # the host set before Phase 2 (and the originating trigger_type) is
        # restored. We assert restoration to the values seen entering process_turn.
        pre_trigger_type = sample_context.trigger_type
        pre_phase = sample_context.phase

        # Wrap _run_phase so Phase 1 runs normally (emitting the event) but
        # Phase 2 raises while context is mutated to EVENT/phase=2.
        real_run_phase = engine._run_phase

        async def run_phase_fail_in_phase2(agents, context):
            if context.phase == 2:
                # Mid-phase failure with the context in its mutated state.
                assert context.trigger_type == TriggerType.EVENT
                assert context.phase == 2
                raise RuntimeError("phase2 boom")
            return await real_run_phase(agents, context)

        with patch.object(engine, '_run_phase', side_effect=run_phase_fail_in_phase2):
            with pytest.raises(RuntimeError, match="phase2 boom"):
                await engine.process_turn(sample_context)

        # (1) The host-owned context is restored despite the Phase-2 exception
        #     (INV-12) — not left corrupted as EVENT/phase=2.
        assert sample_context.trigger_type == pre_trigger_type
        assert sample_context.phase == pre_phase
        assert sample_context.trigger_type != TriggerType.EVENT

        # (2) on_chain_error still fired and the error propagated (B5 contract).
        assert len(tracker.errors) == 1
        assert str(tracker.errors[0]) == "phase2 boom"


class TestReplaceAgents:
    """replace_agents atomically swaps the full registry (P0-3 vault-reload race).

    A vault reload previously did agents.clear() + register loop, which a hot turn
    iterating self.agents could observe half-cleared. replace_agents rebuilds and
    rebinds the three structures so readers only ever see a complete set.
    """

    def test_replace_agents_swaps_registry_and_clears_stale_meta(self, engine):
        a = MockAgent("alpha", priority=5)
        b = MockAgent("beta", priority=3)
        engine.register_agent(a)
        engine.register_agent(b)

        c = MockAgent("gamma", priority=7)
        engine.replace_agents([c])

        assert engine.agents == [c]
        assert engine._agent_meta[c.config.id] == (7, 0)   # (priority, index)
        assert engine._agent_index[c.config.id] == 0
        assert c.llm is engine.llm_client                  # llm injected
        # No stale entries leak from the replaced agents (fresh dicts).
        assert a.config.id not in engine._agent_meta
        assert b.config.id not in engine._agent_index

    def test_replace_agents_never_observed_half_cleared(self):
        """Concurrent readers must only ever see a COMPLETE agent set (old or new),
        never a partial/zero list mid-swap (the agents.clear() race). Verified with a
        tiny GIL switch-interval so threads interleave mid-iteration."""
        import sys
        import threading

        engine = AgentEngine(api_key="test_key")
        for i in range(20):
            engine.register_agent(MockAgent(f"a{i}"))

        errors = []
        stop = threading.Event()

        def reader():
            while not stop.is_set():
                try:
                    n = sum(1 for _ in engine.agents)
                    if n not in (20, 30):            # complete old set or complete new set
                        errors.append(f"partial read: {n}")
                except Exception as exc:             # noqa: BLE001
                    errors.append(repr(exc))

        old = sys.getswitchinterval()
        sys.setswitchinterval(1e-7)
        try:
            readers = [threading.Thread(target=reader) for _ in range(6)]
            for t in readers:
                t.start()
            for _ in range(200):
                engine.replace_agents([MockAgent(f"b{j}") for j in range(30)])
            stop.set()
            for t in readers:
                t.join()
        finally:
            sys.setswitchinterval(old)

        assert not errors, errors[:5]


class TestCallbackInvariants:
    """INV-1 / INV-5 / INV-7 — lifecycle callbacks fire at most once, a no-op callback
    subclass never crashes a turn, and a tracing/callback failure never blocks insight
    delivery (the engine wraps every callback call in try/except)."""

    @pytest.mark.asyncio
    async def test_noop_callback_subclass_survives_a_turn(self, engine, sample_context):
        """INV-7: the callback base defines every method the engine calls — a subclass
        that overrides nothing never crashes a turn."""
        from xubb_agents.core.callbacks import AgentCallbackHandler

        class NoOp(AgentCallbackHandler):
            pass

        engine.callbacks = [NoOp()]
        engine.register_agent(MockAgent("a"))

        response = await engine.process_turn(sample_context)  # must not raise
        assert response is not None

    @pytest.mark.asyncio
    async def test_lifecycle_callbacks_fire_once(self, engine, sample_context):
        """INV-1: each lifecycle callback fires at most once per execution attempt."""
        from collections import Counter
        from xubb_agents.core.callbacks import AgentCallbackHandler

        counts = Counter()

        class Counting(AgentCallbackHandler):
            async def on_turn_start(self, context):
                counts["turn_start"] += 1

            async def on_turn_end(self, response, duration):
                counts["turn_end"] += 1

            async def on_agent_start(self, agent_name, context):
                counts["agent_start"] += 1

            async def on_agent_finish(self, agent_name, response, duration):
                counts["agent_finish"] += 1

        engine.callbacks = [Counting()]
        engine.register_agent(MockAgent("solo"))

        await engine.process_turn(sample_context)

        assert counts["turn_start"] == 1
        assert counts["turn_end"] == 1
        assert counts["agent_start"] == 1  # exactly one agent ran ...
        assert counts["agent_finish"] == 1  # ... and no callback double-fired

    @pytest.mark.asyncio
    async def test_tracing_failure_does_not_block_insight_delivery(self, engine, sample_context):
        """INV-5: a serialization/tracing failure must never prevent insight delivery."""
        from xubb_agents.core.callbacks import AgentCallbackHandler

        class BrokenTracer(AgentCallbackHandler):
            async def on_agent_finish(self, agent_name, response, duration):
                raise RuntimeError("trace serialization blew up")

            async def on_turn_end(self, response, duration):
                raise RuntimeError("trace finalize blew up")

        def speak(context, agent):
            return AgentResponse(insights=[AgentInsight(
                agent_id="a", agent_name="a", type=InsightType.SUGGESTION, content="hello",
            )])

        engine.callbacks = [BrokenTracer()]
        engine.register_agent(MockAgent("a", response_fn=speak))

        response = await engine.process_turn(sample_context)  # must not raise

        # The insight is delivered despite the tracer exploding mid-turn.
        assert any(i.content == "hello" for i in response.insights)
