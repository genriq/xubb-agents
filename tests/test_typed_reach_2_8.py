"""v2.8 — typed reach (docs/SPEC_V2_8_TYPED_REACH.md).

Framework-scope contracts registered in docs/CONTRACTS.yaml:

  TYPED-ADAPTER-FLAT-V1               INV-49  `default` registers under typed_v1 through flat_v1
  TYPED-ADAPTER-ROOT-V2-SIDECAR       INV-49  ui_control / widget_control through root_v2 with the sidecar
  TYPED-UNSUPPORTED-SCHEMA-NAMED      INV-49  custom1 refused by name; no adapter, no registration
  EVIDENCE-COORDINATES-AND-CITATIONS  INV-50  source_index over the host's list; citations on demand
  ISOLATED-INSTRUCTION-RESULT-ONLY    INV-51  the isolated path's instruction offers the envelope only
  URGENCY-PROVENANCE                  INV-52  urgency_provided is engine-owned and explicit-only
  CONTENT-RESULT-AFTER-RELEASE        INV-53  result() returns after the slot is released
  CORRECTABLE-TARGETS                 INV-54  PriorInsightRecord.correctable
  DATA-BY-AGENT                       INV-55  per-agent sidecar attribution

Every class carries its negative control (``test_control_*``). Everything runs through the
real engine with faked model clients.
"""
import asyncio
import json

import pytest

from xubb_agents import AgentEngine, AgentConfigurationError, DynamicAgent, AgentContext, Blackboard, HostInsightCapabilities
from xubb_agents.core.agent import AgentConfig, BaseAgent
from xubb_agents.core.insight_validation import HUMAN_WIRE_VALUES, validate_answers, validate_correction_target
from xubb_agents.core.llm import LLMResult
from xubb_agents.core.models import (
    AgentResponse, InsightType, InsightConfig, InsightReferenceContext, EvidenceCatalogEntry, EvidenceRef,
    PriorInsightRecord, InsightAnswer, TranscriptSegment, TriggerType, InsightContentRequest,
)

from tests.test_dynamic_agent import run
from tests.test_typed_acceptance_g1 import tengine, tagent, tctx, envelope, cand, codes, turn
from tests.test_evidence_catalog_g2 import DeferredLLM
from tests.test_long_form_c1 import CONTENT, OPERATOR, ctx as content_ctx

NINE = list(HUMAN_WIRE_VALUES)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def prompt_of(agent):
    return agent.llm.calls[-1]["messages"][0]["content"]


def output_format_of(prompt):
    return prompt.split("OUTPUT FORMAT:")[1].split("RULES:")[0]


def rules_of(prompt):
    return prompt.split("RULES:")[1]


def legacy_engine(agent):
    engine = AgentEngine(api_key="k")
    fake = agent.llm
    engine.register_agent(agent)
    agent.llm = fake
    return engine


class RecordingContentFake:
    """generate()-style fake carrying the telemetry the content contract needs and
    recording the messages it was sent (the isolated clone shares the client)."""

    def __init__(self, body):
        self.body, self.calls = body, []

    async def generate(self, model=None, messages=None, **kw):
        self.calls.append({"model": model, "messages": messages, **kw})
        raw = json.dumps(self.body).encode("utf-8")
        return LLMResult(parsed=self.body, finish_reason="stop", transport="json_object", raw_bytes=len(raw),
                         usage={"prompt_tokens": 3, "completion_tokens": 9})


class GatedRecorder(RecordingContentFake):
    def __init__(self, body, gate):
        super().__init__(body)
        self.gate = gate

    async def generate(self, model=None, messages=None, **kw):
        await self.gate.wait()
        return await super().generate(model=model, messages=messages, **kw)


LONG = " ".join(["scope"] * 3000)
DEEP = {"has_insight": True, "insight": {"type": "suggestion", "content": LONG, "confidence": 0.8, "urgency": "soon",
                                         "preview": "Short.", "content_format": "markdown"}}


def content_agent(body, agent_id="lf", content=CONTENT):
    cfg = {"id": agent_id, "name": agent_id, "text": "t", "output_format": "insight_v1", "trigger_config": {"cooldown": 0},
           "insight_config": {"allowed_types": ["fact", "suggestion", "warning"]}}
    if content is not None:
        cfg["insight_config"]["content"] = content
    a = DynamicAgent(cfg)
    a.llm = RecordingContentFake(body)
    return a


