# Xubb Agents Framework - Technical Specification

**Version:** 2.6.0
**Status:** Beta — production-hardened (contract-gated; see docs/PROCESS.md)
**Scope:** `xubb_agents` Library
**Compatibility:** Backward compatible with v1.0/v2.0 agents, with one deliberate v2.2 contract correction (fact conflict resolution, F-1). See [SPEC_V2_1_HARDENING.md](archive/SPEC_V2_1_HARDENING.md) (archived) for v2.1 behavioral normalizations and [SPEC_V2_2_HARDENING.md](SPEC_V2_2_HARDENING.md) for the v2.2 hardening items and migration notes.

---

## 1. Executive Summary

The **Xubb Agents Framework** is a standalone, event-driven Python library designed to power real-time conversational intelligence. It provides the infrastructure for creating, managing, and executing autonomous AI agents that "listen" to a conversation and intervene with context-aware insights.

It is designed to be **consumed** by host applications but maintains strict decoupling, ensuring it can be used in any Python-based conversational system (e.g., a CLI tool, a desktop app, or a web service).

### What's New in v2.0

| Feature | v1.0 | v2.0 |
|---------|------|------|
| State management | Flat dictionary | Structured Blackboard |
| Agent coordination | Parallel only | Event-driven pub/sub |
| Trigger conditions | None | Blackboard-aware preconditions |
| Execution phases | Single pass | Multi-phase (normal → event-triggered) |
| Data containers | Unstructured | Variables, Events, Queues, Facts, Memory |
| Response caching | Hash-based LLM cache | **Removed** (cooldowns + conditions are better) |

---

## 2. Architectural Principles

1.  **Event-Driven Execution:** Agents do not run continuously. They are dormant until triggered by specific events (Turn completion, Keyword detection, Silence, Timer, or Events from other agents).
2.  **Stateless Execution (mostly):** Each evaluation is fresh, provided with a `Context` object containing transcript history and Blackboard state. Agents return a `Response` object.
3.  **Non-Blocking Concurrency:** All I/O (LLM calls) is asynchronous (`asyncio`). Multiple agents evaluate in parallel without blocking the main audio/transcript loop.
4.  **Graceful Degradation:** Failures in individual agents (LLM errors, logic bugs) are caught, logged, and isolated, ensuring the host application remains stable.
5.  **Blackboard Snapshot Semantics:** During a phase, all agents evaluate against the **same immutable snapshot** of the Blackboard. State updates are merged only after all agents in the phase complete.

---

## 3. Core Components

### 3.1 Agent Engine (`core/engine.py`)

The central orchestrator.

**Responsibilities:**

| Responsibility | Description |
|----------------|-------------|
| **Registry** | Maintains the list of active agents |
| **Routing** | Determines which agents run based on trigger type |
| **Condition Evaluation** | Checks trigger conditions before running agents |
| **Blackboard Management** | Manages structured state (in-memory for session lifetime) |
| **Event Dispatch** | Collects emitted events, triggers subscribers |
| **Multi-Phase Execution** | Runs normal agents (Phase 1), then event-triggered agents (Phase 2) |
| **Response Aggregation** | Merges insights, applies state updates by priority with deterministic ordering |
| **Observability** | Emits lifecycle events to callbacks |

**Note:** Response caching was removed in v2.0. Cooldowns and trigger conditions provide more correct mechanisms for preventing unnecessary LLM calls.

### 3.2 Base Agent (`core/agent.py`)

The abstract base class for all intelligence units.

