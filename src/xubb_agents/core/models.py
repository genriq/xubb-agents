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
    SUGGESTION = "suggestion"
    WARNING = "warning"
    OPPORTUNITY = "opportunity" # Zone A: Urgent Positive
    FACT = "fact"
    PRAISE = "praise"
    ERROR = "error" # For system alerts

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

    model_config = ConfigDict(arbitrary_types_allowed=True)

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

    # XUBB-ITC-1 §14.3 (G0): runtime-established provenance. Only BaseAgent.process
    # sets "framework" on the ERROR insight it manufactures; a model (or a custom
    # agent) cannot forge it through metadata. Private attrs never serialize.
    _origin: str = PrivateAttr(default="agent")


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

