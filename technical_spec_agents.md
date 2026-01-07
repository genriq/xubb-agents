# Xubb Agents Framework - Technical Specification

**Version:** 1.0
**Status:** Active
**Scope:** `xubb_agents` Library

---

## 1. Executive Summary

The **Xubb Agents Framework** is a standalone, event-driven Python library designed to power real-time conversational intelligence. It provides the infrastructure for creating, managing, and executing autonomous AI agents that "listen" to a conversation and intervene with context-aware insights.

It is designed to be **consumed** by host applications (like `xubb_server`) but maintains strict decoupling, ensuring it can be used in any Python-based conversational system (e.g., a CLI tool, a desktop app, or a web service).

---

## 2. Architectural Principles

1.  **Event-Driven Execution:** Agents do not run continuously. They are dormant until triggered by specific events (Turn completion, Keyword detection, Silence, Timer).
2.  **Stateless Execution (mostly):** Each evaluation is fresh, provided with a `Context` object containing transcript history and shared state. Agents return a `Response` object.
3.  **Non-Blocking Concurrency:** All I/O (LLM calls) is asynchronous (`asyncio`). Multiple agents evaluate in parallel without blocking the main audio/transcript loop.
4.  **Graceful Degradation:** Failures in individual agents (LLM errors, logic bugs) are caught, logged, and isolated, ensuring the host application remains stable.

---

## 3. Core Components

### 3.1 Agent Engine (`core/engine.py`)
The central orchestrator.
*   **Responsibilities:**
    *   **Registry:** Maintains the list of active agents.
    *   **Routing:** Determines which agents to run based on the incoming trigger type (Turn, Keyword, etc.).
    *   **Keyword Detection:** Provides `check_keyword_triggers(text)` to help consumers identify when to wake agents.
    *   **Caching:** Implements a content-addressable cache (`hash(agent_id + transcript)`) to prevent redundant LLM calls for identical contexts.
    *   **State Management:** Manages the "Blackboard" (Shared State) where agents can publish public flags (e.g., `negotiation_phase_active`).
    *   **Aggregation:** Collects responses from parallel agents, sorts state updates by priority, and returns a unified `AgentResponse`.
    *   **Observability:** Emits lifecycle events (`on_turn_start`, `on_agent_finish`) to registered callbacks for debugging and visualization.

### 3.2 Base Agent (`core/agent.py`)
The abstract base class for all intelligence units.
*   **Lifecycle:**
    1.  `__init__`: Configures triggers, cooldowns, and identity.
    2.  `process()`: Template method. Checks triggers and cooldowns.
    3.  `evaluate()`: Abstract method. The actual "Brain" logic (usually an LLM call).
*   **Built-in Safety:**
    *   **Cooldowns:** Prevents spamming (e.g., "Don't speak for 10 seconds after triggering").
    *   **Error Barriers:** Wraps `evaluate` in try/catch blocks to return `InsightType.ERROR` instead of crashing.

### 3.3 Trigger System
Agents define *when* they want to wake up via `AgentConfig`.
1.  **TURN_BASED:** Fires when a speaker finishes an utterance. (Most common).
2.  **KEYWORD:** Fires *immediately* when a substring match is found (e.g., "price", "cancel").
3.  **SILENCE:** Fires when the host detects "dead air" exceeding a threshold.
4.  **INTERVAL:** Fires on a fixed timer (background monitoring).

### 3.4 LLM Client (`core/llm.py`)
A thin wrapper around `AsyncOpenAI`.
*   **Abstraction:** Centralizes API key management and client initialization.
*   **JSON Enforcement:** Enforces `response_format={"type": "json_object"}` to ensure agents return structured data.

---

## 4. Data Models (`core/models.py`)

### 4.1 AgentContext
The input payload delivered to an agent during execution.
*   `session_id`: Unique identifier of the conversation.
*   `recent_segments`: List of `TranscriptSegment` (Speaker, Text, Timestamp). Usually the last 6-10 turns.
*   `shared_state`: Read-only copy of the global blackboard.
*   `trigger_type`: Why was I called?
*   `trigger_metadata`: Extra info (e.g., the specific keyword matched).
*   `user_context`: Injected user profile information (e.g., "User is a Sales Director").
*   `language_directive`: Optional instruction for language control (e.g., "Respond in Spanish").

### 4.2 AgentResponse
The output payload returned by an agent.
*   `insights`: List of `AgentInsight` objects (Content, Type, Confidence, Metadata).
*   `state_updates`: Dictionary of key-value pairs to merge into the Shared Blackboard.
*   `data`: Generic dictionary for sidecar payloads (e.g. `ui_actions`) routed by the Host.
*   `debug_info`: Dictionary for carrying non-production debug data (e.g., raw prompts).

**Insight Types:**
*   `SUGGESTION`: Passive advice (Zone C).
*   `WARNING`: Urgent negative alert (Zone A).
*   `OPPORTUNITY`: Urgent positive alert (Zone A).
*   `FACT`: Contextual information (Zone C).
*   `PRAISE`: Positive reinforcement.
*   `ERROR`: System issues.

**Metadata Passthrough:**
The `AgentInsight` model includes a `metadata: Dict[str, Any]` field. This acts as a universal adapter, allowing agents to pass UI-specific hints (e.g., `{"zone": "A", "color": "red"}`) without the framework needing to understand them.

---

## 5. Dynamic Agent Execution Flow (`library/dynamic.py`)

The `DynamicAgent` is the primary implementation used for user-defined agents. It has a specific execution lifecycle:

