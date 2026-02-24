# Xubb Agents Framework v2.0
## Techno-Functional-Implementation Specification

**Version:** 2.0.3  
**Status:** Final (Production-Ready)  
**Date:** January 27, 2026  
**Scope:** Complete framework redesign with enhanced Blackboard architecture and event-driven agent coordination  
**Compatibility:** 100% backward compatible with v1.0 agents  
**Revision:** v2.0.3 — Fixed operator implementation, aligned examples with v2 patterns, clarified responsibilities

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Vision & Positioning](#2-vision--positioning)
3. [Architectural Principles](#3-architectural-principles)
4. [Core Components](#4-core-components)
5. [Data Models](#5-data-models)
6. [Blackboard Architecture](#6-blackboard-architecture)
7. [Trigger System](#7-trigger-system)
8. [Execution Flow](#8-execution-flow)
9. [Agent Configuration](#9-agent-configuration)
10. [Output Handling](#10-output-handling)
11. [Observability & Debugging](#11-observability--debugging)
12. [Host Integration](#12-host-integration)
13. [Migration from v1.0](#13-migration-from-v10)
14. [Implementation Roadmap](#14-implementation-roadmap)
15. [Future Considerations](#15-future-considerations)
16. [Appendices](#appendix-a-glossary)
    - [A: Glossary](#appendix-a-glossary)
    - [B: Quick Reference](#appendix-b-quick-reference)
    - [C: Condition Operators](#appendix-c-condition-operators-reference)
    - [D: Insight Extensibility](#appendix-d-insight-extensibility-via-metadata)
    - [E: RAG Integration](#appendix-e-rag-integration)

---

## 1. Executive Summary

### 1.1 What is Xubb Agents?

**Xubb Agents** is the first open framework for building real-time conversational intelligence systems. It enables the creation of AI-powered "Conversational Copilots" — systems where multiple AI agents observe live human-to-human conversations and provide real-time guidance, coaching, and insights to participants.

### 1.2 Key Differentiators

| Aspect | Xubb Agents | Traditional Frameworks |
|--------|-------------|------------------------|
| **Model** | AI observes and advises humans | AI replaces humans |
| **Timing** | Real-time (milliseconds) | Batch or post-hoc |
| **Architecture** | Multi-agent parallel execution | Sequential chains |
| **Coordination** | Event-driven Blackboard | Manual state passing |
| **Domain** | Conversational (turns, silence, keywords) | General-purpose |

### 1.3 What's New in v2.0

| Feature | v1.0 | v2.0 |
|---------|------|------|
| State management | Flat dictionary | Structured Blackboard |
| Agent coordination | Parallel only | Event-driven pub/sub |
| Trigger conditions | None | Blackboard-aware preconditions |
| Execution phases | Single pass | Multi-phase (normal → event-triggered) |
| Data containers | Unstructured | Variables, Events, Queues, Facts, Memory |
| Response caching | Hash-based LLM cache | **Removed** (cooldowns + conditions are better) |

### 1.4 v2.0 Scope Summary

#### In Scope (v2.0)

| Category | Features |
|----------|----------|
| **Blackboard Architecture** | Structured state with Variables, Events, Queues, Facts, Memory containers |
| **Event System** | EVENT trigger type, event emission, subscription, multi-phase execution |
| **Trigger Conditions** | Blackboard-aware preconditions to skip unnecessary LLM calls |
| **Extended Response Model** | New fields: events, variable_updates, queue_pushes, facts, memory_updates |
| **Backward Compatibility** | Full v1.0 support with automatic sync layer |
| **Observability** | Multi-phase tracing, new callbacks |
| **RAG Support** | Preserved at v1.0 level (`rag_docs: List[str]`) |
| **Insight Extensibility** | Via `metadata` field (documented pattern, see Appendix D) |

#### Out of Scope (Deferred to v2.1+)

| Feature | Reason |
|---------|--------|
| **Tool/Function Calling** | Requires additional design; agents advise, host acts |
| **MCP Integration** | Waiting for ecosystem maturity |
| **Structured RAG Documents** | v1.0 level sufficient for now |
| **Custom InsightType Registry** | Metadata extensibility is sufficient |
| **Streaming Responses** | Performance optimization, not core architecture |
| **Session Persistence** | Host responsibility in v2.0 |

#### Removed from v1.0

| Feature | Reason |
|---------|--------|
| **Response Caching** | Cooldowns + trigger conditions are more correct; caching risks stale responses in dynamic conversations |

---

## 2. Vision & Positioning

### 2.1 Category Definition

**"Conversational Copilot Framework"**

A system where AI augments human performance in live conversations, rather than replacing the human speaker.

### 2.2 Target Use Cases

| Use Case | Description |
|----------|-------------|
| **Sales Coaching** | Real-time guidance during customer calls |
| **Customer Support** | Live assistance for support agents |
| **Interview Prep** | Coaching during practice interviews |
| **Negotiation** | Tactical advice during negotiations |
| **Meeting Intelligence** | Live insights during team meetings |
| **Language Learning** | Real-time conversation coaching |

### 2.3 Design Philosophy

1. **Observer, Not Speaker** — Agents advise humans, they don't replace them
2. **Event-Driven** — Agents react to conversation events, not timers
3. **Parallel Intelligence** — Multiple specialists analyze simultaneously
4. **Loose Coupling** — Agents communicate via Blackboard, not direct calls
5. **Transcript Agnostic** — Framework doesn't assume transcript format
6. **Host Controlled** — Host application owns preprocessing and triggers

---

## 3. Architectural Principles

### 3.1 Core Principles

| Principle | Description |
|-----------|-------------|
| **Event-Driven Execution** | Agents are dormant until triggered by events |
| **Stateless Evaluation** | Each agent call is a pure function: `f(context) → response` |
| **Non-Blocking Concurrency** | All I/O is async; agents run in parallel |
| **Graceful Degradation** | Individual agent failures are isolated |
| **Separation of Concerns** | Host handles transcription; framework handles intelligence |

### 3.2 System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         HOST APPLICATION                                 │
│  (xubb_server, CLI tool, desktop app, etc.)                             │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │ Transcription│  │ Preprocessing│  │   Session    │                   │
│  │   Source     │─▶│   (optional) │─▶│   Manager    │                   │
│  └──────────────┘  └──────────────┘  └──────┬───────┘                   │
│                                              │                           │
└──────────────────────────────────────────────┼───────────────────────────┘
                                               │
                                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      XUBB_AGENTS FRAMEWORK                               │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                       AgentContext                               │    │
│  │  - session_id          - recent_segments    - shared_state      │    │
│  │  - trigger_type        - trigger_metadata   - rag_docs          │    │
│  │  - user_context        - language_directive - blackboard (v2)   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                     │
│                                    ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                       AgentEngine                                │    │
│  │                                                                  │    │
│  │  Phase 1: Run TURN_BASED/KEYWORD/SILENCE/INTERVAL agents        │    │
│  │      │                                                          │    │
│  │      ▼                                                          │    │
│  │  Collect Events + Apply State Updates                           │    │
│  │      │                                                          │    │
│  │      ▼                                                          │    │
│  │  Phase 2: Run EVENT-triggered agents (if events emitted)        │    │
│  │      │                                                          │    │
│  │      ▼                                                          │    │
│  │  Aggregate Responses                                            │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                     │
│                                    ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                      AgentResponse                               │    │
│  │  - insights            - events             - variable_updates  │    │
│  │  - queue_pushes        - facts              - memory_updates    │    │
│  │  - data                - debug_info                             │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.3 Directory Structure

```
xubb_agents/
├── core/
│   ├── __init__.py
│   ├── agent.py           # BaseAgent, AgentConfig
│   ├── engine.py          # AgentEngine (orchestrator)
│   ├── blackboard.py      # NEW: Structured Blackboard
│   ├── conditions.py      # NEW: Trigger condition evaluator
│   ├── llm.py             # LLM client wrapper
│   ├── models.py          # Pydantic data models
│   └── callbacks.py       # Callback protocol
├── library/
│   ├── __init__.py
│   ├── dynamic.py         # DynamicAgent implementation
│   └── schemas/           # Output format schemas
│       ├── default.json
│       ├── v2_raw.json
│       └── ...
├── utils/
│   ├── __init__.py
│   ├── tracing.py         # Structured logging
│   └── transcript.py      # OPTIONAL: Transcript utilities
├── __init__.py
├── README.md
├── technical_spec_agents.md    # v1.0 spec (legacy)
└── SPEC_V2.md                  # THIS DOCUMENT
```

---

## 4. Core Components

### 4.1 AgentEngine (`core/engine.py`)

The central orchestrator responsible for:

| Responsibility | Description |
|----------------|-------------|
| **Registry** | Maintains list of active agents |
| **Routing** | Determines which agents run based on trigger type |
| **Condition Evaluation** | Checks trigger conditions before running agents |
| **Blackboard Management** | Manages structured state (in-memory for session lifetime) |
| **Event Dispatch** | Collects emitted events, triggers subscribers |
| **Multi-Phase Execution** | Runs normal agents, then event-triggered agents |
| **Response Aggregation** | Merges insights, applies state updates by priority with deterministic ordering |
| **Observability** | Emits lifecycle events to callbacks |

**Note:** Response caching was removed in v2.0. Cooldowns and trigger conditions provide more correct mechanisms for preventing unnecessary LLM calls.

### 4.2 BaseAgent (`core/agent.py`)

The abstract base class for all agents.

**Lifecycle:**
1. `__init__`: Configure triggers, cooldowns, conditions
2. `process()`: Template method — enforces **cooldown only** (routing is engine's job)
3. `evaluate()`: Abstract method — the "brain" (LLM call)

**Responsibility Split (Engine vs Agent):**

| Responsibility | Owner | Notes |
|----------------|-------|-------|
| Trigger type routing | **Engine** | Determines which agents match the trigger type |
| Condition evaluation | **Engine** | Evaluates trigger_conditions before calling agent |
| Cooldown enforcement | **Agent** | Agent's `process()` checks its own cooldown timer |
| Error handling | **Agent** | Returns `InsightType.ERROR` instead of propagating exceptions |

**Note:** `BaseAgent.process()` does **not** re-check trigger type or conditions — that would duplicate engine logic and risk disagreements.

### 4.3 Blackboard (`core/blackboard.py`) — NEW

Structured shared state with typed containers. **In-memory only**; persistence is host responsibility.

```python
class Blackboard:
    events: List[Event]                  # Transient signals (structured)
    variables: Dict[str, Any]            # Session-scoped key-value
    queues: Dict[str, List[Any]]         # Ordered lists (FIFO)
    facts: List[Fact]                    # Extracted knowledge
    memory: Dict[str, Dict[str, Any]]    # Agent-private state
```

**Persistence Boundary:**
- **Framework:** Maintains blackboard in-memory for session lifetime
- **Host:** Responsible for durable persistence (save/restore blackboard to DB/file if needed)
- **Agents:** Emit updates (`variable_updates`, `memory_updates`, etc.) but do NOT persist directly

### 4.4 ConditionEvaluator (`core/conditions.py`) — NEW

Evaluates trigger conditions against Blackboard state.

```python
class ConditionEvaluator:
    def evaluate(self, conditions: dict, blackboard: Blackboard, meta: dict) -> bool
    def evaluate_rule(self, rule: dict, blackboard: Blackboard, meta: dict) -> bool
```

### 4.5 LLMClient (`core/llm.py`)

Thin wrapper around async OpenAI-compatible API.

- Centralizes API key management
- Enforces JSON response format
- Model-agnostic (works with any OpenAI-compatible endpoint)

### 4.6 DynamicAgent (`library/dynamic.py`)

The primary agent implementation for user-defined agents.

- Loads configuration from dictionary (DB/JSON)
- Supports Jinja2 prompt templating
- Pluggable output schemas
- Emits `memory_updates` for private state (host persists if needed)

---

## 5. Data Models

### 5.1 TranscriptSegment

```python
class TranscriptSegment(BaseModel):
    """A single piece of speech from the conversation."""
    speaker: str = Field(..., description="Who spoke? Any string.")
    text: str = Field(..., description="The text content")
    timestamp: float = Field(..., description="Seconds since session start (session-relative)")
    is_final: bool = Field(default=True, description="Is this segment complete?")
```

**Notes:**
- The framework is transcript-agnostic. It accepts any speaker labels and does not assume diarization.
- `timestamp` is session-relative (seconds since session start), not Unix epoch.
- `is_final=False` segments are included in context but may be updated. The engine does not filter non-final segments; the host decides whether to send them.

### 5.2 AgentContext

```python
class AgentContext(BaseModel):
    """The full context delivered to an agent."""
    session_id: str
    recent_segments: List[TranscriptSegment]
    
    # State (v1 compatibility)
    shared_state: Dict[str, Any] = Field(default_factory=dict)
    
    # Blackboard (v2) — structured state
    blackboard: Optional[Blackboard] = None
    
    # Trigger information (set by engine, not host)
    trigger_type: TriggerType = TriggerType.TURN_BASED
    trigger_metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Context enrichment
    rag_docs: List[str] = Field(default_factory=list)
    user_context: Optional[str] = None
    language_directive: Optional[str] = None
    
    # Execution metadata (read-only, set by engine)
    turn_count: int = 0
    phase: int = 1  # Which execution phase (1 = normal, 2 = event-triggered)
```

**API Note:** `trigger_type` is passed to `process_turn()` as a parameter AND stored in `AgentContext`. The engine copies the parameter into context before agent execution. Agents should read from `context.trigger_type`.

### 5.3 AgentResponse

```python
class AgentResponse(BaseModel):
    """The result of an agent evaluation."""
    
    # Core output
    insights: List[AgentInsight] = Field(default_factory=list)
    
    # Blackboard updates (v2)
    events: List[Event] = Field(default_factory=list)  # Structured events
    variable_updates: Dict[str, Any] = Field(default_factory=dict)
    queue_pushes: Dict[str, List[Any]] = Field(default_factory=dict)
    facts: List[Fact] = Field(default_factory=list)
    memory_updates: Dict[str, Any] = Field(default_factory=dict)
    
    # Legacy compatibility (v1)
    state_updates: Dict[str, Any] = Field(default_factory=dict)
    
    # Sidecar data
    data: Dict[str, Any] = Field(default_factory=dict)
    
    # Debug/tracing
    debug_info: Dict[str, Any] = Field(default_factory=dict)
```

**Event Semantics:** Events in the response are used for:
1. **Internal dispatch** — triggering Phase 2 agents
2. **Telemetry** — included in traces for debugging

Events are cleared from the blackboard after each `process_turn()` call completes.

### 5.4 AgentInsight

```python
class AgentInsight(BaseModel):
    """A single piece of advice/feedback."""
    agent_id: str
    agent_name: str
    type: InsightType
    content: str = Field(..., min_length=2)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    expiry: int = Field(default=15, description="Seconds to display")
    action_label: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

### 5.5 InsightType

```python
class InsightType(str, Enum):
    SUGGESTION = "suggestion"   # Passive advice
    WARNING = "warning"         # Urgent negative
    OPPORTUNITY = "opportunity" # Urgent positive
    FACT = "fact"              # Contextual information
    PRAISE = "praise"          # Positive reinforcement
    ERROR = "error"            # System issues
```

### 5.6 TriggerType

```python
class TriggerType(str, Enum):
    TURN_BASED = "turn_based"  # After a turn completes
    KEYWORD = "keyword"        # Keyword detected
    SILENCE = "silence"        # Dead air threshold
    INTERVAL = "interval"      # Time-based periodic
    EVENT = "event"            # NEW: Triggered by Blackboard event
```

### 5.7 Fact — NEW

```python
class Fact(BaseModel):
    """An extracted piece of knowledge."""
    type: str                  # Category: "budget", "timeline", "contact", etc.
    key: Optional[str] = None  # Instance key: "budget.primary", "stakeholder.cfo"
    value: Any                 # The extracted value
    confidence: float = 1.0    # Extraction confidence
    source_agent: str          # Which agent extracted it
    timestamp: float           # When it was extracted (session-relative)
```

**Deduplication:** Facts are deduplicated by `(type, key)`. If `key` is None, deduplication is by `type` only. When duplicates exist: higher agent **priority** wins (via merge ordering); if equal priority, higher **confidence** wins; if still equal, later **registration order** wins. See §6.5.4 for authoritative rules.

**Examples:**
- `Fact(type="budget", key="primary", value=50000)` — primary budget
- `Fact(type="budget", key="secondary", value=20000)` — secondary budget  
- `Fact(type="stakeholder", key="cfo", value="Sarah Chen")` — CFO stakeholder
- `Fact(type="stakeholder", key="cto", value="Mike Johnson")` — CTO stakeholder

### 5.8 Event — NEW

```python
class Event(BaseModel):
    """A structured event emitted by an agent."""
    name: str                           # Event name: "question_detected", "objection_raised"
    payload: Dict[str, Any] = {}        # Event data (e.g., the detected question text)
    source_agent: str                   # Which agent emitted it
    timestamp: float                    # When it was emitted (seconds since session start)
    id: Optional[str] = None            # Optional unique ID for tracing/deduplication
```

**Event ID:** The optional `id` field enables tracing and correlation across systems. If not provided, one can be generated from `(name, source_agent, timestamp)`. If you need explicit deduplication, set a deterministic `id`.

**Event vs Variables:** Use events for "something happened" signals that trigger other agents. Use variables for "current state is X" that persists. Events carry their payload directly; don't use `variable_updates` to pass event data.

**Example:**
```python
# Good: Event with payload
Event(name="question_detected", payload={"question": "What is pricing?"}, source_agent="extractor")

# Avoid: Event without payload + separate variable
# events=["question_detected"], variable_updates={"pending_question": "..."}  # Awkward
```

---

## 6. Blackboard Architecture

### 6.1 Overview

The Blackboard is a structured shared workspace where agents read and write information. It replaces the flat `shared_state` dictionary with typed containers.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            BLACKBOARD                                    │
├─────────────────────────────────────────────────────────────────────────┤
│  EVENTS (transient, structured)                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Event(name="question_detected", payload={"q": "What's price?"}) │    │
│  │ Event(name="objection_raised", payload={"type": "price"})       │    │
│  └─────────────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────────────┤
│  VARIABLES (session-scoped)                                              │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ phase: "negotiation"                                            │    │
│  │ sentiment: 0.7                                                  │    │
│  │ meta_context: "Customer discussing enterprise pricing..."       │    │
│  │ turn_count: 15                                                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────────────┤
│  QUEUES (ordered lists)                                                  │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ pending_questions: ["What's the price?", "When can you start?"] │    │
│  │ action_items: ["Send proposal", "Schedule follow-up"]           │    │
│  └─────────────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────────────┤
│  FACTS (extracted knowledge)                                             │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ {type: "budget", value: "$50,000", confidence: 0.9}             │    │
│  │ {type: "timeline", value: "Q2 2026", confidence: 0.85}          │    │
│  │ {type: "decision_maker", value: "Sarah, VP Sales", conf: 0.95}  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────────────┤
│  MEMORY (agent-private)                                                  │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ question_extractor: {questions_found: 3, last_question: "..."}  │    │
│  │ sentiment_tracker: {history: [...], trend: "improving"}         │    │
│  │ context_summarizer: {last_update_turn: 10}                      │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Container Semantics

| Container | Semantics | Lifetime | Scope | Operations |
|-----------|-----------|----------|-------|------------|
| **Events** | "Something happened" (structured with payload) | Consumed after `process_turn()` | Global | emit, subscribe |
| **Variables** | "Current state is X" | Session | Global | get, set, delete |
| **Queues** | "Ordered work items" | Session | Global | push, pop, peek, clear |
| **Facts** | "Extracted knowledge" (keyed, deduplicated) | Session | Global | add, query, dedupe by (type,key) |
| **Memory** | "Agent's scratchpad" | Session (host persists if needed) | Agent-only | get, set |

**Reserved Variable Namespace:**
- `sys.*` — Reserved for engine-maintained state (e.g., `sys.turn_count`)
- User variables should avoid the `sys.` prefix

### 6.3 Blackboard Class

```python
class Blackboard(BaseModel):
    """Structured shared state for the agent system."""
    
    # Container storage
    events: List[Event] = Field(default_factory=list)      # Structured events
    variables: Dict[str, Any] = Field(default_factory=dict)
    queues: Dict[str, List[Any]] = Field(default_factory=dict)
    facts: List[Fact] = Field(default_factory=list)
    memory: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    
    # --- Event Operations ---
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
    
    # --- Variable Operations ---
    def set_var(self, key: str, value: Any) -> None:
        """Set a session variable."""
        self.variables[key] = value
    
    def get_var(self, key: str, default: Any = None) -> Any:
        """Get a session variable."""
        return self.variables.get(key, default)
    
    def delete_var(self, key: str) -> None:
        """Delete a session variable."""
        self.variables.pop(key, None)
    
    # --- Queue Operations ---
    def push_queue(self, queue_name: str, item: Any) -> None:
        """Push an item to a queue."""
        if queue_name not in self.queues:
            self.queues[queue_name] = []
        self.queues[queue_name].append(item)
    
    def pop_queue(self, queue_name: str) -> Optional[Any]:
        """Pop the first item from a queue."""
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
    
    # NOTE: Queue Consumption Pattern
    # The framework does NOT enforce queue consumption. Common patterns:
    # - Agent pops the queue item it handles
    # - Host pops after displaying or executing an action
    # Queue semantics must be defined at the application level.
    
    # --- Fact Operations ---
    def add_fact(self, fact: Fact) -> None:
        """Add a fact with deduplication. See 6.5.4 for semantics."""
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
    
    # --- Memory Operations ---
    def get_memory(self, agent_id: str) -> Dict[str, Any]:
        """Get an agent's private memory."""
        return self.memory.get(agent_id, {})
    
    def set_memory(self, agent_id: str, data: Dict[str, Any]) -> None:
        """Set an agent's private memory."""
        self.memory[agent_id] = data
    
    def update_memory(self, agent_id: str, updates: Dict[str, Any]) -> None:
        """Merge updates into an agent's memory."""
        if agent_id not in self.memory:
            self.memory[agent_id] = {}
        self.memory[agent_id].update(updates)
```

### 6.4 Agent Access to Blackboard

In Jinja2 templates:

```jinja2
{# Variables #}
Current phase: {{ blackboard.variables.phase }}
Sentiment: {{ blackboard.variables.sentiment }}

{# Queues #}
Pending questions: {{ blackboard.queues.pending_questions | length }}
{% for q in blackboard.queues.pending_questions %}
- {{ q }}
{% endfor %}

{# Facts #}
{% for fact in blackboard.facts %}
- {{ fact.type }}: {{ fact.value }} (confidence: {{ fact.confidence }})
{% endfor %}

{# Memory (own) #}
My last action: {{ blackboard.memory[agent_id].last_action }}
```

### 6.5 Merge Ordering Rules (Deterministic Conflict Resolution)

When multiple agents run in parallel and update the same containers, the engine applies updates in a **deterministic order** to ensure reproducible behavior.

#### 6.5.1 General Rule

Updates are applied in **ascending priority order** (low → high) so that **higher-priority agents write last and therefore win** (last-write-wins semantics). Within the same priority, updates are applied in **agent registration order** (stable tie-break).

```python
# Pseudocode (ASCENDING order = higher priority writes last = higher priority wins)
updates_by_priority = sorted(all_updates, key=lambda u: (u.agent_priority, u.agent_index))
for update in updates_by_priority:
    apply_update(update)
```

#### 6.5.2 Blackboard Snapshot Semantics

**Critical:** During a phase, all agents evaluate against the **same immutable snapshot** of the Blackboard. State updates are collected and merged only **after all agents in the phase complete**. This ensures deterministic behavior regardless of execution timing.

#### 6.5.3 Per-Container Rules

| Container | Conflict Scenario | Resolution |
|-----------|-------------------|------------|
| **Variables** | Same key updated by multiple agents | Higher priority wins (writes last); same priority → later registration order wins |
| **Events** | Same event name from multiple agents | All events kept (no deduplication by default); subscribers see all |
| **Queues** | Multiple agents push to same queue | Pushes applied in ascending priority; higher-priority items appear last |
| **Facts** | Same `(type, key)` from multiple agents | Higher priority wins; if equal priority, higher confidence wins; if still equal, later registration wins |
| **Memory** | Same agent updates own memory | N/A (only one agent can update its own memory) |

#### 6.5.4 Fact Deduplication Semantics

| Case | Deduplication Rule |
|------|-------------------|
| `key` is `None` | Deduplicate by `type` only (replaces any existing fact of that type) |
| `key` is not `None` | Deduplicate by `(type, key)` pair |

When duplicates exist:
1. Higher agent priority wins (writes last)
2. If equal priority, higher confidence wins
3. If still equal, later registration order wins

#### 6.5.5 Example

```
Agent A (priority=5): variable_updates={"phase": "closing"}, queue_pushes={"items": ["A1"]}
Agent B (priority=10): variable_updates={"phase": "negotiation"}, queue_pushes={"items": ["B1", "B2"]}
```

**Result (ascending order, B writes last):**
- `variables["phase"]` = "negotiation" (Agent B wins, higher priority writes last)
- `queues["items"]` = ["A1", "B1", "B2"] (A's items first, then B's — higher priority appends last)

#### 6.5.6 Queue Ordering Considerations

**Note:** The merge ordering means higher-priority agents' items appear **later** in the queue. For FIFO work queues, this may be counterintuitive (high-priority items are processed last).

**Options for priority-aware consumption:**
1. **Default FIFO:** Pop from front; priority determines only merge order
2. **Priority-aware:** Store priority in queue items, consumer picks highest-priority item
3. **Separate queues:** Use `urgent_questions` vs `questions` queues

The framework is **neutral** on consumption patterns — define this at the application level.

#### 6.5.7 Canonical Queue Pattern (Reference)

This is a reference pattern for queue-based agent coordination:

```python
# Phase 1: Extractor pushes to queue
class QuestionExtractor(DynamicAgent):
    # When questions detected, push to queue with structured data
    # Output: {"queue_pushes": {"pending_questions": [
    #   {"text": "...", "speaker": "...", "ts": 45.2, "priority": "normal"}
    # ]}}

# Phase 2: Responder peeks queue, generates response
class QuestionResponder(DynamicAgent):
    # Trigger condition: {"queue": "pending_questions", "op": "not_empty"}
    # Reads: blackboard.queues.pending_questions[0]
    # Does NOT pop — consumption is host/UI responsibility

# Host: After UI displays response
async def on_response_displayed(question_item):
    # Pop the handled item
    session["blackboard"].pop_queue("pending_questions")
```

**Why host pops:** The framework doesn't know when the UI has shown the response. The host has that knowledge and controls the "acknowledgment" lifecycle.

---

## 7. Trigger System

### 7.1 Trigger Types

| Type | When Fired | Use Case |
|------|------------|----------|
| `TURN_BASED` | Host calls `process_turn()` | After speech segment completes |
| `KEYWORD` | Keyword detected in transcript | Immediate reaction to specific terms |
| `SILENCE` | Silence duration exceeds threshold | Dead air intervention |
| `INTERVAL` | Time-based periodic check | Background monitoring |
| `EVENT` | Another agent emits a Blackboard event | Agent coordination |

**KEYWORD Trigger Note:** The engine does **not** automatically scan transcript text for keywords. Keyword detection is **host responsibility**. The engine provides `check_keyword_triggers(text)` as a helper utility. Host workflow:
1. Host detects keyword match (using engine helper or own logic)
2. Host calls `process_turn(..., trigger_type=KEYWORD, allowed_agent_ids=[...])` with matching agents

### 7.2 Event Triggers — NEW

Agents can subscribe to Blackboard events emitted by other agents.

**Emitting Events (Agent A):**
```json
{
  "has_insight": false,
  "events": [
    {
      "name": "question_detected",
      "payload": {"question": "What is your pricing?", "speaker": "CUSTOMER"}
    }
  ]
}
```

**Note:** Event payload carries the data directly. Avoid using `variable_updates` to pass event-related data.

**Subscribing to Events (Agent B):**
```json
{
  "id": "question_responder",
  "trigger_config": {
    "mode": "event",
    "subscribed_events": ["question_detected"]
  }
}
```

**Execution Flow:**
1. Phase 1: Agent A runs, emits `question_detected`
2. Engine collects events, updates Blackboard
3. Phase 2: Engine finds Agent B subscribed to `question_detected`
4. Agent B runs with updated Blackboard context

### 7.3 Trigger Conditions — NEW

Agents can define preconditions that must be satisfied before they run. This prevents unnecessary LLM calls.

**Condition Structure:**
```json
{
  "trigger_conditions": {
    "mode": "all",
    "rules": [
      {"var": "phase", "op": "eq", "value": "negotiation"},
      {"var": "sentiment", "op": "gte", "value": 0.5},
      {"fact": "budget", "op": "exists"},
      {"queue": "pending_questions", "op": "not_empty"}
    ]
  }
}
```

**Supported Operators:**

| Operator | Description | Example |
|----------|-------------|---------|
| `eq` | Equals | `phase == "negotiation"` |
| `neq` | Not equals | `phase != "closed"` |
| `gt` | Greater than | `turn_count > 5` |
| `gte` | Greater than or equal | `sentiment >= 0.5` |
| `lt` | Less than | `risk_score < 3` |
| `lte` | Less than or equal | `confidence <= 0.8` |
| `in` | Value in list | `phase in ["negotiation", "closing"]` |
| `not_in` | Value not in list | `phase not_in ["closed", "lost"]` |
| `contains` | List/string contains value | `topics contains "pricing"` (see note) |
| `exists` | Key is **truthy** (not None, not empty) | `budget exists` |
| `present` | Key exists **regardless of value** | `flag present` (even if `flag=0` or `flag=""`) |
| `not_exists` | Key is **falsy or missing** | `objection not_exists` |
| `not_empty` | Collection has items | `pending_questions not_empty` |
| `empty` | Collection is empty | `action_items empty` |
| `mod` | Modulo operation | `turn_count % 5 == 0` |

**Operator Notes:**
- `exists` tests **truthiness**: `None`, `""`, `[]`, `{}`, `0`, `False` are all considered "not exists"
- `present` tests **key presence only**: the value can be falsy and still pass
- `contains` behavior by type:
  - **list/set/tuple**: membership check (`expected in actual`)
  - **string**: substring check (`expected in actual`)
  - **dict**: key membership check (`expected in actual.keys()`)
  - **None**: returns `False`

**Condition Evaluation Safety:**
Condition evaluation **never raises exceptions**. If a comparison fails due to type mismatch or invalid operation, the condition evaluates to `False`. This ensures agent eligibility checks are always safe.

**Condition Sources:**

| Source | Syntax | Description |
|--------|--------|-------------|
| Variable | `{"var": "key"}` | Blackboard variable |
| Fact | `{"fact": "type"}` | Fact value by type |
| Queue | `{"queue": "name"}` | Queue for length/empty checks |
| Memory (own) | `{"memory": "key"}` | Agent's own memory |
| Memory (other) | `{"memory": "agent_id.key"}` | Another agent's memory (**advanced, discouraged**) |
| Meta | `{"meta": "turn_count"}` | Execution metadata |

**Note on Cross-Agent Memory Access:** Accessing another agent's memory (`{"memory": "other_agent.key"}`) creates tight coupling between agents. Prefer using **facts**, **variables**, or **events** for cross-agent communication instead.

### 7.4 Condition Evaluator

```python
class ConditionEvaluator:
    """Evaluates trigger conditions against Blackboard state."""
    
    def evaluate(self, conditions: Optional[Dict], blackboard: Blackboard, 
                 meta: Dict, agent_id: str) -> bool:
        """
        Evaluate all conditions. Returns True if agent should run.
        
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
        # Get actual value AND key existence (for 'present' operator)
        actual, key_exists = self._get_value(rule, blackboard, meta, agent_id)
        
        # Get operator and expected value
        op = rule.get("op", "eq")
        expected = rule.get("value")
        
        # Evaluate
        return self._compare(actual, op, expected, rule, key_exists)
    
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
            fact = blackboard.get_fact(fact_type)
            key_exists = fact is not None
            return (fact.value if fact else None, key_exists)
        
        elif "queue" in rule:
            queue_name = rule["queue"]
            key_exists = queue_name in blackboard.queues
            return (blackboard.queues.get(queue_name, []), key_exists)
        
        elif "memory" in rule:
            key = rule["memory"]
            if "." in key:
                other_agent, mem_key = key.split(".", 1)
                agent_mem = blackboard.get_memory(other_agent)
                key_exists = mem_key in agent_mem
                return (agent_mem.get(mem_key), key_exists)
            else:
                agent_mem = blackboard.get_memory(agent_id)
                key_exists = key in agent_mem
                return (agent_mem.get(key), key_exists)
        
        elif "meta" in rule:
            meta_key = rule["meta"]
            key_exists = meta_key in meta
            return (meta.get(meta_key), key_exists)
        
        return (None, False)
    
    def _compare(self, actual: Any, op: str, expected: Any, rule: Dict, key_exists: bool) -> bool:
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
                return actual in expected
            elif op == "not_in":
                return actual not in expected
            elif op == "contains":
                return expected in actual if actual else False
            elif op == "exists":
                # Truthiness check: None, "", [], {}, 0, False are all falsy
                return bool(actual)
            elif op == "present":
                # Key presence check: value can be falsy
                return key_exists
            elif op == "not_exists":
                return not bool(actual)
            elif op == "not_empty":
                return bool(actual)
            elif op == "empty":
                return not bool(actual)
            elif op == "mod":
                result = rule.get("result", 0)
                return actual is not None and (actual % expected) == result
            
            return True
        except (TypeError, ValueError, AttributeError):
            # Type mismatch or invalid operation → condition fails
            return False
```

---

## 8. Execution Flow

### 8.1 High-Level Flow

```
Host calls process_turn(context)
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 1: Primary Execution                                       │
│                                                                  │
│  For each registered agent:                                      │
│    1. Check trigger type match                                   │
│    2. Check cooldown                                             │
│    3. Check trigger conditions (against Blackboard)              │
│    4. If all pass → Run agent (LLM call)                        │
│    5. Collect response                                           │
│                                                                  │
│  After all agents complete:                                      │
│    - Merge variable_updates into Blackboard                      │
│    - Process queue_pushes                                        │
│    - Add facts (with deduplication)                              │
│    - Update agent memories                                       │
│    - Collect emitted events                                      │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
                                   ▼
                        Any events emitted?
                                   │
                    ┌──────────────┴──────────────┐
                    │ NO                          │ YES
                    ▼                             ▼
            Skip Phase 2              ┌───────────────────────────┐
                    │                 │ PHASE 2: Event Handling    │
                    │                 │                            │
                    │                 │  Find agents subscribed    │
                    │                 │  to emitted events         │
                    │                 │           │                │
                    │                 │  For each subscribed agent:│
                    │                 │    1. Check cooldown       │
                    │                 │    2. Check conditions     │
                    │                 │    3. Run agent            │
                    │                 │           │                │
                    │                 │  Merge responses           │
                    │                 │  (No further event phases) │
                    │                 └─────────────┬──────────────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    │
                                    ▼
                          Clear transient events
                                    │
                                    ▼
                          Return AgentResponse
```

### 8.2 Agent Eligibility Check

```
Is Agent Eligible to Run?
         │
         ▼
┌─────────────────────┐
│ Trigger Type Match? │───No───▶ Skip (not for this trigger)
└─────────┬───────────┘
          │ Yes
          ▼
┌─────────────────────┐
│ Cooldown Clear?     │───No───▶ Skip (cooling down)
└─────────┬───────────┘
          │ Yes
          ▼
┌─────────────────────┐
│ Conditions Pass?    │───No───▶ Skip (preconditions not met)
└─────────┬───────────┘
          │ Yes
          ▼
┌─────────────────────┐
│ Run Agent (LLM)     │
└─────────────────────┘
```

**Note:** Response caching was removed in v2.0. Cooldowns and trigger conditions provide sufficient protection against unnecessary LLM calls.

### 8.3 State Update Priority

When multiple agents update the same state:

1. Collect all updates with agent priority
2. Sort by priority **ascending** (low → high)
3. Apply in order (higher priority writes last, wins)

```python
# Example: Agent A (priority=1) and Agent B (priority=10) both update "risk_level"
# Apply A first, then B → Agent B's value wins (last-write-wins)
```

### 8.4 Phase Depth Limit

To prevent infinite event cascades:
- **Maximum phases:** 2 (configurable)
- Phase 2 agents **cannot** emit events that trigger Phase 3
- Events emitted in Phase 2 are **recorded and returned** in `AgentResponse.events` and traces, but **not dispatched** to trigger further phases
- All events are **cleared from the Blackboard** after `process_turn()` completes

### 8.5 Agent Failure Atomicity

Agent execution is **atomic** with respect to state updates:

- If an agent errors during evaluation, **none** of its state updates, events, facts, or memory changes are applied
- The agent is isolated from the system state
- An `ERROR` insight may be emitted instead
- Other agents in the same phase continue normally

```python
# Pseudocode
try:
    response = await agent.evaluate(context)
    pending_updates.append(response)  # Only collected if successful
except Exception as e:
    # Response discarded, emit ERROR insight
    error_insight = AgentInsight(type=InsightType.ERROR, content=str(e), ...)
```

### 8.6 Trigger Routing vs Host Allow-Listing

When `allowed_agent_ids` is provided to `process_turn()`, it acts as a **hard allow-list**. Final eligibility is the **intersection** of:

1. `allowed_agent_ids` (if provided) — host filter
2. Trigger type match — engine routing
3. Cooldown status — timing gate
4. Trigger conditions — precondition check

```python
# Pseudocode
def is_eligible(agent, context, allowed_agent_ids):
    if allowed_agent_ids and agent.id not in allowed_agent_ids:
        return False  # Hard filter
    if not matches_trigger_type(agent, context.trigger_type):
        return False
    if not cooldown_clear(agent):
        return False
    if not conditions_pass(agent, context.blackboard):
        return False
    return True
```

**KEYWORD Trigger Note:** Keyword detection is **host responsibility** in v2.0. The engine does not re-scan transcript text; the host must pass `trigger_type=KEYWORD` when keywords are detected.

### 8.7 Canonical Turn Count

The **authoritative turn counter** is `meta.turn_count`. The engine mirrors this value into `blackboard.variables["sys.turn_count"]` for agent access via Jinja2 templates.

**Reserved namespace:** Hosts and agents **must not** write to `sys.*` variables.

```python
# Engine behavior
blackboard.variables["sys.turn_count"] = meta.turn_count
blackboard.variables["sys.session_id"] = context.session_id
# etc.
```

---

## 9. Agent Configuration

### 9.1 Full Configuration Schema

```json
{
  "id": "string (unique identifier)",
  "name": "string (display name)",
  
  "trigger_config": {
    "mode": "turn_based | keyword | silence | interval | event | [array]",
    "cooldown": 15,
    "keywords": ["price", "discount"],
    "silence_threshold": 5,
    "subscribed_events": ["question_detected", "objection_raised"]
  },
  
  "trigger_conditions": {
    "mode": "all | any",
    "rules": [
      {"var": "phase", "op": "eq", "value": "negotiation"},
      {"var": "sentiment", "op": "gte", "value": 0.5}
    ]
  },
  
  "priority": 0,
  
  "model_config": {
    "model": "gpt-4o-mini",
    "context_turns": 30
  },
  
  "text": "Your system prompt here with {{ jinja2 }} templating",

  "output_format": "default | v2_raw | custom_schema_name",

  "include_context": true
}
```

### 9.2 Configuration Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | string | auto-generated | Unique identifier |
| `name` | string | required | Display name |
| `trigger_config.mode` | string/array | "turn_based" | When to trigger |
| `trigger_config.cooldown` | int | 15 | Seconds between runs |
| `trigger_config.keywords` | array | [] | Keywords for KEYWORD trigger |
| `trigger_config.silence_threshold` | int | null | Seconds for SILENCE trigger |
| `trigger_config.subscribed_events` | array | [] | Events for EVENT trigger |
| `trigger_conditions` | object | null | Preconditions (see 7.3) |
| `priority` | int | 0 | State update priority |
| `model_config.model` | string | "gpt-4o-mini" | LLM model |
| `model_config.context_turns` | int | 6 | Transcript segments to include |
| `text` | string | required | System prompt (Jinja2) |
| `output_format` | string | "default" | Output schema name |
| `include_context` | bool | true | Inject user profile & RAG docs into prompt. Set `false` for agents that don't need user/session context (e.g., widget trackers). Language directive is always injected regardless. |

### 9.3 Example Configurations

**Sales Coach (Turn-Based):**
```json
{
  "id": "sales_coach",
  "name": "Sales Coach",
  "trigger_config": {
    "mode": "turn_based",
    "cooldown": 10
  },
  "trigger_conditions": {
    "mode": "all",
    "rules": [
      {"var": "phase", "op": "in", "value": ["discovery", "negotiation", "closing"]}
    ]
  },
  "priority": 5,
  "model_config": {
    "model": "gpt-4o",
    "context_turns": 15
  },
  "text": "You are a sales coach. Phase: {{ blackboard.variables.phase }}..."
}
```

**Question Extractor (Turn-Based, Emits Events):**
```json
{
  "id": "question_extractor",
  "name": "Question Extractor",
  "trigger_config": {
    "mode": "turn_based",
    "cooldown": 0
  },
  "priority": 10,
  "model_config": {
    "model": "gpt-4o-mini",
    "context_turns": 6
  },
  "text": "Detect questions in the conversation. If found, emit question_detected event.",
  "output_format": "v2_events"
}
```

**Question Responder (Event-Triggered):**
```json
{
  "id": "question_responder",
  "name": "Question Responder",
  "trigger_config": {
    "mode": "event",
    "subscribed_events": ["question_detected"],
    "cooldown": 0
  },
  "trigger_conditions": {
    "mode": "all",
    "rules": [
      {"queue": "pending_questions", "op": "not_empty"}
    ]
  },
  "priority": 5,
  "model_config": {
    "model": "gpt-4o",
    "context_turns": 20
  },
  "text": "Answer the question: {{ blackboard.queues.pending_questions[0] }}"
}
```

**Context Summarizer (Periodic):**
```json
{
  "id": "context_summarizer",
  "name": "Context Summarizer",
  "trigger_config": {
    "mode": "turn_based",
    "cooldown": 0
  },
  "trigger_conditions": {
    "mode": "all",
    "rules": [
      {"meta": "turn_count", "op": "mod", "value": 5, "result": 0}
    ]
  },
  "priority": 100,
  "model_config": {
    "model": "gpt-4o-mini",
    "context_turns": 50
  },
  "text": "Update the rolling context summary. Previous: {{ blackboard.variables.meta_context }}"
}
```

**Escalation Monitor (Condition-Based):**
```json
{
  "id": "escalation_monitor",
  "name": "Escalation Monitor",
  "trigger_config": {
    "mode": "turn_based",
    "cooldown": 30
  },
  "trigger_conditions": {
    "mode": "any",
    "rules": [
      {"var": "sentiment", "op": "lt", "value": -0.5},
      {"var": "escalation_flag", "op": "eq", "value": true}
    ]
  },
  "priority": 50,
  "text": "The conversation may need escalation. Assess and recommend action."
}
```

---

## 10. Output Handling

### 10.1 Schema System

Agents return JSON that is parsed according to their `output_format` schema.

**Schema File Structure (`library/schemas/*.json`):**
```json
{
  "instruction": "JSON format instruction appended to prompt",
  "mapping": {
    "root_key": "insight",
    "check_field": "has_insight",
    "content_field": "content",
    "type_field": "type",
    "confidence_field": "confidence",
    "metadata_field": "metadata",
    "events_field": "events",
    "state_field": "variable_updates",
    "queue_field": "queue_pushes",
    "facts_field": "facts",
    "memory_field": "memory_updates"
  }
}
```

### 10.2 Default Schema (v2)

```json
{
  "instruction": "Return JSON: {\"has_insight\": bool, \"content\": \"...\", \"type\": \"suggestion|warning|opportunity|fact|praise\", \"confidence\": 0.0-1.0, \"events\": [...], \"variable_updates\": {...}, \"queue_pushes\": {...}, \"memory_updates\": {...}}",
  "mapping": {
    "check_field": "has_insight",
    "content_field": "content",
    "type_field": "type",
    "confidence_field": "confidence",
    "events_field": "events",
    "state_field": "variable_updates",
    "queue_field": "queue_pushes",
    "memory_field": "memory_updates"
  }
}
```

### 10.3 Response Processing

```python
# Pseudocode for response processing
def process_response(raw_json: dict, schema: dict) -> AgentResponse:
    response = AgentResponse()
    mapping = schema["mapping"]
    
    # Check if agent wants to speak
    if mapping.get("check_field"):
        if not raw_json.get(mapping["check_field"]):
            return response  # No insight
    
    # Extract insight
    content = raw_json.get(mapping.get("content_field", "content"))
    if content:
        response.insights.append(AgentInsight(
            content=content,
            type=raw_json.get(mapping.get("type_field", "type"), "suggestion"),
            confidence=raw_json.get(mapping.get("confidence_field", "confidence"), 1.0)
        ))
    
    # Extract events
    if mapping.get("events_field"):
        response.events = raw_json.get(mapping["events_field"], [])
    
    # Extract state updates
    if mapping.get("state_field"):
        response.variable_updates = raw_json.get(mapping["state_field"], {})
    
    # Extract queue operations
    if mapping.get("queue_field"):
        response.queue_pushes = raw_json.get(mapping["queue_field"], {})
    
    # Extract facts
    if mapping.get("facts_field"):
        raw_facts = raw_json.get(mapping["facts_field"], [])
        response.facts = [Fact(**f) for f in raw_facts]
    
    # Extract memory updates
    if mapping.get("memory_field"):
        response.memory_updates = raw_json.get(mapping["memory_field"], {})
    
    return response
```

### 10.4 Invalid JSON Handling

When an LLM returns invalid JSON:

```python
def handle_llm_response(raw_text: str, agent: BaseAgent) -> AgentResponse:
    """Parse LLM response with error recovery."""
    try:
        # Attempt 1: Direct parse
        return parse_json(raw_text)
    except JSONDecodeError:
        pass
    
    try:
        # Attempt 2: Repair common issues (trailing commas, unquoted keys)
        repaired = attempt_json_repair(raw_text)
        return parse_json(repaired)
    except JSONDecodeError:
        pass
    
    # Attempt 3: Emit ERROR insight, discard all updates
    return AgentResponse(
        insights=[AgentInsight(
            agent_id=agent.config.id,
            agent_name=agent.config.name,
            type=InsightType.ERROR,
            content=f"Agent returned invalid JSON: {raw_text[:100]}...",
            confidence=1.0
        )],
        # No state updates, events, facts, or memory changes applied
    )
```

**Key principle:** Invalid JSON means **all updates are discarded**. The agent's turn is treated as a failure, preserving blackboard integrity.

---

## 11. Observability & Debugging

### 11.0 Timestamp Conventions

| Context | Format | Notes |
|---------|--------|-------|
| **Model timestamps** (`TranscriptSegment.timestamp`, `Event.timestamp`, `Fact.timestamp`) | Seconds since session start | Float, session-relative |
| **Trace timestamps** (`turn_id`, `timestamp` field in JSON) | ISO 8601 wall clock | e.g., `"2026-01-27T10:30:00Z"` |
| **Duration fields** | Milliseconds | Integer, e.g., `duration_ms: 450` |

### 11.1 Callback System

```python
class AgentCallbackHandler(ABC):
    """Protocol for observing agent lifecycle events."""
    
    async def on_turn_start(self, context: AgentContext) -> None:
        """Called when a turn begins processing."""
        pass
    
    async def on_phase_start(self, phase: int, agents: List[str]) -> None:
        """Called when an execution phase begins."""
        pass
    
    async def on_agent_start(self, agent_name: str, context: AgentContext) -> None:
        """Called when an agent begins evaluation."""
        pass
    
    async def on_agent_finish(self, agent_name: str, response: AgentResponse, 
                              duration: float) -> None:
        """Called when an agent completes."""
        pass
    
    async def on_agent_skipped(self, agent_name: str, reason: str) -> None:
        """Called when an agent is skipped (cooldown, conditions, etc.)."""
        pass
    
    async def on_agent_error(self, agent_name: str, error: Exception) -> None:
        """Called when an agent fails."""
        pass
    
    async def on_phase_end(self, phase: int, events_emitted: List[str]) -> None:
        """Called when an execution phase completes."""
        pass
    
    async def on_turn_end(self, response: AgentResponse, duration: float) -> None:
        """Called when a turn completes."""
        pass
```

### 11.2 Structured Tracing (v2)

```json
{
  "turn_id": "uuid",
  "timestamp": "2026-01-27T10:30:00Z",
  "session_id": "session_123",
  
  "context": {
    "user_context": "Sales Director at Acme Corp",
    "language_directive": "Respond in English",
    "transcript_segments": 15,
    "rag_docs_count": 2
  },
  
  "trigger": {
    "type": "turn_based",
    "metadata": {}
  },
  
  "blackboard_initial": {
    "variables": {"phase": "negotiation", "sentiment": 0.7},
    "queues": {"pending_questions": []},
    "facts_count": 3,
    "events": []
  },
  
  "phases": [
    {
      "phase": 1,
      "agents_eligible": ["sales_coach", "question_extractor", "sentiment_tracker"],
      "agents_skipped": [
        {"agent": "escalation_monitor", "reason": "conditions_not_met"}
      ],
      "agents_run": [
        {
          "agent": "question_extractor",
          "duration_ms": 450,
          "insights": 0,
          "events_emitted": [
            {"name": "question_detected", "payload": {"question": "What is pricing?", "speaker": "CUSTOMER"}}
          ],
          "queue_pushes": {"pending_questions": [{"text": "What is pricing?", "speaker": "CUSTOMER", "ts": 45.2}]},
          "variable_updates": {}
        },
        {
          "agent": "sentiment_tracker",
          "duration_ms": 320,
          "insights": 0,
          "events_emitted": [],
          "variable_updates": {"sentiment": 0.65}
        }
      ],
      "events_collected": ["question_detected"]
    },
    {
      "phase": 2,
      "trigger_events": ["question_detected"],
      "agents_eligible": ["question_responder"],
      "agents_run": [
        {
          "agent": "question_responder",
          "duration_ms": 890,
          "insights": 1,
          "events_emitted": [],
          "variable_updates": {}
        }
      ]
    }
  ],
  
  "blackboard_final": {
    "variables": {"phase": "negotiation", "sentiment": 0.65},
    "queues": {"pending_questions": [{"text": "What is pricing?", "speaker": "CUSTOMER", "ts": 45.2}]},
    "facts_count": 3,
    "events": []
  },
  
  "blackboard_delta": {
    "variables_changed": ["sentiment"],
    "queues_changed": ["pending_questions"],
    "facts_added": 0,
    "events_emitted": ["question_detected"]
  },
  
  "response": {
    "insights_count": 1,
    "variable_updates_count": 1,
    "queue_pushes_count": 1,
    "events_emitted_total": 1
  },
  
  "performance": {
    "total_duration_ms": 1660,
    "phase_1_duration_ms": 770,
    "phase_2_duration_ms": 890,
    "llm_calls": 3
  },
  
  "agents_skipped_summary": {
    "cooldown": 0,
    "conditions_not_met": 1,
    "trigger_type_mismatch": 2
  },
  
  "replay": {
    "context_hash": "sha256:abc123...",
    "blackboard_snapshot_hash": "sha256:def456...",
    "agent_configs_hash": "sha256:ghi789..."
  }
}
```

### 11.3 Deterministic Replay

To aid debugging and forensic analysis, traces may include optional **deterministic replay hashes**:

| Hash | Contents |
|------|----------|
| `context_hash` | Hash of `AgentContext` (excluding timestamps) |
| `blackboard_snapshot_hash` | Hash of initial Blackboard state |
| `agent_configs_hash` | Hash of registered agent configurations |

These hashes enable:
- **Reproducible turn execution** — given same hashes, same behavior
- **Regression testing** — detect behavior changes across versions
- **Forensic analysis** — reconstruct exact state during incidents

**Optional fields (privacy-sensitive):**
- `rendered_prompts: Dict[str, str]` — Per-agent rendered prompts (may contain PII)
- `llm_responses: Dict[str, str]` — Raw LLM responses

---

## 12. Host Integration

### 12.1 Host Responsibilities

| Responsibility | Description |
|----------------|-------------|
| **Transcription** | Receive/generate transcript segments |
| **Preprocessing** | Optional aggregation, filtering |
| **Context Building** | Construct `AgentContext` |
| **Trigger Decision** | Decide when to call `process_turn()` |
| **Session Management** | Track sessions, persist state if needed |
| **UI Integration** | Display insights to users |

### 12.2 Integration Example

```python
from xubb_agents import AgentEngine, AgentContext, TriggerType, Blackboard
from xubb_agents.library import DynamicAgent

# Initialize
engine = AgentEngine(api_key="sk-...")

# Load agents from config/DB
agents_config = load_agents_from_db()
for config in agents_config:
    engine.register_agent(DynamicAgent(config))

# Session state
session = {
    "id": "session_123",
    "blackboard": Blackboard(),
    "turn_count": 0,
    "segments": []
}

async def on_transcript_segment(segment: dict):
    """Called by transcription service when speech is detected."""
    session["segments"].append(TranscriptSegment(**segment))
    session["turn_count"] += 1
    
    # NOTE: Do NOT write turn_count to blackboard manually.
    # The engine sets sys.turn_count automatically from context.turn_count.
    
    # Build context
    context = AgentContext(
        session_id=session["id"],
        recent_segments=session["segments"][-100:],  # Keep last 100
        blackboard=session["blackboard"],
        turn_count=session["turn_count"],  # Engine mirrors to sys.turn_count
        user_context="Sales Director at Acme Corp",
        language_directive="Provide coaching in English"
    )
    
    # Process - engine automatically sets blackboard.variables["sys.turn_count"]
    response = await engine.process_turn(
        context,
        trigger_type=TriggerType.TURN_BASED
    )
    
    # Handle response
    for insight in response.insights:
        await send_to_ui(insight)
    
    # Blackboard is updated in-place by engine

async def on_silence(duration_seconds: float):
    """Called when silence is detected."""
    context = AgentContext(
        session_id=session["id"],
        recent_segments=session["segments"][-100:],
        blackboard=session["blackboard"],
        trigger_metadata={"silence_duration": duration_seconds}
    )
    
    response = await engine.process_turn(
        context,
        trigger_type=TriggerType.SILENCE
    )
    
    for insight in response.insights:
        await send_to_ui(insight)

async def on_keyword_detected(keyword: str, segment: dict):
    """Called when a keyword is detected."""
    context = AgentContext(
        session_id=session["id"],
        recent_segments=session["segments"][-100:],
        blackboard=session["blackboard"],
        trigger_metadata={"keyword": keyword}
    )
    
    # Only run agents that care about this keyword
    matches = engine.check_keyword_triggers(segment["text"])
    allowed_ids = [agent.config.id for agent, _ in matches]
    
    response = await engine.process_turn(
        context,
        allowed_agent_ids=allowed_ids,
        trigger_type=TriggerType.KEYWORD
    )
    
    for insight in response.insights:
        await send_to_ui(insight, urgent=True)
```

### 12.3 Transcript Agnosticism

The framework does NOT assume:
- Speaker diarization exists
- Specific speaker labels ("USER"/"SPEAKER" vs names)
- Segment aggregation
- Preprocessing

**The host decides:**
- How to label speakers
- Whether to aggregate segments
- Whether to filter backchannels
- How many segments to include

---

## 13. Migration from v1.0

### 13.1 Backward Compatibility

| v1.0 Feature | v2.0 Status |
|--------------|-------------|
| `shared_state` | Supported (maps to `blackboard.variables`) |
| `state_updates` in response | Supported (maps to `variable_updates`) |
| `memory_{agent_id}` | Supported (maps to `blackboard.memory`) |
| Trigger types | All supported + new `EVENT` type |
| Output schemas | All supported + new fields |

### 13.2 Migration Steps

1. **No immediate changes required** — v1.0 agents work unchanged
2. **Gradual adoption:**
   - Replace `state_updates` with `variable_updates`
   - Replace `shared_state` access with `blackboard.variables`
   - Add `trigger_conditions` to reduce LLM calls
   - Add `events` emission for agent coordination
3. **Full migration:**
   - Convert to structured Blackboard patterns
   - Use Facts for extracted knowledge
   - Use Queues for work items

### 13.3 Compatibility Layer

The compatibility layer ensures 100% backward compatibility with v1.0 agents. **No changes required to existing agents.**

#### 13.3.1 State Synchronization (Bidirectional)

```python
# In AgentEngine, BEFORE running agents:
def _sync_state_to_legacy(self, context: AgentContext) -> None:
    """Sync Blackboard variables INTO shared_state for v1.0 agents."""
    if context.blackboard:
        # v1.0 agents read from context.shared_state
        # Copy blackboard.variables so they see current state
        context.shared_state.update(context.blackboard.variables)

# In AgentEngine, AFTER running agents:
def _sync_state_from_legacy(self, context: AgentContext, 
                            v1_agent_updates: Dict[str, Any]) -> None:
    """Sync shared_state back INTO Blackboard for consistency.
    
    IMPORTANT: Only sync keys that were MODIFIED by v1.0 agents in this turn.
    Do NOT blindly overwrite all keys — this would clobber v2.0 agent updates.
    """
    if context.blackboard:
        # Only apply v1.0-originated keys, not the entire shared_state
        for key, value in v1_agent_updates.items():
            context.blackboard.variables[key] = value
```

#### 13.3.2 Response Field Mapping

```python
# In AgentEngine, when processing responses:
def _normalize_response(self, response: AgentResponse) -> None:
    """Map v1.0 response fields to v2.0 equivalents."""
    
    # Map state_updates → variable_updates (if not already set)
    if response.state_updates and not response.variable_updates:
        response.variable_updates = dict(response.state_updates)
    
    # Handle legacy memory_{agent_id} pattern
    for key, value in list(response.state_updates.items()):
        if key.startswith("memory_"):
            agent_id = key.replace("memory_", "")
            # Move to proper memory location
            if not response.memory_updates:
                response.memory_updates = {}
            response.memory_updates.update(value if isinstance(value, dict) else {})
            # Remove from variable_updates to avoid duplication
            response.variable_updates.pop(key, None)
```

#### 13.3.3 Jinja2 Template Compatibility

Both v1.0 and v2.0 template variables are available:

```python
# In DynamicAgent.evaluate():
rendered_system_prompt = template.render(
    # v1.0 variables (PRESERVED)
    state=context.shared_state,           # {{ state.phase }}
    memory=self.private_state,            # {{ memory.counter }}
    context=context,                      # {{ context.session_id }}
    user_context=context.user_context,    # {{ user_context }}
    
    # v2.0 variables (NEW)
    blackboard=context.blackboard,        # {{ blackboard.variables.phase }}
    agent_id=self.config.id,              # {{ agent_id }}
)
```

**v1.0 prompts continue to work unchanged:**
```jinja2
{# v1.0 style - still works #}
Current phase: {{ state.phase }}
My memory: {{ memory.last_action }}
```

**v2.0 prompts can use new syntax:**
```jinja2
{# v2.0 style - preferred for new agents #}
Current phase: {{ blackboard.variables.phase }}
Pending questions: {{ blackboard.queues.pending_questions | length }}
Budget fact: {{ blackboard.facts | selectattr('type', 'eq', 'budget') | first }}
```

#### 13.3.4 Compatibility Guarantees

| v1.0 Pattern | v2.0 Equivalent | Auto-Mapped? |
|--------------|-----------------|--------------|
| `context.shared_state["key"]` | `context.blackboard.variables["key"]` | ✅ Yes |
| `response.state_updates` | `response.variable_updates` | ✅ Yes |
| `state_updates["memory_X"]` | `blackboard.memory["X"]` | ✅ Yes |
| `{{ state.key }}` in prompts | `{{ blackboard.variables.key }}` | ✅ Both work |
| Trigger types (turn, keyword, etc.) | Same + new EVENT type | ✅ Yes |
| Output schemas | Same + new fields | ✅ Yes |

---

## 14. Implementation Roadmap

### 14.1 Tier 1: Core v2.0 Features

| Feature | Effort | Priority |
|---------|--------|----------|
| `Blackboard` class | 3 hours | P0 |
| `ConditionEvaluator` class | 3 hours | P0 |
| `TriggerType.EVENT` | 2 hours | P0 |
| Multi-phase execution in engine | 3 hours | P0 |
| Extended `AgentResponse` model | 1 hour | P0 |
| Backward compatibility layer | 2 hours | P0 |
| Remove response caching | 0.5 hours | P0 |
| Schema updates for new fields | 2 hours | P0 |
| Updated `DynamicAgent` | 2 hours | P0 |
| Multi-phase tracing | 2 hours | P1 |
| Documentation updates | 3 hours | P1 |

**Tier 1 Total: ~23.5 hours**

### 14.2 Tier 2: Reliability

| Feature | Effort | Priority |
|---------|--------|----------|
| Output validation | 3 hours | P1 |
| LLM retry logic | 3 hours | P1 |
| Insight deduplication | 2 hours | P2 |
| Cost/token tracking | 3 hours | P2 |

**Tier 2 Total: ~11 hours**

### 14.3 Tier 3: Scale & Operations

| Feature | Effort | Priority |
|---------|--------|----------|
| Session persistence | 5 hours | P2 |
| Streaming responses | 6 hours | P2 |
| Agent groups | 4 hours | P3 |
| Rate limiting | 3 hours | P3 |

**Tier 3 Total: ~18 hours**

### 14.4 Milestones

| Milestone | Features | Target |
|-----------|----------|--------|
| **v2.0-alpha** | Blackboard, Events, Conditions | Week 1 |
| **v2.0-beta** | Tracing, validation, retry | Week 2 |
| **v2.0-rc** | Documentation, migration guide | Week 3 |
| **v2.0-release** | Full release | Week 4 |

---

## 15. Future Considerations

### 15.1 Potential Features (Not in v2.0)

| Feature | Description | Complexity |
|---------|-------------|------------|
| **Tool/Function Calling** | Agents can call external APIs | High |
| **Streaming Responses** | Show insights as agents complete | Medium |
| **Human-in-the-Loop** | Approval workflows | Medium |
| **Agent Versioning** | Track prompt changes | Low |
| **A/B Testing** | Compare agent configurations | Medium |
| **Distributed Execution** | Agents across machines | High |

### 15.2 Architecture Evolution

If scale requirements grow significantly:

1. **Phase 1 (Current):** Single-process, in-memory Blackboard
2. **Phase 2:** Redis-backed Blackboard for persistence
3. **Phase 3:** Celery/RQ for distributed agent execution
4. **Phase 4:** Kubernetes for auto-scaling

### 15.3 Ecosystem Vision

```
┌─────────────────────────────────────────────────────────────────┐
│                    XUBB AGENTS ECOSYSTEM                         │
├─────────────────────────────────────────────────────────────────┤
│  xubb_agents          Core framework (this document)            │
│  xubb_agents_ui       React components for insight display      │
│  xubb_agents_studio   Visual agent builder/debugger             │
│  xubb_agents_hub      Pre-built agent templates                 │
│  xubb_agents_eval     Testing & evaluation framework            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **Agent** | An AI unit that evaluates conversation context and produces insights |
| **Blackboard** | Structured shared state where agents read/write information |
| **Event** | A transient signal emitted by an agent to trigger other agents |
| **Fact** | An extracted piece of knowledge with type, value, and confidence |
| **Insight** | A piece of advice/feedback produced by an agent |
| **Phase** | An execution pass (Phase 1 = normal, Phase 2 = event-triggered) |
| **Trigger** | An event that causes agents to run (turn, keyword, silence, etc.) |
| **Turn** | A unit of conversation (segment or logical speaker turn) |

---

## Appendix B: Quick Reference

### Event Emission (Structured)
```json
{
  "events": [
    {"name": "question_detected", "payload": {"question": "What is pricing?"}},
    {"name": "budget_mentioned", "payload": {"amount": 50000}}
  ]
}
```

### Event Subscription
```json
{"trigger_config": {"mode": "event", "subscribed_events": ["question_detected"]}}
```

### Trigger Condition
```json
{"trigger_conditions": {"mode": "all", "rules": [{"var": "phase", "op": "eq", "value": "negotiation"}]}}
```

### Variable Update
```json
{"variable_updates": {"phase": "closing", "sentiment": 0.8}}
```

### Queue Push
```json
{"queue_pushes": {"pending_questions": ["What is the price?"]}}
```

### Fact Addition (with optional key for multiple instances)
```json
{
  "facts": [
    {"type": "budget", "key": "primary", "value": 50000, "confidence": 0.9},
    {"type": "stakeholder", "key": "cfo", "value": "Sarah Chen", "confidence": 0.95}
  ]
}
```

### Memory Update
```json
{"memory_updates": {"last_insight": "...", "counter": 5}}
```

---

## Appendix C: Condition Operators Reference

| Operator | Syntax | Example |
|----------|--------|---------|
| eq | `{"var": "x", "op": "eq", "value": "y"}` | `x == "y"` |
| neq | `{"var": "x", "op": "neq", "value": "y"}` | `x != "y"` |
| gt | `{"var": "x", "op": "gt", "value": 5}` | `x > 5` |
| gte | `{"var": "x", "op": "gte", "value": 5}` | `x >= 5` |
| lt | `{"var": "x", "op": "lt", "value": 5}` | `x < 5` |
| lte | `{"var": "x", "op": "lte", "value": 5}` | `x <= 5` |
| in | `{"var": "x", "op": "in", "value": ["a","b"]}` | `x in ["a","b"]` |
| not_in | `{"var": "x", "op": "not_in", "value": ["a"]}` | `x not in ["a"]` |
| contains | `{"var": "arr", "op": "contains", "value": "x"}` | `"x" in arr` (list), `"x" in str` (string) |
| exists | `{"var": "x", "op": "exists"}` | `x` is truthy (not None/empty/0/False) |
| present | `{"var": "x", "op": "present"}` | key exists (value can be falsy) |
| not_exists | `{"var": "x", "op": "not_exists"}` | `x` is falsy or missing |
| not_empty | `{"queue": "q", "op": "not_empty"}` | `len(q) > 0` |
| empty | `{"queue": "q", "op": "empty"}` | `len(q) == 0` |
| mod | `{"meta": "turn", "op": "mod", "value": 5, "result": 0}` | `turn % 5 == 0` |

**Notes:**
- `exists` tests **truthiness**: `None`, `""`, `[]`, `{}`, `0`, `False` are all "not exists"
- `present` tests **key presence only**: value can be falsy and still pass (e.g., `flag=0` passes)
- `contains` behavior: lists check membership, strings check substring, dicts check key presence
- Condition evaluation **never throws**: type mismatches return `False`

---

## Appendix D: Insight Extensibility via Metadata

### D.1 Philosophy

The `InsightType` enum provides **semantic categories** that the framework understands:

```python
class InsightType(str, Enum):
    SUGGESTION = "suggestion"   # Passive advice
    WARNING = "warning"         # Urgent negative
    OPPORTUNITY = "opportunity" # Urgent positive  
    FACT = "fact"              # Contextual information
    PRAISE = "praise"          # Positive reinforcement
    ERROR = "error"            # System issues
```

**These types are intentionally stable.** They represent universal insight categories that apply across all domains.

For **domain-specific categorization**, use the `metadata` field.

### D.2 The Metadata Extension Pattern

Every `AgentInsight` has a `metadata: Dict[str, Any]` field for arbitrary extensions:

```python
class AgentInsight(BaseModel):
    agent_id: str
    agent_name: str
    type: InsightType           # Framework category
    content: str
    confidence: float
    metadata: Dict[str, Any]    # Domain-specific extensions
```

### D.3 Recommended Metadata Fields

| Field | Type | Description |
|-------|------|-------------|
| `category` | string | Domain-specific category (e.g., "objection", "buying_signal") |
| `subcategory` | string | Further refinement (e.g., "price_objection", "timeline_objection") |
| `severity` | string | "low", "medium", "high", "critical" |
| `zone` | string | UI zone hint (e.g., "A", "B", "C") |
| `color` | string | UI color hint (e.g., "red", "yellow", "green") |
| `action_type` | string | Suggested action category |
| `suggested_response` | string | Script or talking point |
| `related_fact` | string | Reference to a Blackboard fact |
| `expires_at` | float | Timestamp when insight becomes stale |

### D.4 Examples by Domain

#### Sales Coaching

```json
{
  "type": "warning",
  "content": "Customer raised a price objection. Focus on value, not cost.",
  "confidence": 0.92,
  "metadata": {
    "category": "objection",
    "subcategory": "price",
    "severity": "high",
    "suggested_response": "I understand budget is important. Let me show you the ROI our customers typically see...",
    "zone": "A",
    "color": "orange"
  }
}
```

```json
{
  "type": "opportunity",
  "content": "Buying signal detected! Customer asked about implementation timeline.",
  "confidence": 0.88,
  "metadata": {
    "category": "buying_signal",
    "subcategory": "timeline_inquiry",
    "severity": "high",
    "suggested_response": "Great question! We can typically have you up and running in 2-3 weeks.",
    "zone": "A",
    "color": "green"
  }
}
```

#### Customer Support

```json
{
  "type": "warning",
  "content": "Customer frustration increasing. Consider empathy statement.",
  "confidence": 0.85,
  "metadata": {
    "category": "escalation_risk",
    "sentiment_score": -0.7,
    "suggested_response": "I completely understand how frustrating this must be. Let me personally make sure we resolve this for you.",
    "escalation_threshold": 0.8
  }
}
```

#### Interview Coaching

```json
{
  "type": "suggestion",
  "content": "Good answer, but consider adding a specific metric or outcome.",
  "confidence": 0.78,
  "metadata": {
    "category": "answer_improvement",
    "framework": "STAR",
    "missing_element": "Result with metrics",
    "example": "...which resulted in a 25% increase in customer retention."
  }
}
```

### D.5 Host/UI Handling

The host application reads `metadata` for custom rendering:

```python
def render_insight(insight: AgentInsight) -> UICard:
    # Base styling from framework type
    base_style = get_style_for_type(insight.type)
    
    # Override with domain-specific metadata
    if insight.metadata.get("color"):
        base_style.color = insight.metadata["color"]
    
    if insight.metadata.get("zone"):
        base_style.zone = insight.metadata["zone"]
    
    # Add suggested response if present
    suggested = insight.metadata.get("suggested_response")
    
    return UICard(
        content=insight.content,
        style=base_style,
        suggested_response=suggested,
        category=insight.metadata.get("category"),
    )
```

### D.6 Schema Support

Output schemas can map LLM response fields to metadata:

```json
{
  "instruction": "Return JSON with insight details...",
  "mapping": {
    "content_field": "message",
    "type_field": "type",
    "metadata_field": "metadata"
  }
}
```

Or extract specific fields into metadata:

```json
{
  "mapping": {
    "content_field": "message",
    "type_field": "type",
    "metadata_fields": {
      "category": "category",
      "severity": "severity",
      "suggested_response": "script"
    }
  }
}
```

---

## Appendix E: RAG Integration

### E.1 v2.0 RAG Support

RAG (Retrieval-Augmented Generation) support is **preserved at v1.0 level**:

```python
class AgentContext(BaseModel):
    # ... other fields ...
    rag_docs: List[str] = Field(default_factory=list)
```

### E.2 How It Works

1. **Host retrieves documents** (using any retrieval system)
2. **Host passes documents** in `AgentContext.rag_docs`
3. **Framework injects** documents into agent prompts
4. **Agent uses** retrieved context in evaluation

### E.3 Current Injection (DynamicAgent)

```python
# In DynamicAgent.evaluate()
rag_section = ""
if context.rag_docs:
    rag_text = "\n---\n".join(context.rag_docs)
    rag_section = f"\n[RELEVANT KNOWLEDGE/DOCS]\n{rag_text}\n"
```

### E.4 Future Enhancements (v2.1+)

Structured RAG documents are deferred to v2.1+:

```python
# NOT IN v2.0 - Future consideration
class RAGDocument(BaseModel):
    content: str
    source: Optional[str] = None
    title: Optional[str] = None
    relevance_score: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

For v2.0, use the existing `rag_docs: List[str]` interface. If you need metadata, encode it in the string or handle it in the host layer.

---

**End of Specification**

*Document Version: 2.0.3-final*  
*Last Updated: January 27, 2026*  
*Total Estimated Implementation: ~23.5 hours (Tier 1)*  
*Review Status: Production-ready after P0/P1/P2 review passes*  
*v2.0.3 Changes: Fixed present operator, aligned examples with v2 patterns, clarified BaseAgent/Engine split, added invalid JSON handling, canonical queue pattern*
