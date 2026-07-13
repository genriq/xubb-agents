"""
Regression tests for DynamicAgent v2.2 hardening items.

Covers:
- S-1: `expiry` / `action_label` requested by schemas but never parsed.
- A-2: Event/Fact timestamps must be session-relative (INV-13), not wall-clock.
- A-3: LLM-supplied `confidence` must be coerced/clamped to [0,1] before it
       reaches AgentInsight (ge=0, le=1), defaulting to 1.0 on failure.

Fixtures are LOCAL to this file (no conftest edits). The LLM is mocked so no
network is hit.
"""

import asyncio
import time

import pytest

from xubb_agents.library.dynamic import DynamicAgent
from xubb_agents.core.models import (
    AgentContext,
    TranscriptSegment,
    TriggerType,
)


# ---------------------------------------------------------------------------
# Local test helpers / fixtures
# ---------------------------------------------------------------------------

class FakeLLM:
    """Minimal stand-in for the engine-injected LLM client.

    `generate_json` returns a pre-canned dict, mimicking a parsed JSON response.
    """

    def __init__(self, result):
        self._result = result
        self.calls = []

    async def generate_json(self, model=None, messages=None, **kwargs):
        self.calls.append({"model": model, "messages": messages})
        return self._result


def make_agent(result, *, output_format="default_v2", config_extra=None):
    """Build a DynamicAgent with a fake LLM that returns `result`."""
    config = {
        "id": "agent_test",
        "name": "Test Agent",
        "text": "You are a test agent.",
        "output_format": output_format,
        "trigger_config": {"cooldown": 0},
    }
    if config_extra:
        config.update(config_extra)
    agent = DynamicAgent(config)
    agent.llm = FakeLLM(result)
    return agent


def make_context(segments=None, **overrides):
    """Build a minimal AgentContext.

    Segment timestamps are session-relative seconds (the documented convention).
    """
    if segments is None:
        segments = [
            TranscriptSegment(speaker="USER", text="Hello", timestamp=1.0),
            TranscriptSegment(speaker="USER", text="What's the budget?", timestamp=42.0),
        ]
    params = dict(
        session_id="sess_1",
        recent_segments=segments,
        trigger_type=TriggerType.TURN_BASED,
    )
    params.update(overrides)
    return AgentContext(**params)


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# A-3 — confidence coercion / clamping
# ---------------------------------------------------------------------------

class TestConfidenceCoercion:
    def test_coerce_confidence_clamps_above_one(self):
        assert DynamicAgent._coerce_confidence(1.5) == 1.0

    def test_coerce_confidence_clamps_below_zero(self):
        assert DynamicAgent._coerce_confidence(-0.3) == 0.0

    def test_coerce_confidence_non_numeric_defaults_to_one(self):
        assert DynamicAgent._coerce_confidence("high") == 1.0

    def test_coerce_confidence_none_defaults_to_one(self):
        assert DynamicAgent._coerce_confidence(None) == 1.0

    def test_coerce_confidence_numeric_string_passes(self):
        assert DynamicAgent._coerce_confidence("0.42") == pytest.approx(0.42)

    def test_coerce_confidence_in_range_unchanged(self):
        assert DynamicAgent._coerce_confidence(0.73) == pytest.approx(0.73)

    def test_out_of_range_confidence_yields_valid_insight(self):
        """The headline A-3 regression: 1.5 must NOT produce a validation ERROR."""
        result = {"has_insight": True, "content": "Budget looks tight", "confidence": 1.5}
        agent = make_agent(result)
        resp = run(agent.evaluate(make_context()))
        assert len(resp.insights) == 1
        insight = resp.insights[0]
        assert insight.confidence == 1.0
        # Not an ERROR insight — the good insight survived.
        assert insight.content == "Budget looks tight"

    def test_string_confidence_yields_valid_insight(self):
        result = {"has_insight": True, "content": "Note this", "confidence": "very high"}
        agent = make_agent(result)
        resp = run(agent.evaluate(make_context()))
        assert len(resp.insights) == 1
        assert resp.insights[0].confidence == 1.0


# ---------------------------------------------------------------------------
# S-1 — expiry / action_label parse-through
# ---------------------------------------------------------------------------