def content_engine(*agents, limits=None):
    e = AgentEngine(api_key="k", insight_contract="typed_v1", content_limits=dict(OPERATOR, **(limits or {})))
    for a in agents:
        llm = a.llm
        e.register_agent(a)
        a.llm = llm
    return e


# ---------------------------------------------------------------------------
# TA-1 — `default` through flat_v1
# ---------------------------------------------------------------------------

class TestFlatV1Adapter:
    def test_default_registers_and_instruction_is_candidate_plus_memory(self):
        agent = tagent(None, output_format="default", insight_config={"allowed_types": ["warning", "suggestion"]})
        tengine(agent)
        assert agent.descriptor["typed_adapter"] == "flat_v1"
        run(agent.evaluate(tctx()))
        fmt = output_format_of(prompt_of(agent))
        assert '"has_insight": true | false' in fmt and '"type": "suggestion" | "warning"' in fmt
        assert '"memory_updates": { "key": "value" }' in fmt
        for key in ('"events"', '"variable_updates"', '"queue_pushes"', '"facts"', '"insight": null', '"message"',
                    '"state_snapshot"'):
            assert key not in fmt, key

    def test_accepted_flat_result_is_a_typed_insight_and_memory_commits(self):
        body = {"has_insight": True, "type": "warning", "content": "The date depends on an approval.", "confidence": 0.7,
                "urgency": "now", "memory_updates": {"seen": 1}}
        agent = tagent(body, output_format="default", insight_config={"allowed_types": ["warning"]})
        final, ctx = turn(tengine(agent))
        assert [i.type for i in final.insights] == [InsightType.WARNING], codes(final)
        ins = final.insights[0]
        assert ins.id and ins.contract_version == "typed_v1" and ins.urgency == "now" and ins.confidence_provided is True
        assert ctx.blackboard.get_memory("typed_agent") == {"seen": 1}
        assert final.acceptance_by_agent["typed_agent"] == "accepted"

    def test_false_gate_with_placeholders_is_silence_and_memory_still_commits(self):
        body = {"has_insight": False, "type": "warning", "content": "placeholder", "memory_updates": {"seen": 2}}
        agent = tagent(body, output_format="default", insight_config={"allowed_types": ["warning"]})
        final, ctx = turn(tengine(agent))
        assert final.insights == [] and final.acceptance_by_agent["typed_agent"] == "accepted_silent"
        assert ctx.blackboard.get_memory("typed_agent") == {"seen": 2}

    def test_state_only_default_agent_gets_the_silence_envelope_with_memory(self):
        agent = tagent({"has_insight": False, "memory_updates": {"k": 1}}, output_format="default",
                       insight_config={"allowed_types": []})
        tengine(agent)
        run(agent.evaluate(tctx()))
        fmt = output_format_of(prompt_of(agent))
        assert '"has_insight": false' in fmt and '"memory_updates": {}' in fmt
        assert '"events"' not in fmt and '"insight": null' not in fmt

    def test_legacy_path_for_default_is_unchanged(self):
        body = {"has_insight": True, "type": "suggestion", "message": "Ask about timing", "memory_updates": {"seen": 1}}
        agent = tagent(body, output_format="default")
        engine = legacy_engine(agent)
        ctx = tctx()
        final = asyncio.run(engine.process_turn(ctx))
        assert [i.content for i in final.insights] == ["Ask about timing"]
        assert final.insights[0].contract_version is None and final.insights[0].urgency_provided is None
        assert '"message": "Your advice here"' in prompt_of(agent)      # the legacy instruction, byte-identical
        assert ctx.blackboard.get_memory("typed_agent") == {"seen": 1}

    def test_control_typed_declaration_without_an_adapter_is_refused(self):
        """NEGATIVE CONTROL (INV-49): a descriptor may not declare typed_v1 without naming its adapter."""
        agent = tagent(envelope(), output_format="default")
        agent.descriptor = {k: v for k, v in agent.descriptor.items() if k != "typed_adapter"}
        engine = AgentEngine(api_key="k", insight_contract="typed_v1")
        with pytest.raises(AgentConfigurationError, match="without a typed_adapter"):
            engine.register_agent(agent)
        assert engine.agents == []


