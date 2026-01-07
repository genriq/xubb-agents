# Xubb Agents Framework

**A standalone Python library for real-time conversational AI agents.**

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
from xubb_agents import AgentEngine, DynamicAgent, AgentContext

# Initialize engine
engine = AgentEngine(api_key="your-openai-key")

# Load agent from config
agent = DynamicAgent(config_dict)
engine.register_agent(agent)

# Process conversation
context = AgentContext(...)
response = await engine.process_turn(context)
```

## Architecture Relationship

```
┌─────────────────┐
│  xubb_agents    │  ← Standalone library (this project)
│  (Framework)    │
└────────┬────────┘
         │ consumed by
         ▼
┌─────────────────┐
│  xubb_server    │  ← Backend service (separate project)
│  (FastAPI)      │
└─────────────────┘
```

**This library:**
- Defines agent interfaces and protocols
- Provides agent execution engine
- Manages agent lifecycle and triggers
- Handles LLM communication
- Can be used by any application (xubb_server, web apps, etc.)

**Consumers:**
- `xubb_server` - Uses this library for agent functionality
- Other applications can import and use independently

---

A lightweight, event-driven framework for real-time conversational AI agents. Designed for low-latency, high-throughput scenarios where multiple agents provide guidance during live conversations.

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Core Concepts](#core-concepts)
4. [Agent Configuration](#agent-configuration)
5. [Trigger System](#trigger-system)
6. [Agent Communication](#agent-communication)
7. [Advanced Features](#advanced-features)
8. [Performance Optimization](#performance-optimization)
9. [Usage Guide](#usage-guide)
10. [API Reference](#api-reference)

> **For a deep dive into the internal implementation and data models, see [technical_spec_agents.md](technical_spec_agents.md).**

---

## Overview

The Xubb Agents Framework enables you to create intelligent, autonomous agents that analyze conversations in real-time and provide contextual insights, warnings, and suggestions. Agents can:

- **React to events**: Turn completion, keyword detection, silence periods
- **Share state**: Coordinate with other agents via a shared blackboard
- **Remember context**: Maintain private memory across turns
- **Integrate with RAG**: Access document knowledge bases
- **Optimize performance**: Caching and batching for scale

### Key Features

- ✅ **Multiple Trigger Types**: Turn-based, keyword-based, silence-based, interval-based
- ✅ **Priority System**: Higher-priority agents can override lower-priority state updates
- ✅ **Response Caching**: Avoid redundant LLM calls for similar transcript slices
- ✅ **Request Batching**: Group agents by model for efficient API usage
- ✅ **Embedding Cache**: RAG document indexing optimization
- ✅ **Agent-to-Agent Communication**: Shared state blackboard pattern

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Xubb Server (FastAPI)                     │
│                                                               │
│  ┌──────────────┐      ┌──────────────┐                    │
│  │ SessionManager│──────│ AgentEngine  │                    │
│  │              │      │              │                    │
│  │ - Heartbeat  │      │ - Agents[]   │                    │
│  │ - Keyword    │      │ - SharedState│                    │
│  │   Matching   │      │ - Cache      │                    │
│  └──────────────┘      └──────────────┘                    │
│         │                      │                            │
│         └──────────────────────┘                            │
│                    │                                         │
│         ┌───────────┴───────────┐                          │
│         │                        │                          │
│  ┌──────▼──────┐        ┌───────▼──────┐                   │
│  │ BaseAgent   │        │ DynamicAgent │                   │
│  │             │        │              │                   │
│  │ - Config    │        │ - Prompt     │                   │
│  │ - Cooldown  │        │ - Memory     │                   │
│  │ - Priority  │        │ - RAG        │                   │
│  └─────────────┘        └──────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

- **AgentEngine**: Orchestrates agent execution, manages shared state, handles caching
- **BaseAgent**: Abstract base class defining agent interface
- **DynamicAgent**: Configurable agent loaded from prompts/database
- **SessionManager**: Triggers agents based on events (transcript, keywords, silence)
- **LLMClient**: Isolated OpenAI client for agent LLM calls

---

## Core Concepts

### 1. Agent

An agent is a self-contained unit of intelligence that:
- Observes conversation context
- Evaluates whether to provide insight
- Returns structured insights (suggestions, warnings, facts)
- Updates shared state for other agents

### 2. Trigger

A trigger is an event that causes an agent to evaluate. Four types:

- **TURN_BASED**: Agent runs after a speaker finishes a turn (default)
- **KEYWORD**: Agent runs immediately when a keyword is detected
- **SILENCE**: Agent runs after a period of silence (dead air)
- **INTERVAL**: Agent runs on a periodic timer

### 3. Insight

An insight is a piece of advice returned by an agent:

```python
{
    "agent_id": "sales-coach",
    "agent_name": "Sales Coach",
    "type": "warning",  # suggestion, warning, opportunity, fact, praise, error
    "content": "Price objection detected. Focus on value.",
    "confidence": 0.9,
    "expiry": 15,  # seconds
    "metadata": { "zone": "A", "color": "red" } # Optional UI hints
}
```

### 4. Shared State (Blackboard)

A dictionary shared across all agents. Agents can:
- **Read**: `context.shared_state.get("key")`
- **Write**: `response.state_updates = {"key": "value"}`

Higher-priority agents can override lower-priority updates.

### 5. User Context (Cognitive Frame)

Agents receive a `user_context` string containing the user's identity, goals, and expertise. This is injected into the system prompt to ground the agent in the user's reality (e.g., "You are supporting Enrique").

---

## Agent Configuration

### AgentConfig

Every agent has a configuration object:

```python
AgentConfig(
    name="Sales Coach",
    id="sales-coach",  # Unique identifier
    cooldown=15,  # Minimum seconds between runs
    model="gpt-4o-mini",  # LLM model to use
    trigger_types=[TriggerType.TURN_BASED, TriggerType.KEYWORD],
    trigger_keywords=["price", "cost", "expensive"],
    silence_threshold=30,  # Seconds of silence before triggering
    priority=10,  # Higher = more important (default: 0)
    output_format="default" # "default", "v2_raw", or custom filename (e.g. "custom1")
)
```

### Dynamic Agent (JSON/Database)

Agents can be configured via JSON:

```json
{
    "id": "sales-coach",
    "name": "Sales Coach",
    "type": "agent",
    "text": "You are a sales coach...",
    "output_format": "v2_raw",  // Selects schema from library/schemas/v2_raw.json
    "trigger_config": {
        "mode": ["turn_based", "keyword"],  // Can be string or list
        "cooldown": 15,
        "keywords": ["price", "cost"],
        "silence_threshold": 30,
        "priority": 10
    },
    "model_config": {
        "model": "gpt-4o-mini",
        "context_turns": 6
    }
}
```

### Output Schemas (12/10 Architecture)

The framework supports pluggable output schemas located in `library/schemas/`.

*   **`default`**: The standard flat schema (`has_insight`, `message`, `type`). Best for simple advisors.
*   **`v2_raw`**: Structured schema (`insight`, `state_snapshot`). Best for complex agents with metadata.
*   **`widget_control`**: The "Hands" schema. Maps `ui_actions` to `response.data` for controlling UI widgets.
*   **Custom**: Create your own `library/schemas/my_schema.json` to define custom prompt instructions and mapping logic.

---

## Trigger System

### Turn-Based Triggers (Default)

Agents run after a speaker finishes a turn (detected by VAD silence).

**Use Case**: General conversation analysis, sentiment tracking

**Configuration**:
```json
{
    "trigger_config": {
        "mode": "turn_based",
        "cooldown": 10
    }
}
```

### Keyword-Based Triggers

Agents run immediately when a keyword is detected in the transcript.

**Use Case**: Price objections, compliance alerts, competitor mentions

**Configuration**:
```json
{
    "trigger_config": {
        "mode": "keyword",
        "keywords": ["price", "discount", "budget"],
        "cooldown": 5
    }
}
```

**Behavior**:
- Triggers on partial transcripts (before turn completion)
- Case-insensitive matching
- One trigger per agent per segment

### Silence-Based Triggers (Dead Air)

Agents run after a period of silence (e.g., 30 seconds).

**Use Case**: Meeting facilitation, conversation restart suggestions

**Configuration**:
```json
{
    "trigger_config": {
        "mode": "silence",
        "silence_threshold": 30,
        "cooldown": 10
    }
}
```

**Behavior**:
- Heartbeat loop checks every 2 seconds
- Triggers once per threshold level (avoids spam)
- Passes `silence_duration` in `trigger_metadata`

### Interval-Based Triggers

Agents run on a periodic timer (e.g., every 60 seconds).

**Use Case**: Periodic summaries, health checks

**Configuration**:
```json
{
    "trigger_config": {
        "mode": "interval",
        "trigger_interval": 60,
        "cooldown": 5
    }
}
```

---

## Agent Communication

### Shared State Blackboard

Agents communicate indirectly via a shared dictionary:

```python
# Agent A writes
response.state_updates = {
    "detected_objection": "price",
    "conversation_phase": "negotiation"
}

