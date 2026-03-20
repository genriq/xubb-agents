# Xubb Agents Framework - Technical Specification

**Version:** 2.0  
**Status:** Production-Ready  
**Scope:** `xubb_agents` Library  
**Compatibility:** 100% backward compatible with v1.0 agents

---

## 1. Executive Summary

The **Xubb Agents Framework** is a standalone, event-driven Python library designed to power real-time conversational intelligence. It provides the infrastructure for creating, managing, and executing autonomous AI agents that "listen" to a conversation and intervene with context-aware insights.

It is designed to be **consumed** by host applications (like `xubb_server`) but maintains strict decoupling, ensuring it can be used in any Python-based conversational system (e.g., a CLI tool, a desktop app, or a web service).

### What's New in v2.0

| Feature | v1.0 | v2.0 |
|---------|------|------|
| State management | Flat dictionary | Structured Blackboard |
| Agent coordination | Parallel only | Event-driven pub/sub |
| Trigger conditions | None | Blackboard-aware preconditions |
| Execution phases | Single pass | Multi-phase (normal → event-triggered) |
| Data containers | Unstructured | Variables, Events, Queues, Facts, Memory |
| Response caching | Hash-based LLM cache | **Removed** (cooldowns + conditions are better) |

---

## 2. Architectural Principles

1.  **Event-Driven Execution:** Agents do not run continuously. They are dormant until triggered by specific events (Turn completion, Keyword detection, Silence, Timer, or Events from other agents).
2.  **Stateless Execution (mostly):** Each evaluation is fresh, provided with a `Context` object containing transcript history and Blackboard state. Agents return a `Response` object.
3.  **Non-Blocking Concurrency:** All I/O (LLM calls) is asynchronous (`asyncio`). Multiple agents evaluate in parallel without blocking the main audio/transcript loop.
4.  **Graceful Degradation:** Failures in individual agents (LLM errors, logic bugs) are caught, logged, and isolated, ensuring the host application remains stable.
5.  **Blackboard Snapshot Semantics:** During a phase, all agents evaluate against the **same immutable snapshot** of the Blackboard. State updates are merged only after all agents in the phase complete.

---

## 3. Core Components

### 3.1 Agent Engine (`core/engine.py`)

The central orchestrator.

**Responsibilities:**

| Responsibility | Description |
|----------------|-------------|
| **Registry** | Maintains the list of active agents |
| **Routing** | Determines which agents run based on trigger type |
| **Condition Evaluation** | Checks trigger conditions before running agents |
| **Blackboard Management** | Manages structured state (in-memory for session lifetime) |
| **Event Dispatch** | Collects emitted events, triggers subscribers |
| **Multi-Phase Execution** | Runs normal agents (Phase 1), then event-triggered agents (Phase 2) |
| **Response Aggregation** | Merges insights, applies state updates by priority with deterministic ordering |
| **Observability** | Emits lifecycle events to callbacks |

**Note:** Response caching was removed in v2.0. Cooldowns and trigger conditions provide more correct mechanisms for preventing unnecessary LLM calls.

### 3.2 Base Agent (`core/agent.py`)

The abstract base class for all intelligence units.

