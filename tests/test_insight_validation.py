"""Unit tests for core/insight_validation.py (XUBB-ITC-1, G0 legacy safety).

Pure-function tests over plain dicts. Engine-level behaviour (what actually
commits, which callbacks fire) lives in tests/test_engine_boundary_g0.py.
Every rule carries a negative control that would pass under the superseded
behaviour (truthiness gates, unknown → suggestion) and therefore fails here
if that behaviour is restored.
"""
import math

import pytest

from xubb_agents.core.insight_validation import (
    DIAGNOSTIC_CODES, HOST_DEFAULT_SUPPORTED_TYPES,
    Issue, bounded, resolve_gate_mode, evaluate_gate,
    validate_domain_channels,
)

# 3.0.0 note. The classes that exercised `normalize_legacy_type`,
# `validate_legacy_candidate` and `decide_legacy` directly were removed with those
# functions. The rules they asserted that SURVIVE — an unrecognised label is
# `unknown_type`, a recognised-but-disallowed one is `type_not_allowed`, and
# neither is ever silently relabelled — are asserted end-to-end on the typed path
# in `test_typed_acceptance_g1.py` (TestTypeClassification), which drives the real
# engine rather than the validator in isolation. Nothing was dropped; the coverage
# moved to the path that still exists.


# ---------------------------------------------------------------------------
# Gates (spec §8.2) — ITC-04.FW
# ---------------------------------------------------------------------------

class TestBooleanGate:
    MAPPING = {"check_field": "has_insight", "content_field": "content"}

    def test_true_speaks(self):
        speak, issue = evaluate_gate("boolean", self.MAPPING, {}, {"has_insight": True})
        assert speak is True and issue is None

    def test_false_is_valid_silence(self):
        speak, issue = evaluate_gate("boolean", self.MAPPING, {}, {"has_insight": False})
        assert speak is False and issue is None

    @pytest.mark.parametrize("value", ["true", "false", "yes", 1, 0, 1.0, [], {}, None])
    def test_non_boolean_values_are_invalid_never_speech(self, value):
        """NEGATIVE CONTROL for raw truthiness: "true"/"false"/1 would all have
        spoken under bool(value) — they must be invalid_gate and silent."""
        speak, issue = evaluate_gate("boolean", self.MAPPING, {}, {"has_insight": value})
        assert speak is False
        assert issue is not None and issue.code == "invalid_gate"
        assert issue.field_path == "has_insight"

    def test_missing_required_gate_is_invalid(self):
        speak, issue = evaluate_gate("boolean", self.MAPPING, {}, {"content": "x"})
        assert speak is False
        assert issue.code == "invalid_gate" and issue.classification == "missing"


class TestRootPresenceGate:
    MAPPING = {"root_key": "insight"}

    @pytest.mark.parametrize("result", [{}, {"insight": None}, {"insight": {}}])
    def test_absent_null_empty_root_is_silence(self, result):
        speak, issue = evaluate_gate("root_presence", self.MAPPING, result, {})
        assert speak is False and issue is None

    def test_nonempty_object_speaks(self):
        speak, issue = evaluate_gate("root_presence", self.MAPPING, {"insight": {"content": "x"}}, {"content": "x"})
        assert speak is True and issue is None

    @pytest.mark.parametrize("root", ["text", 3, ["a"], True])
    def test_other_root_types_are_invalid(self, root):
        speak, issue = evaluate_gate("root_presence", self.MAPPING, {"insight": root}, {})
        assert speak is False and issue.code == "invalid_gate"


class TestContentPresenceGate:
    """The custom1 adapter gates on its content string — declared, not truthiness."""
    MAPPING = {"check_field": "sales_tip", "content_field": "sales_tip"}

    def test_nonempty_string_speaks(self):
        speak, issue = evaluate_gate("content_presence", self.MAPPING, {}, {"sales_tip": "Ask about timing"})
        assert speak is True and issue is None

    @pytest.mark.parametrize("root", [{}, {"sales_tip": None}, {"sales_tip": ""}])
    def test_absent_null_empty_is_silence(self, root):
        speak, issue = evaluate_gate("content_presence", self.MAPPING, {}, root)
        assert speak is False and issue is None

    @pytest.mark.parametrize("value", [5, True, ["x"], {"a": 1}, "   "])
    def test_non_string_or_blank_is_invalid(self, value):
        speak, issue = evaluate_gate("content_presence", self.MAPPING, {}, {"sales_tip": value})
        assert speak is False and issue.code == "invalid_gate"


class TestGatelessModes:
    def test_gateless_and_state_only_never_speak(self):
        for mode in ("gateless", "state_only"):
            speak, issue = evaluate_gate(mode, {}, {"content": "spam"}, {"content": "spam"})
            assert speak is False and issue is None


class TestResolveGateMode:
    def test_inference_matches_a1_precedence(self):
        assert resolve_gate_mode({"check_field": "has_insight"}) == "boolean"
        assert resolve_gate_mode({"root_key": "insight"}) == "root_presence"
        assert resolve_gate_mode({"content_field": "c", "speak_without_gate": True}) == "content_presence"
        assert resolve_gate_mode({"content_field": "c"}) == "gateless"

    def test_declared_descriptor_wins_when_supported(self):
        assert resolve_gate_mode({"check_field": "sales_tip", "content_field": "sales_tip"},
                                 {"gate_mode": "content_presence"}) == "content_presence"

    def test_misdeclared_descriptor_falls_back_to_inference(self):
        """A 'boolean' declaration with no check_field can only ever read
        'missing' — the safe answer is inference, not a permanently invalid gate."""
        assert resolve_gate_mode({"content_field": "c"}, {"gate_mode": "boolean"}) == "gateless"
        assert resolve_gate_mode({"check_field": "h"}, {"gate_mode": "root_presence"}) == "boolean"