# Agent B reads
if context.shared_state.get("detected_objection") == "price":
    # React to price objection
    insight = self.create_insight(
        content="Price objection detected. Use ROI calculator.",
        type=InsightType.SUGGESTION
    )
```

### Priority System

Higher-priority agents can override lower-priority state updates:

```python
# Compliance Agent (priority: 100)
response.state_updates = {"risk_level": "high"}

# Sales Agent (priority: 10)
response.state_updates = {"risk_level": "low"}

# Result: risk_level = "high" (Compliance wins)
```

**Priority Rules**:
- Default priority: `0`
- Higher number = higher priority
- State updates applied in priority order (descending)

### Private State (Memory)

Each agent maintains a private scratchpad:

```python
# In DynamicAgent
self.private_state = {
    "last_objection": "price",
    "objection_count": 3
}

# LLM can update via JSON response
{
    "memory_updates": {
        "objection_count": 4
    }
}
```

---

## Advanced Features

### Jinja2 Prompt Templating (14/10)

You can access shared state and memory directly in your system prompts using Jinja2 syntax:

*   **`{{ state }}`**: Access the Global Blackboard.
    *   Example: `"The current phase is {{ state.conversation_phase }}"`
*   **`{{ memory }}`**: Access the Agent's Private Memory.
    *   Example: `"You have warned the user {{ memory.warning_count }} times."`
*   **`{{ context }}`**: Access the full `AgentContext`.
*   **`{{ user_context }}`**: Access the User Persona string.

### Widget Control (Sidecar Pattern)

To build agents that control UI widgets ("Hands") instead of just speaking ("Voice"):

1.  Set `output_format: "widget_control"`.
2.  The framework will map the LLM's `ui_actions` output to the `response.data` sidecar.
3.  The Host Application (Backend) routes this data to the Frontend.

---

## Performance Optimization

### Response Caching

Agent responses are cached to avoid redundant LLM calls:

- **Cache Key**: `hash(agent_id + transcript_slice)`
- **TTL**: 5 minutes (configurable)
- **Size Limit**: 100 entries (auto-cleanup)

**Benefits**:
- Reduces API costs
- Lowers latency for similar queries
- Handles repeated conversation patterns

**Configuration**:
```python
engine = AgentEngine(
    api_key=api_key,
    enable_caching=True,
    cache_ttl=300  # seconds
)
```

### Request Batching

Agents using the same model are grouped for potential batching:

- Agents grouped by `model` (e.g., `gpt-4o-mini`)
- Future optimization: Single API call for multiple agents

**Current State**: Grouping implemented, batching pending OpenAI batch API support

### Embedding Cache (RAG)

Document embeddings are cached to avoid re-indexing:

- **Cache Key**: `hash(document_content)`
- **Behavior**: Skip indexing if document unchanged

**Implementation**:
```python
# In RAGManager
content_hash = hashlib.md5(content.encode()).hexdigest()
if cached_hash == content_hash:
    return  # Skip re-indexing
