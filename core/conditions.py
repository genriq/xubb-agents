"""
ConditionEvaluator - Evaluates trigger conditions against Blackboard state (v2).

Trigger conditions allow agents to define preconditions that must be
satisfied before they run. This prevents unnecessary LLM calls.

Supported operators:
- eq, neq: Equality comparisons
- gt, gte, lt, lte: Numeric comparisons
- in, not_in: List membership
- contains: List/string/dict contains value
- exists: Key is truthy (not None, not empty)
- present: Key exists regardless of value
- not_exists: Key is falsy or missing
- not_empty, empty: Collection size checks
- mod: Modulo operation

Condition evaluation NEVER raises exceptions. Type mismatches or
invalid operations return False.
"""

from typing import Dict, Any, Optional, Tuple, List
import logging

from .blackboard import Blackboard

logger = logging.getLogger(__name__)


class ConditionEvaluator:
    """Evaluates trigger conditions against Blackboard state."""
    
    def evaluate(self, conditions: Optional[Dict], blackboard: Blackboard,
                 meta: Dict, agent_id: str) -> bool:
        """Evaluate all conditions. Returns True if agent should run.
        
        Args:
            conditions: The trigger_conditions config (None = always run)
            blackboard: Current Blackboard state
            meta: Execution metadata (turn_count, trigger_type, etc.)
            agent_id: The agent being evaluated (for memory access)
        
        Returns:
            True if all/any conditions pass (based on mode)
        """
        if not conditions:
            return True
        
        mode = conditions.get("mode", "all")
        rules = conditions.get("rules", [])
        
        if not rules:
            return True
        
        results = [self._evaluate_rule(r, blackboard, meta, agent_id) for r in rules]
        
        if mode == "all":
            return all(results)
        elif mode == "any":
            return any(results)
        
        return True
    
    def _evaluate_rule(self, rule: Dict, blackboard: Blackboard,
                       meta: Dict, agent_id: str) -> bool:
        """Evaluate a single condition rule."""
        try:
            # Get actual value AND key existence (for 'present' operator)
            actual, key_exists = self._get_value(rule, blackboard, meta, agent_id)
            
            # Get operator and expected value
            op = rule.get("op", "eq")
            expected = rule.get("value")
            
            # Evaluate
            return self._compare(actual, op, expected, rule, key_exists)
        except Exception as e:
            # Condition evaluation NEVER raises - return False on any error
            logger.debug(f"Condition evaluation error: {e}")
            return False
    
    def _get_value(self, rule: Dict, blackboard: Blackboard,
                   meta: Dict, agent_id: str) -> Tuple[Any, bool]:
        """Extract the value and key existence from the appropriate source.
        
        Returns:
            Tuple of (value, key_exists) where key_exists is True if the 
            key is present in the source container (regardless of value).
        """
        if "var" in rule:
            key = rule["var"]
            key_exists = key in blackboard.variables
            return (blackboard.get_var(key), key_exists)
        
        elif "fact" in rule:
            fact_type = rule["fact"]
            # Check if fact_key is also specified for keyed facts
            fact_key = rule.get("fact_key")
            fact = blackboard.get_fact(fact_type, fact_key)
            key_exists = fact is not None
            return (fact.value if fact else None, key_exists)
        
        elif "queue" in rule:
            queue_name = rule["queue"]
            key_exists = queue_name in blackboard.queues
            return (blackboard.queues.get(queue_name, []), key_exists)
        
        elif "memory" in rule:
            key = rule["memory"]
            if "." in key:
                # Cross-agent memory access: "other_agent.key"
                other_agent, mem_key = key.split(".", 1)
                agent_mem = blackboard.get_memory(other_agent)
                key_exists = mem_key in agent_mem
                return (agent_mem.get(mem_key), key_exists)
            else:
                # Own memory access
                agent_mem = blackboard.get_memory(agent_id)
                key_exists = key in agent_mem
                return (agent_mem.get(key), key_exists)
        
        elif "meta" in rule:
            meta_key = rule["meta"]
            key_exists = meta_key in meta
            return (meta.get(meta_key), key_exists)
        
        return (None, False)
    
    def _compare(self, actual: Any, op: str, expected: Any,
                 rule: Dict, key_exists: bool) -> bool:
        """Compare actual value against expected using operator.
        
        SAFETY: This method never raises exceptions. Type mismatches
        or invalid operations return False.
        """
        try:
            if op == "eq":
                return actual == expected
            
            elif op == "neq":
                return actual != expected
            
            elif op == "gt":
                return actual is not None and actual > expected
            
            elif op == "gte":
                return actual is not None and actual >= expected
            
            elif op == "lt":
                return actual is not None and actual < expected
            
            elif op == "lte":
                return actual is not None and actual <= expected
            
            elif op == "in":
                # Value in list
                return actual in expected if expected else False
            
            elif op == "not_in":
                # Value not in list
                return actual not in expected if expected else True
            
            elif op == "contains":
                # List/string/dict contains value
                # - list: membership check
                # - string: substring check
                # - dict: key membership check
                # - None: returns False
                if actual is None:
                    return False
                return expected in actual
            
            elif op == "exists":
                # Truthiness check: None, "", [], {}, 0, False are all falsy
                return bool(actual)
            
            elif op == "present":
                # Key presence check: value can be falsy
                return key_exists
            
            elif op == "not_exists":
                # Key is falsy or missing
                return not bool(actual)
            
            elif op == "not_empty":
                # Collection has items
                if actual is None:
                    return False
                return bool(actual)
            
            elif op == "empty":
                # Collection is empty
                if actual is None:
                    return True
                return not bool(actual)
            
            elif op == "mod":
                # Modulo operation: turn_count % 5 == 0
                result = rule.get("result", 0)
                if actual is None or expected is None:
                    return False
                return (actual % expected) == result
            
            # Unknown operator - treat as pass
            logger.warning(f"Unknown condition operator: {op}")
            return True
            
        except (TypeError, ValueError, AttributeError) as e:
            # Type mismatch or invalid operation → condition fails
            logger.debug(f"Condition comparison error for op '{op}': {e}")
            return False


def evaluate_conditions(conditions: Optional[Dict], blackboard: Blackboard,
                        meta: Dict, agent_id: str) -> bool:
    """Convenience function to evaluate conditions without instantiating evaluator."""
    evaluator = ConditionEvaluator()
    return evaluator.evaluate(conditions, blackboard, meta, agent_id)
