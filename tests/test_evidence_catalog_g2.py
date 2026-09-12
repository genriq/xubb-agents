"""G2 part 1 — per-agent snapshot evidence catalog and reference resolution.

Framework-scope leaves registered in docs/CONTRACTS.yaml:

  ITC-15.FW  references resolve only to evidence actually exposed to the agent, in
             this session, at the catalog's revision; anything else rejects
  ITC-16.FW  general observations need no evidence; consulting hypotheses and
             implications need resolvable evidence plus their support fields
  ITC-14.FW  (extended) the host reference context survives both phases

Everything runs through the real engine under typed_v1 with a faked LLM.
"""
import asyncio
import json

import pytest

from xubb_agents import AgentEngine, DynamicAgent, AgentContext, Blackboard, HostInsightCapabilities
from xubb_agents.core.agent import AgentConfig, BaseAgent
from xubb_agents.core.insight_validation import (
    HUMAN_WIRE_VALUES, ReferenceContext, snapshot_catalog, snapshot_ref,
)
from xubb_agents.core.models import (
    AgentResponse, InsightReferenceContext, EvidenceCatalogEntry, PriorInsightRecord,
    TranscriptSegment, TriggerType, Event,
)

from tests.test_dynamic_agent import FakeLLM, run
from tests.test_typed_acceptance_g1 import tengine, envelope, cand, codes

SEGMENTS = [TranscriptSegment(speaker="CLIENT", text="We need both entities live by Friday.", timestamp=1.0),
            TranscriptSegment(speaker="CONSULTANT", text="Who owns the approval?", timestamp=2.0),
            TranscriptSegment(speaker="CLIENT", text="Finance, I think.", timestamp=3.0),
            TranscriptSegment(speaker="CLIENT", text="Finance, I think.", timestamp=3.0)]   # identical occurrence


def ctx(*, reference=None, principal="p-1", rag=None, session="typed"):
    return AgentContext(session_id=session, turn_count=1, recent_segments=list(SEGMENTS),
                        rag_docs=rag or [], blackboard=Blackboard(), principal_id=principal,
                        insight_capabilities=HostInsightCapabilities(supported_types=list(HUMAN_WIRE_VALUES)),
                        insight_reference_context=reference or InsightReferenceContext())


def consulting_agent(result, *, context_turns=6, agent_id="consult", allowed=None):
    cfg = {"id": agent_id, "name": agent_id, "text": "You analyse.", "output_format": "insight_v1",
           "trigger_config": {"cooldown": 0}, "context_turns": context_turns,
           "insight_config": {"analysis_profile": "consulting",
                              "allowed_types": allowed or ["fact", "observation", "suggestion", "warning"]}}
    agent = DynamicAgent(cfg)
    agent.llm = FakeLLM(result)
    return agent


def hypothesis(refs, **over):
    body = cand(type="observation", urgency="whenever", observation_kind="hypothesis",
                rationale="Approvals cluster before finance.", validation_step="Ask finance for the approval log.",
                evidence_refs=refs)
    body.update(over)
    return body


class DeferredLLM:
    """Returns a result computed from the prompt the agent actually sent, so a
    test can cite ids the model could only have learned from the catalog."""

    def __init__(self, fn):
        self.fn = fn
        self.calls = []

    async def generate_json(self, model=None, messages=None, **kw):
        self.calls.append({"model": model, "messages": messages})
        return self.fn(messages[0]["content"], messages[1]["content"])


def snapshot_id_from(final, agent_id):
    return final.evidence_snapshots_by_agent[agent_id].snapshot_id


# ---------------------------------------------------------------------------
# Reference-compatible catalog function (package checks reproduced)
# ---------------------------------------------------------------------------

