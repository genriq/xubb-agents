"""
Unit tests for ConditionEvaluator.
"""

import pytest
import time
from xubb_agents.core.conditions import ConditionEvaluator
from xubb_agents.core.blackboard import Blackboard
from xubb_agents.core.models import Fact


@pytest.fixture
def evaluator():
    return ConditionEvaluator()


@pytest.fixture
def blackboard():
    bb = Blackboard()
    bb.set_var("phase", "negotiation")
    bb.set_var("sentiment", 0.7)
    bb.set_var("turn_count", 10)
    bb.set_var("empty_string", "")
    bb.set_var("zero", 0)
    bb.set_var("topics", ["pricing", "timeline", "support"])
    bb.push_queue("pending_questions", {"text": "What is pricing?"})
    bb.add_fact(Fact(
        type="budget", key="primary", value=50000,
        confidence=0.9, source_agent="test", timestamp=time.time()
    ))
    bb.update_memory("test_agent", {"counter": 5})
    return bb


@pytest.fixture
def meta():
    return {"turn_count": 10, "trigger_type": "turn_based", "phase": 1}


class TestBasicOperators:
    """Test basic comparison operators."""
    
    def test_eq(self, evaluator, blackboard, meta):
        conditions = {
            "mode": "all",
            "rules": [{"var": "phase", "op": "eq", "value": "negotiation"}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True
        
        conditions["rules"][0]["value"] = "closing"
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is False
    
    def test_neq(self, evaluator, blackboard, meta):
        conditions = {
            "mode": "all",
            "rules": [{"var": "phase", "op": "neq", "value": "closing"}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True
    
    def test_gt(self, evaluator, blackboard, meta):
        conditions = {
            "mode": "all",
            "rules": [{"var": "sentiment", "op": "gt", "value": 0.5}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True
        
        conditions["rules"][0]["value"] = 0.8
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is False
    
    def test_gte(self, evaluator, blackboard, meta):
        conditions = {
            "mode": "all",
            "rules": [{"var": "sentiment", "op": "gte", "value": 0.7}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True
    
    def test_lt(self, evaluator, blackboard, meta):
        conditions = {
            "mode": "all",
            "rules": [{"var": "turn_count", "op": "lt", "value": 15}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True
    
    def test_lte(self, evaluator, blackboard, meta):
        conditions = {
            "mode": "all",
            "rules": [{"var": "turn_count", "op": "lte", "value": 10}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True


class TestListOperators:
    """Test list membership operators."""
    
    def test_in(self, evaluator, blackboard, meta):
        conditions = {
            "mode": "all",
            "rules": [{"var": "phase", "op": "in", "value": ["discovery", "negotiation", "closing"]}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True
        
        conditions["rules"][0]["value"] = ["closed", "lost"]
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is False
    
    def test_not_in(self, evaluator, blackboard, meta):
        conditions = {
            "mode": "all",
            "rules": [{"var": "phase", "op": "not_in", "value": ["closed", "lost"]}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True
    
    def test_contains_list(self, evaluator, blackboard, meta):
        """Contains on a list checks membership."""
        conditions = {
            "mode": "all",
            "rules": [{"var": "topics", "op": "contains", "value": "pricing"}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True
        
        conditions["rules"][0]["value"] = "missing"
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is False
    
    def test_contains_string(self, evaluator, blackboard, meta):
        """Contains on a string checks substring."""
        blackboard.set_var("message", "Hello world")
        conditions = {
            "mode": "all",
            "rules": [{"var": "message", "op": "contains", "value": "world"}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True


class TestExistenceOperators:
    """Test exists, present, not_exists operators."""
    
    def test_exists_truthy(self, evaluator, blackboard, meta):
        """Exists tests truthiness."""
        conditions = {
            "mode": "all",
            "rules": [{"var": "phase", "op": "exists"}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True
    
    def test_exists_falsy(self, evaluator, blackboard, meta):
        """Empty string is falsy, so exists fails."""
        conditions = {
            "mode": "all",
            "rules": [{"var": "empty_string", "op": "exists"}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is False
    
    def test_exists_zero(self, evaluator, blackboard, meta):
        """Zero is falsy, so exists fails."""
        conditions = {
            "mode": "all",
            "rules": [{"var": "zero", "op": "exists"}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is False
    
    def test_present_key_exists(self, evaluator, blackboard, meta):
        """Present tests key existence, not truthiness."""
        conditions = {
            "mode": "all",
            "rules": [{"var": "empty_string", "op": "present"}]
        }
        # Key exists even though value is empty string
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True
    
    def test_present_zero(self, evaluator, blackboard, meta):
        """Zero value but key exists."""
        conditions = {
            "mode": "all",
            "rules": [{"var": "zero", "op": "present"}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True
    
    def test_present_missing(self, evaluator, blackboard, meta):
        """Missing key returns False."""
        conditions = {
            "mode": "all",
            "rules": [{"var": "nonexistent", "op": "present"}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is False
    
    def test_not_exists(self, evaluator, blackboard, meta):
        conditions = {
            "mode": "all",
            "rules": [{"var": "missing_key", "op": "not_exists"}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True


class TestCollectionOperators:
    """Test not_empty, empty operators."""
    
    def test_not_empty_queue(self, evaluator, blackboard, meta):
        conditions = {
            "mode": "all",
            "rules": [{"queue": "pending_questions", "op": "not_empty"}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True
    
    def test_empty_queue(self, evaluator, blackboard, meta):
        blackboard.clear_queue("pending_questions")
        conditions = {
            "mode": "all",
            "rules": [{"queue": "pending_questions", "op": "empty"}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True


class TestModOperator:
    """Test modulo operator."""
    
    def test_mod_match(self, evaluator, blackboard, meta):
        conditions = {
            "mode": "all",
            "rules": [{"var": "turn_count", "op": "mod", "value": 5, "result": 0}]
        }
        # 10 % 5 == 0
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True
    
    def test_mod_no_match(self, evaluator, blackboard, meta):
        conditions = {
            "mode": "all",
            "rules": [{"var": "turn_count", "op": "mod", "value": 3, "result": 0}]
        }
        # 10 % 3 == 1, not 0
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is False
    
    def test_mod_with_meta(self, evaluator, blackboard, meta):
        """Test mod with meta.turn_count."""
        conditions = {
            "mode": "all",
            "rules": [{"meta": "turn_count", "op": "mod", "value": 5, "result": 0}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True


class TestSources:
    """Test different condition sources."""
    
    def test_var_source(self, evaluator, blackboard, meta):
        conditions = {
            "mode": "all",
            "rules": [{"var": "phase", "op": "eq", "value": "negotiation"}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True
    
    def test_fact_source(self, evaluator, blackboard, meta):
        conditions = {
            "mode": "all",
            "rules": [{"fact": "budget", "op": "eq", "value": 50000}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True
    
    def test_queue_source(self, evaluator, blackboard, meta):
        conditions = {
            "mode": "all",
            "rules": [{"queue": "pending_questions", "op": "not_empty"}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True
    
    def test_memory_own(self, evaluator, blackboard, meta):
        conditions = {
            "mode": "all",
            "rules": [{"memory": "counter", "op": "eq", "value": 5}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test_agent") is True
    
    def test_memory_other_agent(self, evaluator, blackboard, meta):
        """Access another agent's memory (advanced, discouraged)."""
        conditions = {
            "mode": "all",
            "rules": [{"memory": "test_agent.counter", "op": "eq", "value": 5}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "other_agent") is True
    
    def test_meta_source(self, evaluator, blackboard, meta):
        conditions = {
            "mode": "all",
            "rules": [{"meta": "turn_count", "op": "eq", "value": 10}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True


class TestModes:
    """Test all/any condition modes."""
    
    def test_mode_all(self, evaluator, blackboard, meta):
        conditions = {
            "mode": "all",
            "rules": [
                {"var": "phase", "op": "eq", "value": "negotiation"},
                {"var": "sentiment", "op": "gt", "value": 0.5}
            ]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True
        
        # One fails
        conditions["rules"][1]["value"] = 0.9
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is False
    
    def test_mode_any(self, evaluator, blackboard, meta):
        conditions = {
            "mode": "any",
            "rules": [
                {"var": "phase", "op": "eq", "value": "closing"},  # False
                {"var": "sentiment", "op": "gt", "value": 0.5}     # True
            ]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True


class TestSafety:
    """Test that condition evaluation never raises."""
    
    def test_type_mismatch_returns_false(self, evaluator, blackboard, meta):
        """Comparing string to number should return False, not raise."""
        conditions = {
            "mode": "all",
            "rules": [{"var": "phase", "op": "gt", "value": 5}]
        }
        # "negotiation" > 5 is a type error, should return False
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is False
    
    def test_missing_key_returns_false(self, evaluator, blackboard, meta):
        conditions = {
            "mode": "all",
            "rules": [{"var": "nonexistent", "op": "eq", "value": "something"}]
        }
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is False
    
    def test_none_conditions_passes(self, evaluator, blackboard, meta):
        """None conditions means always run."""
        assert evaluator.evaluate(None, blackboard, meta, "test") is True
    
    def test_empty_rules_passes(self, evaluator, blackboard, meta):
        """Empty rules means always run."""
        conditions = {"mode": "all", "rules": []}
        assert evaluator.evaluate(conditions, blackboard, meta, "test") is True
