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

    def test_dedupe_none_key_by_type(self):
        """FACT-DEDUP-KEY: when key is None, dedupe by type alone (type singleton)."""
        bb = Blackboard()
        bb.add_fact(Fact(
            type="summary", key=None, value="first",
            confidence=0.9, source_agent="a", timestamp=1.0
        ))
        bb.add_fact(Fact(
            type="summary", key=None, value="second",
            confidence=0.9, source_agent="a", timestamp=2.0
        ))

        # Same type + None key collapses to ONE singleton (deduped by type alone)...
        summaries = [f for f in bb.facts if f.type == "summary"]
        assert len(summaries) == 1
        # ...and equal priority+confidence means the later registration wins.
        assert summaries[0].value == "second"

        # A keyed fact of the SAME type is a distinct entry (not deduped against the
        # None-key singleton).
        bb.add_fact(Fact(
            type="summary", key="q3", value="keyed",
            confidence=0.9, source_agent="a", timestamp=3.0
        ))
        assert len([f for f in bb.facts if f.type == "summary"]) == 2

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

    # ---- F-1 / INV-9: conflict resolution honors (priority, confidence, order) ----

    def test_higher_priority_wins_over_higher_confidence(self):
        """INV-9 rule 1: higher priority wins even at LOWER confidence."""
        bb = Blackboard()
        bb.add_fact(Fact(
            type="budget", key="primary", value="low_prio",
            confidence=0.9, priority=1, source_agent="a", timestamp=1.0,
        ))
        bb.add_fact(Fact(
            type="budget", key="primary", value="high_prio",
            confidence=0.5, priority=10, source_agent="b", timestamp=2.0,
        ))
        assert bb.get_fact("budget", "primary").value == "high_prio"

    def test_lower_priority_does_not_override(self):
        """A lower-priority fact must NOT replace a higher-priority incumbent."""
        bb = Blackboard()
        bb.add_fact(Fact(
            type="budget", key="primary", value="high_prio",
            confidence=0.5, priority=10, source_agent="a", timestamp=1.0,
        ))
        bb.add_fact(Fact(
            type="budget", key="primary", value="low_prio",
            confidence=0.99, priority=1, source_agent="b", timestamp=2.0,
        ))
        assert bb.get_fact("budget", "primary").value == "high_prio"

    def test_equal_priority_higher_confidence_wins(self):
        """INV-9 rule 2: within equal priority, higher confidence wins."""
        bb = Blackboard()
        bb.add_fact(Fact(
            type="budget", key="primary", value="lower_conf",
            confidence=0.6, priority=5, source_agent="a", timestamp=1.0,
        ))
        bb.add_fact(Fact(
            type="budget", key="primary", value="higher_conf",
            confidence=0.8, priority=5, source_agent="b", timestamp=2.0,
        ))
        assert bb.get_fact("budget", "primary").value == "higher_conf"
        # And a subsequent equal-priority LOWER-confidence write must not replace it.
        bb.add_fact(Fact(
            type="budget", key="primary", value="even_lower",
            confidence=0.4, priority=5, source_agent="c", timestamp=3.0,
        ))
        assert bb.get_fact("budget", "primary").value == "higher_conf"

    def test_equal_priority_equal_confidence_later_registration_wins(self):
        """INV-9 rule 3: full tie → later registration (later add_fact call) wins."""
        bb = Blackboard()
        bb.add_fact(Fact(
            type="budget", key="primary", value="first",
            confidence=0.7, priority=5, source_agent="a", timestamp=1.0,
        ))
        bb.add_fact(Fact(
            type="budget", key="primary", value="second",
            confidence=0.7, priority=5, source_agent="b", timestamp=2.0,
        ))
        assert bb.get_fact("budget", "primary").value == "second"

    def test_priority_resolution_applies_to_keyless_singleton(self):
        """key=None singleton resolution obeys the same (priority, confidence) rule."""
        bb = Blackboard()
        bb.add_fact(Fact(
            type="phase", key=None, value="low_prio",
            confidence=0.95, priority=1, source_agent="a", timestamp=1.0,
        ))
        bb.add_fact(Fact(
            type="phase", key=None, value="high_prio",
            confidence=0.5, priority=10, source_agent="b", timestamp=2.0,
        ))
        assert len(bb.get_facts_by_type("phase")) == 1
        assert bb.get_fact("phase").value == "high_prio"


class TestBlackboardMemory:
    """Test memory operations."""
    
    def test_get_and_set_memory(self):
        bb = Blackboard()
        bb.set_memory("agent1", {"key": "value"})

        mem = bb.get_memory("agent1")
        assert mem["key"] == "value"

    def test_get_memory_returns_copy(self):
        """INV-8: get_memory returns a COPY — mutating it must not change the stored
        value (memory is copy-on-read, not a live reference)."""
        bb = Blackboard()
        bb.set_memory("agent1", {"key": "value"})

        mem = bb.get_memory("agent1")
        mem["key"] = "mutated"
        mem["added"] = "x"

        # The stored memory is untouched by mutating the returned object.
        assert bb.get_memory("agent1") == {"key": "value"}

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

    # ---- M-1 / INV-8': memory values are copies on WRITE as well as read ----

    def test_update_memory_does_not_retain_caller_reference(self):
        """INV-8': mutating a nested object after update_memory must not
        change blackboard state."""
        bb = Blackboard()
        nested = {"items": [1, 2, 3]}
        bb.update_memory("agent1", {"nested": nested})

        # Caller mutates its own object AFTER the write.
        nested["items"].append(4)
        nested["new_key"] = "leaked"

        stored = bb.get_memory("agent1")
        assert stored["nested"]["items"] == [1, 2, 3]
        assert "new_key" not in stored["nested"]

    def test_set_memory_does_not_retain_caller_reference(self):
        """INV-8': mutating a nested object after set_memory must not
        change blackboard state."""
        bb = Blackboard()
        data = {"nested": {"items": [1, 2, 3]}}
        bb.set_memory("agent1", data)

        # Caller mutates its own object AFTER the write.
        data["nested"]["items"].append(4)
        data["top_level"] = "leaked"

        stored = bb.get_memory("agent1")
        assert stored["nested"]["items"] == [1, 2, 3]
        assert "top_level" not in stored


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
