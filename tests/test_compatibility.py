"""
Tests for v1 → v2 compatibility.
"""

import pytest
from xubb_agents.core.models import (
    AgentContext, AgentResponse, TriggerType, TranscriptSegment
)
from xubb_agents.core.blackboard import Blackboard
from xubb_agents.core.agent import AgentConfig


class TestAgentContextCompatibility:
    """Test AgentContext v1 → v2 compatibility."""
    
    def test_v1_fields_still_exist(self):
        """v1 fields should still be available."""
        context = AgentContext(
            session_id="test",
            recent_segments=[],
            shared_state={"key": "value"},
            rag_docs=["doc1"],
            trigger_type=TriggerType.TURN_BASED,
            trigger_metadata={"foo": "bar"},
            language_directive="en",
            user_context="Sales rep"
        )
        
        assert context.session_id == "test"
        assert context.shared_state == {"key": "value"}
        assert context.rag_docs == ["doc1"]
        assert context.trigger_type == TriggerType.TURN_BASED
        assert context.language_directive == "en"
        assert context.user_context == "Sales rep"
    
    def test_v2_fields_have_defaults(self):
        """v2 fields should have sensible defaults."""
        context = AgentContext(
            session_id="test",
            recent_segments=[]
        )
        
        assert context.blackboard is None
        assert context.turn_count == 0
        assert context.phase == 1
    
    def test_v2_fields_can_be_set(self):
        """v2 fields should be settable."""
        bb = Blackboard()
        context = AgentContext(
            session_id="test",
            recent_segments=[],
            blackboard=bb,
            turn_count=5,
            phase=2
        )
        
        assert context.blackboard is bb
        assert context.turn_count == 5
        assert context.phase == 2


class TestAgentResponseCompatibility:
    """Test AgentResponse v1 → v2 compatibility."""
    
    def test_v1_fields_still_exist(self):
        """v1 fields should still be available."""
        response = AgentResponse(
            insights=[],
            state_updates={"key": "value"},
            data={"ui_actions": []},
            debug_info={"prompt": "test"}
        )
        
        assert response.state_updates == {"key": "value"}
        assert response.data == {"ui_actions": []}
        assert response.debug_info == {"prompt": "test"}
    
    def test_v2_fields_have_defaults(self):
        """v2 fields should have sensible defaults."""
        response = AgentResponse()
        
        assert response.events == []
        assert response.variable_updates == {}
        assert response.queue_pushes == {}
        assert response.facts == []
        assert response.memory_updates == {}
    
    def test_v1_response_can_be_created_without_v2_fields(self):
        """Should be able to create a v1-style response."""
        response = AgentResponse(
            insights=[],
            state_updates={"key": "value"}
        )
        
        assert response.state_updates == {"key": "value"}
        # v2 fields should still exist with defaults
        assert response.events == []


class TestAgentConfigCompatibility:
    """Test AgentConfig v1 → v2 compatibility."""
    
    def test_v1_config_creation(self):
        """v1 config creation should still work."""
        config = AgentConfig(
            name="Test Agent",
            cooldown=10,
            model="gpt-4o-mini",
            trigger_types=[TriggerType.TURN_BASED],
            trigger_keywords=["price"],
            priority=5
        )
        
        assert config.name == "Test Agent"
        assert config.cooldown == 10
        assert config.trigger_keywords == ["price"]
        assert config.priority == 5
    
    def test_v2_config_fields(self):
        """v2 config fields should be available."""
        config = AgentConfig(
            name="Test Agent",
            trigger_conditions={"mode": "all", "rules": []},
            subscribed_events=["question_detected"]
        )
        
        assert config.trigger_conditions == {"mode": "all", "rules": []}
        assert config.subscribed_events == ["question_detected"]
    
    def test_v2_fields_have_defaults(self):
        """v2 fields should have defaults."""
        config = AgentConfig(name="Test Agent")
        
        assert config.trigger_conditions is None
        assert config.subscribed_events == []


class TestTriggerTypeCompatibility:
    """Test TriggerType enum compatibility."""
    
    def test_v1_trigger_types_exist(self):
        """v1 trigger types should exist."""
        assert TriggerType.TURN_BASED.value == "turn_based"
        assert TriggerType.KEYWORD.value == "keyword"
        assert TriggerType.SILENCE.value == "silence"
        assert TriggerType.INTERVAL.value == "interval"
    
    def test_v2_event_trigger_type(self):
        """v2 EVENT trigger type should exist."""
        assert TriggerType.EVENT.value == "event"


class TestBlackboardAndSharedStateInterop:
    """Test Blackboard ↔ shared_state interoperability."""
    
    def test_blackboard_can_be_none(self):
        """Context with no blackboard should work (v1 style)."""
        context = AgentContext(
            session_id="test",
            recent_segments=[],
            shared_state={"key": "value"}
        )
        
        assert context.blackboard is None
        assert context.shared_state == {"key": "value"}
    
    def test_both_can_coexist(self):
        """Blackboard and shared_state can both be set."""
        bb = Blackboard()
        bb.set_var("bb_key", "bb_value")
        
        context = AgentContext(
            session_id="test",
            recent_segments=[],
            shared_state={"ss_key": "ss_value"},
            blackboard=bb
        )
        
        assert context.shared_state == {"ss_key": "ss_value"}
        assert context.blackboard.get_var("bb_key") == "bb_value"
