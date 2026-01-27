"""
Unit tests for Blackboard operations.
"""

import pytest
import time
from xubb_agents.core.blackboard import Blackboard
from xubb_agents.core.models import Event, Fact


class TestBlackboardVariables:
    """Test variable operations."""
    
    def test_set_and_get_var(self):
        bb = Blackboard()
        bb.set_var("key", "value")
        assert bb.get_var("key") == "value"
    
    def test_get_var_default(self):
        bb = Blackboard()
        assert bb.get_var("missing", "default") == "default"
        assert bb.get_var("missing") is None
    
    def test_delete_var(self):
        bb = Blackboard()
        bb.set_var("key", "value")
        bb.delete_var("key")
        assert bb.get_var("key") is None
    
    def test_has_var(self):
        bb = Blackboard()
        bb.set_var("key", "value")
        assert bb.has_var("key") is True
        assert bb.has_var("missing") is False


class TestBlackboardEvents:
    """Test event operations."""
    
    def test_emit_event(self):
        bb = Blackboard()
        event = Event(
            name="test_event",
            payload={"data": "value"},
            source_agent="test_agent",
            timestamp=time.time()
        )
        bb.emit_event(event)
        assert len(bb.events) == 1
        assert bb.events[0].name == "test_event"
    
    def test_no_deduplication_by_default(self):
        """Events are NOT deduplicated by default."""
        bb = Blackboard()
        for i in range(3):
            event = Event(
                name="same_event",
                payload={"index": i},
                source_agent="test_agent",
                timestamp=time.time()
            )
            bb.emit_event(event)
        
        # All 3 events should be kept
        assert len(bb.events) == 3
        assert bb.count_events("same_event") == 3
    
    def test_has_event(self):
        bb = Blackboard()
        bb.emit_event(Event(
            name="test_event",
            payload={},
            source_agent="test",
            timestamp=time.time()
        ))
        assert bb.has_event("test_event") is True
        assert bb.has_event("other_event") is False
    
    def test_get_events_by_name(self):
        bb = Blackboard()
        bb.emit_event(Event(name="a", payload={}, source_agent="test", timestamp=1.0))
        bb.emit_event(Event(name="b", payload={}, source_agent="test", timestamp=2.0))
        bb.emit_event(Event(name="a", payload={}, source_agent="test", timestamp=3.0))
        
        a_events = bb.get_events_by_name("a")
        assert len(a_events) == 2
    
    def test_clear_events(self):
        bb = Blackboard()
        bb.emit_event(Event(name="test", payload={}, source_agent="test", timestamp=1.0))
        bb.clear_events()
        assert len(bb.events) == 0


class TestBlackboardQueues:
    """Test queue operations."""
    
    def test_push_and_pop(self):
        bb = Blackboard()
        bb.push_queue("work", "item1")
        bb.push_queue("work", "item2")
        
        assert bb.pop_queue("work") == "item1"
        assert bb.pop_queue("work") == "item2"
        assert bb.pop_queue("work") is None
    
    def test_push_queue_items(self):
        bb = Blackboard()
        bb.push_queue_items("work", ["a", "b", "c"])
        assert bb.queue_length("work") == 3
    
    def test_peek_queue(self):
        bb = Blackboard()
        bb.push_queue("work", "item1")
        
        # Peek doesn't remove
        assert bb.peek_queue("work") == "item1"
        assert bb.peek_queue("work") == "item1"
        assert bb.queue_length("work") == 1
    
    def test_clear_queue(self):
        bb = Blackboard()
        bb.push_queue("work", "item1")
        bb.clear_queue("work")
        assert bb.queue_length("work") == 0