class TestExpiryActionLabel:
    def test_v2_raw_expiry_reaches_insight(self):
        """v2_raw schema instructs the model to return `expiry`; it must land."""
        result = {
            "insight": {
                "type": "warning",
                "content": "Time-sensitive",
                "confidence": 0.8,
                "expiry": 30,
            }
        }
        agent = make_agent(result, output_format="v2_raw")
        resp = run(agent.evaluate(make_context()))
        assert len(resp.insights) == 1
        assert resp.insights[0].expiry == 30

    def test_action_label_reaches_insight(self):
        result = {
            "has_insight": True,
            "content": "Consider this",
            "action_label": "Apply",
        }
        agent = make_agent(result)
        resp = run(agent.evaluate(make_context()))
        assert len(resp.insights) == 1
        assert resp.insights[0].action_label == "Apply"

    def test_missing_expiry_uses_model_default(self):
        """No expiry supplied → AgentInsight default (15) stands."""
        result = {"has_insight": True, "content": "Plain insight"}
        agent = make_agent(result)
        resp = run(agent.evaluate(make_context()))
        assert len(resp.insights) == 1
        assert resp.insights[0].expiry == 15
        assert resp.insights[0].action_label is None

    def test_bad_expiry_does_not_crash_insight(self):
        """Non-numeric / non-positive expiry falls back to the default, never crashes."""
        result = {
            "insight": {
                "type": "suggestion",
                "content": "Resilient",
                "expiry": "soon",
            }
        }
        agent = make_agent(result, output_format="v2_raw")
        resp = run(agent.evaluate(make_context()))
        assert len(resp.insights) == 1
        assert resp.insights[0].expiry == 15  # default applied

    def test_coerce_expiry_helpers(self):
        assert DynamicAgent._coerce_expiry(None) is None
        assert DynamicAgent._coerce_expiry("soon") is None
        assert DynamicAgent._coerce_expiry(0) is None
        assert DynamicAgent._coerce_expiry(-5) is None
        assert DynamicAgent._coerce_expiry("20") == 20
        assert DynamicAgent._coerce_expiry(12.7) == 12

    def test_coerce_action_label_helpers(self):
        assert DynamicAgent._coerce_action_label(None) is None
        assert DynamicAgent._coerce_action_label("   ") is None
        assert DynamicAgent._coerce_action_label("  Go  ") == "Go"


# ---------------------------------------------------------------------------
# A-2 — session-relative timestamps (INV-13)
# ---------------------------------------------------------------------------

class TestSessionRelativeTimestamps:
    def test_event_timestamp_is_session_relative_not_epoch(self):
        result = {
            "has_insight": False,
            "events": [{"name": "question_detected", "payload": {}}],
        }
        agent = make_agent(result)
        # Latest segment timestamp = 42.0 → that's "now" in session-relative seconds.
        resp = run(agent.evaluate(make_context()))
        assert len(resp.events) == 1
        ts = resp.events[0].timestamp
        assert ts == 42.0
        # Definitely not a wall-clock epoch.
        assert ts < 1_000_000_000

    def test_fact_timestamp_is_session_relative_not_epoch(self):
        result = {
            "has_insight": False,
            "facts": [{"type": "budget", "key": "primary", "value": 50000, "confidence": 0.9}],
        }
        agent = make_agent(result)
        resp = run(agent.evaluate(make_context()))
        assert len(resp.facts) == 1
        ts = resp.facts[0].timestamp
        assert ts == 42.0
        assert ts < 1_000_000_000

    def test_no_segments_falls_back_to_zero_not_epoch(self):
        """Documented A-2 limitation: empty window → 0.0, never wall-clock."""
        result = {
            "has_insight": False,
            "events": [{"name": "tick", "payload": {}}],
        }
        agent = make_agent(result)
        before = time.time()
        resp = run(agent.evaluate(make_context(segments=[])))
        assert len(resp.events) == 1
        ts = resp.events[0].timestamp
        assert ts == 0.0
        # Crucially, it is NOT an epoch close to wall-clock.
        assert ts < before

    def test_session_now_uses_max_segment_timestamp(self):
        ctx = make_context(segments=[
            TranscriptSegment(speaker="USER", text="a", timestamp=5.0),
            TranscriptSegment(speaker="USER", text="b", timestamp=3.0),
            TranscriptSegment(speaker="USER", text="c", timestamp=9.5),
        ])
        agent = make_agent({"has_insight": False})
        assert agent._session_now(ctx) == 9.5


# ---------------------------------------------------------------------------
# T-1 — B1: subscribed_events auto-adds TriggerType.EVENT
# ---------------------------------------------------------------------------

