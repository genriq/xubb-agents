from .core.engine import AgentEngine, AgentConfigurationError
from .core.agent import BaseAgent, AgentConfig, DEFAULT_MODEL
from .core.models import (
    AgentContext, AgentConfigOverride, TranscriptSegment, InsightType, AgentResponse, TriggerType,
    # V2 additions
    Event, Fact
)
from .core.blackboard import Blackboard
from .core.conditions import ConditionEvaluator
from .library.dynamic import DynamicAgent

__version__ = "2.6.0"

