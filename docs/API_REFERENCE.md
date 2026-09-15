# API reference

**Applies to runtime:** 3.1.5 · **Surface declared in:** [`api/inventory.yaml`](api/inventory.yaml)

This page is written by hand, and the fact tables in it are generated from the shipped code.
Neither half is trusted on its own: `tools/check_api_docs.py` fails the build when a public
member is undeclared, when a declared member no longer exists, when a generated table is stale,
or when a declared name has nowhere to be read.

> **The tables tell you what a member *is*. The prose tells you what it *means*.** A signature
> cannot say who owns a field, when it is populated, or what happens when it is wrong — and
> those are the things that have actually misled readers here. Where the two appear to
> disagree, the code is right and this page has a bug; please file it.

## Three things to hold apart

Most confusion in this API comes from collapsing these.

| | What it is | Who writes it |
|---|---|---|
| **Provider envelope** | The JSON a model returns, shaped by the agent's output format | The model, within a contract the engine generates |
| **Python response model** | `AgentResponse` and `AgentInsight` after validation | The engine, from the envelope plus its own stamps |
| **Host display** | Cards, widgets, actions the user sees | Your application |

The engine decides what *may* be emitted. Your host decides what is *shown* and what an action
actually does. The engine never renders and never executes a UI action.

## Ownership, which is not visible in a type

Every field on a validated insight belongs to exactly one of three origins. Confusing them is
how a host ends up trusting a model's claim about itself.

- **Model-authored** — proposed by the model and validated (`content`, `type`, `urgency`,
  `evidence_refs`). Untrusted input that passed a check.
- **Host-supplied** — declared by your application before the run (`principal_id`,
  `insight_capabilities`, `widget_capabilities`). The model cannot grant itself these.
- **Engine-derived** — stamped at acceptance and not settable by any producer (`id`, `turn`,
  `contract_version`, `confidence_provided`, `urgency_provided`).

A worked example of why this matters: `confidence` is `1.0` on an insight whose model supplied
no estimate — so **a confidence value is not evidence that confidence was assessed**. The field
that tells you is `confidence_provided`, which the engine derives and no producer can set. The
same holds for `urgency` / `urgency_provided`.

---

## Engine

### AgentEngine

Owns the turn: selects eligible agents, runs them, validates what they produce at one
acceptance boundary, and merges the results. One engine serves many sessions.

**`api_key` is optional.** The engine constructs without one and creates its provider client
lazily, which is what lets the offline examples and the whole test suite run with no key. A
turn that actually calls a model needs one.

Parameters fall into four groups: provider configuration (`api_key`, `llm_*`), execution policy
(`max_phases`, `strict_reasoning_config`), contract policy (`structured_outputs`,
`fallback_signatures`, `content_limits`), and host capability hooks
(`widget_payload_validator`). Registration is **all-or-nothing**: `register_agent` and
`replace_agents` validate before mutating, so a rejected agent leaves the previous registry
serving.

<!-- GENERATED:AgentEngine -->
| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `api_key` | `Optional[str]` | no | `None` |  |
| `callbacks` | `List[callbacks.AgentCallbackHandler]` | no | `None` |  |
| `max_phases` | `int` | no | `2` |  |
| `llm_timeout` | `Optional[float]` | no | `None` |  |
| `llm_max_retries` | `Optional[int]` | no | `None` |  |
| `llm_max_tokens` | `Optional[int]` | no | `None` |  |
| `llm_base_url` | `Optional[str]` | no | `None` |  |
| `llm_wire_max_tokens_param` | `Optional[str]` | no | `None` |  |
| `strict_reasoning_config` | `bool` | no | `True` |  |
| `structured_outputs` | `str` | no | `'auto'` |  |
| `fallback_signatures` | `Optional[List[Dict[str, Any]]]` | no | `None` |  |
| `content_limits` | `Optional[Dict[str, Any]]` | no | `None` |  |
| `widget_payload_validator` | `Optional[Any]` | no | `None` |  |

