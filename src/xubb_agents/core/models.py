from pydantic import BaseModel, ConfigDict, Field, PrivateAttr
from typing import List, Optional, Dict, Any, Literal, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    # Imported for typing only — models.py must not import blackboard at runtime
    # (blackboard.py imports Event/Fact from here, so a runtime import would be
    # circular). AgentContext.model_rebuild() is called from blackboard.py once the
    # real class exists, which resolves this forward reference for Pydantic.
    from .blackboard import Blackboard


class InsightType(str, Enum):
    """The primary communicative PURPOSE of a human-facing message (XUBB-ITC-1 §3).

    A type names what a message is — never a UI surface, colour, voice, length,
    urgency, certainty, or permission to act. The canonical members and wire
    values are preserved; ``INFORMATION`` is an intentional ALIAS of ``FACT``
    (same member, wire value stays ``"fact"``), so this enum must never carry
    ``@unique``. Iteration yields ten unique members (incl. ERROR); ``__members__``
    holds eleven names. Type-offering code uses ``HUMAN_INSIGHT_TYPES``, never
    unrestricted iteration. ``ERROR`` is a framework-manufactured diagnostic only.
    """
    SUGGESTION = "suggestion"      # a recommended action, approach, or course of action
    WARNING = "warning"            # a material risk, adverse consequence, or constraint
    OPPORTUNITY = "opportunity"    # a favourable opening or potential benefit
    FACT = "fact"                  # canonical name retained; see INFORMATION
    PRAISE = "praise"              # recognition of specific effective behaviour
    ERROR = "error"                # legacy framework diagnostics only — never model-authorable

    INFORMATION = FACT             # preferred public name; same member, wire value "fact"
    OBSERVATION = "observation"    # a grounded interpretation, pattern, or synthesis
    REPLY = "reply"                # optional wording for the principal to say to a counterpart
    CORRECTION = "correction"      # explicit repair/withdrawal of earlier assistant assistance
    QUESTION = "question"          # a request from the assistant to the principal for input


# The nine human-facing purposes, in the contract's canonical order. This — not
# enum iteration — is the source for allowed-type sets and provider enums.
HUMAN_INSIGHT_TYPES = (
    InsightType.INFORMATION,
    InsightType.OBSERVATION,
    InsightType.SUGGESTION,
    InsightType.WARNING,
    InsightType.OPPORTUNITY,
    InsightType.PRAISE,
    InsightType.REPLY,
    InsightType.CORRECTION,
    InsightType.QUESTION,
)

# Display labels come from this explicit map, never from ``.name`` (which stays
# "FACT" for the alias). Hosts may override per locale/profile (§12.1 allows
# "Recommendation" for SUGGESTION without changing the wire value).
INSIGHT_TYPE_LABELS = {
    InsightType.INFORMATION: "Information",
    InsightType.OBSERVATION: "Observation",
    InsightType.SUGGESTION: "Suggestion",
    InsightType.WARNING: "Warning",
    InsightType.OPPORTUNITY: "Opportunity",
    InsightType.PRAISE: "Praise",
    InsightType.REPLY: "Reply",
    InsightType.CORRECTION: "Correction",
    InsightType.QUESTION: "Question",
    InsightType.ERROR: "Error",
}


class TriggerType(str, Enum):
    """The type of event that triggered this agent run."""
    TURN_BASED = "turn_based"  # Normal: after a turn completes
    KEYWORD = "keyword"  # Immediate: keyword detected
    SILENCE = "silence"  # Dead air: long silence detected
    INTERVAL = "interval"  # Time-based: periodic check
    EVENT = "event"  # v2: Triggered by Blackboard event
    FORCE = "force"  # User-triggered force-talk, bypasses cooldown/conditions


# ============================================================================
# V2 Models
# ============================================================================

