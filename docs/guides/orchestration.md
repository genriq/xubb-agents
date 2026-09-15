# Orchestration

**Applies to runtime:** 3.1.5 · Part of the [design guide](../DESIGN_GUIDE.md) set.

How several agents work together without talking to each other.

## The blackboard is the only channel

Agents never call one another. They read shared state and *propose* changes; the engine commits
what is permitted at its merge boundary, after validation. Nothing an agent returns writes
directly.

That indirection is what makes a swarm debuggable: one writer, one commit point, one place to
look when something is wrong.

| Container | For | Lifetime |
|---|---|---|
| **variables** | session state — phase, sentiment, whatever your product tracks | the session |
| **events** | "this happened", to wake another agent | the turn |
| **facts** | extracted knowledge, deduplicated | the session |
| **queues** | work handed to another agent or to the host | until drained |
| **memory** | one agent's private scratchpad | the session, per agent |

## Choosing a container

Most coordination questions answer themselves once you ask what the thing *is*:

- Does another agent need to **react now**? An **event**.
- Is it **knowledge about the conversation** that should persist and deduplicate? A **fact**.
- Is it **state the session is in**? A **variable**.
- Is it **work to be done**? A **queue**.
- Is it **only this agent's business**? **Memory**.

The common error is using variables for everything. Variables have no dedup, no precedence and
no structure — they are the right answer only when the thing genuinely is session state.

## Events and the second phase

An agent emits an event; agents that subscribe to it run in a **second phase** within the same
turn. That is how "detect, then react" works without either agent knowing the other exists.

<!-- runnable -->
```python
import asyncio
from xubb_agents import AgentEngine, AgentContext, Blackboard
from xubb_agents.core.agent import BaseAgent, AgentConfig
from xubb_agents.core.models import AgentResponse, Event, TranscriptSegment, TriggerType

class Detector(BaseAgent):
    async def evaluate(self, context):
        if "?" not in (context.recent_segments[-1].text if context.recent_segments else ""):
            return None
        response = AgentResponse()
        response.events.append(Event(name="question_detected", payload={},
                                     source_agent=self.config.id, timestamp=0.0))
        return response

class Responder(BaseAgent):
    async def evaluate(self, context):
        if context.phase != 2:
            return None                       # only reacts in the event phase
        return AgentResponse(insights=[self.create_insight("They asked something — answer it.")])

async def main():
    engine = AgentEngine()
    engine.register_agent(Detector(AgentConfig(name="Detector", id="detector", cooldown=0)))
    engine.register_agent(Responder(AgentConfig(
        name="Responder", id="responder", cooldown=0,
        trigger_types=[TriggerType.EVENT], subscribed_events=["question_detected"])))
    ctx = AgentContext(session_id="s", blackboard=Blackboard(),
                       recent_segments=[TranscriptSegment(speaker="c", timestamp=0.0,
                                                          text="What does it cost?")])
    result = await engine.process_turn(ctx)
    print([i.content for i in result.insights])

asyncio.run(main())
```

Phases are bounded — the engine runs at most two, so an event storm cannot cascade. An agent
that both emits and subscribes to the same event does not loop.

## Facts, and who wins a collision

Facts deduplicate by `(type, key)`. When two agents extract the same fact with different values,
the resolution is fixed and worth knowing, because it is the one place agent **priority** has
teeth:

1. higher agent `priority` wins;
2. then higher `confidence`;
3. then later registration.

**Priority beats confidence.** A specialist agent with `priority: 10` and confidence 0.6
overrides a generalist with `priority: 0` and confidence 0.95 — which is usually what you want,
and always surprising the first time. Set priority deliberately on agents whose facts should be
authoritative.

`Fact.priority` is stamped by the engine at merge time from the emitting agent. Agents should
not set it.

## Reserved namespace

Variables beginning `sys.` are the engine's. A proposed write there is `reserved_state_write`
and rejects the whole response. Do not build host state under that prefix.

## Per-agent attribution

The merged turn response aggregates several agents. When you need to know who did what:

- `acceptance_by_agent` — which agents were accepted or rejected. **One rejected agent does not
  fail the turn**, so the merged `acceptance_status` alone will not tell you.
- `data_by_agent` — each agent's UI action sidecar, attributed.
- `memory_updates_by_agent` — each agent's scratchpad writes.

## Common mistakes

- **Agents that know about each other.** Two agents that must coordinate directly are usually
  one agent.
- **Using variables as a message bus.** If another agent must react, emit an event.
- **Expecting confidence to win a fact collision.** Priority does.
- **Reading the merged `acceptance_status` as per-agent.** Use `acceptance_by_agent`.
