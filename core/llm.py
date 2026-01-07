import os
from typing import Optional, Dict, Any
import logging

# Try to import openai, but don't crash if not present (graceful degradation or mocking)
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

logger = logging.getLogger("AgentLLM")

class LLMClient:
    def __init__(self, api_key: Optional[str] = None):
        self.client = None
        if not OPENAI_AVAILABLE:
            logger.warning("OpenAI package not found. Agents requiring LLM will fail.")
            return

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning("No OpenAI API Key provided. LLM features disabled.")
            return

        self.client = AsyncOpenAI(api_key=self.api_key)

    async def generate_json(self, model: str, messages: list) -> Optional[Dict[str, Any]]:
        """
        Generates a structured JSON response from the LLM.
        """
        if not self.client:
            logger.error("LLM Client not initialized (missing key or package).")
            return None

        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            import json
            return json.loads(content)
        except Exception as e:
            logger.error(f"LLM Generation failed: {e}")
            return None