class Event(BaseModel):
    """A structured event emitted by an agent (v2).
    
    Events are broadcast signals used for agent coordination.
    They are NOT deduplicated by default - multiple events with the
    same name may coexist within a turn.
    """
    name: str = Field(..., description="Event name: 'question_detected', 'objection_raised'")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Event data")
    source_agent: str = Field(..., description="Which agent emitted it")
    timestamp: float = Field(..., description="Seconds since session start")
    id: Optional[str] = Field(default=None, description="Optional unique ID for tracing/deduplication")


class Fact(BaseModel):
    """An extracted piece of knowledge (v2).
    
    Facts are deduplicated by (type, key). If key is None, deduplication
    is by type only. When duplicates exist: higher priority wins; if equal
    priority, higher confidence wins; if still equal, later registration wins.
    """
    type: str = Field(..., description="Category: 'budget', 'timeline', 'stakeholder'")
    key: Optional[str] = Field(default=None, description="Instance key: 'budget.primary', 'stakeholder.cfo'")
    value: Any = Field(..., description="The extracted value")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence")
    priority: int = Field(
        default=0,
        description=(
            "Engine-populated emitting-agent priority, used for conflict resolution "
            "(higher wins; see INV-9). Agents SHOULD NOT set this — the engine stamps it "
            "at merge time. Hosts calling Blackboard.add_fact() directly own it."
        ),
    )
    source_agent: str = Field(..., description="Which agent extracted it")
    timestamp: float = Field(..., description="Seconds since session start")

class TranscriptSegment(BaseModel):
    """A single piece of speech from the conversation."""
    speaker: str = Field(..., description="Who spoke? 'USER', 'SPEAKER', etc.")
    text: str = Field(..., description="The text content")
    timestamp: float = Field(..., description="When it happened (seconds)")
    is_final: bool = True

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


# ============================================================================
# XUBB-ITC-1 (G1) — per-agent insight configuration and host capabilities
# ============================================================================

_INTERACTIVE_FLAGS = (("reply", "allow_reply"), ("question", "allow_question"),
                      ("correction", "allow_correction"))


class ContentProfile(BaseModel):
    """One generation profile of the long-form content contract (§14.6)."""
    model_config = ConfigDict(extra="forbid")
    max_content_chars: int = Field(..., gt=0)
    max_output_tokens: int = Field(..., gt=0)
    llm_timeout_seconds: float = Field(..., gt=0)


class AgentContentConfig(BaseModel):
    """``insight_config.content`` — the agent's side of ``long_form_v1`` (§14.6).
    Illustrative limits are the operator's choice, never framework defaults."""
    model_config = ConfigDict(extra="forbid")
    contract: Literal["long_form_v1"] = "long_form_v1"
    default_depth: Literal["brief", "standard", "detailed"] = "brief"
    formats: List[Literal["plain_text", "markdown"]] = Field(default_factory=lambda: ["plain_text"])
    max_preview_chars: int = Field(..., gt=0)
    profiles: Dict[Literal["brief", "standard", "detailed"], ContentProfile]

    def model_post_init(self, __context: Any) -> None:
        if not self.profiles:
            raise ValueError("insight_config.content.profiles must name at least one depth")
        if self.default_depth not in self.profiles:
            raise ValueError("insight_config.content.default_depth must be one of the configured profiles")
        if not self.formats:
            raise ValueError("insight_config.content.formats must not be empty")


class InsightContentRequest(BaseModel):
    """Host-selected depth for one agent in one run (§14.6); overrides the
    agent's default. Not a permission and not a minimum length."""
    model_config = ConfigDict(extra="forbid")
    depth: Literal["brief", "standard", "detailed"]
    request_id: Optional[str] = None


class ContentExecutionContext(BaseModel):
    """Trusted host/runtime declaration of HOW this run executes (§14.6.1).
    Validated by the adapter; never model metadata. Booleans asserting isolation
    do not replace actual concurrency tests (C2)."""
    model_config = ConfigDict(extra="forbid")
    session_mode: Literal["active", "paused", "post_session"]
    execution_path: Literal["live_turn", "isolated_content", "offline_content"]
    request_id: Optional[str] = None
    source_snapshot_id: Optional[str] = None
    holds_live_turn_lock: Optional[bool] = None
    writes_live_blackboard: Optional[bool] = None
    pause_declared: Optional[bool] = None
    task_isolation_verified: Optional[bool] = None