| Method | Signature |
|---|---|
| `check_keyword_triggers` | `check_keyword_triggers(text: str, allowed_agent_ids: Optional[List[str]] = None) -> List[Tuple[BaseAgent, str]]` |
| `close_session_content` | `close_session_content(session_id: str) -> int` |
| `effective_insight_types` | `effective_insight_types(agent: BaseAgent, context: Optional[AgentContext] = None) -> EffectiveTypes` |
| `get_agents_by_trigger_type` | `get_agents_by_trigger_type(trigger_type: TriggerType) -> List[BaseAgent]` |
| `get_agents_with_keywords` | `get_agents_with_keywords() -> List[BaseAgent]` |
| `get_agents_with_silence_threshold` | `get_agents_with_silence_threshold() -> List[BaseAgent]` |
| `get_event_subscribers` | `get_event_subscribers(event_names: List[str]) -> List[BaseAgent]` |
| `process_turn` | `async process_turn(context: AgentContext, allowed_agent_ids: Optional[List[str]] = None, trigger_type: TriggerType = TriggerType.TURN_BASED, trigger_metadata: Dict[str, Any] = None) -> AgentResponse` |
| `register_agent` | `register_agent(agent: BaseAgent) -> None` |
| `replace_agents` | `replace_agents(agents: List[BaseAgent]) -> None` |
| `start_content_request` | `start_content_request(context: AgentContext, agent_id: str, request: InsightContentRequest) -> 'ContentTaskHandle'` |
| `unregister_agent` | `unregister_agent(agent_id: str) -> bool` |
| `update_api_key` | `update_api_key(api_key: Optional[str]) -> None` |
<!-- /GENERATED:AgentEngine -->

### AgentConfigurationError

Raised at registration or agent construction when a configuration cannot be honoured — an
unknown output format, a structural override, a retired option, an insight configuration that
contradicts itself. It is raised **before** any registry mutation.

<!-- GENERATED:AgentConfigurationError -->
_No public members: this type is a marker or an alias._
<!-- /GENERATED:AgentConfigurationError -->

### ContentTaskHandle

Returned by `AgentEngine.start_content_request`. A long-form generation runs as an engine-owned
task on a frozen snapshot, isolated from the live turn. `await handle.result()` returns only
after the task's concurrency slot is released; `cancel()` revokes publication.

<!-- GENERATED:ContentTaskHandle -->
| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `request_id` | `str` | yes | `—` |  |
| `source_snapshot_id` | `str` | yes | `—` |  |
| `session_id` | `str` | yes | `—` |  |
| `agent_id` | `str` | yes | `—` |  |
| `snapshot_turn` | `int` | yes | `—` |  |

| Method | Signature |
|---|---|
| `cancel` | `cancel() -> None` |
| `result` | `async result() -> ContentResult` |
<!-- /GENERATED:ContentTaskHandle -->

---

## Agents

### BaseAgent

The producer interface. **Subclassing `BaseAgent` is a supported, first-class path** — not
everything is a `DynamicAgent`. A custom producer builds an `AgentResponse` itself and is held
to exactly the same acceptance boundary: engine-owned fields it sets are rejected, its domain
channels are revalidated on the object that would commit, and its UI actions are validated
against the host's declarations.

<!-- GENERATED:BaseAgent -->
| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `config` | `AgentConfig` | yes | `—` |  |

| Method | Signature |
|---|---|
| `create_insight` | `create_insight(content: str, type: InsightType = InsightType.SUGGESTION, confidence: float = 1.0, expiry: Optional[int] = None, action_label: Optional[str] = None) -> AgentInsight` |
| `evaluate` | `async evaluate(context: AgentContext) -> Optional[AgentResponse]` |
| `process` | `async process(context: AgentContext, callbacks: List[Any] = None) -> Optional[AgentResponse]` |
<!-- /GENERATED:BaseAgent -->

### AgentConfig

The normalized configuration an agent carries after construction. `DynamicAgent` derives it
from a configuration dictionary; a custom subclass constructs it directly.

<!-- GENERATED:AgentConfig -->
| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `name` | `str` | yes | `—` |  |
| `id` | `str` | no | `None` |  |
| `trigger_interval` | `Optional[int]` | no | `None` |  |
| `cooldown` | `int` | no | `10` |  |
| `model` | `str` | no | `'gpt-4o-mini'` |  |
| `trigger_types` | `List[TriggerType]` | no | `None` |  |
| `trigger_keywords` | `List[str]` | no | `None` |  |
| `silence_threshold` | `Optional[int]` | no | `None` |  |
| `priority` | `int` | no | `0` |  |
| `output_format` | `str` | no | `'default'` |  |
| `trigger_conditions` | `Optional[Dict[str, Any]]` | no | `None` |  |
| `subscribed_events` | `Optional[List[str]]` | no | `None` |  |
| `reasoning_effort` | `Optional[str]` | no | `None` |  |
| `timeout` | `Optional[float]` | no | `None` |  |
| `max_tokens` | `Optional[int]` | no | `None` |  |
| `model_params` | `Optional[Dict[str, Any]]` | no | `None` |  |
| `insight_config` | `Optional[('InsightConfig')]` | no | `None` |  |
<!-- /GENERATED:AgentConfig -->

### DynamicAgent

An agent defined by data — persona, triggers, model settings and an output format — rather than
by code. Its output format decides the envelope it asks the model for and the channels it may
write; see [MIGRATION_OUTPUT_FORMATS.md](MIGRATION_OUTPUT_FORMATS.md). **Set `output_format`
explicitly**: omitting it currently inherits a deprecated format and warns.