# ---------------------------------------------------------------------------
# TA-2 — ui_control / widget_control through root_v2 with the sidecar
# ---------------------------------------------------------------------------

class TestRootV2Sidecar:
    ACTION = {"target_widget": "goals_widget", "action": "update", "payload": {"done": 1}}

    def widget(self, body, agent_id="w", allowed=("suggestion",), schema="widget_control"):
        return tagent(body, output_format=schema, agent_id=agent_id, insight_config={"allowed_types": list(allowed)})

    @pytest.mark.parametrize("schema", ["widget_control", "ui_control"])
    def test_registers_and_instruction_names_state_and_sidecar_from_the_mapping(self, schema):
        agent = self.widget(None, schema=schema)
        tengine(agent)
        assert agent.descriptor["typed_adapter"] == "root_v2"
        run(agent.evaluate(tctx()))
        prompt = prompt_of(agent)
        fmt, rules = output_format_of(prompt), rules_of(prompt)
        assert '"insight": {' in fmt and '"state_snapshot": { "key": "value" }' in fmt and '"ui_actions": [ ... ]' in fmt
        assert '"ui_actions": ' in rules and "target_widget" in rules
        assert '"has_insight"' not in fmt and '"memory_updates"' not in fmt

    def test_accepted_result_stages_the_insight_state_and_sidecar(self):
        body = {"insight": cand(type="suggestion", content="Confirm the approval owner.", urgency="soon"),
                "ui_actions": [self.ACTION], "state_snapshot": {"phase": "closing"}}
        final, ctx = turn(tengine(self.widget(body)))
        assert [i.type for i in final.insights] == [InsightType.SUGGESTION], codes(final)
        assert final.insights[0].id and final.insights[0].contract_version == "typed_v1"
        assert final.data["ui_actions"] == [self.ACTION]
        assert ctx.blackboard.get_var("phase") == "closing"

    def test_silence_with_actions_commits_the_sidecar(self):
        final, _ = turn(tengine(self.widget({"ui_actions": [self.ACTION], "state_snapshot": {}})))
        assert final.insights == [] and final.acceptance_by_agent["w"] == "accepted_silent"
        assert final.data["ui_actions"] == [self.ACTION]

    def test_silence_only_envelope_keeps_the_sidecar(self):
        agent = self.widget({"ui_actions": [self.ACTION]}, allowed=())
        tengine(agent)
        run(agent.evaluate(tctx()))
        fmt = output_format_of(prompt_of(agent))
        assert '"ui_actions": []' in fmt and '"state_snapshot": { "key": "value" }' in fmt and '"insight"' not in fmt

    def test_v2_raw_instruction_carries_no_sidecar(self):
        agent = tagent(None, output_format="v2_raw", insight_config={"allowed_types": ["warning"]})
        tengine(agent)
        run(agent.evaluate(tctx()))
        fmt = output_format_of(prompt_of(agent))
        assert fmt.rstrip().endswith('"state_snapshot": { "key": "value" }\n}') and "ui_actions" not in fmt

    def test_control_without_a_sidecar_instruction_no_sidecar_block(self):
        """NEGATIVE CONTROL: the block is generated from the descriptor, never assumed from the mapping."""
        agent = self.widget(None)
        agent.descriptor = {k: v for k, v in agent.descriptor.items() if k != "sidecar_instruction"}
        tengine(agent)
        run(agent.evaluate(tctx()))
        prompt = prompt_of(agent)
        assert "ui_actions" not in output_format_of(prompt) and "ui_actions" not in rules_of(prompt)


# ---------------------------------------------------------------------------
# TA-3 — custom1 refused by name
# ---------------------------------------------------------------------------

