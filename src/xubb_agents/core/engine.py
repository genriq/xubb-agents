"""
AgentEngine - Central orchestrator for the Xubb Agents Framework (v2).

Key responsibilities:
- Registry: Maintains list of active agents
- Routing: Determines which agents run based on trigger type
- Condition Evaluation: Checks trigger conditions before running agents
- Blackboard Management: Manages structured state (in-memory for session lifetime);
  syncs Blackboard variables and per-agent memory into shared_state (the MR-1
  memory read-path, INV-14) for the legacy v1 surface
- Event Dispatch: Collects emitted events, triggers subscribers
- Multi-Phase Execution: Runs normal agents (Phase 1), then event-triggered agents (Phase 2)
- Response Aggregation: Merges insights, applies state updates by priority
- Observability: Emits lifecycle events to callbacks

Note: Response caching was removed in v2.0. Cooldowns and trigger conditions
provide more correct mechanisms for preventing unnecessary LLM calls.
"""

import asyncio
import logging
import threading
import time
from copy import deepcopy
from typing import List, Optional, Dict, Any, Tuple

from .models import (
    AgentContext, AgentResponse, TriggerType, Event, InsightType, InsightDiagnostic,
    ContentExecutionContext, ContentResult, InsightContentRequest, AgentInsight,
    EvidenceRef, CorrectionPayload, QuestionPayload,
)
import uuid
from .insight_validation import (
    LEGACY_HUMAN_TYPES, RESERVED_VAR_PREFIX, LEGACY_MEMORY_PREFIX, bounded,
    INSIGHT_CONTRACTS, DEFAULT_INSIGHT_CONTRACT, EffectiveTypes, effective_types_for_run,
    HUMAN_WIRE_VALUES, MISSING, resolve_urgency, validate_answers, validate_correction_target,
    validate_typed_candidate, validate_response_channels, ReferenceContext,
)
from .provider_schema import STRUCTURED_OUTPUT_MODES, DEFAULT_STRUCTURED_OUTPUTS
from .agent import BaseAgent
from .llm import LLMClient, FRAMEWORK_OWNED_PARAMS
from .callbacks import AgentCallbackHandler
from .blackboard import Blackboard
from .conditions import ConditionEvaluator

logger = logging.getLogger("AgentEngine")


class AgentConfigurationError(ValueError):
    """A per-agent LLM configuration is invalid at load time (v2.6, VL-1/RC-2).

    Raised BEFORE any registry mutation: by ``DynamicAgent.__init__`` for
    ``model_params`` collisions with framework-owned wire keys, and by
    ``AgentEngine.register_agent``/``replace_agents`` when a model matching the
    reasoning heuristic lacks an explicit ``reasoning_effort`` (D-1 ruling;
    downgraded to a warning when the engine is constructed with
    ``strict_reasoning_config=False``). The message always contains a
    copy-pasteable fix.
    """


# VL-1 (SPEC_LLM_MODERN_MODELS / INV-19): ADVISORY capability heuristic —
# consulted ONLY for load-time validation signals; it never alters outbound
# payloads (INV-15; pinned by test). OpenAI publishes no capability API and
# effort value-sets are per-model, so this is deliberately a heuristic:
# a wrong guess produces a warning or a loud, fixable load error — never a
# silent wire change. Module-level so tests (and desperate operators) can
# monkeypatch it.
REASONING_MODEL_PREFIXES = ("gpt-5", "o1", "o3", "o4")
# Name shapes that match the prefixes but are known to reject/restrict
# reasoning_effort (chat-tuned, search, codex, pro tiers).
REASONING_MODEL_DENY_MARKERS = ("-chat", "-search", "-codex", "-pro")
REASONING_MODEL_DENY_EXACT = ("o1-mini",)
# Effort values that keep the real-time envelope; anything above triggers the
# budget cross-check (VL-1 rule 3; thresholds normative per spec §7.4).
LOW_EFFORT_VALUES = ("none", "minimal", "low")
RULE3_MIN_TIMEOUT = 10.0    # seconds — effort > low needs more than this
RULE3_MIN_MAX_TOKENS = 4096  # tokens — reasoning eats the cap before output


def _looks_reasoning_capable(model) -> bool:
    """Advisory-only heuristic: does this model name look reasoning-capable?"""
    if not isinstance(model, str):
        return False
    name = model.lower()
    if name in REASONING_MODEL_DENY_EXACT:
        return False
    if any(marker in name for marker in REASONING_MODEL_DENY_MARKERS):
        return False
    return any(name.startswith(prefix) for prefix in REASONING_MODEL_PREFIXES)


# References to best-effort background LLM-client close tasks (see _close_llm_client).
# Holding them prevents a fire-and-forget task from being garbage-collected mid-close;
# each task's done-callback removes itself and logs any failure.
_PENDING_CLOSE_TASKS: set = set()


def _on_close_task_done(task: "asyncio.Task") -> None:
    _PENDING_CLOSE_TASKS.discard(task)
    try:
        exc = task.exception()
    except asyncio.CancelledError:  # pragma: no cover - close task cancelled
        return
    if exc is not None:  # pragma: no cover - best-effort cleanup failure
        logger.warning(f"Failed to close previous LLM client: {exc}")


class ContentTaskHandle:
    """Ownership handle of one isolated content task (C2). ``cancel()`` revokes
    publication and cancels the task; ``result()`` awaits the ContentResult."""

    def __init__(self, request_id: str, source_snapshot_id: str, session_id: str,
                 agent_id: str, snapshot_turn: int):
        self.request_id = request_id
        self.source_snapshot_id = source_snapshot_id
        self.session_id = session_id
        self.agent_id = agent_id
        self.snapshot_turn = snapshot_turn
        self.publishable = True
        self.task: Optional["asyncio.Task"] = None

    def cancel(self) -> None:
        self.publishable = False
        if self.task is not None and not self.task.done():
            self.task.cancel()

    async def result(self) -> ContentResult:
        try:
            return await self.task
        except asyncio.CancelledError:
            return ContentResult(request_id=self.request_id, source_snapshot_id=self.source_snapshot_id,
                                 session_id=self.session_id, agent_id=self.agent_id,
                                 snapshot_turn=self.snapshot_turn, status="cancelled",
                                 diagnostics=[InsightDiagnostic(execution_id=self.request_id, agent_id=self.agent_id,
                                                                code="content_execution_not_allowed", field_path="$",
                                                                classification="cancelled")])