**Lifecycle:**
1.  `__init__`: Configure triggers, cooldowns, conditions
2.  `process()`: Template method — enforces **cooldown only** (routing is engine's job)
3.  `evaluate()`: Abstract method — the actual "Brain" logic (usually an LLM call)

**Responsibility Split (Engine vs Agent):**

| Responsibility | Owner | Notes |
|----------------|-------|-------|
| Trigger type routing | **Engine** | Determines which agents match the trigger type |
| Condition evaluation | **Engine** | Evaluates trigger_conditions before calling agent |
| Cooldown enforcement | **Agent** | Agent's `process()` checks its own cooldown timer |
| Error handling | **Agent** | Returns `InsightType.ERROR` instead of propagating exceptions |

**Note:** `BaseAgent.process()` does **not** re-check trigger type or conditions — that would duplicate engine logic and risk disagreements.

### 3.3 Blackboard (`core/blackboard.py`)

Structured shared state with typed containers. **In-memory only**; persistence is host responsibility.

```python
class Blackboard:
    events: List[Event]                  # Transient signals (structured)
    variables: Dict[str, Any]            # Session-scoped key-value
    queues: Dict[str, List[Any]]         # Ordered lists (FIFO)
    facts: List[Fact]                    # Extracted knowledge
    memory: Dict[str, Dict[str, Any]]    # Agent-private state
```

**Container Semantics:**

| Container | Semantics | Lifetime | Operations |
|-----------|-----------|----------|------------|
| **Events** | "Something happened" (structured with payload) | Consumed after `process_turn()` | emit, subscribe |
| **Variables** | "Current state is X" | Session | get, set, delete |
| **Queues** | "Ordered work items" | Session | push, pop, peek, clear |
| **Facts** | "Extracted knowledge" (keyed, deduplicated) | Session | add, query, dedupe by (type,key) |
| **Memory** | "Agent's scratchpad" | Session | get, set |

**Reserved Variable Namespace:**
- `sys.*` — Reserved for engine-maintained state (e.g., `sys.turn_count`)
- Non-engine writes to `sys.*` emit a warning (the write still proceeds); user variables should avoid the `sys.` prefix
- **v2.2 (E-2):** `sys.*` keys are excluded when the engine syncs blackboard variables into the v1 `shared_state`, so a v1 agent echoing `shared_state` back no longer trips the reserved-key warning on round-trip

### 3.4 Condition Evaluator (`core/conditions.py`)

Evaluates trigger conditions against Blackboard state.

```python
class ConditionEvaluator:
    def evaluate(self, conditions: dict, blackboard: Blackboard, 
                 meta: dict, agent_id: str) -> bool
    def _evaluate_rule(self, rule: dict, blackboard: Blackboard, 
                       meta: dict, agent_id: str) -> bool
```

**Supported Operators:**

| Operator | Description | Example |
|----------|-------------|---------|
| `eq` | Equals | `phase == "negotiation"` |
| `neq` | Not equals | `phase != "closed"` |
| `gt` / `gte` | Greater than (or equal) | `turn_count > 5` |
| `lt` / `lte` | Less than (or equal) | `risk_score < 3` |
| `in` | Value in list | `phase in ["negotiation", "closing"]` |
| `not_in` | Value not in list | `phase not_in ["closed", "lost"]` |
| `contains` | List/string contains value | `topics contains "pricing"` |
| `exists` | Key is truthy | `budget exists` |
| `present` | Key exists regardless of value | `flag present` |
| `not_exists` | Key is falsy or missing | `objection not_exists` |
| `not_empty` | Collection has items | `pending_questions not_empty` |
| `empty` | Collection is empty | `action_items empty` |
| `mod` | Modulo operation (`value` = divisor, `result` = expected remainder, default 0) | `{"var": "turn_count", "op": "mod", "value": 5, "result": 0}` |

**Condition Evaluation Safety:** Condition evaluation **never raises exceptions**. If a comparison fails due to type mismatch or invalid operation, the condition evaluates to `False`. As of v2.2, the evaluator **fails closed** on edge cases that previously fired the agent: an unknown/typo'd operator returns `False` (C-1, was fail-open); membership operators (`in`/`not_in`/`contains`) guard on `expected is None` rather than truthiness so a legitimately-falsy `expected` (e.g. `0`, `""`) still runs a real membership test (C-2); and `mod` with a zero divisor returns `False` locally instead of leaking a `ZeroDivisionError` (C-3).

### 3.5 Trigger System

Agents define *when* they want to wake up via `AgentConfig`:

| Type | When Fired | Use Case |
|------|------------|----------|
| `TURN_BASED` | Host calls `process_turn()` | After speech segment completes |
| `KEYWORD` | Keyword detected in transcript | Immediate reaction to specific terms |
| `SILENCE` | Silence duration exceeds threshold | Dead air intervention |
| `INTERVAL` | Time-based periodic check | Background monitoring |
| `EVENT` | Another agent emits a Blackboard event | Agent coordination |
| `FORCE` | User-triggered via host | Bypasses cooldown and conditions |

**DynamicAgent convenience (v2.1.1):** When a `DynamicAgent` is constructed with `subscribed_events` but `TriggerType.EVENT` is not in `trigger_types`, the framework auto-adds `TriggerType.EVENT`. This prevents a common misconfiguration where agents subscribe to events but never receive them. The engine's `get_event_subscribers()` validates this invariant and logs a warning for any non-DynamicAgent agents that have `subscribed_events` without `EVENT` trigger type.

**KEYWORD Trigger Note:** The engine does **not** automatically scan transcript text for keywords. Keyword detection is **host responsibility**. The engine provides `check_keyword_triggers(text)` as a helper utility.

### 3.6 LLM Client (`core/llm.py`)

A thin wrapper around `AsyncOpenAI`. The framework targets **OpenAI / OpenAI-compatible** endpoints; a dedicated Anthropic SDK adapter is explicitly out of scope for this release.

- **Abstraction:** Centralizes API key management and client initialization.
- **JSON Enforcement:** Enforces `response_format={"type": "json_object"}` to ensure agents return structured data.
- **OpenAI-compatible:** Works with OpenAI and any OpenAI-compatible endpoint.
- **Resilience (v2.2 — R-1, INV-10):** Every call is time-bounded by a per-request `timeout` (default `10.0s`), retries transient failures (429 / 5xx / connection / timeout) with the SDK's exponential backoff (`max_retries`, default `2`), and caps output via `max_tokens` (default `1024`). Failures are mapped to **typed, logged categories** — `timeout`, `rate_limit`, `auth`, `server`, `misconfig`, `truncated`, `malformed`, `not_initialized`, `unknown` — the last two categories added in v2.5 (INV-16: a 4xx parameter/model rejection is `misconfig`, not an outage; a length-stopped response is `truncated`, not bad JSON). The public contract is preserved: `generate_json` **never raises into the turn** and returns the parsed dict on success or `None` on any failure.
- **Wire compatibility (v2.5 — WC-1):** the token cap ships as `max_completion_tokens` (required by reasoning models; accepted by current non-reasoning models). The Python parameter name stays `max_tokens`. Legacy OpenAI-compatible proxies can pin `wire_max_tokens_param="max_tokens"` (ctor-validated).
- **Per-call attribution (v2.5 — OB-2, INV-17):** `generate()` returns an `LLMResult` (`parsed`, `error_category`, `usage`, `finish_reason`) so concurrent agents on the shared client attribute outcomes per call; `usage` holds plain token ints (incl. `reasoning_tokens`/`cached_tokens` when reported) and is populated even on billed failures (`truncated`/`malformed`). `generate_json` is a thin delegate; `last_error_category` remains as a deprecated best-effort mirror.

```python
@dataclass(frozen=True)
class LLMResult:
    parsed: Optional[Dict[str, Any]] = None
    error_category: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    finish_reason: Optional[str] = None

class LLMClient:
    def __init__(self, api_key: Optional[str] = None,
                 timeout: float = 10.0,
                 max_retries: int = 2,
                 max_tokens: int = 1024,
                 wire_max_tokens_param: str = "max_completion_tokens",
                 base_url: Optional[str] = None)              # v2.6 EN-1
    async def generate_json(self, model: str, messages: list,
                            max_tokens: Optional[int] = None,
                            timeout: Optional[float] = None,
                            reasoning_effort: Optional[str] = None,     # v2.6 RC-1
                            extra_params: Optional[Dict[str, Any]] = None  # v2.6 RC-2
                            ) -> Optional[Dict[str, Any]]
    async def generate(self, model: str, messages: list,
                       max_tokens: Optional[int] = None,
                       timeout: Optional[float] = None,
                       reasoning_effort: Optional[str] = None,
                       extra_params: Optional[Dict[str, Any]] = None) -> LLMResult
    last_error_category: Optional[str]  # DEPRECATED mirror (racy under gather); use LLMResult
```

- **Per-agent config (v2.6 — RC-1/RC-2/RC-3, INV-15):** `AgentConfig` carries optional `reasoning_effort` / `timeout` / `max_tokens` / `model_params`. `DynamicAgent` forwards them **only when set** — the framework never injects; omission leaves the model's own default. `model_params` merges with framework-owned keys winning; collisions are rejected at config load (`AgentConfigurationError`).
- **Load-time validation (v2.6 — VL-1, INV-19; D-1 ruling):** `AgentEngine.register_agent`/`replace_agents` hard-fail (`AgentConfigurationError`) when a model matching the advisory reasoning heuristic lacks explicit `reasoning_effort` (warn-only under `AgentEngine(strict_reasoning_config=False)`); budget/sampling mismatches warn once per agent id. `replace_agents` is all-or-nothing — one bad config rejects the reload and the old registry keeps serving.
- **Engine LLM knobs (v2.6 — EN-1, INV-18):** `AgentEngine(llm_timeout=, llm_max_retries=, llm_max_tokens=, llm_base_url=, llm_wire_max_tokens_param=, strict_reasoning_config=)`. The resolved set persists across `update_api_key` — key rotation never resets the client to module defaults.

---

## 4. Data Models (`core/models.py`)

### 4.1 AgentContext

The input payload delivered to an agent during execution.

```python
class AgentContext(BaseModel):
    session_id: str
    recent_segments: List[TranscriptSegment]
    
    # State (v1 compatibility)
    shared_state: Dict[str, Any] = {}
    
    # Blackboard (v2) — structured state
    blackboard: Optional[Blackboard] = None
    
    # Trigger information (set by engine)
    trigger_type: TriggerType = TriggerType.TURN_BASED
    trigger_metadata: Dict[str, Any] = {}
    
    # Context enrichment
    rag_docs: List[str] = []
    user_context: Optional[str] = None
    language_directive: Optional[str] = None
    
    # Execution metadata (read-only, set by engine)
    turn_count: int = 0
    phase: int = 1  # Which execution phase (1 = normal, 2 = event-triggered)

    # Role overrides (per-agent config modifications from Roles)
    agent_config_overrides: Dict[str, AgentConfigOverride] = {}
```

**Note:** `agent_config_overrides` keys are agent config IDs (engine agent IDs, not role IDs). See `AgentConfigOverride` below.

### 4.1.1 AgentConfigOverride

Per-agent configuration overrides applied by Roles. Uses `extra="forbid"` to reject unknown keys at construction time.

```python
class AgentConfigOverride(BaseModel):
    cooldown_modifier: Optional[int] = None       # +N = slower, -N = faster (floor 5s)
    context_turns_modifier: Optional[int] = None   # +N = more context, -N = less (<=0 = all)
    instructions_append: Optional[str] = None      # Extra instructions appended to system prompt
```

### 4.2 AgentResponse

The output payload returned by an agent.

```python
class AgentResponse(BaseModel):
    # Agent identity (v2.1 — set by framework, used for merge ordering)
    source_agent_id: Optional[str] = None

    # Core output
    insights: List[AgentInsight] = Field(default_factory=list)

    # Blackboard updates (v2)
    events: List[Event] = Field(default_factory=list)
    variable_updates: Dict[str, Any] = Field(default_factory=dict)
    queue_pushes: Dict[str, List[Any]] = Field(default_factory=dict)
    facts: List[Fact] = Field(default_factory=list)
    memory_updates: Dict[str, Any] = Field(default_factory=dict)

    # Per-agent keyed memory (v2.1.1 — populated on aggregated responses from process_turn)
    memory_updates_by_agent: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    # Legacy compatibility (v1)
    state_updates: Dict[str, Any] = Field(default_factory=dict)

    # Sidecar data
    data: Dict[str, Any] = Field(default_factory=dict)
    debug_info: Dict[str, Any] = Field(default_factory=dict)

    # Acceptance (XUBB-ITC-1 G0 — engine-derived, never model-authored)
    execution_id: Optional[str] = None
    acceptance_status: Literal["accepted", "accepted_silent", "partial", "rejected"] = "accepted"
    diagnostics: List[InsightDiagnostic] = Field(default_factory=list)
    acceptance_by_agent: Dict[str, str] = Field(default_factory=dict)   # aggregated response only
```

**Note:** `source_agent_id` is stamped automatically by `BaseAgent.process()`. It is used by the engine for merge ordering and memory attribution. Agents should not set it manually.

**Typed acceptance (G1, `AgentEngine(insight_contract="typed_v1")`, `docs/SPEC_INSIGHT_TYPES.md` §6, §8.4):** the model's candidate is validated strictly against the normalized contract (exact wire-value type within the run's effective set, strict confidence, urgency precedence, no engine-owned or unknown keys); any defect, malformed gate or invalid domain payload rejects the whole response (atomic). Accepted insights are stamped by the engine with a session-unique `id`, `turn`, `contract_version`, a resolved `urgency` and runtime-derived `confidence_provided`. The instruction sent to the model is generated per run from the effective set. Requires a schema with a typed adapter (`insight_v1`, `default_v2`, `v2_raw`). In this release the six ordinary purposes are accepted; interactive types and long-form fields remain unavailable and are rejected with a diagnostic.