**Lifecycle:**
1.  `__init__`: Configure triggers, cooldowns, conditions
2.  `process()`: Template method — enforces **cooldown only** (routing is engine's job)
3.  `evaluate()`: Abstract method — the actual "Brain" logic (usually an LLM call)

**Responsibility Split (Engine vs Agent):**

| Responsibility | Owner | Notes |
|----------------|-------|-------|
| Trigger type routing | **Engine** | Determines which agents match the trigger type |
| Condition evaluation | **Engine** | Evaluates trigger_conditions before calling agent |
| Cooldown enforcement | **Agent** | Agent's `process()` checks its own cooldown timer |
| Error handling | **Agent** | Returns `InsightType.ERROR` instead of propagating exceptions |

**Note:** `BaseAgent.process()` does **not** re-check trigger type or conditions — that would duplicate engine logic and risk disagreements.

### 3.3 Blackboard (`core/blackboard.py`)

Structured shared state with typed containers. **In-memory only**; persistence is host responsibility.

```python
class Blackboard:
    events: List[Event]                  # Transient signals (structured)
    variables: Dict[str, Any]            # Session-scoped key-value
    queues: Dict[str, List[Any]]         # Ordered lists (FIFO)
    facts: List[Fact]                    # Extracted knowledge
    memory: Dict[str, Dict[str, Any]]    # Agent-private state
```

**Container Semantics:**

| Container | Semantics | Lifetime | Operations |
|-----------|-----------|----------|------------|
| **Events** | "Something happened" (structured with payload) | Consumed after `process_turn()` | emit, subscribe |
| **Variables** | "Current state is X" | Session | get, set, delete |
| **Queues** | "Ordered work items" | Session | push, pop, peek, clear |
| **Facts** | "Extracted knowledge" (keyed, deduplicated) | Session | add, query, dedupe by (type,key) |
| **Memory** | "Agent's scratchpad" | Session | get, set |

**Reserved Variable Namespace:**
- `sys.*` — Reserved for engine-maintained state (e.g., `sys.turn_count`)
- User variables should avoid the `sys.` prefix

### 3.4 Condition Evaluator (`core/conditions.py`)

Evaluates trigger conditions against Blackboard state.

```python
class ConditionEvaluator:
    def evaluate(self, conditions: dict, blackboard: Blackboard, 
                 meta: dict, agent_id: str) -> bool
    def _evaluate_rule(self, rule: dict, blackboard: Blackboard, 
                       meta: dict, agent_id: str) -> bool
```

**Supported Operators:**

| Operator | Description | Example |
|----------|-------------|---------|
| `eq` | Equals | `phase == "negotiation"` |
| `neq` | Not equals | `phase != "closed"` |
| `gt` / `gte` | Greater than (or equal) | `turn_count > 5` |
| `lt` / `lte` | Less than (or equal) | `risk_score < 3` |
| `in` | Value in list | `phase in ["negotiation", "closing"]` |
| `not_in` | Value not in list | `phase not_in ["closed", "lost"]` |
| `contains` | List/string contains value | `topics contains "pricing"` |
| `exists` | Key is truthy | `budget exists` |
| `present` | Key exists regardless of value | `flag present` |
| `not_exists` | Key is falsy or missing | `objection not_exists` |
| `not_empty` | Collection has items | `pending_questions not_empty` |
| `empty` | Collection is empty | `action_items empty` |
| `mod` | Modulo operation | `turn_count % 5 == 0` |

**Condition Evaluation Safety:** Condition evaluation **never raises exceptions**. If a comparison fails due to type mismatch or invalid operation, the condition evaluates to `False`.

### 3.5 Trigger System

Agents define *when* they want to wake up via `AgentConfig`:

| Type | When Fired | Use Case |
|------|------------|----------|
| `TURN_BASED` | Host calls `process_turn()` | After speech segment completes |
| `KEYWORD` | Keyword detected in transcript | Immediate reaction to specific terms |
| `SILENCE` | Silence duration exceeds threshold | Dead air intervention |
| `INTERVAL` | Time-based periodic check | Background monitoring |
| `EVENT` | Another agent emits a Blackboard event | Agent coordination |

**KEYWORD Trigger Note:** The engine does **not** automatically scan transcript text for keywords. Keyword detection is **host responsibility**. The engine provides `check_keyword_triggers(text)` as a helper utility.

### 3.6 LLM Client (`core/llm.py`)

A thin wrapper around `AsyncOpenAI`.

- **Abstraction:** Centralizes API key management and client initialization.
- **JSON Enforcement:** Enforces `response_format={"type": "json_object"}` to ensure agents return structured data.
- **Model Agnostic:** Works with any OpenAI-compatible endpoint.

---

## 4. Data Models (`core/models.py`)

### 4.1 AgentContext

The input payload delivered to an agent during execution.

```python
class AgentContext(BaseModel):
    session_id: str
    recent_segments: List[TranscriptSegment]
    
    # State (v1 compatibility)
    shared_state: Dict[str, Any] = {}
    
    # Blackboard (v2) — structured state
    blackboard: Optional[Blackboard] = None
    
    # Trigger information (set by engine)
    trigger_type: TriggerType = TriggerType.TURN_BASED
    trigger_metadata: Dict[str, Any] = {}
    
    # Context enrichment
    rag_docs: List[str] = []
    user_context: Optional[str] = None
    language_directive: Optional[str] = None
    
    # Execution metadata (read-only, set by engine)
    turn_count: int = 0
    phase: int = 1  # Which execution phase (1 = normal, 2 = event-triggered)
```

### 4.2 AgentResponse

The output payload returned by an agent.

```python
class AgentResponse(BaseModel):
    # Core output
    insights: List[AgentInsight] = []
    
    # Blackboard updates (v2)
    events: List[Event] = []              # Structured events
    variable_updates: Dict[str, Any] = {} # Session variables
    queue_pushes: Dict[str, List[Any]] = {}
    facts: List[Fact] = []
    memory_updates: Dict[str, Any] = {}
    
    # Legacy compatibility (v1)
    state_updates: Dict[str, Any] = {}
    
    # Sidecar data
    data: Dict[str, Any] = {}
    debug_info: Dict[str, Any] = {}
```

### 4.3 AgentInsight

```python
class AgentInsight(BaseModel):
    agent_id: str
    agent_name: str
    type: InsightType
    content: str
    confidence: float = 1.0
    expiry: int = 15  # Seconds to display
    action_label: Optional[str] = None
    metadata: Dict[str, Any] = {}
```

**Insight Types:**
- `SUGGESTION`: Passive advice (Zone C)
- `WARNING`: Urgent negative alert (Zone A)
- `OPPORTUNITY`: Urgent positive alert (Zone A)
- `FACT`: Contextual information (Zone C)
- `PRAISE`: Positive reinforcement
- `ERROR`: System issues

### 4.4 Event (NEW in v2.0)

```python
class Event(BaseModel):
    name: str                           # Event name: "question_detected"
    payload: Dict[str, Any] = {}        # Event data
    source_agent: str                   # Which agent emitted it
    timestamp: float                    # When it was emitted (session-relative)
    id: Optional[str] = None            # Optional unique ID for tracing
```

### 4.5 Fact (NEW in v2.0)

```python
class Fact(BaseModel):
    type: str                  # Category: "budget", "timeline", "contact"
    key: Optional[str] = None  # Instance key: "budget.primary", "stakeholder.cfo"
    value: Any                 # The extracted value
    confidence: float = 1.0    # Extraction confidence
    source_agent: str          # Which agent extracted it
    timestamp: float           # When it was extracted (session-relative)
```

**Deduplication:** Facts are deduplicated by `(type, key)`. When duplicates exist: higher agent priority wins; if equal priority, higher confidence wins; if still equal, later registration order wins.

### 4.6 TranscriptSegment

```python
class TranscriptSegment(BaseModel):
    speaker: str       # Who spoke? Any string
    text: str          # The text content
    timestamp: float   # Seconds since session start (session-relative)
    is_final: bool = True  # Is this segment complete?
```

---

## 5. Execution Flow

### 5.1 Multi-Phase Execution

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
└──────────────────────────────┬──────────────────────────────────┘
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

### 5.2 Agent Eligibility Check

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

### 5.3 State Update Priority (Merge Ordering)

Updates are applied in **ascending priority order** (low → high) so that **higher-priority agents write last and therefore win** (last-write-wins semantics).

```python
# Agent A (priority=5): variable_updates={"phase": "closing"}
# Agent B (priority=10): variable_updates={"phase": "negotiation"}
# Result: phase = "negotiation" (Agent B wins)
```

### 5.4 Phase Depth Limit

To prevent infinite event cascades:
- **Maximum phases:** 2 (configurable)
- Phase 2 agents **cannot** trigger Phase 3
- Events emitted in Phase 2 are recorded for telemetry but not dispatched
- All events are cleared after `process_turn()` completes

### 5.5 Agent Failure Atomicity

Agent execution is **atomic** with respect to state updates:
- If an agent errors during evaluation, **none** of its state updates are applied
- The agent is isolated from the system state
- An `ERROR` insight may be emitted instead
- Other agents continue normally

---

## 6. Dynamic Agent Execution Flow (`library/dynamic.py`)

The `DynamicAgent` is the primary implementation used for user-defined agents.

### 6.1 Execution Lifecycle

1.  **Memory Loading:**
    - Retrieves persistent memory from `blackboard.memory[agent_id]`
    - Falls back to `shared_state["memory_{agent_id}"]` for v1.0 compatibility

2.  **Context Construction:**
    - Slices transcript based on `context_turns`
    - Injects `user_context` (User Persona) — **only if `include_context: true`**
    - Injects `language_directive` (Language Constraints) — always injected
    - Injects RAG documents if present — **only if `include_context: true`**
    - Injects Trigger Metadata
    - Injects Blackboard state for Jinja2 templating

    > **Note:** When `include_context` is `false` (default: `true`), the `user_context` and `rag_docs` sections are omitted from the system prompt. This saves tokens for agents that don't need user profile or document context (e.g., widget trackers). The host still provides these fields in `AgentContext` — the gating happens at prompt composition time inside `DynamicAgent.evaluate()`.

3.  **Prompt Templating (Jinja2):**
    ```python
    rendered_prompt = template.render(
        # v1.0 variables (preserved)
        state=context.shared_state,
        memory=self.private_state,
        context=context,
        user_context=context.user_context,
        
        # v2.0 variables (new)
        blackboard=context.blackboard,
        agent_id=self.config.id,
    )
    ```

4.  **LLM Call:**
    - Sends rendered prompt with JSON enforcement
    - Parses response according to `output_format` schema

5.  **Response Processing:**
    - Extracts insights, events, variable_updates, queue_pushes, facts, memory_updates
    - Maps v1.0 `state_updates` to `variable_updates` for compatibility

6.  **State Persistence:**
    - Updates `private_state` from `memory_updates`
    - Engine merges all updates into Blackboard

### 6.2 Output Schemas

Located in `library/schemas/`:

- **`default`**: Standard flat schema (`has_insight`, `content`, `type`)
- **`v2_raw`**: Structured schema with full v2.0 fields
- **`widget_control`**: Maps `ui_actions` to `response.data` sidecar
- **Custom**: Create `library/schemas/my_schema.json` for custom formats

---

## 7. Observability & Debugging

### 7.1 Callback System (`core/callbacks.py`)

Consumers can register handlers to receive real-time events:

```python
class AgentCallbackHandler(ABC):
    async def on_turn_start(self, context: AgentContext) -> None
    async def on_phase_start(self, phase: int, agents: List[str]) -> None
    async def on_agent_start(self, agent_name: str, context: AgentContext) -> None
    async def on_agent_finish(self, agent_name: str, response: AgentResponse, 
                              duration: float) -> None
    async def on_agent_skipped(self, agent_name: str, reason: str) -> None
    async def on_agent_error(self, agent_name: str, error: Exception) -> None
    async def on_phase_end(self, phase: int, events_emitted: List[str]) -> None
    async def on_turn_end(self, response: AgentResponse, duration: float) -> None
```

### 7.2 Structured Tracing (`utils/tracing.py`)

The `StructuredLogTracer` generates comprehensive "MRI Scans" of every turn:

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
      "agents_eligible": ["sales_coach", "question_extractor"],
      "agents_skipped": [
        {"agent": "escalation_monitor", "reason": "conditions_not_met"}
      ],
      "agents_run": [
        {
          "agent": "question_extractor",
          "duration_ms": 450,
          "insights": 0,
          "events_emitted": ["question_detected"],
          "variable_updates": {}
        }
      ],
      "events_collected": ["question_detected"]
    },
    {
      "phase": 2,
      "trigger_events": ["question_detected"],
      "agents_run": [
        {
          "agent": "question_responder",
          "duration_ms": 890,
          "insights": 1
        }
      ]
    }
  ],
  
  "blackboard_final": {
    "variables": {"phase": "negotiation", "sentiment": 0.65},
    "queues": {"pending_questions": [...]},
    "facts_count": 3,
    "events": []
  },
  
  "performance": {
    "total_duration_ms": 1660,
    "phase_1_duration_ms": 770,
    "phase_2_duration_ms": 890,
    "llm_calls": 3
  }
}
```

### 7.3 Timestamp Conventions

| Context | Format | Notes |
|---------|--------|-------|
| Model timestamps | Seconds since session start | Float, session-relative |
| Trace timestamps | ISO 8601 wall clock | e.g., `"2026-01-27T10:30:00Z"` |
| Duration fields | Milliseconds | Integer, e.g., `duration_ms: 450` |

---

## 8. Directory Structure

```
xubb_agents/
├── core/
│   ├── __init__.py
│   ├── agent.py           # BaseAgent, AgentConfig
│   ├── engine.py          # AgentEngine (orchestrator)
│   ├── blackboard.py      # Structured Blackboard
│   ├── conditions.py      # Trigger condition evaluator
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
│   └── tracing.py         # Structured logging
├── __init__.py
├── README.md
├── technical_spec_agents.md    # This document
├── prompt_engineering_guide.md # Prompt writing guide
└── SPEC_V2.md                  # Full v2.0 specification
```

---

## 9. Integration Guide (For Consumers)

### 9.1 Basic Integration

```python
from xubb_agents import AgentEngine, AgentContext, TriggerType, Blackboard
from xubb_agents.library import DynamicAgent