<!-- GENERATED:DynamicAgent -->
| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `config_dict` | `dict` | yes | `—` |  |

| Method | Signature |
|---|---|
| `clone_for_isolated_run` | `clone_for_isolated_run() -> 'DynamicAgent'` |
| `content_admission` | `content_admission(context: AgentContext) -> Optional[Dict[str, Any]]` |
| `create_insight` | `create_insight(content: str, type: InsightType = InsightType.SUGGESTION, confidence: float = 1.0, expiry: Optional[int] = None, action_label: Optional[str] = None) -> AgentInsight` |
| `evaluate` | `async evaluate(context: AgentContext) -> AgentResponse` |
| `process` | `async process(context: AgentContext, callbacks: List[Any] = None) -> Optional[AgentResponse]` |
<!-- /GENERATED:DynamicAgent -->

---

## Callbacks

### AgentCallbackHandler

Observability hooks. Every method is a no-op by default, so a subclass implements only what it
needs.

**A callback runs before the acceptance boundary, and what it leaves behind is what gets
validated** — not the version the producer staged. A callback that mutates a response into an
invalid state rejects that response, which is deliberate: there is one boundary, and everything
passes through it.

<!-- GENERATED:AgentCallbackHandler -->
| Method | Signature |
|---|---|
| `on_agent_error` | `async on_agent_error(agent_name: str, error: Exception) -> None` |
| `on_agent_finish` | `async on_agent_finish(agent_name: str, response: Optional[AgentResponse], duration: float) -> None` |
| `on_agent_skipped` | `async on_agent_skipped(agent_name: str, reason: str) -> None` |
| `on_agent_start` | `async on_agent_start(agent_name: str, context: AgentContext) -> None` |
| `on_chain_error` | `async on_chain_error(error: Exception) -> None` |
| `on_insight_validation_error` | `async on_insight_validation_error(issue: InsightDiagnostic) -> None` |
| `on_phase_end` | `async on_phase_end(phase: int, event_names: List[str]) -> None` |
| `on_phase_start` | `async on_phase_start(phase: int, agent_names: List[str]) -> None` |
| `on_turn_end` | `async on_turn_end(response: AgentResponse, duration: float) -> None` |
| `on_turn_start` | `async on_turn_start(context: AgentContext) -> None` |
<!-- /GENERATED:AgentCallbackHandler -->

---

## The turn

### AgentContext

Everything an agent may see for one turn, and the only place a host declares what it can do.
Host-supplied throughout; the engine adds execution metadata and propagates a frozen copy to
every phase.

The capability fields are the ones to get right: a missing `principal_id` withdraws reply,
question and correction for the run, and empty `widget_capabilities` authorizes no UI action at
all. Both fail closed and quietly — the engine cannot tell an intentional omission from a typo.

<!-- GENERATED:AgentContext -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `session_id` | `str` | yes | `—` |  |
| `recent_segments` | `List[TranscriptSegment]` | yes | `—` |  |
| `shared_state` | `Dict[str, Any]` | no | `—` |  |
| `rag_docs` | `List[str]` | no | `—` |  |
| `trigger_type` | `TriggerType` | no | `TriggerType.TURN_BASED` |  |
| `trigger_metadata` | `Dict[str, Any]` | no | `—` |  |
| `language_directive` | `Optional[str]` | no | `None` |  |
| `user_context` | `Optional[str]` | no | `None` |  |
| `blackboard` | `Optional[Blackboard]` | no | `None` |  |
| `turn_count` | `int` | no | `0` |  |
| `phase` | `int` | no | `1` |  |
| `agent_config_overrides` | `Dict[str, AgentConfigOverride]` | no | `—` |  |
| `principal_id` | `Optional[str]` | no | `None` |  |
| `insight_capabilities` | `HostInsightCapabilities` | no | `—` |  |
| `widget_capabilities` | `HostWidgetCapabilities` | no | `—` |  |
| `insight_reference_context` | `InsightReferenceContext` | no | `—` |  |
| `insight_answers` | `List[InsightAnswer]` | no | `—` |  |
| `insight_content_requests` | `Dict[str, InsightContentRequest]` | no | `—` |  |
| `content_execution_context` | `Optional[ContentExecutionContext]` | no | `None` |  |
<!-- /GENERATED:AgentContext -->

### AgentResponse

What a turn produced. Two shapes share the class: a **per-agent** response, and the **merged**
turn response `process_turn` returns.

Two distinctions a field list cannot show:

- **`debug_info` is excluded from serialization.** It exists in Python and carries the prompt
  and raw model output for observability; it never reaches a serialized payload. Do not build a
  host feature on it surviving a round trip.
- **`usage` is per-agent.** It is populated on an individual agent's response and is **not**
  propagated into the merged turn response; per-agent attribution is what
  `acceptance_by_agent` and `data_by_agent` are for.

