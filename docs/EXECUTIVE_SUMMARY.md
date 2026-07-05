# Xubb Agents — Overview

**Version:** 2.4.0

A developer-facing overview of what the framework does and how it is put together. For
the deep design guide see [PLAYBOOK.md](PLAYBOOK.md); for the API and data models see
[technical_spec_agents.md](technical_spec_agents.md).

---

## What it does

xubb-agents is a framework for **real-time conversational copilots**: multiple
specialized agents observe a live human-to-human conversation and surface timely,
actionable insights to one participant, without taking over the conversation itself. It
handles the infrastructure — multi-agent orchestration at sub-second latency, state
across conversation turns, event-driven coordination, and error isolation — so an
integrator writes agent prompts, not plumbing:

- **Observe** live conversation turns as they arrive.
- **Analyze** context, sentiment, and intent per turn.
- **Advise** the participant with concise, actionable insights.
- **Coordinate** specialist agents in parallel through a shared blackboard.

---

## How it works

```
┌─────────────────────────────────────────────────────────────────────┐
│                      LIVE CONVERSATION                               │
│                                                                      │
│    Human A ◄──────────────────────────────────► Human B             │
│    (User)                                        (Customer)          │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             │ Real-time transcript
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    XUBB AGENTS FRAMEWORK                             │
│                                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │ Sales Coach │  │  Question   │  │ Compliance  │  ... more       │
│  │   Agent     │  │  Detector   │  │   Monitor   │    agents       │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                 │
│         │                │                │                         │
│         └────────────────┼────────────────┘                         │
│                          │                                          │
│                    ┌─────▼─────┐                                    │
│                    │ Blackboard │  Shared context & coordination    │
│                    └─────┬─────┘                                    │
│                          │                                          │
└──────────────────────────┼──────────────────────────────────────────┘
                           │
                           │ Real-time insights
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE                               │
│                                                                      │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │  ⚡ "Buying signal detected! Ask about timeline."           │   │
│   │  💡 "Customer mentioned $50K budget - noted."               │   │
│   │  ⚠️  "Compliance: Don't promise delivery dates."            │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

**Key concepts:**

| Concept | Description |
|---------|-------------|
| **Agent** | An AI specialist that analyzes specific aspects of the conversation |
| **Trigger** | What causes an agent to activate (turn completion, keywords, silence, events) |
| **Insight** | Actionable advice delivered to the user (suggestions, warnings, opportunities) |
| **Blackboard** | Shared state where agents coordinate and build collective understanding |
| **Event** | A signal from one agent that triggers others (e.g., "question detected" → "generate answer") |

---

## Target use cases

| Domain | Application |
|--------|-------------|
| **Sales** | Real-time coaching during customer calls — objection handling, buying signals, competitive positioning |
| **Customer Support** | Live assistance for agents — knowledge retrieval, escalation alerts, compliance monitoring |
| **Interviews** | Coaching during practice sessions — answer improvement, pacing and filler-word cues, follow-up suggestions |
| **Negotiations** | Tactical advice during high-stakes discussions — concession tracking, anchoring, BATNA reminders |
| **Meetings** | Live intelligence during team discussions — action item capture, decision tracking, participation balance |
| **Language Learning** | Conversation coaching — pronunciation, grammar, vocabulary suggestions in real-time |

---

## Architecture

The framework uses a **Blackboard Architecture** for multi-agent coordination
(introduced in v2.0, hardened in v2.1 and v2.2).

**Structured state containers:**

| Container | Purpose | Example |
|-----------|---------|---------|
| **Variables** | Current session state | `phase: "negotiation"`, `sentiment: 0.7` |
| **Events** | Signals between agents | `"question_detected"`, `"objection_raised"` |
| **Queues** | Ordered work items | `pending_questions: ["What's the price?", "Timeline?"]` |
| **Facts** | Extracted knowledge | `{type: "budget", value: "$50K", confidence: 0.9}` |
| **Memory** | Agent-private state | Each agent's scratchpad |

**Multi-phase execution:**

1. **Phase 1:** Primary agents analyze the conversation turn.
2. **State merge:** Updates are collected and applied by priority.
3. **Phase 2:** Event-triggered agents respond to Phase 1 signals (single-hop).
4. **Response:** Aggregated insights delivered to the user.

**Intelligent gating** — trigger conditions prevent unnecessary LLM calls:

```json
{
  "trigger_conditions": {
    "rules": [
      {"var": "phase", "op": "eq", "value": "negotiation"},
      {"fact": "budget", "op": "exists"},
      {"queue": "pending_questions", "op": "not_empty"}
    ]
  }
}
```

---

## Technical highlights

- **Async-first:** Built on Python `asyncio` for non-blocking concurrent execution.
- **OpenAI / OpenAI-compatible:** The LLM client wraps `AsyncOpenAI`, so it works with
  OpenAI and any OpenAI-compatible endpoint (e.g. GPT-4o, GPT-4o-mini, or self-hosted
  models behind an OpenAI-compatible API). A dedicated Anthropic adapter is out of scope
  for this release.
- **Pluggable schemas:** Custom output formats without code changes.
- **Observable:** Callback system and structured tracing for debugging.
- **Backward compatible:** v1.0 agents work unchanged in v2.0.
- **Host agnostic:** Consumable by web servers, CLI tools, and desktop apps.

---

## Getting started

```python
from xubb_agents import AgentEngine, DynamicAgent, AgentContext, Blackboard

# Initialize the engine
engine = AgentEngine(api_key="sk-...")

# Register your agents
engine.register_agent(DynamicAgent(sales_coach_config))
engine.register_agent(DynamicAgent(question_detector_config))

# Process a conversation turn (inside an async function)
response = await engine.process_turn(
    AgentContext(
        session_id="call_123",
        recent_segments=transcript,
        blackboard=Blackboard(),
    )
)

# Deliver insights to the user
for insight in response.insights:
    display_to_user(insight)
```

For a complete, runnable example (including a no-key offline variant), see the
[README quickstart](../README.md#quickstart-copy-paste-runnable).

---

**Version:** 2.4.0 · **Status:** Beta, production-hardened (see the contract registry) · **License:** MIT
