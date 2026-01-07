from ..core.agent import BaseAgent, AgentConfig
from ..core.models import AgentContext, AgentResponse, InsightType
import random

class MockSalesCoach(BaseAgent):
    def __init__(self):
        super().__init__(AgentConfig(name="Sales Coach", cooldown=5))

    async def evaluate(self, context: AgentContext) -> AgentResponse:
        # This is a dummy implementation that doesn't use an LLM yet.
        # It just looks for keywords.
        
        text_buffer = " ".join([s.text.lower() for s in context.recent_segments[-3:]])
        
        response = AgentResponse()
        
        if "price" in text_buffer or "cost" in text_buffer or "expensive" in text_buffer:
            insight = self.create_insight(
                content="Price objection detected. Focus on value, not cost.",
                type=InsightType.WARNING
            )
            response.insights.append(insight)
            response.state_updates = {"topic": "pricing"}
            
        elif "feature" in text_buffer:
             insight = self.create_insight(
                content="Mention the new AI capabilities.",
                type=InsightType.SUGGESTION
            )
             response.insights.append(insight)

        return response

