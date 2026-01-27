"""
Blackboard - Structured shared state for the agent system (v2).

The Blackboard provides typed containers for agent coordination:
- Events: Transient signals for triggering other agents
- Variables: Session-scoped key-value storage
- Queues: Ordered lists (FIFO) for work items
- Facts: Extracted knowledge with deduplication
- Memory: Agent-private state

Persistence is host responsibility. The framework maintains the
Blackboard in-memory for session lifetime.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from copy import deepcopy

from .models import Event, Fact


class Blackboard(BaseModel):
    """Structured shared state for the agent system.
    
    In-memory only; persistence is host responsibility.
    """
    
    # Container storage
    events: List[Event] = Field(default_factory=list, description="Transient signals (structured)")
    variables: Dict[str, Any] = Field(default_factory=dict, description="Session-scoped key-value")
    queues: Dict[str, List[Any]] = Field(default_factory=dict, description="Ordered lists (FIFO)")
    facts: List[Fact] = Field(default_factory=list, description="Extracted knowledge")
    memory: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="Agent-private state")
    
    class Config:
        arbitrary_types_allowed = True
    
    # =========================================================================
    # Event Operations
    # =========================================================================
    
    def emit_event(self, event: Event) -> None:
        """Emit a structured event (will trigger subscribed agents).
        
        Events are NOT deduplicated by default. Multiple events with the 
        same name may coexist (e.g., multiple questions detected in one turn).
        If deduplication is needed, use event_id in payload.
        """
        self.events.append(event)
    
    def clear_events(self) -> None:
        """Clear all events (called after process_turn completes)."""
        self.events = []
    
    def has_event(self, event_name: str) -> bool:
        """Check if any event with this name is pending."""
        return any(e.name == event_name for e in self.events)
    
    def get_events_by_name(self, event_name: str) -> List[Event]:
        """Get all events with a given name (may be multiple)."""
        return [e for e in self.events if e.name == event_name]
    
    def count_events(self, event_name: str) -> int:
        """Count events with a given name."""
        return sum(1 for e in self.events if e.name == event_name)
    
    # =========================================================================
    # Variable Operations
    # =========================================================================
    
    def set_var(self, key: str, value: Any) -> None:
        """Set a session variable.
        
        Note: Keys starting with 'sys.' are reserved for engine use.
        Hosts and agents should not write to sys.* variables.
        """
        self.variables[key] = value
    
    def get_var(self, key: str, default: Any = None) -> Any:
        """Get a session variable."""
        return self.variables.get(key, default)
    
    def delete_var(self, key: str) -> None:
        """Delete a session variable."""
        self.variables.pop(key, None)
    
    def has_var(self, key: str) -> bool:
        """Check if a variable exists."""
        return key in self.variables
    
    # =========================================================================
    # Queue Operations
    # =========================================================================
    
    def push_queue(self, queue_name: str, item: Any) -> None:
        """Push an item to a queue."""
        if queue_name not in self.queues:
            self.queues[queue_name] = []
        self.queues[queue_name].append(item)
    
    def push_queue_items(self, queue_name: str, items: List[Any]) -> None:
        """Push multiple items to a queue."""
        if queue_name not in self.queues:
            self.queues[queue_name] = []
        self.queues[queue_name].extend(items)
    
    def pop_queue(self, queue_name: str) -> Optional[Any]:
        """Pop the first item from a queue (FIFO)."""
        if queue_name in self.queues and self.queues[queue_name]:
            return self.queues[queue_name].pop(0)
        return None
    
    def peek_queue(self, queue_name: str) -> Optional[Any]:
        """Peek at the first item without removing."""
        if queue_name in self.queues and self.queues[queue_name]:
            return self.queues[queue_name][0]
        return None
    
    def queue_length(self, queue_name: str) -> int:
        """Get the length of a queue."""
        return len(self.queues.get(queue_name, []))
    
    def clear_queue(self, queue_name: str) -> None:
        """Clear a queue."""
        self.queues[queue_name] = []
    
    def has_queue(self, queue_name: str) -> bool:
        """Check if a queue exists."""
        return queue_name in self.queues
    
    # =========================================================================
    # Fact Operations
    # =========================================================================
    
    def add_fact(self, fact: Fact) -> None:
        """Add a fact with deduplication. See SPEC_V2.md §6.5.4 for semantics.
        
        Deduplication rules:
        - If key is None: replace ANY existing fact of this type
        - If key is set: replace only matching (type, key) pair
        
        When duplicates exist, higher confidence wins (caller handles
        priority via merge ordering).
        """
        if fact.key is None:
            # key=None: replace ANY existing fact of this type
            existing = next((f for f in self.facts if f.type == fact.type), None)
        else:
            # key is set: replace only matching (type, key) pair
            existing = next((f for f in self.facts 
                            if f.type == fact.type and f.key == fact.key), None)
        
        if existing:
            # Higher confidence wins; caller handles priority via merge order
            if fact.confidence >= existing.confidence:
                self.facts.remove(existing)
                self.facts.append(fact)
        else:
            self.facts.append(fact)
    
    def get_fact(self, fact_type: str, key: Optional[str] = None) -> Optional[Fact]:
        """Get a fact by type and optional key."""
        if key is not None:
            return next((f for f in self.facts if f.type == fact_type and f.key == key), None)
        return next((f for f in self.facts if f.type == fact_type), None)
    
    def get_facts_by_type(self, fact_type: str) -> List[Fact]:
        """Get all facts of a type (may have different keys)."""
        return [f for f in self.facts if f.type == fact_type]
    
    def has_fact(self, fact_type: str, key: Optional[str] = None) -> bool:
        """Check if a fact exists."""
        return self.get_fact(fact_type, key) is not None
    
    # =========================================================================
    # Memory Operations (Agent-Private State)
    # =========================================================================
    
    def get_memory(self, agent_id: str) -> Dict[str, Any]:
        """Get an agent's private memory."""
        return self.memory.get(agent_id, {})
    
    def set_memory(self, agent_id: str, data: Dict[str, Any]) -> None:
        """Set an agent's private memory (full replace)."""
        self.memory[agent_id] = data
    
    def update_memory(self, agent_id: str, updates: Dict[str, Any]) -> None:
        """Merge updates into an agent's memory."""
        if agent_id not in self.memory:
            self.memory[agent_id] = {}
        self.memory[agent_id].update(updates)
    
    def has_memory(self, agent_id: str) -> bool:
        """Check if an agent has any memory stored."""
        return agent_id in self.memory and bool(self.memory[agent_id])
    
    # =========================================================================
    # Snapshot (for phase isolation)
    # =========================================================================
    
    def snapshot(self) -> "Blackboard":
        """Create a deep copy of the Blackboard for phase isolation.
        
        During a phase, all agents evaluate against the same immutable
        snapshot. State updates are collected and merged only after all
        agents in the phase complete.
        """
        return Blackboard(
            events=deepcopy(self.events),
            variables=deepcopy(self.variables),
            queues=deepcopy(self.queues),
            facts=deepcopy(self.facts),
            memory=deepcopy(self.memory)
        )
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "events": [e.model_dump() for e in self.events],
            "variables": self.variables,
            "queues": self.queues,
            "facts": [f.model_dump() for f in self.facts],
            "memory": self.memory
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Blackboard":
        """Create from dictionary."""
        return cls(
            events=[Event(**e) for e in data.get("events", [])],
            variables=data.get("variables", {}),
            queues=data.get("queues", {}),
            facts=[Fact(**f) for f in data.get("facts", [])],
            memory=data.get("memory", {})
        )