**Provider structured outputs (G2, §13.3):** `AgentEngine(structured_outputs="strict" | "auto" | "json_object")` is an independent transport control (default `auto`). On the `insight_v1` adapter a typed run sends a strict `json_schema` projection compiled from the shipped contract (`library/contract/`), restricted to the effective enum and linted before the call; open dictionaries travel as `map_entries_v1` and are decoded losslessly before local validation. `strict` never downgrades; `auto` may downgrade once per endpoint/model/adapter/schema-version key, only on a 400 that exactly matches an operator-enabled, evidence-backed signature (`fallback_signatures=[...]`; the shipped registry enables none), and reports it as `unsupported_structured_output`. Everything else fails closed. Refusals are the `refusal` category. Local validation is mandatory regardless of transport.

**Replies and questions (G3, §9, §11):** under `typed_v1`, `reply` is a draft for the principal, available only with `allow_reply`, host `reply_drafts` and an explicit `principal_id`; the engine invokes nothing for it. `question` needs `allow_question`, host `text_questions`, a principal and a `question.reason`; its engine-assigned id correlates the host's `AgentContext.insight_answers` events, which the engine validates at turn start (same session, active question, same principal, answered ⇒ text, dismissed ⇒ none; batch duplicates and conflicts rejected) and exposes only to the originating agent unless `answers_shared`. A dismissal is not consent; answers are data and schedule nothing.

