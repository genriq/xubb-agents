from ..core.agent import BaseAgent, AgentConfig
from ..core.models import AgentContext, AgentResponse, InsightType
from .dynamic import DynamicAgent

class SalesAgent(DynamicAgent):
    """
    A specialized Sales Coach agent.
    Inherits from DynamicAgent to leverage the Schema System and Generic Parsing.
    """
    def __init__(self, output_format: str = "default"):
        
        # Define the specialized Sales Persona
        sales_prompt = """
        You are a world-class Sales Coach watching a live conversation.
        
        YOUR GOAL:
        Identify if the CLIENT (not the user) has just raised an Objection or Buying Signal.
        
        INSTRUCTIONS:
        1. Analyze the last few turns.
        2. If everything is normal, return no insight.
        3. If there is a critical moment, return an insight (Suggestion or Warning).
        
        CRITERIA:
        - Warning: Price objections, Competitor mentions, Compliance risks.
        - Suggestion: Buying signals, Next steps, Missing value prop.
        """
        
        # Pre-configure the Dynamic Agent options
        config = {
            "name": "Sales Coach",
            "id": "sales-coach",
            "text": sales_prompt,
            "trigger_config": {
                "mode": "turn_based",
                "cooldown": 15
            },
            "model_config": {
                "model": "gpt-4o-mini",
                "context_turns": 6
            },
            "output_format": output_format 
        }
        
        # Initialize DynamicAgent with this config
        super().__init__(config)

    # We do NOT need to implement evaluate() because DynamicAgent handles it!
    # It will automatically:
    # 1. Load the correct schema (default/v2_raw/custom)
    # 2. Append the correct instructions
    # 3. Parse the result using the mapping
