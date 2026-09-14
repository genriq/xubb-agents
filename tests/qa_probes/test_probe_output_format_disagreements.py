"""
QA Probe — PROBE-OF1..OF7: the seven output-format contract disagreements.

Origin:    an external assessment of 3.0.0 (commit d9a8b32), reproduced through the
           REAL engine on 2026-09-14 before any code changed. Every case below
           FAILED at that baseline in exactly the way its docstring records.
Contract:  OUTPUT-FORMAT-* (docs/CONTRACTS.yaml) /
           docs/SPEC_OUTPUT_FORMAT_CONSOLIDATION.md §2, §3.

These are escaped defects: each shipped, was documented, and in four cases was
"tested" by a test that asserted the broken behaviour. Per docs/PROCESS.md they
earn a permanent probe that drives the real engine end to end, not a unit in
isolation — the disagreements lived BETWEEN the prompt builder, the parser and
the validator, so no single unit could see them.

STATUS: ACTIVE (hard gate). DO NOT delete these probes and DO NOT xfail them. If
one starts failing, the format contract has drifted apart from its prompt or its
parser again — fix the code, not the probe.
"""
import asyncio

import pytest

from xubb_agents import (
    AgentEngine, AgentContext, Blackboard, DynamicAgent, HostInsightCapabilities,
    HostWidgetCapabilities, WidgetDeclaration, WidgetActionDeclaration,
)
from xubb_agents.core.engine import AgentConfigurationError
from xubb_agents.core.models import TranscriptSegment

ALL_NINE = ["fact", "observation", "suggestion", "warning", "opportunity", "praise",
            "reply", "correction", "question"]
ACTION = {"target_widget": "goals_widget", "action": "update", "payload": {"done": 1}}


class Fake:
    def __init__(self, body):
        self.body, self.calls = body, []

    async def generate_json(self, model=None, messages=None, **kw):
        self.calls.append({"messages": messages})
        return self.body


def ctx(widgets=False):
    caps = HostWidgetCapabilities()
    if widgets:
        caps = HostWidgetCapabilities(widgets=[WidgetDeclaration(
            target_widget="goals_widget",
            actions=[WidgetActionDeclaration(action="update", optional_payload_keys=["done"])])])
    return AgentContext(
        session_id="probe", turn_count=1, blackboard=Blackboard(), principal_id="p",
        recent_segments=[TranscriptSegment(speaker="CLIENT", text="Can we keep the date?", timestamp=1.0)],
        insight_capabilities=HostInsightCapabilities(supported_types=ALL_NINE),
        widget_capabilities=caps)


def agent(body, fmt, agent_id="probe_agent", allowed=("suggestion", "warning")):
    a = DynamicAgent({"id": agent_id, "name": agent_id, "text": "t", "output_format": fmt,
                      "trigger_config": {"cooldown": 0},
                      "insight_config": {"allowed_types": list(allowed)}})
    a.llm = Fake(body)
    return a


def run_turn(*agents, context=None):
    engine = AgentEngine(api_key="k")
    for a in agents:
        keep = a.llm
        engine.register_agent(a)
        a.llm = keep
    c = context or ctx()
    return asyncio.run(engine.process_turn(c)), c


def prompt_of(a):
    return a.llm.calls[-1]["messages"][0]["content"]


class TestProbeOF1ContentAliasDisagreement:
    """PROBE-OF1. BASELINE: `default.json` published `"message"` in its contract
    and its mapping, while the live parser read `content`. An agent authored
    against the published contract produced NO insight and two `invalid_field`
    diagnostics — the format's own documentation was the thing that broke it."""

    def test_a_body_written_against_the_published_contract_is_accepted(self):
        a = agent({"has_insight": True, "message": "Confirm the approval owner.",
                   "type": "suggestion"}, "default")
        final, _ = run_turn(a)
        assert [i.content for i in final.insights] == ["Confirm the approval owner."], \
            [d.code for d in final.diagnostics]

    def test_the_canonical_field_is_accepted_too(self):
        a = agent({"has_insight": True, "content": "Confirm the approval owner.",
                   "type": "suggestion"}, "default")
        final, _ = run_turn(a)
        assert [i.content for i in final.insights] == ["Confirm the approval owner."]

    def test_a_conflicting_body_is_refused_rather_than_silently_resolved(self):
        """NEGATIVE CONTROL: preferring one of two different values would be the
        same class of defect the alias exists to repair."""
        a = agent({"has_insight": True, "message": "one", "content": "two",
                   "type": "suggestion"}, "default")
        final, _ = run_turn(a)
        assert final.insights == []
        assert [(d.code, d.classification) for d in final.diagnostics] == \
            [("invalid_field", "content_alias_conflict")]

    def test_the_generated_prompt_names_the_field_the_parser_reads(self):
        a = agent({"has_insight": False}, "default")
        run_turn(a)
        assert '"content":' in prompt_of(a) and '"message"' not in prompt_of(a)