**Corrections (G3, §10):** `correction` repairs the assistant's OWN earlier message. It needs `allow_correction`, host `corrections` and retained history; the target is validated at the engine boundary (emitted earlier turn, same session, active, same principal; own-agent authority unless the host allowlists the agent), a separate evidence basis must resolve, and violations reject the whole response. At phase close, before anything commits, correction-bearing responses are arbitrated by descending priority then later registration: all targets or nothing, losers rejected whole with `correction_conflict`, earlier-phase reservations standing. Marking the target superseded or withdrawn in the interface is the host's obligation.

**Long-form content (C1, §14.4–§14.10):** an agent opts into `long_form_v1` with `insight_config.content` (depth profiles with character, token and timeout budgets, formats, preview limit); the host declares `content_contracts`, `content_formats`, `expanded_reading` and limits, the schema adapter (`insight_v1`) declares the contract, and the engine carries operator `content_limits` (finite `max_response_bytes`, live ceilings). Depth is the host's `insight_content_requests[agent]` or the agent default. Admission runs BEFORE generation against the host's trusted `content_execution_context`: active sessions admit only `brief` within the live ceilings; extended depth needs a declared pause or post-session execution; the isolated active path is refused until C2. The profile's budget becomes the call budget. Afterwards the complete body (`content`) and optional `preview` are checked against exact decoded-character and transport-byte ceilings with nothing shortened; only a `stop`-finished generation may emit (`length` → `incomplete_generation`, unreported → `completion_unknown`); rejections are atomic. Negotiated insights carry `content_contract`, `response_depth`, `content_request_id`, `preview`, `content_format`; the legacy projection omits them. Reading retention, safe rendering and expand-without-generation are host obligations.

**Engine boundary (H1):** `_enforce_acceptance` is the one acceptance pipeline for every producer. It shape-revalidates the domain channels of the response object that would commit (both contracts; fatal → whole rejection), then under `typed_v1` re-runs the strict candidate validator on the producer-controlled projection of every insight, requires every engine-owned public field to be unset (trusted staging hands provenance and content-contract values over through the private `_staged` slot), resolves references against the host records plus the run's own snapshot held by the agent, validates correction targets under the frozen principal, and only then stamps `id`, `turn`, `contract_version`, `confidence_provided` and the content fields. Each agent receives its own invocation view (`_scoped_view`) whose `insight_answers` are already scoped to its questions unless the host authorised sharing. Typed evaluation failures surface as `invalid_envelope` diagnostics, never as insights.

**Isolated content tasks (C2, §14.6.1):** `AgentEngine.start_content_request(context, agent_id, InsightContentRequest)` returns a `ContentTaskHandle` whose task runs extended generation outside the live turn: a fresh `DynamicAgent` instance cloned from its definition, a frozen deep copy of the context, and an engine-issued isolated declaration (host-authored ones are refused). It never writes the live Blackboard or private memory, never bumps the live turn counter or reserves correction targets, and fires no turn callbacks; live turns proceed concurrently. `await handle.result()` yields a `ContentResult` (request id, source snapshot id, snapshot turn, status, single insight, diagnostics, usage) — result-only: effects or interactive types reject it. Admission is bounded by `content_limits.max_concurrent_content_tasks`; `handle.cancel()` or `close_session_content(session_id)` revokes publication. The host checks currentness against the snapshot id before presenting.

**Content entrypoint and lifecycle (H2):** `start_content_request` admits before it allocates — typed contract, isolatable agent, the agent's pure `content_admission` for this request under the engine's own declaration, capacity — and returns a task-less handle carrying a rejected result otherwise. Capacity is an explicit counter reserved at the entrypoint and released by the task's done-callback on every exit; completed handles leave the pending registry. The generated instruction derives its forbidden fields from the run's descriptor and exposes citation ids whenever an enabled type needs evidence. Content-policy numerics are strict at construction.

**Evidence (G2, §6.3–§6.4):** for every typed invocation the framework builds a snapshot catalog of what the agent actually saw after trimming (`snap:<id>:segment:<n>`, `snap:<id>:document:<n>`; one entry per occurrence), merged with the host's `AgentContext.insight_reference_context` (documents, facts, prior emitted insights). An `evidence_refs` entry resolves only to a catalog entry at its revision; unknown ids, stale revisions and other sessions' entries reject. Consulting hypotheses need evidence, rationale and a validation step; implications need evidence and rationale; general observations need no evidence. The invocation snapshot is returned as `AgentResponse.evidence_snapshot` for hosts that retain revisions.

