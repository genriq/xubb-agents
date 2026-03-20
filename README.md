# Xubb Agents Framework

**A standalone Python library for real-time conversational AI agents.**

**Version:** 2.1.1
**Status:** Production-Ready

> **Note**: This is a **separate product/project** that provides the agent framework. It is consumed by `xubb_server` and other applications that need intelligent conversation agents.

## Installation

```bash
# Install from local development (in xubb_v6 root)
cd xubb_agents
pip install -e .

# Or install from PyPI (when published)
pip install xubb-agents
```

## Usage in Other Projects

```python
from xubb_agents import AgentEngine, DynamicAgent, AgentContext, Blackboard, TriggerType

# Initialize engine
engine = AgentEngine(api_key="your-openai-key")

# Load agent from config
agent = DynamicAgent(config_dict)
engine.register_agent(agent)

# Create session with Blackboard
blackboard = Blackboard()

# Process conversation
context = AgentContext(
    session_id="session_123",
    recent_segments=[...],
    blackboard=blackboard,
    turn_count=1
)
response = await engine.process_turn(context, trigger_type=TriggerType.TURN_BASED)
```

## What's New in v2.0

| Feature | v1.0 | v2.0 |
|---------|------|------|
| State management | Flat dictionary | Structured Blackboard |
| Agent coordination | Parallel only | Event-driven pub/sub |
| Trigger conditions | None | Blackboard-aware preconditions |
| Execution phases | Single pass | Multi-phase (normal → event-triggered) |
| Data containers | Unstructured | Variables, Events, Queues, Facts, Memory |
| Response caching | Hash-based LLM cache | **Removed** (cooldowns + conditions are better) |

## What's New in v2.1

v2.1 is a **hardening release** — no new features, only bug fixes and production-grade improvements:

| Change | Impact |
|--------|--------|
| Jinja2 templates now sandboxed (`SandboxedEnvironment`) | SSTI vulnerability eliminated |
| `source_agent_id` field on `AgentResponse` | Reliable agent identity (no more insight-based inference) |
| `get_memory()` returns deep copy | Snapshot isolation enforced |
| `to_dict()` returns deep copies | No mutable reference leaks |
| Callbacks fire exactly once per agent | Previously fired 2x (engine + agent) |
| Cooldown enforced after errors | Prevents runaway retries on persistent failures |
| `on_phase_start`, `on_phase_end`, `on_agent_skipped` callbacks added | Previously crashed with `AttributeError` |
| `AgentCallbackHandler` is no longer `ABC` | Subclasses don't need to implement anything |
| `sys.*` write protection on Blackboard | Warns on non-engine writes to reserved keys |

> **See [SPEC_V2_1_HARDENING.md](SPEC_V2_1_HARDENING.md) for full details.**

## What's New in v2.1.1

v2.1.1 is a **bugfix release** — 4 bug fixes, 3 defense-in-depth improvements, and 1 test correction:

| Change | Type | Impact |
|--------|------|--------|
| `get_event_subscribers()` now validates `TriggerType.EVENT` | Bug fix | Agents with `subscribed_events` but missing `EVENT` trigger type are excluded with a warning |
| `_sync_state_to_legacy()` runs before Phase 2 | Bug fix | v1 agents in Phase 2 now see correct `shared_state` |
| `memory_updates_by_agent` field on `AgentResponse` | Bug fix | Per-agent keyed memory available on aggregated responses (additive — `memory_updates` unchanged) |
| `process_turn` wrapped for `on_chain_error` | Bug fix | `on_chain_error` callback now fires on unhandled exceptions |
| Prompt whitespace elimination in `DynamicAgent` | Defense | Eliminates blank sections when optional context is absent |
| Class-level `SandboxedEnvironment` in `DynamicAgent` | Defense | Single Jinja2 env instance instead of per-call allocation |
| v2 fields added to `StructuredLogTracer` | Defense | Traces now include events, facts, queues, variables, memory |
| `DynamicAgent` auto-adds `TriggerType.EVENT` | Convenience | Agents with `subscribed_events` get `EVENT` trigger type automatically |

> **See [SPEC_V2_1_1_BUGFIX.md](SPEC_V2_1_1_BUGFIX.md) for full details.**

## Architecture

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
│  │  - data                - debug_info   - memory_updates_by_agent │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