class TestProbeOF2StructuralOverrides:
    """PROBE-OF2. BASELINE: a mapping's `check_field` was ignored by both the
    prompt and the parser (the gate stayed `has_insight`), and a custom
    `root_key` was honoured by the PARSER while the prompt still asked for
    `insight` — so an obedient model was silenced. Overrides now control both,
    or fail at registration."""

    @pytest.mark.parametrize("override", [
        {"check_field": "should_speak"},
        {"root_key": "advice"},
        {"content_field": "tip"},
        {"events_field": "signals"},
    ])
    def test_a_structural_override_fails_at_registration(self, override):
        a = agent({"has_insight": False}, "default_v2")
        a.mapping = dict(a.mapping, **override)
        engine = AgentEngine(api_key="k")
        with pytest.raises(AgentConfigurationError, match="Structural overrides are not supported"):
            engine.register_agent(a)
        assert engine.agents == [], "registration must not partially modify the registry"

    def test_an_unknown_adapter_identifier_fails_at_registration(self):
        a = agent({"has_insight": False}, "insight_v1")
        a.descriptor = dict(a.descriptor, typed_adapter="rootv3_experimental")
        engine = AgentEngine(api_key="k")
        with pytest.raises(AgentConfigurationError, match="typed_adapter"):
            engine.register_agent(a)
        assert engine.agents == []

    def test_negative_control_an_untouched_mapping_registers(self):
        engine = AgentEngine(api_key="k")
        engine.register_agent(agent({"has_insight": False}, "default_v2"))
        assert len(engine.agents) == 1


class TestProbeOF3SpeakWithoutGate:
    """PROBE-OF3. BASELINE: `speak_without_gate` was documented in the playbook,
    the prompt guide and the technical spec, accepted by every schema loader —
    and read by nothing. It was registered as a strict xfail at 3.0.0. No
    accepted-but-ignored setting may remain."""

    def test_the_retired_option_is_refused_with_migration_guidance(self):
        a = agent({"has_insight": False}, "default")
        a.mapping = dict(a.mapping, speak_without_gate=True)
        engine = AgentEngine(api_key="k")
        with pytest.raises(AgentConfigurationError, match="speak_without_gate"):
            engine.register_agent(a)
        assert engine.agents == []

    def test_the_replacement_is_an_explicit_gate_that_actually_gates(self):
        """The guarantee that replaces it: the gate decides, in both directions."""
        speaking, _ = run_turn(agent({"has_insight": True, "insight":
                                      {"type": "suggestion", "content": "Say this."}}, "insight_v1"))
        silent, _ = run_turn(agent({"has_insight": False, "insight": None}, "insight_v1"))
        assert len(speaking.insights) == 1 and silent.insights == []


class TestProbeOF4GateDoesNotGrantWritePermission:
    """PROBE-OF4. BASELINE: `default` declares no event channel. A SILENT
    response carrying `events` was accepted and the events were COMMITTED; the
    identical key while speaking rejected the response. A speech gate decided a
    write permission."""
    BODY = {"events": [{"name": "undeclared_event", "payload": {"k": 1}}]}

    @pytest.mark.parametrize("gate", [False, True])
    def test_an_undeclared_channel_is_refused_under_either_gate(self, gate):
        body = dict(self.BODY, has_insight=gate)
        if gate:
            body.update(type="suggestion", content="Speaking.")
        final, context = run_turn(agent(body, "default", agent_id="und"))
        assert final.events == [], "an undeclared channel must never commit"
        assert "undeclared_channel" in [d.code for d in final.diagnostics]
        assert final.acceptance_by_agent["und"] == "rejected"

    @pytest.mark.parametrize("gate", [False, True])
    def test_negative_control_the_same_body_commits_where_the_channel_is_declared(self, gate):
        """The rule is the FORMAT's binding, not a blanket ban — and it is the
        same under both gates, which is the property that failed."""
        body = dict(self.BODY, has_insight=gate)
        if gate:
            body.update(type="suggestion", content="Speaking.")
        final, _ = run_turn(agent(body, "default_v2", agent_id="dec"))
        assert [e.name for e in final.events] == ["undeclared_event"]
        assert final.acceptance_by_agent["dec"].startswith("accepted")