class InsightConfig(BaseModel):
    """Per-agent ``insight_config`` (XUBB-ITC-1 §7.1).

    ``allowed_types`` are wire values; the default is the six ordinary purposes.
    ``allowed_types=[]`` means STATE-ONLY, never "all". The interactive
    permission flags never implicitly expand ``allowed_types``; a flag and the
    corresponding membership must agree, and the engine rejects a contradictory
    static configuration at registration (see ``contradictions()``).
    Unknown keys are rejected (extra="forbid") so a typo cannot silently widen
    or narrow the vocabulary.
    """
    model_config = ConfigDict(extra="forbid")

    allowed_types: List[str] = Field(
        default_factory=lambda: ["fact", "observation", "suggestion", "warning", "opportunity", "praise"],
        description="Wire values the agent may emit; [] = state-only",
    )
    allow_reply: bool = False
    allow_question: bool = False
    allow_correction: bool = False
    analysis_profile: Literal["general", "consulting"] = "general"
    default_urgency: Optional[Literal["now", "soon", "whenever"]] = None
    # §14.6: opting into long_form_v1 (requires host + schema support; typed only)
    content: Optional[AgentContentConfig] = None

    def model_post_init(self, __context: Any) -> None:
        human = {t.value for t in HUMAN_INSIGHT_TYPES}
        seen = set()
        for value in self.allowed_types:
            if not isinstance(value, str) or value not in human:
                raise ValueError(
                    f"insight_config.allowed_types: {value!r} is not a human-facing wire value "
                    f"(allowed: {sorted(human)})"
                )
            if value in seen:
                raise ValueError(f"insight_config.allowed_types: duplicate value {value!r}")
            seen.add(value)

    def contradictions(self) -> List[str]:
        """Static contradictions that must fail at load time (§7.2)."""
        found = []
        for wire, flag in _INTERACTIVE_FLAGS:
            listed = wire in self.allowed_types
            allowed = getattr(self, flag)
            if listed and not allowed:
                found.append(f"'{wire}' is in allowed_types but {flag} is false")
            elif allowed and not listed:
                found.append(f"{flag} is true but '{wire}' is not in allowed_types "
                             f"(flags never implicitly expand allowed_types)")
        return found


class HostInsightCapabilities(BaseModel):
    """What the HOST declares it can present or handle (XUBB-ITC-1 §6.5).

    Safe defaults: the five existing non-error wire values and every interactive
    capability off. A host that has not declared a capability does not have it;
    in particular OBSERVATION support must be declared explicitly. These are
    host inputs, never model output.
    """
    model_config = ConfigDict(extra="forbid")

    supported_types: List[str] = Field(
        default_factory=lambda: ["suggestion", "warning", "opportunity", "fact", "praise"])
    reply_drafts: bool = False
    text_questions: bool = False
    # §11.3: validated answers are exposed only to the originating agent unless
    # the host explicitly authorises sharing them with every agent in the run.
    answers_shared: bool = False
    corrections: bool = False
    correction_agent_policy: Literal["own_only", "allowlisted"] = "own_only"
    correction_agent_ids: List[str] = Field(default_factory=list)
    expanded_reading: bool = False
    content_contracts: List[str] = Field(default_factory=list)
    content_formats: List[str] = Field(default_factory=lambda: ["plain_text"])
    max_content_chars: Optional[int] = None
    max_preview_chars: Optional[int] = None

    def model_post_init(self, __context: Any) -> None:
        human = {t.value for t in HUMAN_INSIGHT_TYPES}
        for value in self.supported_types:
            if value not in human:
                raise ValueError(f"insight_capabilities.supported_types: {value!r} is not a human-facing wire value")
        if self.content_contracts:
            for name, limit in (("max_content_chars", self.max_content_chars),
                                ("max_preview_chars", self.max_preview_chars)):
                if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
                    raise ValueError(f"insight_capabilities.{name} must be a positive int when content contracts are enabled")