class TestSnapshotCatalogFunction:
    SRC = [{"text": "Repeated text", "speaker": "client", "timestamp": 1},
           {"text": "Repeated text", "speaker": "client", "timestamp": 1}]

    def test_copies_snapshot(self):
        src = [dict(s) for s in self.SRC]
        catalog = snapshot_catalog(src, "inv1")
        src[0]["text"] = "Mutated after snapshot"
        assert catalog[0]["source"]["text"] == "Repeated text"

    def test_distinguishes_identical_occurrences(self):
        catalog = snapshot_catalog(self.SRC, "inv1")
        assert catalog[0]["ref_id"] != catalog[1]["ref_id"]
        assert [c["ref_id"] for c in catalog] == ["snap:inv1:segment:0", "snap:inv1:segment:1"]

    def test_only_exposed_material(self):
        assert len(snapshot_catalog([self.SRC[1]], "inv2")) == 1

    def test_invocation_refs_are_not_durable_identity(self):
        assert snapshot_catalog([self.SRC[1]], "inv3")[0]["ref_id"] != snapshot_catalog([self.SRC[1]], "inv2")[0]["ref_id"]

    def test_invalid_snapshot_id(self):
        with pytest.raises(ValueError, match="invalid_snapshot_id"):
            snapshot_catalog(self.SRC, " ")


class TestReferenceContextResolution:
    def make(self):
        rc = ReferenceContext(session_id="s1", snapshot_id="snapA")
        rc.add("segment", snapshot_ref("snapA", "segment", 0), "snapA")
        rc.add("document", "doc-7", "rev-2")
        rc.add("fact", "budget.primary", None)
        rc.add("insight", "ins-9", None, session_id="s1")
        rc.add("document", "foreign-doc", "r1", session_id="OTHER")
        return rc

    def test_resolves_null_revision_to_current(self):
        issue, rev = self.make().resolve({"kind": "segment", "ref_id": "snap:snapA:segment:0", "revision": None}, "p")
        assert issue is None and rev == "snapA"

    def test_exact_revision_required_when_stated(self):
        rc = self.make()
        assert rc.resolve({"kind": "document", "ref_id": "doc-7", "revision": "rev-2"}, "p")[0] is None
        issue, _ = rc.resolve({"kind": "document", "ref_id": "doc-7", "revision": "rev-1"}, "p")
        assert issue.code == "unknown_reference" and issue.classification == "revision_mismatch"

    def test_unknown_and_cross_session(self):
        rc = self.make()
        assert rc.resolve({"kind": "segment", "ref_id": "snap:snapA:segment:9", "revision": None}, "p")[0].code == "unknown_reference"
        issue, _ = rc.resolve({"kind": "document", "ref_id": "foreign-doc", "revision": None}, "p")
        assert issue.code == "cross_session_reference" and issue.classification == "OTHER"

    def test_kind_is_part_of_identity(self):
        assert self.make().resolve({"kind": "document", "ref_id": "budget.primary", "revision": None}, "p")[0].code == "unknown_reference"


# ---------------------------------------------------------------------------
# ITC-15.FW — through the engine
# ---------------------------------------------------------------------------

