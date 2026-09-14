"""Unit tests for core/insight_validation.py (XUBB-ITC-1, G0 legacy safety).

Pure-function tests over plain dicts. Engine-level behaviour (what actually
commits, which callbacks fire) lives in tests/test_engine_boundary_g0.py.
Every rule carries a negative control that would pass under the superseded
behaviour (truthiness gates, unknown → suggestion) and therefore fails here
if that behaviour is restored.
"""
import math

import pytest

from xubb_agents.core import insight_validation as iv
from xubb_agents.core.insight_validation import (
    DIAGNOSTIC_CODES, GATE_MODES, HOST_DEFAULT_SUPPORTED_TYPES, MISSING,
    Issue, bounded, evaluate_typed_gate,
    validate_domain_channels, validate_ui_actions,
)
from xubb_agents.core.output_format import resolve as resolve_format

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
    """3.1.0: the gate is DECLARED by the format contract and evaluated in one
    place. These are the same rules ``evaluate_gate`` asserted, on the evaluator
    that survives."""

    def test_true_speaks(self):
        speak, issue = evaluate_typed_gate("boolean", True, {"content": "x"})
        assert speak is True and issue is None

    def test_false_is_valid_silence(self):
        speak, issue = evaluate_typed_gate("boolean", False, None)
        assert speak is False and issue is None

    @pytest.mark.parametrize("value", ["true", "false", "yes", 1, 0, 1.0, [], {}, None])
    def test_non_boolean_values_are_invalid_never_speech(self, value):
        """NEGATIVE CONTROL for raw truthiness: "true"/"false"/1 would all have
        spoken under bool(value) — they must be invalid_gate and silent."""
        speak, issue = evaluate_typed_gate("boolean", value, {"content": "x"})
        assert speak is False
        assert issue is not None and issue.code == "invalid_gate"
        assert issue.field_path == "has_insight"

    def test_missing_required_gate_is_invalid(self):
        speak, issue = evaluate_typed_gate("boolean", MISSING, {"content": "x"})
        assert speak is False
        assert issue.code == "invalid_gate" and issue.classification == "missing"


class TestRootPresenceGate:
    """The compatibility adapters gate on presence; the evaluator turns that into
    the canonical Boolean decision."""

    @pytest.mark.parametrize("root", [MISSING, None, {}])
    def test_absent_null_empty_root_is_silence(self, root):
        speak, issue = evaluate_typed_gate("root_presence", MISSING, root)
        assert speak is False and issue is None

    def test_nonempty_object_speaks(self):
        speak, issue = evaluate_typed_gate("root_presence", MISSING, {"content": "x"})
        assert speak is True and issue is None

    @pytest.mark.parametrize("root", ["text", 3, ["a"], True])
    def test_other_root_types_are_invalid(self, root):
        speak, issue = evaluate_typed_gate("root_presence", MISSING, root)
        assert speak is False and issue.code == "invalid_gate"


class TestRetiredGateModes:
    """AMENDED CONTRACT (3.1.0, GATELESS-SILENCE). ``content_presence`` and
    ``gateless`` were inferred modes for user-authored schemas; with every agent
    on a named format whose gate is declared, they cannot arise, and the
    functions that implemented them are gone rather than left to look supported.
    """

    def test_only_two_declared_gate_kinds_remain(self):
        assert GATE_MODES == ("boolean", "root_presence")

    def test_the_inference_helpers_are_gone_not_dormant(self):
        """NEGATIVE CONTROL: if either is reintroduced, a mapping could once more
        declare a gate the generated prompt knows nothing about (F2a/F2b)."""
        assert not hasattr(iv, "resolve_gate_mode")
        assert not hasattr(iv, "evaluate_gate")

    @pytest.mark.parametrize("mode", ["content_presence", "gateless", "state_only"])
    def test_a_retired_mode_never_speaks(self, mode):
        speak, issue = evaluate_typed_gate(mode, True, {"content": "spam"})
        assert speak is False


# ---------------------------------------------------------------------------
# Type labels (spec §8.6) — ITC-06.FW


# ---------------------------------------------------------------------------

