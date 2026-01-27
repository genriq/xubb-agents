"""
AgentEngine - Central orchestrator for the Xubb Agents Framework (v2).

Key responsibilities:
- Registry: Maintains list of active agents
- Routing: Determines which agents run based on trigger type
- Condition Evaluation: Checks trigger conditions before running agents
- Blackboard Management: Manages structured state (in-memory for session lifetime)
- Event Dispatch: Collects emitted events, triggers subscribers
- Multi-Phase Execution: Runs normal agents (Phase 1), then event-triggered agents (Phase 2)
- Response Aggregation: Merges insights, applies state updates by priority
- Observability: Emits lifecycle events to callbacks

Note: Response caching was removed in v2.0. Cooldowns and trigger conditions
provide more correct mechanisms for preventing unnecessary LLM calls.
"""

import asyncio
import logging
import time
from typing import List, Optional, Dict, Any, Tuple

from .models import (
    AgentContext, AgentResponse, AgentInsight, InsightType, TriggerType,
    Event, Fact
)
from .agent import BaseAgent
from .llm import LLMClient
from .callbacks import AgentCallbackHandler
from .blackboard import Blackboard
from .conditions import ConditionEvaluator

logger = logging.getLogger("AgentEngine")


class AgentEngine:
    """Central orchestrator for the agent system (v2)."""
    
    def __init__(self, api_key: Optional[str] = None,
                 callbacks: List[AgentCallbackHandler] = None,
                 max_phases: int = 2):
        """Initialize the AgentEngine.
        
        Args:
            api_key: OpenAI API key
            callbacks: List of callback handlers for observability
            max_phases: Maximum execution phases (default 2: normal + event-triggered)
        """
        self.agents: List[BaseAgent] = []
        self.llm_client = LLMClient(api_key=api_key)
        self.callbacks = callbacks or []
        self.condition_evaluator = ConditionEvaluator()
        self.max_phases = max_phases
        
        # Agent registration order for deterministic tie-breaking
        self._agent_index: Dict[str, int] = {}
        
    def register_agent(self, agent: BaseAgent):
        """Register an agent with the engine."""
        # Inject the LLM client into the agent
        agent.llm = self.llm_client
        
        # Track registration order for deterministic merge ordering
        self._agent_index[agent.config.id] = len(self.agents)
        
        logger.info(f"Registered agent: {agent.config.name} (ID: {agent.config.id}, "
                   f"Model: {agent.config.model}, Triggers: {agent.config.trigger_types})")
        self.agents.append(agent)
    
    def update_api_key(self, api_key: Optional[str]):
        """Update API key for LLM client and re-inject into all agents."""
        self.llm_client = LLMClient(api_key=api_key)
        for agent in self.agents:
            agent.llm = self.llm_client
        logger.info("Updated API key for all agents")
    
    # =========================================================================
    # Agent Query Methods
    # =========================================================================
    
    def get_agents_by_trigger_type(self, trigger_type: TriggerType) -> List[BaseAgent]:
        """Get all agents that respond to a specific trigger type."""
        return [a for a in self.agents if trigger_type in a.config.trigger_types]
    
    def get_agents_with_keywords(self) -> List[BaseAgent]:
        """Get all agents with keyword triggers."""
        return [a for a in self.agents if a.config.trigger_keywords]
    
    def get_agents_with_silence_threshold(self) -> List[BaseAgent]:
        """Get all agents with silence thresholds."""
        return [a for a in self.agents if a.config.silence_threshold is not None]
    
    def get_event_subscribers(self, event_names: List[str]) -> List[BaseAgent]:
        """Get agents subscribed to any of the given events (v2)."""
        subscribers = []
        for agent in self.agents:
            subscribed = getattr(agent.config, 'subscribed_events', None) or []
            if any(event_name in subscribed for event_name in event_names):
                subscribers.append(agent)
        return subscribers
    
    def check_keyword_triggers(self, text: str, 
                               allowed_agent_ids: Optional[List[str]] = None) -> List[tuple]:
        """Check which agents should trigger based on keywords.
        
        Note: Keyword detection is host responsibility in v2.0. The engine
        provides this as a helper utility. Host is responsible for invoking
        it and passing allowed_agent_ids.
        
        Args:
            text: Text to search for keywords
            allowed_agent_ids: Optional list of agent IDs to filter by
        
        Returns:
            List of (agent, matched_keyword) tuples
        """
        text_lower = text.lower()
        matches = []
        
        for agent in self.agents:
            if allowed_agent_ids is not None:
                if agent.config.id not in allowed_agent_ids:
                    continue
            
            if agent.config.trigger_keywords:
                for keyword in agent.config.trigger_keywords:
                    if keyword.lower() in text_lower:
                        logger.info(f"MATCH: Agent '{agent.config.name}' triggered by '{keyword}'")
                        matches.append((agent, keyword))
                        break
        return matches
    
    # =========================================================================
    # Main Processing
    # =========================================================================
    
    async def process_turn(self, context: AgentContext,
                          allowed_agent_ids: Optional[List[str]] = None,
                          trigger_type: TriggerType = TriggerType.TURN_BASED,
                          trigger_metadata: Dict[str, Any] = None) -> AgentResponse:
        """Process a turn with multi-phase execution (v2).
        
        Execution Flow:
        1. Set trigger info and sys.* variables
        2. Sync Blackboard → shared_state for v1 compatibility
        3. Phase 1: Run eligible agents against snapshot
        4. Merge updates (ascending priority - higher priority writes last, wins)
        5. If events emitted, Phase 2: Run event subscribers
        6. Clear events, return aggregated response
        
        Args:
            context: The full context for agents
            allowed_agent_ids: Optional hard allow-list (None = all agents)
            trigger_type: What triggered this turn
            trigger_metadata: Additional trigger info (keyword, silence duration, etc.)
        
        Returns:
            Aggregated AgentResponse with all insights and state updates
        """
        start_time = time.time()
        
        # Set trigger info in context
        context.trigger_type = trigger_type
        context.trigger_metadata = trigger_metadata or {}
        
        # Ensure Blackboard exists
        if context.blackboard is None:
            context.blackboard = Blackboard()
        
        # Set sys.* variables (engine-owned)
        context.blackboard.set_var("sys.turn_count", context.turn_count)
        context.blackboard.set_var("sys.session_id", context.session_id)
        context.blackboard.set_var("sys.trigger_type", trigger_type.value)
        
        # Sync Blackboard → shared_state for v1 compatibility
        self._sync_state_to_legacy(context)
        
        # Build execution metadata for condition evaluation
        meta = {
            "turn_count": context.turn_count,
            "trigger_type": trigger_type.value,
            "phase": 1,
            "session_id": context.session_id
        }
        
        # Fire on_turn_start callbacks
        for cb in self.callbacks:
            try:
                await cb.on_turn_start(context)
            except Exception as e:
                logger.error(f"Callback error on_turn_start: {e}")
        
        # Initialize aggregated response
        final_response = AgentResponse()
        all_events: List[Event] = []
        
        # =====================================================================
        # Phase 1: Primary Execution
        # =====================================================================
        context.phase = 1
        meta["phase"] = 1
        
        phase1_agents = self._get_eligible_agents(
            context, allowed_agent_ids, trigger_type, meta
        )
        
        if phase1_agents:
            logger.info(f"Phase 1: Running {len(phase1_agents)} eligible agents")
            
            # Fire on_phase_start
            for cb in self.callbacks:
                try:
                    await cb.on_phase_start(1, [a.config.name for a in phase1_agents])
                except Exception as e:
                    logger.error(f"Callback error on_phase_start: {e}")
            
            # Run phase 1 and merge results
            phase1_responses = await self._run_phase(phase1_agents, context)
            self._merge_responses(phase1_responses, context.blackboard, final_response)
            
            # Collect events emitted in phase 1
            for resp in phase1_responses:
                all_events.extend(resp.events)
            
            # Apply events to blackboard
            for event in all_events:
                context.blackboard.emit_event(event)
            
            # Fire on_phase_end
            event_names = list(set(e.name for e in all_events))
            for cb in self.callbacks:
                try:
                    await cb.on_phase_end(1, event_names)
                except Exception as e:
                    logger.error(f"Callback error on_phase_end: {e}")
        
        # =====================================================================
        # Phase 2: Event-Triggered Execution (if events were emitted)
        # =====================================================================
        if all_events and self.max_phases >= 2:
            context.phase = 2
            meta["phase"] = 2
            
            event_names = list(set(e.name for e in all_events))
            phase2_agents = self.get_event_subscribers(event_names)
            
            # Filter by allowed_agent_ids and conditions
            phase2_agents = [
                a for a in phase2_agents
                if self._is_eligible_for_phase2(a, context, allowed_agent_ids, meta)
            ]
            
            if phase2_agents:
                logger.info(f"Phase 2: Running {len(phase2_agents)} event subscribers "
                           f"for events: {event_names}")
                
                # Fire on_phase_start
                for cb in self.callbacks:
                    try:
                        await cb.on_phase_start(2, [a.config.name for a in phase2_agents])
                    except Exception as e:
                        logger.error(f"Callback error on_phase_start: {e}")
                
                # Run phase 2 and merge results
                phase2_responses = await self._run_phase(phase2_agents, context)
                self._merge_responses(phase2_responses, context.blackboard, final_response)
                
                # Events emitted in Phase 2 are recorded but NOT dispatched
                phase2_events = []
                for resp in phase2_responses:
                    phase2_events.extend(resp.events)
                    all_events.extend(resp.events)  # Include in telemetry
                
                if phase2_events:
                    logger.debug(f"Phase 2 emitted {len(phase2_events)} events "
                                "(recorded but not dispatched)")
                
                # Fire on_phase_end
                for cb in self.callbacks:
                    try:
                        await cb.on_phase_end(2, [e.name for e in phase2_events])
                    except Exception as e:
                        logger.error(f"Callback error on_phase_end: {e}")
        
        # =====================================================================
        # Finalization
        # =====================================================================
        
        # Clear events from blackboard (events are transient)
        context.blackboard.clear_events()
        
        # Include all emitted events in response (for telemetry)
        final_response.events = all_events
        
        # Sync v1 state_updates from v2 variable_updates
        if final_response.variable_updates:
            final_response.state_updates.update(final_response.variable_updates)
        
        # Calculate duration
        turn_duration = time.time() - start_time
        
        # Fire on_turn_end callbacks
        for cb in self.callbacks:
            try:
                await cb.on_turn_end(final_response, turn_duration)
            except Exception as e:
                logger.error(f"Callback error on_turn_end: {e}")
        
        logger.info(f"Turn completed in {turn_duration*1000:.0f}ms with "
                   f"{len(final_response.insights)} insights")
        
        return final_response
    
    # =========================================================================
    # Phase Execution
    # =========================================================================
    
    async def _run_phase(self, agents: List[BaseAgent],
                         context: AgentContext) -> List[AgentResponse]:
        """Run a phase with snapshot isolation.
        
        All agents in the phase evaluate against the same immutable snapshot
        of the Blackboard. State updates are collected and merged only after
        all agents complete.
        """
        # Create snapshot for phase isolation
        snapshot = context.blackboard.snapshot()
        
        # Create a context with the snapshot for agents to read
        phase_context = AgentContext(
            session_id=context.session_id,
            recent_segments=context.recent_segments,
            shared_state=context.shared_state.copy(),
            blackboard=snapshot,
            rag_docs=context.rag_docs,
            trigger_type=context.trigger_type,
            trigger_metadata=context.trigger_metadata,
            language_directive=context.language_directive,
            user_context=context.user_context,
            turn_count=context.turn_count,
            phase=context.phase
        )
        
        # Run all agents in parallel
        tasks = []
        for agent in agents:
            # Fire on_agent_start
            for cb in self.callbacks:
                try:
                    await cb.on_agent_start(agent.config.name, phase_context)
                except Exception as e:
                    logger.error(f"Callback error on_agent_start: {e}")
            
            tasks.append(self._run_agent_safe(agent, phase_context))
        
        results = await asyncio.gather(*tasks)
        
        # Filter out None results (failed agents)
        return [r for r in results if r is not None]
    
    async def _run_agent_safe(self, agent: BaseAgent,
                              context: AgentContext) -> Optional[AgentResponse]:
        """Run an agent with atomic failure handling.
        
        If an agent errors during evaluation, none of its state updates,
        events, facts, or memory changes are applied. The agent is isolated,
        and an ERROR insight may be emitted instead.
        """
        start_time = time.time()
        
        try:
            response = await agent.process(context, callbacks=self.callbacks)
            duration = time.time() - start_time
            
            # Fire on_agent_finish
            for cb in self.callbacks:
                try:
                    await cb.on_agent_finish(agent.config.name, response, duration)
                except Exception as e:
                    logger.error(f"Callback error on_agent_finish: {e}")
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Agent {agent.config.name} failed: {e}")
            
            # Fire on_agent_error
            for cb in self.callbacks:
                try:
                    await cb.on_agent_error(agent.config.name, e)
                except Exception as cb_e:
                    logger.error(f"Callback error on_agent_error: {cb_e}")
            
            # Return None - agent's updates are discarded (atomic failure)
            return None
    
    # =========================================================================
    # Response Merging
    # =========================================================================
    
    def _merge_responses(self, responses: List[AgentResponse],
                         blackboard: Blackboard,
                         final_response: AgentResponse) -> None:
        """Merge agent responses with deterministic ordering.
        
        Updates are applied in ASCENDING priority order (low → high) so that
        higher-priority agents write last and therefore win (last-write-wins).
        
        Within the same priority, agent registration order is used as a
        stable tie-breaker.
        """
        # Collect updates with priority and registration order
        updates: List[Tuple[int, int, str, AgentResponse]] = []
        
        for resp in responses:
            # Find the agent that produced this response
            agent_id = None
            agent_priority = 0
            agent_index = 0
            
            if resp.insights:
                agent_id = resp.insights[0].agent_id
            
            # Find agent by ID to get priority
            for agent in self.agents:
                if agent.config.id == agent_id:
                    agent_priority = agent.config.priority
                    agent_index = self._agent_index.get(agent_id, 0)
                    break
            
            updates.append((agent_priority, agent_index, agent_id or "unknown", resp))
        
        # Sort by ASCENDING priority, then by registration order
        # This means higher priority agents write LAST (and win)
        updates.sort(key=lambda x: (x[0], x[1]))
        
        # Apply updates
        for priority, index, agent_id, resp in updates:
            # Merge insights
            final_response.insights.extend(resp.insights)
            
            # Merge data sidecar
            for key, value in resp.data.items():
                if key not in final_response.data:
                    final_response.data[key] = value
                elif isinstance(final_response.data[key], list) and isinstance(value, list):
                    final_response.data[key].extend(value)
                else:
                    final_response.data[key] = value
            
            # Apply variable updates to blackboard
            for key, value in resp.variable_updates.items():
                blackboard.set_var(key, value)
                final_response.variable_updates[key] = value
            
            # Apply queue pushes to blackboard
            for queue_name, items in resp.queue_pushes.items():
                blackboard.push_queue_items(queue_name, items)
                if queue_name not in final_response.queue_pushes:
                    final_response.queue_pushes[queue_name] = []
                final_response.queue_pushes[queue_name].extend(items)
            
            # Apply facts to blackboard (deduplication handled by Blackboard)
            for fact in resp.facts:
                blackboard.add_fact(fact)
            final_response.facts.extend(resp.facts)
            
            # Apply memory updates to blackboard
            if resp.memory_updates and agent_id:
                blackboard.update_memory(agent_id, resp.memory_updates)
                final_response.memory_updates.update(resp.memory_updates)
            
            # Handle v1 state_updates (map to variable_updates)
            if resp.state_updates and not resp.variable_updates:
                for key, value in resp.state_updates.items():
                    # Check for legacy memory_{agent_id} pattern
                    if key.startswith("memory_"):
                        # Extract memory data and apply to blackboard memory
                        mem_agent_id = key.replace("memory_", "")
                        if isinstance(value, dict):
                            blackboard.update_memory(mem_agent_id, value)
                    else:
                        blackboard.set_var(key, value)
                        final_response.variable_updates[key] = value
    
    # =========================================================================
    # Eligibility Checks
    # =========================================================================
    
    def _get_eligible_agents(self, context: AgentContext,
                             allowed_agent_ids: Optional[List[str]],
                             trigger_type: TriggerType,
                             meta: Dict) -> List[BaseAgent]:
        """Get agents eligible for Phase 1 execution.
        
        Eligibility is the intersection of:
        1. allowed_agent_ids (if provided) - host filter
        2. Trigger type match - engine routing
        3. Cooldown status - timing gate (handled by agent.process())
        4. Trigger conditions - precondition check
        """
        eligible = []
        
        for agent in self.agents:
            eligible_flag, reason = self._is_eligible(
                agent, context, allowed_agent_ids, trigger_type, meta
            )
            
            if eligible_flag:
                eligible.append(agent)
            else:
                # Fire on_agent_skipped callback
                for cb in self.callbacks:
                    try:
                        if hasattr(cb, 'on_agent_skipped'):
                            asyncio.create_task(
                                cb.on_agent_skipped(agent.config.name, reason)
                            )
                    except Exception as e:
                        logger.error(f"Callback error on_agent_skipped: {e}")
        
        return eligible
    
    def _is_eligible(self, agent: BaseAgent, context: AgentContext,
                     allowed_agent_ids: Optional[List[str]],
                     trigger_type: TriggerType,
                     meta: Dict) -> Tuple[bool, str]:
        """Check if an agent is eligible to run.
        
        Returns:
            Tuple of (is_eligible, skip_reason)
        """
        # 1. Check allow-list (hard filter)
        if allowed_agent_ids is not None:
            if agent.config.id not in allowed_agent_ids:
                return (False, "not_in_allow_list")
        
        # 2. Check trigger type match
        if trigger_type not in agent.config.trigger_types:
            return (False, "trigger_type_mismatch")
        
        # 3. Check trigger conditions (if defined)
        conditions = getattr(agent.config, 'trigger_conditions', None)
        if conditions:
            if not self.condition_evaluator.evaluate(
                conditions, context.blackboard, meta, agent.config.id
            ):
                return (False, "conditions_not_met")
        
        return (True, "")
    
    def _is_eligible_for_phase2(self, agent: BaseAgent, context: AgentContext,
                                 allowed_agent_ids: Optional[List[str]],
                                 meta: Dict) -> bool:
        """Check if an event subscriber is eligible for Phase 2."""
        # Check allow-list
        if allowed_agent_ids is not None:
            if agent.config.id not in allowed_agent_ids:
                return False
        
        # Check trigger conditions
        conditions = getattr(agent.config, 'trigger_conditions', None)
        if conditions:
            if not self.condition_evaluator.evaluate(
                conditions, context.blackboard, meta, agent.config.id
            ):
                return False
        
        return True
    
    # =========================================================================
    # V1 Compatibility Layer
    # =========================================================================
    
    def _sync_state_to_legacy(self, context: AgentContext) -> None:
        """Sync Blackboard variables INTO shared_state for v1.0 agents.
        
        Called BEFORE agents run so v1 agents can read from context.shared_state.
        """
        if context.blackboard:
            context.shared_state.update(context.blackboard.variables)
    
    def _sync_state_from_legacy(self, context: AgentContext,
                                 v1_updates: Dict[str, Any]) -> None:
        """Sync shared_state back INTO Blackboard for consistency.
        
        IMPORTANT: Only sync keys that were MODIFIED by v1.0 agents in this turn.
        Do NOT blindly overwrite all keys — this would clobber v2.0 agent updates.
        """
        if context.blackboard:
            for key, value in v1_updates.items():
                context.blackboard.variables[key] = value