class TestEventTriggerAutoAdd:
    def test_dynamic_agent_auto_adds_event_trigger_type(self):
        """B1 convenience: a DynamicAgent created with `subscribed_events`
        auto-adds TriggerType.EVENT even when the mode is the default
        (turn_based), so the engine can route events to it without the author
        having to also list "event" in trigger_config.mode."""
        agent = make_agent(
            {"has_insight": False},
            config_extra={
                "trigger_config": {
                    "cooldown": 0,
                    "subscribed_events": ["question_detected"],
                }
            },
        )
        assert TriggerType.EVENT in agent.config.trigger_types
        # The default turn_based trigger is still present (auto-add, not replace).
        assert TriggerType.TURN_BASED in agent.config.trigger_types
        assert agent.config.subscribed_events == ["question_detected"]

    def test_no_subscribed_events_does_not_add_event_trigger(self):
        """Guard: without subscribed_events, EVENT is NOT auto-added."""
        agent = make_agent({"has_insight": False})
        assert TriggerType.EVENT not in agent.config.trigger_types

    def test_event_trigger_not_duplicated_when_mode_already_event(self):
        """If the author already declared mode=event AND subscribed_events,
        EVENT appears exactly once (no duplicate from the auto-add)."""
        agent = make_agent(
            {"has_insight": False},
            config_extra={
                "trigger_config": {
                    "cooldown": 0,
                    "mode": "event",
                    "subscribed_events": ["question_detected"],
                }
            },
        )
        assert agent.config.trigger_types.count(TriggerType.EVENT) == 1


# ---------------------------------------------------------------------------
# T-1 — D1: assembled prompt has no leading-whitespace / blank-section bloat
# ---------------------------------------------------------------------------

class TestPromptAssembly:
    def _captured_system_prompt(self, agent):
        """Run one evaluation and return the system message the agent built."""
        run(agent.evaluate(make_context()))
        assert agent.llm.calls, "LLM was not invoked"
        messages = agent.llm.calls[-1]["messages"]
        system = next(m["content"] for m in messages if m["role"] == "system")
        return system

    def test_prompt_has_no_leading_whitespace(self):
        """D1: the assembled system prompt must not start with whitespace/blank
        lines, and assembly must never join in an empty/whitespace-only section
        (blank-section bloat). Sections are joined with "\\n\\n"; we assert each
        joined part carries real content."""
        agent = make_agent({"has_insight": False})
        system = self._captured_system_prompt(agent)

        # No leading whitespace / blank lines: the D1 target is that section
        # assembly must not prepend empty/whitespace-only sections.
        assert system == system.lstrip(), "prompt has leading whitespace"
        assert not system.startswith("\n"), "prompt starts with a blank line"

        # No blank-section bloat: every "\n\n"-joined part has real content
        # (an empty optional section — user_context, language, rag, trigger —
        # being appended unguarded would surface here as a whitespace-only part).
        parts = system.split("\n\n")
        empty_parts = [i for i, p in enumerate(parts) if p.strip() == ""]
        assert empty_parts == [], (
            f"prompt has blank-section bloat at joined part(s) {empty_parts}"
        )

    def test_prompt_includes_core_sections(self):
        """Sanity: the core sections are present and in order so the
        no-whitespace assertion isn't passing on an empty prompt."""
        agent = make_agent({"has_insight": False})
        system = self._captured_system_prompt(agent)
        assert "You are a test agent." in system
        assert "[YOUR MEMORY / SCRATCHPAD]" in system
        # default_v2 ships a json_instruction (the OUTPUT FORMAT block).
        assert "has_insight" in system

    def test_prompt_has_no_blank_sections_with_user_context(self):
        """QW-3 (SPEC_LLM_MODERN_MODELS): a set user_context must not create
        blank-section bloat. The section was built as f"{user_context}\\n\\n"
        and then "\\n\\n"-joined with the other parts, which yielded an empty
        joined part whenever user_context was set — invisible to the D1 sweep
        above only because its fixture omits user_context."""
        agent = make_agent({"has_insight": False})
        run(agent.evaluate(make_context(user_context="[USER PROFILE]\nRole: AE.")))
        assert agent.llm.calls, "LLM was not invoked"
        messages = agent.llm.calls[-1]["messages"]
        system = next(m["content"] for m in messages if m["role"] == "system")

        assert "[USER PROFILE]" in system, "user_context section missing"
        parts = system.split("\n\n")
        empty_parts = [i for i, p in enumerate(parts) if p.strip() == ""]
        assert empty_parts == [], (
            f"user_context created blank joined part(s) {empty_parts}"
        )