class TestDomainChannels:
    """Channels are bound by the FORMAT CONTRACT; the mapping is no longer an
    authority, so these pass the spec the parser actually uses."""
    V2 = resolve_format("default_v2")          # the five standard channels
    RAW = resolve_format("v2_raw")             # state_snapshot -> variable_updates
    UI = resolve_format("ui_control")          # state_snapshot + ui_actions
    FLAT = resolve_format("default")           # private memory only
    CANON = resolve_format("insight_v1")

    def test_absent_channels_are_empty_and_valid(self):
        ch, issues = validate_domain_channels({"has_insight": False}, self.V2)
        assert issues == [] and not ch.has_domain() and ch.retained_names() == []

    def test_valid_channels_are_retained(self):
        result = {"events": ["q_detected", {"name": "x", "payload": {"a": 1}}],
                  "variable_updates": {"phase": "demo"}, "queue_pushes": {"q": [1, 2]},
                  "facts": [{"type": "budget", "value": 5, "confidence": 0.5}],
                  "memory_updates": {"seen": True}}
        ch, issues = validate_domain_channels(result, self.V2)
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
        ch, issues = validate_domain_channels({field: value}, self.V2)
        assert any(i.code == "invalid_domain_payload" and i.fatal for i in issues)

    def test_nan_fact_confidence_is_fatal(self):
        _, issues = validate_domain_channels({"facts": [{"type": "b", "confidence": math.nan}]}, self.V2)
        assert any(i.code == "invalid_domain_payload" for i in issues)

    def test_reserved_sys_write_in_variables_is_fatal(self):
        ch, issues = validate_domain_channels({"variable_updates": {"sys.turn_count": 99, "ok": 1}}, self.V2)
        codes = [(i.code, i.field_path, i.fatal) for i in issues]
        assert ("reserved_state_write", "variable_updates.sys.turn_count", True) in codes

    def test_reserved_sys_write_in_a_renamed_variable_channel_is_fatal(self):
        _, issues = validate_domain_channels({"state_snapshot": {"sys.session_id": "x"}}, self.RAW)
        assert any(i.code == "reserved_state_write" for i in issues)

    def test_private_memory_channel_stages_the_scratchpad(self):
        ch, issues = validate_domain_channels({"memory_updates": {"seen": 1}}, self.FLAT)
        assert issues == [] and ch.state == {"seen": 1} and ch.state_is_memory

    def test_sidecar_is_captured_but_never_counts_as_domain(self):
        auth = {"flash_zone": {"flash": {"required": [], "optional": [], "allow_additional": True}}}
        ch, issues = validate_domain_channels(
            {"ui_actions": [{"target_widget": "flash_zone", "action": "flash", "payload": {}}]},
            self.UI, widget_authorization=auth)
        assert issues == []
        assert ch.data == [{"target_widget": "flash_zone", "action": "flash", "payload": {}}]
        assert not ch.has_domain() and "data" not in ch.retained_names()

    # -- the F4 rule: permissions do not depend on the gate ------------------
    @pytest.mark.parametrize("body", [
        {"has_insight": False, "events": [{"name": "x", "payload": {}}]},
        {"has_insight": True, "events": [{"name": "x", "payload": {}}]},
    ])
    def test_an_undeclared_channel_is_refused_under_either_gate(self, body):
        _, issues = validate_domain_channels(body, self.FLAT)
        assert [(i.code, i.field_path) for i in issues] == [("undeclared_channel", "events")]

    def test_negative_control_the_same_channel_passes_where_it_is_declared(self):
        """NEGATIVE CONTROL: the rule must be the FORMAT's binding, not a blanket
        ban — the identical body is valid on a format that declares events."""
        _, issues = validate_domain_channels(
            {"has_insight": False, "events": [{"name": "x", "payload": {}}]}, self.V2)
        assert issues == []

    def test_an_unknown_top_level_key_is_refused_on_a_nested_envelope(self):
        _, issues = validate_domain_channels({"has_insight": False, "surprise": 1}, self.CANON)
        assert [(i.code, i.classification) for i in issues] == [("invalid_field", "unknown_envelope_key")]

    def test_a_flat_envelope_leaves_its_insight_fields_to_the_candidate_validator(self):
        """NEGATIVE CONTROL for the rule above: on a flat format the insight
        fields legitimately sit at the top level, so the envelope check must not
        claim them."""
        _, issues = validate_domain_channels({"has_insight": True, "content": "x", "type": "fact"}, self.FLAT)
        assert issues == []