`acceptance_status` is `accepted`, `accepted_silent` or `rejected`. Rejection is
whole-response: a defective response commits none of its effects, so a diagnostic never means
"some of this was applied".

<!-- GENERATED:AgentResponse -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `source_agent_id` | `Optional[str]` | no | `None` |  |
| `insights` | `List[AgentInsight]` | no | `—` |  |
| `execution_id` | `Optional[str]` | no | `None` |  |
| `acceptance_status` | `Literal['accepted', 'accepted_silent', 'partial', 'rejected']` | no | `'accepted'` |  |
| `diagnostics` | `List[InsightDiagnostic]` | no | `—` |  |
| `acceptance_by_agent` | `Dict[str, str]` | no | `—` |  |
| `evidence_snapshot` | `Optional[EvidenceSnapshot]` | no | `None` |  |
| `evidence_snapshots_by_agent` | `Dict[str, EvidenceSnapshot]` | no | `—` |  |
| `data_by_agent` | `Dict[str, Dict[str, Any]]` | no | `—` |  |
| `state_updates` | `Dict[str, Any]` | no | `—` |  |
| `data` | `Dict[str, Any]` | no | `—` |  |
| `debug_info` | `Dict[str, Any]` | no | `—` | **excluded from serialization** |
| `events` | `List[Event]` | no | `—` |  |
| `variable_updates` | `Dict[str, Any]` | no | `—` |  |
| `queue_pushes` | `Dict[str, List[Any]]` | no | `—` |  |
| `facts` | `List[Fact]` | no | `—` |  |
| `memory_updates` | `Dict[str, Any]` | no | `—` |  |
| `memory_updates_by_agent` | `Dict[str, Dict[str, Any]]` | no | `—` |  |
| `usage` | `Optional[Dict[str, int]]` | no | `None` |  |
<!-- /GENERATED:AgentResponse -->

### TranscriptSegment

One piece of speech. `timestamp` is **session-relative seconds**, not wall-clock epoch — the
whole framework uses that convention.

<!-- GENERATED:TranscriptSegment -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `speaker` | `str` | yes | `—` |  |
| `text` | `str` | yes | `—` |  |
| `timestamp` | `float` | yes | `—` |  |
| `is_final` | `bool` | no | `True` |  |
<!-- /GENERATED:TranscriptSegment -->

### TriggerType

Why an agent ran.

<!-- GENERATED:TriggerType -->
| Member | Wire value |
|---|---|
| `TURN_BASED` | `turn_based` |
| `KEYWORD` | `keyword` |
| `SILENCE` | `silence` |
| `INTERVAL` | `interval` |
| `EVENT` | `event` |
| `FORCE` | `force` |
<!-- /GENERATED:TriggerType -->

### AgentConfigOverride

Per-agent adjustments a host applies for one turn. Polarity is easy to invert:
`cooldown_modifier` **+N is slower**, and `context_turns_modifier` **+N is more context**.

<!-- GENERATED:AgentConfigOverride -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `cooldown_modifier` | `Optional[int]` | no | `None` |  |
| `context_turns_modifier` | `Optional[int]` | no | `None` |  |
| `instructions_append` | `Optional[str]` | no | `None` |  |
<!-- /GENERATED:AgentConfigOverride -->

---

## Insights

### AgentInsight

The object your host renders. Its fields span all three origins above, so read that section
before trusting any of them.

Beyond `content` and `type`: `urgency` says when it needs to be seen; `evidence_refs` cite what
it was grounded in; `correction` and `question` carry the payloads of those two purposes;
`preview`, `content_format`, `response_depth` and `content_request_id` appear **only** on
negotiated long-form output. `expiry` and `action_label` are display hints a host may honour.

<!-- GENERATED:AgentInsight -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `agent_id` | `str` | yes | `—` |  |
| `agent_name` | `str` | yes | `—` |  |
| `type` | `InsightType` | yes | `—` |  |
| `content` | `str` | yes | `—` |  |
| `confidence` | `float` | no | `1.0` |  |
| `expiry` | `int` | no | `15` |  |
| `action_label` | `Optional[str]` | no | `None` |  |
| `metadata` | `Dict[str, Any]` | no | `—` |  |
| `id` | `Optional[str]` | no | `None` |  |
| `turn` | `Optional[int]` | no | `None` |  |
| `contract_version` | `Optional[str]` | no | `None` |  |
| `urgency` | `Optional[Literal['now', 'soon', 'whenever']]` | no | `None` |  |
| `confidence_provided` | `Optional[bool]` | no | `None` |  |
| `urgency_provided` | `Optional[bool]` | no | `None` |  |
| `observation_kind` | `Optional[Literal['hypothesis', 'implication']]` | no | `None` |  |
| `evidence_refs` | `List[EvidenceRef]` | no | `—` |  |
| `rationale` | `Optional[str]` | no | `None` |  |
| `validation_step` | `Optional[str]` | no | `None` |  |
| `assumptions` | `List[str]` | no | `—` |  |
| `correction` | `Optional[CorrectionPayload]` | no | `None` |  |
| `question` | `Optional[QuestionPayload]` | no | `None` |  |
| `preview` | `Optional[str]` | no | `None` |  |
| `content_format` | `Optional[Literal['plain_text', 'markdown']]` | no | `None` |  |
| `content_contract` | `Optional[str]` | no | `None` |  |
| `response_depth` | `Optional[Literal['brief', 'standard', 'detailed']]` | no | `None` |  |
| `content_request_id` | `Optional[str]` | no | `None` |  |
| `source_snapshot_id` | `Optional[str]` | no | `None` |  |