# ---------------------------------------------------------------------------
# A-1 (INV-11) — gate-less schema silence contract
# ---------------------------------------------------------------------------

def make_gateless_agent(result, *, mapping=None, instruction="", name="Gateless Agent"):
    """Build a DynamicAgent then override its schema to simulate a custom
    user-authored gate-less schema (no schema file needed — we patch the
    already-loaded mapping/instruction directly, mirroring what _load_schema
    would have produced for such a JSON)."""
    agent = make_agent(result)
    agent.mapping = mapping if mapping is not None else {
        "content_field": "content",
        "type_field": "type",
    }
    agent.json_instruction = instruction
    return agent


class TestGatelessSilenceContract:
    def test_gateless_rootless_schema_stays_silent_by_default(self):
        """A-1 core: a schema with NO check_field and NO root_key must NOT
        emit an insight every turn just because content is present. The
        documented default policy is silence."""
        result = {"content": "I would spam this every turn", "type": "suggestion"}
        agent = make_gateless_agent(result)
        resp = run(agent.evaluate(make_context()))
        assert resp.insights == [], "gate-less schema must default to silence (INV-11)"

    def test_gateless_schema_speaks_when_opted_in(self):
        """A schema author can explicitly opt into 'content ⇒ speak' via
        speak_without_gate: true — then content present DOES emit."""
        result = {"content": "Intentional speech", "type": "suggestion"}
        agent = make_gateless_agent(
            result,
            mapping={
                "content_field": "content",
                "type_field": "type",
                "speak_without_gate": True,
            },
        )
        resp = run(agent.evaluate(make_context()))
        assert len(resp.insights) == 1
        assert resp.insights[0].content == "Intentional speech"

    def test_gated_schema_unaffected_speaks_when_true(self):
        """default_v2 (check_field=has_insight) is UNAFFECTED: has_insight=True
        still emits."""
        result = {"has_insight": True, "content": "Real insight"}
        agent = make_agent(result)  # default_v2
        resp = run(agent.evaluate(make_context()))
        assert len(resp.insights) == 1
        assert resp.insights[0].content == "Real insight"

    def test_gated_schema_unaffected_silent_when_false(self):
        """default_v2 with has_insight=False stays silent — unchanged."""
        result = {"has_insight": False, "content": "Should be suppressed"}
        agent = make_agent(result)
        resp = run(agent.evaluate(make_context()))
        assert resp.insights == []

    def test_rootkey_schema_unaffected_speaks_when_present(self):
        """v2_raw (root_key=insight, no check_field) still speaks by presence
        of a non-empty root object — unchanged by A-1."""
        result = {"insight": {"type": "warning", "content": "Present"}}
        agent = make_agent(result, output_format="v2_raw")
        resp = run(agent.evaluate(make_context()))
        assert len(resp.insights) == 1
        assert resp.insights[0].content == "Present"

    def test_rootkey_schema_silent_when_root_empty(self):
        """v2_raw with an empty/absent root object stays silent — unchanged."""
        result = {"insight": {}}
        agent = make_agent(result, output_format="v2_raw")
        resp = run(agent.evaluate(make_context()))
        assert resp.insights == []


