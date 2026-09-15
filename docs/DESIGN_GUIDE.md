# Design guide

**Applies to runtime:** 3.1.5

How to use this framework well. The [API reference](API_REFERENCE.md) says what each piece is;
this says what to do with them, and — more often — what not to.

> This guide replaces the design half of the original Playbook, revalidated against the current runtime. The
> Playbook is preserved as a historical document at
> [archive/PLAYBOOK_v2.2.md](archive/PLAYBOOK_v2.2.md); where the two disagree, this one is
> current.

## The product is restraint

A swarm that comments on everything is worse than no swarm. The scarce resource is the
principal's attention, and every insight spends some of it.

So the framework's defaults run the other way from most agent frameworks: **silence is the
normal outcome**, an agent must pass an explicit gate to speak, and a response that fails any
check is discarded whole rather than partially applied. None of that is incidental — it is the
thing being engineered.

Practically, this means the quality bar for an agent is not "does it produce good text" but
"does it stay quiet when it has nothing". An agent that speaks every turn is a bug even when
every sentence is correct.

## Many small observers, not one large assistant

Prefer several narrow agents over one that does everything.

A narrow agent has a purpose you can state in a sentence, a trigger you can justify, and a
failure you can recognize. Its prompt can be short and specific. You can turn it off when it
misfires without losing the rest. And because agents run concurrently and most stay silent, the
cost of an extra observer is close to zero.

A single broad agent has none of those properties. It is also the shape that produces the
characteristic failure of this product category: plausible commentary that nobody asked for.

**A useful test:** if you cannot say what would make this agent *wrong*, it is too broad.

## What the engine owns, and what you do

This boundary is the one most worth internalizing, because the framework deliberately stops
short of your product.

| The engine | Your host |
|---|---|
| Decides which agents are eligible this turn | Decides what appears on screen, and when |
| Generates the output contract each agent is held to | Renders insights; owns tone, layout, timing |
| Validates everything produced, at one boundary | Executes UI actions the engine validated |
| Commits permitted state to the blackboard | Declares what it can present and what it permits |
| Says what an agent is *permitted* to say | Says what the user actually sees |

The engine never renders and never executes an action. When it publishes a widget action it is
saying "this was well-formed and you authorized it" — not "this happened".

The corollary matters: **capabilities are yours to declare.** An agent cannot grant itself the
right to ask the principal a question, to correct itself, or to drive a widget. If you do not
declare those, they do not exist for the run, and the framework will quietly narrow rather than
guess. See [host integration](guides/host-integration.md).

## Trust levels are not visible in a type

Three kinds of data flow through an insight and they warrant different trust:

- **Model-authored** — validated, still untrusted. It passed a shape check; that is all.
- **Host-supplied** — declarations you made before the run.
- **Engine-derived** — stamped at acceptance; no producer can set these.

The failure this prevents is subtle and common: reading a model's own claim about itself as
evidence. `confidence: 1.0` on an insight whose model offered no estimate is a placeholder, not
an assessment — `confidence_provided` is the field that knows. Design your UI against the
engine-derived fields, not the model-authored ones, wherever the difference matters.

## Coordination through state, not conversation

Agents do not talk to each other. They read and propose changes to shared state, and the engine
commits what is permitted at its merge boundary.

That indirection is what keeps a swarm debuggable: every effect has one writer, one commit
point, and one place to look when it is wrong. Reach for an event when one agent's finding
should wake another; reach for a fact when something extracted should persist; reach for a
variable when it is session state. See [orchestration](guides/orchestration.md).

Resist the urge to make agents aware of each other. Two agents that need to coordinate directly
are usually one agent.

## Fail closed, and loudly

Every error path in this framework returns a safe default and says so. An unevaluable trigger
condition suppresses the agent. An unknown insight type is rejected rather than relabelled. A
missing capability withdraws the capability. A malformed response is discarded whole.

The cost is that misconfiguration can look like quiet correctness — an agent that never speaks
because a typo withdrew its permissions looks identical to an agent with nothing to say. That
is why diagnostics exist and why `capability_unavailable` appears on *accepted* responses. When
an agent is mysteriously silent, read the diagnostics before reading the prompt.

## When not to use this

Be honest about the fit. This framework is built for **many cheap observers over a live,
turn-based conversation, where most of them should stay quiet.**

It is a poor fit for a single conversational assistant that should respond to every message —
you want a chat loop, not a swarm. It is a poor fit for batch analysis over completed
transcripts, where you do not need eligibility, cooldowns or restraint. And it is a poor fit if
your host cannot supply conversation turns, because everything here is anchored to a turn.

## Where to go next

| | |
|---|---|
| Write your first agent | [Authoring agents](guides/authoring-agents.md) |
| Make several agents work together | [Orchestration](guides/orchestration.md) |
| Wire capabilities and read results | [Host integration](guides/host-integration.md) |
| Generate long-form output safely | [Long-form content](guides/long-form-content.md) |