class TestReferencesResolveOnlyToExposedEvidence:
    def test_citing_the_shown_segment_resolves_and_revision_is_filled(self):
        def reply(system, user):
            rid = user.split("[")[1].split("]")[0]                # first marker in the transcript
            return envelope(hypothesis([{"kind": "segment", "ref_id": rid, "revision": None}]))
        agent = consulting_agent(None); agent.llm = DeferredLLM(reply)
        engine = tengine(agent)
        final, _ = asyncio.run(engine.process_turn(ctx())), None
        assert [i.type.value for i in final.insights] == ["observation"]
        ins = final.insights[0]
        sid = snapshot_id_from(final, "consult")
        assert ins.observation_kind == "hypothesis"
        # v2.8 (EC-1): the engine stamps the segment's position in the host's list (a full window here)
        assert [r.model_dump() for r in ins.evidence_refs] == [{"kind": "segment", "ref_id": f"snap:{sid}:segment:0",
                                                                 "revision": sid, "source_index": 0}]

    def test_reference_outside_the_trimmed_window_is_unknown(self):
        """NEGATIVE CONTROL: the agent sees the last 2 segments; segment 3 of the
        full transcript is NOT exposed to it, so it cannot be cited."""
        def reply(system, user):
            sid = user.split("[snap:")[1].split(":")[0]
            return envelope(hypothesis([{"kind": "segment", "ref_id": f"snap:{sid}:segment:3", "revision": None}]))
        agent = consulting_agent(None, context_turns=2); agent.llm = DeferredLLM(reply)
        final = asyncio.run(tengine(agent).process_turn(ctx()))
        assert final.insights == [] and "unknown_reference" in codes(final)
        snap = final.evidence_snapshots_by_agent["consult"]
        assert len(snap.entries) == 2 and all(e.kind == "segment" for e in snap.entries)

    def test_invented_and_stale_revision_ids_reject(self):
        agent = consulting_agent(envelope(hypothesis([{"kind": "segment", "ref_id": "snap:made-up:segment:0", "revision": None}])))
        final = asyncio.run(tengine(agent).process_turn(ctx()))
        assert "unknown_reference" in codes(final) and final.insights == []

        def stale(system, user):
            sid = user.split("[snap:")[1].split(":")[0]
            return envelope(hypothesis([{"kind": "segment", "ref_id": f"snap:{sid}:segment:0", "revision": "older"}]))
        agent2 = consulting_agent(None); agent2.llm = DeferredLLM(stale)
        final = asyncio.run(tengine(agent2).process_turn(ctx()))
        d = next(d for d in final.diagnostics if d.code == "unknown_reference")
        assert d.classification == "revision_mismatch"

    def test_host_supplied_document_and_prior_insight_resolve_cross_session_rejects(self):
        reference = InsightReferenceContext(
            evidence=[EvidenceCatalogEntry(kind="document", ref_id="scope-01", revision="1", excerpt="Scope: one entity."),
                      EvidenceCatalogEntry(kind="document", ref_id="other-session-doc", revision="1", session_id="elsewhere")],
            prior_insights=[PriorInsightRecord(id="i-prev", session_id="typed", agent_id="consult", type="fact",
                                               content="One entity in scope.", turn=0)])
        ok = consulting_agent(envelope(hypothesis([{"kind": "document", "ref_id": "scope-01", "revision": "1"},
                                                   {"kind": "insight", "ref_id": "i-prev", "revision": None}])))
        final = asyncio.run(tengine(ok).process_turn(ctx(reference=reference)))
        assert [i.type.value for i in final.insights] == ["observation"]
        assert [r.ref_id for r in final.insights[0].evidence_refs] == ["scope-01", "i-prev"]

        foreign = consulting_agent(envelope(hypothesis([{"kind": "document", "ref_id": "other-session-doc", "revision": "1"}])))
        final = asyncio.run(tengine(foreign).process_turn(ctx(reference=reference)))
        assert "cross_session_reference" in codes(final) and final.insights == []

    def test_exposed_rag_document_is_citable_and_listed_in_snapshot(self):
        def reply(system, user):
            sid = user.split("[snap:")[1].split(":")[0]
            return envelope(hypothesis([{"kind": "document", "ref_id": f"snap:{sid}:document:0", "revision": None}]))
        agent = consulting_agent(None); agent.llm = DeferredLLM(reply)
        final = asyncio.run(tengine(agent).process_turn(ctx(rag=["Contract clause 4: approvals by finance."])))
        assert [i.type.value for i in final.insights] == ["observation"]
        snap = final.evidence_snapshots_by_agent["consult"]
        assert [e.kind for e in snap.entries] == ["segment"] * 4 + ["document"]
        assert snap.entries[-1].excerpt.startswith("Contract clause 4")

    def test_identical_occurrences_are_distinct_references(self):
        agent = consulting_agent(envelope())
        final = asyncio.run(tengine(agent).process_turn(ctx()))
        entries = final.evidence_snapshots_by_agent["consult"].entries
        assert entries[2].excerpt == entries[3].excerpt and entries[2].ref_id != entries[3].ref_id

    def test_snapshot_ids_differ_per_invocation(self):
        agent = consulting_agent(envelope())
        engine = tengine(agent)
        a = snapshot_id_from(asyncio.run(engine.process_turn(ctx())), "consult")
        b = snapshot_id_from(asyncio.run(engine.process_turn(ctx())), "consult")
        assert a != b


# ---------------------------------------------------------------------------
# ITC-16.FW — general evidence optional; subtype support mandatory
# ---------------------------------------------------------------------------