1.  **Memory Loading:**
    *   Retrieves persistent memory from `shared_state` using key `memory_{agent_id}`.
    *   Merges it with local `private_state` (RAM).
2.  **Context Construction:**
    *   Slices transcript based on `context_turns` (e.g., last 6 turns).
    *   Injects `user_context` (User Persona).
    *   Injects `language_directive` (Language Constraints).
    *   Injects RAG documents if present in context.
    *   Injects Trigger Metadata (e.g., "You were woken up by keyword 'price'").
3.  **LLM Call:**
    *   **Default Mode:** Uses standard JSON prompt `{"has_insight": bool, ...}`.
    *   **Raw Mode (`output_format="v2_raw"`):** Uses strict V2 Schema (`{"insight": {...}, "state_snapshot": {...}}`).
        *   Enforces `InsightType` Enum mapping (safe against hallucinations).
        *   Passes extra fields to `metadata` automatically.
    *   **Widget Control (`output_format="widget_control"`):** Enables "Hands" mode. Maps `ui_actions` to the `response.data` sidecar for UI manipulation.
    *   **Custom Schemas:** Can load external JSON schema definitions from `library/schemas/` to support custom output formats without code changes.
    *   **Prompt Templating (Jinja2):** Before sending to LLM, the system prompt is rendered using Jinja2. Agents can access `{{ state }}`, `{{ memory }}`, and `{{ context }}` directly in the prompt text.
    *   Sends constructed prompt to LLM with JSON enforcement.
4.  **State Persistence:**
    *   Parses `memory_updates` from LLM response.
    *   Updates `private_state`.
    *   Writes full state back to `shared_state["memory_{agent_id}"]` to ensure persistence across sessions.

---

## 6. Performance Features

### 6.1 Response Caching
*   **Mechanism:** `AgentEngine` calculates a hash of `agent_id` + `transcript_text_tail`.
*   **Behavior:** If the exact same context triggers the same agent (e.g., rapid-fire VAD updates), the cached result is returned instantly.
*   **TTL:** Defaults to 5 minutes.

### 6.2 Priority System
*   **Conflict Resolution:** If Agent A (Priority 1) and Agent B (Priority 10) both try to update state key `risk_level`, Agent B wins.
*   **Execution Order:** All agents run in parallel, but state updates are applied in descending priority order.

---

## 7. Observability & Debugging
The framework implements the **Observer Pattern** to provide 13/10 visibility into agent behavior without cluttering the core logic.

### 7.1 AgentCallbackHandler (`core/callbacks.py`)
Consumers can register handlers to receive real-time events:
*   `on_turn_start(context)`
*   `on_agent_start(agent_name, context)`
*   `on_agent_finish(agent_name, response, duration)`
*   `on_turn_end(response, duration)`
*   `on_agent_error(agent_name, error)`

### 7.2 Structured Tracing (`utils/tracing.py`)
A built-in `StructuredLogTracer` is provided to generate "MRI Scans" of every turn.
*   **Output:** Single-line JSON log (`TURN_TRACE: { ... }`).
*   **Contents:** 
    *   **Context:** `user_context` (Identity), `language_directive` (Language constraints), `rag_docs` (Retrieved knowledge), `speaker` identity, `transcript_history` (Full conversation window).
    *   **Trigger:** Full `trigger_metadata` (e.g., specific keyword).
    *   **State:** `initial_shared_state` (Before execution) and full `state_updates` (Values, not just keys).
    *   **Performance:** `timestamp_start` (Real time), `total_latency_ms`.
    *   **Execution:** List of all triggered agents, their latency, and raw outputs.
    *   **Debug Info:** Raw `prompt_messages`, `model`, and `llm_output` (raw JSON from model) used for each agent call.
*   **Use Case:** This data can be consumed by the "Xubb Agent MRI" HTML dashboard or log analysis tools.

---

## 8. Directory Structure

```
xubb_agents/
├── core/
│   ├── agent.py       # Base class and Config
│   ├── engine.py      # Orchestrator
│   ├── llm.py         # OpenAI Wrapper
│   ├── models.py      # Pydantic Schemas
│   └── callbacks.py   # Event Protocol
├── library/
│   ├── dynamic.py     # Prompt-based generic agent
│   └── ...            # Other pre-built agents
├── utils/
│   └── tracing.py     # Debugging tools
├── README.md          # User Guide
└── technical_spec_agents.md # This document
```

---

## 9. Integration Guide (For Consumers)

To use this framework in a host app (like `xubb_server`):

1.  **Initialize Engine:**
    ```python
    engine = AgentEngine(api_key="...")
    ```
2.  **Register Agents:**
    ```python
    engine.register_agent(MyCustomAgent())
    ```
3.  **Check Keywords (Optional):**
    ```python
    # See which agents care about this text
    matches = engine.check_keyword_triggers(text)
    allowed_ids = [agent.config.id for agent, kw in matches]
    ```
4.  **Feed Events:**
    *   On Transcript: `await engine.process_turn(context, trigger_type=TriggerType.TURN_BASED)`
    *   On Keyword: `await engine.process_turn(context, allowed_agent_ids=allowed_ids, trigger_type=TriggerType.KEYWORD)`

---

## 10. Current Limitations
1.  **Local LLM Support:** The `LLMClient` is hardcoded for OpenAI-compatible APIs. While `ollama` or `vllm` can be used by changing the `base_url`, first-class support for local model loading is not yet implemented.
2.  **Batching:** Agents run in parallel (`asyncio.gather`), but requests are not yet batched into a single API call (OpenAI Batch API is async/offline, not real-time). Real-time batching (combining prompts) is a potential future optimization.
