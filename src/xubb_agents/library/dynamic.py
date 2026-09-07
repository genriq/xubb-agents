import os
import json
import logging
import uuid
from typing import Any, Dict, Optional
from jinja2.sandbox import SandboxedEnvironment
from ..core.agent import BaseAgent, AgentConfig, DEFAULT_MODEL
from ..core.models import (
    AgentContext, AgentResponse, InsightType, TriggerType, Event, Fact, InsightDiagnostic,
    InsightConfig,
)
from ..core.insight_validation import (
    DomainChannels, resolve_gate_mode, evaluate_gate, validate_legacy_candidate,
    validate_domain_channels, decide_legacy,
)

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
        # externally-authored configs). Coerced defensively: a non-numeric or
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

        # v2.6 RC-1/RC-3: per-agent LLM-call config — coerced defensively per
        # house pattern (bad values warn and are treated as absent, never a
        # config crash), stored canonically on AgentConfig.
        agent_name = config_dict.get("name", "Dynamic Agent")
        reasoning_effort = model_conf.get("reasoning_effort")
        if reasoning_effort is not None and not isinstance(reasoning_effort, str):
            logger.warning(
                f"Ignoring non-string reasoning_effort ({reasoning_effort!r}) "
                f"for agent '{agent_name}'"
            )
            reasoning_effort = None
        llm_timeout = self._coerce_positive_number(
            model_conf.get("timeout"), "timeout", agent_name, float)
        llm_max_tokens = self._coerce_positive_number(
            model_conf.get("max_tokens"), "max_tokens", agent_name, int)

        # v2.6 RC-2: model_params passthrough — non-dict warns and is treated
        # as absent; collisions with framework-owned wire keys are rejected
        # HERE (pure-config check, reachable even for direct-constructed
        # agents that never pass engine registration).
        model_params = model_conf.get("model_params")
        if model_params is None:
            model_params = {}
        elif not isinstance(model_params, dict):
            logger.warning(
                f"Ignoring non-dict model_params ({model_params!r}) "
                f"for agent '{agent_name}'"
            )
            model_params = {}
        else:
            from ..core.llm import FRAMEWORK_OWNED_PARAMS
            from ..core.engine import AgentConfigurationError
            collisions = sorted(set(model_params) & FRAMEWORK_OWNED_PARAMS)
            if collisions:
                raise AgentConfigurationError(
                    f"Agent '{agent_name}': model_params may not set framework-owned "
                    f"key(s) {collisions} — use the dedicated model_config fields "
                    f"(model / reasoning_effort / timeout / max_tokens) instead."
                )
        
        # XUBB-ITC-1 (G1): per-agent insight_config. A malformed block is a
        # CONFIG error (loud at construction, like model_params collisions) —
        # never a silent widening or narrowing of the vocabulary.
        raw_insight_config = config_dict.get("insight_config")
        insight_config = None
        if raw_insight_config is not None:
            if not isinstance(raw_insight_config, dict):
                from ..core.engine import AgentConfigurationError
                raise AgentConfigurationError(
                    f"Agent '{agent_name}': insight_config must be an object, got "
                    f"{type(raw_insight_config).__name__}")
            try:
                insight_config = InsightConfig(**raw_insight_config)
            except (ValueError, TypeError) as e:
                from ..core.engine import AgentConfigurationError
                raise AgentConfigurationError(f"Agent '{agent_name}': invalid insight_config: {e}") from e

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
            subscribed_events=subscribed_events,
            # v2.6 per-agent LLM-call config (RC-1/RC-2/RC-3)
            reasoning_effort=reasoning_effort,
            timeout=llm_timeout,
            max_tokens=llm_max_tokens,
            model_params=model_params,
            insight_config=insight_config,
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
        # XUBB-ITC-1 §13.1: versioned descriptor (gate_mode, supported types,
        # contracts). Absent on user-authored schemas → inferred from the mapping.
        self.descriptor = self.schema_def.get("descriptor", {}) or {}

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
            },
            "descriptor": {"gate_mode": "boolean", "supported_contracts": ["legacy_v2"]},
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
    def _coerce_positive_number(raw, field_name, agent_name, cast):
        """RC-3: coerce a per-agent LLM budget to a positive number, or None.

        House pattern (cf. trigger_interval): a non-numeric or non-positive
        value is warned and treated as absent — never a config crash.
        """
        if raw is None:
            return None
        try:
            value = cast(raw)
            if value <= 0:
                logger.warning(
                    f"Ignoring non-positive {field_name} ({raw!r}) "
                    f"for agent '{agent_name}'"
                )
                return None
            return value
        except (TypeError, ValueError):
            logger.warning(
                f"Ignoring non-numeric {field_name} ({raw!r}) "
                f"for agent '{agent_name}'"
            )
            return None

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
        # QW-3: no trailing "\n\n" — the join below supplies section separation;
        # a trailing separator here produced a blank joined section (D1 bloat).
        user_context_section = ""
        if self.include_context and context.user_context:
            user_context_section = context.user_context

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
        # OB-2: duck-type the client (same house pattern as _close_llm_client).
        # A real LLMClient exposes the enriched per-call generate() -> LLMResult
        # (race-free category + usage attribution, INV-17); duck-typed fakes
        # (e.g. a test double) may implement only generate_json — both
        # keep working, the enrichment is simply absent.
        # RC-1/RC-2/RC-3 / INV-15: per-agent LLM-call config is forwarded
        # ONLY when configured — an unconfigured agent sends zero extra kwargs,
        # so strict-signature fakes (no **kwargs) stay compatible
        # and the wire carries exactly what the operator wrote.
        llm_kwargs = {}
        if self.config.reasoning_effort is not None:
            llm_kwargs["reasoning_effort"] = self.config.reasoning_effort
        if self.config.timeout is not None:
            llm_kwargs["timeout"] = self.config.timeout
        if self.config.max_tokens is not None:
            llm_kwargs["max_tokens"] = self.config.max_tokens
        if self.config.model_params:
            llm_kwargs["extra_params"] = self.config.model_params

        llm_usage = None
        try:
            gen = getattr(self.llm, "generate", None)
            if callable(gen):
                llm_result = await gen(model=self.model, messages=messages, **llm_kwargs)
                result = llm_result.parsed
                llm_usage = llm_result.usage
            else:
                result = await self.llm.generate_json(model=self.model, messages=messages,
                                                      **llm_kwargs)
        except Exception as e:
            self.logger.error(f"LLM call failed for {self.config.name}: {e}", exc_info=True)
            return None

        execution_id = uuid.uuid4().hex
        response = AgentResponse(execution_id=execution_id)

        # SoC Principle: The Agent knows what it sent. We attach it for observability.
        response.debug_info = {
            "prompt_messages": messages,
            "model": self.model,
            "llm_output": result
        }
        # OB-2: per-call usage — first-class on the response (debug_info is
        # exclude=True and never serializes) AND in debug_info for the tracer.
        if llm_usage is not None:
            response.usage = llm_usage
            response.debug_info["usage"] = llm_usage

        if not isinstance(result, dict):
            # No JSON object arrived: the LLM client already logged its failure
            # category (timeout / malformed / truncated / ...), or the body was
            # not an object. Unparseable envelope ⇒ whole response rejected
            # (D-LR). Usage and the diagnostic survive; nothing is staged.
            self.logger.warning(f"{self.config.name} received no JSON object from LLM")
            response.acceptance_status = "rejected"
            response.diagnostics.append(self._diagnostic(
                execution_id, "invalid_envelope", "$",
                classification="none" if result is None else type(result).__name__,
            ))
            return response

        self._stage_legacy(result, context, working_memory, execution_id, response)
        return response

    # ------------------------------------------------------------------
    # G0 staging (XUBB-ITC-1 §8 / FINAL_DECISIONS D-LR).
    #
    # parse → gate → validate insight → validate domain channels independently
    # → decide → stage. NOTHING here mutates self.private_state, the Blackboard
    # or any durable state; the engine commits staged channels at its merge
    # boundary (legacy_v2: insight-only rejection for recoverable insight
    # errors; fatal domain/envelope errors reject the whole response).
    # ------------------------------------------------------------------

    def _diagnostic(self, execution_id: str, code: str, field_path: str = "",
                    classification: Optional[str] = None, **extra) -> InsightDiagnostic:
        return InsightDiagnostic(execution_id=execution_id, agent_id=self.config.id,
                                 code=code, field_path=field_path,
                                 classification=classification, **extra)

    def _stage_legacy(self, result: Dict[str, Any], context: AgentContext,
                      working_memory: Dict[str, Any], execution_id: str,
                      response: AgentResponse) -> None:
        mapping = self.mapping

        # 1. Root object (nested schemas). A malformed root is reported by the
        #    gate check, not silently treated as an empty object.
        root_key = mapping.get("root_key")
        root_data = result.get(root_key, {}) if root_key else result
        if not isinstance(root_data, dict):
            root_data = {}

        # 2. Gate — declared mode, never raw truthiness (§8.2).
        gate_mode = resolve_gate_mode(mapping, self.descriptor)
        speak, gate_issue = evaluate_gate(gate_mode, mapping, result, root_data)
        insight_issues = [gate_issue] if gate_issue else []

        # 3. Insight candidate (only when the gate says speak).
        candidate = None
        if speak:
            candidate, candidate_issues = validate_legacy_candidate(root_data, mapping)
            insight_issues.extend(candidate_issues)

        # 4. Domain channels — validated independently of insight validity.
        channels, domain_issues = validate_domain_channels(result, mapping)

        # 5. Decide (D-LR).
        decision = decide_legacy(speak, insight_issues, domain_issues, channels.has_domain())
        response.acceptance_status = decision.status
        for issue in insight_issues + domain_issues:
            response.diagnostics.append(self._diagnostic(
                execution_id, issue.code, issue.field_path, issue.classification))
        if decision.status == "rejected":
            return  # nothing staged; usage + diagnostics already on the response

        # 6. Stage the accepted insight (legacy coercions A-3 / S-1 preserved).
        if decision.emit_insight and candidate is not None:
            conf_key = mapping.get("confidence_field", "confidence")
            insight = self.create_insight(
                content=candidate.content,
                type=InsightType(candidate.type_value),
                confidence=self._coerce_confidence(root_data.get(conf_key, 1.0)),
                expiry=self._coerce_expiry(root_data.get(mapping.get("expiry_field", "expiry"))),
                action_label=self._coerce_action_label(
                    root_data.get(mapping.get("action_label_field", "action_label"))),
            )
            insight.metadata = candidate.metadata
            response.insights.append(insight)

        # 7. Stage domain channels. On partial acceptance the action-bearing
        #    data sidecar is withheld and the disposition is reported.
        self._stage_channels(channels, context, working_memory, response)
        if decision.status == "partial":
            withheld = ["data"] if channels.data is not None else []
            response.diagnostics.append(self._diagnostic(
                execution_id, "partial_legacy_response", "$",
                retained_channels=channels.retained_names(), withheld_channels=withheld))
        elif channels.data is not None:
            data_key = mapping.get("data_key", mapping.get("data_field"))
            response.data[data_key] = channels.data

    def _stage_channels(self, ch: DomainChannels, context: AgentContext,
                        working_memory: Dict[str, Any], response: AgentResponse) -> None:
        """Copy shape-validated channels onto the response. No durable writes."""
        # Legacy state_field: the memory alias stages a MERGED view (committed
        # memory + this turn's updates) — it no longer touches private_state.
        if ch.state:
            if ch.state_is_memory:
                staged = dict(working_memory)
                staged.update(ch.state)
                response.state_updates[f"memory_{self.config.id}"] = staged
            else:
                response.state_updates = dict(ch.state)

        if ch.events:
            current_time = self._session_now(context)  # A-2: session-relative
            for evt in ch.events:
                if isinstance(evt, dict):
                    response.events.append(Event(
                        name=evt.get("name", ""),
                        payload=evt.get("payload") or evt.get("data", {}),
                        source_agent=self.config.id,
                        timestamp=current_time,
                        id=evt.get("id"),
                    ))
                elif isinstance(evt, str):
                    response.events.append(Event(
                        name=evt, payload={}, source_agent=self.config.id,
                        timestamp=current_time,
                    ))

        if ch.variable_updates:
            response.variable_updates.update(ch.variable_updates)

        for queue_name, items in ch.queue_pushes.items():
            response.queue_pushes.setdefault(queue_name, []).extend(items)

        if ch.facts:
            current_time = self._session_now(context)
            for f in ch.facts:
                response.facts.append(Fact(
                    type=f.get("type", "unknown"),
                    key=f.get("key"),
                    value=f.get("value"),
                    confidence=f.get("confidence", 1.0),
                    source_agent=self.config.id,
                    timestamp=current_time,
                ))

        if ch.memory_updates:
            response.memory_updates.update(ch.memory_updates)