class TestUiActionContract:
    AUTH = {"goals_widget": {"update": {"required": ["goal_id"], "optional": ["done"],
                                        "allow_additional": False}}}

    def ok(self, **over):
        action = {"target_widget": "goals_widget", "action": "update", "payload": {"goal_id": "g1"}}
        action.update(over)
        return [action]

    def test_a_declared_action_passes(self):
        actions, issues = validate_ui_actions(self.ok(), authorization=self.AUTH)
        assert issues == [] and actions == self.ok()

    @pytest.mark.parametrize("raw", ["a string", 3, {"target_widget": "goals_widget"}])
    def test_a_non_array_is_invalid(self, raw):
        actions, issues = validate_ui_actions(raw, authorization=self.AUTH)
        assert actions is None and issues[0].code == "invalid_ui_action"

    @pytest.mark.parametrize("item", [
        "not an object", {"nonsense": True}, {"target_widget": "goals_widget", "action": "update"},
        {"target_widget": "", "action": "update", "payload": {}},
        {"target_widget": "goals_widget", "action": "", "payload": {}},
        {"target_widget": "goals_widget", "action": "update", "payload": "not an object"},
        {"target_widget": "goals_widget", "action": "update", "payload": {}, "extra": 1},
    ])
    def test_a_malformed_item_is_invalid(self, item):
        actions, issues = validate_ui_actions([item], authorization=self.AUTH)
        assert actions is None and issues[0].code == "invalid_ui_action"

    def test_missing_declarations_authorize_nothing(self):
        actions, issues = validate_ui_actions(self.ok(), authorization={})
        assert actions is None
        assert (issues[0].code, issues[0].classification) == ("unauthorized_ui_action", "no_widgets_declared")

    @pytest.mark.parametrize("over,classification", [
        ({"target_widget": "sentiment_meter"}, "unknown_target"),
        ({"action": "self_destruct"}, "unknown_action"),
        ({"payload": {}}, "missing_payload_key:goal_id"),
        ({"payload": {"goal_id": "g1", "sneaky": 1}}, "unexpected_payload_key:sneaky"),
    ])
    def test_an_unauthorized_action_is_refused_with_the_rule_that_failed(self, over, classification):
        actions, issues = validate_ui_actions(self.ok(**over), authorization=self.AUTH)
        assert actions is None
        assert (issues[0].code, issues[0].classification) == ("unauthorized_ui_action", classification)

    def test_shape_precedes_authorization(self):
        """A malformed item never reaches the declarations — one diagnostic, and
        it names the shape failure."""
        actions, issues = validate_ui_actions([{"nonsense": 1}], authorization={})
        assert [i.code for i in issues] == ["invalid_ui_action"]

    def test_the_host_hook_can_narrow_but_runs_last(self):
        seen = []

        def validator(action):
            seen.append(action)
            return "payload_rejected_by_host"

        actions, issues = validate_ui_actions(self.ok(), authorization=self.AUTH, validator=validator)
        assert seen and actions is None
        assert (issues[0].code, issues[0].classification) == ("unauthorized_ui_action", "payload_rejected_by_host")

    def test_a_raising_hook_rejects_rather_than_crashing_the_turn(self):
        def boom(action):
            raise RuntimeError("bad hook")

        actions, issues = validate_ui_actions(self.ok(), authorization=self.AUTH, validator=boom)
        assert actions is None and issues[0].classification == "validator_error:RuntimeError"

    def test_an_empty_array_is_no_proposal(self):
        actions, issues = validate_ui_actions([], authorization={})
        assert actions is None and issues == []


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
                    "completion_unknown",
                    # 3.1.0 output-format consolidation
                    "undeclared_channel", "invalid_ui_action", "unauthorized_ui_action"}
        assert required <= set(DIAGNOSTIC_CODES)

    def test_issue_rejects_unknown_code(self):
        with pytest.raises(ValueError):
            Issue("made_up_code")

    def test_bounded_never_returns_raw_text_beyond_limit(self):
        assert bounded("a" * 200) == "a" * 64
        assert bounded({"k": "v"}) == "dict"
        assert bounded(None) is None
