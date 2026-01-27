from .core.engine import AgentEngine
from .core.agent import BaseAgent, AgentConfig
from .core.models import (
    AgentContext, TranscriptSegment, InsightType, AgentResponse, TriggerType,
    # V2 additions
    Event, Fact
)
from .core.blackboard import Blackboard
from .core.conditions import ConditionEvaluator
from .library.mock_coach import MockSalesCoach

__version__ = "2.0.0"