**Acceptance (G0, `docs/SPEC_INSIGHT_TYPES.md` §8.6 / D-LR):** every agent response is validated at the engine boundary. On the default `legacy_v2` path a *recoverable insight error* (malformed gate, unknown or disallowed type, invalid insight field) rejects all insights from that result — never relabels them — while independently validated, authorized domain channels still commit with status `partial` (action-bearing `data` sidecars are withheld). *Fatal* rows (invalid domain payload, an agent-proposed `sys.*` write, an unparseable envelope) reject the whole response. A valid `false` gate is `accepted_silent`. `diagnostics` rows are sanitized (`InsightDiagnostic`: execution id, agent, code, field path, bounded classification, retained/withheld channels) and the engine fires `on_insight_validation_error` once per partial/rejected result. Parsing never mutates `private_state` or the Blackboard; memory commits only through the engine merge.

**Note:** `memory_updates_by_agent` is only populated on the aggregated `AgentResponse` returned by `process_turn()`. Individual agent responses use `memory_updates` (flat dict). The engine collects per-agent memory writes and keys them by `agent_id` on the final response, so consumers can inspect which agent wrote which memory keys without parsing the flat merge.

### 4.3 AgentInsight

```python
class AgentInsight(BaseModel):
    agent_id: str
    agent_name: str
    type: InsightType
    content: str
    confidence: float = 1.0
    expiry: int = 15  # Seconds to display
    action_label: Optional[str] = None
    metadata: Dict[str, Any] = {}
```