class AgentEngine:
    """Central orchestrator for the agent system (v2)."""
    
    def __init__(self, api_key: Optional[str] = None,
                 callbacks: List[AgentCallbackHandler] = None,
                 max_phases: int = 2,
                 llm_timeout: Optional[float] = None,
                 llm_max_retries: Optional[int] = None,
                 llm_max_tokens: Optional[int] = None,
                 llm_base_url: Optional[str] = None,
                 llm_wire_max_tokens_param: Optional[str] = None,
                 strict_reasoning_config: bool = True,
                 insight_contract: str = DEFAULT_INSIGHT_CONTRACT,
                 structured_outputs: str = DEFAULT_STRUCTURED_OUTPUTS,
                 fallback_signatures: Optional[List[Dict[str, Any]]] = None,
                 content_limits: Optional[Dict[str, Any]] = None):
        """Initialize the AgentEngine.

        Args:
            api_key: OpenAI API key
            callbacks: List of callback handlers for observability
            max_phases: Execution phases — only 1 (Phase 1 only) or 2 (Phase 1 +
                event-triggered Phase 2) are supported. Other values are clamped (E-7).
            llm_timeout / llm_max_retries / llm_max_tokens / llm_base_url /
                llm_wire_max_tokens_param: engine-level LLMClient configuration
                (EN-1). Unset knobs keep the LLMClient defaults. The resolved
                set is stored and REUSED by ``update_api_key`` (INV-18) — key
                rotation never resets the client to module defaults.
            strict_reasoning_config: VL-1 rule-1 severity (D-1 ruling). True
                (default): registering an agent whose model looks
                reasoning-capable without an explicit ``reasoning_effort``
                raises ``AgentConfigurationError``. False: warns instead.
            insight_contract: XUBB-ITC-1 §7.1 contract selection. ``legacy_v2``
                (default, the current-major compatibility path: G0 legacy
                safety, D-LR partial acceptance). ``typed_v1``: strict local
                validation of the normalized candidate, exact effective-type
                enforcement, whole-response atomic rejection (§8.4), engine-
                minted identity, runtime-derived confidence provenance and
                urgency precedence. Only schemas with a declared typed adapter
                (``insight_v1``, ``default_v2``, ``v2_raw``) may be registered
                under it; anything else fails at registration. Any other value
                is a ``ValueError``.
        """
        if insight_contract not in INSIGHT_CONTRACTS:
            raise ValueError(
                f"insight_contract must be one of {INSIGHT_CONTRACTS}, got {insight_contract!r}")
        self.insight_contract = insight_contract
        # G2 / §13.3: transport policy is a separate control from the contract
        # (structured_outputs: strict | auto | json_object) and lives on the
        # LLMClient, keyed per endpoint/model/adapter/schema version.
        if structured_outputs not in STRUCTURED_OUTPUT_MODES:
            raise ValueError(
                f"structured_outputs must be one of {STRUCTURED_OUTPUT_MODES}, got {structured_outputs!r}")
        self.structured_outputs = structured_outputs
        # C1 / §14.6: OPERATOR limits for long_form_v1 — a finite max_response_bytes
        # (required to enable the extension), the live-lane ceilings
        # (live_max_output_tokens / live_max_timeout_seconds) and optional global
        # character caps. Injected into agents at registration.
        self.content_limits: Dict[str, Any] = dict(content_limits or {})
        # C2 / §14.6.1: bounded shared-provider admission for isolated content
        # tasks (default 1). It bounds content-task concurrency only — it does NOT
        # reserve provider capacity for the live turn — and keeps
        # the registry of live task handles per session (for closure).
        max_tasks = self.content_limits.get("max_concurrent_content_tasks", 1)
        if not isinstance(max_tasks, int) or isinstance(max_tasks, bool) or max_tasks < 1:
            raise ValueError("content_limits.max_concurrent_content_tasks must be a positive int")
        self._content_slots = asyncio.Semaphore(max_tasks)
        self._content_tasks: Dict[str, List["ContentTaskHandle"]] = {}
        # EN-1 / INV-18: only-when-set, so LLMClient defaults keep applying
        # otherwise; update_api_key rebuilds from THIS dict, never bare.
        self._llm_config: Dict[str, Any] = {}
        for key, value in (("timeout", llm_timeout),
                           ("max_retries", llm_max_retries),
                           ("max_tokens", llm_max_tokens),
                           ("base_url", llm_base_url),
                           ("wire_max_tokens_param", llm_wire_max_tokens_param),
                           # only-when-set: the client's own default ("auto") is not recorded
                           ("structured_outputs",
                            structured_outputs if structured_outputs != DEFAULT_STRUCTURED_OUTPUTS else None),
                           ("fallback_signatures", fallback_signatures)):
            if value is not None:
                self._llm_config[key] = value

        self.agents: List[BaseAgent] = []
        self.llm_client = LLMClient(api_key=api_key, **self._llm_config)
        self.callbacks = callbacks or []
        self.condition_evaluator = ConditionEvaluator()
        self.strict_reasoning_config = strict_reasoning_config

        # E-7: the engine only implements Phase 1 + an optional Phase 2. Reject/clamp
        # unsupported values rather than silently accepting a knob that does nothing.
        if max_phases not in (1, 2):
            clamped = 1 if max_phases < 1 else 2
            logger.warning(
                f"max_phases={max_phases} is unsupported (engine implements Phase 1 "
                f"plus an optional Phase 2); using {clamped}."
            )
            max_phases = clamped
        self.max_phases = max_phases

        # Agent registration order for deterministic tie-breaking
        self._agent_index: Dict[str, int] = {}
        # Parallel map for O(1) (priority, registration-order) lookup at merge time (E-5)
        self._agent_meta: Dict[str, Tuple[int, int]] = {}
        # Serializes concurrent replace_agents() callers. Readers stay lock-free:
        # replace_agents rebinds the three structures (never mutates in place), so an
        # in-flight `for a in self.agents` always iterates a complete list.
        self._agents_lock = threading.Lock()
        # E-6: agent ids already warned about EVENT-subscription misconfig (warn once,
        # not every turn, to avoid flooding logs in a long real-time session).
        self._warned_subscriber_ids: set = set()
        # VL-1: agent ids already warned about LLM-config issues — warn once,
        # not on every bulk config reload re-registering the same id (E-6 discipline).
        self._warned_config_agent_ids: set = set()

    def _validate_agent_llm_config(self, agent: BaseAgent) -> List[str]:
        """VL-1 (INV-19): load-time cross-validation of an agent's LLM config.

        Returns the list of HARD violations (registration must fail; empty when
        clean) and emits warn-once warnings for the advisory rules. Reads
        ``agent.config`` via ``getattr`` defaults so custom BaseAgent
        subclasses validate generically. PAYLOAD-ADVISORY (INV-15): this only
        produces signals — it never touches the config or any outbound kwargs.
        """
        cfg = agent.config
        model = getattr(cfg, "model", "") or ""
        effort = getattr(cfg, "reasoning_effort", None)
        timeout = getattr(cfg, "timeout", None)
        max_tokens = getattr(cfg, "max_tokens", None)
        model_params = getattr(cfg, "model_params", None) or {}
        agent_id = getattr(cfg, "id", "?")

        violations: List[str] = []
        warnings_: List[str] = []
        reasoning_like = _looks_reasoning_capable(model)

        # Rule 1 (D-1 ruling: hard-fail; warn under strict_reasoning_config=False).
        if reasoning_like and effort is None:
            msg = (
                f"Agent '{agent_id}' uses model '{model}', which looks reasoning-capable, "
                f"without an explicit reasoning_effort — the API default (often 'medium') "
                f"blows the real-time latency budget and multiplies cost. Fix: add "
                f'"reasoning_effort" to its model_config — "none" (gpt-5.1+/5.6 mainline), '
                f'"minimal" (original gpt-5 family), or "low" (o-series). '
                f"(Escape hatch: AgentEngine(strict_reasoning_config=False).)"
            )
            (violations if self.strict_reasoning_config else warnings_).append(msg)

        # Rule 2: effort declared on a shape known to reject/restrict it.
        if effort is not None and not reasoning_like:
            warnings_.append(
                f"Agent '{agent_id}': reasoning_effort='{effort}' is set but model "
                f"'{model}' does not look reasoning-capable — the API will likely "
                f"reject the parameter (category=misconfig)."
            )

        # Rule 3: deep effort needs real budgets (normative thresholds, spec §7.4).
        if effort is not None and effort not in LOW_EFFORT_VALUES:
            eff_timeout = timeout if timeout is not None \
                else getattr(self.llm_client, "timeout", None)
            eff_cap = max_tokens if max_tokens is not None \
                else getattr(self.llm_client, "max_tokens", None)
            if (not isinstance(eff_timeout, (int, float)) or eff_timeout <= RULE3_MIN_TIMEOUT) or \
               (not isinstance(eff_cap, int) or eff_cap < RULE3_MIN_MAX_TOKENS):
                warnings_.append(
                    f"Agent '{agent_id}': reasoning_effort='{effort}' with "
                    f"timeout={eff_timeout}s / max_tokens={eff_cap} will likely time out "
                    f"or starve the output (category=truncated) — and both outcomes are "
                    f"BILLED. Set model_config timeout > {RULE3_MIN_TIMEOUT:g}s and "
                    f"max_tokens >= {RULE3_MIN_MAX_TOKENS} (OpenAI suggests ~25000 for "
                    f"real reasoning headroom)."
                )

        # Rule 4: sampling params rejected by reasoning models.
        if reasoning_like and isinstance(model_params, dict) and \
                any(k in model_params for k in ("temperature", "top_p")):
            warnings_.append(
                f"Agent '{agent_id}': model_params sets temperature/top_p, but "
                f"reasoning models reject them (category=misconfig)."
            )

        # Rule 5: framework-owned collisions (re-check for custom agents;
        # DynamicAgent already rejects these in its own __init__).
        if isinstance(model_params, dict):
            collisions = sorted(set(model_params) & FRAMEWORK_OWNED_PARAMS)
            if collisions:
                violations.append(
                    f"Agent '{agent_id}': model_params may not set framework-owned "
                    f"key(s) {collisions} — use the dedicated model_config fields "
                    f"(model / reasoning_effort / timeout / max_tokens) instead."
                )

        if warnings_ and agent_id not in self._warned_config_agent_ids:
            self._warned_config_agent_ids.add(agent_id)
            for message in warnings_:
                logger.warning(message)

        return violations

    # -------------------------------------------------------------------------
    # XUBB-ITC-1 (G1) — insight configuration validation and effective types
    # -------------------------------------------------------------------------

    # Typed candidate fields a schema adapter must be able to carry for a given
    # configuration (§13.1: "an agent requesting a type whose required fields
    # cannot be mapped by its schema fails at configuration time").
    _CONSULTING_FIELDS = ("observation_kind", "evidence_refs", "rationale", "validation_step")

    def _validate_insight_config(self, agent: BaseAgent) -> List[str]:
        """Load-time checks (§7.2, §13.1). Returns HARD violations (registration
        fails; nothing mutated):

        * a permission flag and its ``allowed_types`` membership must agree;
        * under ``typed_v1`` a DynamicAgent's schema must declare a typed adapter
          (``supported_contracts`` includes ``typed_v1``) and must be able to
          carry the fields the configuration needs; under ``legacy_v2`` the
          schema must declare ``legacy_v2`` (``insight_v1`` is typed-only).
        """
        cfg = getattr(agent.config, "insight_config", None)
        agent_id = getattr(agent.config, "id", "?")
        violations = []
        if cfg is not None:
            violations += [f"Agent '{agent_id}': insight_config contradiction — {c}" for c in cfg.contradictions()]
        descriptor = getattr(agent, "descriptor", None)
        if descriptor is None:
            return violations                      # custom BaseAgent: no schema to check
        schema = getattr(agent.config, "output_format", "?")
        supported_contracts = descriptor.get("supported_contracts") or ["legacy_v2"]
        if self.insight_contract not in supported_contracts:
            violations.append(
                f"Agent '{agent_id}': schema '{schema}' does not support insight_contract="
                f"'{self.insight_contract}' (declares {supported_contracts}). Typed adapters: "
                f"insight_v1, default_v2, v2_raw.")
            return violations
        if self.insight_contract == "typed_v1" and self.structured_outputs == "strict" \
                and "json_schema" not in (descriptor.get("supported_transports") or []):
            violations.append(
                f"Agent '{agent_id}': structured_outputs='strict' requires a schema adapter with "
                f"json_schema transport; '{schema}' declares "
                f"{descriptor.get('supported_transports') or ['json_object']}. Use insight_v1, or "
                f"structured_outputs='auto'/'json_object'.")
        if cfg is not None and cfg.content is not None:
            # C1 / §14.10: the extension needs the typed contract AND a schema
            # adapter that declares it. Never silently inert.
            if self.insight_contract != "typed_v1":
                violations.append(
                    f"Agent '{agent_id}': insight_config.content (long_form_v1) requires insight_contract='typed_v1'.")
            elif "long_form_v1" not in (descriptor.get("supported_content_contracts") or []):
                violations.append(
                    f"Agent '{agent_id}': schema '{schema}' does not support content contract long_form_v1; use insight_v1.")
        if self.insight_contract == "typed_v1" and cfg is not None:
            fields = set(descriptor.get("supported_insight_fields") or [])
            needed = set()
            if cfg.analysis_profile == "consulting":
                needed |= set(self._CONSULTING_FIELDS)
            if "correction" in cfg.allowed_types:
                needed.add("correction")
            if "question" in cfg.allowed_types:
                needed.add("question")
            missing = sorted(needed - fields)
            if missing:
                violations.append(
                    f"Agent '{agent_id}': schema '{schema}' cannot map required typed field(s) "
                    f"{missing} for this insight_config; use insight_v1.")
        return violations

    def effective_insight_types(self, agent: BaseAgent,
                                context: Optional[AgentContext] = None) -> EffectiveTypes:
        """The run's effective human-facing set for ``agent`` (§7.2): framework
        ∩ agent ∩ schema ∩ host ∩ permission prerequisites ∩ this release's
        implemented set, with a reason for every absent value. Under
        ``legacy_v2`` this is the host-safe five."""
        return effective_types_for_run(contract=self.insight_contract,
                                       insight_config=getattr(agent.config, "insight_config", None),
                                       descriptor=getattr(agent, "descriptor", None),
                                       context=context)

    def register_agent(self, agent: BaseAgent) -> None:
        """Register an agent with the engine.

        Concurrency-safe: mutates the registry under ``self._agents_lock`` using the
        same build-fresh-and-rebind discipline as ``replace_agents`` (never mutating
        the live structures in place), so a lock-free reader on another thread — e.g. a
        turn iterating ``self.agents`` while a bulk reload swaps agents — always sees a
        complete, consistent registry.

        Raises ``AgentConfigurationError`` (VL-1/INV-19) BEFORE any mutation —
        on failure the registry is untouched and the agent's ``llm`` stays None.
        """
        # VL-1: validate-before-mutate.
        violations = self._validate_agent_llm_config(agent) + self._validate_insight_config(agent)
        if violations:
            raise AgentConfigurationError(" | ".join(violations))

        # Inject the LLM client and the engine-selected contract into the agent.
        agent.llm = self.llm_client
        agent.insight_contract = self.insight_contract
        agent.content_limits = self.content_limits

        with self._agents_lock:
            # Track registration order for deterministic merge ordering. Cache
            # (priority, index) so _merge_responses does an O(1) lookup instead of an
            # O(agents × responses) linear scan (E-5). Rebind fresh dicts/list rather
            # than mutating in place so a lock-free reader never sees a torn update.
            index = len(self.agents)
            self._agent_index = {**self._agent_index, agent.config.id: index}
            self._agent_meta = {
                **self._agent_meta,
                agent.config.id: (agent.config.priority, index),
            }
            self.agents = self.agents + [agent]

        logger.info(f"Registered agent: {agent.config.name} (ID: {agent.config.id}, "
                   f"Model: {agent.config.model}, Triggers: {agent.config.trigger_types})")

    def replace_agents(self, agents: List[BaseAgent]) -> None:
        """Atomically replace the full agent set (e.g. when the host reloads
        agent configs from its config store).

        Concurrency-safe alternative to ``agents.clear()`` + ``register_agent`` loop:
        a hot turn iterating ``self.agents`` (or reading ``_agent_meta``) must never
        observe a half-cleared registry. We build the three structures
        (agents / index / meta) FRESH and rebind them in one go — never mutating the
        live ones in place — so a concurrent ``for a in self.agents`` always iterates
        a complete list (old or new), and ``_agent_meta.get()`` always returns a
        consistent value. ``self.agents`` is rebound LAST, after index/meta, so a
        reader that sees the new agents also sees the new metadata.

        ALL-OR-NOTHING (VL-1/INV-19): every incoming agent is validated FIRST;
        one bad config raises ``AgentConfigurationError`` naming every
        violation, no incoming agent is touched (no ``llm`` injection), and the
        old registry keeps serving.
        """
        with self._agents_lock:
            # VL-1: validate ALL incoming agents before mutating anything.
            all_violations: List[str] = []
            for agent in agents:
                all_violations.extend(self._validate_agent_llm_config(agent))
                all_violations.extend(self._validate_insight_config(agent))
            if all_violations:
                raise AgentConfigurationError(
                    "Agent reload rejected (all-or-nothing; old registry still "
                    "serving): " + " | ".join(all_violations)
                )

            new_agents: List[BaseAgent] = []
            new_index: Dict[str, int] = {}
            new_meta: Dict[str, Tuple[int, int]] = {}
            for index, agent in enumerate(agents):
                agent.llm = self.llm_client
                agent.insight_contract = self.insight_contract
                agent.content_limits = self.content_limits
                new_index[agent.config.id] = index
                new_meta[agent.config.id] = (agent.config.priority, index)
                new_agents.append(agent)
            # Rebind (index/meta first, agents last) — each assignment is atomic.
            self._agent_index = new_index
            self._agent_meta = new_meta
            self.agents = new_agents
            logger.info(f"Replaced agent registry: {len(new_agents)} agents")

    def unregister_agent(self, agent_id: str) -> bool:
        """Remove an agent from the registry by id.

        Returns ``True`` if an agent was removed, ``False`` if no agent had that id.
        Concurrency-safe: rebuilds and rebinds the registry under ``self._agents_lock``
        with the same discipline as ``replace_agents`` (never mutating the live
        structures in place), so a lock-free reader on another thread always sees a
        complete registry. Registration indices are recomputed so the ``_agent_meta``
        tie-break order stays contiguous after the removal.
        """
        with self._agents_lock:
            if agent_id not in self._agent_index:
                return False
            remaining = [a for a in self.agents if a.config.id != agent_id]
            new_index: Dict[str, int] = {}
            new_meta: Dict[str, Tuple[int, int]] = {}
            for index, agent in enumerate(remaining):
                new_index[agent.config.id] = index
                new_meta[agent.config.id] = (agent.config.priority, index)
            self._agent_index = new_index
            self._agent_meta = new_meta
            self.agents = remaining
            self._warned_subscriber_ids.discard(agent_id)
            self._warned_config_agent_ids.discard(agent_id)
        logger.info(f"Unregistered agent: {agent_id}")
        return True

    def update_api_key(self, api_key: Optional[str]) -> None:
        """Update API key for LLM client and re-inject into all agents.

        PRECONDITION (E-4): this method is NOT concurrency-safe and MUST NOT be
        called while a ``process_turn`` is in flight. It swaps ``self.llm_client``
        and re-points every agent's ``llm`` reference without synchronization; an
        overlapping turn could observe a half-swapped state or use a client whose
        underlying HTTP session is being torn down. Callers must quiesce turns
        (or hold their own lock) before invoking it.

        The previous LLM client's underlying HTTP session is closed on a
        best-effort basis to avoid leaking the connection pool. Closing is
        synchronous-safe: if the underlying client only exposes an async close,
        it is scheduled when an event loop is running and otherwise skipped.
        """
        old_client = getattr(self, "llm_client", None)

        # EN-1 / INV-18: rebuild from the engine's stored LLM config — never
        # bare. Key rotation must not silently reset timeout/base_url/wire mode
        # to module defaults mid-session. (Ctor config is authoritative: a
        # hand-swapped ``engine.llm_client`` is not preserved across rotation.)
        self.llm_client = LLMClient(api_key=api_key, **self._llm_config)
        for agent in self.agents:
            agent.llm = self.llm_client

        self._close_llm_client(old_client)
        logger.info("Updated API key for all agents")

    @staticmethod
    def _close_llm_client(llm_client: Optional["LLMClient"]) -> None:
        """Best-effort close of a replaced LLMClient's underlying HTTP session (E-4).

        The wrapped OpenAI ``AsyncOpenAI`` client exposes an async ``close()``.
        ``update_api_key`` is synchronous, so we close it without ever blocking:
        if an event loop is running we schedule the coroutine as a task; if not,
        we run it to completion; if neither is possible we log and move on. The
        connection pool leak this prevents is non-fatal, so any failure here is
        swallowed rather than propagated into the caller.
        """
        if llm_client is None:
            return
        underlying = getattr(llm_client, "client", None)
        close = getattr(underlying, "close", None)
        if close is None:
            return
        try:
            result = close()
            if asyncio.iscoroutine(result):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    asyncio.run(result)
                else:
                    # Fire-and-forget on the running loop, but keep a reference so the
                    # task cannot be GC'd mid-close, and surface any failure through the
                    # done-callback rather than as a GC-time "Task exception was never
                    # retrieved" warning.
                    task = loop.create_task(result)
                    _PENDING_CLOSE_TASKS.add(task)
                    task.add_done_callback(_on_close_task_done)
        except Exception as e:  # pragma: no cover - cleanup is best-effort
            logger.warning(f"Failed to close previous LLM client: {e}")
    
    # =========================================================================
    # Agent Query Methods
    # =========================================================================
    
    def get_agents_by_trigger_type(self, trigger_type: TriggerType) -> List[BaseAgent]:
        """Get all agents that respond to a specific trigger type."""
        return [a for a in self.agents if trigger_type in a.config.trigger_types]
    
    def get_agents_with_keywords(self) -> List[BaseAgent]:
        """Get all agents with keyword triggers."""
        return [a for a in self.agents if a.config.trigger_keywords]
    
    def get_agents_with_silence_threshold(self) -> List[BaseAgent]:
        """Get all agents with silence thresholds."""
        return [a for a in self.agents if a.config.silence_threshold is not None]
    
    def get_event_subscribers(self, event_names: List[str]) -> List[BaseAgent]:
        """Get agents subscribed to any of the given events (v2).

        Only returns agents that have TriggerType.EVENT in their trigger_types.
        Agents with subscribed_events but without EVENT trigger type are
        configuration errors — they are excluded from routing and a warning
        is logged. This is a configuration-time exclusion, not a runtime skip.

        Concurrency: this is a reader — it iterates the lock-free ``self.agents``,
        which the rebind discipline keeps consistent. Its only write is the
        ``_warned_subscriber_ids`` warn-once dedup, which is advisory (observability
        only): under a concurrent registry swap the worst case is a duplicate warning
        line, which is harmless, so it is intentionally not lock-guarded.
        """
        subscribers = []
        for agent in self.agents:
            subscribed = getattr(agent.config, 'subscribed_events', None) or []
            if any(event_name in subscribed for event_name in event_names):
                if TriggerType.EVENT in agent.config.trigger_types:
                    subscribers.append(agent)
                elif agent.config.id not in self._warned_subscriber_ids:
                    # E-6: warn once per misconfigured agent, not every turn it matches.
                    self._warned_subscriber_ids.add(agent.config.id)
                    logger.warning(
                        f"Agent '{agent.config.name}' has subscribed_events "
                        f"{subscribed} but TriggerType.EVENT is not in "
                        f"trigger_types {agent.config.trigger_types}. "
                        f"Skipping for Phase 2 (warned once)."
                    )
        return subscribers
    
    def check_keyword_triggers(self, text: str,
                               allowed_agent_ids: Optional[List[str]] = None) -> List[Tuple[BaseAgent, str]]:
        """Check which agents should trigger based on keywords.
        
        Note: Keyword detection is host responsibility in v2.0. The engine
        provides this as a helper utility. Host is responsible for invoking
        it and passing allowed_agent_ids.

        E-8: matching is case-insensitive **substring** matching, not word-boundary
        matching — keyword "car" matches "scared"/"cart". This is intentional for the
        helper's best-effort role; hosts needing word-boundary semantics should do their
        own matching.

        Args:
            text: Text to search for keywords
            allowed_agent_ids: Optional list of agent IDs to filter by
        
        Returns:
            List of (agent, matched_keyword) tuples
        """
        text_lower = text.lower()
        matches = []
        
        for agent in self.agents:
            if allowed_agent_ids is not None:
                if agent.config.id not in allowed_agent_ids:
                    continue
            
            if agent.config.trigger_keywords:
                for keyword in agent.config.trigger_keywords:
                    if keyword.lower() in text_lower:
                        logger.info(f"MATCH: Agent '{agent.config.name}' triggered by '{keyword}'")
                        matches.append((agent, keyword))
                        break
        return matches
    
    # =========================================================================
    # Main Processing
    # =========================================================================
    
    async def process_turn(self, context: AgentContext,
                          allowed_agent_ids: Optional[List[str]] = None,
                          trigger_type: TriggerType = TriggerType.TURN_BASED,
                          trigger_metadata: Dict[str, Any] = None) -> AgentResponse:
        """Process a turn with multi-phase execution (v2).
        
        Execution Flow:
        1. Set trigger info and sys.* variables
        2. Sync Blackboard → shared_state for v1 compatibility
        3. Phase 1: Run eligible agents against snapshot
        4. Merge updates (ascending priority - higher priority writes last, wins)
        5. If events emitted, Phase 2: Run event subscribers
        6. Clear events, return aggregated response
        
        Args:
            context: The full context for agents
            allowed_agent_ids: Optional hard allow-list (None = all agents)
            trigger_type: What triggered this turn
            trigger_metadata: Additional trigger info (keyword, silence duration, etc.)
        
        Returns:
            Aggregated AgentResponse with all insights and state updates
        """
        try:
            return await self._process_turn_inner(context, allowed_agent_ids,
                                                   trigger_type, trigger_metadata)
        except Exception as e:
            for cb in self.callbacks:
                try:
                    await cb.on_chain_error(e)
                except Exception as cb_err:
                    logger.error(f"Callback error on_chain_error: {cb_err}")
            raise

    async def _process_turn_inner(self, context: AgentContext,
                                   allowed_agent_ids: Optional[List[str]],
                                   trigger_type: TriggerType,
                                   trigger_metadata: Dict[str, Any]) -> AgentResponse:
        """Inner implementation of process_turn (extracted for on_chain_error wrapping)."""
        start_time = time.time()

        # Set trigger info in context
        context.trigger_type = trigger_type
        context.trigger_metadata = trigger_metadata or {}
        
        # Ensure Blackboard exists
        if context.blackboard is None:
            context.blackboard = Blackboard()
        
        # Set sys.* variables (engine-owned)
        context.blackboard.set_var("sys.turn_count", context.turn_count, _engine_internal=True)
        context.blackboard.set_var("sys.session_id", context.session_id, _engine_internal=True)
        context.blackboard.set_var("sys.trigger_type", trigger_type.value, _engine_internal=True)
        
        # Sync Blackboard → shared_state for v1 compatibility AND the MR-1
        # memory read-path (memory_<id> keys DynamicAgent reads from; INV-14).
        self._sync_state_to_legacy(context)

        # XUBB-ITC-1 §11.2 (G3): validate the host's answer events ONCE per turn
        # against the retained question records. Invalid events are dropped with
        # an engine-level diagnostic; agents only ever see the validated subset
        # (phase copies). The host's own list is never mutated.
        # §10.3: correction targets reserved by an accepted response in this turn.
        # A later phase cannot overturn an earlier phase's reservation.
        self._reserved_correction_targets = set()
        self._validated_answers, answer_issues = validate_answers(
            list(context.insight_answers), list(context.insight_reference_context.prior_insights),
            context.session_id, context.principal_id)

        # Build execution metadata for condition evaluation
        meta = {
            "turn_count": context.turn_count,
            "trigger_type": trigger_type.value,
            "phase": 1,
            "session_id": context.session_id
        }
        
        # Fire on_turn_start callbacks
        for cb in self.callbacks:
            try:
                await cb.on_turn_start(context)
            except Exception as e:
                logger.error(f"Callback error on_turn_start: {e}")
        
        # Initialize aggregated response
        final_response = AgentResponse()
        turn_execution_id = uuid.uuid4().hex
        for issue in answer_issues:
            final_response.diagnostics.append(InsightDiagnostic(
                execution_id=turn_execution_id, agent_id="engine", code=issue.code,
                field_path=issue.field_path, classification=issue.classification))
        all_events: List[Event] = []
        
        # =====================================================================
        # Phase 1: Primary Execution
        # =====================================================================
        context.phase = 1
        meta["phase"] = 1
        
        phase1_agents = await self._get_eligible_agents(
            context, allowed_agent_ids, trigger_type, meta
        )
        
        if phase1_agents:
            logger.info(f"Phase 1: Running {len(phase1_agents)} eligible agents")
            
            # Fire on_phase_start
            for cb in self.callbacks:
                try:
                    await cb.on_phase_start(1, [a.config.name for a in phase1_agents])
                except Exception as e:
                    logger.error(f"Callback error on_phase_start: {e}")
            
            # Run phase 1 and merge results
            phase1_responses = await self._run_phase(phase1_agents, context)
            await self._arbitrate_corrections(phase1_responses)
            self._merge_responses(phase1_responses, context.blackboard, final_response, phase=1)
            
            # Collect events emitted in phase 1
            for resp in phase1_responses:
                all_events.extend(resp.events)
            
            # Apply events to blackboard
            for event in all_events:
                context.blackboard.emit_event(event)
            
            # Fire on_phase_end
            event_names = list(set(e.name for e in all_events))
            for cb in self.callbacks:
                try:
                    await cb.on_phase_end(1, event_names)
                except Exception as e:
                    logger.error(f"Callback error on_phase_end: {e}")
        
        # =====================================================================
        # Phase 2: Event-Triggered Execution (if events were emitted)
        # =====================================================================
        if all_events and self.max_phases >= 2:
            # Re-sync shared_state for v1 agents AND the MR-1 memory read-path
            # (memory_<id> keys; INV-14) in Phase 2
            self._sync_state_to_legacy(context)

            # Capture the host-owned context mutation targets BEFORE mutating so
            # they can be restored unconditionally. The context is reused across
            # turns by the host; leaving trigger_type=EVENT / phase=2 behind after
            # a mid-phase exception would corrupt every subsequent turn (E-1 / INV-12).
            original_trigger_type = context.trigger_type
            original_phase = context.phase

            # Set trigger_type to EVENT so Phase 2 agents pass their
            # own trigger_type check in BaseAgent.process().
            context.phase = 2
            meta["phase"] = 2
            context.trigger_type = TriggerType.EVENT

            try:
                event_names = list(set(e.name for e in all_events))
                phase2_agents = self.get_event_subscribers(event_names)

                # Filter by allowed_agent_ids and conditions
                phase2_agents = [
                    a for a in phase2_agents
                    if self._is_eligible_for_phase2(a, context, allowed_agent_ids, meta)
                ]

                if phase2_agents:
                    logger.info(f"Phase 2: Running {len(phase2_agents)} event subscribers "
                               f"for events: {event_names}")

                    # Fire on_phase_start
                    for cb in self.callbacks:
                        try:
                            await cb.on_phase_start(2, [a.config.name for a in phase2_agents])
                        except Exception as e:
                            logger.error(f"Callback error on_phase_start: {e}")

                    # Run phase 2 and merge results
                    phase2_responses = await self._run_phase(phase2_agents, context)
                    await self._arbitrate_corrections(phase2_responses)
                    self._merge_responses(phase2_responses, context.blackboard, final_response, phase=2)

                    # Events emitted in Phase 2 are recorded but NOT dispatched
                    phase2_events = []
                    for resp in phase2_responses:
                        phase2_events.extend(resp.events)
                        all_events.extend(resp.events)  # Include in telemetry

                    if phase2_events:
                        logger.debug(f"Phase 2 emitted {len(phase2_events)} events "
                                    "(recorded but not dispatched)")

                    # Fire on_phase_end
                    for cb in self.callbacks:
                        try:
                            await cb.on_phase_end(2, [e.name for e in phase2_events])
                        except Exception as e:
                            logger.error(f"Callback error on_phase_end: {e}")
            finally:
                # Always restore the host-owned context, even if Phase 2 raised
                # (E-1 / INV-12). The on_chain_error path (B5) still fires because
                # the exception propagates out of _process_turn_inner unimpeded.
                context.trigger_type = original_trigger_type
                context.phase = original_phase

        # =====================================================================
        # Finalization
        # =====================================================================
        
        # Clear events from blackboard (events are transient)
        context.blackboard.clear_events()
        
        # Include all emitted events in response (for telemetry)
        final_response.events = all_events
        
        # Sync v1 state_updates from v2 variable_updates
        if final_response.variable_updates:
            final_response.state_updates.update(final_response.variable_updates)
        
        # Calculate duration
        turn_duration = time.time() - start_time
        
        # Fire on_turn_end callbacks
        for cb in self.callbacks:
            try:
                await cb.on_turn_end(final_response, turn_duration)
            except Exception as e:
                logger.error(f"Callback error on_turn_end: {e}")
        
        logger.info(f"Turn completed in {turn_duration*1000:.0f}ms with "
                   f"{len(final_response.insights)} insights")
        
        return final_response
    
    # =========================================================================
    # Phase Execution
    # =========================================================================
    
    async def _run_phase(self, agents: List[BaseAgent],
                         context: AgentContext) -> List[AgentResponse]:
        """Run a phase with snapshot isolation.
        
        All agents in the phase evaluate against the same immutable snapshot
        of the Blackboard. State updates are collected and merged only after
        all agents complete.
        """
        # Create snapshot for phase isolation. Known tradeoff: snapshot() deep-copies
        # the whole blackboard (events/variables/queues/facts/memory), so cost grows
        # O(accumulated state) per phase over a long session. This buys each phase a
        # stable read-view while agents run in parallel; if it ever shows up in turn
        # latency, a copy-on-write / read-only view is the place to optimize.
        snapshot = context.blackboard.snapshot()
        
        # Create a context with the snapshot for agents to read
        phase_context = AgentContext(
            session_id=context.session_id,
            recent_segments=context.recent_segments,
            shared_state=deepcopy(context.shared_state),
            blackboard=snapshot,
            rag_docs=context.rag_docs,
            trigger_type=context.trigger_type,
            trigger_metadata=context.trigger_metadata,
            language_directive=context.language_directive,
            user_context=context.user_context,
            turn_count=context.turn_count,
            phase=context.phase,
            agent_config_overrides=context.agent_config_overrides,
            # XUBB-ITC-1 §6.4 / ITC-14: trusted host inputs are frozen before the
            # run and propagated through EVERY phase-context copy (Phase 1 and 2).
            principal_id=context.principal_id,
            insight_capabilities=context.insight_capabilities.model_copy(deep=True),
            insight_reference_context=context.insight_reference_context.model_copy(deep=True),
            # only the VALIDATED answers reach agents (§11.2)
            insight_answers=[a.model_copy(deep=True) for a in getattr(self, "_validated_answers", [])],
            # C1 §14.6: host depth requests and the trusted execution declaration
            insight_content_requests={k: v.model_copy(deep=True) for k, v in context.insight_content_requests.items()},
            content_execution_context=(context.content_execution_context.model_copy(deep=True)
                                       if context.content_execution_context is not None else None),
        )
        
        # Run all agents in parallel — each on ITS OWN invocation view (H1 / XA-02:
        # answer visibility is decided here, from the frozen context, for every
        # access path an agent has).
        tasks = []
        for agent in agents:
            tasks.append(self._run_agent_safe(agent, self._scoped_view(phase_context, agent)))
        
        results = await asyncio.gather(*tasks)
        
        # Filter out None results (failed agents)
        return [r for r in results if r is not None]
    
    # =========================================================================
    # C2 (§14.6.1) — isolated content tasks
    # =========================================================================

    def start_content_request(self, context: AgentContext, agent_id: str,
                              request: InsightContentRequest) -> "ContentTaskHandle":
        """Run one extended-content generation OUTSIDE the live turn path.

        The task owns a fresh agent instance and a frozen deep copy of the
        context (transcript, Blackboard snapshot, capabilities, references) under
        an engine-issued isolated declaration. It never holds the live turn path,
        never writes the live Blackboard or durable private memory, never bumps
        the live turn counter and never reserves correction targets; its output
        is result-only. Admission is bounded by ``content_limits.max_concurrent_
        content_tasks`` (default 1). Cancel the handle, or ``close_session_content``,
        to revoke publication: a late result then reports ``cancelled`` with its
        diagnostics and usage retained. The host checks currentness against
        ``source_snapshot_id`` before presenting the result.
        """
        agent = next((a for a in self.agents if a.config.id == agent_id), None)
        if agent is None:
            raise ValueError(f"unknown agent id {agent_id!r}")
        clone = getattr(agent, "clone_for_isolated_run", None)
        request_id = request.request_id or uuid.uuid4().hex
        snapshot_id = uuid.uuid4().hex
        frozen = self._scoped_view(context.model_copy(deep=True), agent)
        declaration = ContentExecutionContext(
            session_mode="active", execution_path="isolated_content",
            request_id=request_id, source_snapshot_id=snapshot_id,
            holds_live_turn_lock=False, writes_live_blackboard=False,
            pause_declared=None, task_isolation_verified=clone is not None)
        declaration._engine_issued = True
        frozen.content_execution_context = declaration
        frozen.insight_content_requests = {agent_id: InsightContentRequest(depth=request.depth, request_id=request_id)}
        handle = ContentTaskHandle(request_id=request_id, source_snapshot_id=snapshot_id,
                                   session_id=context.session_id, agent_id=agent_id,
                                   snapshot_turn=context.turn_count)
        runner = clone() if clone is not None else None
        handle.task = asyncio.get_running_loop().create_task(self._run_content_task(handle, runner, frozen))
        self._content_tasks.setdefault(context.session_id, []).append(handle)
        return handle

    def close_session_content(self, session_id: str) -> int:
        """Session closure revokes publication for every pending content task of
        the session and cancels them. Returns the number of handles affected."""
        handles = self._content_tasks.pop(session_id, [])
        for h in handles:
            h.cancel()
        return len(handles)

    async def _run_content_task(self, handle: "ContentTaskHandle", agent: Optional[BaseAgent],
                                frozen: AgentContext) -> ContentResult:
        def diag(code: str, path: str, classification: Optional[str] = None) -> InsightDiagnostic:
            return InsightDiagnostic(execution_id=handle.request_id, agent_id=handle.agent_id, code=code,
                                     field_path=path, classification=classification)

        def finish(status: str, insight=None, diagnostics=(), usage=None) -> ContentResult:
            return ContentResult(request_id=handle.request_id, source_snapshot_id=handle.source_snapshot_id,
                                 session_id=handle.session_id, agent_id=handle.agent_id,
                                 snapshot_turn=handle.snapshot_turn, status=status, insight=insight,
                                 diagnostics=list(diagnostics), usage=usage)

        if agent is None:
            # Only agents that can be re-instantiated from their definition are
            # isolatable; a custom BaseAgent instance would be shared mutable state.
            return finish("rejected", diagnostics=[diag("content_execution_not_allowed", "$", "agent_not_isolatable")])
        if self._content_slots.locked():
            return finish("rejected", diagnostics=[diag("content_execution_not_allowed", "$", "provider_admission_exhausted")])
        async with self._content_slots:
            try:
                response = await agent.evaluate(frozen)   # no turn callbacks: isolated trace
            except asyncio.CancelledError:
                handle.publishable = False
                return finish("cancelled", diagnostics=[diag("content_execution_not_allowed", "$", "cancelled")])
            except Exception as e:
                return finish("rejected", diagnostics=[diag("invalid_envelope", "$", type(e).__name__)])
        if response is None:
            return finish("rejected", diagnostics=[diag("invalid_envelope", "$", "none")])
        response.source_agent_id = handle.agent_id
        self._enforce_acceptance(agent, response, frozen)
        diagnostics = list(response.diagnostics)
        usage = response.usage
        # Result-only, belt and braces: nothing from this task may carry effects.
        effects = any([response.events, response.variable_updates, response.queue_pushes, response.facts,
                       response.memory_updates, response.state_updates, response.data])
        insights = [i for i in response.insights if getattr(i, "_origin", "agent") != "framework"]
        if response.acceptance_status != "rejected" and effects:
            diagnostics.append(diag("content_execution_not_allowed", "$", "domain_effects_on_isolated_path"))
            return finish("rejected", diagnostics=diagnostics, usage=usage)
        if any(i.type in (InsightType.CORRECTION, InsightType.QUESTION) for i in insights):
            diagnostics.append(diag("content_execution_not_allowed", "insight.type", "interactive_type_on_isolated_path"))
            return finish("rejected", diagnostics=diagnostics, usage=usage)
        if not handle.publishable:
            # Cancelled or session closed while generating: no late publication.
            return finish("cancelled", diagnostics=diagnostics + [diag("content_execution_not_allowed", "$", "publication_revoked")], usage=usage)
        if response.acceptance_status == "rejected":
            for cb in self.callbacks:
                try:
                    await cb.on_insight_validation_error(diagnostics[0] if diagnostics else diag("invalid_envelope", "$"))
                except Exception as cb_err:
                    logger.error(f"Callback error on_insight_validation_error: {cb_err}")
            return finish("rejected", diagnostics=diagnostics, usage=usage)
        if not insights:
            return finish("silent", diagnostics=diagnostics, usage=usage)
        insight = insights[0]
        insight.source_snapshot_id = handle.source_snapshot_id
        insight.content_request_id = handle.request_id
        return finish("accepted", insight=insight, diagnostics=diagnostics, usage=usage)

    def _scoped_view(self, context: AgentContext, agent: BaseAgent) -> AgentContext:
        """H1 (XA-02): the per-agent invocation view. A validated answer is visible
        to the agent that asked the question (correlated through the retained
        question record) or to everyone only when the host authorised sharing.
        The filter is applied to the CONTEXT OBJECT the agent receives, so it
        holds through direct attribute access, template aliases, custom agents
        and isolated content tasks alike — not merely a prompt shortcut."""
        shared = bool(context.insight_capabilities.answers_shared)
        questions = {r.id: r for r in context.insight_reference_context.prior_insights if r.type == "question"}
        visible = []
        for a in context.insight_answers:
            rec = questions.get(a.question_insight_id)
            if shared or (rec is not None and rec.agent_id == agent.config.id):
                visible.append(a.model_copy(deep=True))
        return context.model_copy(update={"insight_answers": visible})

    def _boundary_reference_context(self, agent: BaseAgent, response: AgentResponse,
                                    context: AgentContext) -> ReferenceContext:
        """What an insight's references may resolve against at the boundary: the
        host's trusted records for this session plus the framework's own
        snapshot of what THIS run exposed — taken from the agent instance and
        only when it belongs to this execution, never from the mutable response."""
        snap = getattr(agent, "_last_snapshot", None)
        if snap is not None and snap.snapshot_id != response.execution_id:
            snap = None
        response.evidence_snapshot = snap        # authority from the invocation, not the producer
        ref = ReferenceContext(session_id=context.session_id, snapshot_id=snap.snapshot_id if snap else "")
        if snap is not None:
            for e in snap.entries:
                ref.add(e.kind, e.ref_id, e.revision)
        host = context.insight_reference_context
        for e in host.evidence:
            ref.add(e.kind, e.ref_id, e.revision, e.session_id)
        for r in host.prior_insights:
            ref.add("insight", r.id, None, r.session_id)
        return ref

    @staticmethod
    def _candidate_projection(insight: AgentInsight) -> Dict[str, Any]:
        """The producer-controlled fields of an insight, as a wire-shaped
        candidate for the strict validator. Engine-owned fields are checked
        separately and never enter the projection."""
        def dump(v):
            return v.model_dump() if hasattr(v, "model_dump") else v
        t = insight.type
        cand: Dict[str, Any] = {
            "type": t.value if isinstance(t, InsightType) else t,
            "content": insight.content,
            "confidence": insight.confidence,
            "observation_kind": insight.observation_kind,
            "evidence_refs": [dump(r) for r in insight.evidence_refs] if isinstance(insight.evidence_refs, list) else insight.evidence_refs,
            "rationale": insight.rationale,
            "validation_step": insight.validation_step,
            "assumptions": insight.assumptions,
            "correction": dump(insight.correction),
            "question": dump(insight.question),
            "metadata": insight.metadata,
        }
        if insight.urgency is not None:
            cand["urgency"] = insight.urgency
        if insight.preview is not None:
            cand["preview"] = insight.preview
        if insight.content_format is not None:
            cand["content_format"] = insight.content_format
        return cand

    async def _run_agent_safe(self, agent: BaseAgent,
                              context: AgentContext) -> Optional[AgentResponse]:
        """Run an agent with atomic failure handling.

        Callbacks are fired by agent.process() — the engine does NOT
        duplicate them here (B2 fix). If agent.process() itself raises
        (unexpected), we catch and discard to preserve atomic failure.
        """
        try:
            response = await agent.process(context, callbacks=self.callbacks)
        except Exception as e:
            logger.error(f"Agent {agent.config.name} failed unexpectedly: {e}")
            return None
        if response is None:
            return None
        # XUBB-ITC-1 (G0/G1): engine-boundary acceptance. Revalidates EVERY response
        # (DynamicAgent staging and custom BaseAgent subclasses alike) and is the
        # single emitter of on_insight_validation_error — once per rejected or
        # partial execution result.
        self._enforce_acceptance(agent, response, context)
        if response.acceptance_status in ("partial", "rejected") and response.diagnostics:
            primary = next((d for d in response.diagnostics
                            if d.code != "partial_legacy_response"), response.diagnostics[0])
            for cb in self.callbacks:
                try:
                    await cb.on_insight_validation_error(primary)
                except Exception as cb_err:
                    logger.error(f"Callback error on_insight_validation_error: {cb_err}")
        return response

    # =========================================================================
    # Engine-boundary acceptance (XUBB-ITC-1 §6.1 / §8.6, D-LR) — legacy_v2
    # =========================================================================

    def _enforce_acceptance(self, agent: BaseAgent, response: AgentResponse,
                            context: Optional[AgentContext] = None) -> None:
        """Revalidate a response at the engine boundary and apply the contract.

        A mutable object that passed model construction is not proof that its
        current content is valid, so this runs for every response:

        * a proposed write to the reserved ``sys.*`` namespace rejects the
          whole response (``reserved_state_write``) in both contracts;
        * ``legacy_v2`` (D-LR): insight types must be in the legacy human-facing
          set; an ERROR is accepted only with runtime-established framework
          provenance. Any other insight rejects ALL insights from the result
          (never relabelled) → ``partial`` if independently valid channels
          remain, else ``rejected``; on ``partial`` the ``data`` sidecar is withheld;
        * ``typed_v1`` (§8.4): every insight must be in the run's effective set
          and must not carry engine-owned identity; any violation rejects the
          whole response. Accepted insights are then stamped with an engine-
          minted session-unique ``id``, ``turn`` and ``contract_version``, a
          runtime-derived ``confidence_provided`` (unknown provenance ⇒ False,
          never certainty) and a resolved ``urgency``.
        """
        agent_id = agent.config.id
        execution_id = response.execution_id or f"boundary-{id(response):x}"
        response.execution_id = execution_id

        def diag(code: str, path: str, classification=None, **extra) -> InsightDiagnostic:
            return InsightDiagnostic(execution_id=execution_id, agent_id=agent_id, code=code,
                                     field_path=path, classification=classification, **extra)

        # --- fatal: domain channels revalidated on the OBJECT that would commit
        # (H1 / XA-01): shape, reserved ``sys.*`` writes, fact confidence. Applies
        # to every producer and to callback-modified responses; a fatal domain
        # error rejects the whole response in both contracts (D-LR).
        if response.acceptance_status != "rejected":
            fatal = [diag(i.code, i.field_path, i.classification) for i in validate_response_channels(response)]
            if fatal:
                self._reject_whole(response, fatal)
                return

        if self.insight_contract == "typed_v1":
            self._enforce_typed(agent, response, context, diag)
            return

        # --- insight component: allowed types + ERROR provenance --------------
        insight_issues: List[InsightDiagnostic] = []
        for i, insight in enumerate(response.insights):
            value = insight.type.value if isinstance(insight.type, InsightType) else str(insight.type)
            if value in LEGACY_HUMAN_TYPES:
                continue
            if value == InsightType.ERROR.value and getattr(insight, "_origin", "agent") == "framework":
                continue
            insight_issues.append(diag("type_not_allowed", f"insights[{i}].type", bounded(value)))

        if not insight_issues:
            return  # nothing to change — the producer's status stands

        # Recoverable insight error at the boundary (custom agent path):
        # drop every insight, keep independently valid channels, report.
        retained = [name for name, value in (
            ("events", response.events), ("variable_updates", response.variable_updates),
            ("queue_pushes", response.queue_pushes), ("facts", response.facts),
            ("memory_updates", response.memory_updates), ("state_updates", response.state_updates),
        ) if value]
        response.insights = []
        response.diagnostics.extend(insight_issues)
        if retained:
            withheld = ["data"] if response.data else []
            response.data = {}
            response.acceptance_status = "partial"
            response.diagnostics.append(diag("partial_legacy_response", "$",
                                             retained_channels=retained, withheld_channels=withheld))
        else:
            self._reject_whole(response, [])

    # Public fields only the engine may set (§14.2). A producer — or a callback
    # touching the response after staging — leaves them None; trusted staging
    # hands its runtime-derived values over privately (AgentInsight._staged).
    ENGINE_OWNED_PUBLIC_FIELDS = ("id", "turn", "contract_version", "confidence_provided", "content_contract",
                                  "response_depth", "content_request_id", "source_snapshot_id")

    def _enforce_typed(self, agent: BaseAgent, response: AgentResponse,
                       context: Optional[AgentContext], diag) -> None:
        """typed_v1 boundary (§6.1, §8.1 steps 5–8, §14.2) — H1: ONE authoritative
        acceptance pipeline for every producer (DynamicAgent staging, custom
        BaseAgent subclasses, callback-modified responses):

        1. a rejected result stays rejected; a framework ERROR card it carries
           becomes a diagnostic — typed failures never enter the human-facing
           insight channel (XA-07; the ERROR card remains legacy-only);
        2. every insight must be an AgentInsight with every engine-owned public
           field unset;
        3. the producer-controlled projection of every insight is re-run through
           the strict candidate validator against the run's effective set,
           profile, urgency default, reference context (host records + this
           run's own snapshot) and negotiated content extension — so a QUESTION
           without its payload, a hypothesis without evidence, an empty body, a
           non-finite confidence or an un-negotiated content field rejects here,
           whichever class produced it;
        4. correction targets are validated against the trusted history under the
           frozen principal;
        5. any violation rejects the WHOLE response (§8.4). Otherwise the
           validated candidate is written back and the engine stamps identity,
           provenance and the content-contract fields.
        """
        if response.acceptance_status == "rejected":
            errors = [i for i in response.insights if isinstance(i, AgentInsight) and i.type is InsightType.ERROR
                      and getattr(i, "_origin", "agent") == "framework"]
            for err in errors:
                category = (err.metadata or {}).get("exception_type", "unknown") if isinstance(err.metadata, dict) else "unknown"
                response.diagnostics.append(diag("invalid_envelope", "$", f"agent_error:{bounded(category)}"))
            response.insights = []
            return
        eff = self.effective_insight_types(agent, context)
        cfg = getattr(agent.config, "insight_config", None)
        profile = cfg.analysis_profile if cfg is not None else "general"
        default_urgency = cfg.default_urgency if cfg is not None else None
        reference = self._boundary_reference_context(agent, response, context) if context is not None else None
        fatal: List[InsightDiagnostic] = []
        validated = []
        for i, insight in enumerate(response.insights):
            path = f"insights[{i}]"
            if not isinstance(insight, AgentInsight):
                fatal.append(diag("invalid_field", path, bounded(insight)))
                continue
            for owned in self.ENGINE_OWNED_PUBLIC_FIELDS:
                if getattr(insight, owned) is not None:
                    fatal.append(diag("invalid_field", f"{path}.{owned}", "engine_owned"))
            staged = getattr(insight, "_staged", None)
            extension = bool(staged and staged.get("content_extension"))
            typed, issues = validate_typed_candidate(
                self._candidate_projection(insight), effective=eff, analysis_profile=profile,
                default_urgency=default_urgency, reference_context=reference,
                reference_context_available=reference is not None,
                content_extension_enabled=extension)
            for issue in issues:
                field = issue.field_path[len("insight."):] if issue.field_path.startswith("insight.") else issue.field_path
                fatal.append(diag(issue.code, f"{path}.{field}" if field != "insight" else path, issue.classification))
            if typed is not None:
                validated.append((insight, typed, staged))
        # §10.1 (G3 part 2): correction targets — validated here, at the ONE
        # boundary both DynamicAgent and custom agents pass through, under the
        # FROZEN principal (H1 / XA-03: a missing identity rejects).
        if context is not None:
            caps = context.insight_capabilities
            for i, (insight, typed, _staged) in enumerate(validated):
                if typed.type_value != "correction":
                    continue
                issue = validate_correction_target(
                    typed.correction, prior_insights=list(context.insight_reference_context.prior_insights),
                    session_id=context.session_id, principal_id=context.principal_id,
                    turn_count=context.turn_count, agent_id=agent.config.id,
                    policy=caps.correction_agent_policy, allowlist=tuple(caps.correction_agent_ids),
                    field_path=f"insights[{response.insights.index(insight)}].correction")
                if issue is not None:
                    fatal.append(diag(issue.code, issue.field_path, issue.classification))
        if fatal:
            self._reject_whole(response, fatal)
            return
        turn = context.turn_count if context is not None else None
        for insight, typed, staged in validated:
            # write back the VALIDATED candidate (normalised urgency, resolved
            # evidence revisions, normative payload models)
            insight.type = InsightType(typed.type_value)
            insight.content = typed.content
            insight.confidence = typed.confidence
            insight.urgency = typed.urgency
            insight.observation_kind = typed.observation_kind
            insight.evidence_refs = [EvidenceRef(**r) for r in typed.evidence_refs]
            insight.rationale = typed.rationale
            insight.validation_step = typed.validation_step
            insight.assumptions = list(typed.assumptions)
            insight.correction = CorrectionPayload(**typed.correction) if typed.correction else None
            insight.question = QuestionPayload(**typed.question) if typed.question else None
            insight.metadata = dict(typed.metadata)
            # engine-owned stamps (§8.1 step 8)
            insight.id = uuid.uuid4().hex
            insight.turn = turn
            insight.contract_version = "typed_v1"
            # provenance is runtime-derived by trusted staging; a producer that
            # bypassed staging has unknown provenance — never certainty
            insight.confidence_provided = bool(staged["confidence_provided"]) if staged else False
            content = staged.get("content") if staged else None
            if content:
                insight.content_contract = content["content_contract"]
                insight.response_depth = content["response_depth"]
                insight.content_request_id = content["content_request_id"]
                insight.source_snapshot_id = content["source_snapshot_id"]
            insight._staged = None

    async def _arbitrate_corrections(self, responses: List[AgentResponse]) -> None:
        """§10.3 (G3 part 2): deterministic, response-level correction arbitration
        at phase close — BEFORE anything from the phase commits.

        Every correction-bearing response has been held whole (the phase gathers
        all results before merging). Complete, accepted responses that carry
        corrections are ordered by descending agent priority, then later
        registration; a response is accepted only when ALL its targets are still
        unreserved, and then reserves all of them together. Otherwise the whole
        response is rejected with ``correction_conflict`` — it reserves nothing
        and commits nothing (siblings, state, events, memory, sidecars included).
        Duplicate targets inside one response reject it. Reservations made by an
        earlier phase of the same turn cannot be overturned. This is authority
        ordering, never truth adjudication.
        """
        bearing = []
        for resp in responses:
            if resp is None or resp.acceptance_status == "rejected":
                continue
            targets = [ins.correction.target_insight_id for ins in resp.insights
                       if ins.type is InsightType.CORRECTION and ins.correction is not None]
            if targets:
                meta = self._agent_meta.get(resp.source_agent_id or "", (0, 0))
                bearing.append((-meta[0], -meta[1], resp, targets))
        for _neg_priority, _neg_index, resp, targets in sorted(bearing, key=lambda b: (b[0], b[1])):
            execution_id = resp.execution_id or "arbitration"
            agent_id = resp.source_agent_id or "unknown"
            if len(set(targets)) != len(targets):
                reason = "duplicate_targets_in_response"
            elif any(t in self._reserved_correction_targets for t in targets):
                reason = "target_already_reserved"
            else:
                self._reserved_correction_targets.update(targets)
                continue
            diagnostic = InsightDiagnostic(execution_id=execution_id, agent_id=agent_id,
                                           code="correction_conflict", field_path="insights[].correction",
                                           classification=reason)
            self._reject_whole(resp, [diagnostic])
            for cb in self.callbacks:
                try:
                    await cb.on_insight_validation_error(diagnostic)
                except Exception as cb_err:
                    logger.error(f"Callback error on_insight_validation_error: {cb_err}")

    @staticmethod
    def _reject_whole(response: AgentResponse, diagnostics: List[InsightDiagnostic]) -> None:
        """D-LR fatal path: nothing from the response may commit or be shown.
        Usage, debug_info and diagnostics are execution telemetry and survive."""
        response.diagnostics.extend(diagnostics)
        response.acceptance_status = "rejected"
        response.insights = []
        response.events = []
        response.variable_updates = {}
        response.queue_pushes = {}
        response.facts = []
        response.memory_updates = {}
        response.state_updates = {}
        response.data = {}
    
    # =========================================================================
    # Response Merging
    # =========================================================================
    
    def _merge_responses(self, responses: List[AgentResponse],
                         blackboard: Blackboard,
                         final_response: AgentResponse,
                         phase: int = 1) -> None:
        """Merge agent responses with deterministic ordering.
        
        Updates are applied in ASCENDING priority order (low → high) so that
        higher-priority agents write last and therefore win (last-write-wins).
        
        Within the same priority, agent registration order is used as a
        stable tie-breaker.
        """
        # Collect updates with priority and registration order
        updates: List[Tuple[int, int, str, AgentResponse]] = []
        
        for resp in responses:
            # Find the agent that produced this response
            agent_id = resp.source_agent_id

            # Fallback for v1 compat (responses without source_agent_id)
            if not agent_id and resp.insights:
                agent_id = resp.insights[0].agent_id

            # O(1) lookup of (priority, registration-order) instead of a linear
            # scan of self.agents per response (E-5). An unresolvable agent_id is a
            # latent ordering bug: it falls back to (0, 0) but is logged loudly.
            meta = self._agent_meta.get(agent_id) if agent_id else None
            if meta is None:
                agent_priority, agent_index = 0, 0
                logger.warning(
                    f"Could not resolve agent_id '{agent_id}' to a registered "
                    f"agent during merge; defaulting priority/order to 0. Merge "
                    f"ordering for this response may be non-deterministic."
                )
            else:
                agent_priority, agent_index = meta

            updates.append((agent_priority, agent_index, agent_id or "unknown", resp))
        
        # Sort by ASCENDING priority, then by registration order
        # This means higher priority agents write LAST (and win)
        updates.sort(key=lambda x: (x[0], x[1]))
        
        # Apply updates
        for priority, index, agent_id, resp in updates:
            # XUBB-ITC-1 (G0): record the D-LR disposition and carry the sanitized
            # diagnostics; a REJECTED response commits nothing. Its only pass-through
            # is a framework-manufactured ERROR insight (runtime provenance), kept as
            # the migration-era legacy diagnostic channel (§14.3).
            final_response.acceptance_by_agent[agent_id] = resp.acceptance_status
            final_response.diagnostics.extend(resp.diagnostics)
            if resp.evidence_snapshot is not None:
                final_response.evidence_snapshots_by_agent[agent_id] = resp.evidence_snapshot
            if resp.acceptance_status == "rejected":
                if self.insight_contract != "typed_v1":     # H1 / XA-07: legacy surface only
                    final_response.insights.extend(
                        i for i in resp.insights
                        if i.type == InsightType.ERROR and getattr(i, "_origin", "agent") == "framework"
                    )
                continue

            # Merge insights, stamping the D-CR stable merge order
            # (phase, registered-agent index, candidate ordinal) — never arrival.
            for ordinal, insight in enumerate(resp.insights):
                insight._merge_order = (phase, index, ordinal)
            final_response.insights.extend(resp.insights)
            
            # Merge data sidecar
            for key, value in resp.data.items():
                if key not in final_response.data:
                    final_response.data[key] = value
                elif isinstance(final_response.data[key], list) and isinstance(value, list):
                    final_response.data[key].extend(value)
                else:
                    final_response.data[key] = value
            
            # Apply variable updates to blackboard
            for key, value in resp.variable_updates.items():
                blackboard.set_var(key, value)
                final_response.variable_updates[key] = value
            
            # Apply queue pushes to blackboard
            for queue_name, items in resp.queue_pushes.items():
                blackboard.push_queue_items(queue_name, items)
                if queue_name not in final_response.queue_pushes:
                    final_response.queue_pushes[queue_name] = []
                final_response.queue_pushes[queue_name].extend(items)
            
            # Apply facts to blackboard. Stamp the emitting agent's priority so add_fact
            # resolves (type,key) conflicts by (priority, confidence) per INV-9 — higher
            # priority wins regardless of confidence; confidence is only the tiebreaker
            # within equal priority. (deduplication handled by Blackboard.add_fact)
            # NOTE: the stamp mutates each Fact in place — by design, per the documented
            # "engine stamps priority" contract — so the same objects surface (already
            # stamped) in final_response.facts below. Agents must not share one Fact
            # instance across responses expecting an unstamped copy back.
            for fact in resp.facts:
                fact.priority = priority
                blackboard.add_fact(fact)
            final_response.facts.extend(resp.facts)
            
            # Apply memory updates to blackboard
            if resp.memory_updates and agent_id:
                blackboard.update_memory(agent_id, resp.memory_updates)
                # Existing flat merge (backward compatible, last-write-wins)
                final_response.memory_updates.update(resp.memory_updates)
                # Per-agent keyed field (additive)
                if agent_id not in final_response.memory_updates_by_agent:
                    final_response.memory_updates_by_agent[agent_id] = {}
                final_response.memory_updates_by_agent[agent_id].update(resp.memory_updates)
            
            # Handle v1 state_updates (map to variable_updates).
            # E-3: the legacy memory_{agent_id} writes must be processed
            # unconditionally — a hybrid response carrying BOTH state_updates and
            # variable_updates previously dropped them silently. Only the plain-var
            # portion is skipped when v2 variable_updates are present (they
            # supersede the legacy variable channel).
            if resp.state_updates:
                v2_supersedes = bool(resp.variable_updates)
                for key, value in resp.state_updates.items():
                    # Check for legacy memory_{agent_id} pattern
                    if key.startswith("memory_"):
                        # Extract memory data and apply to blackboard memory.
                        # Always applied, regardless of variable_updates presence.
                        mem_agent_id = key.replace("memory_", "")
                        if isinstance(value, dict):
                            blackboard.update_memory(mem_agent_id, value)
                    elif not v2_supersedes:
                        blackboard.set_var(key, value)
                        final_response.variable_updates[key] = value
    
    # =========================================================================
    # Eligibility Checks
    # =========================================================================
    
    async def _get_eligible_agents(self, context: AgentContext,
                                   allowed_agent_ids: Optional[List[str]],
                                   trigger_type: TriggerType,
                                   meta: Dict) -> List[BaseAgent]:
        """Get agents eligible for Phase 1 execution.

        Eligibility is the intersection of:
        1. allowed_agent_ids (if provided) - host filter
        2. Trigger type match - engine routing
        3. Cooldown status - timing gate (handled by agent.process())
        4. Trigger conditions - precondition check
        """
        eligible = []

        for agent in self.agents:
            eligible_flag, reason = self._is_eligible(
                agent, context, allowed_agent_ids, trigger_type, meta
            )

            if eligible_flag:
                eligible.append(agent)
            else:
                for cb in self.callbacks:
                    try:
                        await cb.on_agent_skipped(agent.config.name, reason)
                    except Exception as e:
                        logger.error(f"Callback error on_agent_skipped: {e}")

        return eligible
    
    def _is_eligible(self, agent: BaseAgent, context: AgentContext,
                     allowed_agent_ids: Optional[List[str]],
                     trigger_type: TriggerType,
                     meta: Dict) -> Tuple[bool, str]:
        """Check if an agent is eligible to run.
        
        Returns:
            Tuple of (is_eligible, skip_reason)
        """
        # 1. Check allow-list (hard filter)
        if allowed_agent_ids is not None:
            if agent.config.id not in allowed_agent_ids:
                return (False, "not_in_allow_list")
        
        # 2. FORCE bypasses trigger_type match + conditions (engine is source of truth)
        if trigger_type == TriggerType.FORCE:
            return (True, "")

        # 3. Check trigger type match
        if trigger_type not in agent.config.trigger_types:
            return (False, "trigger_type_mismatch")

        # 4. Check trigger conditions (if defined)
        conditions = getattr(agent.config, 'trigger_conditions', None)
        if conditions:
            if not self.condition_evaluator.evaluate(
                conditions, context.blackboard, meta, agent.config.id
            ):
                return (False, "conditions_not_met")

        return (True, "")
    
    def _is_eligible_for_phase2(self, agent: BaseAgent, context: AgentContext,
                                 allowed_agent_ids: Optional[List[str]],
                                 meta: Dict) -> bool:
        """Check if an event subscriber is eligible for Phase 2."""
        # Check allow-list
        if allowed_agent_ids is not None:
            if agent.config.id not in allowed_agent_ids:
                return False
        
        # Check trigger conditions
        conditions = getattr(agent.config, 'trigger_conditions', None)
        if conditions:
            if not self.condition_evaluator.evaluate(
                conditions, context.blackboard, meta, agent.config.id
            ):
                return False
        
        return True
    
    # =========================================================================
    # V1 Compatibility Layer
    # =========================================================================
    
    def _sync_state_to_legacy(self, context: AgentContext) -> None:
        """Sync Blackboard variables INTO shared_state for v1.0 agents.
        
        Called BEFORE agents run so v1 agents can read from context.shared_state.

        E-2: engine-reserved ``sys.*`` variables are excluded from the legacy
        shared_state. They are an engine-internal namespace; copying them into the
        v1 surface let a v1 agent echo them back via state_updates, tripping the
        NP13 ``sys.*`` write-guard warning on a value the engine itself produced.

        MR-1: per-agent memory is also synced into ``shared_state["memory_<id>"]``,
        the keys DynamicAgent reads its persistent memory from. Memory is *stored* on
        the blackboard (``blackboard.memory[agent_id]`` via ``update_memory``), but the
        read-path only looked at ``shared_state`` — so without this sync, cross-turn
        memory survived only via an agent's in-process ``private_state`` and was
        silently lost whenever the host re-instantiated agents per turn. The blackboard
        is the source of truth; values are deep-copied (INV-8).
        """
        if context.blackboard:
            context.shared_state.update({
                key: value
                for key, value in context.blackboard.variables.items()
                if not key.startswith("sys.")
            })
            for agent_id in list(context.blackboard.memory.keys()):
                context.shared_state[f"memory_{agent_id}"] = \
                    context.blackboard.get_memory(agent_id)
    