class TestGatelessLoadTimeWarning:
    def test_warning_fires_on_gate_field_in_instruction_but_no_check_field(self, caplog):
        """A-1 load-time guard: a gate-less, rootless schema whose instruction
        references a gate field (e.g. has_insight) must WARN at load time —
        this is the misconfiguration that silently loses the silence contract."""
        agent = make_agent({"has_insight": False})
        # Simulate the misconfigured custom schema: instruction mentions the
        # gate, but the mapping forgot to wire check_field.
        agent.json_instruction = (
            'Return {"has_insight": boolean, "content": "..."}'
        )
        agent.mapping = {"content_field": "content"}

        with caplog.at_level("WARNING"):
            agent._warn_on_gateless_misconfig("custom_gateless")

        assert any(
            "gate-less" in rec.message.lower() and "has_insight" in rec.message
            for rec in caplog.records
        ), "expected a load-time gate-less misconfiguration warning"

    def test_no_warning_when_check_field_present(self, caplog):
        """A properly gated schema (default_v2 references has_insight AND wires
        check_field) must NOT warn."""
        agent = make_agent({"has_insight": False})  # default_v2
        with caplog.at_level("WARNING"):
            agent._warn_on_gateless_misconfig("default_v2")
        assert not any(
            "gate-less" in rec.message.lower() for rec in caplog.records
        ), "gated schema must not trigger the A-1 warning"

    def test_no_warning_when_rootkey_present(self, caplog):
        """A root-keyed gate-less schema (v2_raw) is properly gated by presence
        and must NOT warn."""
        agent = make_agent({"insight": {}}, output_format="v2_raw")
        with caplog.at_level("WARNING"):
            agent._warn_on_gateless_misconfig("v2_raw")
        assert not any(
            "gate-less" in rec.message.lower() for rec in caplog.records
        )

    def test_no_warning_when_gateless_but_instruction_has_no_gate_field(self, caplog):
        """A deliberately gate-less schema whose prose does NOT promise a gate
        is a valid (opt-in) design — no warning, to avoid noise."""
        agent = make_agent({"content": "x"})
        agent.json_instruction = 'Return {"content": "...", "type": "..."}'
        agent.mapping = {"content_field": "content", "speak_without_gate": True}
        with caplog.at_level("WARNING"):
            agent._warn_on_gateless_misconfig("opted_in")
        assert not any(
            "gate-less" in rec.message.lower() for rec in caplog.records
        )


# ---------------------------------------------------------------------------
# Interval trigger config: trigger_config.trigger_interval must reach
# AgentConfig.trigger_interval — previously never parsed, so interval-mode
# host-authored agents could never fire (the host gates on `if interval and ...`).
# ---------------------------------------------------------------------------

class TestIntervalTriggerConfig:
    def test_trigger_interval_is_parsed_into_config(self):
        agent = DynamicAgent({
            "id": "iv", "name": "Interval Agent", "text": "x",
            "trigger_config": {"mode": "interval", "trigger_interval": 60},
        })
        assert TriggerType.INTERVAL in agent.config.trigger_types
        assert agent.config.trigger_interval == 60

    def test_numeric_string_interval_is_coerced(self):
        agent = DynamicAgent({
            "id": "iv", "name": "Interval Agent", "text": "x",
            "trigger_config": {"mode": "interval", "trigger_interval": "45"},
        })
        assert agent.config.trigger_interval == 45

    def test_invalid_interval_treated_as_absent_with_warning(self, caplog):
        with caplog.at_level("WARNING"):
            bogus = DynamicAgent({
                "id": "iv", "name": "Interval Agent", "text": "x",
                "trigger_config": {"mode": "interval", "trigger_interval": "soon"},
            })
            negative = DynamicAgent({
                "id": "iv2", "name": "Interval Agent 2", "text": "x",
                "trigger_config": {"mode": "interval", "trigger_interval": 0},
            })
        assert bogus.config.trigger_interval is None
        assert negative.config.trigger_interval is None
        assert sum("trigger_interval" in r.message for r in caplog.records) == 2

    def test_absent_interval_stays_none(self):
        agent = DynamicAgent({
            "id": "tb", "name": "Turn Agent", "text": "x",
            "trigger_config": {"mode": "turn_based"},
        })
        assert agent.config.trigger_interval is None


class TestLegacyMemoryAliasing:
    """The legacy (default-format) memory path must emit a COPY of private_state.

    It previously assigned the live self.private_state dict by reference into
    response.state_updates, so a tracer capturing the response — or the agent's own
    next-turn mutation of private_state — would alter data already 'emitted'.
    """

    def test_legacy_memory_emitted_as_copy_not_alias(self):
        result = {
            "has_insight": True, "type": "suggestion", "message": "noted",
            "memory_updates": {"seen": "first"},
        }
        agent = make_agent(result, output_format="default")
        resp = run(agent.evaluate(make_context()))

        mem_key = f"memory_{agent.config.id}"
        emitted = resp.state_updates[mem_key]
        assert emitted == {"seen": "first"}
        # Must be a copy, not the agent's live internal state.
        assert emitted is not agent.private_state
        # A later turn mutating private_state must not change the emitted snapshot.
        agent.private_state["seen"] = "mutated_later"
        agent.private_state["extra"] = "later"
        assert emitted == {"seen": "first"}