# ---------------------------------------------------------------------------
# Type labels (spec §8.6) — ITC-06.FW


# ---------------------------------------------------------------------------

class TestDomainChannels:
    MAPPING = {"state_field": "state_snapshot", "data_field": "ui_actions"}

    def test_absent_channels_are_empty_and_valid(self):
        ch, issues = validate_domain_channels({"has_insight": False}, {})
        assert issues == [] and not ch.has_domain() and ch.retained_names() == []

    def test_valid_channels_are_retained(self):
        result = {"events": ["q_detected", {"name": "x", "payload": {"a": 1}}],
                  "variable_updates": {"phase": "demo"}, "queue_pushes": {"q": [1, 2]},
                  "facts": [{"type": "budget", "value": 5, "confidence": 0.5}],
                  "memory_updates": {"seen": True}}
        ch, issues = validate_domain_channels(result, {})
        assert issues == []
        assert set(ch.retained_names()) == {"events", "variable_updates", "queue_pushes", "facts", "memory_updates"}

    @pytest.mark.parametrize("field,value", [
        ("events", "none"), ("events", [5]), ("events", [{"name": 3}]),
        ("variable_updates", ["a"]), ("queue_pushes", "q"), ("queue_pushes", {"q": "item"}),
        ("facts", "none"), ("facts", ["x"]), ("facts", [{"type": "b", "confidence": "high"}]),
        ("facts", [{"type": "b", "confidence": 1.5}]), ("facts", [{"type": 3}]),
        ("memory_updates", "remember"),
    ])
    def test_present_but_malformed_channel_is_fatal(self, field, value):
        ch, issues = validate_domain_channels({field: value}, {})
        assert any(i.code == "invalid_domain_payload" and i.fatal for i in issues)

    def test_nan_fact_confidence_is_fatal(self):
        _, issues = validate_domain_channels({"facts": [{"type": "b", "confidence": math.nan}]}, {})
        assert any(i.code == "invalid_domain_payload" for i in issues)

    def test_reserved_sys_write_in_variables_is_fatal(self):
        ch, issues = validate_domain_channels({"variable_updates": {"sys.turn_count": 99, "ok": 1}}, {})
        codes = [(i.code, i.field_path, i.fatal) for i in issues]
        assert ("reserved_state_write", "variable_updates.sys.turn_count", True) in codes

    def test_reserved_sys_write_in_generic_state_field_is_fatal(self):
        _, issues = validate_domain_channels({"state_snapshot": {"sys.session_id": "x"}}, self.MAPPING)
        assert any(i.code == "reserved_state_write" for i in issues)

    def test_memory_alias_state_field_allows_memory_keys(self):
        ch, issues = validate_domain_channels({"memory_updates": {"seen": 1}}, {"state_field": "memory_updates"})
        assert issues == [] and ch.state == {"seen": 1} and ch.state_is_memory

    def test_sidecar_is_captured_but_never_counts_as_domain(self):
        ch, issues = validate_domain_channels({"ui_actions": [{"action": "flash"}]}, self.MAPPING)
        assert issues == []
        assert ch.data == [{"action": "flash"}]
        assert not ch.has_domain() and "data" not in ch.retained_names()


# ---------------------------------------------------------------------------
# D-LR decision table — ITC-24.FW


class TestVocabulary:
    def test_the_undeclared_host_default_is_the_five_that_need_nothing_of_it(self):
        assert set(HOST_DEFAULT_SUPPORTED_TYPES) == {"suggestion", "warning", "opportunity", "fact", "praise"}
        assert "error" not in HOST_DEFAULT_SUPPORTED_TYPES

    def test_all_required_diagnostic_codes_present(self):
        required = {"invalid_gate", "inconsistent_gate", "unknown_type", "type_not_allowed", "invalid_field",
                    "invalid_metadata", "invalid_confidence", "invalid_urgency", "missing_evidence",
                    "unknown_reference", "cross_session_reference", "missing_principal",
                    "capability_unavailable", "invalid_correction_target", "correction_conflict",
                    "invalid_question_contract", "invalid_input_reference", "no_supported_insight_types",
                    "invalid_domain_payload", "reserved_state_write", "partial_legacy_response",
                    "unsupported_structured_output", "provider_schema_error",
                    "content_execution_not_allowed", "invalid_content_execution_context",
                    "content_contract_unavailable", "invalid_content_policy", "unsupported_depth",
                    "unsupported_content_format", "content_too_large", "preview_too_large",
                    "response_too_large", "content_extension_not_enabled", "incomplete_generation",
                    "completion_unknown"}
        assert required <= set(DIAGNOSTIC_CODES)

    def test_issue_rejects_unknown_code(self):
        with pytest.raises(ValueError):
            Issue("made_up_code")

    def test_bounded_never_returns_raw_text_beyond_limit(self):
        assert bounded("a" * 200) == "a" * 64
        assert bounded({"k": "v"}) == "dict"
        assert bounded(None) is None
