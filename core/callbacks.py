from typing import Any, Dict, List, Optional
from .models import AgentContext, AgentResponse


class AgentCallbackHandler:
    """Base callback handler for AgentEngine lifecycle events.

    Override the methods you care about. All methods are no-op by default
    so subclasses are never required to implement anything.
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

    async def on_phase_start(self, phase: int, agent_names: List[str]) -> None:
        """Called when an execution phase begins."""
        pass

    async def on_phase_end(self, phase: int, event_names: List[str]) -> None:
        """Called when an execution phase completes."""
        pass

    async def on_agent_skipped(self, agent_name: str, reason: str) -> None:
        """Called when an agent is skipped during eligibility checks."""
        pass
