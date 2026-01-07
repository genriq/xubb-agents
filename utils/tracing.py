import logging
import json
import time
from typing import Dict, Any, Optional
from ..core.callbacks import AgentCallbackHandler
from ..core.models import AgentContext, AgentResponse

logger = logging.getLogger("AgentTracer")

class StructuredLogTracer(AgentCallbackHandler):
    """
    A production-ready tracer that logs detailed JSON execution traces.
    Use this to debug agent behavior, latency, and outputs.
    """
    def __init__(self):
        self.current_trace: Dict[str, Any] = {}
        
    async def on_turn_start(self, context: AgentContext) -> None:
        self.current_trace = {
            "session_id": context.session_id,
            "trigger": context.trigger_type,
            "trigger_metadata": context.trigger_metadata,
            "input_preview": context.recent_segments[-1].text if context.recent_segments else "",
            "speaker": context.recent_segments[-1].speaker if context.recent_segments else "UNKNOWN",
            "timestamp_start": time.time(),
            "user_context": context.user_context,
            "language_directive": context.language_directive,
            "rag_docs": context.rag_docs,
            "initial_shared_state": context.shared_state,
            "transcript_history": [s.model_dump() for s in context.recent_segments],
            "steps": []
        }

    async def on_agent_start(self, agent_name: str, context: AgentContext) -> None:
        # We don't log start events to keep the log volume down, 
        # we only log the result in on_agent_finish
        pass

    async def on_agent_finish(self, agent_name: str, response: Optional[AgentResponse], duration: float) -> None:
        step_info = {
            "agent": agent_name,
            "latency_ms": round(duration * 1000, 2),
            "status": "success" if response else "no_response",
            "insights": []
        }
        
        if response:
            step_info["insights"] = [
                {
                    "type": i.type,
                    "content": i.content,
                    "confidence": i.confidence,
                    "metadata": i.metadata
                } 
                for i in response.insights
            ]
            if response.state_updates:
                step_info["state_updates"] = response.state_updates
            
            # Capture sidecar data
            if response.data:
                step_info["data"] = response.data

            # Capture debug info (prompts) if available
            if response.debug_info:
                step_info["debug_info"] = response.debug_info
                
        self.current_trace["steps"].append(step_info)

    async def on_agent_error(self, agent_name: str, error: Exception) -> None:
        self.current_trace["steps"].append({
            "agent": agent_name,
            "status": "error",
            "error": str(error)
        })

    async def on_turn_end(self, response: AgentResponse, duration: float) -> None:
        self.current_trace["total_latency_ms"] = round(duration * 1000, 2)
        self.current_trace["final_insight_count"] = len(response.insights)
        self.current_trace["final_state_updates"] = response.state_updates
        
        # The Golden Log Line:
        # "TURN_TRACE: { ... json ... }"
        log_line = f"TURN_TRACE: {json.dumps(self.current_trace)}"
        
        # Log via logger (handled by core/logging_config.py now)
        logger.info(log_line)
        
        # Redundant safety print to ensure it hits stdout even if logging is misconfigured
        # This is temporary debug safety, but acceptable given the user's issue.
        # print(log_line, flush=True)