| Method | Signature |
|---|---|
| `model_dump_legacy` | `model_dump_legacy() -> Dict[str, Any]` |
<!-- /GENERATED:AgentInsight -->

### InsightType

The **primary purpose** of a message — never a UI surface, colour, urgency or permission.
`INFORMATION` is an alias of `FACT` (same member, wire value `fact`), so this enum must never
carry `@unique`. `ERROR` is a framework diagnostic and is never model-authorable.

<!-- GENERATED:InsightType -->
| Member | Wire value |
|---|---|
| `SUGGESTION` | `suggestion` |
| `WARNING` | `warning` |
| `OPPORTUNITY` | `opportunity` |
| `FACT` | `fact` |
| `PRAISE` | `praise` |
| `ERROR` | `error` |
| `OBSERVATION` | `observation` |
| `REPLY` | `reply` |
| `CORRECTION` | `correction` |
| `QUESTION` | `question` |
<!-- /GENERATED:InsightType -->

### InsightConfig

Per-agent insight permissions: which purposes it may use, its analysis profile, urgency default
and long-form content block. Contradictions — a permission flag without the matching allowed
type — fail at registration rather than silently narrowing.

<!-- GENERATED:InsightConfig -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `allowed_types` | `List[str]` | no | `—` |  |
| `allow_reply` | `bool` | no | `False` |  |
| `allow_question` | `bool` | no | `False` |  |
| `allow_correction` | `bool` | no | `False` |  |
| `analysis_profile` | `Literal['general', 'consulting']` | no | `'general'` |  |
| `default_urgency` | `Optional[Literal['now', 'soon', 'whenever']]` | no | `None` |  |
| `content` | `Optional[AgentContentConfig]` | no | `None` |  |

| Method | Signature |
|---|---|
| `contradictions` | `contradictions() -> List[str]` |
<!-- /GENERATED:InsightConfig -->

### InsightDiagnostic

One sanitized finding. `code` is from a fixed vocabulary — see
[DIAGNOSTICS.md](DIAGNOSTICS.md) for all of them — and `classification` is a **bounded** string
chosen by the framework, never raw model text.

<!-- GENERATED:InsightDiagnostic -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `execution_id` | `str` | yes | `—` |  |
| `agent_id` | `str` | yes | `—` |  |
| `code` | `str` | yes | `—` |  |
| `field_path` | `str` | no | `''` |  |
| `classification` | `Optional[str]` | no | `None` |  |
| `retained_channels` | `List[str]` | no | `—` |  |
| `withheld_channels` | `List[str]` | no | `—` |  |
<!-- /GENERATED:InsightDiagnostic -->

### CorrectionPayload

Attached to a `correction`: which earlier insight is being repaired, whether it is replaced or
withdrawn, and why. Validated against the retained record at the boundary.

<!-- GENERATED:CorrectionPayload -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `target_insight_id` | `str` | yes | `—` |  |
| `operation` | `Literal['replace', 'withdraw']` | yes | `—` |  |
| `reason` | `str` | yes | `—` |  |
<!-- /GENERATED:CorrectionPayload -->

### QuestionPayload

Attached to a `question`: why the information is needed and the expected response format. An
unanswered or dismissed question is **not** consent and not an answer.

<!-- GENERATED:QuestionPayload -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `reason` | `str` | yes | `—` |  |
| `response_format` | `Literal['text']` | no | `'text'` |  |
<!-- /GENERATED:QuestionPayload -->

---

## Host declarations

These are how your application states what it can do. The model cannot grant itself any of
them, and an absent declaration authorizes nothing rather than everything.

### HostInsightCapabilities

What your host can present or handle. Defaults are deliberately conservative: the five
purposes that need nothing of a host beyond rendering a card, and every interactive capability
off. Observation support must be declared explicitly.

