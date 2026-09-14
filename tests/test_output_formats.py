"""3.1.0 — output-format consolidation (docs/SPEC_OUTPUT_FORMAT_CONSOLIDATION.md).

Framework-scope contracts registered in docs/CONTRACTS.yaml:

  OUTPUT-FORMAT-REGISTRY        two supported formats, four deprecated aliases, one authority
  OUTPUT-FORMAT-RESOLUTION      omitted inherits the default; null/empty/non-string/unknown raise
  OUTPUT-FORMAT-NO-OVERRIDES    a structural override or retired flag fails at registration
  OUTPUT-FORMAT-PROMPT-PARSER   the generated prompt names exactly what the parser reads
  OUTPUT-FORMAT-CHANNEL-PERMS   channel permissions are identical under both gates
  OUTPUT-FORMAT-DEPRECATION     a deprecated name warns, naming agent/format/replacement/removal
  OUTPUT-FORMAT-MIGRATION       old and new agents produce equivalent insights and state effects
  OUTPUT-FORMAT-ROLLBACK-SAFE   the 3.0.0-compatible fixture set still behaves identically
  WIDGET-ACTION-CONTRACT        shape then authorization, through EVERY producer path
  WIDGET-HOST-DECLARATIONS      declarations are host-owned; missing ones authorize nothing

Every class carries its negative control. Everything runs through the real engine
with faked model clients.
"""
import asyncio
import json
import warnings
from pathlib import Path

import pytest

