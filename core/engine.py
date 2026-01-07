import asyncio
import logging
import hashlib
import time
from typing import List, Optional, Dict, Any
from .models import AgentContext, AgentResponse, TranscriptSegment, AgentInsight, InsightType, TriggerType
from .agent import BaseAgent
from .llm import LLMClient
from .callbacks import AgentCallbackHandler

logger = logging.getLogger("AgentEngine")

class AgentEngine:
    def __init__(self, api_key: Optional[str] = None, enable_caching: bool = True, cache_ttl: int = 300, callbacks: List[AgentCallbackHandler] = None):
        self.agents: List[BaseAgent] = []
        self.shared_state = {}
        self.llm_client = LLMClient(api_key=api_key)
        self.callbacks = callbacks or []
        # Performance optimization: Response cache
        self.enable_caching = enable_caching
        self.cache_ttl = cache_ttl  # 5 minutes default
        self.response_cache: Dict[str, tuple] = {}  # key -> (response, timestamp)
        
    def register_agent(self, agent: BaseAgent):
        # Inject the LLM client into the agent
        agent.llm = self.llm_client
        logger.info(f"Registered agent: {agent.config.name} (ID: {agent.config.id}, Model: {agent.config.model}, Triggers: {agent.config.trigger_types})")
        self.agents.append(agent)
    
    def update_api_key(self, api_key: Optional[str]):
        """Update API key for LLM client and re-inject into all agents."""
        self.llm_client = LLMClient(api_key=api_key)
        for agent in self.agents:
            agent.llm = self.llm_client
        logger.info("Updated API key for all agents")
    
    def get_agents_by_trigger_type(self, trigger_type: TriggerType) -> List[BaseAgent]:
        """Get all agents that respond to a specific trigger type."""
        return [a for a in self.agents if trigger_type in a.config.trigger_types]
    
    def get_agents_with_keywords(self) -> List[BaseAgent]:
        """Get all agents with keyword triggers."""
        return [a for a in self.agents if a.config.trigger_keywords]
    
    def get_agents_with_silence_threshold(self) -> List[BaseAgent]:
        """Get all agents with silence thresholds."""
        return [a for a in self.agents if a.config.silence_threshold is not None]
    
    def check_keyword_triggers(self, text: str, allowed_agent_ids: Optional[List[str]] = None) -> List[tuple]:
        """
        Check which agents should trigger based on keywords.
        
        Args:
            text: Text to search for keywords
            allowed_agent_ids: Optional list of agent IDs to filter by. None = all agents, [] = no agents.
        
        Returns: List of (agent, matched_keyword) tuples.
        """
        text_lower = text.lower()
        matches = []
        
        # Debug log for keywords
        logger.debug(f"Checking keywords in: '{text}'")
        
        for agent in self.agents:
            # Filter by allowed_agent_ids if provided
            if allowed_agent_ids is not None:
                if agent.config.id not in allowed_agent_ids:
                    continue
            
            if agent.config.trigger_keywords:
                for keyword in agent.config.trigger_keywords:
                    # Simple inclusion check (relaxed)
                    if keyword.lower() in text_lower:
                        logger.info(f"MATCH: Agent '{agent.config.name}' triggered by '{keyword}'")
                        matches.append((agent, keyword))
                        break  # One match per agent
        return matches

    def _get_cache_key(self, agent: BaseAgent, context: AgentContext) -> str:
        """Generate a cache key for agent responses."""
        # Hash: agent_id + recent transcript + system prompt hash
        transcript_text = " ".join([s.text for s in context.recent_segments[-6:]])
        cache_data = f"{agent.config.id}:{transcript_text}"
        return hashlib.md5(cache_data.encode()).hexdigest()
    
    def _get_cached_response(self, cache_key: str) -> Optional[AgentResponse]:
        """Retrieve cached response if valid."""
        if not self.enable_caching:
            return None
        
        if cache_key in self.response_cache:
            response, timestamp = self.response_cache[cache_key]
            age = time.time() - timestamp
            if age < self.cache_ttl:
                logger.debug(f"Cache HIT for agent (age: {age:.1f}s)")
                return response
            else:
                # Expired, remove
                del self.response_cache[cache_key]
        
        return None
    
    def _cache_response(self, cache_key: str, response: AgentResponse):
        """Store response in cache."""
        if self.enable_caching:
            self.response_cache[cache_key] = (response, time.time())
            # Cleanup old entries (keep last 100)
            if len(self.response_cache) > 100:
                # Remove oldest 20
                sorted_items = sorted(self.response_cache.items(), key=lambda x: x[1][1])
                for key, _ in sorted_items[:20]:
                    del self.response_cache[key]

    async def process_turn(self, context: AgentContext, allowed_agent_ids: Optional[List[str]] = None, 
                          trigger_type: TriggerType = TriggerType.TURN_BASED, 
                          trigger_metadata: Dict[str, Any] = None) -> AgentResponse:
        """
        Called when a significant event occurs (e.g. user stopped speaking, keyword detected, silence).
        Runs eligible agents in parallel with batching optimization.
        """
        # Set trigger info in context
        context.trigger_type = trigger_type
        context.trigger_metadata = trigger_metadata or {}
        
        # Inject current shared state into context
        context.shared_state = self.shared_state.copy()
        
        # Fire On Turn Start
        for cb in self.callbacks:
            try:
                await cb.on_turn_start(context)
            except Exception as e:
                logger.error(f"Callback error on_turn_start: {e}")
        
        # Group agents by model for potential batching (future optimization)
        agents_by_model: Dict[str, List[BaseAgent]] = {}
        eligible_agents = []
        
        for agent in self.agents:
            # Filter by allowed_agent_ids if provided
            # None means "run all agents"
            # Empty list [] means "run no agents" (all disabled)
            # Non-empty list means "run only these agents"
            if allowed_agent_ids is not None:
                if agent.config.id not in allowed_agent_ids:
                    continue
            
            # Check if agent responds to this trigger type
            if trigger_type not in agent.config.trigger_types:
                continue
            
            eligible_agents.append(agent)
            model = agent.config.model
            if model not in agents_by_model:
                agents_by_model[model] = []
            agents_by_model[model].append(agent)
        
        if not eligible_agents:
            logger.debug(f"No agents eligible for trigger: {trigger_type}")
            return AgentResponse()
        
        logger.info(f"Processing trigger '{trigger_type}' with {len(eligible_agents)} eligible agents")
        
        # Process agents (with caching)
        all_tasks = []
        agent_to_cache_key = {}
        
        for agent in eligible_agents:
            logger.info(f"Evaluating Agent: {agent.config.name} (ID: {agent.config.id})")
            cache_key = self._get_cache_key(agent, context)
            agent_to_cache_key[agent] = cache_key
            
            cached = self._get_cached_response(cache_key)
            if cached:
                # Return cached response
                async def return_cached(cached_resp):
                    return cached_resp
                all_tasks.append(return_cached(cached))
            else:
                # Pass callbacks to process method
                all_tasks.append(agent.process(context, callbacks=self.callbacks))
        
        # Run all agents in parallel
        start_time = time.time()
        results = await asyncio.gather(*all_tasks, return_exceptions=True)
        turn_duration = time.time() - start_time
        
        final_response = AgentResponse()
        state_updates_by_priority: List[tuple] = []  # (priority, updates, agent)
        
        for idx, res in enumerate(results):
            agent = eligible_agents[idx]
            
            if isinstance(res, Exception):
                logger.error(f"Agent {agent.config.name} failed: {res}")
                err_insight = AgentInsight(
                    agent_id="system",
                    agent_name="System",
                    type=InsightType.ERROR,
                    content=f"Agent '{agent.config.name}' error: {str(res)}",
                    confidence=1.0
                )
                final_response.insights.append(err_insight)
                continue
                
            if res and isinstance(res, AgentResponse):
                # Aggregate insights
                final_response.insights.extend(res.insights)
                
                # Cache the response if it wasn't cached
                cache_key = agent_to_cache_key[agent]
                if cache_key not in self.response_cache:
                    self._cache_response(cache_key, res)
                
                # Collect state updates with priority
                if res.state_updates:
                    priority = agent.config.priority
                    state_updates_by_priority.append((priority, res.state_updates, agent.config.name))
        
        # Apply state updates in priority order (higher priority first)
        # Higher priority agents can override lower priority ones
        state_updates_by_priority.sort(key=lambda x: x[0], reverse=True)
        for priority, updates, agent_name in state_updates_by_priority:
            logger.debug(f"Applying state updates from {agent_name} (priority: {priority})")
            self.shared_state.update(updates)
            final_response.state_updates.update(updates)
        
        # Fire On Turn End
        for cb in self.callbacks:
            try:
                await cb.on_turn_end(final_response, turn_duration)
            except Exception as e:
                logger.error(f"Callback error on_turn_end: {e}")

        return final_response