<!-- GENERATED:HostInsightCapabilities -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `supported_types` | `List[str]` | no | `—` |  |
| `reply_drafts` | `bool` | no | `False` |  |
| `text_questions` | `bool` | no | `False` |  |
| `answers_shared` | `bool` | no | `False` |  |
| `corrections` | `bool` | no | `False` |  |
| `evidence_citations` | `bool` | no | `False` |  |
| `correction_agent_policy` | `Literal['own_only', 'allowlisted']` | no | `'own_only'` |  |
| `correction_agent_ids` | `List[str]` | no | `—` |  |
| `expanded_reading` | `bool` | no | `False` |  |
| `content_contracts` | `List[str]` | no | `—` |  |
| `content_formats` | `List[str]` | no | `—` |  |
| `max_content_chars` | `Optional[int]` | no | `None` |  |
| `max_preview_chars` | `Optional[int]` | no | `None` |  |
<!-- /GENERATED:HostInsightCapabilities -->

### HostWidgetCapabilities

The widgets an agent may drive this run. **Empty authorizes nothing.** The declarations also
shape the generated prompt, so an agent is never invited to produce an action the boundary will
reject.

<!-- GENERATED:HostWidgetCapabilities -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `widgets` | `List[WidgetDeclaration]` | no | `—` |  |

| Method | Signature |
|---|---|
| `authorization_map` | `authorization_map() -> Dict[str, Dict[str, Dict[str, Any]]]` |
<!-- /GENERATED:HostWidgetCapabilities -->

### WidgetDeclaration

One widget and the actions it accepts.

<!-- GENERATED:WidgetDeclaration -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `target_widget` | `str` | yes | `—` |  |
| `actions` | `List[WidgetActionDeclaration]` | no | `—` |  |
<!-- /GENERATED:WidgetDeclaration -->

### WidgetActionDeclaration

One action and its payload rule. `allow_additional_payload_keys` is off by default, so a widget
contract cannot widen itself by the model writing into it.

<!-- GENERATED:WidgetActionDeclaration -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `action` | `str` | yes | `—` |  |
| `required_payload_keys` | `List[str]` | no | `—` |  |
| `optional_payload_keys` | `List[str]` | no | `—` |  |
| `allow_additional_payload_keys` | `bool` | no | `False` |  |
<!-- /GENERATED:WidgetActionDeclaration -->

---

## Evidence and interaction

### EvidenceRef

A citation an insight carries. `source_index` is engine-stamped; a producer setting it is
rejected.

<!-- GENERATED:EvidenceRef -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `kind` | `Literal['segment', 'document', 'fact', 'insight']` | yes | `—` |  |
| `ref_id` | `str` | yes | `—` |  |
| `revision` | `Optional[str]` | no | `None` |  |
| `source_index` | `Optional[int]` | no | `None` |  |
<!-- /GENERATED:EvidenceRef -->

### EvidenceCatalogEntry

One resolvable reference. Identity is trusted because the framework or the host supplied it;
the `excerpt` remains untrusted source text.

<!-- GENERATED:EvidenceCatalogEntry -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `kind` | `Literal['segment', 'document', 'fact', 'insight']` | yes | `—` |  |
| `ref_id` | `str` | yes | `—` |  |
| `revision` | `Optional[str]` | no | `None` |  |
| `session_id` | `Optional[str]` | no | `None` |  |
| `excerpt` | `Optional[str]` | no | `None` |  |
| `source_index` | `Optional[int]` | no | `None` |  |
| `timestamp` | `Optional[float]` | no | `None` |  |
<!-- /GENERATED:EvidenceCatalogEntry -->

### EvidenceSnapshot

The immutable per-run record of what an agent was actually shown, after trimming. It is what
the agent's citations resolve against.

<!-- GENERATED:EvidenceSnapshot -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `snapshot_id` | `str` | yes | `—` |  |
| `agent_id` | `str` | yes | `—` |  |
| `entries` | `List[EvidenceCatalogEntry]` | no | `—` |  |
<!-- /GENERATED:EvidenceSnapshot -->

### InsightReferenceContext

Host-supplied records an agent may cite or correct. Hosts need not populate this for ordinary
observations.

<!-- GENERATED:InsightReferenceContext -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `evidence` | `List[EvidenceCatalogEntry]` | no | `—` |  |
| `prior_insights` | `List[PriorInsightRecord]` | no | `—` |  |
<!-- /GENERATED:InsightReferenceContext -->

### PriorInsightRecord

One earlier insight the host retained. `correctable` controls whether it may be the target of a
correction.

<!-- GENERATED:PriorInsightRecord -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `id` | `str` | yes | `—` |  |
| `session_id` | `str` | yes | `—` |  |
| `principal_id` | `Optional[str]` | no | `None` |  |
| `agent_id` | `str` | yes | `—` |  |
| `type` | `str` | yes | `—` |  |
| `content` | `str` | yes | `—` |  |
| `turn` | `int` | yes | `—` |  |
| `status` | `Literal['active', 'superseded', 'withdrawn']` | no | `'active'` |  |
| `correctable` | `bool` | no | `True` |  |
<!-- /GENERATED:PriorInsightRecord -->