class TestEvidenceRequirements:
    def test_general_observation_needs_no_evidence(self):
        agent = consulting_agent(envelope(cand(type="observation", urgency="whenever")))
        final = asyncio.run(tengine(agent).process_turn(ctx()))
        assert [i.type.value for i in final.insights] == ["observation"]
        assert final.insights[0].evidence_refs == [] and final.insights[0].observation_kind is None

    def test_general_profile_agent_has_no_citation_markers_in_prompt(self):
        from tests.test_typed_acceptance_g1 import tagent
        agent = tagent(envelope())
        tengine(agent)
        run(agent.evaluate(ctx()))
        user = agent.llm.calls[-1]["messages"][1]["content"]
        assert "[snap:" not in user

    def test_consulting_prompt_shows_markers_and_citation_contract(self):
        agent = consulting_agent(envelope())
        tengine(agent)
        run(agent.evaluate(ctx(reference=InsightReferenceContext(
            evidence=[EvidenceCatalogEntry(kind="fact", ref_id="budget.primary", revision=None)]))))
        system, user = (m["content"] for m in agent.llm.calls[-1]["messages"])
        assert user.startswith("### TRANSCRIPT:\n[snap:")
        assert "never invent an id" in system and "fact:budget.primary" in system

    def test_hypothesis_without_evidence_is_missing_evidence(self):
        agent = consulting_agent(envelope(hypothesis([])))
        final = asyncio.run(tengine(agent).process_turn(ctx()))
        assert "missing_evidence" in codes(final) and final.insights == []

    def test_implication_requires_rationale_and_evidence(self):
        def reply(system, user):
            rid = user.split("[")[1].split("]")[0]
            return envelope(cand(type="observation", urgency="whenever", observation_kind="implication",
                                 evidence_refs=[{"kind": "segment", "ref_id": rid, "revision": None}]))
        agent = consulting_agent(None); agent.llm = DeferredLLM(reply)
        final = asyncio.run(tengine(agent).process_turn(ctx()))
        assert any(d.classification == "implication_requires_rationale" for d in final.diagnostics)

        def good(system, user):
            rid = user.split("[")[1].split("]")[0]
            return envelope(cand(type="observation", urgency="whenever", observation_kind="implication",
                                 rationale="Transaction-level reconciliation needs per-transaction data.",
                                 evidence_refs=[{"kind": "segment", "ref_id": rid, "revision": None}]))
        agent2 = consulting_agent(None); agent2.llm = DeferredLLM(good)
        final = asyncio.run(tengine(agent2).process_turn(ctx()))
        assert final.insights[0].observation_kind == "implication"

    def test_subtypes_stay_out_of_the_general_profile(self):
        from tests.test_typed_acceptance_g1 import tagent
        agent = tagent(envelope(hypothesis([])))
        final = asyncio.run(tengine(agent).process_turn(ctx()))
        assert any(d.classification == "consulting_profile_required" for d in final.diagnostics)


# ---------------------------------------------------------------------------
# ITC-14.FW (extension) — reference context propagates through both phases
# ---------------------------------------------------------------------------

class Capture(BaseAgent):
    def __init__(self, name, emit=False, subscribed=None):
        super().__init__(AgentConfig(name=name, cooldown=0, trigger_types=[TriggerType.TURN_BASED, TriggerType.EVENT],
                                     subscribed_events=subscribed))
        self.seen = []
        self.emit = emit

    async def evaluate(self, context):
        self.seen.append((context.phase, context.insight_reference_context.model_copy(deep=True)))
        resp = AgentResponse()
        if self.emit:
            resp.events.append(Event(name="ping", payload={}, source_agent=self.config.id, timestamp=1.0))
        return resp


class TestReferenceContextPropagation:
    def test_reference_context_reaches_phase1_and_phase2_unchanged(self):
        reference = InsightReferenceContext(evidence=[EvidenceCatalogEntry(kind="document", ref_id="d1", revision="1")])
        engine = AgentEngine(api_key="k", insight_contract="typed_v1")
        p1 = Capture("p1", emit=True); p2 = Capture("p2", subscribed=["ping"])
        engine.register_agent(p1); engine.register_agent(p2)
        asyncio.run(engine.process_turn(ctx(reference=reference)))
        phases = {phase: rc for agent in (p1, p2) for phase, rc in agent.seen}
        assert set(phases) == {1, 2} and all(rc == reference for rc in phases.values())

    def test_snapshot_serializes_on_the_aggregate(self):
        agent = consulting_agent(envelope(cand(type="observation", urgency="whenever")))
        final = asyncio.run(tengine(agent).process_turn(ctx()))
        dumped = json.loads(final.model_dump_json())
        snap = dumped["evidence_snapshots_by_agent"]["consult"]
        assert snap["agent_id"] == "consult" and len(snap["entries"]) == 4
        assert snap["entries"][0]["ref_id"] == f"snap:{snap['snapshot_id']}:segment:0"