class TestUnsupportedSchema:
    ADAPTERS = "Typed adapters: insight_v1, default_v2, v2_raw, default, ui_control, widget_control."

    def test_custom1_is_refused_by_name_with_the_reason_and_the_alternatives(self):
        engine = AgentEngine(api_key="k", insight_contract="typed_v1")
        with pytest.raises(AgentConfigurationError) as ei:
            engine.register_agent(tagent(envelope(), output_format="custom1"))
        msg = str(ei.value)
        assert "schema 'custom1'" in msg and "no typed projection" in msg and self.ADAPTERS in msg
        assert engine.agents == []

    def test_custom1_still_registers_under_legacy(self):
        engine = AgentEngine(api_key="k")
        engine.register_agent(tagent(envelope(), output_format="custom1"))
        assert len(engine.agents) == 1

    def test_every_other_shipped_schema_registers_under_typed(self):
        for schema in ("insight_v1", "default_v2", "v2_raw", "default", "ui_control", "widget_control"):
            assert len(tengine(tagent(envelope(), output_format=schema)).agents) == 1, schema

    def test_control_adapterless_typed_declaration_is_the_generic_refusal(self):
        """NEGATIVE CONTROL: only a descriptor with typed_unsupported_reason gets the named message."""
        agent = tagent(envelope(), output_format="default")
        agent.descriptor = {k: v for k, v in agent.descriptor.items() if k != "typed_adapter"}
        with pytest.raises(AgentConfigurationError) as ei:
            AgentEngine(api_key="k", insight_contract="typed_v1").register_agent(agent)
        assert "without a typed_adapter" in str(ei.value) and "no typed projection" not in str(ei.value)


# ---------------------------------------------------------------------------
# EC-1 — evidence coordinates and the citations capability
# ---------------------------------------------------------------------------

SEGMENTS = [TranscriptSegment(speaker="CLIENT", text="We need both entities live by Friday.", timestamp=1.0),
            TranscriptSegment(speaker="CONSULTANT", text="Who owns the approval?", timestamp=2.0),
            TranscriptSegment(speaker="CLIENT", text="Finance, I think.", timestamp=3.5),
            TranscriptSegment(speaker="CLIENT", text="But it was proposed, not approved.", timestamp=4.0)]


def ectx(*, citations=False, reference=None):
    caps = HostInsightCapabilities(supported_types=NINE, evidence_citations=citations)
    return AgentContext(session_id="typed", turn_count=1, recent_segments=list(SEGMENTS), blackboard=Blackboard(),
                        principal_id="p-1", insight_capabilities=caps,
                        insight_reference_context=reference or InsightReferenceContext())


def hypothesis(refs):
    return envelope(cand(type="observation", urgency="whenever", observation_kind="hypothesis",
                         rationale="Approvals cluster before finance.", validation_step="Ask finance for the log.",
                         evidence_refs=refs))


def snapshot_id_in(user_message):
    return user_message.split("[snap:")[1].split(":")[0]


