# Xubb Agents — Prompt Engineering Guide

**Version:** 3.0
**Last Updated:** March 20, 2026
**Status:** Production (xubb_agents v2.1.1)

This guide is the **definitive reference** for writing effective prompts for the Xubb Agents framework. It covers system prompt design, Jinja2 templating, output schemas, trigger configuration, and agent coordination patterns.

> **Scope:** This guide covers the `xubb_agents` library only. Host-specific features (UI rendering, database persistence, socket events) are out of scope and documented by the host application.

---

## Table of Contents

1. [How Prompts Work](#1-how-prompts-work)
2. [Jinja2 Templating](#2-jinja2-templating)
3. [Context Injection](#3-context-injection)
4. [Output Schemas](#4-output-schemas)
5. [Trigger Configuration](#5-trigger-configuration)
6. [Agent Coordination Patterns](#6-agent-coordination-patterns)
7. [Prompt Design Best Practices](#7-prompt-design-best-practices)
8. [Complete Examples](#8-complete-examples)
9. [Reliability Checklist](#9-reliability-checklist)

---

## 1. How Prompts Work

A `DynamicAgent`'s system prompt is a **Jinja2 template** that gets rendered at evaluation time. The framework injects context (user profile, Blackboard state, transcript, RAG docs) around your prompt text, then sends the assembled message to the LLM.

### Prompt Assembly Order

The final system prompt is assembled from these sections (empty sections are omitted — no blank lines):

```
1. [User Profile]          — if include_context: true
2. [Language Directive]     — always (if set)
3. [Your Prompt Template]  — rendered via Jinja2
4. [Agent Memory]          — private scratchpad
5. [RAG Documents]         — if include_context: true and docs exist
6. [Trigger Context]       — keyword/silence metadata (if applicable)
7. [Output Schema]         — JSON format instruction
```

The transcript history is sent as separate user/assistant messages (not embedded in the system prompt), controlled by `context_turns`.

---

## 2. Jinja2 Templating

Agent prompts use **Jinja2 syntax** to read Blackboard state at render time. Templates are executed in a `SandboxedEnvironment` — access to Python internals (`__class__`, `__globals__`, `__mro__`) raises `jinja2.SecurityError`.

### Available Template Variables

| Variable | Type | Description |
|----------|------|-------------|
| `state` | `Dict` | Alias for `context.shared_state` (v1 compatibility) |
| `memory` | `Dict` | Agent's private memory (local working copy) |
| `context` | `AgentContext` | Full context object |
| `user_context` | `str` | User profile text |
| `blackboard` | `Blackboard` | Structured Blackboard (v2) |
| `agent_id` | `str` | This agent's config ID |

### Reading Blackboard State

```jinja2
{# Variables #}
Current phase: {{ blackboard.variables.phase }}
Sentiment score: {{ blackboard.variables.sentiment.score }}

{# v1 compatibility (same data) #}
Phase via state: {{ state.phase }}

{# Queues #}
Pending questions ({{ blackboard.queues.pending_questions | length }}):
{% for q in blackboard.queues.pending_questions %}
- {{ q }}
{% endfor %}

{# Facts #}
{% for fact in blackboard.facts %}
- {{ fact.type }}: {{ fact.value }} (confidence: {{ fact.confidence }})
{% endfor %}

{# Own memory #}
My last warning turn: {{ memory.last_warning_turn | default('none') }}
{# Or via blackboard: #}
{{ blackboard.memory[agent_id].last_warning_turn | default('none') }}
```

### Conditional Sections

```jinja2
{% if blackboard.variables.phase == "negotiation" %}
NEGOTIATION CONTEXT:
The conversation is in the negotiation phase. Focus on value-based responses.
{% endif %}

{% if blackboard.facts | length > 0 %}
KNOWN FACTS:
{% for fact in blackboard.facts %}
- {{ fact.type }}: {{ fact.value }}
{% endfor %}
{% endif %}
```

### Filters

All standard Jinja2 filters work: `default`, `length`, `lower`, `upper`, `join`, `sort`, `map`, `select`, `reject`, etc.

```jinja2
Topics discussed: {{ blackboard.queues.topics | default([]) | join(", ") }}
Question count: {{ blackboard.queues.pending_questions | default([]) | length }}
```

---

## 3. Context Injection

The `DynamicAgent` controls what context is injected via the `include_context` config flag.

### Gated by `include_context` (default: `true`)

- **User Profile**: Identity, goals, expertise, session metadata
- **RAG Documents**: Relevant excerpts from attached files

### Always injected (regardless of `include_context`)

- **Language Directive**: Language enforcement/translation constraints
- **Trigger Context**: Keyword or silence metadata that activated the agent
- **Output Schema**: JSON format instruction from the schema definition
- **Agent Memory**: The agent's private scratchpad

### When to disable context

Set `include_context: false` for agents that don't need user profile or RAG docs. This saves tokens and reduces noise:

- Background monitors (sentiment, topic tracking)
- Pure-state agents that only update Blackboard variables
- Widget trackers that operate solely on transcript + Blackboard state

```json
{
  "include_context": false,
  "model_config": {
    "model": "gpt-4o-mini",
    "context_turns": 6
  }
}
```

### Context Turns

Control how much transcript history the agent sees:

```json
"model_config": {
    "model": "gpt-4o-mini",
    "context_turns": 6
}
```

Lower values = cheaper, faster. Higher values = more context but more tokens. Typical ranges:
- **2-4 turns**: Keyword reactors, simple detectors
- **6-10 turns**: General coaching, analysis
- **15-30 turns**: Deep context agents, summarizers

---

## 4. Output Schemas

Agents return JSON conforming to an **output schema**. The schema determines how the LLM response is parsed into an `AgentResponse`.

### Built-in Schemas

Located in `library/schemas/`:

| Schema | Use Case | Key Fields |
|--------|----------|------------|
| `default` | Standard agents with insights | `has_insight`, `type`, `content`, `confidence` |
| `v2_raw` | Full v2 structured response | All Blackboard update fields |
| `widget_control` | Background state agents | `ui_actions`, `state_snapshot` |

### Default Schema

The most common schema. Use when your agent produces insights for the user:

```json
{
  "has_insight": true,
  "type": "suggestion",
  "content": "Brief advice here (max 15 words)",
  "confidence": 0.85,
  "expiry": 30,
  "variable_updates": { "phase": "negotiation" },
  "events": [
    { "name": "objection_detected", "payload": { "type": "price" } }
  ],
  "memory_updates": { "last_objection_turn": 42 }
}
```

When nothing to report:
```json
{ "has_insight": false }
```

### Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `has_insight` | boolean | **Yes** | `true` = produce insight, `false` = silent (state-only) |
| `type` | string | If `has_insight: true` | `"suggestion"`, `"warning"`, `"opportunity"`, `"fact"`, `"praise"` |
| `content` | string | If `has_insight: true` | The insight text (keep concise) |
| `confidence` | float | No | 0.0-1.0 confidence score |
| `expiry` | int | No | Seconds until insight auto-dismisses (default: 15) |
| `variable_updates` | object | No | Key-value pairs to write to Blackboard variables |
| `events` | array | No | Events to emit (triggers other agents in Phase 2) |
| `facts` | array | No | Extracted knowledge: `[{"type": "budget", "value": 50000, "confidence": 0.9}]` |
| `memory_updates` | object | No | Agent-private persistent state |
| `queue_pushes` | object | No | Items to add to named queues: `{"action_items": ["Follow up"]}` |

### Insight Types

| Type | Use Case |
|------|----------|
| `suggestion` | Actionable advice ("Ask about their timeline") |
| `warning` | Risk alerts ("Compliance risk detected") |
| `opportunity` | Positive urgent moment ("Great time to close") |
| `fact` | Neutral information ("Budget confirmed: $50K") |
| `praise` | Positive reinforcement ("Great rapport building!") |

### Custom Schemas

Create `library/schemas/my_schema.json` to define custom output formats. The schema file defines the JSON structure the LLM should return and how it maps to `AgentResponse` fields.

---

## 5. Trigger Configuration

Triggers control *when* an agent runs. Configure via `trigger_config` in the agent's config dict:

```json
{
  "trigger_config": {
    "mode": "keyword",
    "keywords": ["price", "budget", "cost"],
    "cooldown": 10,
    "subscribed_events": [],
    "silence_threshold": null
  }
}
```

### Trigger Modes

| Mode | When It Fires | Cost |
|------|---------------|------|
| `turn_based` | After every transcript segment | High (runs frequently) |
| `keyword` | When specific words are detected | Low (selective) |
| `silence` | After `silence_threshold` seconds of dead air | Low |
| `interval` | Every `trigger_interval` seconds | Medium |
| `event` | When another agent emits a subscribed event | Low (targeted) |
| `force` | User-triggered, bypasses cooldown and conditions | N/A |

**Combining modes**: Set `"mode": ["keyword", "turn_based"]` to trigger on keywords OR every turn.

**Convenience**: If you set `subscribed_events` without including `"event"` in the mode, `DynamicAgent` auto-adds `TriggerType.EVENT` for you.

### Trigger Conditions

Preconditions evaluated against Blackboard state *before* the agent runs. Prevents unnecessary LLM calls:

```json
{
  "trigger_conditions": {
    "mode": "all",
    "rules": [
      {"var": "phase", "op": "in", "value": ["negotiation", "closing"]},
      {"var": "sentiment", "op": "gte", "value": 0.5},
      {"fact": "budget", "op": "exists"},
      {"queue": "pending_questions", "op": "not_empty"},
      {"meta": "turn_count", "op": "gte", "value": 3}
    ]
  }
}
```

**Modes**: `"all"` (AND — all rules must pass) or `"any"` (OR — at least one must pass).

**Available operators**: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, `contains`, `exists`, `present`, `not_exists`, `not_empty`, `empty`, `mod`

### Cooldown

Minimum seconds between runs. Enforced even after errors (prevents runaway retries):

```json
"cooldown": 10
```

Typical values:
- **0-2s**: High-frequency monitors (sentiment)
- **5-10s**: Keyword reactors
- **15-30s**: General coaching agents

---

## 6. Agent Coordination Patterns

### Pattern 1: Event Chain

Agent A detects something and emits an event. Agent B subscribes and reacts:

**Agent A (Detector):**
```json
{
  "trigger_config": { "mode": "turn_based", "cooldown": 5 },
  "text": "Detect price objections in the conversation..."
}
```
Returns:
```json
{
  "has_insight": false,
  "events": [
    { "name": "price_objection_detected", "payload": { "severity": "high" } }
  ]
}
```

**Agent B (Responder):**
```json
{
  "trigger_config": {
    "mode": "event",
    "subscribed_events": ["price_objection_detected"],
    "cooldown": 0
  },
  "text": "A price objection was just detected. Suggest a value-based reframe..."
}
```

Agent B runs automatically in Phase 2 when Agent A emits the event.

### Pattern 2: Background Monitor + Conditional Agent

A monitor tracks state silently. Another agent activates only when state meets conditions:

**Monitor (always runs, never shows insights):**
```json
{
  "trigger_config": { "mode": "turn_based", "cooldown": 3 },
  "include_context": false,
  "text": "Analyze the sentiment of the conversation..."
}
```
Returns: `{ "has_insight": false, "variable_updates": { "sentiment": { "score": 0.3 } } }`

**Conditional Agent (only runs when sentiment drops):**
```json
{
  "trigger_config": { "mode": "turn_based", "cooldown": 15 },
  "trigger_conditions": {
    "mode": "all",
    "rules": [
      {"var": "sentiment.score", "op": "lt", "value": 0.4}
    ]
  },
  "text": "The conversation sentiment is low. Suggest ways to recover rapport..."
}
```

### Pattern 3: Fact Extraction + Downstream Use

One agent extracts facts, another reads them:

**Extractor:**
```json
{
  "has_insight": false,
  "facts": [
    { "type": "budget", "key": "primary", "value": 50000, "confidence": 0.9 }
  ]
}
```

**Consumer (reads via Jinja2):**
```jinja2
{% for fact in blackboard.facts %}
{% if fact.type == "budget" %}
Known budget: {{ fact.value }} (confidence: {{ fact.confidence }})
{% endif %}
{% endfor %}
```

### Pattern 4: Queue-Based Work Items

Agents push items to queues for tracking:

```json
{
  "has_insight": false,
  "queue_pushes": {
    "action_items": ["Schedule follow-up call", "Send pricing proposal"],
    "questions_asked": ["What is your budget?"]
  }
}
```

Another agent reads the queue:
```jinja2
Open action items ({{ blackboard.queues.action_items | default([]) | length }}):
{% for item in blackboard.queues.action_items | default([]) %}
- {{ item }}
{% endfor %}
```

---

## 7. Prompt Design Best Practices

### Keep Insights Brief

The UI displays insights as short cards. Aim for **under 15 words**:

```
GOOD: "Ask about their timeline — they mentioned a Q2 deadline."
BAD:  "Based on my analysis of the conversation, it appears that the prospect mentioned something about a Q2 deadline, so you might want to consider asking about their timeline requirements in more detail."
```

### Use `has_insight: false` Liberally

Most turns, an agent should stay silent. Only surface insights when there's genuine value:

```text
IMPORTANT: Only return has_insight: true if you have specific, actionable advice.
If the conversation is flowing normally, return { "has_insight": false }.
Do NOT force insights when there is nothing meaningful to say.
```

### Be Explicit About JSON Format

Always include the output format in your prompt:

```text
OUTPUT FORMAT:
Return ONLY valid JSON. No markdown, no explanation.

If you have advice:
{ "has_insight": true, "type": "suggestion", "content": "Brief advice", "confidence": 0.85 }

If nothing to report:
{ "has_insight": false }
```

### Separate Detection from Response

Use event chains instead of monolithic agents:
- **Detector agent**: Cheap model (gpt-4o-mini), high frequency, emits events
- **Responder agent**: Better model (gpt-4o), triggered only by events, produces insights

This saves tokens and improves response quality.

### Use Memory for Continuity

Agents can maintain state across turns via `memory_updates`:

```text
YOUR MEMORY:
{{ memory | tojson }}

Use your memory to avoid repeating the same advice. If you already warned about
a topic, don't warn again unless the situation has changed significantly.

If you provide advice, update your memory:
{ "memory_updates": { "last_advice_topic": "pricing", "last_advice_turn": 42 } }
```

---

## 8. Complete Examples

### Example 1: Price Objection Handler

```json
{
  "id": "price-objection-handler",
  "name": "Price Objection Handler",
  "text": "You are a sales objection specialist.\n\nYOUR ROLE:\nDetect price-related objections and suggest value-based reframes.\n\nINSTRUCTIONS:\n1. Analyze the last few turns for price concerns.\n2. If no objection, return { \"has_insight\": false }.\n3. If objection detected, suggest a specific reframe.\n\nOUTPUT FORMAT:\nReturn ONLY valid JSON.\n{ \"has_insight\": true, \"type\": \"suggestion\", \"content\": \"Brief reframe advice\", \"confidence\": 0.85 }\nor\n{ \"has_insight\": false }",
  "trigger_config": {
    "mode": "keyword",
    "keywords": ["expensive", "cost", "price", "budget", "afford", "cheaper"],
    "cooldown": 5
  },
  "trigger_conditions": {
    "mode": "all",
    "rules": [
      {"var": "phase", "op": "in", "value": ["discovery", "negotiation", "closing"]}
    ]
  },
  "priority": 10,
  "model_config": {
    "model": "gpt-4o-mini",
    "context_turns": 4
  },
  "include_context": false
}
```

### Example 2: Question Detector + Responder Chain

**Detector:**
```json
{
  "id": "question-detector",
  "name": "Question Detector",
  "text": "Analyze the conversation for questions asked by the other party.\n\nIf a question is detected:\n{\n  \"has_insight\": false,\n  \"events\": [{\"name\": \"question_detected\", \"payload\": {\"question\": \"the question text\"}}],\n  \"queue_pushes\": {\"pending_questions\": [\"the question text\"]}\n}\n\nIf no question: { \"has_insight\": false }",
  "trigger_config": { "mode": "turn_based", "cooldown": 3 },
  "model_config": { "model": "gpt-4o-mini", "context_turns": 2 },
  "include_context": false
}
```

**Responder:**
```json
{
  "id": "question-coach",
  "name": "Question Coach",
  "text": "A question was just detected in the conversation.\n\nPending questions:\n{% for q in blackboard.queues.pending_questions | default([]) %}\n- {{ q }}\n{% endfor %}\n\nSuggest a brief, strategic answer approach.\n\nOUTPUT FORMAT:\n{ \"has_insight\": true, \"type\": \"suggestion\", \"content\": \"Brief coaching advice\" }",
  "trigger_config": {
    "mode": "event",
    "subscribed_events": ["question_detected"],
    "cooldown": 0
  },
  "model_config": { "model": "gpt-4o", "context_turns": 6 }
}
```

### Example 3: Sentiment Monitor (Silent Background Agent)

```json
{
  "id": "sentiment-monitor",
  "name": "Sentiment Monitor",
  "text": "Analyze the emotional tone of the conversation.\n\nReturn the current sentiment as a silent state update:\n{\n  \"has_insight\": false,\n  \"variable_updates\": {\n    \"sentiment\": {\n      \"score\": 0.0-1.0,\n      \"label\": \"Positive\" | \"Neutral\" | \"Negative\"\n    }\n  }\n}",
  "trigger_config": { "mode": ["turn_based", "interval"], "cooldown": 3 },
  "model_config": { "model": "gpt-4o-mini", "context_turns": 4 },
  "include_context": false,
  "priority": 50
}
```

---

## 9. Reliability Checklist

### For All Agents

- [ ] **JSON instruction**: Does the prompt explicitly say "Return ONLY valid JSON"?
- [ ] **Silent default**: Will the agent return `{ "has_insight": false }` when there's nothing to say?
- [ ] **Cooldown**: Is `cooldown` set appropriately? (minimum 2-5s for monitors, 5-15s for coaching)
- [ ] **Context turns**: Is `context_turns` tuned to balance accuracy vs. token cost?
- [ ] **Model choice**: `gpt-4o-mini` for simple detection, `gpt-4o` for complex reasoning?
- [ ] **include_context**: Set to `false` for agents that don't need user profile or RAG?

### For Agents with Trigger Conditions

- [ ] **Conditions defined**: Did you add `trigger_conditions` to skip unnecessary LLM calls?
- [ ] **Condition mode**: `"all"` (AND) or `"any"` (OR) — correct for your use case?
- [ ] **Variable exists**: Do the variables/facts you check actually get set by another agent?

### For Event-Driven Agents

- [ ] **Emitter configured**: Does the emitter agent include `events` in its output schema?
- [ ] **Subscriber configured**: Does the subscriber have `subscribed_events` set?
- [ ] **Cooldown zero**: Event subscribers typically use `cooldown: 0` to respond immediately
- [ ] **No circular chains**: Phase 2 agents cannot trigger further phases — verify no circular dependency

### For Background Monitors

- [ ] **Always silent**: Prompt always returns `has_insight: false`?
- [ ] **Correct keys**: Using the right variable names in `variable_updates`?
- [ ] **Priority set**: Higher priority for monitors that must win state conflicts?
 