```

---

## Usage Guide

### Enabling Debugging (The Agent MRI)

To see exactly what your agents are thinking, enable the Structured Tracer:

```python
from xubb_agents.utils.tracing import StructuredLogTracer

# 1. Initialize Tracer
tracer = StructuredLogTracer()

# 2. Register with Engine
engine = AgentEngine(api_key="...", callbacks=[tracer])

# 3. Watch your logs for "TURN_TRACE: { ... }"
```

### Creating a Custom Agent

1. **Extend BaseAgent**:

```python
from xubb_agents.core.agent import BaseAgent, AgentConfig
from xubb_agents.core.models import AgentContext, AgentResponse, InsightType

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
        
        # Analyze context
        last_text = context.recent_segments[-1].text
        
        if "urgent" in last_text.lower():
            response.insights.append(
                self.create_insight(
                    content="Urgency detected. Escalate if needed.",
                    type=InsightType.WARNING
                )
            )
        
        return response
```

2. **Register Agent**:

```python
from xubb_agents import AgentEngine

engine = AgentEngine(api_key=api_key)
engine.register_agent(MyAgent())
```

### Using Dynamic Agents

1. **Create Prompt Template** (in `prompts.json`):

```json
{
    "id": "my-dynamic-agent",
    "name": "My Dynamic Agent",
    "type": "agent",
    "text": "You are a helpful assistant...",
    "trigger_config": {
        "mode": ["turn_based", "keyword"],
        "cooldown": 15,
        "keywords": ["help", "assist"],
        "priority": 5
    },
    "model_config": {
        "model": "gpt-4o-mini",
        "context_turns": 6
    }
}
```

2. **Load in Server**:

```python
# In xubb_server/core/state.py
agents = prompt_manager.get_agents()
for agent_config in agents:
    engine.register_agent(DynamicAgent(agent_config))