class TestEvidenceCoordinates:
    def consulting(self, fn, context_turns=2, agent_id="consult"):
        cfg = {"id": agent_id, "name": agent_id, "text": "You analyse.", "output_format": "insight_v1",
               "trigger_config": {"cooldown": 0}, "context_turns": context_turns,
               "insight_config": {"analysis_profile": "consulting", "allowed_types": ["fact", "observation", "warning"]}}
        agent = DynamicAgent(cfg)
        agent.llm = DeferredLLM(fn)
        return agent

    def test_segment_references_are_stamped_with_the_host_list_position(self):
        def reply(system, user):
            sid = snapshot_id_in(user)
            return hypothesis([{"kind": "segment", "ref_id": f"snap:{sid}:segment:0", "revision": None},
                               {"kind": "segment", "ref_id": f"snap:{sid}:segment:1", "revision": None}])
        final = asyncio.run(tengine(self.consulting(reply)).process_turn(ectx()))
        assert [i.type.value for i in final.insights] == ["observation"], codes(final)
        refs = final.insights[0].evidence_refs
        assert [r.source_index for r in refs] == [2, 3]          # the window is the last two of four
        snap = final.evidence_snapshots_by_agent["consult"]
        assert [(e.source_index, e.timestamp) for e in snap.entries] == [(2, 3.5), (3, 4.0)]
        assert refs[0].ref_id == f"snap:{snap.snapshot_id}:segment:0"

    def test_full_window_starts_at_zero_and_documents_carry_no_coordinate(self):
        doc = EvidenceCatalogEntry(kind="document", ref_id="minutes-3", revision="1")

        def reply(system, user):
            sid = snapshot_id_in(user)
            return hypothesis([{"kind": "segment", "ref_id": f"snap:{sid}:segment:3", "revision": None},
                               {"kind": "document", "ref_id": "minutes-3", "revision": "1"}])
        agent = self.consulting(reply, context_turns=0)
        final = asyncio.run(tengine(agent).process_turn(ectx(reference=InsightReferenceContext(evidence=[doc]))))
        assert [i.type.value for i in final.insights] == ["observation"], codes(final)
        assert [r.source_index for r in final.insights[0].evidence_refs] == [3, None]
        assert [e.source_index for e in final.evidence_snapshots_by_agent["consult"].entries] == [0, 1, 2, 3]

    def test_evidence_citations_capability_exposes_the_markers_on_a_general_run(self):
        agent = tagent(envelope(), insight_config={"allowed_types": ["fact", "warning"]})
        tengine(agent)
        run(agent.evaluate(ectx(citations=False)))
        plain_system, plain_user = (m["content"] for m in agent.llm.calls[-1]["messages"])
        run(agent.evaluate(ectx(citations=True)))
        cited_system, cited_user = (m["content"] for m in agent.llm.calls[-1]["messages"])
        assert "[snap:" not in plain_user and "An evidence reference is {" not in plain_system
        assert "[snap:" in cited_user and "An evidence reference is {" in cited_system

    def test_control_unexposed_ordinal_still_rejects(self):
        """NEGATIVE CONTROL: a coordinate never widens what may be cited."""
        def reply(system, user):
            return hypothesis([{"kind": "segment", "ref_id": f"snap:{snapshot_id_in(user)}:segment:2", "revision": None}])
        final = asyncio.run(tengine(self.consulting(reply)).process_turn(ectx()))
        assert final.insights == [] and "unknown_reference" in codes(final)

    def test_control_model_authored_source_index_rejects_the_response(self):
        def reply(system, user):
            return hypothesis([{"kind": "segment", "ref_id": f"snap:{snapshot_id_in(user)}:segment:0", "revision": None,
                                "source_index": 2}])
        final = asyncio.run(tengine(self.consulting(reply)).process_turn(ectx()))
        assert final.insights == [] and "invalid_field" in codes(final)
        assert any(d.classification == "engine_owned" and d.field_path.endswith("source_index") for d in final.diagnostics)

    def test_control_custom_producer_cannot_stamp_a_coordinate(self):
        class Producer(BaseAgent):
            def __init__(self):
                super().__init__(AgentConfig(name="prod", cooldown=0, trigger_types=[TriggerType.TURN_BASED],
                                             insight_config=InsightConfig(allowed_types=["fact"])))

            async def evaluate(self, context):
                ins = self.create_insight("Finance owns the approval.", type=InsightType.FACT)
                ins.evidence_refs = [EvidenceRef(kind="document", ref_id="minutes-3", revision="1", source_index=0)]
                return AgentResponse(insights=[ins])

        engine = AgentEngine(api_key="k", insight_contract="typed_v1")
        engine.register_agent(Producer())
        doc = EvidenceCatalogEntry(kind="document", ref_id="minutes-3", revision="1")
        final = asyncio.run(engine.process_turn(ectx(reference=InsightReferenceContext(evidence=[doc]))))
        assert final.insights == []
        assert any(d.classification == "engine_owned" and "source_index" in d.field_path for d in final.diagnostics)


# ---------------------------------------------------------------------------
# IC-1 — result-only instruction on the isolated path
# ---------------------------------------------------------------------------

class TestIsolatedInstruction:
    def test_isolated_prompt_offers_the_envelope_only_and_no_scratchpad(self):
        agent = content_agent(DEEP)
        engine = content_engine(agent)
        ctx = content_ctx()
        asyncio.run(engine.process_turn(ctx))
        live_prompt = prompt_of(agent)
        assert "[YOUR MEMORY / SCRATCHPAD]" in live_prompt and '"events"' in output_format_of(live_prompt)

        async def deep():
            handle = engine.start_content_request(ctx, "lf", InsightContentRequest(depth="detailed", request_id="r1"))
            return await handle.result()
        result = asyncio.run(deep())
        assert result.status == "accepted", [d.code for d in result.diagnostics]
        iso_prompt = prompt_of(agent)          # the isolated clone shares the recording client
        fmt = output_format_of(iso_prompt)
        assert "[YOUR MEMORY / SCRATCHPAD]" not in iso_prompt
        for key in ('"events"', '"variable_updates"', '"queue_pushes"', '"facts"', '"memory_updates"'):
            assert key not in fmt, key
        assert '"has_insight": true | false' in fmt and '"insight": null | {' in fmt
        assert "result-only" in rules_of(iso_prompt)

    def test_control_channels_returned_anyway_still_reject_the_result(self):
        """NEGATIVE CONTROL: the instruction is not the guard — effects on the isolated path still reject."""
        body = dict(DEEP)
        body["events"] = [{"name": "leak", "payload": {}}]
        agent = content_agent(body)
        engine = content_engine(agent)
        ctx = content_ctx()

        async def deep():
            return await engine.start_content_request(ctx, "lf", InsightContentRequest(depth="detailed", request_id="r2")).result()
        result = asyncio.run(deep())
        assert result.status == "rejected" and result.insight is None and result.diagnostics