# ---------------------------------------------------------------------------
# QW-2 (SPEC_LLM_MODERN_MODELS) — single default-model constant
# ---------------------------------------------------------------------------

class TestQW2DefaultModelConstant:
    """QW-2: the default model string lives in ONE framework constant.

    Both default paths (AgentConfig's parameter default and DynamicAgent's
    config-parse fallback) must resolve to core.agent.DEFAULT_MODEL, and the
    package must export it for hosts. The VALUE stays "gpt-4o-mini" in this
    release — changing it is a separate, eval-gated decision
    (SPEC_LLM_MODERN_MODELS §3 non-goals).
    """

    def test_agent_config_default_model_is_the_constant(self):
        from xubb_agents.core.agent import DEFAULT_MODEL, AgentConfig
        assert AgentConfig(name="X").model == DEFAULT_MODEL

    def test_dynamic_agent_fallback_model_is_the_constant(self):
        from xubb_agents.core.agent import DEFAULT_MODEL
        agent = make_agent({"has_insight": False})
        assert agent.model == DEFAULT_MODEL
        assert agent.config.model == DEFAULT_MODEL

    def test_package_exports_default_model(self):
        import xubb_agents
        from xubb_agents.core.agent import DEFAULT_MODEL
        assert xubb_agents.DEFAULT_MODEL == DEFAULT_MODEL

    def test_default_model_value_unchanged_this_release(self):
        from xubb_agents.core.agent import DEFAULT_MODEL
        assert DEFAULT_MODEL == "gpt-4o-mini"


# ---------------------------------------------------------------------------
# OB-2 (SPEC_LLM_MODERN_MODELS) — duck-typed client + usage passthrough
# ---------------------------------------------------------------------------

class EnrichedFakeLLM:
    """Fake exposing the enriched generate() path (real LLMClient shape)."""

    def __init__(self, result, usage=None):
        self._result = result
        self._usage = usage
        self.calls = []

    async def generate(self, model=None, messages=None, **kwargs):
        from xubb_agents.core.llm import LLMResult
        self.calls.append({"model": model, "messages": messages})
        return LLMResult(parsed=self._result, error_category=None,
                         usage=self._usage, finish_reason="stop")


class TestOB2UsagePassthrough:
    INSIGHT = {"has_insight": True, "content": "Budget is tight", "confidence": 0.9}

    def test_generate_json_only_fake_still_yields_insights(self):
        """Duck-type fallback: a client implementing ONLY generate_json (the
        simulator's MockLLMClient shape, and every in-repo fake) keeps
        working; enrichment is simply absent."""
        agent = make_agent(dict(self.INSIGHT))
        resp = run(agent.evaluate(make_context()))
        assert resp is not None
        assert len(resp.insights) == 1
        assert resp.usage is None
        assert "usage" not in resp.debug_info

    def test_enriched_client_populates_usage(self):
        usage = {"prompt_tokens": 11, "completion_tokens": 7, "reasoning_tokens": 3}
        agent = make_agent(dict(self.INSIGHT))
        agent.llm = EnrichedFakeLLM(dict(self.INSIGHT), usage=usage)

        resp = run(agent.evaluate(make_context()))

        assert resp is not None
        assert len(resp.insights) == 1
        assert resp.usage == usage
        assert resp.debug_info["usage"] == usage
        # debug_info shape contract (simulator/tracer): core keys unchanged.
        assert set(resp.debug_info) >= {"prompt_messages", "model", "llm_output"}

    def test_usage_serializes_but_debug_info_does_not(self):
        """AgentResponse.usage is first-class because debug_info is
        exclude=True — hosts billing per agent need it to survive dumps."""
        usage = {"prompt_tokens": 2, "completion_tokens": 1}
        agent = make_agent(dict(self.INSIGHT))
        agent.llm = EnrichedFakeLLM(dict(self.INSIGHT), usage=usage)

        resp = run(agent.evaluate(make_context()))
        dumped = resp.model_dump()

        assert dumped["usage"] == usage
        assert "debug_info" not in dumped


# ---------------------------------------------------------------------------
# RC-1/RC-2/RC-3 (SPEC_LLM_MODERN_MODELS) — per-agent reasoning config
# ---------------------------------------------------------------------------

class RecordingGenerateLLM:
    """Duck-typed enriched fake recording generate() kwargs verbatim."""

    def __init__(self, result):
        self._result = result
        self.calls = []

    async def generate(self, model=None, messages=None, **kwargs):
        from xubb_agents.core.llm import LLMResult
        self.calls.append({"model": model, "messages": messages, **kwargs})
        return LLMResult(parsed=self._result)


