<!--
  THE XUBB AGENTS PLAYBOOK
  Synthesized from a 10-agent deep analysis of the v2.2 codebase.
  Every pattern is grounded in the real code under core/, library/, utils/.
-->

# The Xubb Agents Playbook
### The secret formula for building a world-class real-time conversational copilot on `xubb_agents`

**For:** engineers building a live HUD/overlay copilot on the `xubb_agents` framework (v2.2) — something that listens to a conversation as it happens, understands it, and surfaces the *right* insight at the *right* moment.

**What this is (and isn't):** the README and the technical spec tell you *what each piece is*. This playbook tells you *how to compose the pieces into something magical* — the design philosophy, the high-leverage patterns, the anti-patterns, and the non-obvious moves that separate a mediocre agent suite from a copilot people trust. It is opinionated on purpose. Every claim is grounded in the real v2.2 code.

---

## The thesis (read this twice)

> **`xubb_agents` is a reactive, blackboard-coordinated *swarm of cheap, specialized observers* that build a shared understanding of a live conversation and surface ephemeral, *earned* insights.**

Mastery is four moves:

1. **Decompose** intelligence into many cheap single-purpose agents — not one mega-prompt.
2. **Coordinate** them through the Blackboard (a shared world-model), not through code that calls code.
3. **Gate ruthlessly** for cost *and* relevance — most agents should run, and say, nothing most of the time.
4. **Translate** accumulated understanding into perfectly-timed HUD moments.

And the one idea that ties them together:

> **Restraint is the product. Silence is the default. A visible insight is rare, earned, and therefore trusted.**

A copilot that speaks on 5% of turns and is right beats one that speaks every turn and is ignored. The entire framework is engineered to make silence the easy path — and this playbook is largely the art of spending the few moments you *do* speak.

---

## The 10 Laws of the Secret Formula (the whole playbook on one page)

1. **Silence is a feature.** Agents return nothing far more often than something; gate-less schemas default to silent; the runtime biases toward not speaking. Engineer for it.
2. **Many cheap observers beat one mega-prompt.** Independent gating, free parallelism, fault isolation, and composability all come from decomposition.
3. **Gate up the funnel, fail down to silence.** `trigger_type` → `trigger_conditions` (free, pre-LLM) → `cooldown` → `evaluate()`. Reject as high as possible; the only expensive step is last.
4. **Detect cheap, analyze expensive.** A `gpt-4o-mini` detector notices on every turn and emits an event; a premium analyzer fires only in Phase 2 when an event has *earned* it.
5. **Choreograph, don't orchestrate.** Agents couple through event-name strings and the Blackboard — never by calling each other. Cross-agent reaction is cross-*phase* (emit an event into Phase 2).
6. **The Blackboard is the mind; agents are disposable.** Persist all understanding to the board (Variables / Events / Queues / Facts / Memory), never to `self`. Get the board's schema right and the eleventh agent is free.
7. **Priority is authority.** Facts resolve by agent **priority** first (then confidence). To make an extractor canonical, raise its agent priority — not its confidence.
8. **The agent is the config.** A whole `DynamicAgent` — persona, when, output-shape, and whether-it-speaks — is four orthogonal JSON dials. Tune dials, not code.
9. **Roles are diffs, not forks.** Adapt the swarm per user/context with `AgentConfigOverride` (cooldown / context / instructions), recomputed every turn. The base swarm never changes.
10. **The insight list is a menu, not a render queue.** The engine hands you `List[AgentInsight]` precisely so you *curate to one*. `for i in insights: hud.show(i)` is the canonical spam bug.

---

## How to read this

- **Chapters 1–5** build the mental model and the orchestration core: philosophy, single-agent design, the Blackboard, triggers/conditions, and multi-agent choreography. Read these in order.
- **Chapters 6–9** are the craft: building agents from config, accumulating understanding over time, the HUD/insight UX, and runtime adaptability (Roles).
- **Chapter 10** is production: cost, latency, resilience, observability, scale, and the host loop.
- **The Capstone** designs a complete copilot agent suite end-to-end, threading every chapter together — the secret formula made concrete.

## Table of contents

1. [Philosophy & Mental Models](#chapter-1--philosophy--mental-models)
2. [Agent Archetypes & Single-Agent Design](#chapter-2--agent-archetypes--single-agent-design)
3. [The Blackboard: the Nervous System](#chapter-3--the-blackboard-the-nervous-system)
4. [Triggers & Conditions: the Reactive Control Plane](#chapter-4--triggers--conditions-the-reactive-control-plane)
5. [Multi-Agent Orchestration & Choreography](#chapter-5--multi-agent-orchestration--choreography)
6. [DynamicAgent: Prompt & Schema Engineering](#chapter-6--dynamicagent-prompt--schema-engineering)
7. [Memory, Facts & Understanding Over Time](#chapter-7--memory-facts--understanding-over-time)
8. [The Real-Time HUD / Insight UX Playbook](#chapter-8--the-real-time-hud--insight-ux-playbook)
9. [Roles, Configuration & Adaptability](#chapter-9--roles-configuration--adaptability)
10. [Production: Cost, Latency, Resilience, Observability & Scale](#chapter-10--production-cost-latency-resilience-observability--scale)
11. [Capstone: Designing a Complete Copilot Agent Suite](#capstone--designing-a-complete-copilot-agent-suite)

---
# Chapter 1 — Philosophy & Mental Models

> **Playbook thesis:** `xubb_agents` is a **reactive, blackboard-coordinated swarm of cheap, specialized observers** that build a shared understanding of a live conversation and surface **ephemeral, earned** insights. Mastery is four moves: (1) decompose intelligence into many cheap single-purpose agents, (2) coordinate through the blackboard, not one mega-prompt, (3) gate ruthlessly for cost and relevance, and (4) translate accumulated understanding into perfectly-timed HUD moments. **Restraint — silence as the default — is a feature, not a gap.**

This chapter sets the altitude. Before you write a single agent config, you have to internalize *what kind of system this is*. Most teams arriving from a chatbot or RAG background reach for the wrong mental model and end up fighting the framework. The framework is small, opinionated, and honest about what it is. Operate at its altitude and it will feel like the obvious tool. Operate above it (treating it as an app) or below it (treating it as a raw LLM SDK) and you will reinvent — badly — the things it already guarantees.

---

## 1. What `xubb_agents` fundamentally IS

It is a **library**, not an application. The README is explicit: it is "a separate product/project that provides the agent framework... consumed by `xubb_server` and other applications." It does not own the microphone, the transcription, the UI, the session store, or the keyword scanner. It owns exactly one thing: **turning a snapshot of conversational context into a set of structured insights and state updates, by running a swarm of agents.**

Concretely, the entire surface area you orchestrate against is one method:

```python
response = await engine.process_turn(
    context,                              # AgentContext: transcript window + blackboard
    allowed_agent_ids=None,               # optional host filter
    trigger_type=TriggerType.TURN_BASED,  # what woke the swarm
    trigger_metadata=None,
)
# response.insights        -> ephemeral HUD moments
# response.events/facts/...  -> accumulated shared understanding
```

Everything else — `Blackboard`, `DynamicAgent`, `ConditionEvaluator`, `LLMClient`, the multi-phase merge — exists to make that one call fast, cheap, coordinated, and crash-safe.

### The "swarm of cheap observers" mental model

Do not picture one smart assistant. Picture a **room full of cheap, narrow specialists** all watching the same live transcript through the same one-way glass, each with a single job and a strict cooldown, most of whom say nothing most of the time. They share a whiteboard (the Blackboard). When one of them notices something worth telling the others, it pins a note on the board (an `Event` or `Fact`), and the right specialist wakes up to react.

This is the **Blackboard architecture** — a classic AI coordination pattern, and the framework names it as such. Five typed containers make up the whiteboard (`core/blackboard.py`):

| Container | Whiteboard role | Lifetime |
|-----------|-----------------|----------|
| **Variables** | "the current state is X" (`phase`, `sentiment`) | Session |
| **Events** | "something just happened" — transient signals between agents | **Cleared after every turn** |
| **Queues** | ordered work items (pending questions, action items) | Session |
| **Facts** | extracted knowledge with confidence + priority | Session |
| **Memory** | each agent's private scratchpad | Session |

The agents never call each other. They never know each other exists. They coordinate *only* through what they read from and write to this whiteboard. That decoupling is the whole point — it is what lets you grow from three agents to thirty without the combinatorial mess of direct wiring.

### Reactive / event-driven, NOT request-response

Architectural Principle #1 in the technical spec: **"Agents do not run continuously. They are dormant until triggered."** This is the single biggest mindset shift. You are not building a request-response service where a user asks and the system answers. You are building a **reactive system** that *observes a stream* and occasionally *reacts*.

There are six trigger types (`TriggerType` in `core/models.py`), and they encode the reactive vocabulary:

- `TURN_BASED` — a speaker finished a turn (the default heartbeat)
- `KEYWORD` — a watched term appeared (price, "cancel", a competitor name)
- `SILENCE` — dead air crossed a threshold (the meeting stalled)
- `INTERVAL` — a periodic background sweep
- `EVENT` — *another agent* pinned a note that woke this one
- `FORCE` — the human hit a button; bypass cooldown and conditions entirely

Notice what is *not* here: there is no "user prompt." The conversation is not addressed *to* the system. The system is eavesdropping, and most of the time the correct reaction to eavesdropping is to keep quiet.

### Stateless agents over a stateful board

Principle #2: **"Stateless Execution (mostly)."** Each agent evaluation is fresh — it receives an `AgentContext` (transcript window + a read-only blackboard snapshot) and returns an `AgentResponse`. The agent holds no durable state of its own; durable understanding lives on the Blackboard. This is why a host can re-instantiate every agent on every turn and lose nothing — v2.2's MR-1 fix syncs `blackboard.memory[id]` back into context before agents run, so even an agent's "private memory" is really board-backed (`engine._sync_state_to_legacy`). The lesson: **trust the board, not the agent object.** Agents are disposable; the board is the mind.

---

## 2. Why many small agents beat one mega-prompt

The instinct of every team is to write one giant system prompt: "You are a sales copilot. Watch the conversation. Detect objections, extract budget, track stakeholders, flag compliance issues, suggest next questions, and..." This is the anti-pattern the framework is built to prevent. Here is why the swarm wins.

**Independent gating.** Each agent has its own `trigger_config` (when to wake) and `trigger_conditions` (preconditions on board state). A budget-extractor can run only when the keyword "budget" appears; a closing-coach can run only when `phase == "negotiation"` and a budget fact exists. A mega-prompt has one gate: it runs or it doesn't, and you pay for the entire reasoning surface every time. The swarm pays only for the specialists whose preconditions are actually met. The `ConditionEvaluator` exists precisely so most agents *skip* most turns without ever touching the LLM.

**Cheap, narrow models.** A single-purpose agent ("is this a question? emit `question_detected` if so") runs reliably on `gpt-4o-mini` with a tiny prompt and a tiny context window (`model_config.context_turns`). You can't shrink a mega-prompt's model without degrading all of its jobs at once. Many cheap specialists cost far less than one expensive generalist asked to do everything every turn.

**Parallelism for free.** Principle #3: all eligible agents in a phase run concurrently via `asyncio.gather` (`engine._run_phase`). Thirty narrow agents finish in roughly the latency of the slowest one. A mega-prompt is one serial, long generation — strictly slower for a live HUD where every hundred milliseconds shows.

**Fault isolation.** Principle #4, Graceful Degradation: `_run_agent_safe` catches any single agent's failure, logs it, and returns `None` — the turn proceeds with the survivors. One specialist hitting a malformed-JSON error or an LLM timeout does not blank your HUD. In a mega-prompt, one bad token taints the *entire* output.

**Composability and ownership.** Specialists are independently testable, independently versioned, independently owned. You can add a "competitor-mention detector" next sprint without touching the objection-handler. The blackboard is the contract between them, so they never collide in code — only, deliberately, on the board (and even then, fact conflicts resolve by priority → confidence → registration order, F-1/INV-9).

**Snapshot determinism.** Principle #5: within a phase, every agent reads the *same immutable snapshot* of the board; writes merge only after all agents finish (`_run_phase` → `_merge_responses`). So agents can't see each other's half-written state mid-phase. This is what makes a swarm reasoned-about instead of a race condition. A mega-prompt has no such structure because it has no parallel parts to coordinate.

> **The decomposition test:** if you can describe an agent's job in one sentence without the word "and," it is correctly scoped. "Detect price objections." "Extract the stated budget." "Suggest a follow-up question when a question went unanswered." The moment you need "and," split it into two agents and let them talk through the board.

---

## 3. The HUD-restraint principle: silence is the default

This is the soul of the playbook and the thing newcomers get most wrong. The product is a **HUD** — a live overlay whispering in the human's ear. The executive summary's tagline is *"AI that whispers in your ear, not speaks for you."* A HUD that talks constantly is noise; the human stops looking. **The scarcest resource in a conversational copilot is the user's attention, and every insight you surface spends it.**

The framework is engineered, top to bottom, so that **saying nothing is the natural resting state**:

- **Cooldowns** (`trigger_config.cooldown`, enforced in `BaseAgent.process()`) mean an agent physically cannot fire again for N seconds even if it wants to. Restraint is wired into the clock.
- **Trigger conditions fail closed** (C-1, v2.2): a typo'd or unknown operator now evaluates to `False`, so a misconfigured agent stays *silent* rather than firing every turn. The framework biases every ambiguity toward silence.
- **Gate-less schemas default to silence** (A-1, v2.2): a custom output schema with no gate field and no root key stays silent unless it explicitly opts in with `speak_without_gate: true`. You have to *earn the right to speak* by declaring you mean to.
- **Separation of observe vs. speak:** an agent can return a perfectly valid `AgentResponse` with rich `facts`, `events`, and `variable_updates` and **zero `insights`**. It updated the shared understanding without spending a single photon of the user's attention. This is the most underused move in the framework — see §5.

So the design intent is: **agents observe constantly and accumulate quietly; they surface an insight only when one is genuinely earned.** An insight is "earned" when the accumulated state on the board crosses a threshold that the human actually needs to know about *right now*. The job of a good agent team is mostly to *not* show things.

### Ephemeral insights: earned AND expiring

Every `AgentInsight` carries an `expiry` (default 15 seconds; `core/models.py`). Insights are not log entries; they are **moments**. They appear, they are relevant for a window, and they are meant to disappear:

```python
class AgentInsight(BaseModel):
    type: InsightType          # SUGGESTION, WARNING, OPPORTUNITY, FACT, PRAISE, ERROR
    content: str
    confidence: float = 1.0
    expiry: int = 15           # seconds to display — the insight is EPHEMERAL by design
    action_label: Optional[str] = None
    metadata: Dict[str, Any] = {}   # UI hints: zone, color, voice style
```

The `InsightType` enum encodes urgency *and* HUD placement: `WARNING` and `OPPORTUNITY` are the urgent Zone-A interrupts ("price objection — focus on value"); `SUGGESTION` and `FACT` are passive Zone-C context; `PRAISE` is reinforcement; `ERROR` is for system alerts. The type is not cosmetic — it is the agent telling the HUD *how loudly to whisper and for how long*.

The mental shift: a HUD moment is a **perishable good**. "The customer just mentioned a competitor" matters for the next ten seconds and is worthless after the topic moves on. v2.2's S-1 fix exists precisely because schemas were *requesting* `expiry`/`action_label` from the model and silently dropping them — the framework now honors per-insight timing because timing *is* the product.

---

## 4. When `xubb_agents` is the right tool

A sharp mental model includes knowing when *not* to reach for it. Three regimes:

**Use a single LLM call when** the task is a one-shot question with a one-shot answer and no live stream: "summarize this finished transcript," "answer this user's question." There is no conversation to observe over time, no swarm to coordinate, no attention budget to ration. `process_turn` would be ceremony around one `generate_json`.

**Use a batch / post-hoc pipeline when** timing doesn't matter and you can see the whole conversation at once: call-quality scoring, compliance audits after the fact, analytics dashboards. The executive summary draws this line explicitly — post-hoc analysis arrives "after the moment has passed." If "during the conversation" is not a requirement, you do not need a reactive swarm; you need a report.

**Use `xubb_agents` when ALL of these hold:**

1. The input is a **live, growing transcript** (a conversation in flight), not a fixed document.
2. The value is **in-the-moment** — an insight is worth far more now than thirty seconds later.
3. The intelligence **decomposes** into multiple distinct concerns (objections, budget, questions, compliance, sentiment...) that benefit from independent gating and coordination.
4. **Restraint matters** — the right output most of the time is nothing, and surfacing too much actively harms the experience.
5. You need **sub-second, parallel, fault-isolated** execution that won't blank the HUD when one specialist trips.

That intersection — live + ephemeral + decomposable + restrained + real-time — is exactly the conversational-copilot shape the framework was carved for. Outside it, simpler tools win.

---

## 5. The core loop (how a turn actually flows)

Tie it together with the real reactive cycle, grounded in `engine.process_turn` → `_process_turn_inner`:

1. **Host feeds a turn.** Transcription produces a segment; the host appends it, bumps `turn_count`, builds an `AgentContext` (recent segments window + the session's `Blackboard`), and calls `process_turn` with a `trigger_type`. *The host owns the stream; the engine owns the reaction.*

2. **Engine stamps and syncs.** It sets engine-owned `sys.*` variables (`sys.turn_count`, `sys.trigger_type`, ...) and syncs board variables + per-agent memory into the legacy `shared_state` read-path (`_sync_state_to_legacy`, MR-1/INV-14).

3. **Engine routes — Phase 1.** `_get_eligible_agents` computes the intersection of: the host allow-list, trigger-type match, and `trigger_conditions` against the board. Ineligible agents are *skipped before any LLM call* and reported via `on_agent_skipped`. **This is the cost gate. Most agents die here, cheaply, every turn — and that is correct.**

4. **Eligible agents observe in parallel.** All survivors evaluate against the *same immutable snapshot* (`_run_phase`), concurrently, each wrapped in `_run_agent_safe`. Each returns an `AgentResponse`: maybe insights, maybe just facts/events/variable updates, maybe nothing.

5. **Blackboard accumulates.** `_merge_responses` applies updates in ascending priority order (higher priority writes last, wins) — variables, queues, facts (priority-stamped, conflict-resolved), memory. The shared understanding grows. Events emitted in Phase 1 are pinned to the board.

6. **Reaction cascade — Phase 2.** If Phase 1 emitted any events and `max_phases >= 2`, the engine flips `trigger_type` to `EVENT`, finds the subscribers (`get_event_subscribers`), and runs them — exception-safely restoring `trigger_type`/`phase` in a `finally` even if Phase 2 raises (E-1/INV-12). This is one specialist's note waking another. *(Phase 2 events are recorded but not re-dispatched — the cascade is bounded to one hop, by design.)*

7. **Surface and forget.** Events are cleared from the board (they are transient). The aggregated `AgentResponse` returns to the host with the earned `insights`. The host renders them to the HUD with their `expiry` and lets them perish. The board's durable understanding (variables, queues, facts, memory) persists into the next turn.

Then it waits. Dormant again until the next trigger. **Observe → accumulate → (rarely) surface → forget → wait.** That is the heartbeat.

---

## 6. The mindset shifts a team must make

| From (wrong altitude) | To (right altitude) |
|---|---|
| "One assistant that does everything" | A swarm of cheap, one-sentence specialists |
| Request → response | Stream observed → occasional reaction |
| State lives in my app objects | Understanding lives on the Blackboard; agents are disposable |
| More output = more value | **Less output = more value**; attention is the scarce resource |
| Insights are answers/logs | Insights are perishable, expiring HUD moments |
| Agents call each other | Agents coordinate only through events/facts on the board |
| Make it smart | Make it cheap, gated, and quiet — then surface only what's earned |
| Handle every conversation centrally | Gate ruthlessly so most agents skip most turns for free |

---

## 7. Anti-patterns (do NOT do — and why)

- **The mega-prompt.** One agent with a sprawling "do everything" prompt. *Why it's wrong:* you forfeit independent gating, cheap models, parallelism, fault isolation, and composability — every advantage the framework offers. Decompose.
- **The chatterbox.** Agents that emit an insight on nearly every turn. *Why it's wrong:* it floods the HUD, burns the user's attention budget, and trains them to ignore the overlay. Default to silence; emit only earned moments. Use cooldowns and conditions to enforce it.
- **No gates.** Agents with `TURN_BASED` and no `trigger_conditions`, all firing every turn. *Why it's wrong:* you pay for an LLM call per agent per turn for output you mostly discard. Conditions exist to skip *before* the LLM. (And note A-1: an ungated custom schema now stays silent by default anyway.)
- **Treating insights as permanent.** Ignoring `expiry`, accumulating insights like a log. *Why it's wrong:* a HUD is moments, not history. Stale advice on a fast-moving conversation is worse than no advice. Honor `expiry`; let moments perish.
- **Side-channel coordination.** Wiring agents to call each other or sharing state through host globals. *Why it's wrong:* you lose snapshot determinism, the priority-ordered merge, and the decoupling that makes the swarm scale. Coordinate *only* through the board (events/facts/queues/variables).
- **Trusting the agent object's memory.** Stashing durable state on the Python agent instance. *Why it's wrong:* hosts re-instantiate agents per turn; only board-backed memory (synced via MR-1) survives. Persist understanding to the Blackboard, not to `self`.
- **Mistaking the library for the app.** Expecting the framework to do transcription, keyword scanning, persistence, or UI. *Why it's wrong:* it deliberately doesn't — keyword detection is host responsibility (`check_keyword_triggers` is only a helper), the board is in-memory only, and there is no UI. Own the plumbing yourself; let the framework own the reaction.

---

## Secret formula — the non-obvious, high-leverage moves

- **Silence is a feature, not a missing one.** The whole runtime biases toward not speaking — cooldowns, fail-closed conditions, gate-less-defaults-to-silent (A-1). Lean into it. Your best agents will be quiet 95% of the time. Measure restraint as a quality metric, not just hit rate.
- **Separate "observing" from "speaking."** The most underused capability: an agent can return facts/events/variable updates with **zero insights**. Build a layer of silent observer-agents that only enrich the board, and a thin layer of speaker-agents gated on the accumulated state. Understanding compounds for free; the HUD stays calm.
- **Gate before you generate, not after.** `trigger_conditions` run in the engine *before* any LLM call. Push every cheap precondition (phase, fact-exists, queue-not-empty, `mod` on turn_count) into conditions so the LLM only ever sees turns that already matter. This is your single biggest cost lever.
- **Let the board do the thinking; let events do the waking.** Don't poll state in prompts. Have observer-agents emit events (`objection_raised`, `question_detected`) and let Phase-2 subscribers react. One-sentence agents + a pub/sub board scale where a mega-prompt collapses.
- **Treat `expiry` and `InsightType` as the product.** Timing and urgency-zone are not metadata — they *are* the HUD experience. A `WARNING` at 8s and a `FACT` at 20s are different products. Tune them per insight; v2.2 (S-1) finally honors what the schema requests.
- **Agents are disposable; the Blackboard is the mind.** Design as if every agent is destroyed and rebuilt each turn (because it may be). Persist all understanding to the board; never to `self`.

---

*Next chapter: how the Blackboard's five containers turn a swarm of strangers into a coordinated team — and the precise contracts (priority, confidence, snapshot semantics) that keep them honest.*
# Chapter 2 — Agent Archetypes & Single-Agent Design

> **Thesis of this chapter:** A great copilot is not one clever agent. It is a *swarm of cheap, single-purpose observers*, most of which stay silent most of the time, coordinated through a blackboard, with a tiny number of expensive agents that only wake up when a cheap one has already proven there is something worth thinking about. Design each agent to do *one job*, gate it ruthlessly, and reach for a premium model only where it earns its cost.

---

## 2.1 Mental model: an agent is a gated function over a sliding window

Strip away the configuration and a `xubb_agents` agent is exactly one thing — an implementation of `BaseAgent.evaluate()`:

```python
# core/agent.py
@abstractmethod
async def evaluate(self, context: AgentContext) -> Optional[AgentResponse]:
    """The brain of the agent. Must be implemented by subclasses."""
```

Everything else is plumbing around that method. `BaseAgent.process()` is the public entry point the engine calls, and before it ever reaches your `evaluate()` it enforces two gates and updates one clock:

1. **Trigger-type gate** — `if not is_force and context.trigger_type not in self.config.trigger_types: return None`. If this run's trigger isn't one your agent subscribes to, you never run.
2. **Cooldown gate** — `if (now - self.last_run_time) < effective_cooldown: return None`. Even when the trigger matches, you stay quiet until your cooldown has elapsed (the `effective_cooldown` can be widened/narrowed by a per-agent role override's `cooldown_modifier`, floored at 5s).
3. **`FORCE` bypass** — a `TriggerType.FORCE` run (user pressed "talk now") skips *both* gates; the engine has already decided eligibility.

The critical design consequence: **`process()` returns `None` far more often than it returns an `AgentResponse`.** Silence is the default path through the code, not an error path. Notice too that `self.last_run_time = now` lives in the `finally` block — your cooldown clock advances on success *and* failure (the comment calls this "B4"). An agent that errors out still respects its own cooldown, so a flapping agent can't hammer the LLM.

The context your `evaluate()` receives (`AgentContext` in `core/models.py`) is the whole sensory world of the agent: `recent_segments` (the sliding transcript window), the shared `blackboard`, `trigger_type` + `trigger_metadata` (e.g. which keyword matched, how many seconds of silence), `turn_count`, `phase`, optional `rag_docs`, and `user_context`. An agent is a pure-ish function of *this snapshot* — and during a phase every agent sees the **same immutable snapshot** (`_run_phase` builds one `blackboard.snapshot()` and a deep-copied `shared_state` for all agents). You read the world as it was at turn start; your writes are merged afterward.

### The output: an `AgentResponse` is a multi-channel emission

`evaluate()` returns an `AgentResponse` (or `None`). It is *not* just "a message." Its channels (`core/models.py`) are the vocabulary of the whole swarm:

| Channel | Field | Used by archetype |
| --- | --- | --- |
| HUD insights | `insights: List[AgentInsight]` | Advisor / Coach / Monitor |
| Coordination signals | `events: List[Event]` | Detector (fan-out trigger) |
| Extracted knowledge | `facts: List[Fact]` | Extractor |
| Shared state | `variable_updates: Dict` | Monitor (thresholds), Extractor |
| Work queues | `queue_pushes: Dict[str, List]` | producers/consumers |
| Private scratchpad | `memory_updates: Dict` | any stateful agent |

A single agent rarely touches more than one or two of these. *Which* channels an agent emits on is what defines its archetype.

---

## 2.2 The single-responsibility principle: one agent = one job

The temptation, coming from a chatbot mindset, is to build one omniscient "assistant" agent with a 2,000-token system prompt that detects questions, extracts the budget, watches the talk-time ratio, *and* coaches the rep. Resist it. In this framework, that is an anti-pattern with a name (§2.7, the Mega-Agent).

Single-responsibility wins for concrete, mechanical reasons baked into the engine:

- **Independent gating.** Each agent carries its own `trigger_types`, `cooldown`, `priority`, and `model`. A question-detector that should fire on *every keyword* and a strategy-advisor that should fire *at most every 45s* cannot share one config. Split them and each gets the exact cadence it needs.
- **Independent failure.** `_run_agent_safe` runs agents with `asyncio.gather` and discards `None` results. If your fact-extractor throws, the coach still speaks. A mega-agent is all-or-nothing.
- **Independent cost.** Per-agent `model` means a trivial detector can run on a cheap model while one premium agent runs on a frontier model. A mega-agent forces *one* model choice on *all* its jobs — you either overpay for detection or underpay for reasoning.
- **Composability via blackboard.** Small agents coordinate through `events`, `facts`, and `variables` rather than through a shared mega-prompt. That's what makes the swarm reactive instead of monolithic.

A good litmus test: *if you can't describe the agent's job in one sentence without using "and," split it.*

---

## 2.3 The four canonical copilot archetypes

These aren't framework classes — they're *design patterns* expressed through `AgentConfig` + which `AgentResponse` channels you emit. All four can be a `DynamicAgent` (config only) or a custom `BaseAgent` subclass.

### Detector — cheap, fast, emits events (not insights)

The workhorse of the swarm. A detector answers one yes/no question about the latest turn ("was a question asked?", "did the prospect object?") and, when yes, emits an **event** — it usually says *nothing* to the HUD. It is the cheapest possible agent: small prompt, cheapest model, short cooldown (or keyword-triggered for near-zero latency).

```python
# A pure detector as config (DynamicAgent). Emits an event, no insight.
question_detector = {
    "id": "question_detector",
    "name": "Question Detector",
    "text": (
        "You watch the transcript for the OTHER party asking the user a "
        "direct question. If and only if the most recent turn contains a "
        "question aimed at the user, emit a 'question_detected' event with "
        "the question text as payload. Do NOT produce an insight."
    ),
    "output_format": "default_v2",
    "model": "gpt-4o-mini",
    "trigger_config": {"mode": "turn_based", "cooldown": 5, "priority": 0},
}
```

Because `default_v2`'s gate field is `has_insight`, leaving `has_insight=false` keeps the HUD clean while the `events` array still flows through. The detector's whole value is the event it drops on the blackboard for *someone else* to react to.

### Extractor — pulls facts into the blackboard

An extractor's job is to turn unstructured speech into structured `Fact`s (`type`, `key`, `value`, `confidence`). It typically emits on the `facts` channel and stays silent on the HUD. Facts are **deduplicated by `(type, key)`** by the blackboard, and on conflict *higher priority wins, then higher confidence* (see the `Fact` docstring and the `_merge_responses` INV-9 comment). Extractors are how the copilot accumulates a memory of the conversation: budget, timeline, stakeholders.

```python
# An extractor as config. Emits facts, no HUD noise.
fact_extractor = {
    "id": "fact_extractor",
    "name": "Deal Fact Extractor",
    "text": (
        "Extract concrete deal facts from the conversation: budget, timeline, "
        "named stakeholders, competitors. Emit each as a fact with a stable "
        "'type' and 'key'. Do not repeat facts you've already extracted "
        "(check {{ blackboard.facts }}). Stay silent on the HUD."
    ),
    "output_format": "default_v2",
    "model": "gpt-4o-mini",
    "trigger_config": {"mode": "turn_based", "cooldown": 20},
}
```

Note the Jinja2 `{{ blackboard.facts }}` in the prompt — `DynamicAgent` renders the system prompt against `blackboard`, `state`, `memory`, and `user_context` (see `evaluate()`), so an extractor can *see what's already known* and avoid re-emitting it.

### Advisor / Coach — emits insights to the HUD

The advisor is the only archetype whose primary product is an `AgentInsight` the user actually sees. Because HUD space and user attention are scarce, advisors must be the **most ruthlessly gated** archetype: long cooldowns, tight `trigger_conditions`, and a hard "stay silent unless it really matters" instruction. An advisor sets `expiry` (how long the chip lives, default 15s) and optionally an `action_label`.

```python
# core/agent.py — create_insight is the canonical way to build one
insight = self.create_insight(
    content="They raised a pricing objection — anchor on ROI, not discount.",
    type=InsightType.SUGGESTION,
    confidence=0.8,
    expiry=20,
    action_label="Show ROI calc",
)
```

The best advisors don't run every turn. They run in **Phase 2**, woken by a detector's event (next section) — meaning the advisor only spends premium tokens once a cheap detector has already confirmed there's a coaching moment.

### Monitor — watches thresholds, mostly silent

A monitor tracks a running quantity across turns (talk-time ratio, sentiment trend, time-since-last-question, filler-word rate) and fires only when a threshold is crossed. Monitors live on **`variable_updates`** (to accumulate the running value on the blackboard) plus an occasional **insight** when the threshold trips. They pair naturally with `trigger_conditions` so the *engine* gates them on blackboard state before the agent even runs, and with `TriggerType.INTERVAL` or `TriggerType.SILENCE` for time-based watching.

```python
talk_ratio_monitor = {
    "id": "talk_ratio_monitor",
    "name": "Talk-Time Monitor",
    "text": (
        "Track the ratio of user words to other-party words across the call, "
        "storing it in variable 'talk_ratio'. Only produce a warning insight "
        "if the user is dominating (>70%) AND you haven't warned recently."
    ),
    "output_format": "default_v2",
    "model": "gpt-4o-mini",
    "trigger_config": {"mode": "interval", "cooldown": 30},
    # Engine-side gate: don't even run until enough turns exist to judge.
    "trigger_conditions": {"var": "sys.turn_count", "gte": 6},
}
```

---

## 2.4 The secret weapon: the cheap-detector → expensive-analyzer cascade

This is the single most important cost-and-quality pattern in the framework, and it falls directly out of the engine's **two-phase execution** (`_process_turn_inner`):

- **Phase 1** runs all eligible normal agents in parallel against the snapshot, then collects every `Event` they emitted and applies them to the blackboard.
- **Phase 2** runs *only* the agents subscribed to those events (`get_event_subscribers`), and *only if* events were actually emitted (`if all_events and self.max_phases >= 2`).

So the pattern is:

> **A swarm of cheap detectors runs every turn on the cheapest model and emits events. An expensive analyzer subscribes to those events and runs only in Phase 2 — i.e. only on the turns where a detector already proved there's something worth the spend.**

The cheap detector pays a few hundred tokens on `gpt-4o-mini` every turn. The expensive analyzer pays its premium-model cost *only* on the small fraction of turns that contain a real question/objection. On a quiet call, the analyzer may never run at all.

### How to wire it (config)

The detector from §2.3 emits `question_detected`. The analyzer subscribes to it:

```python
objection_strategist = {
    "id": "objection_strategist",
    "name": "Objection Strategist",
    "text": (
        "A question/objection was just detected. Read the full context and the "
        "known deal facts ({{ blackboard.facts }}), then give ONE sharp, "
        "specific coaching line for how the user should respond right now."
    ),
    "output_format": "default_v2",
    "model": "gpt-4o",                       # premium — but only Phase 2
    "trigger_config": {
        "mode": "event",                     # EVENT trigger type
        "subscribed_events": ["question_detected", "objection_raised"],
        "cooldown": 15,
    },
}
```

Two engine facts make this robust:

- **Auto-EVENT normalization (DynamicAgent only).** In `DynamicAgent.__init__`, if `subscribed_events` is non-empty it auto-adds `TriggerType.EVENT` to `trigger_types`. A *custom* `BaseAgent` subclass does **not** get this convenience — you must put `TriggerType.EVENT` in its config yourself, or `get_event_subscribers` will log an E-6 warning ("has subscribed_events but TriggerType.EVENT is not in trigger_types") and skip it.
- **Phase 2 events don't re-trigger.** Events emitted *in* Phase 2 are recorded for telemetry but "recorded but not dispatched" — there is no Phase 3. The cascade is exactly one hop deep, which keeps a turn's cost bounded.

### Why this beats one smart agent

One frontier-model agent that does detection *and* analysis every turn pays premium tokens on every silent turn for nothing. The cascade inverts that: detection is commoditized and constant; analysis is premium and *rare*. You get frontier-quality coaching at near-detector cost, because you only invoke the frontier when a cheap signal has earned it.

---

## 2.5 Choosing the knobs: `trigger_types`, `priority`, `cooldown`, `model`

These four `AgentConfig` fields are where archetype meets engine. Choose them per-agent, deliberately.

**`trigger_types`** — *when does the engine even consider me?* The eligibility check (`_is_eligible`) drops any agent whose `trigger_types` doesn't contain the current `trigger_type`. Pick by archetype:

- `TURN_BASED` — the default; detectors/extractors that should look at each completed turn.
- `KEYWORD` — near-instant reaction to a watched word (host calls `check_keyword_triggers`, note it's **case-insensitive substring** matching per E-8 — "car" matches "scared", so choose distinctive keywords).
- `SILENCE` — dead-air handling (a "want a prompt to fill the gap?" coach).
- `INTERVAL` — periodic monitors.
- `EVENT` — Phase-2 analyzers in the cascade.
- `FORCE` — note you don't *subscribe* to FORCE; a FORCE run bypasses the trigger-type and cooldown checks for whichever agents the host force-runs.

**`priority`** — *who wins when we disagree?* `_merge_responses` applies updates in **ascending** priority so higher-priority agents **write last and win** (last-write-wins on variables; for facts, priority is stamped onto the `Fact` and resolves `(type,key)` conflicts via INV-9). Give your authoritative extractor a higher priority than a speculative one so its facts win. Ties break by registration order. Priority does **not** affect whether an agent runs or the order insights are shown — only conflict resolution.

**`cooldown`** — *how often may I speak?* This is your primary spam control and your primary cost control. Rule of thumb by archetype: detectors short (5–10s), extractors medium (15–30s), advisors long (20–60s), monitors interval-length. The `DynamicAgent` default is 15s; the `AgentConfig` default is 10s. Remember role `cooldown_modifier` can adjust it at runtime (floor 5s).

**`model`** — *model tiering, the cost lever.* Every agent has its own `model` (default `gpt-4o-mini`). The discipline: **cheap by default, premium only where reasoning quality is the product.** Detectors, extractors, and monitors should almost always stay on the cheap default. Reserve a frontier model for the *handful* of Phase-2 analyzers/advisors whose entire value is the quality of one sentence. In a well-built copilot the premium model is on a small minority of agents and runs on a small minority of turns.

---

## 2.6 Custom `BaseAgent` subclass vs. `DynamicAgent` (config)

Two ways to build an agent; pick by whether the logic is *prompting* or *computation*.

**Use `DynamicAgent` (config-driven) when the agent is "an LLM call with a persona."** You write a dict (system prompt in `text`, an `output_format` schema, trigger config) and `DynamicAgent` does the rest: Jinja2-renders the prompt against `blackboard`/`state`/`memory`, calls `self.llm.generate_json` on the configured model, and parses the response into the right `AgentResponse` channels via the schema mapping. All four archetypes above are `DynamicAgent`s. This is the default — most of your swarm should be config, not code. It also gives you the v2.2 safety rails for free: confidence clamped to `[0,1]` (A-3), `expiry`/`action_label` coerced safely (S-1), session-relative timestamps (A-2), and the gate-less-silence contract (A-1, see below).

**Write a custom `BaseAgent` subclass when the agent's job is computation, not prompting** — e.g. a deterministic talk-ratio calculator, a regex/keyword counter, an agent that calls an external API, or anything where an LLM is the wrong tool. You only implement `evaluate()`; you get the trigger/cooldown gates and error-to-ERROR-insight handling from `BaseAgent.process()` for free.

```python
# A deterministic monitor — no LLM, just arithmetic. Cheap and instant.
from core.agent import BaseAgent, AgentConfig
from core.models import AgentContext, AgentResponse, InsightType, TriggerType

class TalkRatioAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentConfig(
            name="Talk Ratio Monitor",
            id="talk_ratio",
            trigger_types=[TriggerType.INTERVAL],
            cooldown=30,
            priority=1,
            # model is irrelevant here — we never call an LLM
        ))

    async def evaluate(self, context: AgentContext) -> AgentResponse | None:
        user_words = sum(len(s.text.split())
                         for s in context.recent_segments if s.speaker == "USER")
        other_words = sum(len(s.text.split())
                          for s in context.recent_segments if s.speaker != "USER")
        total = user_words + other_words
        if total == 0:
            return None                      # nothing to say → stay silent
        ratio = user_words / total
        resp = AgentResponse(variable_updates={"talk_ratio": round(ratio, 2)})
        if ratio > 0.7:                      # threshold tripped → one insight
            resp.insights.append(self.create_insight(
                content=f"You're talking {ratio:.0%} of the time — ask a question.",
                type=InsightType.WARNING,
                confidence=1.0,
            ))
        return resp
```

This agent is *cheaper and more reliable than any LLM detector* for its job, costs zero tokens, and returns in microseconds. Knowing when **not** to use an LLM is part of the secret formula.

### `create_insight` — the one helper you always use

Whether subclass or dynamic, build HUD output with `create_insight` (`core/agent.py`). It stamps `agent_id`/`agent_name` for you and only passes `expiry`/`action_label` through when you provide them, so the `AgentInsight` model defaults (`expiry=15`, `action_label=None`) stand otherwise. Its signature: `create_insight(content, type=InsightType.SUGGESTION, confidence=1.0, expiry=None, action_label=None)`.

### Underused: the gate-less-silence contract (A-1 / INV-11)

A subtle `DynamicAgent` capability worth knowing. A schema's *silence gate* is what lets the model choose to say nothing. There are three cases (see the big comment in `DynamicAgent.evaluate`):

- **`check_field` present** (e.g. `default`, `default_v2` use `has_insight`): the boolean drives it — `false` ⇒ silence.
- **`root_key` present, no `check_field`** (e.g. `v2_raw` with `root_key: "insight"`): presence of a non-empty root object *is* the gate.
- **Neither** (a custom gate-less, rootless schema): the **documented default is to stay silent**. To opt into "speak whenever there's content," you must explicitly set `"speak_without_gate": true` in the mapping.

`DynamicAgent` even logs a one-time warning at load if your schema's *instruction* mentions a gate field like `has_insight` but the mapping forgot to wire `check_field` — the exact misconfiguration that silently turns an agent into a HUD spammer. **Restraint is the default; you have to opt out of it.** That's the framework's philosophy encoded in a parser.

---

## 2.7 Anti-patterns (the four deadly sins of agent design)

**The Mega-Agent.** One agent that detects, extracts, monitors, and coaches behind a giant prompt. It forces one model, one cooldown, and one priority on jobs with wildly different needs; it can't participate in the Phase-2 cascade (it *is* both phases); and one parsing failure takes out every job at once. Split it into a detector + extractor + advisor that coordinate through events and facts.

**Every-agent-on-every-turn.** Defaulting every agent to `TURN_BASED` with a short cooldown and no `trigger_conditions`. Now the full swarm makes an LLM call every single turn — maximum cost, maximum HUD spam, minimum signal. Most agents should be event-triggered, interval-triggered, or condition-gated so they run on a *subset* of turns. The engine gives you `trigger_types`, `trigger_conditions`, and the two-phase model precisely so you *don't* run everyone every turn.

**No cooldown (or cooldown too short).** An advisor with `cooldown=0` (or matching the turn cadence) will re-fire the same advice every turn, burning down `expiry` and the user's trust. Cooldown is not optional tuning — it is the core spam-control mechanism. Advisors especially need long ones.

**Premium model everywhere.** Setting `model="gpt-4o"` on the whole swarm "to be safe." This multiplies cost by the number of agents *and* turns, for near-zero quality gain on detectors and extractors that just need to answer a yes/no or pull a number. Cheap-by-default, premium-by-exception is the rule. If more than a small minority of your agents are on a frontier model, you've almost certainly skipped the cascade.

---

> ## 🔑 Secret formula — Chapter 2
>
> **Build a swarm of cheap, single-purpose agents whose default behavior is silence; make a few premium agents that wake only when a cheap detector's event has already proven the moment is worth the spend.**
>
> Concretely:
> 1. **One agent = one job.** If you need an "and" to describe it, split it. Coordinate the pieces through `events` and `facts`, not a mega-prompt.
> 2. **Detect cheap, analyze expensive.** Phase-1 detectors on `gpt-4o-mini` emit events; Phase-2 analyzers on a frontier model subscribe to them and run only when fired.
> 3. **Gate ruthlessly.** `trigger_types` + `trigger_conditions` decide *whether* you run; `cooldown` decides *how often*; `priority` decides *who wins*. Tune all four per archetype.
> 4. **Cheap model by default, premium by exception.** The frontier model should sit on a minority of agents and fire on a minority of turns.
> 5. **Silence is a feature.** `process()` returns `None` most of the time by design; the gate-less-silence contract makes "say nothing" the default you must opt *out* of. A copilot that speaks less is trusted more.
# Chapter 3 — The Blackboard: the Nervous System

> *The swarm doesn't talk to itself. It writes to a shared world-model and reads it back. The Blackboard **is** that world-model — the nervous system that lets a dozen cheap, dumb observers behave like one coherent copilot without a single one of them knowing the others exist.*

---

## Mental model: stigmergy, not conversation

A naive multi-agent design wires agents to each other: the sentiment agent calls the risk agent calls the summarizer. That graph explodes, and every edge is latency you can't afford in a real-time copilot.

`xubb_agents` rejects that. There is exactly **one** shared structure — the `Blackboard` — and agents coordinate through it the way ants coordinate through pheromone trails: one agent leaves a mark, another agent reads the mark and acts, and neither knows the other exists. This is **stigmergy**. The Blackboard is the environment they all modify and sense.

This buys you three things that matter for a copilot:

1. **Decoupling.** Add a tenth observer that reacts to `risk_score`; you change zero existing agents. The new agent just reads a variable that's already there.
2. **Determinism at the seams.** Every write goes through one merge step with defined ordering (Chapter on the engine covers this). No two agents race to mutate each other.
3. **A single integration contract with the host.** Your `xubb_server` HUD doesn't subscribe to ten agents. It reads five containers off one object. (More on this at the end — it's the most underused property of the whole framework.)

The Blackboard is a Pydantic model with exactly five typed containers (`core/blackboard.py`):

```python
class Blackboard(BaseModel):
    events:    List[Event]                 # transient pub/sub signals
    variables: Dict[str, Any]              # current session state
    queues:    Dict[str, List[Any]]        # FIFO work pipelines
    facts:     List[Fact]                  # deduplicated extracted knowledge
    memory:    Dict[str, Dict[str, Any]]   # per-agent private scratchpad
```

Five containers, five jobs. The secret formula of this chapter is **knowing which one a given piece of state belongs in** — because the framework gives each container different semantics (dedup, ordering, isolation, lifetime), and putting state in the wrong one is the single most common way a swarm rots.

---

## The five containers and exactly when to use each

### 1. Variables — the *current* session state

**Use for:** the answers to "what is true *right now*?" — `phase`, `sentiment`, `risk_score`, `current_topic`, `talk_ratio`. Single-valued, overwritten freely, read by everyone.

```python
# An observer updating the shared world-model
bb.set_var("sentiment", "frustrated")
bb.set_var("risk_score", 0.72)

# Any other agent — or a gate — reading it
if bb.get_var("risk_score", 0.0) > 0.6:
    ...
```

The full Variable API is deliberately tiny: `set_var`, `get_var(key, default)`, `has_var`, `delete_var`. Variables are a flat `Dict[str, Any]` — no nesting semantics, no history. The previous value is gone the moment you overwrite it.

**Why variables are the default home for "state":** gates read them cheaply. A `trigger_conditions` rule with `{"var": "risk_score", "op": "gte", "value": 0.6}` reads `blackboard.get_var("risk_score")` directly (`core/conditions.py`). Variables are the substrate your gating is built on — see Chapter on gating. Keep the things you gate on here.

> The agents that *write* `risk_score` and the gates that *read* it never reference each other. That's the nervous system working: a reflex arc through shared state.

### 2. Events — transient "something happened" signals

**Use for:** pub/sub. An observer noticed something this turn and wants *other* agents to react to it *this same turn*: `question_detected`, `objection_raised`, `competitor_mentioned`.

```python
from core.models import Event

bb.emit_event(Event(
    name="objection_raised",
    payload={"text": "that's too expensive", "severity": "high"},
    source_agent="objection_spotter",
    timestamp=t,
))
```

Read/query API: `has_event(name)`, `get_events_by_name(name)`, `count_events(name)`, and the engine-only `clear_events()`.

Three properties define events and you must internalize all three:

- **They are NOT deduplicated.** Three questions in one turn = three `question_detected` events. That's deliberate — `count_events("question_detected")` is a meaningful signal. If you need dedup, put an `id` in the payload and dedup yourself.
- **They drive Phase 2.** An event emitted in Phase 1 routes to agents that have `TriggerType.EVENT` in their trigger types and the event name in `subscribed_events`. This is how the framework turns "X happened" into "now the responder runs" — without the spotter and the responder knowing about each other.
- **They are wiped every turn.** `process_turn` calls `clear_events()` at the end (`core/engine.py`). Events live for **one turn**. They are signals, not memory.

That last point is the whole trap, so it gets its own anti-pattern below.

### 3. Queues — FIFO work pipelines

**Use for:** ordered backlogs of work items that accumulate and drain over time: `pending_questions`, `action_items`, `followups_to_surface`.

```python
bb.push_queue("pending_questions", "What's the contract length?")
bb.push_queue_items("action_items", ["send pricing", "loop in legal"])

q_len = bb.queue_length("pending_questions")   # gate on backlog depth
nxt   = bb.peek_queue("pending_questions")      # look without consuming
item  = bb.pop_queue("pending_questions")       # FIFO consume
```

Full API: `push_queue`, `push_queue_items`, `pop_queue` (FIFO, returns `None` when empty), `peek_queue`, `queue_length`, `clear_queue`, `has_queue`.

The distinction from events is **lifetime and consumption semantics**. An event says "a question happened" and vanishes. A queue *holds* the question until something explicitly pops it. Use a queue when work must survive across turns and be drained deliberately. The HUD's "3 unanswered questions" badge is `queue_length("pending_questions")` — durable, countable, ordered.

A common, powerful pairing: a spotter agent *emits an event* (so a responder fires this turn) **and** *pushes to a queue* (so the item persists if nobody handled it). The event is the doorbell; the queue is the inbox.

### 4. Facts — deduplicated extracted knowledge

**Use for:** durable, factual knowledge extracted from the conversation that should accumulate and *not* duplicate: `budget`, `timeline`, `stakeholders`, `decision_criteria`.

```python
from core.models import Fact

bb.add_fact(Fact(
    type="budget", key="budget.primary",
    value="$50k/yr", confidence=0.9,
    source_agent="extractor", timestamp=t,
))

bb.get_fact("budget", "budget.primary")     # one fact
bb.get_facts_by_type("stakeholder")          # all stakeholders
bb.has_fact("timeline")
```

Facts are the only container with **built-in deduplication and conflict resolution** (`add_fact`, INV-9):

- Dedup key is `(type, key)`. If `key is None`, the `type` is a **singleton** — one budget fact, period.
- On collision, the incoming fact wins iff `(priority, confidence) >= (existing.priority, existing.confidence)`. Priority dominates; confidence breaks ties; later registration breaks remaining ties.
- **`fact.priority` is engine-stamped.** Agents should *not* set it — the engine writes the emitting agent's priority at merge time (`_merge_responses` in `core/engine.py`). So a high-priority extractor's budget overrides a low-priority one's automatically. If you call `add_fact` directly from the host, *you* own `priority` (defaults to `0`).

This is what makes facts the right home for "what we've learned." Two agents independently extract the budget; you get one budget, resolved by trust — not two contradictory ones. That's knowledge, not state.

**Variables vs. Facts — the line that trips people up:** `risk_score` is a *variable* (it's the current reading, it changes constantly, you gate on it). `budget = $50k` is a *fact* (it's learned knowledge, it should dedup, it carries confidence and provenance). If it has a `confidence` and a `source`, it's a fact. If it's "the current value of X," it's a variable.

### 5. Memory — per-agent private scratchpad

**Use for:** one agent's private cross-turn state that no other agent needs: "have I greeted the user yet," "last time I fired," a running summary only the summarizer maintains.

```python
mem = bb.get_memory("summarizer")          # returns a DEEP COPY
mem["running_summary"] = updated
bb.set_memory("summarizer", mem)           # full replace (deep-copied in)
bb.update_memory("summarizer", {"turns_seen": n})  # merge
bb.has_memory("summarizer")
```

`memory` is keyed by `agent_id` (`Dict[str, Dict[str, Any]]`). Two safety properties matter (INV-8'):

- `get_memory` returns a **deep copy** — mutating what you read does not touch the Blackboard. You must write back explicitly.
- `set_memory` / `update_memory` **deep-copy on the way in** — a caller mutating a nested object it passed in won't corrupt Blackboard state.

Memory is *private by convention*, not enforced: gates can read another agent's memory via `{"memory": "other_agent.key"}` (`core/conditions.py`). But the design intent is a scratchpad. If two agents both need it, it isn't memory — promote it to a variable or a fact.

> **The decision table, memorized:**
> | If the state is... | it goes in |
> |---|---|
> | the current value of something you gate on | **Variables** |
> | a one-turn "this happened, react now" signal | **Events** |
> | a durable, ordered backlog drained over time | **Queues** |
> | learned knowledge that must dedup + carry confidence | **Facts** |
> | one agent's private cross-turn notes | **Memory** |

---

## Designing the shared world-model for a copilot

Before you write a single agent, design the Blackboard. The world-model *is* the architecture; the agents are just functions over it. For a sales/meeting copilot, a real schema looks like:

```
variables:
  sys.turn_count, sys.session_id, sys.trigger_type   # engine-owned (see below)
  phase            : "discovery" | "demo" | "negotiation" | "close"
  sentiment        : "positive" | "neutral" | "frustrated"
  risk_score       : float 0..1
  talk_ratio       : float        # rep talk time / total

events:            # transient, per-turn
  question_detected, objection_raised, competitor_mentioned, buying_signal

queues:
  pending_questions   : [str]     # drains as rep answers
  action_items        : [str]     # surfaced in HUD, drained on follow-up

facts:
  budget       (singleton)
  timeline     (singleton)
  stakeholder  (keyed: stakeholder.cfo, stakeholder.champion)
  decision_criteria (keyed)

memory:
  summarizer   : {running_summary, last_summarized_turn}
  coach        : {last_nudge_turn, nudges_given}
```

Notice the shape: a **small** set of gated variables, a handful of event names that are really a shared vocabulary, two or three queues, a flat fact taxonomy, and memory only where an agent genuinely needs private continuity. The whole swarm reads and writes *this*. Adding the eleventh agent means picking which of these it reads and which it writes — nothing more.

### Naming conventions

- **Variables:** flat, lowercase, snake — `risk_score`, `current_topic`. Use dotted prefixes to namespace families you scan together (`talk.ratio`, `talk.silence_ms`) — but remember `sys.` is reserved (below).
- **Events:** `noun_pastVerb` — `question_detected`, `objection_raised`. The event name is a contract; the spotter and the subscriber agree on the string and nothing else.
- **Queues:** plural nouns — `pending_questions`, `action_items`.
- **Facts:** `type` is a singular category (`budget`, `stakeholder`); `key` is `type.instance` (`stakeholder.cfo`). `key=None` means "there's only ever one."
- **Memory:** keyed by the literal `agent_id`. Don't invent a parallel key space.

### The `sys.*` reserved namespace

The engine owns the `sys.` prefix. Every turn it stamps (`_engine_internal=True`):

```python
bb.set_var("sys.turn_count",   context.turn_count,   _engine_internal=True)
bb.set_var("sys.session_id",   context.session_id,   _engine_internal=True)
bb.set_var("sys.trigger_type", trigger_type.value,   _engine_internal=True)
```

Rules of the namespace:

- **Read them freely.** `sys.turn_count` is gold for gating — "don't fire before turn 3," "summarize every 5 turns."
- **Don't write them.** A non-engine `set_var("sys.x", ...)` is *not blocked* but logs a warning (`core/blackboard.py`) — it's a code smell, not a guardrail.
- **They never leak into the v1 surface.** `sys.*` keys are excluded from the `shared_state` sync (E-2, `_sync_state_to_legacy`), so an engine value can't round-trip back through a legacy agent's `state_updates` and trip its own write-guard. You get a clean engine-managed namespace for free.

---

## Snapshot-per-phase isolation — the property that makes it deterministic

This is the most important mechanic in the chapter and the most commonly ignored.

When a phase runs, the engine does **not** let agents read and write live shared state. It takes one **immutable snapshot** and runs every agent in that phase against it in parallel (`_run_phase`, `core/engine.py`):

```python
snapshot = context.blackboard.snapshot()   # deep copy of all five containers
# ... every agent in the phase reads `snapshot`, runs concurrently ...
results = await asyncio.gather(*tasks)
# ... only AFTER all complete are updates merged back ...
```

`snapshot()` deep-copies events, variables, queues, facts, and memory. The consequences are precise and you must build around them:

- **Within a phase, agents see a consistent, frozen world.** Agent B in Phase 1 does **not** see Agent A's writes from the same phase — both read the world as it was at phase start. Writes from this phase land *after the phase ends*, via the merge.
- **Writes are collected, then merged with deterministic ordering** (ascending priority, registration order as tie-break — covered in the engine chapter). No two parallel agents stomp each other mid-flight.
- **Cross-agent reaction is cross-*phase*, not cross-agent-within-phase.** If Agent B must react to what Agent A wrote, A emits an **event** and B subscribes — B then runs in **Phase 2** against a snapshot that *includes* A's merged writes. That's the entire reason Phase 2 exists.

**The mental trap this kills:** "Agent A sets `risk_score`, so Agent B (also Phase 1) can gate on it." No. B evaluated its gate against the pre-phase snapshot where `risk_score` was still the old value. If B must react to A's fresh write, route it through an event into Phase 2. Designing around the snapshot is the difference between a swarm that's deterministic and one that's subtly turn-order-dependent.

---

## The Blackboard as the integration contract with the host

Here is the underused superpower. Your host (`xubb_server`, the HUD) should **not** be wired to individual agents. It should read the Blackboard. The framework hands you a clean serialization boundary:

```python
state = bb.to_dict()    # deep copies: events, variables, queues, facts, memory
#   render the HUD entirely from this one dict
#   - risk meter      <- state["variables"]["risk_score"]
#   - questions badge <- len(state["queues"].get("pending_questions", []))
#   - known facts     <- state["facts"]
restored = Blackboard.from_dict(state)   # rehydrate next session
```

`to_dict` / `from_dict` are your persistence and HUD-rendering contract. Persistence is explicitly the **host's** responsibility — the framework keeps the Blackboard in-memory for the session lifetime only (`core/blackboard.py` docstring). So:

- **The HUD renders from `to_dict()`.** One read, five containers, the whole world-model. Add an agent that writes a new variable and the HUD that already iterates `variables` shows it with zero glue code.
- **Session continuity is `from_dict()`.** Snapshot at session end, rehydrate at session start; facts and memory survive.
- **The five containers are the API surface between swarm and product.** This is why container discipline matters beyond aesthetics: the HUD *is* a consumer of your naming conventions. `pending_questions` being a queue (not buried in a variable dict) is what lets the host count it generically.

> Design the Blackboard schema as a **public API between the swarm and the product**, then let agents and HUD both be thin functions over it. That decoupling is the entire payoff of the architecture.

---

## Anti-patterns (the four ways the nervous system rots)

**1. Stuffing everything into variables.**
The `variables` dict will happily hold your questions list, your budget, and your per-agent notes. Don't. You lose dedup (facts), FIFO + counting (queues), and isolation (memory). A variable holding `{"questions": [...]}` is a queue you've crippled — no `pop`, no `queue_length`, no generic HUD rendering. Match the container to the semantics.

**2. Using events for durable state.**
Events are cleared every turn (`clear_events()`). Writing "objection was raised" as an event and expecting to read it three turns later means it's *gone*. If the fact must persist, it's a **fact** or a **queue** entry. Events are a doorbell, not a logbook. The pattern that's correct: emit the event (react now) *and* push to a queue or add a fact (persist).

**3. Ignoring snapshot semantics.**
Assuming a same-phase agent sees your write, or that parallel agents read each other live. They read a frozen snapshot; writes merge after. Cross-agent reaction *within a turn* must go event → Phase 2. Build a swarm on the wrong assumption and it works in dev (one agent) and breaks in prod (ten agents, turn-order-sensitive).

**4. Unbounded queues and facts.**
Nothing in the framework caps `queues` or `facts` growth — `push_queue` and `add_fact` append forever. A `pending_questions` queue that's never drained, or a keyed fact taxonomy with unbounded distinct keys (`note.0`, `note.1`, …), grows for the whole session and bloats every `snapshot()` (a full deep copy, every phase, every turn — so growth is a *latency* problem, not just memory). Drain queues deliberately (`pop_queue` / `clear_queue`), keep fact keys to a bounded taxonomy, and prefer singleton facts (`key=None`) where there's genuinely one truth.

---

## Secret formula

> **The Blackboard is a public API, not a junk drawer.** Design its five-container schema *first* — it's your architecture and your host contract in one. Then make every agent a thin function that reads a snapshot and returns writes, and make the HUD a thin function over `to_dict()`. Pick the container by its *semantics*, not convenience: gate on **variables**, signal with **events**, queue durable work in **queues**, accumulate dedup'd knowledge as **facts**, and keep private continuity in **memory**. Coordinate cross-agent reactions through **event → Phase 2**, never through same-phase reads — the snapshot makes that the *only* deterministic path. Get the schema right and the eleventh agent costs you nothing.
# Chapter 4 — Triggers & Conditions: the Reactive Control Plane

> **Thesis recap.** A copilot is a reactive blackboard-coordinated swarm of many cheap agents. The single most important skill is *not* writing clever agents — it's deciding **when they are allowed to think**. Triggers are the *coarse* router ("which class of moment is this?"); conditions are the *fine* gate ("is this specific moment worth an LLM call for *this* agent?"). Together they are the cost-and-relevance control plane. Restraint is the product. An agent that stays silent 90% of turns and lands perfectly the other 10% beats one that fires every turn.

---

## Mental model: two gates and a bypass

Every turn, the engine asks four questions per agent, in order (`AgentEngine._is_eligible`, `core/engine.py`):

1. **Allow-list** — is this agent in `allowed_agent_ids`? (host-owned hard filter; `None` = all)
2. **FORCE bypass** — is `trigger_type == FORCE`? If so, **run immediately**, skipping the next two gates entirely.
3. **Trigger-type match** — does the turn's `trigger_type` appear in `agent.config.trigger_types`?
4. **Conditions** — do `agent.config.trigger_conditions` evaluate `True` against the blackboard?

Then `BaseAgent.process` (`core/agent.py`) applies a **fifth, agent-owned gate**: the **cooldown**. So the full eligibility funnel is:

```
allow-list  →  trigger-type  →  conditions   (engine, core/engine.py)
                                    ↓
                                cooldown      (agent, core/agent.py)
                                    ↓
                              agent.evaluate()  ← the only place LLM cost is spent
```

The mental model that matters for cost: **trigger type is the cheap coarse filter, conditions are the cheap fine filter, cooldown is the timing backstop, and `evaluate()` is the only expensive step.** Push as much rejection as possible up the funnel into the free, synchronous, no-LLM gates. The condition evaluator never calls the network and never raises (`core/conditions.py`); it is the cheapest lever you own.

---

## The six trigger types — and exactly when to use each in a copilot

From `TriggerType` (`core/models.py`). An agent's `trigger_types` is a list — an agent can subscribe to several.

| Trigger | Value | Who fires it | Copilot use |
|---|---|---|---|
| `TURN_BASED` | `turn_based` | Engine default, after each conversational turn | The workhorse. Use for any agent that reasons over what was just said. **Default trigger** if you specify none (`AgentConfig` defaults `trigger_types` to `[TURN_BASED]`). |
| `KEYWORD` | `keyword` | **Host**, via `check_keyword_triggers` helper | Latency-critical reactions to specific terms ("pricing", a competitor name, "cancel"). Fire *between* turns, the instant the term is transcribed. |
| `SILENCE` | `silence` | **Host**, when dead-air exceeds a threshold | Re-engagement / nudge agents. The dead-air HUD prompt: "Ask about their timeline." |
| `INTERVAL` | `interval` | **Host**, on a wall-clock timer | Slow background sweeps — periodic summarizer, health/risk re-scorer — that should run on time, not on talk. |
| `EVENT` | `event` | Engine, in **Phase 2**, from blackboard events emitted in Phase 1 | Agent-to-agent reactions. A `question_detected` event wakes an answer-drafting agent *within the same turn*. Requires `subscribed_events` **and** `EVENT` in `trigger_types` (see below). |
| `FORCE` | `force` | **Host**, user-initiated ("force-talk" button) | The user demands output now. Bypasses trigger-type match, conditions, **and** cooldown. The escape hatch from your own gating. |

### How the host invokes the non-TURN triggers

The engine does **not** watch the clock or scan text on its own. v2 deliberately makes keyword/silence/interval detection a **host responsibility** — the engine only routes once the host declares the trigger type on `process_turn(...)`. The pattern:

```python
# KEYWORD: host scans the new transcript, then calls process_turn with the matches
matches = engine.check_keyword_triggers(new_text)          # [(agent, matched_keyword), ...]
if matches:
    await engine.process_turn(
        context,
        allowed_agent_ids=[a.config.id for a, _ in matches],   # only the agents that matched
        trigger_type=TriggerType.KEYWORD,
        trigger_metadata={"keyword": matches[0][1]},
    )

# SILENCE: host's own dead-air timer fires
silent_agents = engine.get_agents_with_silence_threshold()
await engine.process_turn(context, trigger_type=TriggerType.SILENCE,
                          trigger_metadata={"silence_seconds": 8})

# INTERVAL: host's periodic scheduler
await engine.process_turn(context, trigger_type=TriggerType.INTERVAL)

# FORCE: user pressed the button
await engine.process_turn(context, allowed_agent_ids=[chosen_id],
                          trigger_type=TriggerType.FORCE)
```

Three host helpers exist purely to *find* the candidate agents so the host can decide whether to fire at all:
- `get_agents_by_trigger_type(t)` — routing introspection.
- `get_agents_with_keywords()` — which agents even have keywords worth scanning for.
- `get_agents_with_silence_threshold()` — which agents care about dead air (and at what threshold — read `silence_threshold` off each).

> **Note on `check_keyword_triggers` (E-8):** matching is **case-insensitive substring**, not word-boundary — `"car"` matches `"scared"` and `"cart"`. It's a best-effort helper; if you need word boundaries, the host does its own matching and passes `allowed_agent_ids` directly.

> **Note on `EVENT` wiring:** an agent only fires in Phase 2 if it has the event name in `subscribed_events` **and** `TriggerType.EVENT` in `trigger_types`. Listing the event but omitting the trigger type is a config error — `get_event_subscribers` excludes the agent and logs a one-time warning (E-6). Don't rely on `subscribed_events` alone.

---

## Conditions: the cost-and-relevance gate (the biggest lever)

Trigger type answers "what *kind* of moment is this?". Conditions answer "given the blackboard *right now*, should *this* agent spend an LLM call?". This is where you stop the swarm from burning money.

### Shape of the DSL

`trigger_conditions` is a dict with a `mode` and a list of `rules` (`ConditionEvaluator.evaluate`, `core/conditions.py`):

```json
{
  "mode": "all",
  "rules": [
    { "var": "stage", "op": "eq", "value": "discovery" }
  ]
}
```

- **`mode`**: `"all"` (every rule must pass — logical AND, the default) or `"any"` (at least one — logical OR). Unknown mode falls through to `True` (treated as no gate).
- **`rules`**: each rule names exactly one **source**, an **`op`**, and usually a **`value`**.
- **No `trigger_conditions`** (or empty `rules`) ⇒ always passes. That's an agent with *no relevance gate* — a deliberate choice, not a default to fall into.

### The four sources (where a rule reads from)

A rule selects its source by which key is present (`_get_value`):

| Key | Reads from | Example |
|---|---|---|
| `"var"` | `blackboard.variables` (session key-value) | `{"var": "stage", "op": "eq", "value": "closing"}` |
| `"fact"` (+ optional `"fact_key"`) | `blackboard` facts, by `(type, key)` | `{"fact": "budget", "op": "present"}` |
| `"queue"` | `blackboard.queues` (returns the **list**) | `{"queue": "open_questions", "op": "not_empty"}` |
| `"memory"` | this agent's private memory (or `"other.key"` for cross-agent) | `{"memory": "greeted", "op": "exists"}` |
| `"meta"` | engine execution metadata | `{"meta": "turn_count", "op": "mod", "value": 5, "result": 0}` |

> **`meta` exposes exactly four keys** (`core/engine.py`, where `meta` is built): `turn_count`, `trigger_type` (the string value, e.g. `"keyword"`), `phase` (`1` or `2`), and `session_id`. There is no `silence_seconds` in `meta` — silence duration lives in `trigger_metadata`, which conditions do **not** see. Gate on silence by routing (the `SILENCE` trigger type), not a condition.

### Every operator (and the value it expects)

From `_compare` (`core/conditions.py`):

| `op` | Passes when | Notes |
|---|---|---|
| `eq` / `neq` | `actual == value` / `!=` | |
| `gt` / `gte` / `lt` / `lte` | numeric compare; **`None` actual always fails** | threshold gating |
| `in` / `not_in` | `actual in value` (value is the list) | `value: null` ⇒ `in`=False, `not_in`=True (guarded on `is None`, so `value: 0` or `""` still does a real test) |
| `contains` | `value in actual` | works on list (membership), string (substring), dict (key); `None` actual ⇒ False |
| `exists` | `bool(actual)` is truthy | `None`, `""`, `[]`, `{}`, `0`, `False` all **fail** |
| `present` | the **key exists**, value may be falsy | uses `key_exists`, not the value — the precise "was this ever set?" check |
| `not_exists` | `not bool(actual)` | falsy *or* missing |
| `not_empty` / `empty` | collection has / lacks items | `None` ⇒ `not_empty`=False, `empty`=True |
| `mod` | `(actual % value) == result` | `result` defaults to `0`; `None` operands or `value == 0` fail closed |

Two operators that punch above their weight in a copilot:

- **`present` vs `exists`** is a real distinction. `present` asks *"has this key ever been written?"* (so a deliberate `False`/`0`/`""` counts as set). `exists` asks *"is the value truthy?"*. Use `present` for "have we recorded a decision either way?"; use `exists` for "do we have a non-empty value to act on?".
- **`mod`** is your turn-cadence operator: `{"meta": "turn_count", "op": "mod", "value": 5, "result": 0}` runs an agent every 5th turn — a periodic sweep without an `INTERVAL` timer.

### Fail-closed is the law (C-1)

Two safety guarantees you should *design around*, not just trust:

1. **Evaluation never raises.** `_evaluate_rule` wraps everything; any exception (type mismatch, bad source, divide-by-zero) ⇒ that rule is `False` (`core/conditions.py`).
2. **Unknown operators fail closed.** A typo'd `op` (`"eq "`, `"equals"`, `"greater"`) logs a warning and returns **`False`**, not `True` (C-1). The agent stays silent rather than firing every turn.

The discipline this enables: **in `mode: "all"`, a bug makes an agent over-silent, never over-firing.** Over-silence is a visible, debuggable symptom ("why won't my agent talk?"); over-firing silently burns money and clutters the HUD. Design your gates so the failure mode is silence. (Caveat below in anti-patterns: `mode: "any"` can invert this.)

---

## Recipe library

Copy-paste starting points. All are real `trigger_conditions` payloads.

**Phase-gating (`eq` / `in`)** — only run during certain conversation stages:
```json
{ "mode": "all", "rules": [
  { "var": "stage", "op": "in", "value": ["discovery", "qualification"] }
]}
```

**Turn cadence (`mod`)** — a background summarizer every 4th turn, no timer needed:
```json
{ "mode": "all", "rules": [
  { "meta": "turn_count", "op": "mod", "value": 4, "result": 0 }
]}
```

**Fact-presence gating (`present`)** — an objection-handler that only wakes once a budget fact exists:
```json
{ "mode": "all", "rules": [
  { "fact": "budget", "op": "present" }
]}
```

**Queue-not-empty** — an answer agent that only runs when there are open questions to drain:
```json
{ "mode": "all", "rules": [
  { "queue": "open_questions", "op": "not_empty" }
]}
```

**Threshold (`gt` / `lt`)** — a risk-escalation agent only when a score crosses a line:
```json
{ "mode": "all", "rules": [
  { "var": "risk_score", "op": "gt", "value": 0.7 }
]}
```

**Multi-rule AND (`all`)** — late-stage *and* a deal-blocker fact present *and* not too chatty:
```json
{ "mode": "all", "rules": [
  { "var": "stage",       "op": "eq",   "value": "closing" },
  { "fact": "blocker",    "op": "present" },
  { "meta": "turn_count", "op": "gte",  "value": 6 }
]}
```

**Multi-rule OR (`any`)** — wake on *either* a pending question *or* a fresh objection event-flag var:
```json
{ "mode": "any", "rules": [
  { "queue": "open_questions", "op": "not_empty" },
  { "var": "objection_open",   "op": "exists" }
]}
```

**Run-once-per-session via memory (`not_exists`)** — a greeting agent that fires once, then gates itself off (it writes `greeted` to its own memory on first run):
```json
{ "mode": "all", "rules": [
  { "memory": "greeted", "op": "not_exists" }
]}
```

**Cross-agent coordination (`memory` with dotted key)** — only run if another agent has flagged readiness in *its* memory:
```json
{ "mode": "all", "rules": [
  { "memory": "qualifier.qualified", "op": "exists" }
]}
```

---

## Cooldown strategy (the timing backstop)

Conditions answer *whether* the moment is relevant; cooldown answers *how often*, in wall-clock seconds, an agent may speak even when it stays relevant. Enforced in `BaseAgent.process` (`core/agent.py`): if `now - last_run_time < effective_cooldown`, the agent returns `None` before `evaluate()`.

Key facts:
- **`cooldown` is per-agent**, in seconds (`AgentConfig`, default `10`).
- **It's a backstop, not a relevance filter.** A relevant agent on a 30s cooldown still goes quiet for 30s after firing — useful to stop a chatty agent from re-stating, but it can *also* silence a genuinely urgent follow-up. Pair tight conditions with a modest cooldown; don't lean on cooldown to do conditions' job.
- **`last_run_time` updates on every run, success or failure (B4)** — a crashing agent still respects its cooldown, so a broken agent can't hot-loop.
- **FORCE ignores cooldown entirely.** The user can always force output.

### `cooldown_modifier` for Roles

A Role (or any per-turn host policy) can tune an agent's cadence without editing the agent via `AgentConfigOverride.cooldown_modifier` (`core/models.py`), passed through `context.agent_config_overrides[agent_id]`:

```python
effective_cooldown = max(5, self.config.cooldown + overrides.cooldown_modifier)
```

- **Polarity:** `+N` = *slower* (longer cooldown), `-N` = *faster*.
- **Hard floor of 5 seconds** — you can speed an agent up but never below a 5s floor, so no Role can turn an agent into a per-turn LLM firehose.
- `AgentConfigOverride` is `extra="forbid"` — a typo'd modifier key is rejected at construction, not silently ignored.

Strategic use: ship agents with a *conservative* (longer) base `cooldown`, then let an "aggressive copilot" Role dial them down with negative modifiers for high-touch sessions, and a "background / observe-only" Role dial them up. The agent code never changes.

---

## FORCE: the user-owned bypass

`FORCE` is the deliberate hole in your gating. When `trigger_type == FORCE`, `_is_eligible` returns `(True, "")` immediately — **no trigger-type match, no conditions** — and `BaseAgent.process` skips the cooldown check. The agent still runs its real `evaluate()`, and `last_run_time` still updates (so the forced run reseeds the cooldown).

Use it for exactly one thing: **the user explicitly demands this agent's output now.** Scope it with `allowed_agent_ids=[the_one_agent]` so FORCE doesn't wake the whole swarm. Never use FORCE as a workaround for conditions you couldn't get right — if you find yourself forcing routinely, your conditions are wrong.

> **Underused capability — FORCE + override-less debug.** When you FORCE an agent that has *no* override in `agent_config_overrides`, the engine logs a debug line ("FORCE run with no override"). In practice this is a clean way to manually probe a single agent's `evaluate()` in a live session, gates-off, to see what it *would* say — a built-in "what would you do here?" button for tuning.

---

## Secret formula

> **Gate up the funnel, fail down to silence.** Reject as early and as cheaply as you can — trigger type before conditions, conditions before cooldown, all three before the one expensive `evaluate()`. Then arrange every gate so its *failure mode is silence*: `mode: "all"` + fail-closed conditions means a bug makes an agent too quiet (loud, debuggable) instead of too expensive (silent, costly). Cheap filters first; expensive thought last; silence as the safe default. The swarm's intelligence is mostly in what it declines to do.

---

## Anti-patterns

**1. No conditions — every agent every turn.** An agent with `trigger_types=[TURN_BASED]` and no `trigger_conditions` runs on *every* turn (cooldown permitting). With a swarm of 15 agents that's 15 LLM calls per turn, most of them irrelevant. **Conditions are not optional polish — they are the cost model.** Default every agent to a phase or fact gate; justify any agent that has none.

**2. Conditions too loose.** `{"var": "stage", "op": "exists"}` passes as soon as `stage` is set to *anything* — which is almost always. A condition that's true 95% of the time isn't a gate. Gate on the *specific* states that matter (`in: ["closing"]`), not mere presence, unless presence genuinely is the signal.

**3. Relying on cooldown alone for relevance.** Cooldown throttles *frequency*, not *relevance*. An agent gated only by a 20s cooldown still fires every 20s regardless of whether the conversation has anything to do with it — paying for irrelevant calls on a timer. Cooldown is a backstop behind conditions, never a substitute.

**4. Fail-open operator typos.** C-1 fixed the engine so unknown operators fail **closed** — but that protects you only if you understand *why* it matters. A typo like `"op": "eq "` (trailing space) or `"op": "equals"` now correctly yields `False` and a logged warning. The discipline: **read the warning logs.** A silently-`False` rule in `mode: "all"` makes your agent mysteriously never fire — the symptom of a typo'd op is "my agent is dead," and the warning log is where it confesses.

**5. `mode: "any"` inverting the fail-closed guarantee.** Fail-closed only protects you in `mode: "all"`. In `mode: "any"`, a *correct* rule that should be the real gate, sitting next to a *typo'd* rule, still passes whenever the correct one does — but worse, if you intended several gates and one is malformed, `any` can fire on a rule you didn't mean. Prefer `all` for cost-critical gates; reserve `any` for genuine "wake on either signal" cases and double-check every rule in an `any` block.

**6. Gating on data the evaluator can't see.** Conditions read only `var` / `fact` / `queue` / `memory` / `meta`-with-four-keys. They do **not** see `trigger_metadata` (so silence-duration, matched-keyword, etc. are invisible to conditions). If you write `{"meta": "silence_seconds", ...}` it reads `None` and fails closed forever. Gate on those by *routing* (the right `trigger_type`) and let conditions gate on blackboard state.
# Chapter 5 — Multi-Agent Orchestration & Choreography

> **Thesis in one breath.** A copilot is not one big agent — it is a *swarm* of cheap,
> single-minded observers that never talk to each other directly. They coordinate
> through the Blackboard, react in two crisp phases, and resolve disagreements by
> priority. Orchestration here is *choreography*, not conducting: nobody is in charge,
> the dance is in the rules.

---

## 5.1 Mental model: a turn is a two-beat dance

Every call to `AgentEngine.process_turn` is a single turn with **at most two phases**,
hard-capped in the constructor (`max_phases` is clamped to `1` or `2`, engine.py E-7):

```
            ┌─────────────────────── one process_turn ───────────────────────┐
  TURN_BASED│  PHASE 1                          PHASE 2 (only if events fired) │
   trigger →│  observers run in PARALLEL  ──►   subscribers run in PARALLEL    │──► merged
            │  against a frozen snapshot   events   against a fresh snapshot    │   AgentResponse
            │  (they may emit events)      cascade  (trigger_type = EVENT)      │
            └─────────────────────────────────────────────────────────────────┘
                                                  ▲
                                          events are dispatched
                                          ONCE, between the beats
```

The two beats are *different kinds* of work:

- **Phase 1 — observation.** Every agent whose trigger type matches the turn (and whose
  cooldown/conditions pass) runs. These are your detectors, extractors, watchers. They
  read the conversation, write variables/facts, and — crucially — **emit events** when
  they notice something another agent should handle.
- **Phase 2 — reaction.** The engine collects every event Phase 1 emitted, finds the
  agents *subscribed* to those event names (and carrying `TriggerType.EVENT`), and runs
  them. This is where a Detector's `objection_raised` becomes an Objection-Handler's
  rebuttal — **within the same turn**.

That is the whole machine. There is no Phase 3. Events emitted in Phase 2 are *recorded
for telemetry but never dispatched* (engine.py: `"recorded but not dispatched"`). The
cascade is exactly one hop deep, and that shallowness is a feature — it bounds latency
and makes every turn analyzable.

---

## 5.2 The event cascade: how Phase 1 hands work to Phase 2

The cascade lives in `_process_turn_inner`. Read it as four moves:

1. **Phase 1 runs and returns responses.** Each `AgentResponse` may carry `.events`.
2. **The engine harvests and dispatches events onto the Blackboard:**

   ```python
   # engine.py — after Phase 1 merge
   for resp in phase1_responses:
       all_events.extend(resp.events)
   for event in all_events:
       context.blackboard.emit_event(event)
   ```

3. **The engine flips into event mode and routes to subscribers:**

   ```python
   context.phase = 2
   context.trigger_type = TriggerType.EVENT          # so subscribers pass their own trigger check
   event_names = list(set(e.name for e in all_events))
   phase2_agents = self.get_event_subscribers(event_names)
   ```

4. **Subscribers run, merge, and the turn finalizes** — events are cleared
   (`blackboard.clear_events()`), because **events are transient**: they live for exactly
   one turn and never leak into the next.

`get_event_subscribers` is the routing table. An agent is a subscriber **only if both**
are true: its name appears in the emitted `event_names`, *and* it carries
`TriggerType.EVENT`:

```python
# engine.py
subscribed = getattr(agent.config, 'subscribed_events', None) or []
if any(event_name in subscribed for event_name in event_names):
    if TriggerType.EVENT in agent.config.trigger_types:
        subscribers.append(agent)
    elif agent.config.id not in self._warned_subscriber_ids:
        # E-6: warn ONCE — subscribed_events set but EVENT trigger missing
        logger.warning(...)
```

> **Underused capability.** `DynamicAgent` *auto-adds* `TriggerType.EVENT` for you when
> `subscribed_events` is non-empty (dynamic.py: "auto-add TriggerType.EVENT when
> subscribed_events is non-empty"). So config-driven agents just declare
> `subscribed_events` and they Just Work. The engine-level guard + once-only warning
> exists for hand-rolled `BaseAgent` subclasses that forget the trigger.

How does an agent emit an event? It returns one in its response. For a `DynamicAgent`,
the LLM emits an `events` array and the parser stamps the rest:

```python
# dynamic.py — event extraction
event = Event(
    name=evt.get("name", ""),
    payload=evt.get("payload") or evt.get("data", {}),
    source_agent=self.config.id,
    timestamp=current_time,        # A-2: session-relative, never wall-clock
    id=evt.get("id"),
)
```

---

## 5.3 Pub/sub choreography: agents that build on each other without coupling

This is the strategic heart of the chapter. Detectors and handlers never import each
other, never share a function call, never know each other's IDs. They share **one
string** — an event name — and the Blackboard does the matchmaking.

### Pattern: a real two-phase choreography (Detector → Objection-Handler)

**Phase-1 agent — the Detector.** Pure observer. Its only job is to notice an objection
and *name* it as an event. Config (DynamicAgent JSON):

```json
{
  "id": "objection_detector",
  "name": "Objection Detector",
  "trigger_config": { "mode": "turn_based", "cooldown": 8 },
  "output_format": "v2_raw",
  "text": "Watch the prospect's last lines. If they raise a pricing/timing/authority objection, emit an event 'objection_raised' with payload {kind, quote}. Do not write advice yourself."
}
```

Its model output (parsed by `dynamic.py` into `response.events`):

```json
{ "events": [
  { "name": "objection_raised",
    "payload": { "kind": "pricing", "quote": "honestly it's just too expensive" } }
] }
```

**Phase-2 agent — the Objection-Handler.** Subscribes to the event name. It only ever
runs when the Detector (or *any* agent) emits `objection_raised`:

```json
{
  "id": "objection_handler",
  "name": "Objection Handler",
  "trigger_config": {
    "subscribed_events": ["objection_raised"],
    "cooldown": 12
  },
  "output_format": "default",
  "text": "An objection was just detected this turn. Read {{ blackboard.events }} for the kind and quote, and the transcript for tone. Offer ONE crisp rebuttal line the rep can say out loud."
}
```

Because the handler reads `{{ blackboard.events }}` in its Jinja prompt, it sees the live
events on the Phase-2 snapshot. The framework gives it the lookup helper it needs:

```python
# blackboard.py
def get_events_by_name(self, event_name: str) -> List[Event]:
    return [e for e in self.events if e.name == event_name]
```

**What the user sees:** one turn, one HUD card — a perfectly-timed rebuttal that
appeared the *instant* the objection landed. Two agents collaborated; neither knows the
other exists.

### Why this beats a monolith

A single "objection coach" agent would have to detect *and* handle in one LLM call,
every turn, on every line. Split into Detector + Handler:

- The **Detector is cheap and gated** (`gpt-4o-mini`, short cooldown) and stays silent
  by default — it only speaks (emits) on a real objection.
- The **Handler is expensive but rare** — it only fires when there's genuinely something
  to handle. You pay for the smart model *only on the turns that need it*.

That is the swarm economics of this whole framework: **many cheap observers gating one
expensive reactor.**

### Underused: events as a fan-out bus

`get_event_subscribers` matches *any* agent subscribed to the name. One
`objection_raised` event can wake a Handler **and** a `Risk-Logger` **and** a
`Sentiment-Tracker` simultaneously — they all run in parallel in Phase 2. And events are
**not deduplicated** (blackboard.py: "Events are NOT deduplicated by default"), so three
objections in one turn produce three events, and a counting subscriber can read
`count_events("objection_raised") == 3` to escalate.

---

## 5.4 Priority-driven merge: how disagreements resolve

When several agents write to the same place, the engine needs a deterministic winner.
That is `_merge_responses`. The rule is **ascending priority order — higher priority
writes last, and last-write-wins:**

```python
# engine.py
updates.sort(key=lambda x: (x[0], x[1]))   # (priority asc, registration_index asc)
for priority, index, agent_id, resp in updates:
    ...
    for key, value in resp.variable_updates.items():
        blackboard.set_var(key, value)     # higher-priority agent overwrites later
```

Ties within equal priority break by **registration order** — register your authoritative
agents accordingly. The per-channel merge semantics differ and you must know them:

| Channel | Merge rule |
|---|---|
| **insights** | Append-only. Every agent's insights are kept (the HUD layer decides what to show). |
| **variables** | Last-write-wins by priority. Highest-priority writer of a key wins. |
| **queues** | Additive — `push_queue_items` appends; nothing is overwritten. |
| **facts** | **Resolved by priority via F-1/INV-9**, not last-write-wins (see below). |
| **memory** | Per-agent namespaced (`memory_<id>`); flat merge is last-write-wins but each agent owns its own key, so no real collision. |
| **data sidecar** | New keys added; matching lists extended; scalars overwritten. |

### Facts are special: F-1 / INV-9 priority resolution

Variables resolve by *write order*. Facts resolve by an explicit *comparison*. At merge
time the engine **stamps each fact with the emitting agent's priority**, then hands it to
`add_fact`:

```python
# engine.py — facts get the agent's priority stamped on
for fact in resp.facts:
    fact.priority = priority
    blackboard.add_fact(fact)
```

```python
# blackboard.py — conflict resolution on (type, key)
if (fact.priority, fact.confidence) >= (existing.priority, existing.confidence):
    self.facts.remove(existing); self.facts.append(fact)
```

So on a `(type, key)` collision: **higher priority wins regardless of confidence**;
confidence is only the tiebreaker *within* equal priority; remaining ties go to later
registration. This is the exact contract the v2.1.1 "facts-vs-priority" escaped defect
violated — a priority-10/confidence-0.5 authoritative extractor must override a
priority-1/confidence-0.9 noisy one. It is now guarded by `PROBE-F1`
(`tests/qa_probes/test_probe_f1_facts_priority.py`). Lean on it: give your
*authoritative* extractor (CRM lookup, confirmed-by-user fact) a high priority and let
the noisy LLM guessers run low — the Blackboard sorts out the truth for you.

---

## 5.5 Snapshot isolation (INV-2): the rule that makes parallelism safe

Within a phase, **all agents read the same immutable snapshot** and run concurrently:

```python
# engine.py _run_phase
snapshot = context.blackboard.snapshot()          # deep copy, INV-2
phase_context = AgentContext(..., blackboard=snapshot, ...)
tasks = [self._run_agent_safe(a, phase_context) for a in agents]
results = await asyncio.gather(*tasks)            # true parallelism
```

`snapshot()` deep-copies every container (blackboard.py), so one agent's in-flight
thinking can never be seen — or corrupted — by a sibling. Writes are collected and
**merged only after the whole phase completes**. This is what lets you run a dozen
observers at once without locks or race conditions.

The direct consequence — and the #1 mistake newcomers make:

> **An agent CANNOT see another agent's writes from the same phase.** They all read the
> snapshot taken *before* the phase began. If Agent B needs Agent A's output, A must emit
> an **event** and B must be a **Phase-2 subscriber** — the cascade is the *only*
> intra-turn channel between agents.

`_run_agent_safe` also gives you **atomic failure**: if one agent throws, it returns
`None` and is filtered out; the rest of the phase is unaffected. One flaky observer never
takes down the swarm.

---

## 5.6 Cross-turn choreography: turn N informs turn N+1

The two-phase cascade is intra-turn. *Durable* coordination is **cross-turn**, and it
rides the persistent channels of the Blackboard. Events are wiped at turn's end
(`clear_events()`), but **variables, queues, facts, and memory survive** for the session
lifetime.

The pattern:

- **Turn N:** an extractor writes `fact(type="budget", key="primary", value=50000)` and
  sets `variable "stage" = "negotiation"`.
- **Turn N+1:** any agent gates on it via `trigger_conditions` (e.g. only run the
  Discount-Coach when `stage == "negotiation"`) or reads it in its Jinja prompt
  (`{{ blackboard.get_fact("budget", "primary").value }}`).

This is how a copilot accumulates *understanding* without re-deriving it every turn. A
fact established once is authoritative for the rest of the session; a queue of
unanswered-questions built up over five turns can be drained by a silence-triggered agent
later. **Use facts/variables for the slow-moving truth of the conversation; use events
only for "react to this *right now*."**

> **Underused capability.** Cross-turn memory (`memory_<id>`) is per-agent and now
> survives host re-instantiation thanks to the MR-1 read-path (engine syncs
> `blackboard.memory` → `shared_state["memory_<id>"]`, INV-14). A detector can remember
> "I already flagged this objection" across turns and refuse to re-flag — turning a noisy
> agent into a polite one for free.

---

## 5.7 Anti-patterns (the restraint catalog)

**1. Reading a sibling's write within a phase.** You author Agent B to read a variable
Agent A sets *this same turn*. B reads the pre-phase snapshot — it sees the **old** value
and silently misbehaves. *Fix:* A emits an event; B subscribes in Phase 2. The snapshot
is a wall by design (INV-2).

**2. Event storms.** A Phase-1 agent emits an event on *every* turn "just in case."
Phase 2 now runs every turn, doubling LLM cost and HUD noise. *Fix:* emit events only on
a genuine signal — events are interrupts, not heartbeats. Gate the detector ruthlessly so
silence is the default.

**3. Expecting deep event chains.** You design A → emits `x` → B reacts and emits `y` →
C reacts to `y`. **C never runs.** Phase-2 events are recorded but not dispatched; the
cascade is exactly one hop. *Fix:* collapse the chain (B does C's work too), or push the
second hop to the *next turn* via a fact/variable + a `trigger_conditions` gate.

**4. Priority collisions.** Two agents write the same variable at the same priority. The
winner is decided by registration order — invisible, fragile, and a nightmare to debug
when you reorder registration months later. *Fix:* give agents that contend for a key
**distinct** priorities, and let the merge be deterministic on purpose, not by accident.

**5. Confidence-as-authority for facts.** Cranking an LLM agent's `confidence` to 1.0 to
"win" a fact. It loses anyway to any higher-*priority* agent (INV-9). *Fix:* model
authority with **priority**; reserve confidence for tie-breaking among equals.

**6. Misconfigured subscribers.** Setting `subscribed_events` on a hand-rolled
`BaseAgent` subclass but forgetting `TriggerType.EVENT`. The engine silently excludes it
from Phase 2 (one warning, then quiet). *Fix:* include the EVENT trigger, or just use
`DynamicAgent`, which adds it for you.

---

## 5.8 Secret formula

> **THE SECRET FORMULA — Choreograph, don't orchestrate.**
>
> 1. **One job per agent.** Detectors detect, handlers handle. A detector's *only* output
>    on a hit is an **event** — it writes no advice itself.
> 2. **Couple through names, not code.** The single shared artifact between two agents is
>    an event-name string. Change a handler, swap a detector, add a third subscriber — no
>    other agent changes.
> 3. **Cheap observers gate one expensive reactor.** Many `gpt-4o-mini` watchers stay
>    silent by default; the smart model fires only in Phase 2, only on the turns that
>    earned it.
> 4. **Two beats, no more.** Anything needing a "third hop" is really *next turn's*
>    Phase 1 — carry it on a fact/variable, gate it with `trigger_conditions`.
> 5. **Priority is authority.** Rank agents so the Blackboard's merge resolves every
>    disagreement deterministically, in your favor, without a single `if`.
>
> Restraint is the architecture: the swarm is loud in *potential* and silent in *practice*.
# Chapter 6 — DynamicAgent: Prompt & Schema Engineering

> **Thesis check.** A copilot is a *swarm of cheap, reactive, gated agents coordinated through a blackboard, that stays silent by default and surfaces a perfectly-timed HUD card only when it earns the right to speak.* `DynamicAgent` is the unit of that swarm. The whole point of this chapter: **you build an entire agent — persona, triggers, output contract, memory, coordination — from a JSON config + a JSON schema, with no Python.** That is the single highest-leverage capability in `xubb_agents`. Master it and you author a new copilot behavior in minutes, not a deploy.

---

## 1. Mental model

`DynamicAgent` (`library/dynamic.py`) is a fully data-driven `BaseAgent`. You hand its constructor **one dict** (your config, typically a DB row or JSON file) and it becomes a live agent. Two documents define everything:

1. **The agent config** — persona (`text`), triggers (`trigger_config`), conditions (`trigger_conditions`), model, context window, and which schema to use (`output_format`).
2. **The output schema** — a file in `library/schemas/<output_format>.json` with two keys: `instruction` (the JSON shape you tell the model to emit) and `mapping` (how `DynamicAgent` reads that JSON back into an `AgentResponse`).

At evaluation time `DynamicAgent.evaluate()` runs a fixed pipeline:

```
load memory  →  slice transcript  →  render Jinja prompt
  →  assemble system prompt  →  call LLM (JSON mode)
  →  resolve root  →  SILENCE GATE  →  extract insight
  →  extract state / data / events / facts / queues / memory
```

The mental shift: **the schema's `mapping` is a tiny interpreter.** It is the contract that decouples "what the model says" from "what the framework does." Change the mapping, and the same LLM JSON drives a completely different `AgentResponse` — an insight, a silent state write, a UI-widget command, or an event that wakes another agent. You are not writing parsing code; you are *declaring* it.

---

## 2. Build a whole agent with no Python

Here is a complete, real copilot agent — config only. It detects price objections, only runs during the right phase, stays cheap, and is silent unless it has something to say:

```json
{
  "id": "price-objection-handler",
  "name": "Price Objection Handler",
  "text": "You are a sales objection specialist.\nDetect price-related objections and suggest value-based reframes.\nIf no objection, return { \"has_insight\": false }.\nIf objection detected, suggest a specific reframe (max 15 words).",
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
  "model_config": { "model": "gpt-4o-mini", "context_turns": 4 },
  "include_context": false,
  "output_format": "default_v2"
}
```

Every field maps to constructor logic in `DynamicAgent.__init__`:

| Config key | What it does (code) |
|---|---|
| `id` | `config_dict.get("id")` → `self.config.id`. **Crucial** — namespaces memory (`memory_<id>`) and selection filtering. Always set it. |
| `name` | Display name; defaults to `"Dynamic Agent"`. |
| `text` | The raw system prompt; rendered as a Jinja template each turn (`self.system_prompt`). |
| `trigger_config.mode` | One of `turn_based`/`keyword`/`silence`/`interval`/`event`, or a **list** to combine. |
| `trigger_config.keywords` | List or comma-string (auto-split). |
| `trigger_config.cooldown` | Seconds between runs (default **15**). Enforced by `BaseAgent.process`, even after errors. |
| `trigger_config.subscribed_events` | Events that wake this agent. **Non-empty auto-adds `TriggerType.EVENT`** — you don't have to list `"event"` in `mode`. |
| `trigger_conditions` | Precondition rules evaluated by the engine *before* the LLM call. Skips cost. |
| `priority` | From `trigger_config.priority` or top-level `priority`. Drives fact-conflict resolution and selection. |
| `model_config.model` / `model` | LLM id (default `gpt-4o-mini`). |
| `model_config.context_turns` / `context_turns` | Transcript window size (default **6**). `<= 0` means *all* segments. |
| `include_context` | Gates user-profile + RAG injection (default `true`). |
| `output_format` | Schema filename in `library/schemas/`. Missing file → falls back to `default.json` (with a warning). |

**Secret formula — the agent IS the config.** Treat `text`, `trigger_config`, `trigger_conditions`, and `output_format` as four orthogonal dials. Persona is one dial; *when* it fires is another; *what shape* it speaks in is a third; *whether it's even allowed to think* (conditions) is the fourth. Tuning a copilot is tuning dials across a roster of these dicts — never editing Python.

---

## 3. The schema `mapping` fields — full reference

A schema is `{ "instruction": "...", "mapping": {...} }`. `instruction` is appended last to the system prompt (it tells the model what JSON to emit). `mapping` tells `DynamicAgent` how to *read* that JSON. Every mapping key, grounded in `evaluate()`:

| Mapping key | Default | Role in `evaluate()` |
|---|---|---|
| `root_key` | `null` | If set, the insight is read from `result[root_key]` instead of the top level. Non-dict → treated as `{}`. |
| `check_field` | — | **The silence gate.** Boolean field whose truthiness decides whether to speak. |
| `content_field` | `"content"` | The insight text. **If empty/falsy, no insight is emitted even when the gate is open.** |
| `type_field` | `"type"` | Mapped to `InsightType`; unknown values default to `SUGGESTION`. |
| `confidence_field` | `"confidence"` | Coerced + clamped to `[0,1]` (A-3). |
| `expiry_field` | `"expiry"` | Seconds to display; coerced to positive int or `None` → default 15 (S-1). |
| `action_label_field` | `"action_label"` | Optional button text; coerced to non-empty str or `None` (S-1). |
| `metadata_field` | — | If set, copies `root_data[metadata_field]` to `insight.metadata`. |
| `state_field` | — | Legacy state write. `"memory_updates"` → private state synced to `memory_<id>`; any other key → direct `response.state_updates`. Read from `result` root, **not** `root_data`. |
| `data_field` / `data_key` | — | Generic sidecar: copies `result[data_field]` to `response.data[data_key]` (`data_key` defaults to `data_field`). Used by `ui_control`/`widget_control` for `ui_actions`. |
| `events_field` | `"events"` | List → `response.events` (dict or string items). |
| `variable_updates_field` | `"variable_updates"` | Dict → `response.variable_updates` (v2 blackboard write). |
| `queue_field` | `"queue_pushes"` | `{queue_name: [items]}` → `response.queue_pushes`. |
| `facts_field` | `"facts"` | List of `{type,key,value,confidence}` → `response.facts`. |
| `memory_field` | `"memory_updates"` | Dict → `response.memory_updates` **and** `self.private_state`. |

Note the dual read path: **insight fields are read from `root_data`** (the object under `root_key`, or the whole result if rootless), while **`state_field`, `data_field`, `events`, `variable_updates`, `queues`, `facts`, and `memory` are read from the top-level `result`.** A `root_key` only scopes the insight, not the sidecars.

### Comparing the six built-in schemas

| Schema | `root_key` | `check_field` | `content_field` | Gate style | Designed for |
|---|---|---|---|---|---|
| `default` | `null` | `has_insight` | **`message`** | (a) boolean | Legacy flat agents |
| `default_v2` | `null` | `has_insight` | `content` | (a) boolean | Modern full-featured agents |
| `custom1` | `null` | `sales_tip` | `sales_tip` | (a) boolean — *gate IS the content field* | Mapping demo / custom field names |
| `v2_raw` | `insight` | `null` | `content` | (b) presence | Insight + `state_snapshot` separation |
| `ui_control` | `insight` | `null` | `content` | (b) presence | Voice insight + `ui_actions` sidecar |
| `widget_control` | `insight` | `null` | `content` | (b) presence | Pure widget control (Hands) |

> **Verified-against-code correction.** The prose in `docs/prompt_engineering_guide.md` lists the `default` schema's key field as `content`. The actual `default.json` maps `content_field: "message"`. If you target `default`, your model must emit `"message"`, not `"content"` — or switch to `default_v2`, which does use `content`. **Prefer `default_v2` for new agents**; treat `default` as legacy.

> **`custom1` is a sharp lesson:** its `check_field` and `content_field` are the *same* key (`sales_tip`). The gate is truthiness of the content string itself — emit a non-empty tip and you speak; emit `""`/omit it and you're silent. Elegant, but it means there is no separate "I considered it and decided to stay quiet" signal.

---

## 4. The silence gate — restraint as a feature

Silence is the default posture of a copilot. The gate lives in `evaluate()` and has **three cases in strict precedence**:

```python
check_field = self.mapping.get("check_field")
if check_field:
    # (a) explicit boolean gate
    should_speak = root_data.get(check_field, False)
elif self.mapping.get("root_key"):
    # (b) presence gate: a non-empty root object means speak
    should_speak = bool(root_data)
else:
    # (c) gate-less + rootless: SILENT unless opted in
    should_speak = bool(self.mapping.get("speak_without_gate", False))
```

- **Case (a) — explicit gate.** `default`, `default_v2`, `custom1`. The model returns `has_insight: false` and the agent says nothing. A *missing* gate field also reads as `False` (safe default). This is the workhorse: most agents should use it and return `{ "has_insight": false }` on the vast majority of turns.
- **Case (b) — presence gate.** `v2_raw`, `ui_control`, `widget_control`. There's no boolean; emitting a non-empty `insight` object *is* the act of speaking. Omit `insight` (or send `{}`) and the agent is silent while still doing its sidecar work (state/widgets).
- **Case (c) — gate-less + rootless** (only reachable via a hand-written custom schema with neither `check_field` nor `root_key`). The **documented default policy is SILENCE** (A-1 / INV-11). The framework refuses to spam an insight every turn just because content exists. To get "speak whenever there's content," you must **opt in explicitly**:

```json
"mapping": { "content_field": "tip", "speak_without_gate": true }
```

Even when the gate is open, **`content` must be truthy** — an empty `content_field` produces no insight. Speaking is gate-open *and* content-present.

### The load-time misconfig warning (A-1 / INV-11)

`_warn_on_gateless_misconfig` runs once at construction. If your `mapping` has **no** `check_field` and **no** `root_key`, but the `instruction` text mentions a gate word (`has_insight`, `should_speak`, `speak`, `is_relevant`), `DynamicAgent` logs a warning: you *told the model* to emit a gate but never *wired it up*, so the model's intended silence will be silently dropped. The fix is in the warning: add `check_field`, or set `speak_without_gate: true` to acknowledge the speak-on-content default on purpose.

> **Secret formula — gate ruthlessly, then trust the gate.** Pick a gated schema (`default_v2`) or a presence schema (`v2_raw`) deliberately; never ship a gate-less custom schema by accident. Then write the prompt so silence is the *easy* path: tell the model, in the instruction, that `{ "has_insight": false }` is the correct answer when the conversation is flowing. A copilot that whispers once is worth more than one that narrates constantly.

---

## 5. Reliable structured output

`evaluate()` calls `await self.llm.generate_json(...)`. The JSON-mode request (provider `response_format: json_object` under the hood) plus an explicit `instruction` block is what makes parsing reliable. Belt-and-suspenders rules grounded in the parser:

- **Mirror the mapping in the instruction.** The model only emits the keys your `mapping` reads. If your mapping uses `content_field: "message"`, your instruction's example JSON must show `"message"`. Asking the model for fields the parser never reads is wasted tokens and confusion (see anti-patterns).
- **Robust coercion means a bad value won't crash a good insight.** `confidence` is run through `_coerce_confidence` (non-numeric like `"high"` → `1.0`; out of range → clamped; `NaN`/`inf` handled). `expiry` → `_coerce_expiry` (positive int or `None`→15). `action_label` → non-empty str or `None`. So you can *ask* for these and a sloppy model response degrades gracefully instead of raising.
- **Unknown `type` is safe.** Any `type` string that isn't a valid `InsightType` falls back to `SUGGESTION`. Still, instruct the model to use the real enum: `suggestion | warning | opportunity | fact | praise`.
- **Failure is silent, not fatal.** If the LLM call throws, `evaluate` logs and returns `None`; a `None` result logs a warning and returns an empty `AgentResponse`. The swarm keeps running.

---

## 6. Jinja prompt templating

`self.system_prompt` (your `text`) is compiled fresh each turn with a **class-level `SandboxedEnvironment`** and rendered with this exact context:

```python
template.render(
    state=context.shared_state,         # {{ state.phase }}  (v1 alias)
    memory=working_memory,              # {{ memory.last_warning_turn }}
    context=context,                    # {{ context }}
    user_context=context.user_context,  # {{ user_context }}
    blackboard=context.blackboard,      # {{ blackboard.variables.phase }}
    agent_id=self.config.id             # {{ agent_id }}
)
```

Read the live blackboard to make the agent *context-aware before the LLM even sees the transcript*:

```jinja2
{% if blackboard.variables.phase == "negotiation" %}
You are in NEGOTIATION. Be value-focused.
{% endif %}

Open questions ({{ blackboard.queues.pending_questions | default([]) | length }}):
{% for q in blackboard.queues.pending_questions | default([]) %}- {{ q }}
{% endfor %}

My last warning was turn {{ memory.last_warning_turn | default('never') }}.
```

`working_memory` is `self.private_state` overlaid with the engine-synced `shared_state["memory_<id>"]` (MR-1). All standard filters work (`default`, `length`, `join`, `tojson`, ...).

**Rendering fails gracefully.** If the template raises, `evaluate` logs a warning and falls back to the *raw, unrendered* prompt — the agent stays alive. So guard every blackboard access with `| default(...)`; an `{{ blackboard.variables.phase }}` on a fresh session won't crash, but a deeper attribute chain might, and silently shipping the raw `{{ ... }}` text to the model is worse than a guarded empty string.

### The sandbox (SSTI defense)

The environment is `jinja2.sandbox.SandboxedEnvironment`. Access to `__class__`, `__globals__`, `__mro__`, etc. raises `SecurityError`. This matters because **prompt `text` often comes from a DB / user-authored persona** — untrusted template input. The sandbox is your guardrail against server-side template injection. Do not "optimize" it away to a plain `Environment`, and don't interpolate raw user strings into the template *source* (render them as *data* via the context instead).

---

## 7. Insight vs. state separation

The single most important architectural idea here: **an insight is what the user sees; state is what the swarm shares.** They are different output channels and a single turn can use both, either, or neither.

- **Insight** → `response.insights` → a HUD card (the *Voice*). Gated, expiring, content-bearing.
- **State** → `variable_updates` / `facts` / `queue_pushes` / `events` / `memory_updates` → the *blackboard* (silent coordination). Read from the top-level result, ungated.

This is what lets you build the canonical copilot pattern — a **silent background monitor** that updates state every turn but never shows a card:

```json
{
  "id": "sentiment-monitor",
  "output_format": "default_v2",
  "include_context": false,
  "text": "Analyze emotional tone. Always return has_insight:false. Emit variable_updates only.",
  "trigger_config": { "mode": "turn_based", "cooldown": 3 },
  "priority": 50
}
```
Model emits: `{ "has_insight": false, "variable_updates": { "sentiment": { "score": 0.3 } } }`

The gate keeps it silent (case a, `has_insight:false`); the `variable_updates` still land on the blackboard. A downstream gated agent then reads `{{ blackboard.variables.sentiment.score }}` (or gates on it via `trigger_conditions`) and is the *only* one that ever speaks. Detection and response are separated; cheap and quiet does the watching, expensive and rare does the talking.

`v2_raw` (and `ui_control`/`widget_control`) bakes this separation into the schema shape: `insight` (root-keyed, presence-gated Voice) sits next to `state_snapshot` / `ui_actions` (silent Hands). Choosing one of those schemas is choosing the Voice/Hands split at the contract level.

---

## 8. Expiry, action_label, confidence

These three "polish" fields make HUD timing feel intentional (S-1 / A-3). They are read from `root_data` via their mapped keys and passed straight into `create_insight`:

- **`confidence`** (`confidence_field`, default `confidence`) — clamped to `[0,1]`; a junk value never fails validation. Use it to drive HUD prominence; don't over-trust model self-reports.
- **`expiry`** (`expiry_field`, default `expiry`) — seconds the card lives; positive int or `None`→**15**. This is your timing lever: a 5-second flash for an "opportunity," 30 seconds for a "warning" the user must act on.
- **`action_label`** (`action_label_field`, default `action_label`) — optional button text on the card; non-empty str or `None`.

`create_insight` (`core/agent.py`) only passes `expiry`/`action_label` through when non-`None`, so the `AgentInsight` model defaults (`expiry=15`, `action_label=None`) stand otherwise. Ask for them in the instruction *only if your schema's mapping reads them* — `v2_raw`'s instruction shows `expiry`, and its mapping reads it; `default`/`default_v2` don't map an `expiry_field` explicitly but inherit the `"expiry"` default key, so `expiry` in the JSON still flows through.

> **Secret formula — timing is a field, not an afterthought.** `expiry` is the "perfectly-timed HUD" dial. A copilot that picks expiry per insight type — flash the opportunity, hold the warning — feels alive. Bake an `expiry` convention into your schema instruction and let the model set it.

---

## 9. Designing a reusable schema library for a copilot

Schemas are *shared infrastructure* across your whole agent roster. Treat `library/schemas/` as a small, curated set, not a dumping ground. A practical starting library:

1. **`default_v2`** — the everyday gated insight agent (coaches, detectors that also advise). The 80% case.
2. **`v2_raw`** — when an agent both advises *and* writes structured `state_snapshot`, and you want presence-gating.
3. **`widget_control` / `ui_control`** — Hands agents that drive HUD widgets via the `ui_actions` data sidecar (optionally with a Voice insight).
4. **One narrow custom schema per *novel output shape*** (like `custom1`) — only when field names or structure genuinely differ. Renaming `content`→`message` is not worth a new schema; a new *sidecar channel* is.

Rules of thumb:

- **Reuse the gate; vary the prompt.** Ten different coaching agents should share `default_v2` and differ only in `text` + triggers. The schema encodes the *contract*; the config encodes the *behavior*.
- **One schema = one output contract.** If two agents need the same JSON shape, they share a schema. Divergent shapes get divergent files — but keep the count low.
- **Name by capability, not by agent.** `widget_control`, not `sentiment_widget_schema`. Schemas outlive individual agents.
- **Keep instructions tight.** The `instruction` is concatenated into every prompt of every agent using it — bloat there is paid on every single LLM call.

---

## 10. Anti-patterns

- **No silence gate → HUD spam.** Shipping a gate-less, rootless custom schema and relying on "the model will know when to stay quiet." It won't, and case (c) defaults to silence precisely to protect you — but if you slap `speak_without_gate: true` on without a `check_field`, you get a card every turn there's any content. **Fix:** use `check_field` (case a) or a `root_key` presence gate (case b).

- **Over-stuffed schemas.** Cramming events, facts, queues, ui_actions, state, *and* insight into one schema that every agent loads. Most agents need a gate + content + maybe one sidecar. Every extra field in `instruction` is per-call token cost and a chance for the model to hallucinate structure. **Fix:** minimal schema per role; reach for `default_v2` and only add the sidecars you actually consume.

- **Asking for fields the parser drops.** Telling the model to emit `"priority"` on a fact (the engine stamps that from agent config — it's ignored in JSON), or emitting `content` when your mapping reads `message`, or putting `variable_updates` inside the `root_key` object where the parser won't look (it reads sidecars from the top-level result). **Fix:** make the instruction's example JSON byte-for-byte match what `mapping` reads, at the right nesting level.

- **Unsanitized template input (SSTI).** Concatenating user/DB text into the *template source* (`"Hello " + user_name + ", {{ blackboard... }}"`), or swapping `SandboxedEnvironment` for a plain `Environment` to "fix" a filter. **Fix:** keep the sandbox; pass user text as render *data*, never as template source.

- **Ignoring the memory scratchpad.** Re-deriving "did I already warn about pricing?" from the transcript every turn, leading to repeated identical cards. **Fix:** write `memory_updates` (synced to `memory_<id>`), read it back via `{{ memory.* }}`, and gate your own repetition in the prompt.

- **Targeting `default` for new work.** Its `content_field` is `message` (legacy), which trips up authors who copy `content`-based examples. **Fix:** use `default_v2`.

- **Unguarded Jinja that silently ships raw braces.** A deep `{{ blackboard.x.y.z }}` chain throws on a fresh blackboard; `evaluate` falls back to the *raw* prompt, sending literal `{{ ... }}` to the model. **Fix:** guard with `| default(...)` and test the cold-start render.

---

## 11. The pipeline, end to end (reference)

```
__init__:   parse triggers/model/output_format → load schema → A-1 misconfig warning
evaluate:
  0. memory   = shared_state["memory_<id>"] overlaid on private_state
  1. slice    = last context_turns segments (<=0 → all)  (+ role modifier)
  2. render   = Jinja(text) in sandbox  [state, memory, blackboard, agent_id, ...]
  3. assemble = [user_profile?] [language?] rendered_prompt [MEMORY] [RAG?] [trigger?] [instruction]
  4. call     = llm.generate_json(model, messages)   (JSON mode)
  5. root     = result[root_key] or result
  6. GATE     = check_field | root presence | speak_without_gate
  7. insight  = content + type + confidence(clamp) + expiry + action_label + metadata
  8. sidecars = state_field | data_field | events | variable_updates | queues | facts | memory
```

That is the whole agent. No subclass, no Python — just the config dict and the schema file.

---

### Secret formula one-liners

1. **The agent is the config** — persona, *when*, *what-shape*, and *whether-it-thinks* are four orthogonal dials in a JSON dict; tune dials, never code.
2. **Gate ruthlessly, then trust the gate** — choose a gated (`default_v2`) or presence (`v2_raw`) schema on purpose, write the prompt so `has_insight:false` is the easy path, and let silence be the default.
3. **Insight is the Voice, state is the blackboard** — one cheap silent monitor watches and writes state every turn; one rare gated agent reads that state and is the only thing that ever speaks.
4. **Timing is a field** — set `expiry` per insight type (flash the opportunity, hold the warning) so the HUD feels deliberately timed, not noisy.
5. **The mapping must mirror the instruction** — the model only emits, and the parser only reads, the exact keys at the exact nesting your `mapping` declares; everything else is wasted tokens or dropped data.
6. **Reuse the gate, vary the prompt** — ten agents share one schema (the contract) and differ only in `text` + triggers (the behavior); keep `library/schemas/` small and capability-named.
# Chapter 7 — Memory, Facts & Understanding Over Time

> The copilot's edge is not any single clever insight. It is that the world-model
> gets *richer every turn*: who the stakeholders are, what the budget is, which
> objections surfaced, where the timeline stands. A swarm of cheap observers,
> each writing a small structured note to a shared surface, compounds into an
> understanding no single prompt could hold. This chapter is about the three
> places that understanding lives — **Facts**, **Memory**, and **Variables** —
> and how to use each one for exactly what it is good at.

---

## Mental model: three stores, three jobs

The Blackboard (`core/blackboard.py`) gives you several typed containers. Three
of them carry knowledge across time, and they are *not* interchangeable:

| Store | What it is | Scope | Lifetime | Use for |
|-------|-----------|-------|----------|---------|
| **Facts** | A priority-ranked, deduplicated knowledge base | **Shared** across all agents | Session | Durable shared knowledge: stakeholders, budget, objections, the world-model |
| **Memory** | A per-agent private scratchpad | **Private** to one `agent_id` | Session (survives re-instantiation) | One agent's cross-turn continuity: "what did I already say / track / count?" |
| **Variables** | Session-scoped key/value | **Shared** | Session | Current ephemeral state / flags: `phase`, `mode`, `last_topic` |

A one-line decision rule you should internalize:

> **Facts = shared knowledge. Memory = private continuity. Variables = current state.**

If you remember nothing else, remember that. Most design mistakes in a copilot
are a value sitting in the wrong one of these three.

---

## Part 1 — Facts as a priority-ranked knowledge store

### The (type, key) model

A `Fact` (`core/models.py`) is a small structured record:

```python
class Fact(BaseModel):
    type: str                      # category: "budget", "timeline", "stakeholder"
    key: Optional[str] = None      # instance: "stakeholder.cfo", "budget.primary"
    value: Any                     # the extracted value
    confidence: float = 1.0        # ge=0.0, le=1.0
    priority: int = 0              # engine-stamped; agents SHOULD NOT set this
    source_agent: str
    timestamp: float               # session-relative seconds
```

Facts are **deduplicated by `(type, key)`**. This is the heart of the model:

- `key` set → the fact is *one instance among many of its type*. `stakeholder`
  with `key="stakeholder.cfo"` and `stakeholder` with `key="stakeholder.champion"`
  coexist. You read them all with `get_facts_by_type("stakeholder")`.
- `key=None` → the type is a **singleton**. `add_fact` matches *any* existing
  fact of that type and resolves the conflict. Use this for "there is exactly one
  current X": `type="deal_stage"`, `type="primary_budget"`.

```python
# A multi-instance fact: many stakeholders coexist under one type
bb.get_facts_by_type("stakeholder")   # [cfo, champion, blocker, ...]

# A singleton fact: there is one current deal stage
bb.get_fact("deal_stage")             # the single most-authoritative one
bb.has_fact("budget", "budget.primary")
```

### F-1 / INV-9: how conflicts resolve

When a new fact collides with an existing one on `(type, key)`,
`Blackboard.add_fact` resolves it in **strict order**:

1. **higher agent `priority` wins**;
2. ties broken by **higher `confidence`**;
3. remaining ties by **later registration order**.

The implementation is a single lexicographic comparison — the new fact replaces
the old one iff `(priority, confidence) >= (existing.priority, existing.confidence)`:

```python
# core/blackboard.py — add_fact
if existing:
    if (fact.priority, fact.confidence) >= (existing.priority, existing.confidence):
        self.facts.remove(existing)
        self.facts.append(fact)
else:
    self.facts.append(fact)
```

Two consequences you must design around:

- **Priority dominates confidence.** A high-priority extractor that emits a fact
  at `confidence=0.6` *still beats* a low-priority extractor at `confidence=0.99`.
  Confidence is only the tiebreaker *within equal priority*. This is intentional:
  it lets you make one extractor authoritative.
- **`>=` means later equal writes win.** On a full `(priority, confidence)` tie,
  the most recent registration replaces the incumbent — the freshest reading of
  equally-trusted observers wins.

### Where `priority` comes from — don't set it yourself

Agents **should not** set `fact.priority`. The engine stamps it at merge time
with the *emitting agent's* priority. In `core/engine.py._merge_responses`:

```python
for fact in resp.facts:
    fact.priority = priority          # the emitting agent's priority
    blackboard.add_fact(fact)
```

And merges run in **ascending priority order** (low → high write last), so the
whole pipeline is deterministic last-write-wins.

> The practical lever: **to make an extractor authoritative, raise the *agent's*
> `priority`** in its trigger config. A `budget_extractor` at priority 10 will
> overwrite the loose guesses of a general `context_observer` at priority 0 — no
> matter how confident the observer was.

### Confidence: the within-tier tiebreaker

Set `confidence` to express *how sure this reading is*, knowing it only matters
among same-priority agents. Two cheap observers both extracting `budget`?
Whichever is more sure wins. A good extractor prompt should return a calibrated
confidence; `DynamicAgent` passes it straight through into the `Fact`
(`core/dynamic.py`, fact extraction block).

### Pattern: cheap extractors write facts, conditions gate on fact-presence

This is the core "accumulate understanding" loop, and it is the thesis of the
whole playbook applied to knowledge:

1. **Cheap observers** (small models, narrow prompts) each watch for one kind of
   thing and emit a `Fact` when they see it. A stakeholder-spotter, a
   budget-spotter, an objection-spotter, a timeline-spotter.
2. **Heavier agents gate on fact-presence** via `trigger_conditions`, so they
   only fire once the world-model is rich enough to act on.

```jsonc
// objection_handler — only wakes up once an objection fact exists
{
  "name": "Objection Handler",
  "trigger_conditions": { "has_fact": { "type": "objection" } },
  "trigger_config": { "priority": 5 }
}
```

```jsonc
// LLM output from a cheap objection-spotter (DynamicAgent facts_field)
{
  "facts": [
    { "type": "objection", "key": "objection.price",
      "value": "Thinks the annual price is too high vs. competitor X",
      "confidence": 0.8 }
  ]
}
```

The extractors are dumb and constant-cost; the expensive reasoning only fires
when the blackboard says it is worth it. That is *gating ruthlessly* applied to
knowledge rather than to speech.

### Pattern: enrich, don't restate — the world-model grows each turn

Each turn, observers add or sharpen facts. Singleton facts (`key=None`) let a
later, more authoritative reading *replace* an earlier vague one cleanly:

```python
# Turn 3: vague observer (priority 0)
Fact(type="deal_stage", value="probably discovery", confidence=0.5)
# Turn 7: dedicated stage classifier (agent priority 8) overwrites it
Fact(type="deal_stage", value="negotiation", confidence=0.9)
# get_fact("deal_stage") now returns "negotiation" — priority won.
```

Multi-instance facts (`key` set) accumulate the cast of characters:
`stakeholder.cfo`, `stakeholder.champion`, `stakeholder.blocker` all coexist and
the HUD can render the whole org chart at the right moment.

---

## Part 2 — Agent memory as a cross-turn scratchpad

Facts are shared. **Memory is private to one agent.** It is where an agent keeps
*its own* continuity: a running count, the last thing it said (to avoid
repeating itself), a checklist of what it has already covered.

### MR-1 / INV-14: memory survives agent re-instantiation

This is the most **underused** durability guarantee in the framework, and it
exists because of a subtle bug class. Memory is *stored on the blackboard*
(`blackboard.memory[agent_id]`), but `DynamicAgent` *reads* it from
`shared_state["memory_<id>"]`. The engine bridges the two **before agents run**,
in `_sync_state_to_legacy` (`core/engine.py`):

```python
# MR-1: blackboard memory → shared_state["memory_<id>"], every turn, pre-run
for agent_id in list(context.blackboard.memory.keys()):
    context.shared_state[f"memory_{agent_id}"] = \
        context.blackboard.get_memory(agent_id)
```

Why this matters for a real copilot: many hosts **re-instantiate agents every
turn** (load config from DB, build a fresh `DynamicAgent`, run, discard). Without
MR-1, cross-turn memory survived only in the agent's in-process `private_state` —
which dies with the instance. With MR-1, **the blackboard is the source of
truth**, so a freshly-built agent reads back everything it wrote last turn.

The write side closes the loop. In `DynamicAgent.evaluate`, parsed
`memory_updates` go into `response.memory_updates`; the engine applies them in
`_merge_responses`:

```python
if resp.memory_updates and agent_id:
    blackboard.update_memory(agent_id, resp.memory_updates)   # persists on blackboard
```

So the full cross-turn cycle is:

```
turn N:   agent emits memory_updates
          → engine: blackboard.update_memory(agent_id, ...)
turn N+1: engine: sync blackboard.memory → shared_state["memory_<id>"]
          → DynamicAgent reads shared_state["memory_<id>"] into working_memory
          → injected into the prompt as [YOUR MEMORY / SCRATCHPAD]
```

In the prompt, the agent literally sees its own scratchpad
(`current_memory = json.dumps(working_memory)`), so a memory-aware agent can
reason "last turn I noted the CFO was skeptical; has that changed?"

### M-1 / INV-8': memory is deep-copied on every boundary

Every read and write crosses a **deep-copy** boundary. `get_memory` returns a
copy; `set_memory` / `update_memory` store a copy:

```python
def get_memory(self, agent_id):           return deepcopy(self.memory.get(agent_id, {}))
def set_memory(self, agent_id, data):     self.memory[agent_id] = deepcopy(data)
def update_memory(self, agent_id, upd):   self.memory[agent_id].update(deepcopy(upd))
```

Consequence: **mutating the dict you got back from `get_memory` does nothing to
blackboard state.** This is a guarantee, not an accident — it stops one agent's
in-place mutation of a nested object from silently corrupting shared state. The
only way to persist a change is to *return* `memory_updates` (or call
`update_memory` explicitly). `DynamicAgent` already respects this: it builds a
`working_memory = dict(self.private_state)` copy for the prompt and never relies
on mutating the returned structure.

### Pattern: memory for "what have I already done?"

The canonical use is anti-repetition and progress-tracking — central to
*restraint as a feature*:

```jsonc
// LLM output: agent records what it covered so it won't repeat next turn
{
  "has_insight": true,
  "message": "Worth confirming the CFO is the economic buyer.",
  "memory_updates": {
    "covered_topics": ["intro", "budget_range", "economic_buyer"],
    "last_nudge_turn": 12
  }
}
```

Next turn the agent reads `covered_topics` back from its scratchpad and stays
quiet about anything already covered. Memory is how a single observer builds
*its own* understanding over time without polluting the shared Fact store.

---

## Part 3 — Facts vs Memory vs Variables: choosing correctly

A worked example — the copilot is tracking a sales call:

- **"The CFO is the economic buyer."** → **Fact**
  (`type="stakeholder", key="stakeholder.cfo"`). Shared knowledge; many agents
  want it; it should dedupe and be overwritable by a more authoritative reader.
- **"I (the nudge agent) already suggested confirming the buyer."** → **Memory**
  (`memory_updates.covered_topics`). Private continuity; nobody else cares; it
  exists only to stop *this* agent repeating itself.
- **"We are currently in phase 2 / objection-handling mode."** → **Variable**
  (`set_var("mode", "objection")`). Current ephemeral state; cheap to read in a
  Jinja condition; no need for dedup or priority.

Litmus tests:

- *Would another agent want to read this?* Yes → Fact (or Variable if it's just a
  flag). No → Memory.
- *Does it represent durable knowledge about the world?* → Fact.
- *Is it "where are we right now"?* → Variable.
- *Is it "what have I personally done/seen"?* → Memory.

---

## Anti-patterns

- **Putting durable knowledge in Variables.** A Variable has no `(type, key)`
  dedup, no priority resolution, no confidence. Stuffing the stakeholder map into
  `variables["cfo"]` means the *last writer always wins blindly* — a sloppy
  observer clobbers a careful one. Durable, contended knowledge belongs in Facts
  precisely so F-1 can arbitrate.

- **Low-priority authoritative extractors.** If your dedicated `budget_extractor`
  runs at `priority=0`, every passing general observer can overwrite its reading
  on a `(priority, confidence)` tie or beat it on confidence. The authoritative
  extractor must have **higher agent priority** so it wins regardless of how
  confident the noise is. This is the single most common Facts mistake.

- **Mutating returned memory and expecting it to stick.** `get_memory` returns a
  deep copy (M-1). Mutating it in place is a no-op against the blackboard. Persist
  by returning `memory_updates`.

- **Treating memory as shared.** Memory is keyed by `agent_id` and private. Agent
  A cannot read agent B's memory. If two agents need the same value, it is a Fact
  or a Variable, not Memory. (Mirror trap: writing shared truth into one agent's
  Memory hides it from the swarm.)

- **Unbounded fact growth.** Multi-instance facts (`key` set) never dedup across
  *different* keys, so an extractor that mints a fresh `key` every turn
  (`objection.{turn}`) grows the store without bound and bloats every prompt that
  renders facts. Prefer **stable keys** (`objection.price`) so re-observation
  *updates* rather than *appends*, or use a **singleton** (`key=None`) when there
  is conceptually one current value.

- **Setting `fact.priority` by hand.** Agents that set their own `priority` fight
  the engine, which overwrites it at merge with the emitting agent's priority.
  Control authority through the *agent's* config priority, not the fact field.

---

> ### Secret formula — Authority through priority, continuity through memory
>
> The whole knowledge layer comes down to two moves the engine makes for you:
>
> 1. **Authority is an agent property, not a fact property.** Want one extractor
>    to be the source of truth for `budget`? Don't make it more *confident* —
>    make the *agent* higher *priority*. F-1 stamps the agent's priority onto the
>    fact and priority strictly dominates confidence, so the authoritative reader
>    wins even when it's unsure, and noisy observers can never overwrite it. Build
>    a **tiered extractor hierarchy**: cheap broad observers at priority 0 sketch
>    the world-model; dedicated specialists at high priority lock in the canonical
>    values.
>
> 2. **Memory is free cross-turn continuity, even if you throw the agent away.**
>    MR-1 makes the blackboard — not the live object — the source of truth, so a
>    host that rebuilds agents every turn loses nothing. Lean on it: have each
>    observer keep a private `covered_topics` / `last_seen` scratchpad and gate
>    its own speech on it. That is how restraint compounds — the copilot
>    remembers what it already said and stays quiet.
>
> Put together: **shared knowledge arbitrated by priority + private continuity
> guaranteed across turns = an understanding that only gets sharper, and a HUD
> that only speaks when the new understanding earns it.**
# Chapter 8 — The Real-Time HUD / Insight UX Playbook

> *Turning accumulated understanding into perfectly-timed HUD moments. The HUD's
> job is not to show what the swarm thinks — it is to show the **one** thing
> worth a human's 2 seconds of attention, and to show **nothing** the rest of
> the time.*

This chapter is about the last mile: an `AgentInsight` has been earned, it has
survived the silence gate, and now it must land on a live overlay without
breaking the user's flow. Everything here is grounded in the real v2.2 surface:
`AgentInsight` (`core/models.py`), `create_insight` (`core/agent.py`), the
silence gate in `library/dynamic.py`, the stock schemas in
`library/schemas/*.json`, the trace shape in `utils/tracing.py`, and the
reference visualizer `tools/debugger.html`.

---

## 1. Mental model: the HUD is a 2-second stage, not a log

A real-time copilot HUD is a **single, tiny, glanceable stage**. At any instant
the user can absorb roughly one short line of text out of the corner of their
eye while doing something else (talking, selling, presenting). That is the
entire budget.

So the host does not "render the insights." The host **curates** them. The swarm
may produce three insights in a turn; the HUD shows zero or one. The framework
gives you exactly the fields you need to make that curation deterministic:

| Field on `AgentInsight` | What the HUD uses it for |
| --- | --- |
| `type` (`InsightType`) | **Zone + color + urgency** — where on the overlay and what tone |
| `content` (`min_length=2`) | The glanceable line — must read in one beat |
| `confidence` (`0.0–1.0`) | **Rank and filter** — drop the noise, surface the strongest |
| `expiry` (int seconds, default `15`) | **Ephemerality** — how long the moment lives before it dissolves |
| `action_label` (optional str) | The single interactive **button** the user can click |
| `metadata` (dict) | UI rendering hints: zone override, color, voice style, icon |
| `agent_id` / `agent_name` | Attribution, dedup, and per-source cooldown bookkeeping |

The golden rule that runs through every section: **silence is the default and a
feature.** The framework is built so that the *absence* of a structural gate
defaults to silence (INV-11, see §3), confidence defaults high but is meant to
be filtered, and `expiry` guarantees that even a shown insight returns the stage
to silence on its own.

---

## 2. The `InsightType` taxonomy — the zone/urgency model

`InsightType` is the single most important UX decision per insight, because it
drives **where** the insight lands and **how loud** it is. The enum
(`core/models.py`) carries real zone semantics in its comments:

```python
class InsightType(str, Enum):
    SUGGESTION = "suggestion"
    WARNING = "warning"
    OPPORTUNITY = "opportunity"  # Zone A: Urgent Positive
    FACT = "fact"
    PRAISE = "praise"
    ERROR = "error"              # For system alerts
```

The reference debugger (`tools/debugger.html`) already encodes the canonical
color mapping for five of these, which is your de-facto HUD palette:

| `type` | Border / accent (from debugger) | Zone & urgency | When to use |
| --- | --- | --- | --- |
| `WARNING` | red (`border-red-500`) | **Urgent Negative** — top, demands a glance | Risk in flight: objection unhandled, you're talking over someone, a claim is wrong. Interrupt-worthy. |
| `OPPORTUNITY` | emerald (`border-emerald-500`) | **Zone A: Urgent Positive** | A door just opened — buying signal, a perfect moment to ask for the close. Time-critical *good* news. |
| `SUGGESTION` | blue (`border-blue-500`) | **Advisory** — calm, non-urgent | A nudge: "ask about timeline," "slow down." Default coaching tone. |
| `FACT` | slate/grey (`border-slate-500`) | **Ambient / reference** | Earned knowledge worth keeping on screen: "Budget: $50k," "CFO is the decision-maker." Lowest urgency, longest-lived. |
| `PRAISE` | pink (`border-pink-500`) | **Reinforcement** | Positive feedback to keep the user doing the right thing. Brief, warm. |
| `ERROR` | (system) | **System alert** — out-of-band | NOT a coaching insight. Emitted automatically by `BaseAgent.process` when an agent throws (see `core/agent.py`). Render in a dev/system channel, never in the coaching zone. |

**The urgency gradient is the design.** `WARNING` and `OPPORTUNITY` are the only
two types that justify interrupting the user mid-flow; everything else is
advisory or ambient. A HUD that paints `SUGGESTION`s as red alerts has thrown
away the taxonomy.

Two non-obvious rules:

- **`ERROR` is not yours to author for UX.** It is the framework's failure
  channel. When `evaluate` raises, `process` returns a single `ERROR` insight
  with `confidence=1.0` so the failure is visible. Route `ERROR` to a system
  tray, not the coaching overlay — otherwise an LLM hiccup becomes a red scare
  on the user's stage.
- **`FACT` is the one type designed to *persist*.** Suggestions and warnings are
  about *now*; a fact is durable understanding. Give facts long `expiry` and a
  quiet ambient zone (see §5).

---

## 3. The restraint discipline — silence as the default

This is the heart of the chapter. A great HUD is defined by what it *doesn't*
show. v2.2 makes silence the structural default at four layers; use all four.

### 3.1 The silence gate (`should_speak`) — the agent never speaks by accident

`DynamicAgent.evaluate` (`library/dynamic.py`) decides whether an insight is even
created using a three-case gate. This is the INV-11 contract, verbatim from the
code's precedence:

```python
check_field = self.mapping.get("check_field")
if check_field:
    # (a) Explicit gate field drives the decision.
    should_speak = root_data.get(check_field, False)
elif self.mapping.get("root_key"):
    # (b) Presence of a non-empty root object is the gate.
    should_speak = bool(root_data)
else:
    # (c) Gate-less + rootless: default to silence unless opted in.
    should_speak = bool(self.mapping.get("speak_without_gate", False))
```

Read the three cases as three HUD philosophies:

- **(a) Boolean gate** — the stock `default` / `default_v2` schemas wire
  `check_field: "has_insight"`. The model must *actively decide* to speak by
  setting `has_insight=true`. Missing or `false` ⇒ silence. This is the safest
  default for coaching agents. Note the default is `False`: if the model forgets
  the field, the agent stays quiet.
- **(b) Presence gate** — `ui_control` / `widget_control` set
  `root_key: "insight"` with `check_field: null`. Emitting a non-empty `insight`
  object *is* the act of speaking; an empty/absent root ⇒ silence. Good when the
  voice insight is optional alongside silent UI actions.
- **(c) Gate-less + rootless** — a custom schema with neither. The **documented
  default is silence**, full stop. You must `"speak_without_gate": true` to opt
  into "content present ⇒ speak." And the framework *warns you at load time*
  (`_warn_on_gateless_misconfig`, INV-11/A-1) if your instruction text mentions
  a gate field like `has_insight` but your mapping forgot to wire it — the exact
  misconfiguration that silently turns a polite agent into a HUD spammer.

**Takeaway:** prefer an explicit `check_field` gate for any coaching agent. The
gate is your first and best spam filter, evaluated before an insight even exists.

### 3.2 Confidence thresholds — filter at the host, rank for the stage

`confidence` defaults to `1.0` but is meant to be *used*, not trusted blindly.
v2.2 hardens it: `_coerce_confidence` (A-3) clamps any LLM-supplied value into
`[0,1]` and falls back to `1.0` on garbage ("high", `NaN`, `1.5`) so a bad value
never crashes the insight — but a bad value also never *helps* you filter. Have
agents emit honest confidence, then **threshold at the host**:

```python
# Host-side curation (you own this — the framework hands you raw insights)
MIN_CONFIDENCE = {
    InsightType.WARNING: 0.55,      # warnings can be more speculative — better safe
    InsightType.OPPORTUNITY: 0.70,
    InsightType.SUGGESTION: 0.75,   # nudges must be earned
    InsightType.FACT: 0.80,         # don't pollute the knowledge zone with guesses
    InsightType.PRAISE: 0.80,
}

def curate(insights: list[AgentInsight]) -> list[AgentInsight]:
    kept = [i for i in insights if i.confidence >= MIN_CONFIDENCE.get(i.type, 0.75)]
    # Rank: urgency first, then confidence. Limited stage ⇒ usually take top 1.
    return sorted(kept, key=lambda i: (URGENCY[i.type], i.confidence), reverse=True)
```

Two thresholds do two jobs: the **floor** kills noise; the **ranking** picks the
single winner for the stage. A confident `WARNING` beats a confident
`SUGGESTION`; among equals, higher confidence wins.

### 3.3 Expiry timing — the moment dissolves itself

`expiry` (default `15` seconds) is the HUD's self-cleaning mechanism: it is "how
long to display." Tune it to the type's half-life:

```python
EXPIRY_BY_TYPE = {
    InsightType.WARNING: 6,       # act now or it's irrelevant
    InsightType.OPPORTUNITY: 8,   # the door is closing
    InsightType.SUGGESTION: 10,   # a nudge, then gone
    InsightType.PRAISE: 5,        # a flash of warmth
    InsightType.FACT: 45,         # durable — keep it on the ambient rail
}
```

`expiry` is parsed through `_coerce_expiry` (S-1): non-positive or non-numeric
values fall back to the model default of 15s, so you can never accidentally pin
an insight forever or for zero seconds. **Short expiry is restraint too** — an
expired insight returns the stage to silence without the user (or the host)
lifting a finger.

### 3.4 Cooldowns — per-agent rate limiting, enforced by the framework

The fourth layer is temporal. `AgentConfig.cooldown` (default `10s`, `15s` for
`DynamicAgent`) is enforced inside `BaseAgent.process`:

```python
if (now - self.last_run_time) < effective_cooldown:
    return None
```

A cheap observer cannot fire every turn even if it wants to. Crucially,
`last_run_time` updates in the `finally` block on **every** run — success,
silence, or error — so an agent that runs and stays silent still spends its
cooldown. Role modifiers can slow a chatty agent down (`cooldown_modifier`,
floor of 5s). Only a `FORCE` trigger (user explicitly asks "what should I say?")
bypasses cooldown and the gate.

**The four layers compose into restraint:** gate (does an insight exist?) →
confidence (is it strong enough?) → cooldown (is this agent allowed to speak
again yet?) → expiry (the shown insight cleans itself up). Spam requires *all
four* to fail.

> ### Secret formula — "Earn the 2 seconds"
> The HUD's quality metric is its **silence-to-signal ratio**, not its
> throughput. Engineer every layer to default closed: gate defaults to `False`,
> host confidence floor defaults high, cooldown spends on silent runs, expiry
> defaults short. Then a visible insight is a rare, *earned* event — and the
> user learns to trust the glow because it almost never lies. A HUD that speaks
> 5% of turns and is right is infinitely more valuable than one that speaks
> every turn and is usually ignorable. **Restraint is the product.**

---

## 4. `action_label` — the one interactive button

`action_label` is an optional string that turns a passive insight into an
interactive one: it is the button text the HUD renders. Keep it to one verb
phrase that reads in a glance — this is a HUD, not a form.

```python
self.create_insight(
    content="They raised price. Anchor on ROI before discounting.",
    type=InsightType.WARNING,
    confidence=0.82,
    expiry=8,
    action_label="Show ROI stat",   # ← single tappable affordance
)
```

Real wiring notes:

- `create_insight` (`core/agent.py`) takes `action_label` as an optional
  pass-through; omit it (`None`) and the model default (`None`) stands, so the
  HUD renders a plain insight with no button.
- For `DynamicAgent`, the LLM can supply it: the parser reads
  `mapping["action_label_field"]` (default key `action_label`) and runs it
  through `_coerce_action_label` (S-1), which strips it to a non-empty string or
  `None`. **Caveat (real, underused):** none of the *stock* schemas
  (`default`, `default_v2`, `ui_control`, …) wire `action_label_field` or
  instruct the model to produce it. To get LLM-authored buttons you must add the
  field to your schema's `instruction` and `mapping`. Until then, set
  `action_label` in code (programmatic agents) where you control the affordance
  precisely.
- **One button, not a toolbar.** The field is singular by design. If you find
  yourself wanting three buttons, you want three (separately gated, separately
  ranked) insights — and the HUD will still show one.

---

## 5. `metadata` — UI rendering hints (zone / color / voice)

`metadata` is the open extension point: `Dict[str, Any]`, defaulting to `{}`,
explicitly documented as *"Generic extension point for UI-specific rendering
options (zone, color, voice style, etc.)."* The framework never interprets it —
it rides untouched from the agent, through the trace, to your HUD. That makes it
the right place for everything the typed fields don't cover.

A practical metadata convention for a HUD:

```python
self.create_insight(
    content="Budget confirmed: $50k, Q3 close.",
    type=InsightType.FACT,
    confidence=0.9,
    expiry=45,
).metadata = {
    "zone": "ambient_rail",     # override default zone for this type
    "color": "#64748b",         # HUD-specific accent
    "icon": "dollar-sign",      # glanceable glyph
    "voice": "calm",            # TTS style if the copilot also speaks
    "pin": True,                # keep on the rail past expiry (host honors)
    "priority_hint": 0.3,       # host curation tiebreaker
}
```

For `DynamicAgent`, wire `mapping["metadata_field"]` (the stock `default` /
`default_v2` schemas already set `"metadata_field": "metadata"`) and the parser
copies `root_data["metadata"]` straight onto `insight.metadata`. The LLM can
then *self-describe its rendering* — e.g. emit `{"zone": "flash", "voice":
"urgent"}` alongside a warning.

Because metadata flows into the trace verbatim (`utils/tracing.py` logs
`"metadata": i.metadata` per insight), it doubles as a debugging signal: you can
see in the MRI exactly which zone/voice hint an agent asked for.

**Discipline:** metadata is a *hint*, never a *requirement*. The host must render
a correct HUD even if metadata is `{}` — derive zone/color from `type` as the
floor, and let metadata *override*. Never make a metadata key load-bearing for
safety; a missing hint should degrade to the typed default, not break the stage.

---

## 6. How the host consumes `AgentResponse.insights`

The framework's contract ends at `AgentResponse.insights: List[AgentInsight]`.
The engine aggregates each turn's responses; the **host owns curation and
render.** A reference consumption loop:

```python
async def on_turn(self, response: AgentResponse):
    # 1. Split system alerts out of the coaching channel
    coaching = [i for i in response.insights if i.type != InsightType.ERROR]
    alerts   = [i for i in response.insights if i.type == InsightType.ERROR]
    for a in alerts:
        self.system_tray.flash(a.content)   # never on the coaching stage

    # 2. Curate: confidence floor + urgency/confidence ranking (see §3.2)
    ranked = curate(coaching)
    if not ranked:
        return                              # the common, correct case: stay silent

    # 3. The stage shows ONE. Dedup by agent_id so one observer can't dominate.
    top = ranked[0]
    if self._recently_shown(top.agent_id):  # host-side per-source cooldown
        return
    self.hud.present(
        text=top.content,
        zone=top.metadata.get("zone", ZONE_BY_TYPE[top.type]),
        color=top.metadata.get("color", COLOR_BY_TYPE[top.type]),
        ttl_seconds=top.expiry,             # the insight dissolves itself
        button=top.action_label,            # None ⇒ no button
        on_click=self._dispatch_action,
    )
```

Note the host adds a fifth restraint layer on top of the four framework layers:
**limited-stage curation** (take top 1) and **per-source dedup** (`agent_id`).
The framework gives you the raw material and the gates; the *glanceability
budget* is a host policy and must be enforced here. Never `for i in
response.insights: hud.show(i)` — that is the canonical spam bug (see §8).

---

## 7. Designing for glanceability

The `content` field has `min_length=2` and no max — the model *can* return a
paragraph. The HUD's job is to ensure it never does, or to truncate ruthlessly.

- **One line, one idea, ~8 words.** "Ask about their timeline" beats "It might
  be a good idea to consider asking the prospect about what their timeline looks
  like for this decision." Put the verb first.
- **Type does the labeling.** Don't write "WARNING: …" in `content`; the zone
  and color already say it. Spend the words on the *content*.
- **Action in the button, context in the line.** `content` = what's happening;
  `action_label` = what to do about it.
- **Facts are nouns, suggestions are verbs.** A `FACT` reads "Budget: $50k"; a
  `SUGGESTION` reads "Confirm the budget." The grammar reinforces the zone.
- **Render-time truncation is a safety net, not a license.** Enforce a hard
  character cap at the HUD and fix the *prompt* if agents routinely overflow.

The MRI debugger (`tools/debugger.html`) is your glanceability lab: it renders
each insight exactly as `type` (border/color), `content`, and `confidence`
("Conf: 0.82"), plus a metadata block. If an insight looks like a wall of text
in the MRI, it will look worse on a 2-second overlay.

---

## 8. Anti-patterns

Each of these is a real failure mode the v2.2 surface is explicitly built to
prevent — these are the ways teams defeat their own framework.

- **HUD spam — rendering every insight.** `for i in response.insights:
  hud.show(i)`. No curation, no top-1, no per-source dedup. The framework hands
  you a *list* precisely so you can pick; showing all of them buries the one
  that mattered. **Fix:** curate to one (§6).
- **Gate-less agents that always speak.** A custom schema with no `check_field`
  and no `root_key`, relying on "there's content ⇒ show it." v2.2 defaults this
  to *silence* (INV-11 case (c)) and warns at load time — do not "fix" the
  warning by flipping `speak_without_gate: true` to make the noise come back.
  **Fix:** wire an explicit `check_field` gate.
- **Low-confidence noise.** Treating `confidence` as decoration and rendering
  everything. The A-3 clamp keeps bad values from crashing, but it can't filter
  for you. **Fix:** host-side confidence floors per type (§3.2).
- **No cooldown / one observer dominates.** A chatty agent with `cooldown=0`
  monopolizing the stage. **Fix:** respect/raise `cooldown`, and dedup by
  `agent_id` at the host.
- **Ignoring `expiry`.** Pinning insights indefinitely (or until manually
  cleared) so the HUD accretes stale advice. Silence is the default state; an
  insight that won't leave violates it. **Fix:** always pass `expiry` to
  `hud.present(ttl=...)`; let `FACT` live long and `WARNING` die fast.
- **Wrong insight type.** Painting routine nudges as `WARNING` (red-zone fatigue)
  or burying a live buying signal in a grey `FACT`. The urgency gradient is the
  UX; mis-typing destroys it. **Fix:** match the type to the zone semantics in
  §2.
- **`ERROR` on the coaching stage.** Routing the framework's failure channel
  (auto-emitted by `process` on exceptions) to the user's overlay, turning an
  LLM timeout into a scary red alert. **Fix:** split `ERROR` to a system tray
  (§6 step 1).
- **Walls of text.** Treating `content` like a chat reply. `min_length=2` is the
  only constraint the model sees — glanceability is *your* constraint. **Fix:**
  one line, verb-first, truncate at the HUD (§7).
- **Load-bearing metadata.** Making the HUD crash or mis-render when `metadata`
  is `{}`. Metadata is an optional *hint*. **Fix:** derive zone/color from `type`
  as the floor; let metadata override (§5).

---

## 9. Underused capabilities (steal these)

- **`metadata` as a per-insight voice/zone director.** Almost no one ships the
  `voice` / `zone` hint pattern, yet it's free: the field is unopinionated and
  flows through the trace untouched. Let urgent warnings request `"voice":
  "urgent"` and ambient facts request `"zone": "rail"`.
- **LLM-authored `action_label` and `expiry`.** The parser already reads
  `expiry_field` and `action_label_field` (S-1) and coerces them safely — but no
  stock schema wires them. Add them to a custom schema's `instruction`+`mapping`
  and your agents can self-author the button text and the moment's lifetime.
- **`FACT` as a persistent ambient rail.** Most teams only think in
  suggestions/warnings. Use long-`expiry` `FACT` insights as a quiet, always-on
  "what we know" rail (budget, stakeholder, timeline) separate from the
  interrupt zone — durable understanding made glanceable.
- **The MRI as a UX rehearsal tool.** `tools/debugger.html` renders insights with
  the production color/zone mapping. Paste a `TURN_TRACE` log and *see your HUD*
  before you build it — including the per-insight `confidence` and `metadata` you
  intend to curate on.

---

### Summary

The HUD is a 2-second stage. The framework gives you a typed insight whose every
field is a curation lever — `type` for zone/urgency, `confidence` to rank and
filter, `expiry` for self-cleaning ephemerality, `action_label` for the single
button, `metadata` for render hints — and four composable restraint layers
(gate → confidence → cooldown → expiry) that default to silence. The host adds
the fifth (curate to one, dedup by `agent_id`). Build it so a visible insight is
rare and earned, and the glow becomes trustworthy. Restraint is the product.
# Chapter 9 — Roles, Configuration & Adaptability

> *Making the swarm adapt per-user, per-role, and per-context — without writing a single new line of agent code.*

The thesis of this playbook is a **reactive, blackboard-coordinated swarm of cheap, configurable agents**. This chapter is where the word *configurable* earns its keep. A real-time copilot serves many users, many roles, many moments: a junior rep wants more hand-holding, a senior closer wants the HUD to shut up unless something is urgent, a "demo mode" wants the swarm chatty for the audience. The naive answer is to fork agents or branch code per persona. The v2.2 answer is to keep **one studio of configurable agents** and bend them at runtime with data.

There are exactly two data-driven levers, and they live at two different scales:

1. **`AgentConfigOverride`** — per-turn, per-session role modifiers that nudge an *existing* agent's timing, context window, and instructions. The dial.
2. **`DynamicAgent` + JSON schema** — config-driven *instantiation* that builds a whole agent (persona, triggers, output shape) from a dict and a schema file. The factory.

Master these and you stop shipping code to change behavior. You ship config.

---

## Mental model: the dial and the factory

Picture two layers between "what the product wants" and "what the LLM sees":

```
                 product intent  ("this user is a novice; ramp up coaching")
                        │
        ┌───────────────┴────────────────┐
        ▼                                 ▼
   AgentConfigOverride               DynamicAgent + schema
   (the DIAL — per session/turn)     (the FACTORY — per deployment)
   • cooldown_modifier               • persona text  (config_dict["text"])
   • context_turns_modifier          • triggers      (trigger_config)
   • instructions_append             • output shape  (output_format → schema)
        │                                 │
        └───────────────┬────────────────┘
                        ▼
              one running agent instance
                        ▼
                  the LLM prompt
```

The **dial** (`AgentConfigOverride`) does *not* create or destroy agents. It modulates ones that already exist, and it does so on the `AgentContext` that flows through every turn — so it is inherently per-session and can change turn to turn. The **factory** (`DynamicAgent`) is how the agent existed in the first place: it reads a dict (from your DB or a JSON file) and a schema, and constructs the agent with zero bespoke Python.

A useful rule of thumb: **the factory decides what an agent *is*; the dial decides how *loud* and *informed* it is right now.**

---

## Part 1 — The Roles/overrides system (the dial)

### The shape of an override

`AgentConfigOverride` (`core/models.py`) is deliberately tiny and deliberately strict:

```python
class AgentConfigOverride(BaseModel):
    """Per-agent config overrides from Role modifiers.

    Typed to prevent silent typos — unknown keys rejected (extra='forbid').
    Polarity: cooldown_modifier +N = slower, -N = faster (floor 5s).
    context_turns_modifier +N = more context, -N = less (<=0 = all).
    """
    model_config = ConfigDict(extra="forbid")

    cooldown_modifier: Optional[int] = None
    context_turns_modifier: Optional[int] = None
    instructions_append: Optional[str] = None
```

Three knobs. That's the entire surface. Everything below is about how they flow and how they're applied.

### How overrides reach an agent: the context, keyed by agent ID

Overrides ride on the context, not on the engine and not on the agent:

```python
class AgentContext(BaseModel):
    ...
    agent_config_overrides: Dict[str, AgentConfigOverride] = Field(
        default_factory=dict, description="Per-agent config overrides from Role modifiers"
    )
```

The dictionary is keyed by **`agent.config.id`** — the *engine* agent ID, **not** a role ID. This is the single most important fact in the chapter and the one most likely to be gotten wrong. If your agent registered as `id="objection_handler"`, the override key must be the literal string `"objection_handler"`. A mismatched key is not an error; it is a silent no-op. (See the anti-pattern on contamination below.)

A "Role" in your product is therefore just a **named bundle of these overrides** that your host assembles and drops onto the context each turn:

```python
# Host side: build a Role as a dict of overrides, keyed by engine agent id.
NOVICE_ROLE = {
    "objection_handler": AgentConfigOverride(
        cooldown_modifier=-5,                       # react faster to objections
        context_turns_modifier=+4,                  # give it more of the conversation
        instructions_append="The user is new. Explain *why* in one short clause.",
    ),
    "small_talk_coach": AgentConfigOverride(
        cooldown_modifier=+20,                       # rarely; novices get overwhelmed
    ),
}

context = AgentContext(
    session_id=sid,
    recent_segments=window,
    agent_config_overrides=NOVICE_ROLE,             # the Role, applied this turn
)
response = await engine.process_turn(context)
```

### How the engine propagates overrides (and why it never cross-contaminates)

When the engine runs a phase, it builds a fresh `phase_context` for the snapshot but **passes the same overrides dict straight through** (`core/engine.py`, `_run_phase`):

```python
phase_context = AgentContext(
    session_id=context.session_id,
    recent_segments=context.recent_segments,
    ...
    agent_config_overrides=context.agent_config_overrides,   # carried verbatim
)
```

Two consequences worth internalizing:

- **Both phases see the same overrides.** Phase 1 (turn-based) and Phase 2 (event-triggered) agents read the identical dict. A Role applies to the whole turn, not just the first wave.
- **No cross-agent contamination by construction.** Each agent looks itself up by *its own* `self.config.id` (`context.agent_config_overrides.get(self.config.id)`). Agent A literally cannot read agent B's override entry. There is no shared mutable "current override" — the lookup is per-agent, every time, in both `BaseAgent.process` and `DynamicAgent.evaluate`. You get isolation for free as long as you key the dict correctly.

### Knob 1 — `cooldown_modifier` and the 5-second floor

Cooldown is enforced by the *agent*, not the engine (`core/agent.py`, `BaseAgent.process`):

```python
effective_cooldown = self.config.cooldown
overrides = context.agent_config_overrides.get(self.config.id)
if overrides and overrides.cooldown_modifier is not None:
    effective_cooldown = max(5, effective_cooldown + overrides.cooldown_modifier)
if (now - self.last_run_time) < effective_cooldown:
    return None
```

Polarity, made concrete:

- `cooldown_modifier=+20` on a base-15s agent → 35s between runs. **Slower, calmer HUD.**
- `cooldown_modifier=-8` on a base-15s agent → 7s. **Snappier reactions.**
- `cooldown_modifier=-50` on a base-15s agent → `max(5, -35)` → **5s.** The floor catches you.

The **5-second floor is non-negotiable and engine-enforced.** No Role, however aggressive, can make an agent fire faster than every 5 seconds. This is a deliberate guardrail against a "turbo" Role that would turn the copilot into a strobe light and torch your token budget. Design your Roles knowing the floor exists — don't author `cooldown_modifier=-999` as a lazy "always on," because it silently clamps and you'll mis-reason about timing.

Note also the FORCE path: a user-triggered force-talk bypasses cooldown entirely, so overrides on cooldown are irrelevant during FORCE. Overrides shape the *ambient* cadence, not the explicit "talk now" button.

### Knob 2 — `context_turns_modifier` (more or less memory of the room)

Applied in `DynamicAgent.evaluate` when formatting the transcript window:

```python
effective_turns = self.context_turns
overrides = context.agent_config_overrides.get(self.config.id)
if overrides and overrides.context_turns_modifier is not None:
    effective_turns = effective_turns + overrides.context_turns_modifier

if effective_turns <= 0:
    target_segments = context.recent_segments            # ALL available
else:
    slice_start = -effective_turns if len(...) >= effective_turns else 0
    target_segments = context.recent_segments[slice_start:]
```

Polarity and the special case:

- `+N` → a **wider** window (more turns of transcript in the prompt). Good for agents that need narrative arc — a summarizer, a "where is this conversation going" coach.
- `-N` → a **narrower** window. Good for a fast keyword reactor that only cares about the last utterance; less context means cheaper, sharper, faster.
- **`<= 0` → the entire available window.** Crossing zero doesn't mean "no context," it means "all of it." If a base agent has `context_turns=6` and you apply `context_turns_modifier=-6`, you get *everything in the window*, not silence. This is a polarity trap: be careful not to drive an agent past zero expecting starvation when you'll actually flood it.

### Knob 3 — `instructions_append` (steer the persona without rewriting it)

Appended to the *end* of the assembled system prompt, after the base persona and schema instruction (`DynamicAgent.evaluate`):

```python
if overrides and overrides.instructions_append and overrides.instructions_append.strip():
    full_system_prompt += f"\n\n# Role Overrides\n{overrides.instructions_append.strip()}"
```

This is your per-context tone/policy injection: *"the user is a CFO — lead with numbers,"* *"demo mode: be enthusiastic,"* *"compliance-sensitive account: never speculate on pricing."* Because it lands under an explicit `# Role Overrides` heading at the bottom, later instructions generally win — that's the point. But it is *additive*, not a replacement: the base persona is still there above it. The skill is writing appends that **refine** the base ("...and keep replies under 12 words") rather than **contradict** it ("ignore everything above"), which just confuses the model (see anti-patterns).

### Typed-override safety: `extra="forbid"` earns its keep

Because `AgentConfigOverride` sets `model_config = ConfigDict(extra="forbid")`, a typo is a loud failure at construction, not a silent shrug at runtime:

```python
AgentConfigOverride(cooldown_modifer=-5)   # typo: 'modifer'
# pydantic.ValidationError: Extra inputs are not permitted
```

Contrast the failure modes. A bare `dict` payload would happily carry `cooldown_modifer`, the agent would read `cooldown_modifier` (which is `None`), and your "faster" Role would do *nothing* — in production, on a real call, with no error anywhere. The typed model converts a silent behavioral bug into an immediate, local exception. **Always construct overrides through the model, never hand-roll the dict**, precisely so a misspelled knob can't quietly evaporate.

> ### 🔑 Secret formula — Roles are diffs, not forks
> A Role is a **diff against the studio's defaults**, expressed as a `Dict[str, AgentConfigOverride]` keyed by engine agent ID, dropped onto the context each turn. The base agents never change; the *same* swarm becomes a novice-coach, a senior-closer, or a demo-bot depending on which diff you attach this turn. You can recompute the diff *every turn* from live blackboard state ("phase == negotiation → loosen the objection handler") — adaptation is a function of context, evaluated continuously, costing zero deploys.

---

## Part 2 — Building a "studio" of configurable agents (the factory)

### Config + schema = a new agent, no code

`DynamicAgent` (`library/dynamic.py`) is the workhorse. Its constructor takes **one dict** and reads everything from it — persona, triggers, model, and output shape:

```python
agent = DynamicAgent({
    "id": "objection_handler",                 # MUST match your override keys
    "name": "Objection Handler",
    "text": "You spot objections and coach a crisp rebuttal. {{ blackboard.variables.deal_stage }}",
    "trigger_config": {
        "mode": "keyword",
        "keywords": "too expensive, not sure, competitor",
        "cooldown": 15,
        "priority": 5,
    },
    "model_config": {
        "model": "gpt-4o-mini",
        "context_turns": 6,
    },
    "output_format": "default_v2",             # selects library/schemas/default_v2.json
})
```

A few load-time behaviors worth knowing from `DynamicAgent.__init__`:

- **Triggers from data.** `trigger_config.mode` maps strings (`"keyword"`, `"silence"`, `"interval"`, `"event"`, or a *list* of them) onto `TriggerType`s. Subscribing to events (`subscribed_events`) auto-adds `TriggerType.EVENT` so you can't forget the wiring.
- **`model_config` is the model/context bag.** `model_config.model` picks the LLM (default `gpt-4o-mini` — cheap, by design); `model_config.context_turns` sets the base window the `context_turns_modifier` later bends. Both fall back to top-level keys for convenience.
- **Jinja2 persona.** `text` is rendered with `{{ blackboard }}`, `{{ state }}`, `{{ memory }}`, `{{ user_context }}` in a **sandboxed** environment, and fails *gracefully* to the raw string if a template errors — a live copilot never dies on a bad brace.

The point: a product manager can stand up a new agent by inserting a **row in a table**. No deploy, no subclass.

### Schema selection: the output contract is also data

`output_format` names a file in `library/schemas/`. The schema's `mapping` tells the generic parser how to read the model's JSON — what gates speech, where the content lives, where facts/events/state hide. The studio ships several:

| Schema | Gate mechanism | Use it for |
|---|---|---|
| `default` | `check_field: has_insight` | Simple flat agents; legacy `message` field. |
| `default_v2` | `check_field: has_insight` | Full v2 swarm: insights **+** events, facts, variable & memory updates. The default workhorse. |
| `v2_raw` | `root_key: insight` (presence-gated) | Structured insight + `state_snapshot`; model speaks by *emitting* the object. |
| `custom1` | `check_field: sales_tip` | Worked example of remapping arbitrary field names (`sales_tip`, `risk_category`). |
| `ui_control` / `widget_control` | `root_key: insight` + `data_field: ui_actions` | Agents that drive HUD widgets (the "Hands") alongside or instead of voice. |

Two structural gate styles, both real and both load-bearing for restraint:

- **Boolean gate** (`check_field`): the model must explicitly raise `has_insight: true`. Silence is the default; speech is opt-in.
- **Presence gate** (`root_key`, no `check_field`): emitting a non-empty root object *is* the decision to speak; an absent/empty object means silence.

And the trap the framework warns you about: a **gate-less + rootless** custom schema (no `check_field`, no `root_key`) has *no structural gate*. The documented default is to **stay silent** unless the mapping sets `"speak_without_gate": true`. `DynamicAgent` even emits a one-time load-time warning (`_warn_on_gateless_misconfig`) when your instruction *mentions* a gate field like `has_insight` but the mapping forgot to wire `check_field` — the exact misconfiguration that silently turns a polite agent into a HUD spammer. **If you author a schema, wire a gate.** Restraint is a feature; a missing gate quietly removes it.

> ### 🔑 Secret formula — One studio, many products
> Keep agents as **rows** (a dict per agent) and output contracts as **schema files**. A "sales copilot," a "support copilot," and a "tutoring copilot" are then three *catalogs of config over the same `DynamicAgent` engine* — not three codebases. New agent = new row. New output shape = new schema file. New persona for a customer = an `instructions_append` Role. The Python stops changing; the product keeps moving.

---

## Part 3 — The decision: override vs. new agent vs. new schema

When behavior needs to change, pick the **smallest** lever that fits. Reach for the next one only when the current one genuinely can't express the change.

**Use an `AgentConfigOverride` (a Role) when** the *same* agent should behave differently for this user/context, and the difference is timing, context width, or a tone/policy nudge. Per-novice slowdown, "be terse for executives," "react faster during the demo." This is per-session and can change every turn. **Cheapest. Default to this.**

**Author a new `DynamicAgent` config (a new row) when** you need a genuinely *different job* — a new persona, different trigger conditions, a different model, a distinct event subscription. A "pricing watcher" is not a slowed-down "objection handler"; it's a different agent. Still **no code** — just config.

**Author a new schema (a new JSON file) when** the *output contract* itself must change — a new gate field, a new sidecar (e.g. driving a new HUD widget via `data_field`), a different field-name mapping. Schemas are about *shape of the LLM's reply*, not about persona or timing. Rare; the six shipped schemas cover most needs.

**Write actual Python (a new `BaseAgent` subclass) only when** the agent needs logic the prompt-and-parse loop can't express — calling an external API mid-evaluate, deterministic computation, bespoke control flow. If you're tempted here, first prove an `instructions_append` + existing schema can't do it.

The ladder, smallest to largest: **override → config row → schema file → code.** Most "we need the agent to do X for customer Y" requests die on the first rung.

---

## Part 4 — Per-session reconfiguration (the engine re-applies every turn)

There is no "set the Role once" call. The engine reads `context.agent_config_overrides` **off the context on every `process_turn`**, and the agents re-resolve their own entry every evaluation. That means the right pattern for an adaptive copilot is:

```python
def role_for(turn_state) -> Dict[str, AgentConfigOverride]:
    """Recompute the Role from live state — runs every turn."""
    role = dict(BASE_ROLE)
    if turn_state.user_expertise == "novice":
        role["objection_handler"] = AgentConfigOverride(
            cooldown_modifier=-5, context_turns_modifier=+4,
            instructions_append="User is new; explain the why briefly.",
        )
    if turn_state.blackboard_phase == "closing":
        role["closer"] = AgentConfigOverride(cooldown_modifier=-5)
    return role

# each turn:
context.agent_config_overrides = role_for(current_state)
await engine.process_turn(context)
```

Because the dict is re-read every turn, **adaptation is continuous and free of ceremony.** A user who starts as a novice and visibly gains confidence can be smoothly de-escalated turn by turn — loosen cooldowns, trim the `instructions_append` hand-holding — with no engine restart and no agent re-instantiation. The Role is a pure function of the moment.

One caution: this is also why the **engine ID key** matters so much. Recomputing a Role each turn multiplies the blast radius of a mis-keyed entry — a typo in `"objection_handler"` is a no-op *every single turn*, invisibly. Construct keys from `agent.config.id` you actually registered, not from hand-typed strings.

---

## Anti-patterns

**Hardcoding what should be configurable.** A literal `if user.is_novice: cooldown = 8` buried in agent logic is a Role pretending to be code. Anything that varies by user/role/context belongs in an `AgentConfigOverride` recomputed per turn, not in a branch you have to redeploy to change. If you find yourself adding persona `if`s to a `BaseAgent`, you wanted a config row.

**Forking an agent instead of overriding it.** Copy-pasting `objection_handler` into `objection_handler_novice` to slow it down doubles your maintenance surface and drifts immediately. A novice objection handler is the *same agent with a diff*: one config row, one override entry. Forks are for genuinely different jobs, never for "same job, different dial."

**`instructions_append` that fights the base prompt.** The append lands *after* the persona, not instead of it. Writing `"Ignore all previous instructions and..."` produces a confused model and unpredictable output, because the base persona is still right there above your text. Appends must *refine* ("...and keep it under 12 words," "...lead with the number"), never *contradict*. If you truly need a different persona, that's a new config row, not an append.

**Ignoring the cooldown floor.** Authoring `cooldown_modifier=-999` as shorthand for "always on" silently clamps to a 5s effective floor (`max(5, ...)`). You'll then mis-reason about cadence and token spend because the number you wrote isn't the number that runs. Respect the floor explicitly; if you want roughly-as-fast-as-possible, write a modifier that lands *at* 5s and *know* that's where it lands. (And remember FORCE bypasses cooldown entirely — that's the real "talk now" path.)

**Cross-agent override contamination — i.e., the wrong key.** The framework gives you isolation for free (each agent reads only `overrides.get(self.config.id)`), so the only way to "contaminate" is to **key the dict wrong**: putting agent B's tuning under agent A's ID, or keying by a *role* name instead of the *engine* agent ID. The override then either silently misfires onto the wrong agent or no-ops entirely. There is no runtime error. Audit your Role keys against the registered `agent.config.id`s — make that a test.

**Gate-less custom schemas.** Authoring a new schema with neither `check_field` nor `root_key` (and not deliberately setting `speak_without_gate`) removes the silence contract. The shipped warning will tell you; don't ignore it. Every schema you write should declare *how the agent stays quiet*, because in a real-time HUD, quiet is the default the user is paying for.

---

## Takeaways

- Two levers, two scales: the **dial** (`AgentConfigOverride`: cooldown / context-turns / instructions, per session, re-read every turn) and the **factory** (`DynamicAgent` + JSON schema, per deployment, config-only agent creation).
- Overrides are a `Dict[str, AgentConfigOverride]` keyed by **engine `agent.config.id`**, carried verbatim into both phases; agents read only their own entry, so isolation is automatic and the only real footgun is a wrong key.
- Mind the **polarities and floors**: `+cooldown` = slower (floor **5s**); `+context_turns` = wider, and `<= 0` = **all** turns, not none.
- `extra="forbid"` turns a misspelled knob into an immediate exception — always build overrides through the model, never a raw dict.
- Climb the ladder **override → config row → schema file → code**, and stop at the lowest rung that works; most behavior changes never reach code.
- Every schema must declare a gate (`check_field` or `root_key`); a gate-less schema silently sacrifices restraint, which in a real-time copilot is the whole product.
# Chapter 10 — Production: Cost, Latency, Resilience, Observability & Scale

> *The framework is a swarm of cheap observers coordinating on a blackboard. In production, "cheap" is not a vibe — it is an engineering discipline enforced at four gates before a single token is spent, and a never-raise contract that guarantees one flaky agent never takes down the turn. This chapter is about running that swarm under real-time pressure, in production, at scale.*

---

## 10.0 Mental model: the turn is a budget, and you spend it reluctantly

A `process_turn` call is the unit of production cost and latency. Everything in `xubb_agents` is built so that **most agents, most turns, spend nothing.** The engine is a funnel that filters agents *out* before they ever touch the LLM:

```
process_turn(trigger_type)
   │
   ├─ allow-list filter        (host hard filter — free)
   ├─ trigger_type match       (engine routing — free)
   ├─ trigger_conditions       (blackboard predicate — free, no LLM)
   ├─ cooldown                 (agent.process timing gate — free)
   └─ evaluate() ──► LLM call  (the ONLY thing that costs money)
        ▲
        └─ model tier + max_tokens cap the spend when you *do* pay
```

The mental model: **a turn is a budget you spend reluctantly.** The funnel above is the cost stack — conditions gate first (cheapest, no I/O), then cooldowns, then model tiering decides *how much* a surviving call costs, then `max_tokens` caps the worst case. A production deployment that ignores any layer of this funnel is leaking money or latency, usually both.

The runtime is wall-clock-bounded by design. `core/llm.py` ships defaults *tuned for a real-time conversational copilot* (the docstring calls this INV-10):

```python
# core/llm.py
DEFAULT_TIMEOUT = 10.0      # seconds, per request
DEFAULT_MAX_RETRIES = 2     # bounded retries on transient failures
DEFAULT_MAX_TOKENS = 1024   # output cap for the JSON object
```

And the default model is the cheap one — `gpt-4o-mini`, set in `AgentConfig.__init__`. The framework's defaults are already the frugal choice. Most production mistakes are *overriding* these defaults in the expensive direction.

---

## 10.1 LLM economics: the cost stack, gate by gate

### Gate 1 — `trigger_conditions` (free, evaluated before anything)

The cheapest call is the one you never make. `trigger_conditions` is a blackboard predicate the engine evaluates in `_is_eligible` **with no LLM and no I/O** — pure in-memory state inspection:

```python
# core/engine.py — _is_eligible
conditions = getattr(agent.config, 'trigger_conditions', None)
if conditions:
    if not self.condition_evaluator.evaluate(
        conditions, context.blackboard, meta, agent.config.id
    ):
        return (False, "conditions_not_met")
```

An agent that only matters once a budget has been mentioned should not run before then. Gate it on a blackboard fact, not on the LLM's judgment:

```python
AgentConfig(
    name="Budget Negotiator",
    model="gpt-4o",                       # premium — but rarely runs
    trigger_types=[TriggerType.TURN_BASED],
    trigger_conditions={"var:budget_mentioned": True},  # free precondition
)
```

This is the single highest-leverage cost lever in the framework. A premium agent behind a tight condition can cost less per session than a cheap agent that runs every turn. **Spend your condition budget before your token budget.**

### Gate 2 — `cooldown` (free, enforced in the agent)

Cooldown is enforced by `BaseAgent.process()`, not the engine — the responsibility split is explicit in the code ("Engine: Decides trigger eligibility … Agent: Enforces cooldown"):

```python
# core/agent.py — process()
if not is_force:
    effective_cooldown = self.config.cooldown
    overrides = context.agent_config_overrides.get(self.config.id)
    if overrides and overrides.cooldown_modifier is not None:
        effective_cooldown = max(5, effective_cooldown + overrides.cooldown_modifier)
    if (now - self.last_run_time) < effective_cooldown:
        return None        # ← no evaluate(), no LLM, no cost
```

Default cooldown is `10` seconds. In a fast back-and-forth conversation that alone can halve an agent's call count. Tune it per agent: a high-value-but-slow analyzer gets a long cooldown (30–60s); a fast keyword scout gets a short one. Roles can nudge cooldown at runtime via `cooldown_modifier` (floor 5s) without rebuilding the agent.

> **`FORCE` bypasses both gates.** `TriggerType.FORCE` skips trigger-type match, conditions, *and* cooldown (`is_force` in `process`, and the early return in `_is_eligible`). It is the "user pressed the talk button — run everything now" escape hatch. Use it deliberately; it is the one path that ignores your cost discipline by design.

### Gate 3 — model tiering: cheap detectors, premium analyzers

Each agent carries its own `model` (`AgentConfig.model`, default `gpt-4o-mini`), and `DynamicAgent` passes exactly that into the call:

```python
# library/dynamic.py — evaluate()
result = await self.llm.generate_json(model=self.model, messages=messages)
```

This is the **detector → analyzer** tiering pattern, and it is the framework's most underused cost capability. Run a swarm of cheap `gpt-4o-mini` *detectors* on every turn; let each emit a blackboard fact or event when it sees something worth a closer look. Gate one premium `gpt-4o` *analyzer* on that signal so it fires only when a detector has already paid the cheap cost of noticing:

```python
# Cheap detector — runs every turn, emits an event when it sees an objection
AgentConfig(name="Objection Scout", model="gpt-4o-mini",
            trigger_types=[TriggerType.TURN_BASED], cooldown=8)

# Premium analyzer — Phase 2, fires ONLY on the detector's event
AgentConfig(name="Objection Strategist", model="gpt-4o",
            trigger_types=[TriggerType.EVENT],
            subscribed_events=["objection_raised"])
```

The detector is cheap and always-on; the expensive model only spends tokens on turns where a cheap model already found a reason. You get premium reasoning at detector prices.

### Gate 4 — `max_tokens`: cap the worst case

Every call is output-capped. The cap is the per-call override or the client default (1024):

```python
# core/llm.py — generate_json
effective_max_tokens = max_tokens if max_tokens is not None else self.max_tokens
```

Because responses are forced JSON (`response_format={"type": "json_object"}`), a tight `max_tokens` both bounds cost *and* protects the latency budget — a runaway generation can't blow either. For a HUD insight that's one sentence and a confidence score, 1024 is generous; many agents are happy at 256. **Cap to the shape of the output you actually render.**

---

## 10.2 Latency: engineering for the real-time budget

In a live conversation the HUD must update within the rhythm of speech. Two structural facts make that achievable.

**Agents within a phase run in parallel.** `_run_phase` fans every eligible agent out concurrently and gathers them — turn latency is the *slowest* agent, not the *sum*:

```python
# core/engine.py — _run_phase
tasks = []
for agent in agents:
    tasks.append(self._run_agent_safe(agent, phase_context))
results = await asyncio.gather(*tasks)
return [r for r in results if r is not None]
```

So ten agents at ~600ms each cost ~600ms of wall clock, not six seconds. Your real-time budget is `slowest Phase 1 agent + (slowest Phase 2 agent, if events fired)`.

**Every request is independently time-bounded.** The 10s client timeout is the ceiling, but you should pass a tighter per-request budget for HUD agents — `generate_json` accepts a `timeout` override that the SDK honors per call:

```python
# tight budget for an always-on HUD detector
result = await self.llm.generate_json(
    model=self.model, messages=messages,
    max_tokens=256, timeout=3.0,
)
```

A slow agent that blows its per-request timeout returns `None` (a categorized `timeout` failure) instead of stalling the whole `gather`. The turn proceeds with whatever the other agents produced.

**The 2-phase cap is a latency guarantee, not just a feature.** The engine implements *at most* Phase 1 + an optional event-triggered Phase 2 — `max_phases` is clamped to `{1, 2}`:

```python
# core/engine.py — __init__
if max_phases not in (1, 2):
    clamped = 1 if max_phases < 1 else 2
    logger.warning(f"max_phases={max_phases} is unsupported … using {clamped}.")
    max_phases = clamped
```

Phase 2 only runs if Phase 1 emitted events *and* `max_phases >= 2`. There is no Phase 3 — events emitted in Phase 2 are recorded for telemetry but **not dispatched**, so the swarm cannot cascade into an unbounded chain of LLM calls inside one turn. Worst-case latency is bounded at two serial LLM rounds. If you want strictly single-round latency (no event fan-out at all), construct the engine with `max_phases=1` and your turn is exactly one parallel round.

---

## 10.3 Resilience: one agent's failure never breaks the turn

Production resilience in `xubb_agents` rests on three layers that compose into a single guarantee: **a turn always completes and always returns an `AgentResponse`.**

### Layer 1 — the LLM never raises into the turn (R-1)

`generate_json` is contractually total: it returns the parsed dict on success or `None` on *any* failure, and it classifies the failure into a typed category recorded on `last_error_category`:

```python
# core/llm.py — categories: timeout | rate_limit | auth | server | malformed | not_initialized | unknown
except APITimeoutError as e:
    self.last_error_category = "timeout";   logger.error(f"… [category=timeout]: {e}");   return None
except RateLimitError as e:
    self.last_error_category = "rate_limit"; logger.error(f"… [category=rate_limit]: {e}"); return None
except AuthenticationError as e:
    self.last_error_category = "auth";      logger.error(f"… [category=auth]: {e}");      return None
```

These categories are operationally distinct and you must treat them so. `auth` means **stop** — your key is bad; retrying burns latency on a guaranteed failure and `rate_limit` retries make it worse. `rate_limit` / `server` / `timeout` are transient — the SDK already retried with exponential backoff (`max_retries=2`) before the exception surfaced. `malformed` means the model returned non-JSON or filtered content — a prompt/schema problem, not an infra problem. **Monitoring `last_error_category` is how you tell "OpenAI is down" from "my prompt is broken."** Ignoring it is flying blind during an incident.

### Layer 2 — graceful degradation in the agent

If `evaluate()` raises, `BaseAgent.process()` catches it and returns an `InsightType.ERROR` insight instead of propagating — the agent degrades to a visible-but-harmless error card:

```python
# core/agent.py — process()
except Exception as e:
    self.logger.error(f"Error in agent evaluation: {e}")
    # … fire on_agent_error callbacks …
    response = AgentResponse(
        source_agent_id=self.config.id,
        insights=[self.create_insight(
            content=f"Agent '{self.config.name}' encountered an error: {e}",
            type=InsightType.ERROR, confidence=1.0)])
    return response
```

### Layer 3 — atomic discard in the engine

As a final backstop, `_run_agent_safe` wraps each agent so that even an unexpected raise is caught and the response discarded (`None`), then filtered out of the merge:

```python
# core/engine.py — _run_agent_safe
try:
    return await agent.process(context, callbacks=self.callbacks)
except Exception as e:
    logger.error(f"Agent {agent.config.name} failed unexpectedly: {e}")
    return None        # ← atomic discard; the rest of the phase is unaffected
```

A failed agent contributes nothing to the merged blackboard state — its partial writes never land, because the merge only sees `gather` results that survived the filter. **One agent failing is a non-event for the other nine.**

### The cooldown-after-error discipline (B4)

Cooldown is updated in a `finally` block — *success or failure both arm the cooldown*:

```python
# core/agent.py — process()
finally:
    # B4: Always update cooldown, success or failure
    self.last_run_time = now
```

This is deliberate and load-bearing. A misconfigured or flapping agent that errors every call **cannot hot-loop** the LLM — it is rate-limited by its own cooldown exactly as a healthy agent is. Without this, an agent stuck in a `rate_limit` loop would hammer the API the instant each error returned. The error path respects the same timing gate as the happy path.

### Hot-swapping keys safely (E-4)

`update_api_key` rebuilds the `LLMClient`, re-injects it into every agent, and best-effort closes the old HTTP session to avoid leaking the connection pool. It carries a hard precondition you must honor:

```python
# core/engine.py — update_api_key docstring
# PRECONDITION (E-4): this method is NOT concurrency-safe and MUST NOT be
# called while a process_turn is in flight. … Callers must quiesce turns
# (or hold their own lock) before invoking it.
```

In production, gate key rotation behind the same lock that serializes turns for a session (see §10.5). Rotating a key mid-turn can hand an agent a half-torn-down client.

---

## 10.4 Observability: callbacks, the structured tracer, and the visual debugger

You cannot operate a swarm you cannot see. The framework gives you a clean observability seam: `AgentCallbackHandler` (`core/callbacks.py`) defines no-op lifecycle hooks the engine fires throughout a turn —

`on_turn_start` → `on_phase_start` → `on_agent_start` → `on_agent_finish` / `on_agent_error` / `on_agent_skipped` → `on_phase_end` → `on_turn_end`, plus `on_chain_error` if the whole turn blows up.

Every hook is wrapped so a *callback's* own failure never breaks the turn (`logger.error(f"Callback error …")` everywhere they're fired). Observability is safe to add aggressively.

### The batteries-included tracer

`utils/tracing.StructuredLogTracer` is a production-ready handler that accumulates per-turn state and emits one JSON line — the "Golden Log Line" — at `on_turn_end`:

```python
# utils/tracing.py — on_turn_end
log_line = f"TURN_TRACE: {json.dumps(self.current_trace, default=str)}"
logger.info(log_line)
```

It captures, per turn: trigger + metadata, the input/speaker preview, full transcript history, initial shared state, and a `steps[]` array with **per-agent latency** (`latency_ms`), status (`success` / `no_response` / `error`), insights, variable/event/fact/queue/memory deltas, and — when present — `debug_info` (raw prompts and LLM output). The `default=str` guard means a non-serializable value degrades to a string instead of crashing the trace. This single line per turn is your latency profiler, your cost auditor (which agents actually ran), and your post-incident record.

### Hooking it up

```python
from xubb_agents.core.engine import AgentEngine
from xubb_agents.utils.tracing import StructuredLogTracer
from xubb_agents.core.callbacks import AgentCallbackHandler

class CostMeter(AgentCallbackHandler):
    """A custom handler: count real LLM rounds and surface error categories."""
    def __init__(self, engine): self.engine = engine; self.calls = 0
    async def on_agent_finish(self, agent_name, response, duration):
        self.calls += 1
        cat = self.engine.llm_client.last_error_category   # watch R-1 categories
        if cat in ("auth",):
            logger.critical(f"LLM auth failure on {agent_name} — STOP, rotate key")

engine = AgentEngine(api_key=key, callbacks=[StructuredLogTracer()])
engine.callbacks.append(CostMeter(engine))   # callbacks compose; add as many as you like
```

> Note `last_error_category` lives on the **shared** `engine.llm_client` (one client per engine), so read it in `on_agent_finish` right after the call, or correlate via the tracer's per-step `status`. For per-agent attribution, prefer `status == "no_response"` in the trace step as your "this agent's call failed or was a no-op" signal.

### The visual debugger (`tools/debugger.html`)

`tools/debugger.html` is a zero-backend, single-file Vue app — the "Xubb Agent MRI." It ingests the `TURN_TRACE:` lines two ways: **paste** a block of logs, or connect **live over WebSocket** (default `ws://localhost:8000/ws/debug`). It renders a turn timeline with per-turn trigger badges and average latency, then a detail view per agent: status, latency, insights (color-coded by `InsightType`), state/variable/event/fact/queue/memory deltas, sidecar `data`, and collapsible raw prompt + raw response from `debug_info`. In practice: pipe the tracer's log line into the live WS during development, or paste production logs after an incident. It turns the Golden Log Line into a clickable MRI of why the swarm did what it did.

**What to log and monitor in production:**
- Per-turn: `total_latency_ms` (p50/p95/p99 vs your real-time budget), `final_insight_count`.
- Per-agent: `latency_ms` (find the slow agent capping your turn), `status` distribution (rising `no_response`/`error` = an agent degrading).
- LLM health: `last_error_category` distribution — alert hard on `auth`, page on a `rate_limit`/`server` spike, treat a `malformed` spike as a prompt regression.
- Cost proxy: count of `on_agent_finish` events per turn = real LLM rounds; if it creeps up, your gates are loosening.

---

## 10.5 The host loop: how a host like `xubb_server` drives the engine

The engine is a stateless-per-call orchestrator over *host-owned* state. The division of labor is strict:

| Responsibility | Owner |
|---|---|
| Audio/transcription, keyword & silence detection, interval timers | **Host** |
| Choosing the `TriggerType` and calling `process_turn` | **Host** |
| Building `AgentContext` (transcript window, blackboard, user context) | **Host** |
| Routing, conditions, cooldown, parallel execution, merge | **Engine** |
| Rendering insights to the HUD; persistence | **Host** |
| One engine + one blackboard, **per session** | **Host** |

The host is the real-time loop; the engine is what it calls. Crucially, **persistence is the host's job** — the blackboard is in-memory for the session lifetime (`engine.py` module docstring: *"Manages structured state (in-memory for session lifetime)"*). If you want cross-restart durability, the host snapshots the blackboard out and rehydrates it.

### A host loop sketch

```python
class SessionRuntime:
    """One per live conversation. Owns the engine, the blackboard, and a lock."""
    def __init__(self, session_id, api_key):
        self.session_id = session_id
        self.engine = build_engine(api_key)          # fresh engine per session
        self.blackboard = Blackboard()               # one blackboard per session
        self.segments: list[TranscriptSegment] = []  # the sliding transcript window
        self.turn_count = 0
        self._lock = asyncio.Lock()                  # serialize turns for this session

    def _context(self) -> AgentContext:
        return AgentContext(
            session_id=self.session_id,
            recent_segments=self.segments[-20:],     # host owns the window size
            blackboard=self.blackboard,              # SAME instance every turn
            turn_count=self.turn_count,
            user_context="Rep: Dana. Goal: renewal.",
        )

    async def _drive(self, trigger_type, metadata=None, allowed=None):
        # The no-concurrent-turn precondition (and E-4) are honored by this lock.
        async with self._lock:
            self.turn_count += 1
            resp = await self.engine.process_turn(
                self._context(),
                allowed_agent_ids=allowed,
                trigger_type=trigger_type,
                trigger_metadata=metadata or {},
            )
            self._render(resp.insights)              # paint the HUD
            return resp

    # ── Host detects the real-world signal, picks the TriggerType ──
    async def on_final_segment(self, seg):           # speaker finished a turn
        self.segments.append(seg)
        await self._drive(TriggerType.TURN_BASED)

    async def on_keyword(self, seg, keyword):        # host-side keyword spotting
        self.segments.append(seg)
        # engine.check_keyword_triggers is a helper; host owns detection (E-8: substring match)
        allowed = [a.config.id for a, _ in self.engine.check_keyword_triggers(seg.text)]
        await self._drive(TriggerType.KEYWORD, {"keyword": keyword}, allowed=allowed)

    async def on_silence(self, seconds):             # dead-air timer fired
        await self._drive(TriggerType.SILENCE, {"silence_duration": seconds})

    async def on_interval(self):                     # periodic background check
        await self._drive(TriggerType.INTERVAL)

    async def on_force_talk(self):                   # user pressed the button
        await self._drive(TriggerType.FORCE)         # bypasses cooldown + conditions

    async def rotate_key(self, new_key):
        async with self._lock:                       # E-4: no turn in flight
            self.engine.update_api_key(new_key)
```

Each real-world signal maps to one `TriggerType`, and the host calls `process_turn` with it. The engine sets the `sys.*` blackboard vars (`sys.turn_count`, `sys.session_id`, `sys.trigger_type`) and `context.trigger_type` itself — the host never sets these. The host's only jobs around the call are: build the context, pick the trigger, render the returned insights, and persist if it wants durability.

> **Why the lock matters.** `update_api_key` *requires* no in-flight turn (E-4), and the blackboard's phase-snapshot isolation assumes turns don't interleave on one session. The per-session `asyncio.Lock` is the simplest correct way to enforce the no-concurrent-turn precondition. It does **not** serialize *across* sessions — see scaling below.

---

## 10.6 Scaling: many concurrent sessions

The unit of isolation is the session: **one `AgentEngine` + one `Blackboard` per live conversation.** This is the load-bearing scaling decision, and it's why the host owns construction.

- **Sessions run fully in parallel.** Each `SessionRuntime` has its own lock, so the lock serializes turns *within* a session but never *across* sessions. A thousand conversations advance concurrently on one event loop; the engine's `gather`-based phase execution is `async` all the way down, so concurrency is I/O-bound on the LLM, not CPU-bound.
- **No shared mutable state between sessions.** Because each session has its own blackboard and engine, there is nothing to contend on. The `sys.*` vars, facts, queues, and memory are per-blackboard. Two sessions cannot corrupt each other.
- **The blackboard is in-memory and ephemeral.** It lives for the session's lifetime. For horizontal scale across processes/hosts, the host layer owns session affinity (route a session's turns to the host holding its runtime) and any snapshot/rehydrate to a store. The framework deliberately does not impose a persistence backend.
- **One `LLMClient` (and its connection pool) per engine, hence per session.** That's fine at conversational concurrency; if you run thousands of sessions per process, watch your aggregate OpenAI rate limits — the SDK's `max_retries=2` backoff will absorb brief `rate_limit` bursts, and your `last_error_category` monitoring will tell you when you're structurally over the limit rather than momentarily spiking.

The scaling story is intentionally boring: **share nothing, isolate per session, let `asyncio` interleave the I/O.** That is what lets a swarm of cheap observers run across a fleet of live conversations without coordination overhead.

---

## 10.7 Anti-patterns (the production hall of shame)

- **No `trigger_conditions` anywhere → cost blowup.** Every agent runs every eligible turn. You are paying for relevance you could have gated for free. Conditions are the first and cheapest gate; skipping them is the #1 cause of runaway spend.
- **Premium model on every agent.** `model="gpt-4o"` as the default across the swarm throws away the detector→analyzer tiering. Keep detectors on `gpt-4o-mini`; reserve premium models for event-gated analyzers that rarely fire.
- **No timeout / loose `max_tokens`.** A single slow request stalls the `gather` up to the full 10s; an uncapped JSON reply can blow both latency and cost. Pass a tight per-request `timeout` and a `max_tokens` matched to the rendered output.
- **Sharing one engine/blackboard across sessions.** Cross-session state leakage, snapshot-isolation violations, and a single lock throttling all conversations. One engine + one blackboard **per session**, always.
- **Calling `update_api_key` mid-turn.** Violates the E-4 precondition; an in-flight agent can get a half-swapped client. Always rotate behind the session lock with no turn in flight.
- **Ignoring `last_error_category`.** Retrying an `auth` failure burns latency on a guaranteed loss; treating a `malformed` spike as an outage sends you debugging infra when the bug is your prompt. The categories exist so you respond correctly — use them.
- **No observability.** Running the swarm with no tracer means you can't see which agent capped your latency, which agents actually spent tokens, or whether errors are creeping up. Attach `StructuredLogTracer` from day one — callbacks can't break the turn, so there's no excuse.

---

## 10.8 Production-readiness checklist

**Cost**
- [ ] Every always-on agent has a `cooldown` tuned to its value/latency (not the default 10 by accident).
- [ ] High-cost agents sit behind `trigger_conditions` (a free blackboard precondition) or a Phase-2 event subscription.
- [ ] Premium models (`gpt-4o`) are reserved for event-gated analyzers; detectors stay on `gpt-4o-mini`.
- [ ] `max_tokens` is set to the shape of the rendered output (often well under the 1024 default).

**Latency**
- [ ] HUD-critical agents pass a tight per-request `timeout` (e.g. 3s), not just the 10s client ceiling.
- [ ] You know your real-time budget = slowest Phase 1 agent (+ slowest Phase 2 if events fire).
- [ ] `max_phases` is `1` if you want strictly single-round latency; `2` only if you actually use event fan-out.

**Resilience**
- [ ] Confirmed: no agent path can raise out of `process_turn` (R-1 + graceful degradation + atomic discard).
- [ ] Cooldown-after-error (B4) is relied upon — a flapping agent can't hot-loop the LLM.
- [ ] Key rotation goes through the session lock (E-4); no `update_api_key` mid-turn.

**Observability**
- [ ] `StructuredLogTracer` is attached; `TURN_TRACE:` lines are shipped to your log store.
- [ ] Alerts on `last_error_category`: hard-stop on `auth`, page on `rate_limit`/`server` spikes, prompt-regression alert on `malformed`.
- [ ] Dashboards on `total_latency_ms` (p95/p99) and per-agent `latency_ms` + `status`.
- [ ] `tools/debugger.html` wired to the live WS for dev, and usable for paste-in post-incident review.

**Host integration & scale**
- [ ] One `AgentEngine` + one `Blackboard` per session; nothing shared across sessions.
- [ ] A per-session lock enforces the no-concurrent-turn precondition.
- [ ] Each real-world signal maps to the right `TriggerType`; the host never sets `sys.*` or `trigger_type` on the context directly.
- [ ] Blackboard persistence (snapshot/rehydrate) is implemented by the host if cross-restart durability is required.

---

## 🔑 Secret formula

> **Gate ruthlessly, pay reluctantly, fail invisibly, watch everything.**
>
> 1. **Four gates before a token.** Conditions (free) → cooldown (free) → model tier (cheap-vs-premium) → `max_tokens` (cap). Most agents, most turns, spend nothing. The premium model only fires after a cheap detector has already paid to notice.
> 2. **The turn is two parallel rounds, hard-bounded.** `gather` makes latency the slowest agent, not the sum; the `{1,2}` phase cap means the swarm can never cascade into an unbounded chain inside one turn. Tighten per-request `timeout` below the 10s ceiling for the HUD.
> 3. **Nothing can break a turn.** R-1 (`generate_json` never raises, returns `None`, categorizes the failure) + graceful degradation (`InsightType.ERROR`) + atomic discard (`_run_agent_safe` → `None`) compose into a total guarantee. B4 cooldown-after-error means even a failing agent is rate-limited.
> 4. **`last_error_category` is your incident compass.** `auth` = stop. `rate_limit`/`server`/`timeout` = transient, already retried. `malformed` = your prompt, not their infra. Monitoring it is how you tell "OpenAI is down" from "I shipped a bad prompt."
> 5. **Share nothing, isolate per session.** One engine + one blackboard per conversation, a per-session lock for the no-concurrent-turn precondition, `asyncio` interleaving the I/O. Scaling to thousands of live sessions is boring on purpose — and *restraint is the feature*: the cheapest, fastest, most resilient turn is the one where every gate did its job and almost nothing ran.
# Capstone — Designing a Complete Copilot Agent Suite

This chapter threads all ten together. We design a real suite end-to-end: a **live sales-call copilot**. The rep is on a call; transcript segments stream in; a HUD shows the occasional, perfectly-timed nudge. Watch how every decision is one of the ten laws.

> The worked configs below are illustrative of the real `DynamicAgent` config + schema shape (Chapter 6) and the real `AgentConfig` / `trigger_conditions` / `AgentConfigOverride` APIs. Treat them as the *design*, not copy-paste-final code.

---

## Step 0 — Design the Blackboard first (Law 6)

Before a single agent, design the world-model. This is the architecture *and* the host contract.

| Container | Keys | Written by | Read by |
|-----------|------|------------|---------|
| **Variables** | `phase` (discovery/demo/pricing/closing), `sentiment` (-1..1), `talk_ratio`, `risk_score` | PhaseDetector, SentimentMonitor, TalkRatioMonitor | conditions on advisors |
| **Facts** | `(budget, primary)`, `(stakeholder, *)`, `(timeline, *)`, `(objection, *)` | Extractors (high priority), Detectors (low priority) | advisors, the HUD summary rail |
| **Queues** | `pending_questions`, `unhandled_objections` | QuestionDetector, ObjectionDetector | AnswerSuggester, ObjectionCoach |
| **Events** | `objection_raised`, `question_asked`, `buying_signal`, `pricing_mentioned` | Phase-1 detectors | Phase-2 advisors (via `subscribed_events`) |
| **Memory** | per-advisor: `{last_advice_turn, themes_covered}` | each advisor (private) | same advisor next turn (MR-1) |

Get this table right and the rest is filling in agents.

---

## Step 1 — The roster, by archetype (Law 2)

Ten cheap agents, one premium-by-exception. Note the **priority** column — it's authority for fact merges (Law 7) and merge order.

| Agent | Archetype | Trigger | Model | Priority | Speaks? |
|-------|-----------|---------|-------|----------|---------|
| PhaseDetector | Detector | TURN_BASED (mod 3) | mini | 1 | no (writes `phase`) |
| ObjectionDetector | Detector | TURN_BASED | mini | 1 | no (emits event, queues) |
| QuestionDetector | Detector | TURN_BASED | mini | 1 | no (emits event, queues) |
| BuyingSignalDetector | Detector | KEYWORD + TURN_BASED | mini | 1 | no (emits event) |
| BudgetExtractor | Extractor | TURN_BASED (gated) | mini | **10** | no (writes facts) |
| StakeholderExtractor | Extractor | TURN_BASED (gated) | mini | **10** | no (writes facts) |
| TalkRatioMonitor | Monitor | TURN_BASED | — (no LLM) | 1 | rarely (WARNING) |
| ObjectionCoach | Advisor | **EVENT** `objection_raised` | **gpt-4o** | 5 | yes |
| AnswerSuggester | Advisor | **EVENT** `question_asked` | gpt-4o | 5 | yes |
| CloseAdvisor | Advisor | TURN_BASED (gated) | gpt-4o | 5 | yes |
| SilenceCoach | Advisor | SILENCE | mini | 3 | yes (gently) |

**Every turn, the expensive models usually don't run at all.** That's the formula.

---

## Step 2 — Detectors: cheap, silent, event-emitting (Laws 4, 5)

A detector's entire job is to *notice* and emit — it writes no advice. Real `DynamicAgent` config + a presence-gated schema:

```python
ObjectionDetector = {
  "name": "objection_detector",
  "model": "gpt-4o-mini",            # cheap; runs every turn
  "priority": 1,
  "cooldown": 0,                      # detection must not be rate-limited
  "trigger_types": ["TURN_BASED"],
  "instructions": "Watch the latest SPEAKER turns. If the prospect raises an "
                  "objection (price, timing, authority, need), name it. Otherwise "
                  "return has_objection=false.",
  "schema": "objection_detect.json"  # gate-less? NO — uses check_field (Ch.6)
}
```

`objection_detect.json` maps `check_field: "has_objection"` (the silence gate) and, when true, emits an **event** and pushes to a **queue**:

```json
{ "has_objection": true,
  "events": [{"name": "objection_raised", "payload": {"kind": "price"}}],
  "queues": {"unhandled_objections": [{"text": "too expensive", "turn": 14}]} }
```

The detector spoke to *no one* — it rang a doorbell (event) and dropped a note in an inbox (queue). The premium ObjectionCoach will pick it up in Phase 2.

---

## Step 3 — Extractors: cheap, gated, high-priority facts (Laws 3, 7)

Extractors build the durable knowledge graph. They are **high priority** so their facts are canonical (Law 7), and **gated** so they don't burn calls every turn:

```python
BudgetExtractor = {
  "name": "budget_extractor",
  "model": "gpt-4o-mini",
  "priority": 10,                     # authoritative — wins fact merges
  "cooldown": 30,
  "trigger_types": ["TURN_BASED"],
  "trigger_conditions": {             # only run when budget is plausibly in play
    "mode": "any",
    "rules": [
      {"var": "phase", "op": "in", "value": ["pricing", "closing"]},
      {"queue": "pending_questions", "op": "contains", "value": "cost"}
    ]
  },
  "instructions": "Extract any stated budget figure as a fact.",
  "schema": "fact_extract.json"
}
```

Its fact lands as `(budget, primary)` with `priority=10` stamped by the engine. A chatty low-priority detector that also guesses a budget can **never** overwrite it (F-1 / INV-9). That's how you make one extractor the single source of truth without a line of `if`.

---

## Step 4 — Advisors: premium, event-or-condition-gated, the only voices (Laws 1, 4, 8, 10)

Advisors are the only agents that speak — and they almost never run. Two patterns:

**(a) Event-driven advisor (Phase 2).** Subscribes to a detector's event:

```python
ObjectionCoach = {
  "name": "objection_coach",
  "model": "gpt-4o",                  # premium — but only fires on an objection
  "priority": 5,
  "cooldown": 20,
  "trigger_types": ["EVENT"],         # DynamicAgent auto-adds EVENT when subscribed
  "subscribed_events": ["objection_raised"],
  "instructions": "An objection was just raised. Read the conversation and the "
                  "(objection,*) facts. Give the rep ONE crisp, specific rebuttal "
                  "line they can say now. If you have nothing strong, stay silent.",
  "schema": "default_v2.json"         # gated insight + expiry + action_label
}
```

It runs in **Phase 2 of the same turn** the objection was detected — the rep gets the rebuttal in the same beat. The schema's `has_insight: false` path lets it decline gracefully (Law 1).

**(b) Condition-driven advisor (Phase 1).** Fires on accumulated state, no event needed:

```python
CloseAdvisor = {
  "name": "close_advisor",
  "model": "gpt-4o",
  "priority": 5,
  "cooldown": 45,
  "trigger_types": ["TURN_BASED"],
  "trigger_conditions": {
    "mode": "all",
    "rules": [
      {"var": "phase", "op": "eq", "value": "closing"},
      {"var": "sentiment", "op": "gte", "value": 0.4},
      {"fact": "budget.primary", "op": "present"}
    ]
  },
  "instructions": "Conditions say it's time to close. Suggest the next concrete step."
}
```

This agent costs nothing until the conversation has *earned* it: closing phase, positive sentiment, budget known. The conditions did the thinking for free (Law 3).

---

## Step 5 — Monitors: computation, not tokens (Law 2)

Not every agent needs an LLM. `TalkRatioMonitor` is a custom `BaseAgent` subclass that counts words and writes a variable + (rarely) a WARNING — zero LLM cost, every turn:

```python
class TalkRatioMonitor(BaseAgent):
    async def evaluate(self, ctx):
        rep, them = self._word_split(ctx.recent_segments)
        ratio = rep / max(rep + them, 1)
        resp = AgentResponse(variable_updates={"talk_ratio": ratio})
        if ratio > 0.7:
            resp.insights.append(self.create_insight(
                InsightType.WARNING, "You're talking 70%+ — ask a question.",
                expiry=8))
        return resp
```

`talk_ratio` is now a Blackboard variable other agents can gate on. Cheap signal, shared once, reused everywhere (Law 6).

---

## Step 6 — One turn, traced end-to-end (Law 5)

The prospect says *"Honestly the price feels high for what we'd use."* The host calls `engine.process_turn(ctx, trigger_type=TURN_BASED)`:

1. **Phase 1** (parallel, against one snapshot): PhaseDetector keeps `phase=pricing`; **ObjectionDetector** fires → emits `objection_raised`, queues the objection; BudgetExtractor (gated on pricing phase) confirms `(budget, primary)`; TalkRatioMonitor updates `talk_ratio`. *No one has spoken.*
2. The engine harvests Phase-1 events, sees `objection_raised`, flips to **Phase 2**.
3. **Phase 2**: `ObjectionCoach` (subscribed) runs on `gpt-4o`, reads the objection fact + transcript, returns one rebuttal insight (`expiry=12`, `action_label="Use this"`).
4. **Merge** (by priority) → `AgentResponse` with one insight, several facts, one event, updated variables.
5. The host **curates to one** insight and renders it. The HUD glows for 12 seconds, then clears itself (Law 10).

Cost of that turn: ~4 mini calls + **1** premium call. A quiet turn (no objection, no question): ~4 mini calls, **zero** premium, **zero** insights. That asymmetry is the whole game.

---

## Step 7 — Roles: one suite, many personalities (Law 9)

The same eleven agents become a *rookie* copilot or an *expert* copilot via `AgentConfigOverride`, recomputed each turn from the rep's profile — no new agents:

```python
ROOKIE_ROLE = {
  objection_coach.id: AgentConfigOverride(cooldown_modifier=-15),   # coach more often
  close_advisor.id:   AgentConfigOverride(context_turns_modifier=+4,  # more context
                       instructions_append="Explain WHY, the rep is learning."),
}
EXPERT_ROLE = {
  objection_coach.id: AgentConfigOverride(cooldown_modifier=+40),   # rarely interrupt
  silence_coach.id:   AgentConfigOverride(cooldown_modifier=+9999), # basically off
}
```

Pass the role's dict as `context.agent_config_overrides` each turn. The base swarm is untouched; the *diff* is the product surface. (Cooldown floor is 5s; overrides are typed — a typo'd knob raises immediately.)

---

## Step 8 — The host loop (Law 3 + Chapter 10)

The host owns the stream and maps real-world signals to triggers; the engine owns the reaction. One engine + one blackboard **per session**:

```python
async with session.lock:                      # never overlap turns on one engine
  if segment.is_final:
      await engine.process_turn(ctx, trigger_type=TURN_BASED)
  if matched := engine.check_keyword_triggers(segment.text):
      await engine.process_turn(ctx, trigger_type=KEYWORD,
                                allowed_agent_ids=[a.id for a, _ in matched])
  if silence_seconds > threshold:
      await engine.process_turn(ctx, trigger_type=SILENCE,
                                trigger_metadata={"silence_seconds": silence_seconds})
  # render: curate ctx-returned insights to ONE, honor expiry as TTL
```

`KEYWORD`/`SILENCE`/`INTERVAL`/`FORCE` are *host-invoked* — the engine doesn't watch the clock or scan text. The host decides *when*; the swarm decides *what*.

---

## Step 9 — Why this is the secret formula

Count what happens on a typical turn: eleven agents are *eligible*, the funnel rejects most of them for free, four cheap detectors/monitors run, the Blackboard gets a little richer, and **usually nobody speaks**. When the prospect finally objects, exactly one premium agent wakes up, says one earned thing, and goes quiet. The understanding compounds silently across the whole call; the HUD stays calm; the one time it glows, the rep trusts it.

That is the entire framework working as designed:

- **Decompose** (11 narrow agents) ·
- **Coordinate** (events + facts + the board, no agent calls another) ·
- **Gate** (conditions + cooldowns + cheap-detect/premium-analyze) ·
- **Time** (one curated, expiring insight at the earned moment) ·
- **Restraint** (silence is the default; speaking is the exception).

Build every copilot this way and it will feel less like a chatbot bolted onto a call and more like a quiet expert sitting beside the rep — which is the only version worth shipping.

---

*End of the Xubb Agents Playbook. The framework gives you the primitives; the formula is how you wield them. Now go build something that earns its two seconds.*
