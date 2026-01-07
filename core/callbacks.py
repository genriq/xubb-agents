from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from .models import AgentContext, AgentResponse, AgentInsight

class AgentCallbackHandler(ABC):
    """
    Base callback handler that can be used to handle callbacks from the AgentEngine.
    Implementations should override the methods they care about.
    """
    
    async def on_turn_start(self, context: AgentContext) -> None:
        """Called when a new turn processing begins."""
        pass
        
    async def on_turn_end(self, response: AgentResponse, duration: float) -> None:
        """Called when a turn processing finishes."""
        pass
        
    async def on_agent_start(self, agent_name: str, context: AgentContext) -> None:
        """Called when an individual agent starts evaluation."""
        pass
        
    async def on_agent_finish(self, agent_name: str, response: Optional[AgentResponse], duration: float) -> None:
        """Called when an individual agent finishes evaluation."""
        pass
        
    async def on_agent_error(self, agent_name: str, error: Exception) -> None:
        """Called when an individual agent errors."""
        pass
        
    async def on_chain_error(self, error: Exception) -> None:
        """Called when the main engine loop errors."""
        pass
