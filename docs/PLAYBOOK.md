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

The playbook is in two parts. **Part I — The Doctrine** (Chapters 1–10 + the Capstone) is *why* and *how to think*. **Part II — The Operating Manual** is the checklists, blueprints, metrics, tests, and review gates that make the doctrine daily practice and hard to violate. Read Part I to understand; live in Part II.

## Table of contents

### Part I — The Doctrine

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

### Part II — The Operating Manual

12. [Agent Design Checklist: From Idea to Production](#agent-design-checklist--from-idea-to-production)
13. [Xubb Agent Patterns & Smells](#xubb-agent-patterns--smells)
14. [The Insight Curator: The Final Authority Before the HUD](#the-insight-curator--the-final-authority-before-the-hud)
15. [The Minimum Viable Swarm](#the-minimum-viable-swarm)
16. [The Golden Path: Build a Price-Objection Suite in 30 Minutes](#the-golden-path--build-a-price-objection-agent-suite-in-30-minutes)
17. [Testing Templates: Prove It Works (Especially the Silence)](#testing-templates--prove-it-works-especially-the-silence)
18. [Quality Metrics: Making Restraint Measurable](#quality-metrics--making-restraint-measurable)
19. [Definition of Done: For an Agent](#definition-of-done--for-an-agent)
20. [The Agent Review Board](#the-agent-review-board)
21. [Product Experience Doctrine](#product-experience-doctrine)

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
| `model_config.model` / `model` | LLM id (default `gpt-4o-mini` = `xubb_agents.DEFAULT_MODEL`). |
| `model_config.context_turns` / `context_turns` | Transcript window size (default **6**). `<= 0` means *all* segments. |
| `model_config.reasoning_effort` | v2.6. Explicit reasoning effort (`"none"`/`"minimal"`/`"low"`/`"medium"`/…). Sent on the wire **only when set** — the framework never injects (INV-15). **Required at registration** when the model name looks reasoning-capable (INV-19; `AgentEngine(strict_reasoning_config=False)` downgrades to a warning). Value validity is per-model — a wrong pair surfaces as `misconfig`. |
| `model_config.timeout` | v2.6. Per-agent request timeout (seconds); unset → client budget. Deep-effort agents need `> 10`. |
| `model_config.max_tokens` | v2.6. Per-agent token cap (wire: `max_completion_tokens`; **includes reasoning tokens** — deep-effort agents need `>= 4096`, ~25000 for real headroom). |
| `model_config.model_params` | v2.6. Verbatim Chat-Completions passthrough dict (e.g. `{"verbosity": "low"}`). Framework-owned keys rejected at load; documented as wire-shaped, **not** transport-portable. |
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

> **v2.6 — the two-lane upgrade of this pattern.** With reasoning models the tiering dial gains a second axis: `reasoning_effort`. The fast lane pins it low and cheap; the deep lane buys real thinking *with matching budgets*:
>
> ```python
> # Fast lane: current-gen detector, thinking OFF, real-time envelope
> AgentConfig(name="Objection Scout", model="gpt-5.4-nano",
>             reasoning_effort="none", cooldown=8)
>
> # Deep lane: silence-triggered analyzer, explicit effort + budgets to match
> AgentConfig(name="Objection Strategist", model="gpt-5.6-terra",
>             reasoning_effort="medium", timeout=30.0, max_tokens=25000,
>             trigger_types=[TriggerType.EVENT],
>             subscribed_events=["objection_raised"])
> ```
>
> **Custom `BaseAgent` subclasses: the config fields are a declaration, not magic.** Registration validation (INV-19) reads them, but *your* `evaluate()` owns forwarding them into the call — otherwise the wire never carries the effort and you silently pay the model's default:
>
> ```python
> async def evaluate(self, context):
>     ...
>     result = await self.llm.generate_json(
>         model=self.config.model, messages=messages,
>         reasoning_effort=self.config.reasoning_effort,   # forward the declaration
>         timeout=self.config.timeout,
>         max_tokens=self.config.max_tokens,
>     )
> ```
> (`DynamicAgent` does this for you, only-when-configured.)

### Gate 4 — `max_tokens`: cap the worst case

Every call is output-capped. The cap is the per-call override or the client default (1024):

```python
# core/llm.py — generate()
effective_max_tokens = max_tokens if max_tokens is not None else self.max_tokens
call_kwargs[self.wire_max_tokens_param] = effective_max_tokens   # max_completion_tokens by default (v2.5)
```

Because responses are forced JSON (`response_format={"type": "json_object"}`), a tight `max_tokens` both bounds cost *and* protects the latency budget — a runaway generation can't blow either. For a HUD insight that's one sentence and a confidence score, 1024 is generous; many agents are happy at 256. **Cap to the shape of the output you actually render.**

> **v2.5 wire note:** the Python parameter is still `max_tokens`, but it ships on the wire as
> `max_completion_tokens` — required by reasoning models, accepted by everything current. Old
> OpenAI-compatible proxies that predate the kwarg can pin
> `LLMClient(wire_max_tokens_param="max_tokens")`. On reasoning models the cap covers
> *reasoning tokens too*: a cap sized for a one-sentence whisper will starve a reasoning
> model into a `truncated` failure — billed, with no output.

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
# core/llm.py — categories: timeout | rate_limit | auth | server | misconfig | truncated | malformed | not_initialized | unknown
except APITimeoutError as e:
    logger.error(f"… [category=timeout]: {e}");   return self._finish(error_category="timeout")
except RateLimitError as e:
    logger.error(f"… [category=rate_limit]: {e}"); return self._finish(error_category="rate_limit")
except AuthenticationError as e:
    logger.error(f"… [category=auth]: {e}");      return self._finish(error_category="auth")
```

These categories are operationally distinct and you must treat them so. `auth` means **stop** — your key is bad; retrying burns latency on a guaranteed failure and `rate_limit` retries make it worse. `rate_limit` / `server` / `timeout` are transient — the SDK already retried with exponential backoff (`max_retries=2`) before the exception surfaced. `misconfig` (v2.5) is a **4xx client rejection** — an unsupported parameter, unknown model, or bad request shape: an operator problem that no amount of retrying fixes, and *not* an outage. `truncated` (v2.5) means the model stopped on the token cap (`finish_reason="length"`) — with reasoning models this is the classic starved-cap signature: **you were billed for tokens and got no usable output**; raise the cap or lower the effort. `malformed` means the model returned non-JSON or filtered content — a prompt/schema problem, not an infra problem. **Monitoring the error category is how you tell "OpenAI is down" from "my prompt is broken" from "my config is wrong."** Ignoring it is flying blind during an incident.

> **v2.5 attribution note:** for per-call attribution use the enriched
> `generate()` method, which returns an `LLMResult` carrying `parsed`,
> `error_category`, `usage` (prompt/completion/reasoning/cached token ints —
> populated even on `truncated`/`malformed`, which are billed), and
> `finish_reason`. `generate_json` is now a thin delegate over it and keeps
> the dict-or-`None` contract. `last_error_category` remains as a deprecated
> best-effort mirror — see the concurrency caveat in §10.4.

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

> Note `last_error_category` lives on the **shared** `engine.llm_client` (one client per engine) and agents run concurrently — under `asyncio.gather` it can only report the *last writer*, so it is now a **deprecated best-effort mirror**. For per-agent attribution use the v2.5 path: `DynamicAgent` calls the enriched `generate()` and surfaces the per-call result — `response.usage` (first-class, serializes) and `debug_info["usage"]` — or correlate via the tracer's per-step `status`.

### The visual debugger (`tools/debugger.html`)

`tools/debugger.html` is a zero-backend, single-file Vue app — the "Xubb Agent MRI." It ingests the `TURN_TRACE:` lines two ways: **paste** a block of logs, or connect **live over WebSocket** (default `ws://localhost:8000/ws/debug`). It renders a turn timeline with per-turn trigger badges and average latency, then a detail view per agent: status, latency, insights (color-coded by `InsightType`), state/variable/event/fact/queue/memory deltas, sidecar `data`, and collapsible raw prompt + raw response from `debug_info`. In practice: pipe the tracer's log line into the live WS during development, or paste production logs after an incident. It turns the Golden Log Line into a clickable MRI of why the swarm did what it did.

**What to log and monitor in production:**
- Per-turn: `total_latency_ms` (p50/p95/p99 vs your real-time budget), `final_insight_count`.
- Per-agent: `latency_ms` (find the slow agent capping your turn), `status` distribution (rising `no_response`/`error` = an agent degrading).
- LLM health: error-category distribution — alert hard on `auth`, page on a `rate_limit`/`server` spike, treat a `malformed` spike as a prompt regression, treat `misconfig` as a config/deploy bug (a 4xx rejection — don't page the outage runbook), and treat `truncated` as a token-budget bug: **you are paying for output you never see** (raise `max_tokens` or lower reasoning effort).
- Cost: v2.5 puts real token usage on every per-agent response (`response.usage`, incl. `reasoning_tokens`/`cached_tokens` when reported) — sum it per agent per session instead of counting rounds; `on_agent_finish` count per turn remains the sanity check that your gates aren't loosening.

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
- **Ignoring the error categories.** Retrying an `auth` failure burns latency on a guaranteed loss; treating a `malformed` spike as an outage sends you debugging infra when the bug is your prompt; paging the outage runbook on `misconfig` (a 4xx config rejection) hides a deploy bug; ignoring `truncated` quietly bills you for output the cap ate. The categories exist so you respond correctly — use them.
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
- [ ] Alerts on error categories: hard-stop on `auth`, page on `rate_limit`/`server` spikes, prompt-regression alert on `malformed`, deploy/config alert on `misconfig` (4xx — not an outage), token-budget alert on `truncated` (billed, no output).
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
> 4. **The error category is your incident compass.** `auth` = stop. `rate_limit`/`server`/`timeout` = transient, already retried. `misconfig` = 4xx config rejection — your deploy, not their infra. `truncated` = the token cap ate a billed answer. `malformed` = your prompt. Monitoring it is how you tell "OpenAI is down" from "I shipped a bad prompt" from "I shipped a bad config." (Per-call: `LLMResult.error_category`; the shared `last_error_category` mirror is deprecated.)
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

*This concludes **Part I — The Doctrine**. Part II turns it into an operating manual — the checklists, blueprints, metrics, and review gates that make the doctrine hard to violate.*
---

# Part II — The Operating Manual

Part I is doctrine: *why* a Xubb copilot is a restrained, blackboard-coordinated swarm, and the architecture that makes it so. Part II is the **operating manual** — the checklists, blueprints, metrics, and review gates that turn the doctrine into daily engineering practice.

The point of Part II is not to re-explain the philosophy. It is to make the philosophy **hard to violate**. A team can read Part I, nod, and still ship a chatty, ungated, mega-agent swarm. Part II exists so that the *easy* path — the checklist, the template, the Definition of Done, the review questions — is also the *correct* path.

Use it like this:

- **Designing a new agent?** Run the [Agent Design Checklist](#agent-design-checklist--from-idea-to-production) and check it against the [Patterns & Smells](#xubb-agent-patterns--smells).
- **Starting a copilot from zero?** Build the [Minimum Viable Swarm](#the-minimum-viable-swarm), then walk the [Golden Path](#the-golden-path--build-a-price-objection-agent-suite-in-30-minutes).
- **Shipping?** Gate on the [Definition of Done](#definition-of-done--for-an-agent), the [Testing Templates](#testing-templates--prove-it-works-especially-the-silence), and the [Quality Metrics](#quality-metrics--making-restraint-measurable).
- **Reviewing a teammate's agent?** Convene the [Agent Review Board](#the-agent-review-board).
- **Always:** hold the [Product Experience Doctrine](#product-experience-doctrine) as the bar.

Every artifact below is grounded in the real v2.2 framework, and every one serves the same end: a copilot that earns its two seconds.

### Part II contents

- [Agent Design Checklist: From Idea to Production](#agent-design-checklist--from-idea-to-production)
- [Xubb Agent Patterns & Smells](#xubb-agent-patterns--smells)
- [The Insight Curator: The Final Authority Before the HUD](#the-insight-curator--the-final-authority-before-the-hud)
- [The Minimum Viable Swarm](#the-minimum-viable-swarm)
- [The Golden Path: Build a Price-Objection Suite in 30 Minutes](#the-golden-path--build-a-price-objection-agent-suite-in-30-minutes)
- [Testing Templates: Prove It Works (Especially the Silence)](#testing-templates--prove-it-works-especially-the-silence)
- [Quality Metrics: Making Restraint Measurable](#quality-metrics--making-restraint-measurable)
- [Definition of Done: For an Agent](#definition-of-done--for-an-agent)
- [The Agent Review Board](#the-agent-review-board)
- [Product Experience Doctrine](#product-experience-doctrine)

---
## Agent Design Checklist — From Idea to Production

Before you write a line of config, force yourself to answer these thirteen questions. If you cannot answer one cleanly, the agent isn't designed yet. Each maps to a real framework mechanism — answering them *is* the design.

| # | Question | Why it matters (the framework hook) |
|---|----------|-------------------------------------|
| 1 | **What is the agent's one-sentence job?** | If the sentence needs an "and," it's two agents. Single-responsibility is what makes gating, failure, and cost independent (Ch. 2). |
| 2 | **Is it a Detector, Extractor, Advisor, or Monitor?** | The archetype decides everything else: which `AgentResponse` channels it writes (events / facts / variables / insights) and whether it's allowed to speak (Ch. 2). |
| 3 | **What Blackboard containers does it READ?** | Declares its inputs: `variables`, `facts`, `queues`, `memory`. Reads happen against an immutable per-phase snapshot (Ch. 3). |
| 4 | **What Blackboard containers does it WRITE?** | Declares its outputs. Detectors write `events`/`queues`; Extractors write `facts`; Monitors write `variables`; Advisors write `insights`. Writing the wrong container is the #1 design error (Ch. 3). |
| 5 | **What trigger wakes it?** | `TURN_BASED`, `KEYWORD`, `SILENCE`, `INTERVAL`, `EVENT`, or `FORCE`. EVENT (subscribing another agent's signal) is how the cheap→premium cascade works (Ch. 4–5). |
| 6 | **What conditions prevent it from running?** | `trigger_conditions` run **before any LLM call** — the single biggest cost lever. Push every cheap precondition here (phase, fact-presence, queue-not-empty, turn cadence). No conditions = runs every eligible turn (Ch. 4). |
| 7 | **What model does it use, and why?** | Default `gpt-4o-mini`. Premium (`gpt-4o`) is *by exception* — only the few Advisors that have earned it via an event. "Premium everywhere" is a cost smell (Ch. 2, 10). |
| 8 | **What is its cooldown?** | The timing backstop (default 10s, floor 5s with a Role modifier). Detectors often `cooldown=0`; Advisors are higher. Cooldown is enforced even on a silent/failed run (Ch. 4). |
| 9 | **Can it stay silent?** | The most important question. Detectors/Extractors/Monitors should emit **zero insights** most turns; Advisors should decline via the schema's `check_field` (`has_insight: false`). Silence must be the easy path (Ch. 6, 8). |
| 10 | **What would be a false positive?** | An interruption the user didn't need. The cost of a false positive in a HUD is *lost trust*, not a wrong answer. Tune conditions/confidence to make it rare (Ch. 8). |
| 11 | **What would be a false negative?** | A missed critical moment — the one failure where silence is *wrong*. The deliberate counterweight to restraint. Decide which moments you must never miss (Ch. 8, Metrics). |
| 12 | **What should be logged for observability?** | Hook the lifecycle callbacks / tracer: did it run, skip (and why), speak, or error? Per-agent insight rate and skip reason are the signal (Ch. 10, Metrics). |
| 13 | **What test transcript proves it works — including that it correctly stays silent?** | At least three transcripts: one where it should fire, one where it must *not*, one edge case. The silence test is non-negotiable (Testing Templates). |

### Fill-in template (copy per agent)

```
Agent: ______________________
1.  Job (one sentence): ______________________
2.  Archetype:  Detector | Extractor | Advisor | Monitor
3.  Reads:   variables[...] facts[...] queues[...] memory[...]
4.  Writes:  events[...] facts[...] variables[...] queues[...] insights? Y/N
5.  Trigger: TURN_BASED | KEYWORD | SILENCE | INTERVAL | EVENT(<event>) | FORCE
6.  Conditions (pre-LLM gate): ______________________
7.  Model: gpt-4o-mini | gpt-4o  — because: ______________________
8.  Cooldown: ___s
9.  Silent path: ______________________  (how it says nothing)
10. False positive looks like: ______________________
11. False negative looks like: ______________________
12. Observability: ______________________
13. Test transcripts: [fires] ___  [SILENT] ___  [edge] ___
```

If row 9 or row 13's "[SILENT]" is blank, the agent is not ready to build.
## Xubb Agent Patterns & Smells

Part I argues the anti-patterns in prose. Here they are as a scannable, teachable checklist — pin it above your desk. If a design matches a pattern, you're on the path. If it matches a smell, stop.

### ✅ Good patterns

| Pattern | What it is |
|---------|-----------|
| **Silent Observer** | An agent that enriches the Blackboard (facts/events/variables) and emits **zero** insights. Understanding compounds; the HUD stays calm. |
| **Cheap Detector → Premium Advisor** | A `gpt-4o-mini` detector notices every turn and emits an event; a `gpt-4o` advisor fires only in Phase 2 when the event earns it. The core cost pattern. |
| **Event Doorbell + Queue Inbox** | A detector rings a doorbell (`emit_event`) *and* drops a durable note (`push_queue`). The reactor wakes on the doorbell; the inbox survives for later. |
| **One-Insight Curator** | The host curates `response.insights` down to a single rendered insight. The list is a menu, not a render queue (Law 10). |
| **Phase-Based Escalation** | Observation in Phase 1, reaction in Phase 2 — never a same-phase read. Cross-agent reaction routes through an event. |
| **Role Override, Not Fork** | Adapt behavior per user/context with `AgentConfigOverride` (cooldown / context / instructions). The base swarm never changes. |
| **Blackboard-First Design** | Design the five-container world-model *before* the agents. It's the architecture and the host contract in one. |
| **Authority by Priority** | Make an extractor canonical by raising its **agent priority**, so its facts win merges regardless of a noisier agent's confidence. |
| **Gate in Config, Not Code** | The silence gate (`check_field`/`has_insight`) lives in the schema; declining to speak is a returned field, not a branch. |

### 🚩 Bad smells

| Smell | Why it's wrong |
|-------|----------------|
| **Agent purpose has an "and" in it** | It's a mega-agent. Split it; let the halves talk through events and facts. |
| **Agent emits an insight every time it runs** | No silence gate. It will spam the HUD and erode trust. |
| **Agent uses a premium model for detection** | You're paying `gpt-4o` to do a `gpt-4o-mini` job on every turn. Tier it. |
| **Agent writes durable state into an event** | Events are cleared after the turn. Durable knowledge belongs in facts/variables. |
| **Agent has no cooldown (and isn't a pure detector)** | It can fire back-to-back. Cost and HUD-spam risk. |
| **Agent needs another agent to call it directly** | There is no agent-to-agent call. Coordinate through an event or the board. |
| **Agent reads another agent's same-phase write** | It won't see it — agents run against a frozen snapshot. Route the dependency through Phase 2. |
| **Agent requires the HUD to understand agent-specific logic** | Rendering should depend only on `InsightType` + standard fields + `metadata` hints, never on which agent produced it. |
| **No `trigger_conditions` on a non-detector** | It runs every eligible turn and burns calls. Push preconditions into the free, pre-LLM gate. |
| **Confidence used as authority** | Priority wins fact merges; confidence is only the tiebreaker within equal priority. A high-confidence low-priority agent is not authoritative. |

> **The one-line test:** if you can't say *what the agent reads, what it writes, what wakes it, what stops it, and how it stays silent* in five short phrases, it has a smell you haven't named yet.
## The Insight Curator — The Final Authority Before the HUD

> *The swarm earns insights. The curator decides which one — if any — the user
> is allowed to see. It is the last gate between a roomful of cheap observers and
> a single human's two seconds of attention. The insight list is a menu, not a
> render queue (Law 10); the curator is the host-side authority that reads the
> menu and orders one dish.*

This is a Part II operating-manual pattern: a **first-class, host-side
component** that every serious deployment needs and the framework deliberately
does not ship. The framework's job ends at a typed list of earned insights. The
curator's job begins there and ends at the HUD.

---

### 1. Why the curator is the missing bridge

The architecture chapters end at a clean contract: `AgentResponse.insights:
List[AgentInsight]`. The product law (Chapter 8, Law 10) is equally clean: the
HUD shows **at most one** earned insight, and silence the rest of the time.
Between those two facts sits a gap that nothing in the framework closes — and the
curator is what closes it.

Walk the pipeline and watch the gap appear:

1. **The agent gates itself.** `DynamicAgent.evaluate` (`library/dynamic.py`)
   runs the INV-11 silence gate — `check_field` / `root_key` / gate-less default
   — so an agent that has nothing to say creates *no insight at all*. This is the
   **first gate**, and it operates on one agent in isolation.
2. **The engine appends — it does not curate.** `Engine._merge_responses`
   (`core/engine.py`) collects every agent's response and does, literally:

   ```python
   # core/engine.py — _merge_responses
   for priority, index, agent_id, resp in updates:
       # Merge insights
       final_response.insights.extend(resp.insights)
   ```

   That is the *entire* insight-handling step. Responses are sorted by
   `(priority, registration_order)` for deterministic *ordering*, but every
   surviving insight is **appended**. The engine never drops, ranks, dedups, or
   caps anything. Curation is explicitly **not** the engine's responsibility —
   it is the host's.
3. **The HUD can show only one.** A copilot overlay is a 2-second glanceable
   stage, not a log (Chapter 8 §1).

Now the gap is obvious. Each agent gated itself honestly, the engine faithfully
appended, and on a *busy turn* — a hot moment in the conversation where an
objection, a buying signal, and a coachable habit all land at once — three
different agents each legitimately produce one insight. The first gate did its
job per-agent; nothing checked the **cross-agent** total. The host receives:

```python
response.insights == [
    AgentInsight(agent_id="risk_watcher",  type=WARNING,     content="Claim about pricing is wrong", confidence=0.82, ...),
    AgentInsight(agent_id="closer",        type=OPPORTUNITY, content="They just asked about onboarding — ask for the close", confidence=0.74, ...),
    AgentInsight(agent_id="coach",         type=SUGGESTION,  content="You're talking over them", confidence=0.66, ...),
]
```

A perfectly-gated swarm just handed the host three insights. With no curator, the
naive consumer writes the canonical spam bug — `for i in response.insights:
hud.show(i)` — and the HUD stacks three cards. The one that mattered is buried;
the user's trust in the glow erodes; restraint, the actual product, is gone.

**The curator is the second gate: the cross-agent gate.** The silence gate
filters *within* an agent (`library/dynamic.py`); the curator filters *across*
agents, on the host side, immediately before render. It is the component that
turns "the engine handed me a menu" into "the user sees one earned insight, or
nothing." Without it, the architecture is correct and the product is noisy.

---

### 2. Where it sits — after `process_turn`, before render

The curator is a single, well-defined seam in the host's turn loop:

```
swarm (gated per-agent)
      │   each agent: INV-11 silence gate  →  0 or 1 insight
      ▼
Engine.process_turn(...)  ──▶  AgentResponse.insights : List[AgentInsight]   (APPENDED, not curated)
      │
      ▼
╔══════════════════════════════════════════════╗
║  InsightCurator.curate(response, now)         ║   ◀── the second, cross-agent gate (THIS pattern)
║   floor → rank → dedup → suppress → cap to 1  ║
╚══════════════════════════════════════════════╝
      │
      ▼
Optional[AgentInsight]   ──▶  HUD.present(...)   or   silence
```

It runs **after** the engine has finished aggregating the turn and **before** a
single pixel is rendered. It is pure host policy: the glanceability budget is not
a framework concern (the framework can't know your overlay), so the law that "the
HUD shows at most one" can only be enforced here.

One responsibility split worth stating plainly, because it is the whole point of
the pattern:

| Layer | Owns | Lives in |
| --- | --- | --- |
| Agent silence gate | "Should *I* speak this turn?" (per-agent) | `library/dynamic.py` (framework) |
| Engine merge | Deterministic ordering + blackboard application; **append** insights | `core/engine.py` (framework) |
| **Insight Curator** | "Of everything the swarm earned, what does the **user** see?" (cross-agent, ≤ 1) | **host** (this pattern) |

---

### 3. The ranking model — grounded in the real fields

The curator ranks on the fields that actually exist on `AgentInsight`
(`core/models.py`): `type`, `confidence`, `action_label`, `agent_id`, `content`,
`expiry`. No invented fields. Four levers, in priority order:

**Lever 1 — Urgency tier (from the `InsightType` enum).** The enum carries zone
semantics in its own comments (`OPPORTUNITY = "opportunity"  # Zone A: Urgent
Positive`). That gradient *is* the ranking spine — prefer urgent over
interesting:

| `InsightType` | Tier | Rationale (from enum/zone semantics) |
| --- | --- | --- |
| `WARNING` | 4 — Urgent Negative | Risk in flight; interrupt-worthy. |
| `OPPORTUNITY` | 3 — Zone A: Urgent Positive | A door just opened; time-critical good news. |
| `SUGGESTION` | 2 — Advisory | A calm nudge; default coaching. |
| `PRAISE` | 1 — Reinforcement | Warm, never urgent. |
| `FACT` | 0 — Ambient | Durable knowledge, not a stage interrupt. |
| `ERROR` | — | **Not a coaching insight.** Framework failure channel (auto-emitted by `BaseAgent.process` on exception). Split to a system tray; never ranked for the stage. |

**Lever 2 — Actionable beats descriptive.** `action_label` is `Optional[str]`. An
insight that ships a button (`action_label` present) gives the user something to
*do*; among equal urgency, prefer it. This is a real field-presence signal, not a
heuristic.

**Lever 3 — Confidence.** `confidence` (`0.0–1.0`, default `1.0`, clamped by A-3)
is the tiebreaker *and* the floor. As a floor it kills noise before ranking; as a
tiebreaker, among equal urgency and equal actionability, the more-confident
insight wins.

**Lever 4 — Recency / repetition (cross-turn).** The framework gives no
cross-turn memory, so the curator keeps a small short-term history keyed by
`agent_id` and a normalized `content` signature. This enforces "prevent repeated
coaching": don't re-show the same agent's point turn after turn, even when it
keeps re-winning the rank.

Composite sort key (descending): `(urgency_tier, actionable, confidence)`. Then
dedup, suppress against history, and **cap to one**.

---

### 4. Reference implementation — a runnable `InsightCurator`

Drop-in host-side class. It depends only on the real public surface
(`AgentInsight`, `InsightType`, `AgentResponse`) and the standard library. It
applies a per-type confidence floor, ranks on the model above, dedups by
`agent_id` and by content similarity, suppresses recently-shown insights and
repeated coaching across turns, enforces one-at-a-time, and honors `expiry` as a
TTL.

```python
import time
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional, List, Dict, Tuple

from core.models import AgentInsight, InsightType, AgentResponse


# Urgency tiers — straight from the InsightType enum's zone comments.
# Higher = more deserving of the user's 2 seconds.
URGENCY_TIER: Dict[InsightType, int] = {
    InsightType.WARNING: 4,      # Urgent Negative
    InsightType.OPPORTUNITY: 3,  # Zone A: Urgent Positive
    InsightType.SUGGESTION: 2,   # Advisory
    InsightType.PRAISE: 1,       # Reinforcement
    InsightType.FACT: 0,         # Ambient / reference
    # ERROR intentionally absent — never competes for the coaching stage.
}

# Per-type confidence floor. The floor kills noise; ranking picks the winner.
MIN_CONFIDENCE: Dict[InsightType, float] = {
    InsightType.WARNING: 0.55,      # warnings may be speculative — better safe
    InsightType.OPPORTUNITY: 0.70,
    InsightType.SUGGESTION: 0.75,   # nudges must be earned
    InsightType.PRAISE: 0.80,
    InsightType.FACT: 0.80,         # don't pollute the knowledge zone with guesses
}
DEFAULT_FLOOR = 0.75

# How long a shown insight blocks near-duplicates from the same source / topic.
SOURCE_COOLDOWN_S = 20.0      # same agent_id can't re-take the stage this fast
REPEAT_COOLDOWN_S = 45.0      # same *content* (any agent) — anti repeated-coaching
SIMILARITY_THRESHOLD = 0.82   # content dedup / repeat-detection cutoff


def _signature(text: str) -> str:
    """Normalize content for similarity comparison (lowercase, collapse space)."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, _signature(a), _signature(b)).ratio()


@dataclass
class _Shown:
    agent_id: str
    signature: str
    shown_at: float


@dataclass
class InsightCurator:
    """The final authority before the HUD (Law 10, Chapter 8 §6).

    The engine APPENDS every earned insight into AgentResponse.insights and does
    not curate (see core/engine.py::_merge_responses). This class is the host's
    second, cross-agent gate: it consumes that list plus a short-term history and
    returns AT MOST ONE insight to render — or None (silence, the common case).
    """
    history: List[_Shown] = field(default_factory=list)
    history_limit: int = 32

    def curate(
        self,
        response: AgentResponse,
        now: Optional[float] = None,
    ) -> Optional[AgentInsight]:
        """Return the single insight to render this turn, or None for silence."""
        now = time.time() if now is None else now
        self._evict_expired_history(now)

        # 0. ERROR is the framework's failure channel, not a coaching insight.
        #    Pull it out here; the host routes it to a system tray, not the stage.
        candidates = [i for i in response.insights if i.type != InsightType.ERROR]
        if not candidates:
            return None

        # 1. Confidence floor — kill noise before ranking.
        candidates = [
            i for i in candidates
            if i.confidence >= MIN_CONFIDENCE.get(i.type, DEFAULT_FLOOR)
        ]
        if not candidates:
            return None

        # 2. Rank: urgency tier, then actionable (action_label present),
        #    then confidence. All descending.
        candidates.sort(key=self._rank_key, reverse=True)

        # 3. Within-turn dedup: one insight per agent_id (highest-ranked wins),
        #    then drop near-duplicate CONTENT from *different* agents so two
        #    observers saying the same thing don't both occupy a slot.
        candidates = self._dedup(candidates)

        # 4. Cross-turn suppression: skip anything we just showed (same source
        #    too recently) or any repeated coaching (same content too recently).
        for insight in candidates:
            if self._suppressed(insight, now):
                continue
            # 5. One-at-a-time: the first survivor IS the turn's single insight.
            self._remember(insight, now)
            return insight

        # Everything that survived the floor was a recent repeat — stay silent.
        return None

    # ----- ranking -------------------------------------------------------

    @staticmethod
    def _rank_key(i: AgentInsight) -> Tuple[int, int, float]:
        urgency = URGENCY_TIER.get(i.type, 0)
        actionable = 1 if i.action_label else 0   # actionable beats descriptive
        return (urgency, actionable, i.confidence)

    # ----- dedup ---------------------------------------------------------

    @staticmethod
    def _dedup(ranked: List[AgentInsight]) -> List[AgentInsight]:
        kept: List[AgentInsight] = []
        seen_agents: set = set()
        for i in ranked:
            if i.agent_id in seen_agents:
                continue  # one slot per source; ranked order means best survives
            if any(_similar(i.content, k.content) >= SIMILARITY_THRESHOLD for k in kept):
                continue  # near-duplicate topic already represented this turn
            kept.append(i)
            seen_agents.add(i.agent_id)
        return kept

    # ----- cross-turn suppression ---------------------------------------

    def _suppressed(self, insight: AgentInsight, now: float) -> bool:
        sig = _signature(insight.content)
        for shown in self.history:
            same_source = shown.agent_id == insight.agent_id
            if same_source and (now - shown.shown_at) < SOURCE_COOLDOWN_S:
                return True  # this observer just had the stage
            if (now - shown.shown_at) < REPEAT_COOLDOWN_S:
                if SequenceMatcher(None, sig, shown.signature).ratio() >= SIMILARITY_THRESHOLD:
                    return True  # repeated coaching — already said this recently
        return False

    def _remember(self, insight: AgentInsight, now: float) -> None:
        self.history.append(
            _Shown(agent_id=insight.agent_id,
                   signature=_signature(insight.content),
                   shown_at=now)
        )
        if len(self.history) > self.history_limit:
            self.history = self.history[-self.history_limit:]

    def _evict_expired_history(self, now: float) -> None:
        horizon = max(SOURCE_COOLDOWN_S, REPEAT_COOLDOWN_S)
        self.history = [s for s in self.history if (now - s.shown_at) <= horizon]
```

Wiring it into the turn loop — the curator owns the menu, the HUD honors
`expiry` as a TTL so the moment dissolves itself:

```python
curator = InsightCurator()   # one instance per session; it holds the short-term history

async def on_turn(self, response: AgentResponse):
    # System alerts never touch the coaching stage.
    for a in (i for i in response.insights if i.type == InsightType.ERROR):
        self.system_tray.flash(a.content)

    top = curator.curate(response)         # the second, cross-agent gate
    if top is None:
        return                             # the common, correct case: silence

    self.hud.present(
        text=top.content,
        zone=top.metadata.get("zone", ZONE_BY_TYPE[top.type]),
        ttl_seconds=top.expiry,            # expiry is the self-clean TTL (default 15s)
        button=top.action_label,           # None ⇒ no button
    )
```

Notes on the contract honored here:

- **`expiry` as TTL.** `AgentInsight.expiry` (default `15`, "Seconds to display")
  is passed straight to the HUD's `ttl_seconds`. The curator picks *what* shows;
  `expiry` guarantees it *un*-shows itself, returning the stage to silence with
  no further host action.
- **One-at-a-time is structural.** `curate` returns `Optional[AgentInsight]`, not
  a list. The type signature makes "the HUD shows at most one" unrepresentable to
  violate — there is no list to accidentally `for`-loop over.
- **Defaults are honest.** `confidence` defaults to `1.0` and is A-3-clamped, so
  the floor never throws; `action_label` defaults to `None`, so the actionable
  lever is a true presence check; `expiry` is S-1-coerced upstream, so the TTL is
  always a sane positive int.

---

### 5. Tie-in: Law 10 and Chapter 8

This pattern is the *implementation* of two things the playbook asserts but
locates on the host side:

- **Law 10 — "The insight list is a menu, not a render queue."** The engine hands
  the host `List[AgentInsight]` *precisely so it can curate to one*. The
  `InsightCurator` is the named component that reads the menu and orders exactly
  one dish (or declines). `for i in insights: hud.show(i)` — the canonical spam
  bug Law 10 warns against — is structurally impossible once `curate` returns an
  `Optional`, not a list.
- **Chapter 8 §6 — "the host owns curation and render."** Chapter 8 sketches the
  consumption loop and the fifth restraint layer (curate-to-one + dedup by
  `agent_id`). This pattern promotes that sketch into a **first-class, reusable,
  testable** component with cross-turn memory — the layer that Chapter 8 says the
  host *must* add on top of the framework's four (gate → confidence → cooldown →
  expiry).

The swarm is a reactive crowd of cheap observers; restraint is the product; and
the Insight Curator is the single host-side authority that enforces it at the
last possible moment — the final gate before the HUD.
## The Minimum Viable Swarm

"Build many cheap agents" is good advice that paralyzes a team on day one. So here is the concrete starting point — the first production-grade swarm for a conversational copilot. Three layers, twelve agents, only a few of which ever speak. Start here, then specialize.

```
┌─────────────────────────────────────────────────────────────┐
│ CORE OBSERVER LAYER  — cheap, every turn, mostly silent      │
│   question_detector        Detector   mini   emits event+queue│
│   objection_detector       Detector   mini   emits event+queue│
│   sentiment_monitor        Monitor    mini   writes variable  │
│   fact_extractor           Extractor  mini   writes facts (hi-pri)│
│   action_item_extractor    Extractor  mini   writes facts/queue│
├─────────────────────────────────────────────────────────────┤
│ REASONING LAYER — premium, EVENT/condition-gated, the voices │
│   question_response_coach  Advisor    4o     EVENT: question  │
│   objection_strategy_coach Advisor    4o     EVENT: objection │
│   meeting_momentum_coach   Advisor    4o     condition-gated  │
├─────────────────────────────────────────────────────────────┤
│ CONTROL LAYER — guards the experience & the budget           │
│   insight_curator          host-side  —      curate to ONE    │
│   repetition_guard         pattern    —      memory-based dedup│
│   silence_guard            Advisor    mini   SILENCE trigger  │
│   cost_monitor             callback   —      metrics/alerts   │
└─────────────────────────────────────────────────────────────┘
```

**How to read the layers**

- **Observer layer (5):** the senses. All cheap (`gpt-4o-mini` or deterministic), all run often, all (except a rare sentiment WARNING) **silent**. They turn raw transcript into a structured world-model — events, facts, variables, queues. This layer is where 90% of your agents will eventually live.
- **Reasoning layer (3):** the voices. Premium models, but they almost never run — each is gated by an event the observers raise or by accumulated state (`trigger_conditions`). On a quiet turn, this entire layer costs **zero**.
- **Control layer (4):** the conscience. Not "more intelligence" — *restraint infrastructure*. The `insight_curator` (host-side) enforces one visible insight; the `repetition_guard` (a memory pattern, not always a separate agent) stops repeated coaching; the `silence_guard` handles dead air gently; the `cost_monitor` (a callback handler) watches the budget and the insight rate.

**Why this is the *minimum* viable swarm:** drop any observer and the copilot goes blind to a signal; drop a reasoning agent and it can't act on one; drop the control layer and a good swarm still produces noise. It is also genuinely *viable* — each agent is a few lines of config, and the whole thing runs at near-zero cost on quiet turns.

**The growth path:** specialize the observer layer first (a `competitor_detector`, a `buying_signal_detector`, a `commitment_extractor`), then add reasoning agents only when an observer raises a signal nothing yet handles. You will add ten observers before you add a second voice — and that ratio is the formula working.
## The Golden Path — Build a Price-Objection Agent Suite in 30 Minutes

This is the worked build. By the end you have four agents that, together, watch a sales call and — only when a real price objection lands — surface **one** short, non-repeating coaching line to the rep. Everything else stays silent. That restraint is the product.

The suite is a textbook **detect-cheap → analyze-expensive cascade**: three `gpt-4o-mini` observers do the cheap watching and write structured signals to the blackboard; a single `gpt-4o` strategist wakes up *only* when an objection event fires, and a memory guard keeps it from repeating itself. Three of the four agents never touch the HUD at all.

Every config, schema field, condition operator, and channel below is the real v2.2 surface — grounded in `library/dynamic.py`, `library/schemas/*.json`, `core/agent.py`, `core/models.py`, `core/engine.py`, `core/blackboard.py`, and `core/conditions.py`. Where the host has to supply glue, it is flagged **[HOST GLUE]**.

---

### The cast

| Agent | Model | Trigger | Phase | Writes | HUD? |
|---|---|---|---|---|---|
| `price_objection_detector` | `gpt-4o-mini` | `turn_based` | 1 | event `price_objection_raised` + queue push | **No** |
| `deal_fact_extractor` | `gpt-4o-mini` | `turn_based` | 1 | facts (`budget`/`urgency`/`stakeholder`/`competitor`), priority 10 | **No** |
| `price_objection_strategist` | `gpt-4o` | `event` (subscribes detector's event) | 2 | exactly one insight + writes its own memory | **Yes (≤1)** |
| `repetition_guard` | — (no LLM) | — | host pre-filter | reads/writes strategist memory | No |

A note on the fourth agent: `repetition_guard` is **not a separate `DynamicAgent`**. Cross-turn de-duplication is implemented inside the strategist by *reading its own memory* (the last advice fingerprint) and *writing it back* — the MR-1 memory read-path. We show both the in-agent recipe (zero host glue, recommended) and, as an alternative, a true standalone guard that needs **[HOST GLUE]**. Pick one.

---

### The blackboard schema this suite uses

The shared world-model these four agents read and write. Naming follows the `domain.detail` convention.

**Events** (transient, dispatched Phase 1 → Phase 2):
- `price_objection_raised` — emitted by the detector; payload `{ "quote": "<verbatim rep/prospect line>", "severity": "soft" | "hard" }`. The strategist subscribes to this name.

**Queues** (FIFO work log):
- `objections` — each detected objection pushed as `{ "quote": "...", "severity": "..." }`. Lets the host render an objection history panel and lets conditions test "has anything been raised".

**Facts** (deduplicated by `(type, key)`, conflict resolved by emitting-agent priority then confidence — INV-9):
- `budget` (key `budget.primary`) — value e.g. `"$40k ceiling"`.
- `urgency` (key `urgency.timeline`) — value e.g. `"end of quarter"`.
- `stakeholder` (key per role, e.g. `stakeholder.economic_buyer`) — value e.g. `"VP Finance"`.
- `competitor` (key per name, e.g. `competitor.acme`) — value e.g. `"evaluating Acme"`.

The extractor runs at **priority 10** so its facts are canonical: if any other agent ever emits a conflicting `budget`/`urgency` fact, the extractor's wins regardless of confidence (the engine stamps `fact.priority = agent.priority` at merge time, then `Blackboard.add_fact` resolves `(priority, confidence)` — `core/engine.py` `_merge_responses`, `core/blackboard.py` `add_fact`).

**Memory** (agent-private, per `agent_id`):
- `memory_price_objection_strategist` — `{ "last_advice_topic": "<short tag>", "last_quote": "<the objection it last coached on>" }`. This is the repetition guard's state. Read via `shared_state["memory_price_objection_strategist"]` (synced from the blackboard by the engine every phase — INV-14).

**Variables** (optional, for HUD/host):
- `deal.stage` — host may set/read; the strategist can read it via `{{ blackboard.variables['deal.stage'] }}` for tone.

---

### Schema files: pick the right gate for each job

Three of these agents must stay silent on the HUD. The silence gate in `dynamic.py` (`evaluate`, the `should_speak` block) gives you three structural options — choose deliberately:

1. **`check_field` present** (e.g. `has_insight`) → the boolean drives speech. Missing/false ⇒ silence. This is `default_v2`.
2. **`root_key` present, no `check_field`** → presence of a non-empty root object is the gate.
3. **Neither** → defaults to **silence** unless you set `"speak_without_gate": true`. (A-1/INV-11. Don't do this here.)

The detector and extractor must emit **events/queues/facts but never an insight**. The trick: use a schema whose `check_field` gate stays `false`, while events/queue/facts are parsed from the **result root** regardless of the gate (steps 6–9 in `evaluate` run unconditionally, independent of `should_speak`). So we reuse `default_v2.json` and instruct the model to keep `has_insight=false`.

> **Why this is safe:** in `dynamic.py`, the insight is only appended when `should_speak` is true (step 2–3). Events (step 6), queue pushes (step 8), and facts (step 9) are extracted from `result` outside that gate. A `has_insight:false` response with a populated `events`/`facts`/`queue_pushes` array produces **zero insights and full coordination output**. This is the canonical "detector emits signal, not noise" pattern.

#### Schema A — `default_v2.json` (SHIPS WITH THE FRAMEWORK — used by detector + extractor)

Already in `library/schemas/default_v2.json`. Its mapping (verbatim):

```json
{
  "mapping": {
    "root_key": null,
    "check_field": "has_insight",
    "content_field": "content",
    "type_field": "type",
    "confidence_field": "confidence",
    "metadata_field": "metadata",
    "events_field": "events",
    "variable_updates_field": "variable_updates",
    "queue_field": "queue_pushes",
    "facts_field": "facts",
    "memory_field": "memory_updates",
    "state_field": null
  }
}
```

The detector and extractor both set `output_format: "default_v2"`. They never set `has_insight:true`, so they never reach the HUD — but their `events`, `queue_pushes`, and `facts` flow to the blackboard.

#### Schema B — `coaching_v2.json` (NEW FILE — used by the strategist)

The strategist needs the gated insight contract **plus** `expiry`/`action_label` pass-through (S-1) so it can ship a self-expiring, actionable HUD card, **plus** the ability to write its own memory (the repetition fingerprint). `dynamic.py` reads `expiry`/`action_label` from `mapping.get("expiry_field","expiry")` / `mapping.get("action_label_field","action_label")` — so with the default field names, the model just emits `expiry` and `action_label` at the insight root and they pass through `_coerce_expiry` / `_coerce_action_label`.

Create `library/schemas/coaching_v2.json`:

```json
{
  "id": "coaching_v2",
  "description": "Gated single-insight coaching schema with expiry + action_label pass-through and private memory.",
  "instruction": "\nIMPORTANT: Return a valid JSON object. Emit AT MOST ONE coaching insight, and ONLY if it is genuinely useful right now.\n\nOUTPUT FORMAT:\n{\n    \"has_insight\": boolean,        // false = stay silent (PREFERRED when unsure)\n    \"type\": \"suggestion\" | \"warning\" | \"opportunity\",\n    \"content\": \"One short coaching line for the rep (<= 18 words).\",\n    \"confidence\": 0.0-1.0,\n    \"expiry\": 20,                  // seconds the card stays on the HUD\n    \"action_label\": \"Try this\",   // optional button text, omit if none\n    \"memory_updates\": {            // your private scratchpad (repetition guard)\n        \"last_advice_topic\": \"<short tag, e.g. 'anchor-on-value'>\",\n        \"last_quote\": \"<the objection you just coached on>\"\n    }\n}\n\nRULES:\n- Set has_insight=false if your advice would repeat last_advice_topic in YOUR MEMORY.\n- Never emit more than one insight.\n- Keep content punchy; the rep reads it mid-call.\n",
  "mapping": {
    "root_key": null,
    "check_field": "has_insight",
    "content_field": "content",
    "type_field": "type",
    "confidence_field": "confidence",
    "expiry_field": "expiry",
    "action_label_field": "action_label",
    "memory_field": "memory_updates",
    "metadata_field": "metadata",
    "state_field": null
  }
}
```

> **On the fourth agent:** because `coaching_v2` instructs the model to set `has_insight=false` when its advice would repeat `last_advice_topic` (read from `[YOUR MEMORY]`, which the engine populates from `shared_state["memory_<id>"]`), the strategist **is** its own repetition guard. The `memory_updates` it returns are merged to `blackboard.memory["price_objection_strategist"]` (engine `_merge_responses`) and re-synced into `shared_state` next turn (INV-14). No separate agent, no host glue.

---

### The four agent configs (real `DynamicAgent` config dicts)

These are the dicts you pass to `DynamicAgent(config_dict)`. Field names are exactly what `dynamic.py.__init__` reads: `id`, `name`, `model`, `text` (the system prompt), `output_format`, `trigger_config` (`mode`, `cooldown`, `priority`, `subscribed_events`), and top-level `trigger_conditions`.

#### 1. `price_objection_detector` — cheap, silent, event-only

```json
{
  "id": "price_objection_detector",
  "name": "Price Objection Detector",
  "model": "gpt-4o-mini",
  "output_format": "default_v2",
  "trigger_config": {
    "mode": "turn_based",
    "cooldown": 8,
    "priority": 0
  },
  "text": "You are a fast detector on a live sales call. Your ONLY job is to spot when the PROSPECT raises a PRICE or BUDGET objection (too expensive, can't afford, need a discount, not in budget, sticker shock). You do NOT give advice. Keep has_insight=false ALWAYS.\n\nIf and only if a price objection is present in the latest turns, emit:\n- one event named 'price_objection_raised' with payload {\"quote\": \"<verbatim line>\", \"severity\": \"soft\"|\"hard\"}\n- one queue_push to 'objections' with {\"quote\": \"<verbatim line>\", \"severity\": \"soft\"|\"hard\"}\nIf there is NO price objection, return {\"has_insight\": false} and nothing else."
}
```

Note: `subscribed_events` is omitted, so this stays a pure `turn_based` Phase-1 agent (the engine only auto-adds `TriggerType.EVENT` when `subscribed_events` is non-empty — `dynamic.py` lines 80–81).

What a positive turn returns from the LLM (parsed by `default_v2` mapping):

```json
{
  "has_insight": false,
  "events": [
    {"name": "price_objection_raised", "payload": {"quote": "Honestly that's way over our budget.", "severity": "hard"}}
  ],
  "queue_pushes": {
    "objections": [{"quote": "Honestly that's way over our budget.", "severity": "hard"}]
  }
}
```

`has_insight:false` ⇒ no HUD card. The event and queue push still land on the blackboard.

#### 2. `deal_fact_extractor` — cheap, silent, canonical facts (priority 10)

```json
{
  "id": "deal_fact_extractor",
  "name": "Deal Fact Extractor",
  "model": "gpt-4o-mini",
  "output_format": "default_v2",
  "trigger_config": {
    "mode": "turn_based",
    "cooldown": 12,
    "priority": 10
  },
  "trigger_conditions": {
    "mode": "any",
    "rules": [
      {"queue": "objections", "op": "not_empty"},
      {"meta": "turn_count", "op": "mod", "value": 3, "result": 0}
    ]
  },
  "text": "You extract durable deal facts from a live sales call. You NEVER give advice. Keep has_insight=false ALWAYS.\n\nExtract any of these as facts (only when clearly stated):\n- budget   (key 'budget.primary')           value: the budget/price ceiling stated\n- urgency  (key 'urgency.timeline')          value: the deadline / time pressure\n- stakeholder (key 'stakeholder.<role>')     value: name/role of a decision-maker\n- competitor  (key 'competitor.<name>')      value: a competitor being evaluated\n\nReturn facts as: {\"facts\": [{\"type\": \"budget\", \"key\": \"budget.primary\", \"value\": \"$40k ceiling\", \"confidence\": 0.9}, ...]}.\nIf nothing durable is stated, return {\"has_insight\": false}."
}
```

The `trigger_conditions` (gating, evaluated by `core/conditions.py`) say: run if the `objections` queue is non-empty **OR** every 3rd turn (`turn_count % 3 == 0`). This is the cheap-precondition gate that keeps the extractor from burning a call on every turn while still catching facts around objections. Operators `not_empty` and `mod` are real (`conditions.py` `_compare`); `mod` reads `value` as divisor and `result` as the expected remainder.

Priority 10 makes its facts canonical (F-1 / INV-9). Example emission:

```json
{
  "has_insight": false,
  "facts": [
    {"type": "budget", "key": "budget.primary", "value": "$40k ceiling", "confidence": 0.9},
    {"type": "urgency", "key": "urgency.timeline", "value": "end of quarter", "confidence": 0.8}
  ]
}
```

#### 3. `price_objection_strategist` — premium, event-triggered, exactly one insight

```json
{
  "id": "price_objection_strategist",
  "name": "Price Objection Strategist",
  "model": "gpt-4o",
  "output_format": "coaching_v2",
  "trigger_config": {
    "mode": "event",
    "cooldown": 20,
    "priority": 5,
    "subscribed_events": ["price_objection_raised"]
  },
  "trigger_conditions": {
    "mode": "all",
    "rules": [
      {"queue": "objections", "op": "not_empty"}
    ]
  },
  "text": "You are a senior sales coach. You ONLY run when a price objection has just been raised. Read the latest objection (in the queue and the transcript) and the deal facts on the blackboard:\n- Budget ceiling: {{ blackboard.get_fact('budget','budget.primary').value if blackboard.has_fact('budget','budget.primary') else 'unknown' }}\n- Timeline: {{ blackboard.get_fact('urgency','urgency.timeline').value if blackboard.has_fact('urgency','urgency.timeline') else 'unknown' }}\n\nYOUR MEMORY shows your last coaching ('last_advice_topic', 'last_quote'). DO NOT repeat the same angle twice in a row: if your new advice would reuse last_advice_topic, set has_insight=false.\n\nIf you DO coach, emit exactly ONE short line (<=18 words), set an expiry of 20s and an action_label, and write memory_updates with the new last_advice_topic and last_quote."
}
```

`mode: "event"` plus `subscribed_events: ["price_objection_raised"]` is the wiring. Even though `mode` already sets `TriggerType.EVENT`, the non-empty `subscribed_events` would auto-add it anyway (belt and suspenders). Because it's an EVENT agent, it is **excluded from Phase 1** (Phase 1 routes only matching trigger types — `_is_eligible` checks `trigger_type in agent.config.trigger_types`; the turn's trigger is `turn_based`). It only runs in Phase 2, and only if the detector actually emitted `price_objection_raised`.

A coaching turn returns:

```json
{
  "has_insight": true,
  "type": "suggestion",
  "content": "Reframe on ROI: tie the price to the end-of-quarter deadline they just named.",
  "confidence": 0.86,
  "expiry": 20,
  "action_label": "Anchor on value",
  "memory_updates": {"last_advice_topic": "anchor-on-value", "last_quote": "way over our budget"}
}
```

That yields exactly one `AgentInsight` (`expiry=20`, `action_label="Anchor on value"` via S-1 pass-through), and writes the fingerprint to memory.

#### 4. `repetition_guard` — the in-agent recipe (recommended) vs. standalone (alternative)

**Recommended (already done, zero glue):** the guard *is* the strategist's memory loop. Turn N writes `last_advice_topic`; the engine merges it to `blackboard.memory["price_objection_strategist"]`; turn N+1's `_sync_state_to_legacy` copies it into `shared_state["memory_price_objection_strategist"]`; `dynamic.py.evaluate` loads it into `[YOUR MEMORY]`; the prompt rule suppresses a repeat by setting `has_insight=false`. This is MR-1 cross-turn memory working exactly as designed.

**Alternative (standalone agent):** if you want a *structural* guard rather than a prompt rule, add an `event`-triggered guard that subscribes the same event, runs at higher priority than the strategist, and uses a `trigger_conditions` memory check to short-circuit. But note: conditions can only **suppress the guard itself**, not the strategist — so a true standalone guard needs **[HOST GLUE]**: the host must read `final_response.insights`, compare each strategist insight's topic against `blackboard.get_memory("price_objection_strategist")["last_advice_topic"]`, and drop duplicates before rendering. Config skeleton if you go this route:

```json
{
  "id": "repetition_guard",
  "name": "Repetition Guard",
  "model": "gpt-4o-mini",
  "output_format": "default_v2",
  "trigger_config": {
    "mode": "event",
    "cooldown": 5,
    "priority": 9,
    "subscribed_events": ["price_objection_raised"]
  },
  "trigger_conditions": {
    "mode": "all",
    "rules": [
      {"memory": "last_advice_topic", "op": "present"}
    ]
  },
  "text": "You guard against repeated coaching. Read YOUR MEMORY's last_advice_topic. If the incoming objection would draw the same advice, emit variable_updates {\"coaching.suppress\": true}; else {\"coaching.suppress\": false}."
}
```

The `{"memory": "last_advice_topic", "op": "present"}` rule reads **this agent's own** memory (`conditions.py` `_get_value`, `memory` branch — own-memory access when there's no `.`). The host then honors `coaching.suppress`. **The in-agent recipe is simpler and is what we ship.**

---

### The event wiring (detector emits → strategist subscribes)

```
TURN (trigger_type = turn_based)
        │
   ┌────┴───────────── PHASE 1 (parallel, snapshot-isolated) ─────────────┐
   │  price_objection_detector  (turn_based)  ── emits Event ─────────┐    │
   │  deal_fact_extractor       (turn_based, cond) ── writes Facts    │    │
   └─────────────────────────────────────────────────────────────────┼────┘
                                                                      │
              engine collects events, blackboard.emit_event(...)      │
              event name = "price_objection_raised"                   │
                                                                      ▼
   ┌──────────── PHASE 2 (only if events emitted, max_phases>=2) ──────────┐
   │  get_event_subscribers(["price_objection_raised"])                    │
   │     → price_objection_strategist (mode=event, subscribed) ── insight  │
   │       (re-sync memory_<id> into shared_state first — INV-14)          │
   └───────────────────────────────────────────────────────────────────────┘
        │
   merge (ascending priority), clear events, return AgentResponse
```

The contract, line by line in `core/engine.py`:
- Phase 1 responses' `.events` are collected (`all_events`) and applied via `blackboard.emit_event` (lines ~328–333).
- If `all_events` and `max_phases >= 2`, the engine re-syncs memory into `shared_state` (INV-14), sets `context.trigger_type = EVENT`, `phase = 2`, and calls `get_event_subscribers(event_names)` (lines ~346–366).
- `get_event_subscribers` returns only agents that have `price_objection_raised` in `subscribed_events` **and** `TriggerType.EVENT` in `trigger_types` (else it warns once and skips — E-6).
- Phase-2 eligibility also re-checks `trigger_conditions` (`_is_eligible_for_phase2`).
- After Phase 2, the engine restores `trigger_type`/`phase` in a `finally` (E-1/INV-12) so the next turn isn't corrupted.

**[HOST GLUE] required for the cascade to fire at all:** the host must construct the `AgentEngine` with `max_phases=2` (the default), `register_agent(...)` all four, and call `process_turn(context, trigger_type=TriggerType.TURN_BASED)` each turn. Phase 2 is engine-internal once events exist — you do not invoke it.

---

### Turn-by-turn trace: one price objection

Setup: rep and prospect have been talking; on an earlier turn the prospect said *"We're trying to wrap this up before end of quarter."* The extractor already wrote `urgency = "end of quarter"`. `deal.stage = "negotiation"`.

**Turn 7 — the objection lands.** Latest transcript: `PROSPECT: Honestly, $52k a year is way over our budget.`

`process_turn(context, trigger_type=TURN_BASED)`:

*Phase 1* (snapshot taken; detector + extractor run in parallel against the same frozen blackboard):
- `price_objection_detector` (cooldown ok, turn_based) → LLM returns `has_insight:false` + event `price_objection_raised {quote:"...way over our budget", severity:"hard"}` + queue push to `objections`. **No insight.** Engine collects the event.
- `deal_fact_extractor` (condition: `objections` not_empty was false *in the snapshot* — but `turn_count % 3` → 7%3≠0, so it ran only if the queue was already non-empty from a prior turn; assume it ran on the mod gate on turn 6). On turn 7 the `mod` rule is false and the snapshot queue was empty at phase start, so **extractor is skipped** (`conditions_not_met`, `on_agent_skipped` fires). Facts already on board from before stand.

Merge: detector's event applied to blackboard; queue `objections` now `[{quote,severity}]`. No insights yet.

*Phase 2* (events present, `max_phases=2`):
- Engine re-syncs memory → `shared_state["memory_price_objection_strategist"]` (empty so far — first objection of the call).
- `get_event_subscribers(["price_objection_raised"])` → `price_objection_strategist` (has EVENT + subscription). Eligibility: `trigger_conditions` `objections not_empty` → **true** (queue was filled in Phase 1, and Phase 2 reads the merged board). Runs.
- Strategist (`gpt-4o`) reads the objection from queue+transcript, sees `urgency = "end of quarter"` via Jinja `blackboard.get_fact(...)`, `[YOUR MEMORY]` empty → no repeat risk. Returns:
  - `has_insight:true`, content `"Reframe on ROI — tie the cost to the end-of-quarter deadline they need to hit."`, `type:"suggestion"`, `expiry:20`, `action_label:"Anchor on value"`, `memory_updates:{last_advice_topic:"anchor-on-value", last_quote:"way over our budget"}`.

Merge: one `AgentInsight` appended to `final_response.insights`; `memory_updates` merged to `blackboard.memory["price_objection_strategist"]`. Events cleared.

**What the rep sees on turn 7:** a single HUD card — *"Reframe on ROI — tie the cost to the end-of-quarter deadline they need to hit."* with an "Anchor on value" button, auto-expiring after 20s. One card. From four agents. That is the whole point.

**Turn 8 — prospect pushes again on price.** `PROSPECT: I just don't see how we justify that number.`

*Phase 1:* detector fires again → new `price_objection_raised` event + queue push (queue now length 2). Extractor: `objections not_empty` → **true**, runs, may refine `budget.primary = "$52k/yr, over budget"` (priority 10, becomes canonical).

*Phase 2:* strategist eligible again (cooldown 20s — **[NOTE]** if turn 8 is within 20s of turn 7, `BaseAgent.process` cooldown gates it out and **nothing is emitted** — silence by design). Assume >20s passed. Now `[YOUR MEMORY]` shows `last_advice_topic:"anchor-on-value"`. The prompt rule says: if the new advice repeats that angle, `has_insight=false`. The model judges its best move is *still* value-anchoring → returns `has_insight:false`. **No second card.** The repetition guard worked — the rep is not nagged with the same advice twice.

If instead the model finds a genuinely new angle (e.g. payment-terms split), it emits one new card and updates `last_advice_topic:"payment-terms"`.

**Net over two objection turns:** exactly one (occasionally two, never duplicate) coaching cards; a populated `objections` queue the host can render as history; canonical `budget`/`urgency` facts; zero HUD noise from the two cheap observers.

---

### The 30-minute build checklist

1. **(2 min)** Confirm framework v2.2 and that `library/schemas/default_v2.json` exists. Construct `AgentEngine(api_key=..., max_phases=2)`. **[HOST GLUE]**
2. **(3 min)** Create `library/schemas/coaching_v2.json` exactly as above (gated `check_field: has_insight`, `expiry_field`, `action_label_field`, `memory_field`).
3. **(4 min)** Write the `price_objection_detector` config dict (`default_v2`, `turn_based`, cooldown 8). Prompt: detect price objection → emit `price_objection_raised` event + push to `objections` queue, `has_insight` always false.
4. **(4 min)** Write the `deal_fact_extractor` config (`default_v2`, `turn_based`, **priority 10**, `trigger_conditions` = `objections not_empty` OR `turn_count mod 3`). Prompt: extract `budget`/`urgency`/`stakeholder`/`competitor` as facts, never an insight.
5. **(5 min)** Write the `price_objection_strategist` config (`coaching_v2`, `mode:"event"`, `subscribed_events:["price_objection_raised"]`, cooldown 20, priority 5, `trigger_conditions` = `objections not_empty`). Prompt: read queue+facts via Jinja, read `[YOUR MEMORY]`, emit ≤1 line, set `expiry`/`action_label`, write `last_advice_topic`/`last_quote` to `memory_updates`. **This is also your repetition guard.**
6. **(2 min)** Decide on the guard: keep the in-agent memory recipe (default — done in step 5) OR add the standalone `repetition_guard` and wire the host to honor `coaching.suppress`. **[HOST GLUE if standalone]**
7. **(3 min)** `DynamicAgent(cfg)` for each; `engine.register_agent(...)` in this order: detector, extractor, strategist (registration order is the merge tie-breaker within equal priority). **[HOST GLUE]**
8. **(3 min)** Per turn: build `AgentContext` (`session_id`, `recent_segments`, optional `user_context`/`language_directive`), then `await engine.process_turn(context, trigger_type=TriggerType.TURN_BASED)`. **[HOST GLUE]**
9. **(2 min)** Render `final_response.insights` on the HUD (respect each insight's `expiry` and `action_label`). Optionally render the `objections` queue and `budget`/`urgency` facts in a side panel. **[HOST GLUE]**
10. **(2 min)** Smoke test: feed a transcript with a clear price objection. Assert exactly one insight on the objection turn, zero on a neutral turn, and no duplicate insight when the same objection repeats inside the strategist cooldown / same advice topic.

**Total ≈ 30 min.** The only code you write is one schema file and the host loop; the four agents are pure config.

---

### Things to flag before you ship

- **Cooldown vs. silence:** the strategist's 20s cooldown (`BaseAgent.process`) is a hard gate *before* the LLM runs — it produces silence, not a deferred card. Tune it to your call cadence.
- **Detector substring caution:** if you ever move objection detection to the engine's `check_keyword_triggers` helper, note it's case-insensitive **substring** matching (E-8) — `"car"` matches `"scared"`. Here we use an LLM detector, so this doesn't bite, but don't swap in keyword triggers naively.
- **Fact priority is host-owned when you call `add_fact` directly:** the priority-10 canonicality only holds for facts that flow through `process_turn` merge (engine stamps `fact.priority`). If the host writes facts straight to the blackboard, it owns `fact.priority` (default 0).
- **`expiry`/`action_label` pass-through depends on the model actually emitting them.** Bad/missing values are coerced safely (`_coerce_expiry` → default 15s; `_coerce_action_label` → None), so a sloppy model degrades gracefully rather than crashing the insight.
- **Phase-2 events are recorded but not re-dispatched** — the strategist can't trigger a Phase-3 cascade. If you need chained analysis, do it within the strategist or via a host-driven second `process_turn`.
## Testing Templates — Prove It Works (Especially the Silence)

> **Thesis recap.** XUBB AGENTS is a reactive swarm of cheap observers. Restraint
> is the product. The HUD is worth more for what it *doesn't* say than for what it
> does. So the most important test you will ever write for an agent is not "does it
> produce the right insight?" — it is **"does it correctly produce NOTHING?"**
>
> This chapter gives you transcript-based test templates grounded in how *this
> repo's* tests actually run: you build an `AgentContext` out of
> `TranscriptSegment`s, mock the one external dependency (`LLMClient.generate_json`),
> run the agent, and assert on the channels of the returned `AgentResponse` —
> including the empty ones.

---

### How an agent actually runs (and what you mock)

Before the templates, anchor on the real execution path, because the templates
assert against exactly these surfaces.

1. The engine injects an LLM client onto the agent (`agent.llm`). In tests you
   replace it with a fake.
2. `BaseAgent.process()` does the gatekeeping (trigger-type match, cooldown) and
   then calls `evaluate()`. For unit tests you almost always call `evaluate()`
   **directly** — it skips cooldown/trigger bookkeeping and exercises the agent's
   brain. (Call `process()` only when the behavior under test *is* the cooldown or
   trigger-type gate.)
3. `DynamicAgent.evaluate()` builds the prompt, calls
   `await self.llm.generate_json(model=..., messages=...)`, and parses the returned
   dict into an `AgentResponse` according to its **schema mapping**.
4. The schema mapping is the whole game for silence. The parser decides
   `should_speak` from the mapping (`core/llm.py` is just transport; the *gate*
   lives in `library/dynamic.py`):
   - **`check_field` present** (e.g. `default_v2` → `has_insight`): the boolean
     gate drives it. Missing/false ⇒ **silence**.
   - **`root_key` present, no `check_field`** (e.g. `v2_raw` → `insight`): a
     non-empty root object is the gate. Empty/absent ⇒ **silence**.
   - **neither** (a hand-rolled custom schema): default policy is **silence**
     unless the author sets `speak_without_gate: true`.

**The only thing you mock is `generate_json`.** It is an `async` method that
returns a parsed `dict` (or `None`). Everything downstream — gating, confidence
clamping, event/fact/queue extraction — is pure local code you *want* to exercise
for real.

The canonical fake, lifted straight from `tests/test_dynamic_agent.py`:

```python
class FakeLLM:
    """Stand-in for the engine-injected LLM client. generate_json returns a
    pre-canned dict, mimicking a parsed JSON response — no network."""
    def __init__(self, result):
        self._result = result
        self.calls = []

    async def generate_json(self, model=None, messages=None, **kwargs):
        self.calls.append({"model": model, "messages": messages})
        return self._result
```

For engine-level / multi-agent tests, the repo instead uses a `MockAgent`
subclass of `BaseAgent` with an injectable `response_fn(context, agent) ->
AgentResponse` (see `tests/test_engine.py`). Use `FakeLLM` + `DynamicAgent` when
you're testing *parsing/gating*; use `MockAgent` when you're testing *engine
orchestration* (event routing, priority, cooldown).

---

### The Silence Test — the test that protects the thesis

A reactive swarm that speaks on every turn is worse than no swarm at all: it
trains the operator to ignore the HUD. Every other guarantee in this codebase —
cooldowns, gates, the `has_insight` boolean, the gate-less default-to-silence
policy — exists to make silence the *default* and speech the *exception*. **If you
don't test the silence path, you are not testing the product.**

There are three concrete ways an agent stays silent, and each has a distinct
assertion. Memorize these — every silence test is one of them.

| # | Silence mechanism | What the LLM returns (mock) | The assertion |
|---|---|---|---|
| 1 | **Gated, gate says no** (`check_field`, e.g. `has_insight=false`) | `{"has_insight": False, ...}` | `assert resp.insights == []` |
| 2 | **Root-keyed, empty root** (`root_key`, no `check_field`) | `{"insight": {}}` | `assert resp.insights == []` |
| 3 | **Gate-less + rootless, no opt-in** (custom schema, INV-11) | `{"content": "...", "type": "..."}` | `assert resp.insights == []` |

The crucial subtlety in case 1: an agent can **emit signal while staying silent on
the HUD**. `has_insight=False` suppresses the *insight*, but the same response may
still carry `events`, `facts`, `variable_updates`, and `queue_pushes`. That is the
intended shape of a Detector or Extractor — it changes shared state and fires
events for other agents without ever interrupting the human. So the canonical
silence assertion for those archetypes is the **paired** form:

```python
# The agent did its job WITHOUT speaking:
assert resp.insights == []          # produced NOTHING on the HUD
assert len(resp.events) == 1        # but DID emit the coordination signal
```

Why `== []` and not `not resp.insights`? Because an empty-list assertion fails
loudly with a readable diff when an agent regresses into chattiness — it prints
the exact unwanted insight. That diagnostic is the difference between catching HUD
spam in CI and shipping it.

One more guard worth a dedicated test: the **gate-less misconfiguration**. A
custom schema whose *prose* tells the model to emit `has_insight` but whose
*mapping* forgets to wire `check_field` silently loses the gate. The repo asserts
the load-time warning fires (`test_warning_fires_on_gate_field_in_instruction_but_no_check_field`).
If you author custom schemas, copy that test — a lost gate is invisible until it
spams production.

---

### Per-archetype test templates

The four archetypes differ almost entirely in **which response channels they are
allowed to touch**, and therefore in what your test asserts is present vs. empty.
The "Expected SILENCE" column is not optional — it is the load-bearing column.

> Legend: `variable_updates` = blackboard var writes; `queue_pushes` = work-queue
> appends; `events` = coordination signals; `facts` = deduped knowledge;
> `insights` = HUD output. "—" means *assert empty*.

| Archetype | Input transcript (mock returns) | Expected `variable_updates` | Expected `queue_pushes` | Expected `events` | Expected `facts` | Expected `insights` | **Expected SILENCE** |
|---|---|---|---|---|---|---|---|
| **Detector** (sees a thing, signals others; never speaks) | A turn containing the trigger (e.g. a question). Mock: `{"has_insight": false, "events":[{"name":"question_detected","payload":{...}}]}` | — | — | **1** event, `name=="question_detected"`, `source_agent==agent.id`, `timestamp` session-relative | — | **— (none)** | **YES — primary.** `assert resp.insights == []` while `assert len(resp.events)==1`. A Detector that produces an insight is a bug. |
| **Extractor** (pulls structured facts into the blackboard) | A turn stating a fact (e.g. "budget is 50k"). Mock: `{"has_insight": false, "facts":[{"type":"budget","key":"primary","value":50000,"confidence":0.9}]}` | optional | optional | optional | **1** fact, `type=="budget"`, `key=="primary"`, `value==50000`, `source_agent==agent.id` | **— (none)** | **YES — primary.** `assert resp.insights == []`. Extraction is a state change, not an interruption. Assert the fact landed AND the HUD stayed quiet. |
| **Advisor** (the only archetype whose *job* is to speak — rarely) | Two cases. Quiet: `{"has_insight": false}`. Speak: `{"has_insight": true, "type":"warning", "content":"...", "expiry":30}` | — | — | — | — | **0 in the quiet case; exactly 1** in the speak case (assert `type`, `content`, `expiry`) | **YES — and this is the default case.** The quiet-turn test (`has_insight=false ⇒ 0 insights`) is the *more important* of the two. Most turns must be silent. |
| **Monitor** (interval/silence-triggered watcher; tracks state, speaks only on threshold breach) | Below threshold: `{"has_insight": false, "variable_updates":{"idle_turns": 3}}`. Breach: `{"has_insight": true, "type":"opportunity", "content":"..."}` | **1** (`idle_turns` updated) in the below-threshold case | — | optional | — | **0 below threshold; 1** on breach | **YES — primary.** A Monitor must update its tracked variable *without speaking* on every quiet tick. Assert `variable_updates` changed but `insights == []`. |

Reading the table the right way: for **Detector, Extractor, and Monitor**, the
"speak" column is mostly empty and the **SILENCE column is the spec**. Only the
**Advisor** is allowed to put text on the HUD — and even there, the test you must
not skip is the *quiet* one.

---

### Runnable example 1 — Detector: emits an event, says NOTHING

This is the archetypal silence test. The agent detects a customer question, fires
a `question_detected` event for downstream agents to react to, and **produces zero
insights**. We use the real `DynamicAgent` with the `default_v2` schema (whose
gate is `has_insight`), mock `generate_json` to return a detection with
`has_insight: false`, and assert the paired contract.

```python
import asyncio
import pytest
from xubb_agents.library.dynamic import DynamicAgent
from xubb_agents.core.models import AgentContext, TranscriptSegment, TriggerType


class FakeLLM:
    def __init__(self, result):
        self._result = result
        self.calls = []
    async def generate_json(self, model=None, messages=None, **kwargs):
        self.calls.append({"model": model, "messages": messages})
        return self._result


def make_detector(result):
    agent = DynamicAgent({
        "id": "question_detector",
        "name": "Question Detector",
        "text": "Emit a 'question_detected' event when the customer asks something. Never speak.",
        "output_format": "default_v2",   # gate = has_insight
        "trigger_config": {"cooldown": 0},
    })
    agent.llm = FakeLLM(result)
    return agent


def test_detector_emits_event_and_stays_silent():
    # The customer asks a question. The detector signals — but must not speak.
    context = AgentContext(
        session_id="sess_detector",
        recent_segments=[
            TranscriptSegment(speaker="AGENT",    text="How can I help?",        timestamp=10.0),
            TranscriptSegment(speaker="CUSTOMER", text="What does this cost?",    timestamp=12.0),
        ],
        trigger_type=TriggerType.TURN_BASED,
    )

    # The LLM "detects" the question: it fires an event, with has_insight=False.
    llm_result = {
        "has_insight": False,
        "events": [
            {"name": "question_detected", "payload": {"text": "What does this cost?"}}
        ],
    }
    agent = make_detector(llm_result)

    resp = asyncio.run(agent.evaluate(context))

    # --- The coordination signal fired ---
    assert len(resp.events) == 1
    evt = resp.events[0]
    assert evt.name == "question_detected"
    assert evt.payload == {"text": "What does this cost?"}
    assert evt.source_agent == "question_detector"
    # A-2 / INV-13: timestamp is session-relative (max segment ts), never wall-clock.
    assert evt.timestamp == 12.0
    assert evt.timestamp < 1_000_000_000

    # --- THE SILENCE TEST: produced NOTHING on the HUD ---
    assert resp.insights == []
```

What this proves: the Detector does real work (an event other agents subscribe to)
*through a silent response*. If a future change makes the gate leak — say someone
swaps the schema for a gate-less one — `resp.insights == []` fails with the exact
unwanted insight printed.

---

### Runnable example 2 — Advisor: silent by default, one insight on breach

The Advisor is the only archetype allowed on the HUD, so it gets the most rigorous
silence test: we assert that `has_insight=false` yields **zero** insights, and only
then that `has_insight=true` yields **exactly one** insight with the expected type
and expiry. Both halves use the same agent + `default_v2` schema; only the mocked
LLM result changes.

```python
import asyncio
from xubb_agents.library.dynamic import DynamicAgent
from xubb_agents.core.models import (
    AgentContext, TranscriptSegment, TriggerType, InsightType,
)


class FakeLLM:
    def __init__(self, result):
        self._result = result
    async def generate_json(self, model=None, messages=None, **kwargs):
        return self._result


def make_advisor(result):
    agent = DynamicAgent({
        "id": "objection_advisor",
        "name": "Objection Advisor",
        "text": "Warn the rep only when the customer raises a hard objection. Otherwise stay silent.",
        "output_format": "default_v2",   # gate = has_insight
        "trigger_config": {"cooldown": 0},
    })
    agent.llm = FakeLLM(result)
    return agent


def _context():
    return AgentContext(
        session_id="sess_advisor",
        recent_segments=[
            TranscriptSegment(speaker="CUSTOMER", text="This is way too expensive.", timestamp=8.0),
        ],
        trigger_type=TriggerType.TURN_BASED,
    )


def test_advisor_is_silent_when_gate_is_false():
    # THE DEFAULT CASE: nothing worth saying → ZERO insights.
    agent = make_advisor({"has_insight": False, "content": "suppressed draft"})
    resp = asyncio.run(agent.evaluate(_context()))
    assert resp.insights == []          # produced NOTHING — the product working as designed


def test_advisor_emits_exactly_one_insight_on_breach():
    # THE EXCEPTION: a real objection → exactly one well-formed insight.
    agent = make_advisor({
        "has_insight": True,
        "type": "warning",
        "content": "Price objection — anchor on ROI before discounting.",
        "confidence": 0.9,
        "expiry": 30,
    })
    resp = asyncio.run(agent.evaluate(_context()))

    assert len(resp.insights) == 1
    insight = resp.insights[0]
    assert insight.type == InsightType.WARNING
    assert insight.content == "Price objection — anchor on ROI before discounting."
    assert insight.confidence == 0.9
    assert insight.expiry == 30            # S-1: schema expiry passes through
    assert insight.agent_id == "objection_advisor"
```

What this proves: the Advisor obeys the gate in *both* directions. The first test
is the one that protects the thesis — it guarantees the Advisor shuts up when it
has nothing to add. The second test pins the *shape* of the rare insight so a
regression can't quietly drop the `expiry` or mislabel the `type`.

---

### Checklist: writing a test for any new agent

1. **Pick the archetype** → that fixes which channels are allowed and which must
   be asserted empty.
2. **Write the silence test first.** Mock the LLM to the agent's "nothing to do"
   output and assert `resp.insights == []` (plus any non-HUD channels that *should*
   still fire). This is mechanism #1, #2, or #3 from the Silence Test table.
3. **Then write the speak test** (Advisors) or the **signal test** (Detector event
   / Extractor fact / Monitor variable). Assert *exactly one* of the expected
   output and pin its fields (`type`, `expiry`, `name`, `key`, `value`,
   `source_agent`).
4. **Assert timestamps are session-relative** for any emitted event/fact
   (`ts == max segment timestamp`, `ts < 1_000_000_000`) — INV-13 / A-2.
5. **Call `evaluate()` directly** for parsing/gating; reserve `process()` for when
   the *cooldown or trigger-type gate itself* is under test.
6. If the agent uses a **custom schema**, add the gate-less misconfiguration
   warning test — a lost `check_field` is invisible until it spams the HUD.

If your test file does not contain at least one `assert resp.insights == []`, you
have not tested the most important property of the agent.
## Quality Metrics — Making Restraint Measurable

The doctrine of Part I says the product is *restraint*: a reactive swarm of cheap observers whose highest virtue is staying silent. But "be quiet most of the time" is unfalsifiable as written. A swarm that never speaks is trivially restrained and useless; a swarm that speaks every turn is loud and useless. The product lives in the narrow band between, and you cannot tune your way into that band without numbers. This artifact turns the doctrine into instrumentation.

Three metric families, all from the owner's spec, all kept:

- **HUD Quality** — is what reaches the operator worth the interruption?
- **Cost & Latency** — what did the gating actually save, and is the turn fast enough to be real-time?
- **Blackboard Quality** — is the shared coordination substrate healthy, or quietly rotting?

Before the catalogue, the single number that matters most.

---

### The headline metric: insight rate (the silence-to-signal ratio)

> **Insight rate** = insights surfaced per 100 turns.
> **Silence-to-signal ratio** = (turns that produced zero insights) / (total turns).

These are the same fact stated two ways. Insight rate is the *signal* side; the silence-to-signal ratio is its complement and the more honest framing for a product whose value proposition is quiet. If 100 turns produce 8 insights across 6 distinct turns, your silence ratio is 94/100 — 94% of turns the HUD said nothing. **That number being high is the goal, not a failure.** A team shipping a "smart" copilot will instinctively read 94% silence as 94% missed opportunity. In this architecture it is 94% restraint earned.

Direction: there is no universal target, because the *right* rate is host- and role-specific. What you want is a **stable, intentional** rate that you chose by tuning cooldowns, conditions, and confidence floors — not an emergent rate you discovered after the fact. The metric's job is to make the rate visible so drift is detectable. A sudden jump from 6/100 to 30/100 after a prompt change is the alarm; the absolute value is the dial.

How to capture it, framework-side, for free: count turns in `on_turn_start`; count `len(response.insights)` in `on_turn_end`; a turn is "silent" when that count is zero. Both hooks exist and carry exactly these payloads (`on_turn_start(context)`, `on_turn_end(response, duration)`). This is the cheapest, most important counter in the system, and it is two integers.

Everything below refines this headline: the HUD family asks whether the signal was *good*, the cost family asks what the silence *saved*, and the blackboard family asks whether the substrate producing both is *sound*.

---

### A note on where each metric can be measured

The framework gives you three observation surfaces, and every metric belongs to exactly one:

1. **Framework-side (callbacks + tracer)** — counted from `AgentCallbackHandler` hooks and `StructuredLogTracer` output. Cheap, synchronous, no host cooperation needed. This covers production/skip/gate/latency accounting.
2. **Host-side (UI events)** — acceptance, dismissal, usefulness, "missed moment". The framework emits an insight and forgets it; it never learns whether the operator clicked, ignored, or cursed at it. Only the host UI sees that, so these metrics require the host to log its own events and join them back to insight identity.
3. **Blackboard inspection** — fact duplication/conflict, queue growth, stale variables. These are properties of `context.blackboard` state, read by snapshotting containers across turns. Not emitted by any callback; you read them.

The instrumentation sketch at the end implements (1) in full and shows the hook points for (2) and (3).

---

### Family 1 — HUD Quality

Does what survived the gate deserve to have survived?

### 1.1 Insight rate per 100 turns
*(See headline above.)* Production count of insights, normalized per 100 turns. **Good = low and stable.** Framework-side: `len(response.insights)` summed in `on_turn_end`, divided by turn count from `on_turn_start`.

### 1.2 Insight acceptance / usefulness rate
> Of insights surfaced, the fraction the operator acted on (clicked the `action_label`, expanded, pinned) or later rated useful.

**Good = high.** This is the truest measure of signal quality: an insight that is shown and ignored is noise that happened to clear the gate. Direction caveat — acceptance is not the same as usefulness. An operator may act on a bad suggestion or silently benefit from one they never click. Capture both if the UI affords it: a hard *acceptance* signal (click/act) and a soft *usefulness* signal (thumbs-up, survey, downstream outcome).

**Host-side only.** The framework hands the host `AgentInsight` objects (with `agent_id`, `agent_name`, `type`, `content`, `action_label`). Acceptance is a UI event the host fires when the operator interacts with that rendered insight. To make the join possible, the host must carry a stable insight identity from render to interaction — `AgentInsight` has no `id` field, so the host should mint one at render time (e.g. hash of `agent_id` + `content` + turn) and key its accept/dismiss events on it.

### 1.3 Dismissal rate
> Fraction of surfaced insights the operator explicitly dismissed (closed before expiry).

**Good = low.** The dual of acceptance, but distinct: a dismissal is an *active rejection*, stronger evidence of noise than a mere non-click. A high dismissal rate on a specific `agent_name` is a precise signal — that observer is mis-tuned, and you can raise its cooldown or confidence floor in isolation. **Host-side.** The host fires a dismiss event; group by `agent_id` to localize the offender.

### 1.4 Repeated-insight rate
> Fraction of insights whose content substantially repeats an insight surfaced earlier in the same session.

**Good = low.** Repetition is the most common failure mode of a swarm with short cooldowns: the same observer notices the same condition turn after turn and says the same thing. It is corrosive because each repeat is individually plausible but collectively nagging. **Host-side (with framework assist).** The host maintains a per-session set of recently-surfaced contents (or embeddings) and flags near-duplicates. The framework assist: agent-private `memory` (`response.memory_updates`, persisted via `blackboard.update_memory` and read back through `shared_state["memory_<id>"]`, INV-14) lets a well-behaved agent remember "I already said this" and self-suppress — which is the *fix*, while the metric is the *detector*.

### 1.5 Average insight lifetime
> Mean wall-clock time an insight remains displayed before it expires or is dismissed.

**Good = context-dependent, watched for drift.** `AgentInsight.expiry` defaults to 15 (seconds to display); agents can override per-insight (the `create_insight` `expiry` pass-through, S-1). Two readings: (a) the *configured* lifetime — auditable framework-side by recording `insight.expiry` in `on_turn_end`; (b) the *realized* lifetime — how long it actually stayed up before dismissal, which is host-side. A realized lifetime far below configured expiry means operators are swatting insights away early: a dismissal-rate signal in disguise.

### 1.6 False-positive interruption rate
> Fraction of *interrupting* insights (high-salience: `WARNING`, `OPPORTUNITY`, or anything the host renders as an alert) that the operator judged unwarranted.

**Good = near zero.** This is the most expensive failure mode in the whole system. A false-positive interruption doesn't just waste a glance — it teaches the operator to distrust the HUD, after which even true positives are ignored. The doctrine's "gate ruthlessly" exists primarily to protect this number. **Host-side**, but the framework localizes it: `InsightType` (`WARNING`/`OPPORTUNITY` vs `SUGGESTION`/`FACT`/`PRAISE`) and `confidence` are on every insight, so the host can compute false-positive rate *per type* and confirm that the loud types clear a higher confidence bar than the quiet ones.

### 1.7 Missed-critical-moment rate
> Of moments that *should* have produced an insight (objection, buying signal, compliance risk), the fraction where the HUD stayed silent.

**Good = near zero — and this is the one metric where silence is the failure.** Every other HUD metric pushes toward quiet; this one is the counterweight that stops you from tuning the swarm into uselessness. It is the reason the headline metric has no "lower is always better" rule. **Host-side, and the hardest to capture** because it requires ground truth the framework cannot have: a human label, a post-call review, or a downstream outcome (deal lost on an unhandled objection). Pragmatically, sample sessions for manual review and label missed moments; track the rate on that sample. A swarm with an enviable 2/100 insight rate and a 40% missed-critical-moment rate is not restrained — it is asleep.

---

### Family 2 — Cost & Latency

What did the gating buy you, and is the turn fast enough to be real-time?

This family is almost entirely **framework-side and free**, because the engine's whole job is deciding who runs, and it announces every decision through callbacks. The three "skip" metrics below correspond to three real, distinct gates in `engine.py` / `agent.py`, and they decompose the total savings into where each cheap-observer dollar was saved.

### 2.1 Agents skipped before LLM (the gate inventory)
> Per turn: how many registered agents did **not** run, and why.

**Good = high relative to agents that ran** — most observers should sit out most turns. The engine reports every Phase-1 skip through **`on_agent_skipped(agent_name, reason)`**, fired in `_get_eligible_agents`. The `reason` string is one of a fixed vocabulary from `_is_eligible`, and these are the sub-metrics:

- `"not_in_allow_list"` — host hard-filtered the agent (host policy, e.g. role not active).
- `"trigger_type_mismatch"` — agent doesn't subscribe to this turn's trigger type.
- `"conditions_not_met"` — agent's `trigger_conditions` evaluated false against the blackboard.

Capture: increment a counter keyed on `reason` in `on_agent_skipped`. This single hook gives you 2.2 and most of 2.1 directly.

### 2.2 Agents gated by condition
> Subset of 2.1 where `reason == "conditions_not_met"`.

**Good = high.** This is the blackboard-driven precondition gate doing its job — agents declining to run because the *state* doesn't warrant it (no question pending, budget already known). It's the cheapest possible gate: pure dict/condition evaluation, zero LLM, zero agent body. A low number here on a condition-heavy config means your conditions aren't biting and you're paying to run agent bodies that will no-op. **Framework-side, from the same `on_agent_skipped` reason.**

### 2.3 Agents blocked by cooldown
> Per turn: agents that were eligible by trigger/condition but did not run because their cooldown window had not elapsed.

**Good = present and steady** — cooldown is the anti-nag throttle, the mechanism most directly responsible for the silence ratio. **This is the one cost metric the callbacks do *not* hand you cleanly**, and it's worth understanding why. Cooldown is enforced *inside* `BaseAgent.process()` (the `(now - self.last_run_time) < effective_cooldown` check), which returns `None` *before* firing `on_agent_start` — but `process()` is only called for agents the engine already deemed eligible, so a cooldown skip is silent: no `on_agent_skipped` (that's engine-side eligibility, and cooldown lives in the agent), and no `on_agent_start`/`on_agent_finish` pair.

You therefore infer it by subtraction. For a turn, let `E` = agents the engine deemed eligible (it logged "Phase 1: Running E eligible agents"; equivalently, registered minus the `on_agent_skipped` count). Let `S` = agents that actually started (`on_agent_start` fires). **Cooldown-blocked = E − S.** A `MetricsCollector` that counts eligibility (via the absence of a skip) and counts `on_agent_start` per turn computes this without touching the agent internals. The gap is exactly the cooldown gate plus the rare Phase-2 trigger-type re-check.

### 2.4 LLM calls per turn
> Number of actual model invocations (`generate_json`) per turn.

**Good = low**, and it should approximate the number of agents that *ran and chose to think* — not the number registered. This is the real cost driver. The framework doesn't emit a dedicated "LLM call" callback, but `on_agent_start` is a faithful proxy: an agent that starts is an agent that may call the model (a no-op gate already skipped it). For exactness, count agents that started **and** returned a non-`None` response (`on_agent_finish` with a non-null `response` / the tracer's `status: "success"`). Cross-check against provider-side call counts during validation. **Framework-side.**

### 2.5 Premium-model calls per session
> Count of LLM calls made by agents configured with an expensive model (e.g. a `gpt-4o`-class model vs the `gpt-4o-mini` default).

**Good = low and deliberate** — the swarm doctrine is *cheap* observers; a premium call should be a rare escalation, not a default. `AgentConfig.model` is per-agent and the default is `"gpt-4o-mini"`. Capture: in the `MetricsCollector`, hold a name→model map built at registration (or read `agent.config.model`), and when an agent of a premium model starts/finishes, increment a per-session premium counter. **Framework-side**, given the model map. This metric is the guardrail against "just bump that one agent to the big model" quietly becoming the cost story.

### 2.6 Average `process_turn` latency
> Mean wall-clock duration of a full turn.

**Good = comfortably under the host's real-time budget** (the LLM client's per-request budget is `DEFAULT_TIMEOUT = 10.0s`, with bounded retries — a turn that routinely approaches that is at risk of HUD stall). Handed to you directly: **`on_turn_end(response, duration)`** carries the turn duration, and `StructuredLogTracer` emits it as `total_latency_ms`. Track mean and, more usefully, the tail (p95/p99) — real-time UX dies on the tail, not the mean. **Framework-side.**

### 2.7 Phase-1 vs Phase-2 latency
> Turn latency attributed to Phase 1 (primary agents) vs Phase 2 (event-triggered subscribers).

**Good = Phase 2 rare and cheap.** Phase 2 only runs when Phase-1 agents emit events (`if all_events and self.max_phases >= 2`), and it's a second fan-out of LLM calls — the most expensive thing a turn can do. You want to know how often you pay for it. Capture via the phase callbacks: **`on_phase_start(phase, agent_names)`** and **`on_phase_end(phase, event_names)`** bracket each phase; record timestamps on start and diff on end, keyed by `phase`. Frequency of a `phase == 2` start is itself a metric — a session where most turns trigger Phase 2 has an event-happy agent that is effectively doubling cost. **Framework-side.**

### 2.8 Cost per session
> Total estimated LLM spend for a session.

**Good = low and predictable.** The framework has no pricing knowledge, so this is a host-side rollup: combine 2.4 (calls), 2.5 (premium split), and per-model token estimates (the client caps output at `DEFAULT_MAX_TOKENS = 1024`, which bounds the per-call output cost). The `MetricsCollector` produces the call counts per model; the host multiplies by its price table. **Framework-side counts, host-side pricing.**

---

### Family 3 — Blackboard Quality

Is the coordination substrate healthy? These are properties of `context.blackboard` state, not lifecycle events — **blackboard inspection**, read by snapshotting containers across turns. The blackboard is the swarm's only shared memory; if it rots, every downstream gate makes worse decisions.

### 3.1 Fact duplication rate
> Fraction of `add_fact` attempts that targeted a `(type, key)` already present.

**Good = low, but interpret carefully.** The blackboard *dedupes by design*: `add_fact` matches on `(type, key)` (or `type` alone when `key is None`) and keeps a single winner. So duplication never bloats storage — but a high *attempt* rate means many agents are independently re-deriving the same fact every turn, which is wasted LLM work upstream of a gate that throws the result away. Capture: the engine doesn't count this, so inspect `blackboard.facts` before/after a turn, or wrap/observe `add_fact`. The signal you want is "N agents emitted `budget` this turn; 1 survived" — that's N−1 wasted extractions. **Blackboard inspection.**

### 3.2 Fact conflict rate
> Fraction of `add_fact` attempts where an incoming fact *disagreed* (different `value`) with the existing fact at the same `(type, key)` and replaced it (or was rejected).

**Good = low.** Conflict is more serious than duplication: two observers disagree about a fact (different budgets, contradictory stakeholders), and the blackboard silently resolves it by `(priority, confidence)` (INV-9). The resolution is deterministic and correct *mechanically*, but a high conflict rate means your observers are genuinely uncertain or contradictory about the world — and only one side's view survives to drive gates. Capture by inspecting whether an `add_fact` replaced an existing fact whose `value` differed (vs a benign re-assertion of the same value). **Blackboard inspection**, since neither the callback nor the tracer reports replacements.

### 3.3 Queue growth rate
> Net change in total queue depth (`sum(len(q) for q in blackboard.queues.values())`) per turn.

**Good ≈ zero over time** — queues should be drained as fast as they fill. Queues are FIFO work-item lists; agents `push_queue_items` (visible in the tracer as `queue_pushes`) and consumers `pop_queue`. The tracer reports *pushes* per agent (`step_info["queue_pushes"]`) but not pops, so net growth must be read from blackboard state. Monotonic growth is a leak: producers without consumers, an unbounded backlog that will eventually distort conditions that test queue length. Capture: sample total queue depth in `on_turn_end` and difference across turns. **Blackboard inspection.**

### 3.4 Stale variable rate
> Fraction of blackboard variables not written for many turns yet still read by conditions/agents.

**Good = low.** Variables are session-scoped and never auto-expire (`set_var` just writes; there's no TTL). A variable set once at turn 3 and still steering a `trigger_conditions` check at turn 200 is a stale-state hazard — the gate is firing on a fact about a conversation that has moved on. Capture: track last-write turn per variable (snapshot `blackboard.variables` keys each turn, record when each value last changed) and flag variables whose age exceeds a host threshold while still being referenced. Exclude the engine-managed `sys.*` keys (`sys.turn_count`, `sys.session_id`, `sys.trigger_type`), which are rewritten every turn by design. **Blackboard inspection.**

### 3.5 Event-to-insight conversion rate
> Of events emitted in Phase 1, the fraction that ultimately produced an insight via a Phase-2 subscriber.

**Good = high-ish, but not 1.0.** Events are the swarm's internal nervous system: a Phase-1 observer emits `question_detected`, a Phase-2 subscriber reacts. If events fire constantly but rarely convert to an insight, Phase 2 is burning LLM calls (cost!) chasing signals that fizzle — an event-happy agent inflating 2.7. If conversion is suspiciously near 1.0, your Phase-2 agents aren't gating at all and every event becomes a surfaced insight, which will hurt the HUD-quality family. Capture: `on_phase_end(1, event_names)` gives the events emitted in Phase 1; the Phase-2 insights are the delta in `response.insights` attributable to subscribers (or counted from `on_phase_end(2, ...)` plus the per-agent `on_agent_finish` insight counts). **Framework-side**, joining the phase callbacks.

---

### Instrumentation sketch: `MetricsCollector`

A custom `AgentCallbackHandler` that records the cheap framework-side counters per turn and per session. Register it in the `AgentEngine(callbacks=[...])` list alongside (or instead of) the `StructuredLogTracer`. It implements every Family-2 metric and the headline directly; it marks the hook points where host-side and blackboard-inspection metrics attach. This is a sketch to illustrate the *capture points* — the real signatures match `core/callbacks.py` exactly.

```python
import time
from collections import Counter, defaultdict
from xubb_agents.core.callbacks import AgentCallbackHandler

# A premium model is anything not the cheap default; tune to your fleet.
PREMIUM_MODELS = {"gpt-4o", "gpt-4-turbo", "o1", "o1-mini"}

class MetricsCollector(AgentCallbackHandler):
    def __init__(self, agent_models: dict[str, str]):
        # name -> model, built from [a.config.name: a.config.model] at registration.
        self._models = agent_models
        self.session = {
            "turns": 0,
            "silent_turns": 0,            # HEADLINE: silence-to-signal
            "insights_total": 0,          # HEADLINE: insight rate
            "skips_by_reason": Counter(), # 2.1 / 2.2  (from on_agent_skipped)
            "agents_started": 0,          # 2.4 proxy: agents that ran
            "agents_produced": 0,         # 2.4 exact: ran AND returned a response
            "llm_calls_premium": 0,       # 2.5
            "turn_latencies_ms": [],      # 2.6 (mean + tail)
            "phase2_turns": 0,            # 2.7 frequency
            "phase_latency_ms": defaultdict(float),  # 2.7
        }
        self._turn_started = 0            # per-turn: eligible-that-actually-started
        self._turn_skipped = 0            # per-turn: engine eligibility skips
        self._phase_start_ts = {}

    async def on_turn_start(self, context):
        self.session["turns"] += 1
        self._turn_started = 0
        self._turn_skipped = 0

    async def on_agent_skipped(self, agent_name, reason):
        # 2.1 / 2.2: engine eligibility gate (allow-list / trigger / conditions)
        self.session["skips_by_reason"][reason] += 1
        self._turn_skipped += 1

    async def on_agent_start(self, agent_name, context):
        # An agent that starts has passed eligibility AND cooldown -> may call LLM.
        self._turn_started += 1
        self.session["agents_started"] += 1
        if self._models.get(agent_name) in PREMIUM_MODELS:
            self.session["llm_calls_premium"] += 1  # 2.5

    async def on_agent_finish(self, agent_name, response, duration):
        if response is not None and response.insights is not None:
            self.session["agents_produced"] += 1     # 2.4 exact

    async def on_phase_start(self, phase, agent_names):
        self._phase_start_ts[phase] = time.time()
        if phase == 2:
            self.session["phase2_turns"] += 1          # 2.7 frequency

    async def on_phase_end(self, phase, event_names):
        started = self._phase_start_ts.pop(phase, None)
        if started is not None:
            self.session["phase_latency_ms"][phase] += (time.time() - started) * 1000
        # 3.5 hook: stash Phase-1 event_names here, reconcile against
        #            Phase-2 insights at turn end (event-to-insight conversion).

    async def on_turn_end(self, response, duration):
        n = len(response.insights)
        self.session["insights_total"] += n           # HEADLINE numerator
        if n == 0:
            self.session["silent_turns"] += 1          # HEADLINE: silence ratio
        self.session["turn_latencies_ms"].append(duration * 1000)  # 2.6

        # 2.3 cooldown-blocked (inferred, no direct callback):
        #   eligible = registered_agents - self._turn_skipped
        #   cooldown_blocked = eligible - self._turn_started
        # (records the gap; the engine never reports a cooldown skip directly.)

        # BLACKBOARD INSPECTION hooks (Family 3) — read response/blackboard state:
        #   3.1 fact dup / 3.2 fact conflict: diff blackboard.facts pre/post turn,
        #       or observe add_fact; compare (type,key) and value.
        #   3.3 queue growth: sum(len(q) for q in blackboard.queues.values()) delta.
        #   3.4 stale vars: track last-write turn per non-sys.* variable key.

    async def on_chain_error(self, error):
        # Turn-fatal error; count separately so it doesn't masquerade as "silence".
        self.session.setdefault("turn_errors", 0)
        self.session["turn_errors"] += 1
```

### What the sketch does *not* capture, and where it lives

- **Family 1 (HUD quality) beyond raw counts** — acceptance, dismissal, repeated-insight, realized lifetime, false-positive interruptions, missed moments — is **host-side UI accounting**. The host renders each `AgentInsight`, mints a stable id (the model has none), and logs interaction events (`accept`, `dismiss`, `rate`, `expire`) keyed on that id and on `agent_id` / `type`. The framework's contribution is identity and classification (`agent_id`, `agent_name`, `type`, `confidence`, `expiry`, `action_label`); the verdict comes from the operator. Missed-critical-moment needs ground truth the framework cannot supply — sample sessions and label them by hand or by downstream outcome.
- **Family 3 (blackboard quality)** is **blackboard inspection**: snapshot `context.blackboard` containers across turns (facts, queues, variables) and diff. The tracer surfaces *pushes* and *fact counts* per agent but not pops, replacements, or staleness, so these are read from state, not from events. They attach at the `on_turn_end` hook points marked above.
- **Cooldown-blocked (2.3)** is the one cost metric requiring inference — `E − S`, eligible minus started — because cooldown is enforced inside `BaseAgent.process()` before any callback fires.

### Reading the dashboard

Lead with the headline. Insight rate and the silence-to-signal ratio sit at the top, because every other number is in service of keeping that ratio high *without* letting missed-critical-moment rate climb. The cost family proves the gates are doing real work (high skip/cooldown counts, low LLM-calls-per-turn, rare Phase 2). The HUD family proves the few things that survived the gates were worth it (high acceptance, low dismissal, near-zero false-positive interruptions). The blackboard family proves the substrate feeding all of it is sound. A healthy swarm shows mostly-silence up top, mostly-skips in the middle, mostly-accepted in the small set that got through, and a flat, drained, fresh blackboard underneath. That is restraint, made measurable.
## Definition of Done — For an Agent

A backend utility is done when it works. A Xubb agent affects a live human's attention, so the bar is higher. An agent is **not production-ready** until every box is checked. This is the gate that protects the system from erosion — it makes the anti-patterns *enforceable*, not just discouraged.

An agent is Done when:

- [ ] **It has a single responsibility** — its job is one sentence with no "and."
- [ ] **It has at least one pre-LLM gate** — a `trigger_type` plus, for anything but a pure every-turn detector, `trigger_conditions` that reject cheaply before any model call.
- [ ] **It can return silence** — there is an explicit, tested path where it produces no insight (a Detector/Extractor/Monitor emits zero insights by design; an Advisor declines via `check_field` / `has_insight: false`).
- [ ] **It has a cooldown** — a deliberate value (not the default by accident), appropriate to its archetype.
- [ ] **It declares its Blackboard reads/writes** — documented inputs and outputs, and it writes to the *correct* container for its archetype.
- [ ] **It has at least three test transcripts** — one where it fires, one where it must stay **silent**, one edge case — each asserting the expected channels (events/facts/variables/insights) *and* the expected silence.
- [ ] **It has observability fields** — its runs, skips (with reason), speaks, and errors are visible via the callbacks/tracer; its insight rate is measurable.
- [ ] **It has a known failure mode** — you can state what a false positive and a false negative look like, and what the user experiences in each.
- [ ] **It does not emit HUD output unless it is explicitly an Advisor or Monitor** — Detectors and Extractors are silent by contract; emitting an insight from one is a defect, not a feature.

> **The enforcement principle:** the framework already biases toward silence (gate-less schemas default quiet; conditions fail closed; failed agents are discarded). The Definition of Done makes sure a *human* can't quietly undo that bias by shipping an ungated, chatty, mega-agent. If a PR adds an agent and any box above is unchecked, the PR is not done — it's a draft.
## The Agent Review Board

Adding a backend endpoint is a code review. Adding an agent is **adding a new voice into the user's ear** — a new claimant on the scarcest resource in the product: attention. It deserves a different kind of scrutiny.

The "board" is not bureaucracy; it's a short, mandatory set of questions any reviewer asks before a new agent (or a meaningful change to one) merges. It exists to enforce the product philosophy that *every visible agent must justify its existence.*

### Agent Review Questions

Ask these of every new or materially-changed agent:

1. **Does this agent deserve to exist?** — What user moment is unserved without it? If you can't name one, don't add it.
2. **Is it silent by default?** — On a typical turn, does it produce nothing? If it speaks often, it's a redesign, not a review.
3. **Could this be a deterministic rule instead of an LLM?** — Counting, thresholds, and keyword presence don't need a model. Spend tokens only on judgment.
4. **Does this create HUD noise?** — Does it compete with existing Advisors for the one slot? How will the curator rank it?
5. **Does it duplicate another agent?** — Two agents detecting the same thing is two costs and a dedup problem. Merge or differentiate.
6. **Does it write to the right Blackboard container?** — Events for signals, facts for knowledge, variables for state, queues for work, memory for private continuity. A misplaced write is a latent bug.
7. **Does it need a premium model?** — Justify `gpt-4o`. The default is `gpt-4o-mini`; premium is earned by an event, not assumed.
8. **What user harm occurs if it fires at the wrong moment?** — A false-positive interruption costs trust. Is the gating tight enough that this is rare?
9. **What user harm occurs if it fails silently?** — If this is a must-never-miss moment, silence is the failure. Is that monitored (missed-critical-moment rate)?

### When to convene

- **Always** for a new Advisor or Monitor (anything that can speak).
- **Always** when raising an agent to a premium model, removing a condition, or lowering a cooldown — each *increases* the agent's claim on attention or budget.
- **Lightweight** for a new silent Detector/Extractor (verify it's truly silent and writes the right container).

> A new endpoint asks "is the code correct?" A new agent asks "does this voice deserve the user's two seconds?" The first is necessary; the second is what keeps the copilot calm as the team scales.
## Product Experience Doctrine

Every chapter in this playbook is, ultimately, in service of one feeling. The architecture, the gating, the curation, the metrics — they all exist to make the product feel a particular way to the human wearing it. Name that feeling, and you have the bar that every technical decision answers to.

> **Xubb should feel like a calm intelligence layer, not an eager assistant.**

From that single line, the whole doctrine follows:

- **It should not compete with the conversation.** The user's primary task is talking to another human. The copilot is a second screen, not a second voice. If it ever pulls focus from the live exchange, it has failed — no matter how correct it was.
- **It should not explain itself while the user is listening.** No preambles, no reasoning, no "I noticed that…". One actionable phrase the user can act on without reading a paragraph. Words are cognitive load; spend them like they're expensive.
- **It should not create cognitive load.** A glanceable, single, expiring insight — never a list, never a wall of text, never two things at once. The HUD is read in the gaps of a conversation, in under two seconds.
- **It should surface only the next useful move.** Not everything it knows — the one thing that helps *right now*. Understanding accumulates silently on the Blackboard; only the earned next-step reaches the glass.
- **It should disappear when it has nothing earned to say.** Which is most of the time. An empty HUD is not a broken HUD — it is a confident one. Silence is the default state, and the product is *better* in it.

### Connecting the doctrine to the architecture

This is not a poster; it is a spec. Each line of the doctrine is enforced by a real mechanism in Part I:

| Doctrine | Enforced by |
|----------|-------------|
| Don't compete with the conversation | Reactive, host-driven triggers; the swarm observes, it doesn't converse |
| Don't explain yourself | `AgentInsight.content` is a short phrase (`min_length` only); `expiry` makes it ephemeral |
| Don't create cognitive load | The Insight Curator → one visible insight; `expiry` as a TTL |
| Only the next useful move | Conditions + priority + the cheap→premium cascade earn the one moment worth surfacing |
| Disappear when nothing's earned | Silence as default: gate-less schemas stay quiet, conditions fail closed, failed agents are discarded |

Hold this doctrine above every design review. When two implementations are equally correct, the one that makes the copilot quieter, calmer, and more glanceable is the right one. **Attention is the budget. Spend it like it's the only currency that matters — because to the user, it is.**

---

## Closing

The framework gives you primitives: agents, a blackboard, triggers, conditions, phases, insights. Part I taught the doctrine for composing them; Part II made that doctrine an operating manual — checklists, blueprints, metrics, and gates that make it hard to build badly.

But the whole playbook reduces to one idea you should be able to recite from memory:

> **A Xubb copilot is a restrained, blackboard-coordinated swarm that earns the right to interrupt. It is silent by default, decomposed into many cheap observers, coordinated through a shared world-model, gated ruthlessly, and curated to a single, perfectly-timed, expiring moment of help.**

Build every agent so that silence is the easy path and a visible insight is rare, earned, and trusted. Do that, and the product won't feel like a chatbot bolted onto a conversation. It will feel like a quiet expert sitting beside the user — which is the only version worth shipping.

*Now go build something that earns its two seconds.*