# ---- XUBB-ITC-1 §6.4 trusted reference context (G2) ----

class EvidenceCatalogEntry(BaseModel):
    """One resolvable reference: framework-built snapshot entries (segments,
    documents actually exposed to the agent) or host-supplied entries (documents,
    facts, retained revisions). Identity is trusted because the framework or the
    host supplied it; the excerpt stays untrusted source text."""
    model_config = ConfigDict(extra="forbid")
    kind: Literal["segment", "document", "fact", "insight"]
    ref_id: str = Field(..., min_length=1)
    revision: Optional[str] = None
    session_id: Optional[str] = Field(default=None, description="Owning session; None = current")
    excerpt: Optional[str] = Field(default=None, max_length=4000, description="Bounded source excerpt (untrusted)")


class PriorInsightRecord(BaseModel):
    """A previously EMITTED human-facing insight the host retained (§6.4). Used to
    resolve ``kind: insight`` references now and correction targets at G3."""
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., min_length=1)
    session_id: str
    principal_id: Optional[str] = None
    agent_id: str
    type: str
    content: str
    turn: int
    status: Literal["active", "superseded", "withdrawn"] = "active"


class InsightReferenceContext(BaseModel):
    """Host-supplied, read-only reference records (§6.4/§6.5). Empty by default;
    ordinary observations need none of it — the framework builds the segment
    catalog itself. Frozen per run and propagated through both phases."""
    model_config = ConfigDict(extra="forbid")
    evidence: List[EvidenceCatalogEntry] = Field(default_factory=list)
    prior_insights: List[PriorInsightRecord] = Field(default_factory=list)


class InsightAnswer(BaseModel):
    """A host-owned input event answering (or dismissing) an emitted QUESTION
    (§11.2). The engine-assigned question insight id is the correlation key; the
    host owns durable idempotency (each logical answer supplied once). Answer
    text is untrusted data — it never changes permissions or identity, and a
    dismissal is never consent."""
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(..., min_length=1)
    question_insight_id: str = Field(..., min_length=1)
    principal_id: str = Field(..., min_length=1)
    status: Literal["answered", "dismissed"]
    text: Optional[str] = None


class EvidenceSnapshot(BaseModel):
    """The immutable invocation view an agent's references point into. Returned
    on the per-agent response so a host that wants durable cross-turn references
    can RETAIN it (§6.4: snapshot refs are not durable identities by themselves)."""
    model_config = ConfigDict(extra="forbid")
    snapshot_id: str
    agent_id: str
    entries: List[EvidenceCatalogEntry] = Field(default_factory=list)