### InsightAnswer

The principal's reply to a question, or a dismissal. Validated against the retained question
record at turn start; agents only ever see the validated subset, and by default only the agent
that asked.

<!-- GENERATED:InsightAnswer -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `event_id` | `str` | yes | `—` |  |
| `question_insight_id` | `str` | yes | `—` |  |
| `principal_id` | `str` | yes | `—` |  |
| `status` | `Literal['answered', 'dismissed']` | yes | `—` |  |
| `text` | `Optional[str]` | no | `None` |  |
<!-- /GENERATED:InsightAnswer -->

---

## Long-form content

Extended generation is **negotiated**, not requested: the agent declares a content block, the
host declares limits and formats, and admission runs *before* any model call so a request that
cannot be honoured costs nothing.

### AgentContentConfig

The agent's side of the negotiation: depth profiles, formats and preview ceiling.

<!-- GENERATED:AgentContentConfig -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `contract` | `Literal['long_form_v1']` | no | `'long_form_v1'` |  |
| `default_depth` | `Literal['brief', 'standard', 'detailed']` | no | `'brief'` |  |
| `formats` | `List[Literal['plain_text', 'markdown']]` | no | `—` |  |
| `max_preview_chars` | `int` | yes | `—` |  |
| `profiles` | `Dict[Literal['brief', 'standard', 'detailed'], ContentProfile]` | yes | `—` |  |
<!-- /GENERATED:AgentContentConfig -->

### ContentProfile

One depth's generation budget. `max_output_tokens` includes reasoning tokens on reasoning
models; `llm_timeout_seconds` is wall-clock.

<!-- GENERATED:ContentProfile -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `max_content_chars` | `int` | yes | `—` |  |
| `max_output_tokens` | `int` | yes | `—` |  |
| `llm_timeout_seconds` | `float` | yes | `—` |  |
<!-- /GENERATED:ContentProfile -->

### InsightContentRequest

A host asking one agent for a particular depth on this turn.

<!-- GENERATED:InsightContentRequest -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `depth` | `Literal['brief', 'standard', 'detailed']` | yes | `—` |  |
| `request_id` | `Optional[str]` | no | `None` |  |
<!-- /GENERATED:InsightContentRequest -->

### ContentExecutionContext

The trusted declaration of *where* generation runs. The isolated active-session path is
admitted only on a declaration the engine issued for a task it owns — a host-authored boolean
cannot stand in for the runtime.

<!-- GENERATED:ContentExecutionContext -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `session_mode` | `Literal['active', 'paused', 'post_session']` | yes | `—` |  |
| `execution_path` | `Literal['live_turn', 'isolated_content', 'offline_content']` | yes | `—` |  |
| `request_id` | `Optional[str]` | no | `None` |  |
| `source_snapshot_id` | `Optional[str]` | no | `None` |  |
| `holds_live_turn_lock` | `Optional[bool]` | no | `None` |  |
| `writes_live_blackboard` | `Optional[bool]` | no | `None` |  |
| `pause_declared` | `Optional[bool]` | no | `None` |  |
| `task_isolation_verified` | `Optional[bool]` | no | `None` |  |
<!-- /GENERATED:ContentExecutionContext -->

### ContentResult

The outcome of a content task: status, the insight if one was accepted, diagnostics and usage.

<!-- GENERATED:ContentResult -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `request_id` | `str` | yes | `—` |  |
| `source_snapshot_id` | `str` | yes | `—` |  |
| `session_id` | `str` | yes | `—` |  |
| `agent_id` | `str` | yes | `—` |  |
| `snapshot_turn` | `int` | yes | `—` |  |
| `status` | `Literal['accepted', 'silent', 'rejected', 'cancelled']` | yes | `—` |  |
| `insight` | `Optional[('AgentInsight')]` | no | `None` |  |
| `diagnostics` | `List[('InsightDiagnostic')]` | no | `—` |  |
| `usage` | `Optional[Dict[str, int]]` | no | `None` |  |
<!-- /GENERATED:ContentResult -->

---

## Blackboard

### Blackboard

Shared session state: variables, events, queues, facts and per-agent private memory. The engine
commits agent proposals here at its merge boundary; nothing an agent returns writes directly.

Facts deduplicate by `(type, key)`, and on collision **higher agent priority wins**, ties broken
by confidence, then by later registration. The `sys.*` variable namespace is engine-reserved: a
proposed write there rejects the whole response.