class TestProbeOF5WidgetActionsAreValidated:
    """PROBE-OF5. BASELINE: `ui_actions` was captured with `ch.data = payload`
    and published to the host verbatim. A bare string, an item naming an unknown
    widget and an unknown action, and `[{"nonsense": true}]` were all accepted."""

    def test_a_declared_action_is_published(self):
        final, _ = run_turn(agent({"has_insight": False, "insight": None, "ui_actions": [ACTION]},
                                  "widget_control", agent_id="w"), context=ctx(widgets=True))
        assert final.data["ui_actions"] == [ACTION]
        assert final.acceptance_by_agent["w"] == "accepted_silent"

    @pytest.mark.parametrize("payload,code", [
        ("a bare string, not an array", "invalid_ui_action"),
        ([{"nonsense": True}], "invalid_ui_action"),
        ([{"target_widget": "goals_widget", "action": "update", "payload": "not-an-object"}], "invalid_ui_action"),
        ([{"target_widget": "unknown_widget", "action": "update", "payload": {}}], "unauthorized_ui_action"),
        ([{"target_widget": "goals_widget", "action": "self_destruct", "payload": {}}], "unauthorized_ui_action"),
    ])
    def test_malformed_and_unauthorized_actions_reject_the_whole_response(self, payload, code):
        body = {"has_insight": True, "insight": {"type": "suggestion", "content": "And also speak."},
                "ui_actions": payload}
        final, _ = run_turn(agent(body, "widget_control", agent_id="w"), context=ctx(widgets=True))
        assert final.data == {} and final.insights == [], "no partial commit of a defective response"
        assert code in [d.code for d in final.diagnostics]

    def test_an_undeclared_host_authorizes_nothing(self):
        final, _ = run_turn(agent({"has_insight": False, "insight": None, "ui_actions": [ACTION]},
                                  "widget_control", agent_id="w"), context=ctx(widgets=False))
        assert final.data == {}
        assert [(d.code, d.classification) for d in final.diagnostics] == \
            [("unauthorized_ui_action", "no_widgets_declared")]


class TestProbeOF6UnknownFormatNames:
    """PROBE-OF6. BASELINE: `_load_schema` fell back to `default.json` for any
    name it could not find, logging a warning. A typo registered the agent under
    a different envelope with different channels, and ran."""

    def test_an_unknown_name_is_refused_by_name(self):
        with pytest.raises(AgentConfigurationError, match="Unknown output_format"):
            agent({"has_insight": False}, "insigt_v1")          # a plausible typo

    def test_the_error_names_the_supported_formats(self):
        with pytest.raises(AgentConfigurationError) as excinfo:
            agent({"has_insight": False}, "does_not_exist")
        assert "insight_v1" in str(excinfo.value) and "widget_control" in str(excinfo.value)

    def test_negative_control_an_omitted_key_still_resolves(self):
        """The refusal must not swallow the one value that legitimately inherits
        a default — 93 maintained configurations rely on it."""
        from xubb_agents.core.output_format import implicit_default
        a = DynamicAgent({"id": "implicit", "name": "implicit", "text": "t",
                          "trigger_config": {"cooldown": 0}})
        assert a.config.output_format == implicit_default()


class TestProbeOF7ProviderOffersOnlyWhatItReads:
    """PROBE-OF7. BASELINE: `compile_schema(full=True)` added every channel in
    the response descriptor and the conservative subset requires every property,
    so a strict `insight_v1` request REQUIRED the model to fill `state_updates`
    and `data` — two channels whose values that format's parser then discarded."""

    def test_the_projection_offers_exactly_the_channels_the_format_binds(self):
        from xubb_agents.core.output_format import resolve
        from xubb_agents.core.provider_schema import compile_schema
        for fid in ("insight_v1", "widget_control"):
            spec = resolve(fid)
            schema = compile_schema(full=True, content_extension=False,
                                    allowed_types=["fact"], channels=list(spec.channels))
            offered = set(schema["properties"]) - {"has_insight", "insight"}
            assert offered == set(spec.channels), fid
            assert set(schema["required"]) == set(schema["properties"]), fid

    def test_no_supported_format_offers_a_channel_it_cannot_consume(self):
        """NEGATIVE CONTROL: a provider-required field whose output the parser
        discards is the defect. Every offered channel must reach a sink."""
        from xubb_agents.core.output_format import all_formats, CHANNEL_SINKS
        for fid, spec in all_formats().items():
            for wire, sink in spec.channels.items():
                assert sink in CHANNEL_SINKS, (fid, wire)

    def test_state_updates_and_data_are_no_longer_model_facing(self):
        from xubb_agents.core.provider_schema import load_response_contract
        channels = load_response_contract()["domain_channels"]
        assert "state_updates" not in channels and "data" not in channels
        assert "ui_actions" in channels