class AgentContext(BaseModel):
    """The full context required for an Agent to think."""
    session_id: str
    # The sliding window of conversation
    recent_segments: List[TranscriptSegment]
    # Shared blackboard state (v1 compatibility)
    shared_state: Dict[str, Any] = Field(default_factory=dict)
    # Optional: Retrieved docs from RAG (list of text chunks)
    rag_docs: List[str] = Field(default_factory=list)
    # What triggered this agent run (set by engine, not host)
    trigger_type: TriggerType = TriggerType.TURN_BASED
    # Optional metadata (e.g., keyword that matched, silence duration)
    trigger_metadata: Dict[str, Any] = Field(default_factory=dict)
    # Optional: Language Directive (for translation/enforcement)
    language_directive: Optional[str] = None
    # Optional: User Profile / Context (Identity, Goal, Mic mapping)
    user_context: Optional[str] = None

    # ---- V2 Fields ----
    # Structured Blackboard (v2) - typed containers for state
    blackboard: Optional["Blackboard"] = Field(default=None, description="Blackboard instance (v2)")
    # Execution metadata (read-only, set by engine)
    turn_count: int = Field(default=0, description="Current turn number")
    phase: int = Field(default=1, description="Execution phase (1=normal, 2=event-triggered)")

    # ---- Role Override Fields ----
    # Per-agent config overrides from Roles. Keys = agent.config.id (engine agent ID, NOT role ID).
    agent_config_overrides: Dict[str, AgentConfigOverride] = Field(
        default_factory=dict, description="Per-agent config overrides from Role modifiers"
    )

    # ---- XUBB-ITC-1 (G1) trusted host inputs — never model output ----
    # Stable identity of the assisted human. Host-declared; the framework never
    # infers it from transcript speakers. Absent ⇒ no principal ⇒ REPLY/QUESTION
    # unavailable for the run.
    principal_id: Optional[str] = Field(default=None, description="Host-declared principal identity")
    # Host capability declaration (safe defaults). Frozen per run and propagated
    # through every phase-context copy (§6.4, ITC-14).
    insight_capabilities: HostInsightCapabilities = Field(default_factory=HostInsightCapabilities)
    # Host-supplied reference records (§6.4). The framework adds its own per-agent
    # snapshot catalog on top at run time; hosts need not populate this for
    # ordinary observations.
    insight_reference_context: InsightReferenceContext = Field(default_factory=InsightReferenceContext)
    # Host-supplied answer/dismissal events for emitted questions (§11.2). The
    # engine validates them against the retained question records at turn start;
    # agents only ever see the VALIDATED subset (phase copies), and by default
    # only the originating agent sees its own answers.
    insight_answers: List[InsightAnswer] = Field(default_factory=list)
    # §14.6 long-form: host-selected depth per agent, and the trusted execution
    # declaration for this run (required whenever an agent has a content block).
    insight_content_requests: Dict[str, InsightContentRequest] = Field(default_factory=dict)
    content_execution_context: Optional[ContentExecutionContext] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

# ---- XUBB-ITC-1 §6.3 typed payloads (normative shapes; unknown keys rejected) ----

class EvidenceRef(BaseModel):
    """A reference to evidence actually exposed in the invocation (§6.3/§6.4)."""
    model_config = ConfigDict(extra="forbid")
    kind: Literal["segment", "document", "fact", "insight"]
    ref_id: str = Field(..., min_length=1)
    revision: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        if not self.ref_id.strip():
            raise ValueError("evidence_refs.ref_id must be non-blank")
        if self.revision is not None and not self.revision.strip():
            raise ValueError("evidence_refs.revision must be non-blank or null")


class CorrectionPayload(BaseModel):
    """Required only for CORRECTION (§10)."""
    model_config = ConfigDict(extra="forbid")
    target_insight_id: str = Field(..., min_length=1)
    operation: Literal["replace", "withdraw"]
    reason: str = Field(..., min_length=1)


class QuestionPayload(BaseModel):
    """Required only for QUESTION (§11)."""
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(..., min_length=1)
    response_format: Literal["text"] = "text"


Urgency = Literal["now", "soon", "whenever"]

# Keys of AgentInsight that only the ENGINE may set (§6.2 "engine-owned fields").
# A candidate carrying any of these — at its root or inside metadata — is rejected.
ENGINE_OWNED_INSIGHT_FIELDS = (
    "id", "turn", "contract_version", "confidence_provided", "content_contract",
    "response_depth", "content_request_id", "source_snapshot_id", "acceptance_status",
    "origin", "agent_id", "agent_name",
)

# The public wire shape before the insight contract (v2.6). ``model_dump_legacy``
# projects onto it so old strict consumers never see new keys (§14.10).
_LEGACY_INSIGHT_KEYS = ("agent_id", "agent_name", "type", "content", "confidence",
                        "expiry", "action_label", "metadata")