class StrictFakeLLM:
    """generate_json-only fake with a STRICT signature (no **kwargs) — the
    simulator's MockLLMClient shape. An unconfigured agent must drive it."""

    def __init__(self, result):
        self._result = result
        self.calls = []

    async def generate_json(self, model, messages):
        self.calls.append({"model": model, "messages": messages})
        return self._result


INSIGHT = {"has_insight": True, "content": "hi", "confidence": 0.9}


class TestRC1ReasoningConfig:
    def _agent(self, model_config):
        return make_agent(dict(INSIGHT), config_extra={"model_config": model_config})

    def test_fields_land_on_agent_config_canonically(self):
        agent = self._agent({
            "model": "gpt-5.6-luna",
            "reasoning_effort": "low",
            "timeout": 30,
            "max_tokens": 25000,
            "model_params": {"verbosity": "low"},
        })
        assert agent.config.reasoning_effort == "low"
        assert agent.config.timeout == 30.0
        assert agent.config.max_tokens == 25000
        assert agent.config.model_params == {"verbosity": "low"}

    def test_unconfigured_defaults_are_absent(self):
        agent = make_agent(dict(INSIGHT))
        assert agent.config.reasoning_effort is None
        assert agent.config.timeout is None
        assert agent.config.max_tokens is None
        assert agent.config.model_params == {}

    def test_unconfigured_agent_drives_strict_fake(self):
        """INV-15 sibling guarantee: no config -> NO extra kwargs -> a strict
        generate_json(model, messages) fake works unmodified."""
        agent = make_agent(dict(INSIGHT))
        agent.llm = StrictFakeLLM(dict(INSIGHT))
        resp = run(agent.evaluate(make_context()))
        assert resp is not None and len(resp.insights) == 1

    def test_configured_kwargs_reach_generate(self):
        agent = self._agent({
            "model": "gpt-5.6-luna",
            "reasoning_effort": "low",
            "timeout": 30,
            "max_tokens": 25000,
            "model_params": {"verbosity": "low"},
        })
        agent.llm = RecordingGenerateLLM(dict(INSIGHT))
        run(agent.evaluate(make_context()))
        call = agent.llm.calls[-1]
        assert call["reasoning_effort"] == "low"
        assert call["timeout"] == 30.0
        assert call["max_tokens"] == 25000
        assert call["extra_params"] == {"verbosity": "low"}

    def test_unconfigured_kwargs_omitted_from_generate(self):
        """INV-15: omitted config means the kwarg is ABSENT, never None."""
        agent = make_agent(dict(INSIGHT))
        agent.llm = RecordingGenerateLLM(dict(INSIGHT))
        run(agent.evaluate(make_context()))
        call = agent.llm.calls[-1]
        for key in ("reasoning_effort", "timeout", "max_tokens", "extra_params"):
            assert key not in call, f"unconfigured {key} leaked into the call"

    def test_bad_timeout_and_max_tokens_coerced_absent_with_warning(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING):
            agent = self._agent({"timeout": "fast", "max_tokens": -5})
        assert agent.config.timeout is None
        assert agent.config.max_tokens is None
        assert "timeout" in caplog.text and "max_tokens" in caplog.text


class TestRC2ModelParams:
    def test_collision_with_framework_key_raises_at_init(self):
        from xubb_agents import AgentConfigurationError
        for bad_key in ("model", "messages", "response_format",
                        "max_tokens", "max_completion_tokens",
                        "timeout", "reasoning_effort"):
            with pytest.raises(AgentConfigurationError):
                make_agent(dict(INSIGHT), config_extra={
                    "model_config": {"model_params": {bad_key: "x"}}
                })

    def test_non_dict_model_params_warned_and_absent(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING):
            agent = make_agent(dict(INSIGHT), config_extra={
                "model_config": {"model_params": "verbosity=low"}
            })
        assert agent.config.model_params == {}
        assert "model_params" in caplog.text

    def test_empty_model_params_zero_wire_diff(self):
        agent = make_agent(dict(INSIGHT), config_extra={
            "model_config": {"model_params": {}}
        })
        agent.llm = RecordingGenerateLLM(dict(INSIGHT))
        run(agent.evaluate(make_context()))
        assert "extra_params" not in agent.llm.calls[-1]