- **AgentEngine**: Orchestrates agent execution, manages Blackboard, handles multi-phase execution
- **BaseAgent**: Abstract base class defining agent interface
- **DynamicAgent**: Configurable agent loaded from prompts/database
- **Blackboard**: Structured shared state (Variables, Events, Queues, Facts, Memory)
- **ConditionEvaluator**: Evaluates trigger conditions against Blackboard state
- **LLMClient**: Isolated OpenAI client for agent LLM calls

> **For detailed implementation and data models, see [technical_spec_agents.md](technical_spec_agents.md).**
> **For prompt writing best practices, see [prompt_engineering_guide.md](prompt_engineering_guide.md).**

---

## Table of Contents

1. [Core Concepts](#core-concepts)
2. [Blackboard Architecture](#blackboard-architecture)
3. [Trigger System](#trigger-system)
4. [Agent Configuration](#agent-configuration)
5. [Agent Communication](#agent-communication)
6. [Usage Guide](#usage-guide)
7. [API Reference](#api-reference)

---

## Core Concepts

### 1. Agent

An agent is a self-contained unit of intelligence that:
- Observes conversation context
- Evaluates whether to provide insight
- Returns structured insights (suggestions, warnings, facts)
- Updates Blackboard state for other agents
- Emits events to trigger other agents

### 2. Blackboard

The structured shared workspace where agents read and write information. Contains five containers:

| Container | Purpose | Lifetime |
|-----------|---------|----------|
| **Variables** | Session-scoped key-value state | Session |
| **Events** | Transient signals to trigger other agents | Cleared after turn |
| **Queues** | Ordered work items (FIFO) | Session |
| **Facts** | Extracted knowledge with confidence | Session |
| **Memory** | Agent-private scratchpad | Session |

### 3. Trigger

A trigger is an event that causes an agent to evaluate. Six types:

| Type | Description | Use Case |
|------|-------------|----------|
| **TURN_BASED** | After a speaker finishes a turn | General conversation analysis |
| **KEYWORD** | Keyword detected in transcript | Price objections, compliance alerts |
| **SILENCE** | Dead air threshold exceeded | Meeting facilitation |
| **INTERVAL** | Time-based periodic | Background monitoring |
| **EVENT** | Another agent emitted an event | Agent coordination |
| **FORCE** | User-triggered, bypasses cooldown and conditions | Manual intervention, debugging |

### 4. Trigger Conditions

Preconditions that must be satisfied before an agent runs. Prevents unnecessary LLM calls.

```json
{
  "trigger_conditions": {
    "mode": "all",
    "rules": [
      {"var": "phase", "op": "eq", "value": "negotiation"},
      {"fact": "budget", "op": "exists"}
    ]
  }
}
```

### 5. Insight

A piece of advice returned by an agent:

```python
{
    "agent_id": "sales-coach",
    "agent_name": "Sales Coach",
    "type": "warning",  # suggestion, warning, opportunity, fact, praise, error
    "content": "Price objection detected. Focus on value.",
    "confidence": 0.9,
    "expiry": 15,  # seconds
    "action_label": "Handle Objection",  # Optional button text
    "metadata": {"zone": "A", "color": "red"}  # Optional UI hints
}
```

**Insight Types:**
- `SUGGESTION`: Passive advice (Zone C)
- `WARNING`: Urgent negative alert (Zone A)
- `OPPORTUNITY`: Urgent positive alert (Zone A)
- `FACT`: Contextual information (Zone C)
- `PRAISE`: Positive reinforcement
- `ERROR`: System issues

---

## Blackboard Architecture

### Container Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            BLACKBOARD                                    │
├─────────────────────────────────────────────────────────────────────────┤
│  EVENTS (transient, structured)                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ Event(name="question_detected", payload={"q": "What's price?"}) │    │
│  └─────────────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────────────┤
│  VARIABLES (session-scoped)                                              │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ phase: "negotiation", sentiment: 0.7, turn_count: 15            │    │
│  └─────────────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────────────┤
│  QUEUES (ordered lists)                                                  │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ pending_questions: ["What's the price?", "When can you start?"] │    │
│  └─────────────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────────────┤
│  FACTS (extracted knowledge)                                             │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ {type: "budget", value: "$50,000", confidence: 0.9}             │    │
│  └─────────────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────────────┤
│  MEMORY (agent-private)                                                  │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ question_extractor: {questions_found: 3, last_question: "..."}  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Accessing Blackboard in Templates (Jinja2)

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
My counter: {{ blackboard.memory[agent_id].counter }}
```

---

## Trigger System

### Turn-Based Triggers (Default)

Agents run after a speaker finishes a turn.

```json
{
  "trigger_config": {
    "mode": "turn_based",
    "cooldown": 10
  }
}
```

### Keyword-Based Triggers

Agents run immediately when a keyword is detected.

```json
{
  "trigger_config": {
    "mode": "keyword",
    "keywords": ["price", "discount", "budget"],
    "cooldown": 5
  }
}
```

**Note:** Keyword detection is host responsibility. The engine provides `check_keyword_triggers(text)` as a helper.

### Silence-Based Triggers

Agents run after a period of silence.

```json
{
  "trigger_config": {
    "mode": "silence",
    "silence_threshold": 30,
    "cooldown": 10
  }
}
```

### Interval-Based Triggers

Agents run on a periodic timer.

```json
{
  "trigger_config": {
    "mode": "interval",
    "trigger_interval": 60,
    "cooldown": 5
  }
}
```

### Event-Based Triggers (NEW in v2.0)

Agents run when another agent emits a specific event.

```json
{
  "trigger_config": {
    "mode": "event",
    "subscribed_events": ["question_detected", "objection_raised"],
    "cooldown": 0
  }
}
```

### Trigger Conditions

Define preconditions that must be satisfied:

```json
{
  "trigger_conditions": {
    "mode": "all",
    "rules": [
      {"var": "phase", "op": "in", "value": ["negotiation", "closing"]},
      {"queue": "pending_questions", "op": "not_empty"},
      {"meta": "turn_count", "op": "gte", "value": 3}
    ]
  }
}
```

**Available Operators:** `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, `contains`, `exists`, `present`, `not_exists`, `not_empty`, `empty`, `mod`

---

## Agent Configuration

### Full Configuration Schema

```json
{
  "id": "string (unique identifier)",
  "name": "string (display name)",
  
  "trigger_config": {
    "mode": "turn_based | keyword | silence | interval | event | [array]",
    "cooldown": 15,
    "keywords": ["price", "discount"],
    "silence_threshold": 5,
    "subscribed_events": ["question_detected"]
  },
  
  "trigger_conditions": {
    "mode": "all | any",
    "rules": [
      {"var": "phase", "op": "eq", "value": "negotiation"}
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

### Configuration Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | string | auto-generated | Unique identifier |
| `name` | string | required | Display name |
| `trigger_config.mode` | string/array | "turn_based" | When to trigger |
| `trigger_config.cooldown` | int | 15 | Seconds between runs |
| `trigger_config.keywords` | array | [] | Keywords for KEYWORD trigger |
| `trigger_config.silence_threshold` | int | null | Seconds for SILENCE trigger |
| `trigger_config.subscribed_events` | array | [] | Events for EVENT trigger |
| `trigger_conditions` | object | null | Preconditions (Blackboard-aware) |
| `priority` | int | 0 | State update priority (higher wins) |
| `model_config.model` | string | "gpt-4o-mini" | LLM model |
| `model_config.context_turns` | int | 6 | Transcript segments to include |
| `text` | string | required | System prompt (Jinja2) |
| `output_format` | string | "default" | Output schema name |
| `include_context` | bool | true | Inject user profile & RAG docs into prompt. Set `false` for widget trackers and agents that don't need user/session context. Language directive always injected. |

---

## Agent Communication

### Event-Driven Coordination

**Agent A (Emitter):**
```json
{
  "has_insight": false,
  "events": [
    {"name": "question_detected", "payload": {"question": "What is pricing?", "speaker": "CUSTOMER"}}
  ]
}
```

**Agent B (Subscriber):**
```json
{
  "trigger_config": {
    "mode": "event",
    "subscribed_events": ["question_detected"]
  }
}
```

### Multi-Phase Execution

1. **Phase 1:** TURN_BASED, KEYWORD, SILENCE, INTERVAL agents run in parallel
2. **State Update:** Variables, queues, facts, memory merged (priority-ordered)
3. **Event Collection:** Events gathered from Phase 1 responses
4. **Phase 2:** EVENT-triggered agents run (if events were emitted)
5. **Cleanup:** Events cleared from Blackboard

### Priority System

Higher-priority agents can override lower-priority state updates:

```python
# Agent A (priority=5): variable_updates={"phase": "closing"}
# Agent B (priority=10): variable_updates={"phase": "negotiation"}

# Result: phase = "negotiation" (Agent B wins, higher priority)
```

Updates are applied in **ascending** priority order (low → high), so higher priority writes last and wins.

### Private Memory

Each agent maintains a private scratchpad via `memory_updates`:

```json
{
  "memory_updates": {
    "last_objection": "price",
    "objection_count": 4
  }
}
```

Access in templates: `{{ blackboard.memory[agent_id].objection_count }}`

---

## Usage Guide

### Basic Integration

```python
from xubb_agents import (
    AgentEngine, AgentContext, TriggerType, Blackboard,
    DynamicAgent, TranscriptSegment
)

# Initialize
engine = AgentEngine(api_key="sk-...")

# Load agents from config
for config in load_agents_from_db():
    engine.register_agent(DynamicAgent(config))

# Session state
session = {
    "id": "session_123",
    "blackboard": Blackboard(),
    "turn_count": 0,
    "segments": []
}

async def on_transcript_segment(segment: dict):
    """Called when speech is detected."""
    session["segments"].append(TranscriptSegment(**segment))
    session["turn_count"] += 1
    
    context = AgentContext(
        session_id=session["id"],
        recent_segments=session["segments"][-100:],
        blackboard=session["blackboard"],
        turn_count=session["turn_count"],
        user_context="Sales Director at Acme Corp"
    )
    
    response = await engine.process_turn(
        context,
        trigger_type=TriggerType.TURN_BASED
    )
    
    for insight in response.insights:
        await send_to_ui(insight)
```

### Keyword Handling

```python
async def on_keyword_detected(keyword: str, segment: dict):
    """Called when a keyword is detected."""
    matches = engine.check_keyword_triggers(segment["text"])
    allowed_ids = [agent.config.id for agent, _ in matches]
    
    context = AgentContext(
        session_id=session["id"],
        recent_segments=session["segments"][-100:],
        blackboard=session["blackboard"],
        trigger_metadata={"keyword": keyword}
    )
    
    response = await engine.process_turn(
        context,
        allowed_agent_ids=allowed_ids,
        trigger_type=TriggerType.KEYWORD
    )
```

### Creating a Custom Agent

```python
from xubb_agents.core.agent import BaseAgent, AgentConfig
from xubb_agents.core.models import AgentContext, AgentResponse, InsightType, TriggerType, Event

class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentConfig(
            name="My Agent",
            id="my-agent",
            cooldown=10,
            trigger_types=[TriggerType.TURN_BASED],
            priority=5
        ))
    
    async def evaluate(self, context: AgentContext) -> AgentResponse:
        response = AgentResponse()
        
        last_text = context.recent_segments[-1].text
        
        if "urgent" in last_text.lower():
            response.insights.append(
                self.create_insight(
                    content="Urgency detected. Escalate if needed.",
                    type=InsightType.WARNING
                )
            )
            # Emit event for other agents
            response.events.append(Event(
                name="urgency_detected",
                payload={"text": last_text},
                source_agent=self.config.id
            ))
        
        return response
```

### Enabling Debugging

```python
from xubb_agents.utils.tracing import StructuredLogTracer
from xubb_agents.core.callbacks import AgentCallbackHandler

tracer = StructuredLogTracer()
engine = AgentEngine(api_key="...", callbacks=[tracer])

# Traces include multi-phase execution details
```

### Writing Custom Callbacks

Subclass `AgentCallbackHandler` and override only the methods you need — all are no-op by default:

```python
class MyCallback(AgentCallbackHandler):
    async def on_turn_start(self, context: AgentContext) -> None: ...
    async def on_turn_end(self, response: AgentResponse, duration: float) -> None: ...
    async def on_agent_start(self, agent_name: str, context: AgentContext) -> None: ...
    async def on_agent_finish(self, agent_name: str, response: Optional[AgentResponse],
                              duration: float) -> None: ...
    async def on_agent_error(self, agent_name: str, error: Exception) -> None: ...
    async def on_agent_skipped(self, agent_name: str, reason: str) -> None: ...
    async def on_phase_start(self, phase: int, agent_names: List[str]) -> None: ...
    async def on_phase_end(self, phase: int, event_names: List[str]) -> None: ...
    async def on_chain_error(self, error: Exception) -> None: ...
```

Callback failures are non-fatal — they are logged and never abort turn processing.

---

## API Reference

### AgentEngine

```python
class AgentEngine:
    def __init__(self, api_key: str, callbacks: List[AgentCallbackHandler] = None,
                 max_phases: int = 2)
    def register_agent(self, agent: BaseAgent) -> None
    def update_api_key(self, api_key: str) -> None
    async def process_turn(
        self,
        context: AgentContext,
        allowed_agent_ids: Optional[List[str]] = None,
        trigger_type: TriggerType = TriggerType.TURN_BASED,
        trigger_metadata: Dict[str, Any] = None
    ) -> AgentResponse
    def check_keyword_triggers(
        self,
        text: str,
        allowed_agent_ids: Optional[List[str]] = None
    ) -> List[tuple]
```

### Blackboard

```python
class Blackboard(BaseModel):
    events: List[Event]
    variables: Dict[str, Any]
    queues: Dict[str, List[Any]]
    facts: List[Fact]
    memory: Dict[str, Dict[str, Any]]
    
    # Event operations
    def emit_event(self, event: Event) -> None
    def has_event(self, event_name: str) -> bool
    def count_events(self, event_name: str) -> int
    def get_events_by_name(self, event_name: str) -> List[Event]
    def clear_events(self) -> None

    # Variable operations (sys.* keys are engine-reserved)
    def set_var(self, key: str, value: Any) -> None
    def get_var(self, key: str, default: Any = None) -> Any
    def has_var(self, key: str) -> bool
    def delete_var(self, key: str) -> None

    # Queue operations
    def push_queue(self, queue_name: str, item: Any) -> None
    def push_queue_items(self, queue_name: str, items: List[Any]) -> None
    def pop_queue(self, queue_name: str) -> Optional[Any]
    def peek_queue(self, queue_name: str) -> Optional[Any]
    def queue_length(self, queue_name: str) -> int
    def has_queue(self, queue_name: str) -> bool
    def clear_queue(self, queue_name: str) -> None

    # Fact operations
    def add_fact(self, fact: Fact) -> None
    def get_fact(self, fact_type: str, key: Optional[str] = None) -> Optional[Fact]
    def get_facts_by_type(self, fact_type: str) -> List[Fact]
    def has_fact(self, fact_type: str, key: Optional[str] = None) -> bool

    # Memory operations (get_memory returns a deep copy)
    def get_memory(self, agent_id: str) -> Dict[str, Any]
    def set_memory(self, agent_id: str, data: Dict[str, Any]) -> None
    def update_memory(self, agent_id: str, updates: Dict[str, Any]) -> None
    def has_memory(self, agent_id: str) -> bool

    # Serialization
    def snapshot(self) -> Blackboard
    def to_dict(self) -> Dict[str, Any]
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Blackboard
```

### AgentContext

```python
class AgentContext(BaseModel):
    session_id: str
    recent_segments: List[TranscriptSegment]
    
    # State (v1 compatibility)
    shared_state: Dict[str, Any] = {}
    
    # Blackboard (v2)
    blackboard: Optional[Blackboard] = None
    
    # Trigger information
    trigger_type: TriggerType = TriggerType.TURN_BASED
    trigger_metadata: Dict[str, Any] = {}
    
    # Context enrichment
    rag_docs: List[str] = []
    user_context: Optional[str] = None
    language_directive: Optional[str] = None
    
    # Execution metadata
    turn_count: int = 0
    phase: int = 1

    # Role overrides (per-agent config modifications)
    agent_config_overrides: Dict[str, AgentConfigOverride] = {}
```

### AgentConfigOverride

```python
class AgentConfigOverride(BaseModel):
    cooldown_modifier: Optional[int] = None       # +N = slower, -N = faster (floor 5s)
    context_turns_modifier: Optional[int] = None   # +N = more context, -N = less
    instructions_append: Optional[str] = None      # Extra instructions appended to prompt
```

### AgentResponse

```python
class AgentResponse(BaseModel):
    # Agent identity (v2.1 — set by framework)
    source_agent_id: Optional[str] = None

    # Core output
    insights: List[AgentInsight] = Field(default_factory=list)

    # Blackboard updates (v2)
    events: List[Event] = Field(default_factory=list)
    variable_updates: Dict[str, Any] = Field(default_factory=dict)
    queue_pushes: Dict[str, List[Any]] = Field(default_factory=dict)
    facts: List[Fact] = Field(default_factory=list)
    memory_updates: Dict[str, Any] = Field(default_factory=dict)

    # Per-agent keyed memory (v2.1.1 — populated on aggregated responses from process_turn)
    memory_updates_by_agent: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    # Legacy compatibility (v1)
    state_updates: Dict[str, Any] = Field(default_factory=dict)

    # Sidecar data
    data: Dict[str, Any] = Field(default_factory=dict)
    debug_info: Dict[str, Any] = Field(default_factory=dict)
```

### AgentConfig

```python
class AgentConfig:
    def __init__(self,
        name: str,                                          # Display name (required)
        id: str = None,                                     # Unique ID (auto-generated from name)
        cooldown: int = 10,                                 # Seconds between runs
        model: str = "gpt-4o-mini",                         # LLM model
        trigger_types: List[TriggerType] = [TriggerType.TURN_BASED],
        trigger_keywords: List[str] = [],                   # For KEYWORD trigger
        silence_threshold: Optional[int] = None,            # For SILENCE trigger
        trigger_interval: Optional[int] = None,             # For INTERVAL trigger
        priority: int = 0,                                  # Merge priority (higher wins)
        output_format: str = "default",                     # Output schema name
        trigger_conditions: Optional[Dict] = None,          # Blackboard preconditions
        subscribed_events: Optional[List[str]] = None       # For EVENT trigger
    )
```

### Data Models

```python
class Event(BaseModel):
    name: str
    payload: Dict[str, Any] = {}
    source_agent: str
    timestamp: float
    id: Optional[str] = None  # Optional unique ID for tracing/deduplication

class Fact(BaseModel):
    type: str
    key: Optional[str] = None
    value: Any
    confidence: float = 1.0
    source_agent: str
    timestamp: float

class AgentInsight(BaseModel):
    agent_id: str
    agent_name: str
    type: InsightType
    content: str
    confidence: float = 1.0
    expiry: int = 15
    action_label: Optional[str] = None
    metadata: Dict[str, Any] = {}
```

---

## Best Practices

1. **Use Trigger Conditions**: Prevent unnecessary LLM calls with preconditions
2. **Emit Events**: Use events for agent coordination instead of polling state
3. **Set Appropriate Cooldowns**: 10-30 seconds typical to prevent spam
4. **Use Priority Wisely**: Higher priority for critical agents (compliance, escalation)
5. **Limit Context Window**: 6-10 turns for cost efficiency
6. **Use Facts for Knowledge**: Structured extraction with confidence scores
7. **Use Queues for Work Items**: FIFO processing of pending tasks

---

## Migration from v1.0 / v2.0

v2.1 is backward compatible. Existing agents work unchanged, with these behavioral normalizations:

- **Callback count halved**: Callbacks now fire once per agent (was 2x due to a bug). Dashboards tracking callback counts will see a 50% drop — this is correct.
- **`get_memory()` returns a copy**: Code that mutated the returned dict as a shortcut must now use `update_memory()` explicitly.
- **Jinja2 sandboxed**: Templates accessing Python internals (`__class__`, `__globals__`) will raise `SecurityError`. All documented template patterns continue to work.
- **Cooldown after errors**: Agents that fail now respect cooldown (previously retried every turn).

| v1.0 Pattern | v2.0 Equivalent | Auto-Mapped? |
|--------------|-----------------|--------------|
| `shared_state["key"]` | `blackboard.variables["key"]` | ✅ Yes |
| `state_updates` | `variable_updates` | ✅ Yes |
| `memory_{agent_id}` | `blackboard.memory[agent_id]` | ✅ Yes |
| `{{ state.key }}` | `{{ blackboard.variables.key }}` | ✅ Both work |

**Gradual Migration:**
1. Add `trigger_conditions` to reduce LLM calls
2. Add `events` for agent coordination
3. Use `facts` for extracted knowledge
4. Use `queues` for work items

---

## License

See main project license.