class AgentInsight(BaseModel):
    """A single piece of advice/feedback."""
    agent_id: str
    agent_name: str
    type: InsightType
    content: str = Field(..., min_length=2, description="The advice text")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    expiry: int = Field(default=15, description="Seconds to display")
    action_label: Optional[str] = None # Optional button text

    # Generic extension point for UI-specific rendering options (zone, color, voice style, etc.)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # ---- XUBB-ITC-1 typed contract fields (G1). Engine-owned ones are stamped at
    # acceptance and are None on legacy emissions; model-authored ones are
    # validated candidates. None/empty means "not on the typed path". ----
    id: Optional[str] = Field(default=None, description="Engine-minted, session-unique (typed_v1)")
    turn: Optional[int] = Field(default=None, description="Engine copy of context.turn_count (typed_v1)")
    contract_version: Optional[str] = Field(default=None, description='"typed_v1" on typed emissions')
    urgency: Optional[Urgency] = Field(default=None, description="Resolved at acceptance (typed_v1)")
    confidence_provided: Optional[bool] = Field(
        default=None,
        description="Runtime-derived: True = model estimate; False = numeric placeholder (not certainty); None = unknown provenance (legacy)",
    )
    observation_kind: Optional[Literal["hypothesis", "implication"]] = None
    evidence_refs: List[EvidenceRef] = Field(default_factory=list)
    rationale: Optional[str] = None
    validation_step: Optional[str] = None
    assumptions: List[str] = Field(default_factory=list)
    correction: Optional[CorrectionPayload] = None
    question: Optional[QuestionPayload] = None
    # ---- long_form_v1 (C1). Model-authored: preview / content_format (only when
    # negotiated). Engine-stamped: the rest. All None outside the extension and
    # omitted from the legacy projection (§14.10). ----
    preview: Optional[str] = Field(default=None, description="Optional plain-text entry point; never replaces content")
    content_format: Optional[Literal["plain_text", "markdown"]] = None
    content_contract: Optional[str] = Field(default=None, description='"long_form_v1" when negotiated (engine-stamped)')
    response_depth: Optional[Literal["brief", "standard", "detailed"]] = Field(default=None, description="Effective depth (engine-stamped)")
    content_request_id: Optional[str] = None
    source_snapshot_id: Optional[str] = None

    # XUBB-ITC-1 §14.3 (G0): runtime-established provenance. Only BaseAgent.process
    # sets "framework" on the ERROR insight it manufactures; a model (or a custom
    # agent) cannot forge it through metadata. Private attrs never serialize.
    _origin: str = PrivateAttr(default="agent")
    # D-CR stable merge order (phase, registered-agent index, candidate ordinal),
    # stamped by the engine at merge; never completion order.
    _merge_order: Optional[tuple] = PrivateAttr(default=None)

    @property
    def merge_order(self) -> Optional[tuple]:
        return self._merge_order

    def model_dump_legacy(self) -> Dict[str, Any]:
        """The pre-contract (v2.6) wire shape — no typed keys, no null additions.
        Use for consumers that reject unknown keys (§14.10)."""
        return self.model_dump(include=set(_LEGACY_INSIGHT_KEYS))


# ============================================================================
# XUBB-ITC-1 (G0) — acceptance status and sanitized diagnostics
# ============================================================================

# D-LR (FINAL_DECISIONS.md): the engine-derived disposition of one agent response.
#   accepted        — a permitted insight was emitted; authorized channels committed
#   accepted_silent — valid false gate / no candidate; authorized channels committed
#   partial         — all insights rejected (recoverable insight error); independently
#                     validated channels committed; action-bearing sidecars withheld
#   rejected        — nothing from the response committed
AcceptanceStatus = Literal["accepted", "accepted_silent", "partial", "rejected"]