<!-- GENERATED:Blackboard -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `events` | `List[Event]` | no | `—` |  |
| `variables` | `Dict[str, Any]` | no | `—` |  |
| `queues` | `Dict[str, List[Any]]` | no | `—` |  |
| `facts` | `List[Fact]` | no | `—` |  |
| `memory` | `Dict[str, Dict[str, Any]]` | no | `—` |  |

| Method | Signature |
|---|---|
| `add_fact` | `add_fact(fact: Fact) -> None` |
| `clear_events` | `clear_events() -> None` |
| `clear_queue` | `clear_queue(queue_name: str) -> None` |
| `count_events` | `count_events(event_name: str) -> int` |
| `delete_var` | `delete_var(key: str) -> None` |
| `emit_event` | `emit_event(event: Event) -> None` |
| `from_dict` | `from_dict(data: Dict[str, Any]) -> 'Blackboard'` |
| `get_events_by_name` | `get_events_by_name(event_name: str) -> List[Event]` |
| `get_fact` | `get_fact(fact_type: str, key: Optional[str] = None) -> Optional[Fact]` |
| `get_facts_by_type` | `get_facts_by_type(fact_type: str) -> List[Fact]` |
| `get_memory` | `get_memory(agent_id: str) -> Dict[str, Any]` |
| `get_var` | `get_var(key: str, default: Any = None) -> Any` |
| `has_event` | `has_event(event_name: str) -> bool` |
| `has_fact` | `has_fact(fact_type: str, key: Optional[str] = None) -> bool` |
| `has_memory` | `has_memory(agent_id: str) -> bool` |
| `has_queue` | `has_queue(queue_name: str) -> bool` |
| `has_var` | `has_var(key: str) -> bool` |
| `peek_queue` | `peek_queue(queue_name: str) -> Optional[Any]` |
| `pop_queue` | `pop_queue(queue_name: str) -> Optional[Any]` |
| `push_queue` | `push_queue(queue_name: str, item: Any) -> None` |
| `push_queue_items` | `push_queue_items(queue_name: str, items: List[Any]) -> None` |
| `queue_length` | `queue_length(queue_name: str) -> int` |
| `set_memory` | `set_memory(agent_id: str, data: Dict[str, Any]) -> None` |
| `set_var` | `set_var(key: str, value: Any, _engine_internal: bool = False) -> None` |
| `snapshot` | `snapshot() -> 'Blackboard'` |
| `to_dict` | `to_dict() -> Dict[str, Any]` |
| `update_memory` | `update_memory(agent_id: str, updates: Dict[str, Any]) -> None` |
<!-- /GENERATED:Blackboard -->

### Event

A broadcast signal for agent coordination. Not deduplicated — several events with the same name
may coexist in a turn. `timestamp` is session-relative seconds.

<!-- GENERATED:Event -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `name` | `str` | yes | `—` |  |
| `payload` | `Dict[str, Any]` | no | `—` |  |
| `source_agent` | `str` | yes | `—` |  |
| `timestamp` | `float` | yes | `—` |  |
| `id` | `Optional[str]` | no | `None` |  |
<!-- /GENERATED:Event -->

### Fact

Extracted knowledge. `priority` is **engine-populated** at merge time from the emitting agent;
agents should not set it. Hosts calling `Blackboard.add_fact` directly own it.

<!-- GENERATED:Fact -->
| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `type` | `str` | yes | `—` |  |
| `key` | `Optional[str]` | no | `None` |  |
| `value` | `Any` | yes | `—` |  |
| `confidence` | `float` | no | `1.0` |  |
| `priority` | `int` | no | `0` |  |
| `source_agent` | `str` | yes | `—` |  |
| `timestamp` | `float` | yes | `—` |  |
<!-- /GENERATED:Fact -->

### ConditionEvaluator

Evaluates an agent's `trigger_conditions` against the blackboard. It **fails closed**: an
unevaluable condition suppresses the agent rather than guessing.

<!-- GENERATED:ConditionEvaluator -->
| Method | Signature |
|---|---|
| `evaluate` | `evaluate(conditions: Optional[Dict], blackboard: Blackboard, meta: Dict, agent_id: str) -> bool` |
<!-- /GENERATED:ConditionEvaluator -->

---

## Constants

- **`DEFAULT_MODEL`** — the model a `DynamicAgent` uses when its configuration names none.
- **`HUMAN_INSIGHT_TYPES`** — the nine human-facing purposes in canonical order. This tuple,
  not enum iteration, is the source for allowed-type sets and provider enums; iteration also
  yields `ERROR`, which is never model-authorable.
- **`INSIGHT_TYPE_LABELS`** — display labels. Hosts may override per locale without changing
  any wire value.

## What is deliberately not here

`docs/api/inventory.yaml` records the classes excluded from the supported surface and why —
internal provider adapters and per-run framework internals. "Undocumented" there is a decision
someone made, not a gap nobody noticed.
