# Host integration

**Applies to runtime:** 3.1.5 · Part of the [design guide](../DESIGN_GUIDE.md) set.

Wiring the engine into your application: what you declare, what you get back, and how to read
it.

## Declare what you can do

The engine will not let an agent use a capability your host has not declared. This is the
security property that makes the rest safe — **an agent cannot grant itself anything** — and
it is also the most common cause of "why is my agent silent".

Declarations live on `AgentContext` and are frozen for the run.

<!-- runnable -->
```python
from xubb_agents import (AgentContext, Blackboard, HostInsightCapabilities,
                         HostWidgetCapabilities, WidgetDeclaration, WidgetActionDeclaration)

context = AgentContext(
    session_id="s-1",
    recent_segments=[],
    blackboard=Blackboard(),

    # Who the assistant is helping. Without this, reply / question / correction
    # are withdrawn for the run.
    principal_id="user-42",

    # What your UI can present.
    insight_capabilities=HostInsightCapabilities(
        supported_types=["suggestion", "warning", "fact", "observation", "question"],
        text_questions=True,        # you can render a question and collect an answer
        corrections=True,           # you can retract or replace an earlier card
    ),

    # Which widgets an agent may drive. Empty authorizes NOTHING.
    widget_capabilities=HostWidgetCapabilities(widgets=[
        WidgetDeclaration(target_widget="goals_widget", actions=[
            WidgetActionDeclaration(action="update",
                                    required_payload_keys=["goal_id"],
                                    optional_payload_keys=["done"]),
        ]),
    ]),
)
print(sorted(context.widget_capabilities.authorization_map()))
```

**Defaults are conservative on purpose.** `HostInsightCapabilities()` permits the five purposes
that need nothing of a host beyond rendering a card, with every interactive capability off.
`observation` must be declared explicitly.

### The silent-failure to watch for

These fields fail closed, which means a mistake looks like correctness:

- A misspelled `widget_capabilities` is accepted and ignored — the field keeps its empty
  default, and **every** UI action is then refused as `unauthorized_ui_action` /
  `no_widgets_declared` while your host believes it declared them.
- A missing or misspelled `principal_id` silently withdraws reply, question and correction,
  visible only as `capability_unavailable` diagnostics that look like ordinary policy.

If agents are mysteriously quiet or actions never arrive, check the diagnostics first and the
prompt second.

## Read the result

```python
response = await engine.process_turn(context)
```

| | |
|---|---|
| `response.insights` | what to show. Empty is a normal, successful turn |
| `response.acceptance_status` | `accepted` / `accepted_silent` / `rejected`, **aggregated** across agents |
| `response.acceptance_by_agent` | per-agent — use this to find *which* agent was refused |
| `response.diagnostics` | why something was refused; codes in [DIAGNOSTICS.md](../DIAGNOSTICS.md) |
| `response.data["ui_actions"]` | validated, authorized widget actions for you to execute |
| `response.data_by_agent` | the same, attributed per agent |

**Rejection is whole-response.** A rejected agent commits none of its effects — no insight, no
state, no actions. A diagnostic never means "part of this applied".

**A diagnostic is not automatically a failure.** `capability_unavailable` and
`unsupported_structured_output` appear on accepted responses. Never write
`if response.diagnostics: discard()`.

## Execute actions; the engine does not

When the engine publishes `data["ui_actions"]`, it is telling you the action was well-formed and
your declarations authorized it. **It has not happened.** Your host executes it, and your host
owns what happens when execution fails. Nothing here is transactional over your UI.

An action can arrive with no insight attached — acting without speaking is the point of
`widget_control`.

For payload rules a key list cannot express, pass a validator once at the engine; it can only
narrow what the declarations already permit:

```python
engine = AgentEngine(api_key=..., widget_payload_validator=my_validator)
# my_validator(action) -> None to allow, or a short string naming why it was refused
```

## Questions and answers

An agent may ask the principal for information when `text_questions` is declared and
`principal_id` is present. Your host renders the question, collects a reply, and returns it on
the next turn through `insight_answers`.

Two rules the framework enforces and your UI should reflect: an answer reaches **only the agent
that asked**, unless you declare `answers_shared`; and **a dismissed or unanswered question is
not consent and not an answer**.

## Corrections

An agent may repair its own earlier message when `corrections` is declared and your host passes
the retained records in `insight_reference_context`. Mark a record `correctable: False` to take
it off the table.

Your UI decides what a correction looks like — replacing the card, striking it through, or
withdrawing it. The engine validates that the target is real, is the agent's own, and is not
from the current turn; it does not decide your presentation.

## Lifecycle

Register agents once and reuse the engine; it is not per-session. `replace_agents` swaps the
whole registry atomically for hot reloads — prefer it over clearing and re-registering, which
can expose a half-built registry to a concurrent turn.

Registration is **all-or-nothing**: one bad configuration raises `AgentConfigurationError` and
leaves the previous registry serving.

## Common mistakes

- **Not declaring capabilities**, then debugging the prompt. Read the diagnostics.
- **Assuming a published action executed.** It did not; you execute it.
- **Discarding a response because it has diagnostics.** Check `acceptance_status`.
- **Reading the merged `acceptance_status` as per-agent.** Use `acceptance_by_agent`.
