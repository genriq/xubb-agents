import os
import json
import logging
from jinja2.sandbox import SandboxedEnvironment
from ..core.agent import BaseAgent, AgentConfig, DEFAULT_MODEL
from ..core.models import AgentContext, AgentResponse, InsightType, TriggerType, Event, Fact

logger = logging.getLogger(__name__)

class DynamicAgent(BaseAgent):
    """
    An agent that loads its persona and configuration from a dictionary (DB/JSON).
    Supports persistent memory via 'private_state'.
    Uses 'schemas/' directory for pluggable output formats.

    V2 additions:
    - trigger_conditions: Preconditions evaluated by engine
    - subscribed_events: Events that trigger this agent
    - Blackboard access in Jinja2 templates via {{ blackboard }}
    - Parses v2 response fields: events, variable_updates, queue_pushes, facts, memory_updates

    v2.2 hardening:
    - A-1 silence gate: a gate-less + rootless agent defaults to silence;
      opt in to speaking via the ``speak_without_gate`` flag.
    - A-2 session-relative timestamps: time references are anchored to the
      session, not wall-clock.
    - A-3 confidence clamp: parsed insight confidence is clamped to [0, 1].
    - S-1 schema pass-through: ``expiry`` and ``action_label`` are read from
      the mapped fields and passed through to created insights.
    - MR-1 memory read-path: persistent memory is read from
      ``shared_state["memory_<id>"]`` (synced from the blackboard by the engine).
    """
    _jinja_env = SandboxedEnvironment()
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
        elif trigger_mode == "event":
            trigger_types.append(TriggerType.EVENT)
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
                    elif mode == "event":
                        trigger_types.append(TriggerType.EVENT)
            else:
                trigger_types = [TriggerType.TURN_BASED]  # Default
        
        # Parse keywords
        trigger_keywords = trigger_conf.get("keywords", [])
        if isinstance(trigger_keywords, str):
            trigger_keywords = [k.strip() for k in trigger_keywords.split(",")]
        
        # Parse silence threshold
        silence_threshold = trigger_conf.get("silence_threshold")

        # Parse interval (seconds between INTERVAL-mode firings). Previously never
        # read here, so AgentConfig.trigger_interval stayed None and the host's
        # `if interval and ...` gate never fired an interval-mode agent (DOA for
        # vault-authored configs). Coerced defensively: a non-numeric or
        # non-positive value is treated as absent (warn), not a config crash.
        trigger_interval = trigger_conf.get("trigger_interval")
        if trigger_interval is not None:
            try:
                trigger_interval = int(trigger_interval)
                if trigger_interval <= 0:
                    logger.warning(
                        f"Ignoring non-positive trigger_interval ({trigger_interval}) "
                        f"for agent '{config_dict.get('name', '?')}'"
                    )
                    trigger_interval = None
            except (TypeError, ValueError):
                logger.warning(
                    f"Ignoring non-numeric trigger_interval "
                    f"({trigger_conf.get('trigger_interval')!r}) for agent "
                    f"'{config_dict.get('name', '?')}'"
                )
                trigger_interval = None

        # V2: Parse subscribed events
        subscribed_events = trigger_conf.get("subscribed_events", [])

        # DynamicAgent convenience normalization: auto-add TriggerType.EVENT
        # when subscribed_events is non-empty. Custom BaseAgent subclasses are
        # not auto-modified — the engine-level guard catches those.
        if subscribed_events and TriggerType.EVENT not in trigger_types:
            trigger_types.append(TriggerType.EVENT)

        # Parse priority
        priority = trigger_conf.get("priority", config_dict.get("priority", 0))
        
        name = config_dict.get("name", "Dynamic Agent")
        # Extract ID if available (crucial for selection filtering)
        agent_id = config_dict.get("id")
        
        # Parse Model Config
        # Support top-level keys or nested 'model_config'
        model_conf = config_dict.get("model_config", {})
        model = model_conf.get("model", config_dict.get("model", DEFAULT_MODEL))
        
        # Parse output format (default, v2_raw, or custom filename)
        output_format = config_dict.get("output_format", "default")
        
        # V2: Parse trigger conditions
        trigger_conditions = config_dict.get("trigger_conditions")
        
        super().__init__(AgentConfig(
            name=name,
            id=agent_id,
            cooldown=cooldown,
            model=model,
            trigger_interval=trigger_interval,
            trigger_types=trigger_types,
            trigger_keywords=trigger_keywords,
            silence_threshold=silence_threshold,
            priority=priority,
            output_format=output_format,
            # V2 additions
            trigger_conditions=trigger_conditions,
            subscribed_events=subscribed_events
        ))
        
        self.system_prompt = config_dict.get("text", "")

        # Context Config
        self.context_turns = model_conf.get("context_turns", config_dict.get("context_turns", 6))
        self.include_context = config_dict.get("include_context", True)
        
        # Assign model to self for easy access (or use self.config.model)
        self.model = model
        
        # --- SCHEMA LOADING ---
        # Load schema definition from library/schemas/{output_format}.json
        self.schema_def = self._load_schema(output_format)
        self.json_instruction = self.schema_def.get("instruction", "")
        self.mapping = self.schema_def.get("mapping", {})

        # A-1 / INV-11: warn at load time if the schema is misconfigured in a way
        # that silently loses the "stay silent" contract.
        self._warn_on_gateless_misconfig(output_format)

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

    # A-1 (INV-11): gate fields a schema's instruction might reference. If the
    # prose tells the model about one of these but the mapping forgets to wire it
    # up via `check_field`, the silence gate is silently lost — the exact
    # misconfiguration A-1 guards against.
    _GATE_FIELD_HINTS = ("has_insight", "should_speak", "speak", "is_relevant")

    def _warn_on_gateless_misconfig(self, format_name: str) -> None:
        """A-1 / INV-11: load-time warning for gate-less schema misconfiguration.

        A custom schema can lose the "stay silent" contract in a way that is
        invisible until it spams the HUD: the instruction text tells the model
        to emit a boolean gate (e.g. ``has_insight``), but the mapping omits
        ``check_field`` (and has no ``root_key`` emptiness gate either). In that
        state the parser has nothing to gate on, so the documented gate-less
        default policy (see `evaluate`'s should_speak block) applies and the
        model's intended silence is dropped.

        We warn ONCE at load time so the author notices the mismatch. Gated
        schemas (default, default_v2, custom1) and root-keyed schemas (v2_raw,
        ui_control, widget_control) are all unaffected.
        """
        mapping = self.mapping or {}
        if mapping.get("check_field") or mapping.get("root_key"):
            return  # Properly gated — nothing to warn about.

        instruction = (self.json_instruction or "").lower()
        referenced = [hint for hint in self._GATE_FIELD_HINTS if hint in instruction]
        if referenced:
            self.logger.warning(
                "Schema '%s' is gate-less (mapping has no 'check_field' and no "
                "'root_key') but its instruction references gate field(s) %s. The "
                "silence gate is NOT wired up: the model's intended silence will be "
                "ignored. Add 'check_field' to the mapping, or set "
                "'speak_without_gate: true' to opt into the speak-when-content "
                "default explicitly. (A-1/INV-11)",
                format_name,
                referenced,
            )

    @staticmethod
    def _coerce_confidence(raw) -> float:
        """A-3: Coerce model-supplied confidence to a float in [0,1].

        Accepts ints/floats/numeric strings. Clamps out-of-range values into
        [0,1]. Returns 1.0 for anything non-numeric (e.g. "high") or NaN so a
        bad value never propagates into AgentInsight's ge=0,le=1 validator.
        """
        try:
            val = float(raw)
        except (TypeError, ValueError):
            return 1.0
        # Reject NaN (NaN != NaN); inf clamps below.
        if val != val:
            return 1.0
        if val < 0.0:
            return 0.0
        if val > 1.0:
            return 1.0
        return val

    @staticmethod
    def _coerce_expiry(raw):
        """S-1: Coerce model-supplied expiry to a positive int (seconds).

        Returns None (→ AgentInsight default of 15s) for missing/invalid/
        non-positive values so a bad value never crashes the insight.
        """
        if raw is None:
            return None
        try:
            val = int(float(raw))
        except (TypeError, ValueError):
            return None
        if val <= 0:
            return None
        return val

    @staticmethod
    def _coerce_action_label(raw):
        """S-1: Coerce model-supplied action_label to a non-empty str or None."""
        if raw is None:
            return None
        try:
            text = str(raw).strip()
        except Exception:
            return None
        return text or None

    def _session_now(self, context: AgentContext) -> float:
        """A-2 / INV-13: best-available session-relative 'now' in seconds.

        The documented convention (SPEC_V2 §timestamps) is that ALL model
        timestamps — TranscriptSegment, Event, Fact — are session-relative
        seconds, not wall-clock epoch. The engine does not currently thread a
        dedicated session-start reference into the agent, so the cleanest
        non-invasive reference reachable here is the conversation itself: the
        most recent segment's (already session-relative) timestamp is the
        current session-relative time.

        LIMITATION: if the context carries no segments (e.g. an event-only
        Phase-2 run with an empty window), we fall back to 0.0 (session start)
        rather than wall-clock. This is a deliberate minimal-safe choice: it
        guarantees we NEVER emit a raw epoch, at the cost of a 0.0 stamp in the
        rare no-segment case. A future signature change threading an explicit
        session clock would remove this fallback.
        """
        try:
            segments = context.recent_segments or []
            if segments:
                return float(max(seg.timestamp for seg in segments))
        except Exception:
            pass
        return 0.0

    async def evaluate(self, context: AgentContext) -> AgentResponse:
        if not self.llm:
            return None

        # 0. Load Persistent Memory (from Shared Blackboard)
        # We namespace memory by agent ID to avoid collisions
        mem_key = f"memory_{self.config.id}"
        persistent_memory = context.shared_state.get(mem_key, {}) if context.shared_state else {}

        # Build working memory for this evaluation (do not mutate self.private_state)
        working_memory = dict(self.private_state)
        if persistent_memory and isinstance(persistent_memory, dict):
            working_memory.update(persistent_memory)

        # 1. Format Transcript (Configurable Window)
        # Apply context_turns_modifier from role overrides (+N = more, -N = less, <=0 = all)
        effective_turns = self.context_turns
        overrides = context.agent_config_overrides.get(self.config.id)
        if overrides and overrides.context_turns_modifier is not None:
            effective_turns = effective_turns + overrides.context_turns_modifier

        turns = []
        if effective_turns <= 0:
            target_segments = context.recent_segments  # All available in context
        else:
            slice_start = -effective_turns if len(context.recent_segments) >= effective_turns else 0
            target_segments = context.recent_segments[slice_start:]
        
        for seg in target_segments:
            turns.append(f"{seg.speaker}: {seg.text}")
        
        transcript_slice = "\n".join(turns)
        
        # 2. Build Prompt with Memory Injection
        # We serialize the private state to JSON
        current_memory = json.dumps(working_memory, indent=2)
        
        # Jinja2 Rendering of System Prompt
        # This allows prompts to access {{ state.phase }}, {{ blackboard.variables }}, etc.
        # We fail gracefully if Jinja2 crashes to keep the agent alive.
        rendered_system_prompt = self.system_prompt
        try:
            template = self._jinja_env.from_string(self.system_prompt)
            rendered_system_prompt = template.render(
                # V1 compatibility
                state=context.shared_state,      # Access via {{ state.my_key }}
                memory=working_memory,            # Access via {{ memory.my_key }}
                context=context,                 # Access via {{ context }}
                user_context=context.user_context, # Shortcut
                # V2 additions
                blackboard=context.blackboard,   # Access via {{ blackboard.variables.key }}
                agent_id=self.config.id          # Access via {{ agent_id }}
            )
        except Exception as e:
            self.logger.warning(f"Jinja2 rendering failed for {self.config.name}: {e}. using raw prompt.")

        
        # 3. Inject RAG (if available and include_context is enabled)
        rag_section = ""
        if self.include_context and context.rag_docs:
            rag_text = "\n---\n".join(context.rag_docs)
            rag_section = f"\n[RELEVANT KNOWLEDGE/DOCS]\n{rag_text}\n"

        # 4. Inject trigger context
        trigger_context = ""
        if context.trigger_type == TriggerType.KEYWORD and context.trigger_metadata.get("keyword"):
            trigger_context = f"\n[TRIGGER] You were activated by keyword: '{context.trigger_metadata['keyword']}'\n"
        elif context.trigger_type == TriggerType.SILENCE and context.trigger_metadata.get("silence_duration"):
            trigger_context = f"\n[TRIGGER] You were activated after {context.trigger_metadata['silence_duration']:.1f} seconds of silence.\n"

        # 5. Inject Language Directive (always injected — language is not "context")
        language_section = ""
        if context.language_directive:
            language_section = f"\n{context.language_directive}\n"

        # 6. Inject User Context (Cognitive Frame — gated by include_context)
        user_context_section = ""
        if self.include_context and context.user_context:
            user_context_section = f"{context.user_context}\n\n"

        parts = []
        if user_context_section:
            parts.append(user_context_section)
        if language_section:
            parts.append(language_section)
        parts.append(rendered_system_prompt)
        parts.append(f"[YOUR MEMORY / SCRATCHPAD]\n{current_memory}")
        if rag_section:
            parts.append(rag_section)
        if trigger_context:
            parts.append(trigger_context)
        if self.json_instruction:
            parts.append(self.json_instruction)

        full_system_prompt = "\n\n".join(parts)

        # Append role instructions_append (after system prompt, before user content)
        if overrides and overrides.instructions_append and overrides.instructions_append.strip():
            full_system_prompt += f"\n\n# Role Overrides\n{overrides.instructions_append.strip()}"

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
            
            # --- Generic dynamic parsing ---
            # 1. Resolve Root Object (if nested)
            root_data = result
            if self.mapping.get("root_key"):
                root_data = result.get(self.mapping["root_key"], {})
            
            if not isinstance(root_data, dict):
                 # Fallback/Safety if root key was missing or invalid
                 root_data = {}

            # 2. Check "Should I Speak?" condition
            #
            # A-1 / INV-11 — gate-less schema silence contract.
            # An agent must stay silent when its schema's gate says so, and the
            # ABSENCE of a gate must never *force* speech every turn (HUD spam).
            # Three cases, in precedence order:
            #
            #   (a) check_field present (default, default_v2, custom1):
            #       the boolean gate (e.g. has_insight) drives the decision.
            #       Missing/false ⇒ silence. UNCHANGED behavior.
            #
            #   (b) no check_field but root_key present (v2_raw, ui_control,
            #       widget_control): the model speaks by *presence* — emitting a
            #       non-empty root object IS the gate. An absent/empty root ⇒
            #       silence. UNCHANGED behavior.
            #
            #   (c) no check_field AND no root_key (gate-less, rootless — only
            #       reachable via user-authored custom schemas): there is NO
            #       structural gate at all. The DOCUMENTED DEFAULT POLICY is to
            #       stay SILENT rather than emit an insight on every turn that has
            #       any content. A schema author who genuinely wants
            #       "content-present ⇒ speak" must OPT IN explicitly by setting
            #       "speak_without_gate": true in the mapping. This is the safe,
            #       documented default that honors INV-11; load-time warning in
            #       _warn_on_gateless_misconfig flags the common misconfiguration.
            check_field = self.mapping.get("check_field")
            if check_field:
                # (a) Explicit gate field drives the decision.
                should_speak = root_data.get(check_field, False)
            elif self.mapping.get("root_key"):
                # (b) Presence of a non-empty root object is the gate.
                should_speak = bool(root_data)
            else:
                # (c) Gate-less + rootless: default to silence unless opted in.
                should_speak = bool(self.mapping.get("speak_without_gate", False))

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
                    
                    # Confidence (A-3): coerce to float and clamp to [0,1].
                    # A bad LLM value (e.g. 1.5 or "high") must NOT turn a good
                    # insight into a validation ERROR — default to 1.0 on failure.
                    conf_key = self.mapping.get("confidence_field", "confidence")
                    confidence = self._coerce_confidence(root_data.get(conf_key, 1.0))

                    # expiry / action_label (S-1): schemas instruct the model to
                    # return these, so honor the contract and pass them through.
                    # Coerce safely; a bad value must not crash the insight.
                    expiry = self._coerce_expiry(
                        root_data.get(self.mapping.get("expiry_field", "expiry"))
                    )
                    action_label = self._coerce_action_label(
                        root_data.get(self.mapping.get("action_label_field", "action_label"))
                    )

                    insight = self.create_insight(
                        content=content,
                        type=insight_type,
                        confidence=confidence,
                        expiry=expiry,
                        action_label=action_label,
                    )
                    
                    # Metadata Extraction
                    meta_key = self.mapping.get("metadata_field")
                    if meta_key:
                        # Look in root_data first, then fallback to result root if needed?
                        # Usually metadata is alongside content
                        insight.metadata = root_data.get(meta_key, {})

                    response.insights.append(insight)
            
            # 4. State/Memory Extraction
            state_key = self.mapping.get("state_field")
            if state_key:
                updates = result.get(state_key, {})
                
                if updates and isinstance(updates, dict):
                     # Legacy memory logic vs V2 State Logic
                     # If legacy (key=memory_updates), we treat it as Private State -> Shared Blackboard
                     if state_key == "memory_updates":
                         self.private_state.update(updates)
                         mem_key = f"memory_{self.config.id}"
                         # Emit a COPY: self.private_state is live and keeps mutating on
                         # later turns, and the response may be captured by a tracer — it
                         # must not alias the agent's internal state.
                         response.state_updates[mem_key] = dict(self.private_state)
                     else:
                         # V2 Generic State Logic (Direct write to blackboard)
                         response.state_updates = updates

            # 5. Generic Data Sidecar Extraction
            # Allows schema to map arbitrary fields (e.g. 'ui_actions') to response.data
            data_field = self.mapping.get("data_field")
            data_key = self.mapping.get("data_key", data_field) # Default to same name
            
            if data_field and data_key:
                # We assume sidecar data is at the root of the result
                sidecar_payload = result.get(data_field)
                if sidecar_payload:
                    response.data[data_key] = sidecar_payload
            
            # ================================================================
            # V2: Extract new fields (events, variable_updates, queue_pushes, facts, memory_updates)
            # ================================================================
            
            # 6. Events extraction
            events_field = self.mapping.get("events_field", "events")
            raw_events = result.get(events_field, [])
            if raw_events and isinstance(raw_events, list):
                current_time = self._session_now(context)  # A-2: session-relative, not epoch
                for evt in raw_events:
                    if isinstance(evt, dict):
                        event = Event(
                            name=evt.get("name", ""),
                            payload=evt.get("payload") or evt.get("data", {}),
                            source_agent=self.config.id,
                            timestamp=current_time,
                            id=evt.get("id")
                        )
                        response.events.append(event)
                    elif isinstance(evt, str):
                        # Simple string event (legacy format)
                        event = Event(
                            name=evt,
                            payload={},
                            source_agent=self.config.id,
                            timestamp=current_time
                        )
                        response.events.append(event)
            
            # 7. Variable updates (v2 style - replaces state_updates)
            var_field = self.mapping.get("variable_updates_field", "variable_updates")
            var_updates = result.get(var_field, {})
            if var_updates and isinstance(var_updates, dict):
                response.variable_updates.update(var_updates)
            
            # 8. Queue pushes
            queue_field = self.mapping.get("queue_field", "queue_pushes")
            queue_pushes = result.get(queue_field, {})
            if queue_pushes and isinstance(queue_pushes, dict):
                for queue_name, items in queue_pushes.items():
                    if isinstance(items, list):
                        if queue_name not in response.queue_pushes:
                            response.queue_pushes[queue_name] = []
                        response.queue_pushes[queue_name].extend(items)
            
            # 9. Facts extraction
            facts_field = self.mapping.get("facts_field", "facts")
            raw_facts = result.get(facts_field, [])
            if raw_facts and isinstance(raw_facts, list):
                current_time = self._session_now(context)  # A-2: session-relative, not epoch
                for f in raw_facts:
                    if isinstance(f, dict):
                        fact = Fact(
                            type=f.get("type", "unknown"),
                            key=f.get("key"),
                            value=f.get("value"),
                            confidence=f.get("confidence", 1.0),
                            source_agent=self.config.id,
                            timestamp=current_time
                        )
                        response.facts.append(fact)
            
            # 10. Memory updates (v2 style - agent-private state)
            memory_field = self.mapping.get("memory_field", "memory_updates")
            memory_updates = result.get(memory_field, {})
            if memory_updates and isinstance(memory_updates, dict):
                # Also update private_state for backward compatibility
                self.private_state.update(memory_updates)
                response.memory_updates.update(memory_updates)

        else:
            self.logger.warning(f"{self.config.name} received None result from LLM")
            
        return response