# ---------------------------------------------------------------------------
# UP-1 — urgency provenance
# ---------------------------------------------------------------------------

class TestUrgencyProvenance:
    @staticmethod
    def producer(**insight_fields):
        class Producer(BaseAgent):
            def __init__(self):
                super().__init__(AgentConfig(name="prod", cooldown=0, trigger_types=[TriggerType.TURN_BASED],
                                             insight_config=InsightConfig(allowed_types=["warning"])))

            async def evaluate(self, context):
                ins = self.create_insight("The date is at risk.", type=InsightType.WARNING)
                for key, value in insight_fields.items():
                    setattr(ins, key, value)
                return AgentResponse(insights=[ins])
        return Producer()

    def test_explicit_urgency_is_provided(self):
        final, _ = turn(tengine(tagent(envelope(cand(urgency="now")))))
        ins = final.insights[0]
        assert ins.urgency == "now" and ins.urgency_provided is True

    def test_agent_default_is_not_provided(self):
        body = envelope(cand())
        del body["insight"]["urgency"]
        agent = tagent(body, insight_config={"allowed_types": ["warning"], "default_urgency": "soon"})
        final, _ = turn(tengine(agent))
        assert final.insights[0].urgency == "soon" and final.insights[0].urgency_provided is False

    def test_type_fallback_is_not_provided(self):
        body = envelope(cand())
        del body["insight"]["urgency"]
        final, _ = turn(tengine(tagent(body)))
        assert final.insights[0].urgency == "now" and final.insights[0].urgency_provided is False   # warning → now

    def test_candidate_carrying_the_flag_rejects(self):
        final, _ = turn(tengine(tagent(envelope(cand(urgency_provided=True)))))
        assert final.insights == []
        assert any(d.classification == "engine_owned" and d.field_path.endswith("urgency_provided") for d in final.diagnostics)

    def test_custom_producer_cannot_set_the_flag(self):
        engine = AgentEngine(api_key="k", insight_contract="typed_v1")
        engine.register_agent(self.producer(urgency="now", urgency_provided=True))
        final = asyncio.run(engine.process_turn(tctx()))
        assert final.insights == []
        assert any(d.field_path.endswith("urgency_provided") and d.classification == "engine_owned" for d in final.diagnostics)

    def test_custom_producer_without_staging_has_unknown_provenance(self):
        engine = AgentEngine(api_key="k", insight_contract="typed_v1")
        engine.register_agent(self.producer(urgency="now"))
        final = asyncio.run(engine.process_turn(tctx()))
        assert [i.urgency for i in final.insights] == ["now"], codes(final)
        assert final.insights[0].urgency_provided is False

    def test_legacy_projection_and_legacy_emission_carry_no_flag(self):
        final, _ = turn(tengine(tagent(envelope(cand(urgency="now")))))
        assert "urgency_provided" not in final.insights[0].model_dump_legacy()
        agent = tagent({"has_insight": True, "type": "warning", "content": "Risk.", "confidence": 0.5}, output_format="default_v2")
        legacy = asyncio.run(legacy_engine(agent).process_turn(tctx()))
        assert [i.type for i in legacy.insights] == [InsightType.WARNING] and legacy.insights[0].urgency_provided is None

    def test_control_invalid_explicit_urgency_still_rejects(self):
        """NEGATIVE CONTROL: an invalid explicit value is never defaulted into 'provided'."""
        final, _ = turn(tengine(tagent(envelope(cand(urgency="asap")))))
        assert final.insights == [] and "invalid_urgency" in codes(final)


# ---------------------------------------------------------------------------
# CS-1 — result() returns after the slot is released
# ---------------------------------------------------------------------------

