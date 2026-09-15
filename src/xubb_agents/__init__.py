from .core.engine import AgentEngine, AgentConfigurationError
from .core.agent import BaseAgent, AgentConfig, DEFAULT_MODEL
from .core.models import (
    AgentContext, AgentConfigOverride, TranscriptSegment, InsightType, AgentResponse, TriggerType,
    # V2 additions
    Event, Fact,
    # XUBB-ITC-1 (G0/G1)
    HUMAN_INSIGHT_TYPES, INSIGHT_TYPE_LABELS, InsightConfig, HostInsightCapabilities,
    InsightDiagnostic,
    # 3.1.0 output-format consolidation: host-owned widget declarations
    HostWidgetCapabilities, WidgetDeclaration, WidgetActionDeclaration,
)
from .core.blackboard import Blackboard
from .core.conditions import ConditionEvaluator
from .library.dynamic import DynamicAgent

__version__ = "3.1.5"

