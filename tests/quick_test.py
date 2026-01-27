#!/usr/bin/env python
"""Quick functional test to verify v2 implementation works."""

import sys
import os
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from xubb_agents import Blackboard, ConditionEvaluator, Event, Fact

def main():
    print("Testing Xubb Agents Framework v2.0 implementation...")
    print()
    
    # Test Blackboard
    print("=== Blackboard Tests ===")
    bb = Blackboard()
    
    # Variables
    bb.set_var("phase", "negotiation")
    bb.set_var("sentiment", 0.7)
    assert bb.get_var("phase") == "negotiation"
    assert bb.get_var("sentiment") == 0.7
    print("[OK] Variables work")
    
    # Queues
    bb.push_queue("questions", {"text": "What is pricing?"})
    bb.push_queue("questions", {"text": "When can you start?"})
    assert bb.queue_length("questions") == 2
    assert bb.peek_queue("questions")["text"] == "What is pricing?"
    print("[OK] Queues work")
    
    # Facts
    bb.add_fact(Fact(
        type="budget", 
        key="primary",
        value=50000, 
        confidence=0.9, 
        source_agent="test", 
        timestamp=time.time()
    ))
    fact = bb.get_fact("budget", "primary")
    assert fact.value == 50000
    print("[OK] Facts work")
    
    # Events
    bb.emit_event(Event(
        name="question_detected", 
        payload={"question": "What is pricing?"}, 
        source_agent="extractor", 
        timestamp=time.time()
    ))
    assert bb.has_event("question_detected")
    assert bb.count_events("question_detected") == 1
    print("[OK] Events work")
    
    # Memory
    bb.update_memory("agent1", {"counter": 5})
    assert bb.get_memory("agent1")["counter"] == 5
    print("[OK] Memory works")
    
    # Snapshot
    snap = bb.snapshot()
    bb.set_var("phase", "closing")
    assert snap.get_var("phase") == "negotiation"  # Snapshot unchanged
    print("[OK] Snapshot isolation works")
    
    print()
    
    # Test ConditionEvaluator
    print("=== ConditionEvaluator Tests ===")
    evaluator = ConditionEvaluator()
    
    # Reset phase
    bb.set_var("phase", "negotiation")
    
    # Test eq
    conditions = {"mode": "all", "rules": [{"var": "phase", "op": "eq", "value": "negotiation"}]}
    assert evaluator.evaluate(conditions, bb, {"turn_count": 5}, "test") is True
    print("[OK] eq operator works")
    
    # Test gt
    conditions = {"mode": "all", "rules": [{"var": "sentiment", "op": "gt", "value": 0.5}]}
    assert evaluator.evaluate(conditions, bb, {"turn_count": 5}, "test") is True
    print("[OK] gt operator works")
    
    # Test in
    conditions = {"mode": "all", "rules": [{"var": "phase", "op": "in", "value": ["discovery", "negotiation"]}]}
    assert evaluator.evaluate(conditions, bb, {"turn_count": 5}, "test") is True
    print("[OK] in operator works")
    
    # Test exists
    conditions = {"mode": "all", "rules": [{"var": "phase", "op": "exists"}]}
    assert evaluator.evaluate(conditions, bb, {"turn_count": 5}, "test") is True
    print("[OK] exists operator works")
    
    # Test present (key exists even if falsy value)
    bb.set_var("zero", 0)
    conditions = {"mode": "all", "rules": [{"var": "zero", "op": "present"}]}
    assert evaluator.evaluate(conditions, bb, {"turn_count": 5}, "test") is True
    print("[OK] present operator works")
    
    # Test queue not_empty
    conditions = {"mode": "all", "rules": [{"queue": "questions", "op": "not_empty"}]}
    assert evaluator.evaluate(conditions, bb, {"turn_count": 5}, "test") is True
    print("[OK] not_empty operator works")
    
    # Test mod
    conditions = {"mode": "all", "rules": [{"meta": "turn_count", "op": "mod", "value": 5, "result": 0}]}
    assert evaluator.evaluate(conditions, bb, {"turn_count": 10}, "test") is True
    print("[OK] mod operator works")
    
    # Test fact source
    conditions = {"mode": "all", "rules": [{"fact": "budget", "op": "eq", "value": 50000}]}
    assert evaluator.evaluate(conditions, bb, {"turn_count": 5}, "test") is True
    print("[OK] fact source works")
    
    # Test memory source
    conditions = {"mode": "all", "rules": [{"memory": "counter", "op": "eq", "value": 5}]}
    assert evaluator.evaluate(conditions, bb, {"turn_count": 5}, "agent1") is True
    print("[OK] memory source works")
    
    # Test safety (never raises)
    conditions = {"mode": "all", "rules": [{"var": "phase", "op": "gt", "value": 5}]}  # Type mismatch
    assert evaluator.evaluate(conditions, bb, {"turn_count": 5}, "test") is False
    print("[OK] Type safety works (returns False, no exception)")
    
    print()
    print("=" * 50)
    print("All tests passed! [OK]")
    print("=" * 50)

if __name__ == "__main__":
    main()
