from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum

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

class TranscriptSegment(BaseModel):
    """A single piece of speech from the conversation."""
    speaker: str = Field(..., description="Who spoke? 'USER', 'SPEAKER', etc.")
    text: str = Field(..., description="The text content")
    timestamp: float = Field(..., description="When it happened (seconds)")
    is_final: bool = True

class AgentContext(BaseModel):
    """The full context required for an Agent to think."""
    session_id: str
    # The sliding window of conversation
    recent_segments: List[TranscriptSegment]
    # Shared blackboard state
    shared_state: Dict[str, Any] = Field(default_factory=dict)
    # Optional: Retrieved docs from RAG (list of text chunks)
    rag_docs: List[str] = Field(default_factory=list)
    # What triggered this agent run
    trigger_type: TriggerType = TriggerType.TURN_BASED
    # Optional metadata (e.g., keyword that matched, silence duration)
    trigger_metadata: Dict[str, Any] = Field(default_factory=dict)
    # Optional: Language Directive (for translation/enforcement)
    language_directive: Optional[str] = None
    # Optional: User Profile / Context (Identity, Goal, Mic mapping)
    user_context: Optional[str] = None

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

class AgentResponse(BaseModel):
    """The result of a processing cycle."""
    insights: List[AgentInsight] = []
    # Updates to the shared memory
    state_updates: Dict[str, Any] = {}
    
    # Generic Data Sidecar (For arbitrary payloads like ui_actions)
    data: Dict[str, Any] = Field(default_factory=dict)
    
    # Debug information (e.g. raw prompt messages) - Not for production use, purely for tracing
    debug_info: Dict[str, Any] = Field(default_factory=dict, exclude=True) # Exclude from standard serialization if needed, but we want it in traces