**Insight Types** (XUBB-ITC-1 §3 — a type names the message's *purpose*, never a surface, urgency or permission; `HUMAN_INSIGHT_TYPES` is the canonical nine-tuple, `INSIGHT_TYPE_LABELS` the display map):
- `INFORMATION` (alias of `FACT`, wire value `"fact"`): relevant information without added interpretation
- `OBSERVATION`: a grounded interpretation, pattern or synthesis *(G1 member; unavailable until `typed_v1`)*
- `SUGGESTION`: a recommended action, approach or course of action
- `WARNING`: a material risk, adverse consequence or constraint
- `OPPORTUNITY`: a favourable opening or potential benefit
- `PRAISE`: recognition of specific effective behaviour
- `REPLY`: optional wording for the principal to say to a counterpart *(G1 member; permissioned, unavailable until `typed_v1`)*
- `CORRECTION`: explicit repair/withdrawal of earlier assistant assistance *(G1 member; permissioned, unavailable until `typed_v1`)*
- `QUESTION`: a request from the assistant to the principal for input *(G1 member; permissioned, unavailable until `typed_v1`)*
- `ERROR`: Framework-manufactured diagnostic only (G0): content is the sanitized category `agent_error`, metadata carries the exception class name, the exception text lives only in the non-serializing `debug_info`. Never offered to a model; a model-authored `"error"` is rejected (`type_not_allowed`), and an agent-authored ERROR insight is dropped at the engine boundary (runtime provenance).

> **Type labels on the legacy path (G0):** an absent type defaults to `suggestion` (declared adapter default); labels are case-folded; any other unrecognised label is `unknown_type` and `observation` / `reply` / `correction` / `question` are `type_not_allowed` until the typed contract (`typed_v1`, gate G1) is selected. Unknown labels are never relabelled. The full nine-purpose vocabulary is specified in `docs/SPEC_INSIGHT_TYPES.md` §3.

### 4.4 Event (NEW in v2.0)

```python
class Event(BaseModel):
    name: str                           # Event name: "question_detected"
    payload: Dict[str, Any] = {}        # Event data
    source_agent: str                   # Which agent emitted it
    timestamp: float                    # When it was emitted (session-relative)
    id: Optional[str] = None            # Optional unique ID for tracing
```

### 4.5 Fact (NEW in v2.0)

```python
class Fact(BaseModel):
    type: str                  # Category: "budget", "timeline", "contact"
    key: Optional[str] = None  # Instance key: "budget.primary", "stakeholder.cfo"
    value: Any                 # The extracted value
    confidence: float = 1.0    # Extraction confidence
    priority: int = 0          # v2.2 — engine-stamped emitting-agent priority (conflict resolution)
    source_agent: str          # Which agent extracted it
    timestamp: float           # When it was extracted (session-relative)
```

**Deduplication & conflict resolution (v2.2 — F-1, INV-9):** Facts are deduplicated by `(type, key)` (by `type` alone when `key is None`). When duplicates collide, the winner is decided by **priority** first, then **confidence**, then **registration order**. The engine stamps each fact's `priority` from the emitting agent at merge time, so `Blackboard.add_fact` resolves the conflict self-sufficiently regardless of call order; agents should not set `priority` themselves. Hosts calling `add_fact()` directly own the field (it defaults to `0`).

> **Note:** Prior to v2.2, `add_fact` resolved collisions by **confidence only**, which could silently let a lower-priority/higher-confidence agent overrule a high-priority authoritative extractor. v2.2 corrects this to honor the always-documented precedence. `priority` is additive and defaulted, so serialized v2.1.1 facts load unchanged.

### 4.6 TranscriptSegment

```python
class TranscriptSegment(BaseModel):
    speaker: str       # Who spoke? Any string
    text: str          # The text content
    timestamp: float   # Seconds since session start (session-relative)
    is_final: bool = True  # Is this segment complete?
```

---

## 5. Execution Flow

### 5.1 Multi-Phase Execution

```
Host calls process_turn(context)
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 1: Primary Execution                                       │
│                                                                  │
│  For each registered agent:                                      │
│    1. Check trigger type match                                   │
│    2. Check cooldown                                             │
│    3. Check trigger conditions (against Blackboard)              │
│    4. If all pass → Run agent (LLM call)                        │
│    5. Collect response                                           │
│                                                                  │
│  After all agents complete:                                      │
│    - Merge variable_updates into Blackboard                      │
│    - Process queue_pushes                                        │
│    - Add facts (with deduplication)                              │
│    - Update agent memories                                       │
│    - Collect emitted events                                      │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
                    Any events emitted?
                               │
                ┌──────────────┴──────────────┐
                │ NO                          │ YES
                ▼                             ▼
        Skip Phase 2              ┌───────────────────────────┐
                │                 │ PHASE 2: Event Handling    │
                │                 │                            │
                │                 │  Find agents subscribed    │
                │                 │  to emitted events         │
                │                 │           │                │
                │                 │  For each subscribed agent:│
                │                 │    1. Check cooldown       │
                │                 │    2. Check conditions     │
                │                 │    3. Run agent            │
                │                 │           │                │
                │                 │  Merge responses           │
                │                 │  (No further event phases) │
                │                 └─────────────┬──────────────┘
                │                               │
                └───────────────┬───────────────┘
                                │
                                ▼
                      Clear transient events
                                │
                                ▼
                      Return AgentResponse
```

### 5.2 Agent Eligibility Check

```
Is Agent Eligible to Run?
         │
         ▼
┌─────────────────────┐
│ Trigger Type Match? │───No───▶ Skip (not for this trigger)
└─────────┬───────────┘
          │ Yes
          ▼
┌─────────────────────┐
│ Cooldown Clear?     │───No───▶ Skip (cooling down)
└─────────┬───────────┘
          │ Yes
          ▼
┌─────────────────────┐
│ Conditions Pass?    │───No───▶ Skip (preconditions not met)
└─────────┬───────────┘
          │ Yes
          ▼
┌─────────────────────┐
│ Run Agent (LLM)     │
└─────────────────────┘
```

### 5.3 State Update Priority (Merge Ordering)

Updates are applied in **ascending priority order** (low → high) so that **higher-priority agents write last and therefore win** (last-write-wins semantics).

```python
# Agent A (priority=5): variable_updates={"phase": "closing"}
# Agent B (priority=10): variable_updates={"phase": "negotiation"}
# Result: phase = "negotiation" (Agent B wins)
```

### 5.4 Phase Depth Limit

To prevent infinite event cascades:
- **Supported phases:** `max_phases` accepts only **1** (Phase 1 only) or **2** (Phase 1 + event-triggered Phase 2). As of v2.2 (E-7), any other value is clamped (`<1` → `1`, `>2` → `2`) with a warning, rather than being silently ignored. `AgentEngine(max_phases=2)` is the default. No Phase 3+ exists.
- `max_phases=1` disables the event-triggered Phase 2 entirely
- Phase 2 agents **cannot** trigger Phase 3
- Events emitted in Phase 2 are recorded for telemetry but not dispatched
- All events are cleared after `process_turn()` completes
- **Phase-2 exception safety (v2.2 — E-1, INV-12):** the engine restores the host-owned `context.trigger_type` and `context.phase` via `try/finally`, so a Phase-2 failure can never leave a host-reused context corrupted as `EVENT`/`phase=2`

### 5.5 Agent Failure Atomicity

Agent execution is **atomic** with respect to state updates:
- If an agent errors during evaluation, **none** of its state updates are applied
- The agent is isolated from the system state
- An `ERROR` insight may be emitted instead
- Other agents continue normally
- **v2.1:** Cooldown is always enforced after an execution attempt (success or failure), preventing runaway retries on persistent errors

---

## 6. Dynamic Agent Execution Flow (`library/dynamic.py`)

The `DynamicAgent` is the primary implementation used for user-defined agents.

### 6.1 Execution Lifecycle

1.  **Memory Loading (cross-turn persistent memory):**
    - `DynamicAgent` reads its persistent memory from `context.shared_state["memory_{agent_id}"]`.
    - **v2.2 (MR-1):** the engine populates that key from the authoritative blackboard store (`blackboard.memory[agent_id]`, deep-copied) via `_sync_state_to_legacy` *before* agents run, so committed memory survives across turns even when the host re-instantiates agents each turn. Previously, cross-turn memory survived only via an agent's in-process `private_state` and was silently lost on per-turn re-instantiation.
    - The loaded persistent memory is merged over a copy of `private_state` into a local `working_memory` for the evaluation (the agent's `private_state` is not mutated during prompt assembly).

2.  **Context Construction:**
    - Slices transcript based on `context_turns`
    - Injects `user_context` (User Persona) — **only if `include_context: true`**
    - Injects `language_directive` (Language Constraints) — always injected
    - Injects RAG documents if present — **only if `include_context: true`**
    - Injects Trigger Metadata
    - Injects Blackboard state for Jinja2 templating

    > **Note:** When `include_context` is `false` (default: `true`), the `user_context` and `rag_docs` sections are omitted from the system prompt. This saves tokens for agents that don't need user profile or document context (e.g., widget trackers). The host still provides these fields in `AgentContext` — the gating happens at prompt composition time inside `DynamicAgent.evaluate()`.

3.  **Prompt Templating (Jinja2 — Sandboxed):**

    As of v2.1, templates are rendered via a **class-level** `jinja2.sandbox.SandboxedEnvironment` (single instance shared across all DynamicAgent instances, avoiding per-call allocation). Access to Python internals (`__class__`, `__globals__`, `__mro__`) is blocked.

    ```python
    rendered_prompt = template.render(
        # v1.0 variables (preserved)
        state=context.shared_state,
        memory=working_memory,      # local copy, not self.private_state
        context=context,
        user_context=context.user_context,

        # v2.0 variables (new)
        blackboard=context.blackboard,
        agent_id=self.config.id,
    )
    ```

4.  **LLM Call:**
    - Sends rendered prompt with JSON enforcement
    - Parses response according to `output_format` schema

5.  **Response Processing:**
    - Extracts insights, events, variable_updates, queue_pushes, facts, memory_updates
    - Maps v1.0 `state_updates` to `variable_updates` for compatibility
    - **Silence gate (v2.2 — A-1, INV-11):** whether the agent speaks is decided by the schema's gate, in precedence order: (a) `check_field` present → the boolean gate drives the decision; (b) no `check_field` but `root_key` present → a non-empty root object is the gate; (c) gate-less **and** rootless → defaults to **silence** unless the schema opts in via `"speak_without_gate": true`. A load-time warning fires if the instruction references a gate field but the mapping omits `check_field`.
    - **v2.2 (A-3):** model-supplied `confidence` is coerced to float and clamped to `[0, 1]` (default `1.0` on a non-numeric value) so a bad value never turns a good insight into a validation error.
    - **v2.2 (S-1):** `expiry` and `action_label` returned by the model are parsed and passed through to the `AgentInsight` (previously requested by schemas but dropped).
    - **v2.2 (A-2, INV-13):** `Event`/`Fact` timestamps are stamped session-relative (derived from the most recent transcript segment) rather than wall-clock epoch.

6.  **State Persistence:**
    - Updates `private_state` from `memory_updates`
    - Engine merges all updates into Blackboard

### 6.2 Output Schemas

Located in `library/schemas/` (shipped: `default`, `default_v2`, `v2_raw`, `ui_control`, `widget_control`, `custom1`):

- **`default`**: Standard flat schema (`has_insight`, `content`, `type`) — gated by `check_field`
- **`default_v2`**: Default flat schema plus the full v2 update fields; gated by `check_field: has_insight` and writes state via `variable_updates`
- **`v2_raw`**: Structured schema with full v2 fields, gated by presence of its root object
- **`ui_control`** / **`widget_control`**: Root-keyed schemas that map UI actions to the `response.data` sidecar
- **Custom**: Create `library/schemas/my_schema.json` for custom formats

> **v2.2 (S-3):** all v2 schemas route state through `variable_updates_field`, so a v2-only host reading `variable_updates` no longer misses updates that previously went only through the v1 `state_updates` path. The dead `is_state_at_root` key (S-2) was removed from all schemas — it was never read by the parser.

> **v2.2 (A-1):** a custom schema that has neither a `check_field` gate nor a `root_key` defaults to **silence**; set `"speak_without_gate": true` in its mapping to opt into "speak whenever there is content." See §6.1 step 5.

---

## 7. Observability & Debugging

### 7.1 Callback System (`core/callbacks.py`)

Consumers can register handlers to receive real-time events:

```python
class AgentCallbackHandler:
    """Base handler — override only the methods you care about. All are no-op by default."""
    async def on_turn_start(self, context: AgentContext) -> None
    async def on_turn_end(self, response: AgentResponse, duration: float) -> None
    async def on_agent_start(self, agent_name: str, context: AgentContext) -> None
    async def on_agent_finish(self, agent_name: str, response: Optional[AgentResponse],
                              duration: float) -> None
    async def on_agent_error(self, agent_name: str, error: Exception) -> None
    async def on_agent_skipped(self, agent_name: str, reason: str) -> None
    async def on_phase_start(self, phase: int, agent_names: List[str]) -> None
    async def on_phase_end(self, phase: int, event_names: List[str]) -> None
    async def on_chain_error(self, error: Exception) -> None
```

**Callback failure policy:** Callback failures are non-fatal. They are logged at `ERROR` level and never abort turn processing or suppress agent output.

**`on_chain_error` firing (v2.1.1):** `process_turn()` is wrapped in a try/except that calls `on_chain_error` on all registered callbacks before re-raising. This ensures observers are notified of unhandled exceptions (e.g., for alerting or metrics). If a callback itself raises during `on_chain_error`, that failure is logged but does not mask the original exception.

### 7.2 Structured Tracing (`utils/tracing.py`)

The `StructuredLogTracer` is an `AgentCallbackHandler` that accumulates a per-turn trace across the callback lifecycle (`on_turn_start` → `on_agent_finish`/`on_agent_error` → `on_turn_end`) and emits it as a single JSON log line prefixed `TURN_TRACE:` at `INFO` (serialized with `default=str` so non-serializable values never crash the log).

The emitted object is **flat** with a `steps[]` array (one entry per agent), not the nested `phases[]` structure of earlier drafts. The actual shape:

```json
{
  "session_id": "session_123",
  "trigger": "turn_based",
  "trigger_metadata": {},
  "input_preview": "What's your pricing?",
  "speaker": "CUSTOMER",
  "timestamp_start": 1730000000.123,
  "user_context": "Sales Director at Acme Corp",
  "language_directive": "Respond in English",
  "rag_docs": ["..."],
  "initial_shared_state": { "phase": "negotiation" },
  "transcript_history": [ { "speaker": "CUSTOMER", "text": "...", "timestamp": 12.4, "is_final": true } ],

  "steps": [
    {
      "agent": "question_extractor",
      "latency_ms": 450.0,
      "status": "success",
      "insights": [
        { "type": "suggestion", "content": "...", "confidence": 0.85, "metadata": {} }
      ],
      "state_updates": { "phase": "negotiation" },
      "variable_updates": ["phase"],
      "events_emitted": ["question_detected"],
      "facts_count": 1,
      "queue_pushes": { "pending_questions": 2 },
      "memory_updates_keys": ["last_question"],
      "data": {},
      "debug_info": {}
    },
    {
      "agent": "escalation_monitor",
      "status": "error",
      "error": "..."
    }
  ],

  "total_latency_ms": 1660.0,
  "final_insight_count": 1,
  "final_state_updates": {}
}
```

Notes on the per-step (`steps[]`) fields — each is included **only when present** on that agent's response:
- `latency_ms`, `status` (`"success"` / `"no_response"`, or `"error"` with an `error` string) are always present.
- `state_updates` is the raw v1 dict; `variable_updates` is the **list of changed variable keys** (not the values); `events_emitted` is the list of event names; `facts_count` is an integer count; `queue_pushes` maps queue name → number of items pushed; `memory_updates_keys` is the list of memory keys written.
- `data` and `debug_info` are passed through when the response carries them.

The turn-level fields (`total_latency_ms`, `final_insight_count`, `final_state_updates`) are written on `on_turn_end`. The trace does not currently emit a nested per-phase breakdown or a `blackboard_final` snapshot.

### 7.3 Timestamp Conventions

| Context | Format | Notes |
|---------|--------|-------|
| Model timestamps (`TranscriptSegment`, `Event`, `Fact`) | Seconds since session start | Float, session-relative (v2.2 — A-2 emits `Event`/`Fact` session-relative, not epoch) |
| Trace `timestamp_start` | Wall-clock epoch seconds | Float from `time.time()` (not ISO 8601) |
| Latency / duration fields | Milliseconds | Float, e.g., `latency_ms: 450.0`, `total_latency_ms: 1660.0` |

---

## 8. Directory Structure

```
xubb_agents/
├── core/
│   ├── __init__.py
│   ├── agent.py           # BaseAgent, AgentConfig
│   ├── engine.py          # AgentEngine (orchestrator)
│   ├── blackboard.py      # Structured Blackboard
│   ├── conditions.py      # Trigger condition evaluator
│   ├── llm.py             # LLM client wrapper
│   ├── models.py          # Pydantic data models
│   └── callbacks.py       # Callback protocol
├── library/
│   ├── __init__.py
│   ├── dynamic.py         # DynamicAgent implementation
│   └── schemas/           # Output format schemas
│       ├── default.json
│       ├── v2_raw.json
│       └── ...
├── utils/
│   ├── __init__.py
│   └── tracing.py         # Structured logging
├── docs/
│   ├── technical_spec_agents.md    # This document
│   ├── prompt_engineering_guide.md # Prompt writing guide
│   ├── EXECUTIVE_SUMMARY.md        # Strategic overview
│   ├── CONTRACTS.yaml              # Contract registry (live, machine-checkable)
│   ├── SPEC_V2_2_HARDENING.md      # Current spec (v2.2)
│   └── archive/                    # Superseded specs (v2.0 / v2.1 / v2.1.1)
│       ├── SPEC_V2.md
│       ├── SPEC_V2_1_HARDENING.md
│       └── SPEC_V2_1_1_BUGFIX.md
├── __init__.py
├── README.md
└── CHANGELOG.md
```

---

## 9. Integration Guide (For Consumers)

### 9.1 Basic Integration

```python
from xubb_agents import AgentEngine, AgentContext, TriggerType, Blackboard
from xubb_agents.library import DynamicAgent

# Initialize Engine
engine = AgentEngine(api_key="...")

# Register Agents
for config in load_agents_from_db():
    engine.register_agent(DynamicAgent(config))

# Session State
session = {
    "id": "session_123",
    "blackboard": Blackboard(),
    "turn_count": 0,
    "segments": []
}

# Process Turn
async def on_transcript(segment):
    session["segments"].append(segment)
    session["turn_count"] += 1
    
    context = AgentContext(
        session_id=session["id"],
        recent_segments=session["segments"][-100:],
        blackboard=session["blackboard"],
        turn_count=session["turn_count"]
    )
    
    response = await engine.process_turn(
        context, 
        trigger_type=TriggerType.TURN_BASED
    )
    
    for insight in response.insights:
        await send_to_ui(insight)
```

### 9.2 Keyword Handling

```python
# Check keywords (host responsibility)
matches = engine.check_keyword_triggers(text)
allowed_ids = [agent.config.id for agent, kw in matches]

# Trigger keyword agents
response = await engine.process_turn(
    context,
    allowed_agent_ids=allowed_ids,
    trigger_type=TriggerType.KEYWORD
)
```

### 9.3 Handling Events

Event-triggered agents run automatically in Phase 2 when other agents emit events. No host intervention required.

---

## 10. Backward Compatibility (v1.0 Migration)

### 10.1 Compatibility Guarantees

| v1.0 Pattern | v2.0 Equivalent | Auto-Mapped? |
|--------------|-----------------|--------------|
| `context.shared_state["key"]` | `context.blackboard.variables["key"]` | ✅ Yes |
| `response.state_updates` | `response.variable_updates` | ✅ Yes |
| `state_updates["memory_X"]` | `blackboard.memory["X"]` | ✅ Yes |
| `{{ state.key }}` in prompts | `{{ blackboard.variables.key }}` | ✅ Both work |
| All v1.0 trigger types | Same + new EVENT type | ✅ Yes |

### 10.2 Migration Path

1. **No immediate changes required** — v1.0 agents work unchanged
2. **Gradual adoption:**
   - Replace `state_updates` with `variable_updates`
   - Add `trigger_conditions` to reduce LLM calls
   - Add `events` emission for agent coordination
3. **Full migration:**
   - Use `facts` for extracted knowledge
   - Use `queues` for work items
   - Use `blackboard.*` in templates

---

## 11. Current Limitations

1. **Local LLM Support:** The `LLMClient` is for OpenAI-compatible APIs. Local model loading not yet implemented.
2. **Session Persistence:** Framework maintains in-memory Blackboard only. Host responsible for durable persistence.
3. **Phase Depth:** Maximum 2 phases per turn (no event cascades).
4. **Streaming:** Not yet supported.

---

## 12. Future Considerations

| Feature | Description | Complexity |
|---------|-------------|------------|
| **Tool/Function Calling** | Agents can call external APIs | High |
| **Streaming Responses** | Show insights as agents complete | Medium |
| **Session Persistence** | Built-in persistence layer | Medium |
| **Structured RAG** | `RAGDocument` model with metadata | Low |
| **MCP Integration** | Model Context Protocol support | High |
| **AgentConfig → Pydantic** | Type-safe config validation (NP3) | Medium |
| **`collections.deque` queues** | O(1) pop for high-volume queues (NP14) | Low |
| **Differentiated retry** | Error classification + per-category cooldowns | Medium |