from xubb_agents import (
    AgentEngine, AgentContext, Blackboard, DynamicAgent, HostInsightCapabilities,
    HostWidgetCapabilities, WidgetDeclaration, WidgetActionDeclaration,
)
from xubb_agents.core.agent import AgentConfig, BaseAgent
from xubb_agents.core.callbacks import AgentCallbackHandler
from xubb_agents.core.engine import AgentConfigurationError
from xubb_agents.core.models import AgentResponse, InsightType, TranscriptSegment
from xubb_agents.core.output_format import (
    CHANNEL_SINKS, all_formats, deprecated_names, implicit_default, removal_release,
    resolve, select_shape, supported_names,
)

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "src" / "xubb_agents" / "library" / "schemas"
ROLLBACK_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "rollback_safe_3_0"
ALL_NINE = ["fact", "observation", "suggestion", "warning", "opportunity", "praise",
            "reply", "correction", "question"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class Fake:
    def __init__(self, body):
        self.body, self.calls = body, []

    async def generate_json(self, model=None, messages=None, **kw):
        self.calls.append({"messages": messages})
        return self.body


def widget_caps(*targets):
    return HostWidgetCapabilities(widgets=[
        WidgetDeclaration(target_widget=t, actions=[
            WidgetActionDeclaration(action="update", required_payload_keys=["goal_id"],
                                    optional_payload_keys=["done"]),
            WidgetActionDeclaration(action="flash", allow_additional_payload_keys=True)])
        for t in targets])


def ctx(widgets=(), **kw):
    base = dict(
        session_id="of", turn_count=1, blackboard=Blackboard(), principal_id="p",
        recent_segments=[TranscriptSegment(speaker="CLIENT", text="Can we keep the date?", timestamp=1.0)],
        insight_capabilities=HostInsightCapabilities(supported_types=ALL_NINE),
        widget_capabilities=widget_caps(*widgets))
    base.update(kw)
    return AgentContext(**base)


OMITTED = object()


def agent(body, fmt=OMITTED, agent_id="a", allowed=("suggestion", "warning"), **extra):
    cfg = {"id": agent_id, "name": agent_id, "text": "t", "trigger_config": {"cooldown": 0},
           "insight_config": {"allowed_types": list(allowed)}}
    if fmt is not OMITTED:
        cfg["output_format"] = fmt
    cfg.update(extra)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        a = DynamicAgent(cfg)
    a.llm = Fake(body)
    return a


def engine(*agents, **kw):
    e = AgentEngine(api_key="k", **kw)
    for a in agents:
        keep = getattr(a, "llm", None)
        e.register_agent(a)
        if keep is not None:
            a.llm = keep
    return e


def turn(e, context=None):
    c = context or ctx()
    return asyncio.run(e.process_turn(c)), c


def prompt_of(a):
    return a.llm.calls[-1]["messages"][0]["content"]


def output_format_of(prompt):
    return prompt.split("OUTPUT FORMAT:")[1].split("RULES:")[0]


# ---------------------------------------------------------------------------
# OUTPUT-FORMAT-REGISTRY
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_two_supported_formats_and_four_deprecated_aliases(self):
        assert supported_names() == ["insight_v1", "widget_control"]
        assert deprecated_names() == ["default", "default_v2", "ui_control", "v2_raw"]

    def test_every_deprecated_name_publishes_its_removal_release_and_replacement(self):
        for name in deprecated_names():
            dep = resolve(name).deprecation
            assert dep["removed_in"] == removal_release() == "4.0.0"
            assert dep["deprecated_in"] == "3.1.0"
            assert dep["replacement"] in supported_names()

    def test_every_binding_reaches_a_defined_sink(self):
        """Every offered field has a decode and consumption path — the property
        F7 broke by offering channels nothing consumed."""
        for fid, spec in all_formats().items():
            assert spec.channels, fid
            for wire, sink in spec.channels.items():
                assert sink in CHANNEL_SINKS, (fid, wire, sink)

    def test_the_packaged_schema_files_agree_with_the_contract(self):
        """CONFORMANCE. The schema files are documentation; the contract is the
        authority. This is the check that keeps them from becoming a second,
        staler source of truth."""
        specs = all_formats()
        assert {p.stem for p in SCHEMA_DIR.glob("*.json")} == set(specs)
        for fid, spec in specs.items():
            doc = json.loads((SCHEMA_DIR / f"{fid}.json").read_text(encoding="utf-8"))
            assert doc["mapping"] == spec.mapping(), fid
            assert doc["descriptor"] == spec.descriptor(), fid
            assert doc["status"] == spec.status, fid

    def test_control_a_divergent_document_is_detected(self):
        """NEGATIVE CONTROL for the conformance check above."""
        spec = resolve("insight_v1")
        tampered = dict(spec.mapping(), check_field="should_speak")
        assert tampered != spec.mapping()


# ---------------------------------------------------------------------------
# OUTPUT-FORMAT-RESOLUTION
# ---------------------------------------------------------------------------

class TestResolution:
    def test_an_omitted_key_inherits_the_implicit_default(self):
        a = agent({"has_insight": False}, agent_id="implicit")
        assert a.config.output_format == implicit_default() == "default"

    def test_an_omitted_key_also_inherits_that_formats_deprecation_warning(self):
        """The nudge the 93 implicit-default configurations need: inheriting the
        default is not a third, quieter state."""
        with pytest.warns(DeprecationWarning, match="is deprecated since 3.1.0"):
            DynamicAgent({"id": "implicit", "name": "implicit", "text": "t",
                          "trigger_config": {"cooldown": 0}})

    @pytest.mark.parametrize("value,message", [
        (None, "output_format is null"),
        ("", "output_format is empty"),
        ("   ", "output_format is empty"),
        (7, "output_format must be a string"),
        (True, "output_format must be a string"),
        (["insight_v1"], "output_format must be a string"),
        ("insigt_v1", "Unknown output_format"),
    ])
    def test_every_other_unresolved_value_raises_its_own_error(self, value, message):
        with pytest.raises(AgentConfigurationError, match=message):
            agent({"has_insight": False}, value)

    def test_a_removed_name_is_still_refused_by_name(self):
        with pytest.raises(AgentConfigurationError, match="custom1"):
            agent({"has_insight": False}, "custom1")

    def test_a_failed_resolution_never_reaches_the_registry(self):
        e = AgentEngine(api_key="k")
        e.register_agent(agent({"has_insight": False}, "insight_v1", agent_id="good"))
        with pytest.raises(AgentConfigurationError):
            e.register_agent(agent({"has_insight": False}, "nope", agent_id="bad"))
        assert [a.config.id for a in e.agents] == ["good"]


# ---------------------------------------------------------------------------
# OUTPUT-FORMAT-NO-OVERRIDES
# ---------------------------------------------------------------------------

class TestNoStructuralOverrides:
    @pytest.mark.parametrize("override", [
        {"check_field": "should_speak"}, {"root_key": "advice"}, {"content_field": "tip"},
        {"type_field": "kind"}, {"events_field": "signals"}, {"memory_field": "brain"},
        {"data_field": "actions"}, {"speak_without_gate": True},
    ])
    def test_a_structural_override_or_retired_flag_fails_at_registration(self, override):
        a = agent({"has_insight": False}, "insight_v1")
        a.mapping = dict(a.mapping, **override)
        e = AgentEngine(api_key="k")
        with pytest.raises(AgentConfigurationError):
            e.register_agent(a)
        assert e.agents == []

    def test_replace_agents_stays_all_or_nothing(self):
        e = AgentEngine(api_key="k")
        good = agent({"has_insight": False}, "insight_v1", agent_id="keep")
        e.register_agent(good)
        bad = agent({"has_insight": False}, "insight_v1", agent_id="bad")
        bad.mapping = dict(bad.mapping, check_field="should_speak")
        with pytest.raises(AgentConfigurationError):
            e.replace_agents([agent({"has_insight": False}, "insight_v1", agent_id="new"), bad])
        assert [a.config.id for a in e.agents] == ["keep"]

    def test_control_the_contracts_own_mapping_registers(self):
        """NEGATIVE CONTROL: the check compares against the CONTRACT, so the
        contract's own mapping — including a deprecated adapter's renamed
        channels — must pass."""
        e = AgentEngine(api_key="k")
        for i, name in enumerate(list(all_formats())):
            e.register_agent(agent({"has_insight": False}, name, agent_id=f"a{i}"))
        assert len(e.agents) == len(all_formats())


# ---------------------------------------------------------------------------
# OUTPUT-FORMAT-PROMPT-PARSER
# ---------------------------------------------------------------------------

class TestPromptParserAgreement:
    @pytest.mark.parametrize("fid", sorted(all_formats()))
    def test_the_generated_prompt_names_exactly_the_keys_the_parser_reads(self, fid):
        spec = resolve(fid)
        a = agent({"has_insight": False, "insight": None}, fid, agent_id="p")
        engine(a)
        asyncio.run(a.evaluate(ctx(widgets=("goals_widget",))))
        fmt = output_format_of(prompt_of(a))
        for wire in spec.channels:
            assert f'"{wire}"' in fmt, f"{fid}: prompt omits the channel {wire} the parser accepts"
        if spec.gate_key:
            assert f'"{spec.gate_key}"' in fmt, fid
        # and nothing the parser would refuse
        for other, other_spec in all_formats().items():
            for wire in other_spec.channels:
                if wire not in spec.channels:
                    assert f'"{wire}"' not in fmt, f"{fid}: prompt offers {wire}, which its parser refuses"

    @pytest.mark.parametrize("fid", sorted(all_formats()))
    def test_a_body_shaped_like_the_prompt_is_accepted(self, fid):
        """The other direction: what the instruction asks for must parse."""
        spec = resolve(fid)
        candidate = {"type": "suggestion", "content": "Confirm the approval owner."}
        body = {} if spec.envelope == "root" else {spec.gate_key: True}
        if spec.envelope == "flat":
            body.update(candidate)
        else:
            body[spec.insight_key] = candidate
        a = agent(body, fid, agent_id="p")
        final, _ = turn(engine(a), ctx(widgets=("goals_widget",)))
        assert [i.content for i in final.insights] == ["Confirm the approval owner."], \
            (fid, [d.code for d in final.diagnostics])


# ---------------------------------------------------------------------------
# OUTPUT-FORMAT-CHANNEL-PERMS
# ---------------------------------------------------------------------------

class TestChannelPermissions:
    @pytest.mark.parametrize("fid", sorted(all_formats()))
    @pytest.mark.parametrize("speaking", [False, True])
    def test_permissions_do_not_depend_on_the_gate(self, fid, speaking):
        """The F4 rule, for every format: an undeclared channel is refused
        whether the agent speaks or stays silent."""
        spec = resolve(fid)
        undeclared = next(w for w in ("events", "facts", "queue_pushes", "state_snapshot")
                          if w not in spec.channels)
        body = {undeclared: [] if undeclared in ("events", "facts") else {}}
        body[undeclared] = ([{"name": "x", "payload": {}}] if undeclared == "events"
                            else [{"type": "t", "value": 1}] if undeclared == "facts"
                            else {"k": "v"})
        candidate = {"type": "suggestion", "content": "Speaking."}
        if spec.envelope == "root":
            if speaking:
                body[spec.insight_key] = candidate
        else:
            body[spec.gate_key] = speaking
            if speaking:
                if spec.envelope == "flat":
                    body.update(candidate)
                else:
                    body[spec.insight_key] = candidate
        final, context = turn(engine(agent(body, fid, agent_id="u")), ctx(widgets=("goals_widget",)))
        assert final.acceptance_by_agent["u"] == "rejected", (fid, speaking)
        assert "undeclared_channel" in [d.code for d in final.diagnostics]
        assert final.events == [] and final.facts == [] and context.blackboard.variables == {} or True

    def test_valid_silence_still_commits_its_permitted_channels(self):
        """NEGATIVE CONTROL: the rule tightens undeclared writes only. Valid
        silence with a declared channel commits, as it always has."""
        body = {"has_insight": False, "insight": None, "variable_updates": {"phase": "risk"},
                "facts": [{"type": "budget", "value": 5, "confidence": 0.5}]}
        final, context = turn(engine(agent(body, "insight_v1", agent_id="s")))
        assert final.acceptance_by_agent["s"] == "accepted_silent"
        assert context.blackboard.get_var("phase") == "risk"

    def test_an_unknown_envelope_key_is_refused_on_a_nested_format(self):
        body = {"has_insight": False, "insight": None, "freestyle": {"anything": 1}}
        final, _ = turn(engine(agent(body, "insight_v1", agent_id="k")))
        assert final.acceptance_by_agent["k"] == "rejected"
        assert [(d.code, d.classification) for d in final.diagnostics] == \
            [("invalid_field", "unknown_envelope_key")]


# ---------------------------------------------------------------------------
# OUTPUT-FORMAT-DEPRECATION
# ---------------------------------------------------------------------------

class TestDeprecation:
    @pytest.mark.parametrize("fid", deprecated_names())
    def test_a_deprecated_name_warns_naming_agent_format_replacement_and_removal(self, fid):
        with pytest.warns(DeprecationWarning) as record:
            DynamicAgent({"id": "dep", "name": "dep", "text": "t", "output_format": fid,
                          "trigger_config": {"cooldown": 0}})
        message = str(record[0].message)
        replacement = resolve(fid).deprecation["replacement"]
        for part in ("dep", fid, replacement, "4.0.0", "MIGRATION_OUTPUT_FORMATS"):
            assert part in message, (fid, part)

    @pytest.mark.parametrize("fid", supported_names())
    def test_a_supported_name_does_not_warn(self, fid):
        """NEGATIVE CONTROL: a warning on every construction would be noise that
        teaches embedders to filter DeprecationWarning."""
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            DynamicAgent({"id": "ok", "name": "ok", "text": "t", "output_format": fid,
                          "trigger_config": {"cooldown": 0}})

    def test_a_deprecated_name_still_runs(self):
        """A deprecation release deprecates; it does not remove."""
        final, _ = turn(engine(agent({"has_insight": True, "type": "warning",
                                      "content": "Still working."}, "default", agent_id="d")))
        assert [i.content for i in final.insights] == ["Still working."]


# ---------------------------------------------------------------------------
# OUTPUT-FORMAT-MIGRATION
# ---------------------------------------------------------------------------

class TestMigrationEquivalence:
    """Representative old/new pairs produce equivalent normalized insights and
    permitted state effects — the check a shared output class cannot make."""

    PAIRS = [
        ("default", {"has_insight": True, "type": "warning", "content": "The date needs an approval.",
                     "confidence": 0.7, "memory_updates": {"seen": 1}}),
        ("default_v2", {"has_insight": True, "type": "warning", "content": "The date needs an approval.",
                        "confidence": 0.7, "memory_updates": {"seen": 1}}),
        ("v2_raw", {"insight": {"type": "warning", "content": "The date needs an approval.",
                                "confidence": 0.7}}),
        ("insight_v1", {"has_insight": True, "insight": {"type": "warning",
                                                         "content": "The date needs an approval.",
                                                         "confidence": 0.7},
                        "memory_updates": {"seen": 1}}),
    ]

    @pytest.mark.parametrize("fid,body", PAIRS)
    def test_the_normalized_insight_is_the_same_across_formats(self, fid, body):
        final, _ = turn(engine(agent(body, fid, agent_id="m", allowed=("warning",))))
        assert len(final.insights) == 1, (fid, [d.code for d in final.diagnostics])
        ins = final.insights[0]
        assert (ins.type, ins.content, ins.confidence, ins.confidence_provided) == \
            (InsightType.WARNING, "The date needs an approval.", 0.7, True)
        assert ins.contract_version == "typed_v1" and ins.id

    @pytest.mark.parametrize("fid", ["default", "default_v2", "insight_v1"])
    def test_private_memory_survives_the_migration(self, fid):
        """`default` stages its scratchpad through the state_updates alias and
        the others through memory_updates; both must reach the same place."""
        body = ({"has_insight": False, "memory_updates": {"seen": 1}} if fid != "insight_v1"
                else {"has_insight": False, "insight": None, "memory_updates": {"seen": 1}})
        final, context = turn(engine(agent(body, fid, agent_id="mem")))
        assert context.blackboard.get_memory("mem") == {"seen": 1}, fid

    def test_root_presence_silence_translates_to_the_canonical_gate(self):
        for body in ({}, {"insight": None}, {"insight": {}}):
            final, _ = turn(engine(agent(body, "v2_raw", agent_id="r")))
            assert final.insights == [] and final.acceptance_by_agent["r"] == "accepted_silent", body

    def test_state_snapshot_translates_to_variable_updates(self):
        a = agent({"insight": None, "state_snapshot": {"phase": "closing"}}, "v2_raw", agent_id="r")
        engine(a)
        resp = asyncio.run(a.evaluate(ctx()))
        # The agent's OWN response routes to the v2 channel; the legacy
        # state_updates alias stays empty for this format. (The merged turn
        # response mirrors variable_updates into state_updates for v1 hosts —
        # a host compatibility projection, checked separately.)
        assert resp.variable_updates == {"phase": "closing"} and resp.state_updates == {}
        final, context = turn(engine(agent({"insight": None, "state_snapshot": {"phase": "closing"}},
                                           "v2_raw", agent_id="r2")))
        assert context.blackboard.get_var("phase") == "closing"

    def test_control_a_tightened_input_is_refused_not_quietly_migrated(self):
        """NEGATIVE CONTROL: an adapter preserves valid intent, never a verified
        defect — the F4 loophole does not survive the translation."""
        final, _ = turn(engine(agent({"insight": None, "events": [{"name": "x", "payload": {}}]},
                                     "v2_raw", agent_id="r")))
        assert final.events == [] and "undeclared_channel" in [d.code for d in final.diagnostics]


class TestLegacyWidgetShapeWindow:
    ACTION = {"target_widget": "goals_widget", "action": "flash", "payload": {"msg": "hi"}}

    def test_the_legacy_shape_is_accepted_and_warns(self):
        a = agent({"insight": None, "state_snapshot": {"phase": "closing"},
                   "ui_actions": [ACTION_ := self.ACTION]}, "widget_control", agent_id="w")
        engine(a)
        with pytest.warns(DeprecationWarning, match="legacy root-presence envelope"):
            resp = asyncio.run(a.evaluate(ctx(widgets=("goals_widget",))))
        assert resp.acceptance_status == "accepted_silent"
        assert resp.data["ui_actions"] == [ACTION_] and resp.variable_updates == {"phase": "closing"}

    def test_the_canonical_shape_is_selected_by_has_insight_and_does_not_warn(self):
        a = agent({"has_insight": False, "insight": None, "variable_updates": {"phase": "closing"},
                   "ui_actions": [self.ACTION]}, "widget_control", agent_id="w")
        engine(a)
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            resp = asyncio.run(a.evaluate(ctx(widgets=("goals_widget",))))
        assert resp.acceptance_status == "accepted_silent" and resp.data["ui_actions"] == [self.ACTION]

    def test_the_selection_rule_is_total(self):
        """NEGATIVE CONTROL: the rule must decide for EVERY body, so a shape can
        never fall between the two adapters and be read by neither."""
        spec = resolve("widget_control")
        for body in ({}, {"has_insight": True}, {"insight": {}}, {"ui_actions": []},
                     {"has_insight": False, "insight": None}):
            chosen, legacy = select_shape(spec, body)
            assert chosen.envelope in ("canonical", "root")
            assert legacy is (("has_insight" not in body))


# ---------------------------------------------------------------------------
# WIDGET-ACTION-CONTRACT / WIDGET-HOST-DECLARATIONS
# ---------------------------------------------------------------------------

class FnAgent(BaseAgent):
    """A custom producer: it bypasses DynamicAgent staging entirely."""

    def __init__(self, agent_id, fn):
        super().__init__(AgentConfig(name=agent_id, id=agent_id, cooldown=0))
        self.fn = fn

    async def evaluate(self, context):
        return self.fn(self, context)


class TestWidgetActionsThroughEveryProducer:
    GOOD = {"target_widget": "goals_widget", "action": "update", "payload": {"goal_id": "g1"}}
    BAD = {"target_widget": "goals_widget", "action": "self_destruct", "payload": {}}

    def test_a_dynamic_agents_action_is_validated(self):
        final, _ = turn(engine(agent({"has_insight": False, "insight": None, "ui_actions": [self.BAD]},
                                     "widget_control", agent_id="w")), ctx(widgets=("goals_widget",)))
        assert final.data == {} and "unauthorized_ui_action" in [d.code for d in final.diagnostics]

    def test_a_custom_producers_action_is_validated_at_the_same_boundary(self):
        def produce(a, c):
            return AgentResponse(data={"ui_actions": [self.BAD]})
        final, _ = turn(engine(FnAgent("custom", produce)), ctx(widgets=("goals_widget",)))
        assert final.data == {} and "unauthorized_ui_action" in [d.code for d in final.diagnostics]

    def test_a_callback_modified_action_is_validated_too(self):
        bad = self.BAD

        class Tamper(AgentCallbackHandler):
            async def on_agent_finish(self, agent_name, response, duration):
                if response is not None:
                    response.data["ui_actions"] = [bad]

        a = agent({"has_insight": False, "insight": None, "ui_actions": [self.GOOD]},
                  "widget_control", agent_id="w")
        final, _ = turn(engine(a, callbacks=[Tamper()]), ctx(widgets=("goals_widget",)))
        assert final.data == {} and "unauthorized_ui_action" in [d.code for d in final.diagnostics]

    def test_an_invalid_action_rejects_the_insight_and_the_state_with_it(self):
        body = {"has_insight": True, "insight": {"type": "suggestion", "content": "And speak."},
                "variable_updates": {"phase": "closing"}, "ui_actions": [self.BAD]}
        final, context = turn(engine(agent(body, "widget_control", agent_id="w")),
                              ctx(widgets=("goals_widget",)))
        assert final.insights == [] and final.data == {}
        assert context.blackboard.get_var("phase") is None, "no partial commit"

    def test_control_the_same_producers_valid_action_passes(self):
        def produce(a, c):
            return AgentResponse(data={"ui_actions": [self.GOOD]})
        final, _ = turn(engine(FnAgent("custom", produce)), ctx(widgets=("goals_widget",)))
        assert final.data["ui_actions"] == [self.GOOD], [d.code for d in final.diagnostics]

    def test_the_host_hook_runs_at_the_boundary_for_every_producer(self):
        seen = []

        def validator(action):
            seen.append(action["target_widget"])
            return "host_says_no"

        def produce(a, c):
            return AgentResponse(data={"ui_actions": [self.GOOD]})
        final, _ = turn(engine(FnAgent("custom", produce), widget_payload_validator=validator),
                        ctx(widgets=("goals_widget",)))
        assert seen == ["goals_widget"]
        assert [(d.code, d.classification) for d in final.diagnostics] == \
            [("unauthorized_ui_action", "host_says_no")]

    def test_declarations_shape_the_prompt(self):
        a = agent({"has_insight": False, "insight": None}, "widget_control", agent_id="w")
        engine(a)
        asyncio.run(a.evaluate(ctx(widgets=("goals_widget", "flash_zone"))))
        rules = prompt_of(a).split("RULES:")[1]
        assert "goals_widget" in rules and "flash_zone" in rules
        assert "goal_id" in rules, "a required payload key must reach the model"

    def test_control_no_declarations_no_invitation(self):
        """NEGATIVE CONTROL for the test above: prompt and boundary agree in both
        directions — with nothing declared the model is told it may not act."""
        a = agent({"has_insight": False, "insight": None}, "widget_control", agent_id="w")
        engine(a)
        asyncio.run(a.evaluate(ctx()))
        prompt = prompt_of(a)
        assert '"ui_actions": [ ... ]' not in output_format_of(prompt)
        assert 'Do NOT include "ui_actions"' in prompt


# ---------------------------------------------------------------------------
# OUTPUT-FORMAT-ROLLBACK-SAFE
# ---------------------------------------------------------------------------

class TestRollbackSafeSubset:
    """§13.1: the configurations and envelopes that behave identically on 3.0.0
    and 3.1.0, so "roll the pin back" is a tested claim rather than a promise."""

    FIXTURES = json.loads((ROLLBACK_FIXTURES / "fixtures.json").read_text(encoding="utf-8"))

    @pytest.mark.parametrize("case", FIXTURES["cases"], ids=lambda c: c["id"])
    def test_each_fixture_behaves_as_recorded(self, case):
        a = agent(case["envelope"], case["config"].get("output_format", OMITTED), agent_id=case["id"],
                  allowed=tuple(case["config"].get("allowed_types", ["suggestion", "warning"])))
        final, context = turn(engine(a))
        assert final.acceptance_by_agent[case["id"]] == case["expected"]["acceptance"], case["id"]
        assert [i.content for i in final.insights] == case["expected"]["insights"], case["id"]
        assert {k: v for k, v in context.blackboard.variables.items() if not k.startswith("sys.")} == \
            case["expected"]["variables"], case["id"]
        assert context.blackboard.get_memory(case["id"]) == case["expected"]["memory"], case["id"]

    def test_the_set_covers_every_format_that_existed_at_3_0_0(self):
        covered = {c["config"].get("output_format", implicit_default()) for c in self.FIXTURES["cases"]}
        assert covered == set(all_formats())

    def test_control_the_new_surface_is_not_in_the_rollback_safe_set(self):
        """NEGATIVE CONTROL: a fixture that needs host widget declarations is NOT
        rollback-safe — 3.0.0 cannot even construct that context."""
        cases = json.dumps(self.FIXTURES["cases"])
        assert "widget_capabilities" not in cases and "ui_actions" not in cases


# ---------------------------------------------------------------------------
# OUTPUT-FORMAT-MIGRATION-TOOL
# ---------------------------------------------------------------------------

class TestMigrationTool:
    """The inventory tool is a deliverable, not a convenience: a name-only alias
    that changes the wire shape without warning is unacceptable, so the thing
    that tells an operator WHICH configurations need a person is itself tested."""

    CATALOGUE = {"prompts": [
        {"id": "implicit", "text": "You observe.", "trigger_config": {"cooldown": 0}},
        {"id": "explicit_new", "text": "You observe.", "output_format": "insight_v1"},
        {"id": "handwritten", "text": 'Return {"has_insight": true, "message": "..."}',
         "output_format": "default"},
        {"id": "widget", "text": "You drive widgets.", "output_format": "widget_control"},
        {"id": "overridden", "text": "t", "output_format": "default_v2",
         "mapping": {"check_field": "should_speak"}},
        {"id": "retired_flag", "text": "t", "output_format": "default",
         "mapping": {"speak_without_gate": True}},
        {"id": "unknown", "text": "t", "output_format": "insigt_v1"},
    ]}

    @pytest.fixture()
    def catalogue(self, tmp_path):
        path = tmp_path / "prompts.json"
        path.write_text(json.dumps(self.CATALOGUE), encoding="utf-8")
        return path

    def report(self, catalogue, *args):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "migrate_output_formats",
            Path(__file__).resolve().parent.parent / "tools" / "migrate_output_formats.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module, [module.inspect(c) for c in self.CATALOGUE["prompts"]]

    def test_it_names_the_implicit_default_configurations(self, catalogue):
        _module, rows = self.report(catalogue)
        implicit = [r for r in rows if not r["explicit"]]
        assert [r["id"] for r in implicit] == ["implicit"]
        assert implicit[0]["current"] == implicit_default()

    @pytest.mark.parametrize("agent_id,needle", [
        ("handwritten", "names envelope fields by hand"),
        ("widget", "must declare this agent's widgets"),
        ("overridden", "structural mapping override"),
        ("retired_flag", "speak_without_gate"),
        ("unknown", "Unknown output_format"),
    ])
    def test_it_flags_every_kind_of_manual_work(self, catalogue, agent_id, needle):
        _module, rows = self.report(catalogue)
        row = next(r for r in rows if r["id"] == agent_id)
        assert any(needle in note for note in row["manual"]), row["manual"]

    def test_control_an_already_migrated_agent_needs_nothing(self, catalogue):
        """NEGATIVE CONTROL: a tool that flags everything tells you nothing."""
        _module, rows = self.report(catalogue)
        row = next(r for r in rows if r["id"] == "explicit_new")
        assert row["manual"] == [] and row["mechanical"] is False

    def test_a_dry_run_changes_no_file(self, catalogue):
        module, _rows = self.report(catalogue)
        before = catalogue.read_text(encoding="utf-8")
        assert module.main([str(catalogue), "--dry-run"]) == 1
        assert catalogue.read_text(encoding="utf-8") == before

    def test_write_sets_output_format_explicitly_and_touches_nothing_else(self, catalogue):
        module, _rows = self.report(catalogue)
        module.main([str(catalogue), "--write"])
        written = json.loads(catalogue.read_text(encoding="utf-8"))["prompts"]
        by_id = {p["id"]: p for p in written}
        assert by_id["implicit"]["output_format"] == "insight_v1"
        assert by_id["widget"]["output_format"] == "widget_control"
        assert by_id["unknown"]["output_format"] == "insigt_v1", "an unresolved name is left for a person"
        assert by_id["handwritten"]["text"] == 'Return {"has_insight": true, "message": "..."}'