class TestContentSlotOrdering:
    def make(self, gate=None):
        agent = content_agent(DEEP)
        if gate is not None:
            agent.llm = GatedRecorder(DEEP, gate)
        engine = content_engine(agent, limits={"max_concurrent_content_tasks": 1})
        return agent, engine

    def test_result_returns_only_after_the_slot_is_released_so_a_replacement_admits_at_once(self):
        async def scenario():
            gate = asyncio.Event()
            agent, engine = self.make(gate)
            ctx = content_ctx()
            first = engine.start_content_request(ctx, "lf", InsightContentRequest(depth="detailed", request_id="r1"))
            await asyncio.sleep(0)                      # the task runs and parks on the gate
            assert engine._content_active == 1 and not first.released.is_set()
            first.cancel()
            result = await first.result()
            assert result.status == "cancelled"
            assert engine._content_active == 0 and first.released.is_set()
            second = engine.start_content_request(ctx, "lf", InsightContentRequest(depth="detailed", request_id="r2"))
            assert second.task is not None, [d.classification for d in second._result.diagnostics]
            gate.set()
            return await second.result()
        result = asyncio.run(scenario())
        assert result.status == "accepted", [d.code for d in result.diagnostics]

    def test_released_alone_marks_the_same_point(self):
        async def scenario():
            gate = asyncio.Event()
            agent, engine = self.make(gate)
            handle = engine.start_content_request(content_ctx(), "lf", InsightContentRequest(depth="detailed", request_id="r1"))
            await asyncio.sleep(0)
            handle.cancel()
            await handle.released
            return engine._content_active, handle.released.is_set()
        assert asyncio.run(scenario()) == (0, True)

    def test_completed_task_and_refused_handle_release(self):
        async def completed():
            agent, engine = self.make()
            handle = engine.start_content_request(content_ctx(), "lf", InsightContentRequest(depth="detailed", request_id="r1"))
            res = await handle.result()
            return res.status, engine._content_active, handle.released.is_set()
        assert asyncio.run(completed()) == ("accepted", 0, True)

        async def refused():
            agent = content_agent(DEEP, content=None)               # no content block → refused at the entrypoint
            engine = content_engine(agent)
            handle = engine.start_content_request(content_ctx(), "lf", InsightContentRequest(depth="brief", request_id="r0"))
            res = await handle.result()
            return handle.task, res.status, handle.released.is_set(), engine._content_active
        assert asyncio.run(refused()) == (None, "rejected", True, 0)

    def test_control_without_the_release_signal_result_would_not_return(self):
        """NEGATIVE CONTROL (INV-53): result() waits on the release signal, not merely on the task."""
        async def scenario():
            agent, engine = self.make()

            def bookkeeping_only(session_id, handle):      # frees the counter but never signals
                engine._content_active = max(0, engine._content_active - 1)
            engine._release_content_task = bookkeeping_only
            handle = engine.start_content_request(content_ctx(), "lf", InsightContentRequest(depth="detailed", request_id="r1"))
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(handle.result(), 0.3)
            await handle.task                               # the task itself has completed
            return handle.task.done(), handle.released.is_set(), engine._content_active
        assert asyncio.run(scenario()) == (True, False, 0)


# ---------------------------------------------------------------------------
# CT-1 — correctable targets
# ---------------------------------------------------------------------------

BASIS_DOC = EvidenceCatalogEntry(kind="document", ref_id="minutes-3", revision="1")
BASIS = [{"kind": "document", "ref_id": "minutes-3", "revision": "1"}]


def rec(rid="i-1", correctable=True, type_="warning", agent_id="fixer"):
    return PriorInsightRecord(id=rid, session_id="typed", principal_id="p-1", agent_id=agent_id, type=type_,
                              content="The date was approved.", turn=1, status="active", correctable=correctable)


def cctx(*records):
    caps = HostInsightCapabilities(supported_types=NINE, corrections=True)
    return AgentContext(session_id="typed", turn_count=3, blackboard=Blackboard(), principal_id="p-1",
                        recent_segments=[TranscriptSegment(speaker="CLIENT", text="Was it approved?", timestamp=1.0)],
                        insight_capabilities=caps,
                        insight_reference_context=InsightReferenceContext(prior_insights=list(records), evidence=[BASIS_DOC]))


def fixer(body):
    return tagent(body, agent_id="fixer", insight_config={"allowed_types": ["warning", "correction"], "allow_correction": True})