class TestBlackboardFacts:
    """Test fact operations."""
    
    def test_add_fact(self):
        bb = Blackboard()
        fact = Fact(
            type="budget",
            value=50000,
            confidence=0.9,
            source_agent="test",
            timestamp=time.time()
        )
        bb.add_fact(fact)
        assert len(bb.facts) == 1
    
    def test_dedupe_by_type_when_key_none(self):
        """When key is None, dedupe by type only."""
        bb = Blackboard()
        
        # Add first fact
        bb.add_fact(Fact(
            type="budget", key=None, value=50000,
            confidence=0.8, source_agent="a", timestamp=1.0
        ))
        
        # Add second fact with same type but higher confidence
        bb.add_fact(Fact(
            type="budget", key=None, value=75000,
            confidence=0.9, source_agent="b", timestamp=2.0
        ))
        
        # Should replace (higher confidence)
        assert len(bb.facts) == 1
        assert bb.facts[0].value == 75000
    
    def test_dedupe_by_type_key_pair(self):
        """When key is set, dedupe by (type, key) pair."""
        bb = Blackboard()
        
        # Add facts with different keys - both should exist
        bb.add_fact(Fact(
            type="stakeholder", key="cfo", value="Sarah",
            confidence=0.9, source_agent="a", timestamp=1.0
        ))
        bb.add_fact(Fact(
            type="stakeholder", key="cto", value="Mike",
            confidence=0.9, source_agent="a", timestamp=2.0
        ))
        
        assert len(bb.facts) == 2
        
        # Update CFO - should replace
        bb.add_fact(Fact(
            type="stakeholder", key="cfo", value="Sarah Chen",
            confidence=0.95, source_agent="a", timestamp=3.0
        ))
        
        assert len(bb.facts) == 2
        cfo_fact = bb.get_fact("stakeholder", "cfo")
        assert cfo_fact.value == "Sarah Chen"
    
    def test_get_fact(self):
        bb = Blackboard()
        bb.add_fact(Fact(
            type="budget", key="primary", value=50000,
            confidence=0.9, source_agent="a", timestamp=1.0
        ))
        
        # Get by type only
        fact = bb.get_fact("budget")
        assert fact is not None
        assert fact.value == 50000
        
        # Get by type and key
        fact = bb.get_fact("budget", "primary")
        assert fact is not None
        
        # Get missing
        assert bb.get_fact("missing") is None


class TestBlackboardMemory:
    """Test memory operations."""
    
    def test_get_and_set_memory(self):
        bb = Blackboard()
        bb.set_memory("agent1", {"key": "value"})
        
        mem = bb.get_memory("agent1")
        assert mem["key"] == "value"
    
    def test_update_memory(self):
        bb = Blackboard()
        bb.set_memory("agent1", {"a": 1})
        bb.update_memory("agent1", {"b": 2})
        
        mem = bb.get_memory("agent1")
        assert mem["a"] == 1
        assert mem["b"] == 2
    
    def test_get_memory_empty(self):
        bb = Blackboard()
        mem = bb.get_memory("nonexistent")
        assert mem == {}


class TestBlackboardSnapshot:
    """Test snapshot isolation."""
    
    def test_snapshot_creates_deep_copy(self):
        bb = Blackboard()
        bb.set_var("key", "original")
        bb.push_queue("work", "item1")
        
        # Create snapshot
        snap = bb.snapshot()
        
        # Modify original
        bb.set_var("key", "modified")
        bb.push_queue("work", "item2")
        
        # Snapshot should be unchanged
        assert snap.get_var("key") == "original"
        assert snap.queue_length("work") == 1


class TestBlackboardSerialization:
    """Test to_dict and from_dict."""
    
    def test_round_trip(self):
        bb = Blackboard()
        bb.set_var("key", "value")
        bb.push_queue("work", "item")
        bb.add_fact(Fact(
            type="budget", value=50000,
            confidence=0.9, source_agent="test", timestamp=1.0
        ))
        bb.emit_event(Event(
            name="test", payload={"data": 1},
            source_agent="test", timestamp=1.0
        ))
        
        # Serialize and deserialize
        data = bb.to_dict()
        bb2 = Blackboard.from_dict(data)
        
        assert bb2.get_var("key") == "value"
        assert bb2.queue_length("work") == 1
        assert len(bb2.facts) == 1
        assert len(bb2.events) == 1
