# Authoring agents

**Applies to runtime:** 3.1.5 · Part of the [design guide](../DESIGN_GUIDE.md) set.

Two ways to write an agent, and both are first-class.

| | Use when |
|---|---|
| **`DynamicAgent`** | The agent is a prompt plus configuration. Defined by data, so it can live in a database and be edited without a deploy. |
| **`BaseAgent` subclass** | The agent is code — a rule, a lookup, a calculation. No model call, or a call you make yourself. |

Both go through the same acceptance boundary. A custom producer gets no shortcuts: its
engine-owned fields are rejected, its channels are revalidated, its actions are authorized.

## A rule-based agent

No model, no key, deterministic. Good for anything you can decide without a language model —
and good as the first agent in a new host, because it isolates your wiring from prompt quality.

<!-- runnable -->
```python
import asyncio
from xubb_agents import AgentEngine, AgentContext, Blackboard
from xubb_agents.core.agent import BaseAgent, AgentConfig
from xubb_agents.core.models import AgentResponse, TranscriptSegment

class BudgetWatcher(BaseAgent):
    async def evaluate(self, context):
        last = context.recent_segments[-1].text.lower() if context.recent_segments else ""
        if "budget" not in last:
            return None                      # silence: the common case
        return AgentResponse(insights=[
            self.create_insight("Budget came up — ask what range they had in mind."),
        ])

async def main():
    engine = AgentEngine()
    engine.register_agent(BudgetWatcher(AgentConfig(name="Budget Watcher", cooldown=0)))
    ctx = AgentContext(
        session_id="s", blackboard=Blackboard(),
        recent_segments=[TranscriptSegment(speaker="customer", timestamp=0.0,
                                           text="It depends on the budget.")])
    result = await engine.process_turn(ctx)
    print([i.content for i in result.insights])

asyncio.run(main())
```

**Returning `None` is how you stay silent.** So is an `AgentResponse` with no insights — use
that when you are silent but still want to write state.

## A model-backed agent

`DynamicAgent` takes a configuration dictionary. The fields that matter most:

```python
{
    "id": "objection-spotter",           # stable; used for memory and attribution
    "name": "Objection Spotter",
    "text": "...the system prompt, Jinja2-templated...",
    "output_format": "insight_v1",        # ALWAYS set this explicitly
    "trigger_config": {"mode": "turn_based", "cooldown": 30},
    "insight_config": {"allowed_types": ["warning", "suggestion"]},
    "model_config": {"model": "gpt-4o-mini", "context_turns": 6},
}
```

**`output_format` is not optional in practice.** Omitting it inherits a deprecated format and
warns; it becomes an error in 4.0.0. Use `insight_v1`, or `widget_control` if the agent also
drives host UI. See [migration](../MIGRATION_OUTPUT_FORMATS.md).

**Do not write the output envelope into your prompt.** The engine generates the exact
instruction for each run from the agent's permissions — which types it may use, which channels
it may write, which evidence it may cite. A hand-written envelope in `text` can only contradict
that. Write the *persona and the judgement*; let the framework write the format.

### Narrow the purposes

`insight_config.allowed_types` is the strongest quality lever you have. An agent permitted to
emit anything will emit something.

<!-- runnable -->
```python
from xubb_agents import DynamicAgent

agent = DynamicAgent({
    "id": "risk-watcher", "name": "Risk Watcher",
    "text": "Watch for commitments the seller cannot keep.",
    "output_format": "insight_v1",
    "trigger_config": {"cooldown": 60},
    "insight_config": {"allowed_types": ["warning"]},     # this agent only warns
})
print(agent.config.insight_config.allowed_types)
```

A permission the host has not declared is withdrawn for the run and reported as
`capability_unavailable` — not an error, but the reason your agent is quiet.

## Triggers, and the cost of firing

`trigger_config.mode` is `turn_based`, `keyword`, `silence`, `interval`, `event`, or a list.

`cooldown` is the seconds between firings, and it is the other big quality lever. A turn-based
agent with `cooldown: 0` evaluates every turn; that is right for a cheap rule and usually wrong
for a model call.

`trigger_conditions` gates on blackboard state before the agent runs at all — the cheapest
possible filter, because it costs no model call. It **fails closed**: a condition that cannot
be evaluated suppresses the agent.

## Memory

An agent's private scratchpad persists across turns, namespaced by agent id. It is written by
returning `memory_updates` and read back through the templated prompt. It is private: no other
agent sees it.

Use it for continuity ("I already raised this"), not for shared state — that belongs on the
blackboard, where other agents can see it.

## Testing an agent

Test through the real engine with a faked provider, not by calling `evaluate` directly. The
interesting failures live in the space between your agent and the acceptance boundary —
permissions, channels, envelope shape — and calling `evaluate` skips all of it.

Every test in this repository works that way; `tests/test_typed_acceptance_g1.py` is the
pattern to copy.

## Common mistakes

- **An agent that speaks every turn.** Narrow the purposes, raise the cooldown, or add a
  trigger condition. If none of those help, the agent is too broad — split it.
- **Writing the envelope into the prompt.** See above; the framework already did it.
- **Reading `confidence` as an assessment.** It is `1.0` when the model offered nothing.
  `confidence_provided` is the field you want.
- **Treating silence as failure.** An empty `insights` list is a successful turn.