```

### Triggering Agents

**Turn-Based** (automatic):
```python
# In SessionManager.add_transcript_segment
await self._run_agent_check(engine, session)
```

**Keyword-Based** (automatic):
```python
# In SessionManager.add_transcript_segment
if keyword in text:
    await self._run_agent_check(
        engine, session,
        trigger_type="keyword",
        trigger_metadata={"keyword": keyword}
    )
```

**Silence-Based** (automatic):
```python
# In SessionManager._heartbeat_loop
if silence_duration >= agent.config.silence_threshold:
    await self._run_agent_check(
        engine, session,
        trigger_type="silence",
        trigger_metadata={"silence_duration": silence_duration}
    )
```

---

## API Reference

### AgentEngine

```python
class AgentEngine:
    def __init__(self, api_key: str, enable_caching: bool = True, cache_ttl: int = 300)
    def register_agent(self, agent: BaseAgent)
    async def process_turn(
        self,
        context: AgentContext,
        allowed_agent_ids: Optional[List[str]] = None,
        trigger_type: TriggerType = TriggerType.TURN_BASED,
        trigger_metadata: Dict[str, Any] = None
    ) -> AgentResponse
    def check_keyword_triggers(self, text: str, allowed_agent_ids: Optional[List[str]] = None) -> List[tuple]
```

### BaseAgent

```python
class BaseAgent(ABC):
    def __init__(self, config: AgentConfig)
    async def process(self, context: AgentContext) -> Optional[AgentResponse]
    @abstractmethod
    async def evaluate(self, context: AgentContext) -> Optional[AgentResponse]
    def create_insight(self, content: str, type: InsightType, confidence: float = 1.0) -> AgentInsight
```

### AgentInsight

```python
class AgentInsight(BaseModel):
    agent_id: str
    agent_name: str
    type: InsightType  # SUGGESTION, WARNING, OPPORTUNITY, FACT, PRAISE, ERROR
    content: str
    confidence: float
    expiry: int
    metadata: Dict[str, Any] # Universal adapter for UI extensions (zone, color, voice)
```

### AgentContext

```python
class AgentContext(BaseModel):
    session_id: str
    recent_segments: List[TranscriptSegment]
    shared_state: Dict[str, Any]
    rag_docs: List[str]
    trigger_type: TriggerType
    trigger_metadata: Dict[str, Any]
    user_context: Optional[str]  # Injected User Profile
    language_directive: Optional[str] # Translation/Language instruction
```

### AgentResponse

```python
class AgentResponse(BaseModel):
    insights: List[AgentInsight]
    state_updates: Dict[str, Any]
```

---

## Best Practices

1. **Cooldowns**: Set appropriate cooldowns to prevent agent spam (10-30 seconds typical)
2. **Priority**: Use priority to ensure critical agents (e.g., compliance) override others
3. **Context Window**: Limit `context_turns` to 6-10 for cost efficiency
4. **Keywords**: Use specific, low-frequency keywords to avoid false positives
5. **Caching**: Enable caching for agents that analyze similar patterns repeatedly
6. **Error Handling**: Always return `AgentResponse` with error insights on exceptions

---

## Troubleshooting

### Agents Not Triggering

- Check `ai/agents_enabled` setting in database
- Verify agent is registered: `engine.agents`
- Check trigger type matches: `agent.config.trigger_types`
- Verify cooldown hasn't expired: `agent.last_run_time`

### Duplicate Insights

- Check de-duplication logic in `SessionManager._run_agent_check`
- Verify cooldown is set correctly
- Check cache isn't returning stale results

### Performance Issues

- Enable caching: `AgentEngine(enable_caching=True)`
- Reduce `context_turns` in model config
- Use faster models (`gpt-4o-mini` vs `gpt-4o`)
- Check RAG embedding cache is working

---

## License

See main project license.