class InsightDiagnostic(BaseModel):
    """A sanitized, serializable validation issue (XUBB-ITC-1 §8.5 / §14).

    Carries an execution id, the agent, an error code and a field path. It MAY
    carry a bounded raw classification string; it never carries transcripts,
    prompts, raw exception bodies or hidden reasoning. The engine is the single
    emitter of ``on_insight_validation_error`` for these.
    """
    model_config = ConfigDict(extra="forbid")

    execution_id: str
    agent_id: str
    code: str
    field_path: str = ""
    classification: Optional[str] = Field(
        default=None, max_length=64,
        description="Bounded raw classification string (e.g. the unknown type label)",
    )
    retained_channels: List[str] = Field(
        default_factory=list, description="Domain channels committed on partial acceptance"
    )
    withheld_channels: List[str] = Field(
        default_factory=list, description="Channels withheld on partial acceptance (e.g. data sidecars)"
    )


class AgentResponse(BaseModel):
    """The result of a processing cycle."""
    # Agent that produced this response (set by framework, used for identity resolution)
    source_agent_id: Optional[str] = Field(default=None, description="Agent that produced this response")
    insights: List[AgentInsight] = Field(default_factory=list)

    # ---- XUBB-ITC-1 (G0) acceptance / diagnostics ----
    # Engine-derived; a model cannot author these (they are not schema-mapped).
    execution_id: Optional[str] = Field(default=None, description="Opaque id of the producing execution")
    acceptance_status: AcceptanceStatus = Field(
        default="accepted",
        description="D-LR disposition of this response (per-agent responses); engine-derived",
    )
    diagnostics: List[InsightDiagnostic] = Field(
        default_factory=list, description="Sanitized validation diagnostics (per-agent and aggregated)"
    )
    acceptance_by_agent: Dict[str, str] = Field(
        default_factory=dict,
        description="Aggregated responses only: agent_id → acceptance_status",
    )
    # ---- XUBB-ITC-1 (G2) evidence snapshot retention aid ----
    evidence_snapshot: Optional[EvidenceSnapshot] = Field(
        default=None, description="typed_v1: the immutable invocation view this agent's references point into")
    evidence_snapshots_by_agent: Dict[str, EvidenceSnapshot] = Field(
        default_factory=dict, description="Aggregated responses only: agent_id → evidence snapshot")
    # Updates to the shared memory (v1 compatibility)
    state_updates: Dict[str, Any] = Field(default_factory=dict)
    
    # Generic Data Sidecar (For arbitrary payloads like ui_actions)
    data: Dict[str, Any] = Field(default_factory=dict)
    
    # Debug information (e.g. raw prompt messages) - Not for production use, purely for tracing
    debug_info: Dict[str, Any] = Field(default_factory=dict, exclude=True)
    
    # ---- V2 Fields ----
    # Structured events for agent coordination
    events: List[Event] = Field(default_factory=list, description="Events emitted by this agent")
    # Variable updates (replaces state_updates in v2)
    variable_updates: Dict[str, Any] = Field(default_factory=dict, description="Blackboard variable updates")
    # Queue push operations
    queue_pushes: Dict[str, List[Any]] = Field(default_factory=dict, description="Items to push to queues")
    # Extracted facts
    facts: List[Fact] = Field(default_factory=list, description="Facts extracted by this agent")
    # Agent-private memory updates
    memory_updates: Dict[str, Any] = Field(default_factory=dict, description="Updates to agent's private memory")
    # Per-agent keyed memory updates (aggregated final response only)
    memory_updates_by_agent: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="Memory updates keyed by agent_id (populated on aggregated responses from process_turn)")

    # OB-2 (SPEC_LLM_MODERN_MODELS): per-call token usage (plain ints:
    # prompt_tokens / completion_tokens / reasoning_tokens / cached_tokens when
    # reported). First-class — debug_info is exclude=True and never serializes —
    # so hosts can attribute cost per agent. Populated on per-agent responses
    # only; NOT propagated into the aggregated process_turn response (deferred
    # with the cost-ceiling follow-up).
    usage: Optional[Dict[str, int]] = Field(default=None, description="LLM token usage for this agent's call (per-agent responses only)")