def correction(target="i-1"):
    return envelope(cand(type="correction", content="Correction: the date was proposed, not approved.", urgency="now",
                         evidence_refs=BASIS,
                         correction={"target_insight_id": target, "operation": "replace", "reason": "It was not approved."}))


class TestCorrectableTargets:
    def test_non_correctable_record_is_not_offered(self):
        agent = fixer(None)
        tengine(agent)
        run(agent.evaluate(cctx(rec("i-1", correctable=False), rec("i-2"))))
        listing = rules_of(prompt_of(agent))
        assert "i-2 (turn 1)" in listing and "i-1 (turn 1)" not in listing

    def test_correction_naming_a_non_correctable_record_is_rejected(self):
        final = asyncio.run(tengine(fixer(correction("i-1"))).process_turn(cctx(rec("i-1", correctable=False))))
        assert final.insights == [] and "invalid_correction_target" in codes(final)
        assert any(d.classification == "target_not_correctable" for d in final.diagnostics)

    def test_correctable_record_is_offered_and_corrected(self):
        agent = fixer(correction("i-1"))
        final = asyncio.run(tengine(agent).process_turn(cctx(rec("i-1"))))
        assert [i.type.value for i in final.insights] == ["correction"], codes(final)
        assert "i-1 (turn 1)" in rules_of(prompt_of(agent))

    def test_answers_still_validate_against_a_non_correctable_question(self):
        question = rec("q-1", correctable=False, type_="question")
        answer = InsightAnswer(event_id="e1", question_insight_id="q-1", principal_id="p-1", status="answered", text="Finance.")
        valid, issues = validate_answers([answer], [question], "typed", "p-1")
        assert valid == [answer] and issues == []

    def test_control_unknown_target_is_still_unknown(self):
        """NEGATIVE CONTROL: the new check masks none of the earlier ones."""
        issue = validate_correction_target({"target_insight_id": "nope"}, prior_insights=[rec("i-1", correctable=False)],
                                           session_id="typed", principal_id="p-1", turn_count=3, agent_id="fixer")
        assert issue.classification == "unknown_target"


# ---------------------------------------------------------------------------
# DS-1 — data_by_agent
# ---------------------------------------------------------------------------

class TestDataByAgent:
    A1 = {"target_widget": "goals_widget", "action": "update", "payload": {"a": 1}}
    A2 = {"target_widget": "sentiment_meter", "action": "set", "payload": {"b": 2}}

    def widget(self, agent_id, body):
        return tagent(body, output_format="widget_control", agent_id=agent_id, insight_config={"allowed_types": ["suggestion"]})

    def test_each_agents_sidecar_is_attributed_and_the_merge_keeps_its_shape(self):
        w1 = self.widget("w1", {"ui_actions": [self.A1], "state_snapshot": {}})
        w2 = self.widget("w2", {"ui_actions": [self.A2], "state_snapshot": {}})
        final, _ = turn(tengine(w1, w2))
        assert final.data["ui_actions"] == [self.A1, self.A2]
        assert final.data_by_agent == {"w1": {"ui_actions": [self.A1]}, "w2": {"ui_actions": [self.A2]}}

    def test_rejected_agent_contributes_to_neither(self):
        w1 = self.widget("w1", {"ui_actions": [self.A1], "state_snapshot": {}})
        bad = self.widget("bad", {"insight": cand(type="praise"), "ui_actions": [self.A2]})    # praise not allowed
        final, _ = turn(tengine(w1, bad))
        assert final.acceptance_by_agent["bad"] == "rejected"
        assert final.data["ui_actions"] == [self.A1] and "bad" not in final.data_by_agent

    def test_per_agent_responses_leave_it_empty(self):
        agent = self.widget("w1", {"ui_actions": [self.A1]})
        tengine(agent)
        resp = run(agent.evaluate(tctx()))
        assert resp.data == {"ui_actions": [self.A1]} and resp.data_by_agent == {}

    def test_control_attribution_is_a_copy_not_an_alias(self):
        """NEGATIVE CONTROL: mutating the attribution never changes the merged sidecar."""
        w1 = self.widget("w1", {"ui_actions": [self.A1], "state_snapshot": {}})
        final, _ = turn(tengine(w1))
        final.data_by_agent["w1"]["ui_actions"].append({"target_widget": "x", "action": "set", "payload": {}})
        assert final.data["ui_actions"] == [self.A1]
