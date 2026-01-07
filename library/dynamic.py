import os
import json
from jinja2 import Template
from ..core.agent import BaseAgent, AgentConfig
from ..core.models import AgentContext, AgentResponse, InsightType, TriggerType

class DynamicAgent(BaseAgent):
    """
    An agent that loads its persona and configuration from a dictionary (DB/JSON).
    Supports persistent memory via 'private_state'.
    Uses 'schemas/' directory for pluggable output formats.
    """
    def __init__(self, config_dict: dict):
        # Parse Trigger Config
        trigger_conf = config_dict.get("trigger_config", {})
        cooldown = trigger_conf.get("cooldown", 15)
        
        # Parse trigger types (default: turn_based)
        trigger_mode = trigger_conf.get("mode", "turn_based")
        trigger_types = []
        if trigger_mode == "turn_based":
            trigger_types.append(TriggerType.TURN_BASED)
        elif trigger_mode == "keyword":
            trigger_types.append(TriggerType.KEYWORD)
        elif trigger_mode == "silence":
            trigger_types.append(TriggerType.SILENCE)
        elif trigger_mode == "interval":
            trigger_types.append(TriggerType.INTERVAL)
        else:
            # Support multiple modes
            if isinstance(trigger_mode, list):
                for mode in trigger_mode:
                    if mode == "turn_based":
                        trigger_types.append(TriggerType.TURN_BASED)
                    elif mode == "keyword":
                        trigger_types.append(TriggerType.KEYWORD)
                    elif mode == "silence":
                        trigger_types.append(TriggerType.SILENCE)
                    elif mode == "interval":
                        trigger_types.append(TriggerType.INTERVAL)
            else:
                trigger_types = [TriggerType.TURN_BASED]  # Default
        
        # Parse keywords
        trigger_keywords = trigger_conf.get("keywords", [])
        if isinstance(trigger_keywords, str):
            trigger_keywords = [k.strip() for k in trigger_keywords.split(",")]
        
        # Parse silence threshold
        silence_threshold = trigger_conf.get("silence_threshold")
        
        # Parse priority
        priority = trigger_conf.get("priority", config_dict.get("priority", 0))
        
        name = config_dict.get("name", "Dynamic Agent")
        # Extract ID if available (crucial for selection filtering)
        agent_id = config_dict.get("id")
        
        # Parse Model Config
        # Support top-level keys or nested 'model_config'
        model_conf = config_dict.get("model_config", {})
        model = model_conf.get("model", config_dict.get("model", "gpt-4o-mini"))
        
        # Parse output format (default, v2_raw, or custom filename)
        output_format = config_dict.get("output_format", "default")
        
        super().__init__(AgentConfig(
            name=name, 
            id=agent_id, 
            cooldown=cooldown, 
            model=model,
            trigger_types=trigger_types,
            trigger_keywords=trigger_keywords,
            silence_threshold=silence_threshold,
            priority=priority,
            output_format=output_format
        ))
        
        self.system_prompt = config_dict.get("text", "")
        
        # Context Config
        self.context_turns = model_conf.get("context_turns", config_dict.get("context_turns", 6))
        
        # Assign model to self for easy access (or use self.config.model)
        self.model = model
        
        # --- SCHEMA LOADING ---
        # Load schema definition from library/schemas/{output_format}.json
        self.schema_def = self._load_schema(output_format)
        self.json_instruction = self.schema_def.get("instruction", "")
        self.mapping = self.schema_def.get("mapping", {})

    def _load_schema(self, format_name: str) -> dict:
        """Loads schema config from disk, falling back to default if not found."""
        try:
            # Construct path relative to this file
            base_dir = os.path.dirname(os.path.abspath(__file__))
            schema_path = os.path.join(base_dir, "schemas", f"{format_name}.json")
            
            if os.path.exists(schema_path):
                with open(schema_path, "r") as f:
                    return json.load(f)
            else:
                # Fallback to default if file missing
                if format_name != "default":
                    self.logger.warning(f"Schema '{format_name}' not found. Falling back to default.")
                
                # Load default
                default_path = os.path.join(base_dir, "schemas", "default.json")
                if os.path.exists(default_path):
                    with open(default_path, "r") as f:
                        return json.load(f)
                        
        except Exception as e:
            self.logger.error(f"Failed to load schema '{format_name}': {e}")
        
        # Emergency Hardcoded Fallback (if JSON files are missing entirely)
        return {
            "instruction": "IMPORTANT: Return { \"has_insight\": boolean, \"message\": \"...\", \"type\": \"suggestion\" }",
            "mapping": {
                "check_field": "has_insight",
                "content_field": "message",
                "type_field": "type"
            }
        }

    async def evaluate(self, context: AgentContext) -> AgentResponse:
        if not self.llm:
            return None

        # 0. Load Persistent Memory (from Shared Blackboard)
        # We namespace memory by agent ID to avoid collisions
        mem_key = f"memory_{self.config.id}"
        persistent_memory = context.shared_state.get(mem_key, {}) if context.shared_state else {}
        
        # Merge Persistent State into RAM State
        # (Persistence is the source of truth for restart recovery)
        if persistent_memory and isinstance(persistent_memory, dict):
            self.private_state.update(persistent_memory)

        # 1. Format Transcript (Configurable Window)
        # Use self.context_turns to slice
        turns = []
        
        # Handle 0 or large numbers gracefully
        # If context_turns is 0, take ALL (slice_start=0)? Or none? Let's assume 0 means "Unlimited/All".
        # Actually standard python slice [-0:] is empty.
        if self.context_turns <= 0:
            target_segments = context.recent_segments # All available in context
        else:
            slice_start = -self.context_turns if len(context.recent_segments) >= self.context_turns else 0
            target_segments = context.recent_segments[slice_start:]
        
        for seg in target_segments:
            turns.append(f"{seg.speaker}: {seg.text}")
        
        transcript_slice = "\n".join(turns)
        
        # 2. Build Prompt with Memory Injection
        # We serialize the private state to JSON
        current_memory = json.dumps(self.private_state, indent=2)
        
        # 14/10 Upgrade: Jinja2 Rendering of System Prompt
        # This allows prompts to access {{ state.phase }}, {{ context.user_context }}, etc.
        # We fail gracefully if Jinja2 crashes to keep the agent alive.
        rendered_system_prompt = self.system_prompt
        try:
            template = Template(self.system_prompt)
            # We inject both the raw shared_state (as object) and a flattened version for convenience if needed.
            # Best practice: Use {{ state.key }}
            rendered_system_prompt = template.render(
                state=context.shared_state,      # Access blackboard via {{ state.my_key }}
                memory=self.private_state,       # Access private via {{ memory.my_key }}
                context=context,                 # Access full context via {{ context }}
                user_context=context.user_context # Shortcut
            )
        except Exception as e:
            self.logger.warning(f"Jinja2 rendering failed for {self.config.name}: {e}. using raw prompt.")

        
        # 3. Inject RAG (if available)
        rag_section = ""
        if context.rag_docs:
            rag_text = "\n---\n".join(context.rag_docs)
            rag_section = f"\n[RELEVANT KNOWLEDGE/DOCS]\n{rag_text}\n"
        
        # 4. Inject trigger context
        trigger_context = ""
        if context.trigger_type == TriggerType.KEYWORD and context.trigger_metadata.get("keyword"):
            trigger_context = f"\n[TRIGGER] You were activated by keyword: '{context.trigger_metadata['keyword']}'\n"
        elif context.trigger_type == TriggerType.SILENCE and context.trigger_metadata.get("silence_duration"):
            trigger_context = f"\n[TRIGGER] You were activated after {context.trigger_metadata['silence_duration']:.1f} seconds of silence.\n"

        # 5. Inject Language Directive
        language_section = ""
        if context.language_directive:
            language_section = f"\n{context.language_directive}\n"

        # 6. Inject User Context (Cognitive Frame)
        user_context_section = ""
        if context.user_context:
            user_context_section = f"{context.user_context}\n\n"

        full_system_prompt = f"""
        {user_context_section}
        {language_section}
        {rendered_system_prompt}
        
        [YOUR MEMORY / SCRATCHPAD]
        {current_memory}
        {rag_section}
        {trigger_context}
        {self.json_instruction}
        """
        
        messages = [
            {"role": "system", "content": full_system_prompt},
            {"role": "user", "content": f"### TRANSCRIPT:\n{transcript_slice}"}
        ]
        
        # 4. Call LLM (Dynamic Model)
        try:
            result = await self.llm.generate_json(model=self.model, messages=messages)
        except Exception as e:
            self.logger.error(f"LLM call failed for {self.config.name}: {e}", exc_info=True)
            return None
        
        response = AgentResponse()
        
        # SoC Principle: The Agent knows what it sent. We attach it for observability.
        response.debug_info = {
            "prompt_messages": messages,
            "model": self.model,
            "llm_output": result
        }
        
        if result:
            # Log for debugging
            self.logger.debug(f"{self.config.name} evaluation: result_keys={list(result.keys())}")
            
            # --- GENERIC DYNAMIC PARSING (12/10 Architecture) ---
            # 1. Resolve Root Object (if nested)
            root_data = result
            if self.mapping.get("root_key"):
                root_data = result.get(self.mapping["root_key"], {})
            
            if not isinstance(root_data, dict):
                 # Fallback/Safety if root key was missing or invalid
                 root_data = {}

            # 2. Check "Should I Speak?" condition
            should_speak = True
            check_field = self.mapping.get("check_field")
            if check_field:
                # If check field exists (e.g. "has_insight"), assume it drives the decision
                should_speak = result.get(check_field, False)
            else:
                # If no check field (like v2_raw), existence of root content implies yes
                # But we check if root_data is empty
                if not root_data and self.mapping.get("root_key"):
                    should_speak = False

            # 3. Extract Core Fields
            if should_speak:
                # Content
                content_key = self.mapping.get("content_field", "content")
                content = root_data.get(content_key)
                
                if content:
                    # Type
                    type_key = self.mapping.get("type_field", "type")
                    type_str = root_data.get(type_key, "suggestion").lower()
                    try:
                        insight_type = InsightType(type_str)
                    except ValueError:
                        # Map common aliases if needed, or default
                        insight_type = InsightType.SUGGESTION
                    
                    # Confidence
                    conf_key = self.mapping.get("confidence_field", "confidence")
                    confidence = root_data.get(conf_key, 1.0)
                    
                    insight = self.create_insight(
                        content=content,
                        type=insight_type,
                        confidence=confidence
                    )
                    
                    # Metadata Extraction
                    meta_key = self.mapping.get("metadata_field")
                    if meta_key:
                        # Look in root_data first, then fallback to result root if needed?
                        # Usually metadata is alongside content
                        insight.metadata = root_data.get(meta_key, {})
                    else:
                        # Default behavior: try "metadata" key anyway if present? 
                        # Or strictly follow schema. Let's start strictly.
                        pass
                        
                    response.insights.append(insight)
            
            # 4. State/Memory Extraction
            state_key = self.mapping.get("state_field")
            if state_key:
                # Check if state is at root of RESULT (like v2_raw state_snapshot) or inside ROOT_DATA?
                # v2_raw has state_snapshot at RESULT level, not INSIGHT level.
                # default has memory_updates at RESULT level.
                # So state is usually at RESULT level.
                is_state_at_root = self.mapping.get("is_state_at_root", False) # Flag for v2 style
                
                updates = {}
                if is_state_at_root:
                    # Look in top-level result
                    updates = result.get(state_key, {})
                else:
                    # Look in top-level result (Legacy default behavior was top level too)
                    updates = result.get(state_key, {})
                
                if updates and isinstance(updates, dict):
                     # Legacy memory logic vs V2 State Logic
                     # If legacy (key=memory_updates), we treat it as Private State -> Shared Blackboard
                     if state_key == "memory_updates":
                         self.private_state.update(updates)
                         mem_key = f"memory_{self.config.id}"
                         if response.state_updates is None: response.state_updates = {}
                         response.state_updates[mem_key] = self.private_state
                     else:
                         # V2 Generic State Logic (Direct write to blackboard)
                         response.state_updates = updates

            # 5. Generic Data Sidecar Extraction (12/10 Architecture)
            # Allows schema to map arbitrary fields (e.g. 'ui_actions') to response.data
            data_field = self.mapping.get("data_field")
            data_key = self.mapping.get("data_key", data_field) # Default to same name
            
            if data_field and data_key:
                # We assume sidecar data is at the root of the result
                sidecar_payload = result.get(data_field)
                if sidecar_payload:
                    response.data[data_key] = sidecar_payload

        else:
            self.logger.warning(f"{self.config.name} received None result from LLM")
            
        return response
