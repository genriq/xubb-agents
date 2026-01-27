import logging
import time
from typing import Optional, Dict, Any, List
from abc import ABC, abstractmethod
from .models import AgentContext, AgentResponse, AgentInsight, InsightType, TriggerType

logger = logging.getLogger(__name__)

# Need to import callbacks to annotate properly, but avoid circular import if possible
# Usually handled by injecting callbacks into Agent or having Agent return metadata
# For 13/10 SoC, the Engine handles the callbacks, but the Agent needs to expose hooks?
# No, the Engine orchestrates the callbacks.
# But we need to know when the agent STARTS running logic inside process().
# We can add a 'callback_handler' to the Agent, but that couples them.
# BETTER: Agent returns a wrapper or we wrap the process call in Engine.
# Actually, the simplest way is to pass the callback handler to process? No, messy signature.
# 
# CORRECTION: The Engine calls `agent.process`. The Engine can fire `on_agent_start` 
# right before calling `agent.process`.
# HOWEVER, `agent.process` does checks (cooldown, trigger). We only want `on_agent_start` 
# if it ACTUALLY runs.
#
# So, we will add an optional `callbacks` argument to `process` method.

class AgentConfig:
    """Configuration for an agent.
    
    Responsibility Split (Engine vs Agent):
    - Engine: Decides trigger eligibility, evaluates conditions
    - Agent: Enforces cooldown, handles errors
    
    V2 additions:
    - trigger_conditions: Preconditions evaluated by engine before running
    - subscribed_events: Events that trigger this agent (for EVENT trigger type)
    """
    
    def __init__(self, name: str, id: str = None, trigger_interval: Optional[int] = None,
                 cooldown: int = 10, model: str = "gpt-4o-mini",
                 trigger_types: List[TriggerType] = None,
                 trigger_keywords: List[str] = None,
                 silence_threshold: Optional[int] = None,
                 priority: int = 0, output_format: str = "default",
                 # V2 additions
                 trigger_conditions: Optional[Dict[str, Any]] = None,
                 subscribed_events: Optional[List[str]] = None):
        self.name = name
        self.id = id or name.lower().replace(" ", "_")
        self.trigger_interval = trigger_interval
        self.cooldown = cooldown
        self.model = model
        # Trigger system
        self.trigger_types = trigger_types or [TriggerType.TURN_BASED]
        self.trigger_keywords = trigger_keywords or []
        self.silence_threshold = silence_threshold
        self.priority = priority
        self.output_format = output_format
        
        # V2: Trigger conditions (preconditions evaluated by engine)
        self.trigger_conditions = trigger_conditions
        
        # V2: Event subscriptions (for EVENT trigger type)
        self.subscribed_events = subscribed_events or []

class BaseAgent(ABC):
    def __init__(self, config: AgentConfig):
        self.config = config
        self.last_run_time = 0.0
        self.private_state: Dict[str, Any] = {}
        self.logger = logging.getLogger(f"Agent.{config.name}")
        # Will be injected by Engine
        self.llm = None 

    async def process(self, context: AgentContext, callbacks: List[Any] = None) -> Optional[AgentResponse]:
        """Main entry point. Handles checks before running logic.
        
        Responsibility Split (v2):
        - Engine: Decides trigger eligibility (trigger type, conditions)
        - Agent: Enforces cooldown, handles errors
        
        Note: The trigger type check is kept for backward compatibility,
        but the engine already filters by trigger type before calling.
        """
        now = time.time()
        
        # 1. Trigger Type Check (kept for backward compatibility; engine already filters)
        if context.trigger_type not in self.config.trigger_types:
            return None
        
        # 2. Cooldown Check (agent's responsibility)
        if (now - self.last_run_time) < self.config.cooldown:
            return None
        
        # 3. Fire Start Callback
        if callbacks:
            for cb in callbacks:
                try:
                    await cb.on_agent_start(self.config.name, context)
                except Exception:
                    pass

        # 4. Execute Logic (Subclass implementation)
        start_time = time.time()
        response = None
        try:
            response = await self.evaluate(context)
            self.last_run_time = now
            return response
        except Exception as e:
            self.logger.error(f"Error in agent evaluation: {e}")
            if callbacks:
                for cb in callbacks:
                    try:
                        await cb.on_agent_error(self.config.name, e)
                    except Exception:
                        pass
            
            # Return an error insight for UI feedback
            return AgentResponse(insights=[
                self.create_insight(
                    content=f"Agent '{self.config.name}' encountered an error: {e}",
                    type=InsightType.ERROR,
                    confidence=1.0
                )
            ])
        finally:
            duration = time.time() - start_time
            if callbacks:
                for cb in callbacks:
                    try:
                        await cb.on_agent_finish(self.config.name, response, duration)
                    except Exception:
                        pass

    @abstractmethod
    async def evaluate(self, context: AgentContext) -> Optional[AgentResponse]:
        """
        The brain of the agent. Must be implemented by subclasses.
        """
        pass

    def create_insight(self, content: str, type: InsightType = InsightType.SUGGESTION, confidence: float = 1.0) -> AgentInsight:
        """Helper to create a valid Insight object"""
        return AgentInsight(
            agent_id=self.config.id,
            agent_name=self.config.name,
            type=type,
            content=content,
            confidence=confidence
        )