# Initialize Engine
engine = AgentEngine(api_key="...")

# Register Agents
for config in load_agents_from_db():
    engine.register_agent(DynamicAgent(config))

# Session State
session = {
    "id": "session_123",
    "blackboard": Blackboard(),
    "turn_count": 0,
    "segments": []
}

# Process Turn
async def on_transcript(segment):
    session["segments"].append(segment)
    session["turn_count"] += 1
    
    context = AgentContext(
        session_id=session["id"],
        recent_segments=session["segments"][-100:],
        blackboard=session["blackboard"],
        turn_count=session["turn_count"]
    )
    
    response = await engine.process_turn(
        context, 
        trigger_type=TriggerType.TURN_BASED
    )
    
    for insight in response.insights:
        await send_to_ui(insight)
```

### 9.2 Keyword Handling

```python
# Check keywords (host responsibility)
matches = engine.check_keyword_triggers(text)
allowed_ids = [agent.config.id for agent, kw in matches]

# Trigger keyword agents
response = await engine.process_turn(
    context,
    allowed_agent_ids=allowed_ids,
    trigger_type=TriggerType.KEYWORD
)
```

### 9.3 Handling Events

Event-triggered agents run automatically in Phase 2 when other agents emit events. No host intervention required.

---

## 10. Backward Compatibility (v1.0 Migration)

### 10.1 Compatibility Guarantees

| v1.0 Pattern | v2.0 Equivalent | Auto-Mapped? |
|--------------|-----------------|--------------|
| `context.shared_state["key"]` | `context.blackboard.variables["key"]` | ✅ Yes |
| `response.state_updates` | `response.variable_updates` | ✅ Yes |
| `state_updates["memory_X"]` | `blackboard.memory["X"]` | ✅ Yes |
| `{{ state.key }}` in prompts | `{{ blackboard.variables.key }}` | ✅ Both work |
| All v1.0 trigger types | Same + new EVENT type | ✅ Yes |

### 10.2 Migration Path

1. **No immediate changes required** — v1.0 agents work unchanged
2. **Gradual adoption:**
   - Replace `state_updates` with `variable_updates`
   - Add `trigger_conditions` to reduce LLM calls
   - Add `events` emission for agent coordination
3. **Full migration:**
   - Use `facts` for extracted knowledge
   - Use `queues` for work items
   - Use `blackboard.*` in templates

---

## 11. Current Limitations

1. **Local LLM Support:** The `LLMClient` is for OpenAI-compatible APIs. Local model loading not yet implemented.
2. **Session Persistence:** Framework maintains in-memory Blackboard only. Host responsible for durable persistence.
3. **Phase Depth:** Maximum 2 phases per turn (no event cascades).
4. **Streaming:** Not yet supported. Planned for v2.1+.

---

## 12. Future Considerations (v2.1+)

| Feature | Description | Complexity |
|---------|-------------|------------|
| **Tool/Function Calling** | Agents can call external APIs | High |
| **Streaming Responses** | Show insights as agents complete | Medium |
| **Session Persistence** | Built-in persistence layer | Medium |
| **Structured RAG** | `RAGDocument` model with metadata | Low |
| **MCP Integration** | Model Context Protocol support | High |
