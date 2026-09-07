"""G3 part 2 — the correction lifecycle (spec §10).

Framework-scope leaves registered in docs/CONTRACTS.yaml:

  ITC-18.FW  a correction targets a previously emitted, active, human-facing insight from an
             earlier turn in the same session for the same principal, with a separate
             evidence basis; own-agent authority by default, host allowlist otherwise
  ITC-20.FW  correction-bearing responses are held whole and arbitrated at phase close:
             deterministic priority/registration order, all-or-nothing target reservation,
             losers commit nothing, earlier-phase reservations stand, duplicates reject

Host delivery (ITC-19) — marking the target superseded/withdrawn, never redisplaying it
as current — is a conformance run and not claimed here.
"""
import asyncio

import pytest

from xubb_agents import AgentEngine, DynamicAgent, AgentContext, Blackboard, HostInsightCapabilities
from xubb_agents.core.agent import AgentConfig, BaseAgent
from xubb_agents.core.insight_validation import (
    HUMAN_WIRE_VALUES, IMPLEMENTED_TYPED_TYPES, validate_correction_target, effective_insight_types,
)
from xubb_agents.core.models import (
    AgentResponse, InsightType, InsightConfig, InsightReferenceContext, PriorInsightRecord,
    EvidenceCatalogEntry, EvidenceRef, CorrectionPayload, TranscriptSegment, TriggerType, Event, Fact,
)

from tests.test_dynamic_agent import FakeLLM, run
from tests.test_legacy_acceptance_g0 import Recording
from tests.test_typed_acceptance_g1 import envelope, cand, codes

NINE = list(HUMAN_WIRE_VALUES)


def record(rid="i-1", agent_id="fixer", turn=1, status="active", session="s", principal="p-1", type_="warning"):
    return PriorInsightRecord(id=rid, session_id=session, principal_id=principal, agent_id=agent_id, type=type_,
                              content="The date was approved.", turn=turn, status=status)


def caps(**over):
    base = dict(supported_types=NINE, corrections=True)
    base.update(over)
    return HostInsightCapabilities(**base)


def ctx(*, prior=None, capabilities=None, principal="p-1", turn_count=3, evidence=None):
    return AgentContext(session_id="s", turn_count=turn_count, blackboard=Blackboard(), principal_id=principal,
                        recent_segments=[TranscriptSegment(speaker="CLIENT", text="Was the date approved?", timestamp=1.0)],
                        insight_capabilities=capabilities or caps(),
                        insight_reference_context=InsightReferenceContext(
                            prior_insights=prior if prior is not None else [record()],
                            evidence=evidence or [EvidenceCatalogEntry(kind="document", ref_id="minutes-3", revision="1")]))


BASIS = [{"kind": "document", "ref_id": "minutes-3", "revision": "1"}]


def correction(target="i-1", operation="replace", refs=BASIS, **over):
    body = cand(type="correction", content="Correction: the date was proposed, not approved.", urgency="now",
                correction={"target_insight_id": target, "operation": operation, "reason": "The minutes show no approval."},
                evidence_refs=refs)
    body.update(over)
    return body


def fixer(result, *, agent_id="fixer", priority=0):
    a = DynamicAgent({"id": agent_id, "name": agent_id, "text": "You repair your own mistakes.", "output_format": "insight_v1",
                      "trigger_config": {"cooldown": 0, "priority": priority},
                      "insight_config": {"allowed_types": ["fact", "correction"], "allow_correction": True}})
    a.llm = FakeLLM(result)
    return a


def engine(*agents, callbacks=None):
    e = AgentEngine(api_key="k", insight_contract="typed_v1", callbacks=callbacks or [])
    for a in agents:
        llm = getattr(a, "llm", None)
        e.register_agent(a)
        if isinstance(a, DynamicAgent):
            a.llm = llm
    return e


def turn(e, c=None):
    c = c or ctx()
    return asyncio.run(e.process_turn(c)), c


class Corrector(BaseAgent):
    """Custom agent emitting an arbitrary set of corrections (plus a sibling fact and state)."""

    def __init__(self, name, targets, priority=0, sibling=True, phase2=False):
        super().__init__(AgentConfig(name=name, cooldown=0, priority=priority,
                                     trigger_types=[TriggerType.EVENT] if phase2 else [TriggerType.TURN_BASED, TriggerType.EVENT],
                                     subscribed_events=["ping"] if phase2 else None,
                                     insight_config=InsightConfig(allowed_types=["fact", "correction"], allow_correction=True)))
        self.targets = targets
        self.sibling = sibling

    async def evaluate(self, context):
        resp = AgentResponse()
        for t in self.targets:
            ins = self.create_insight("Correction: the date was proposed, not approved.", type=InsightType.CORRECTION)
            ins.correction = CorrectionPayload(target_insight_id=t, operation="replace", reason="Minutes show no approval.")
            ins.evidence_refs = [EvidenceRef(kind="document", ref_id="minutes-3", revision="1")]
            resp.insights.append(ins)
        if self.sibling:
            resp.insights.append(self.create_insight(f"{self.config.id} sibling fact", type=InsightType.FACT))
            resp.variable_updates[f"{self.config.id}_ran"] = True
            resp.facts.append(Fact(type="ran", key=self.config.id, value=True, source_agent=self.config.id, timestamp=1.0))
        return resp


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

class TestAvailability:
    def test_correction_is_implemented_and_needs_history(self):
        assert "correction" in IMPLEMENTED_TYPED_TYPES
        base = dict(contract="typed_v1", allowed_types=NINE, allow_reply=True, allow_question=True, allow_correction=True,
                    schema_supported=None, host_supported=NINE, host_reply_drafts=True, host_text_questions=True,
                    host_corrections=True, principal_present=True)
        assert "correction" in effective_insight_types(**base)
        e = effective_insight_types(**base, history_present=False)
        assert e.unavailable["correction"] == "missing_history" and e.diagnostic_code_for("correction") == "capability_unavailable"

    def test_no_history_this_run_is_capability_unavailable(self):
        final, _ = turn(engine(fixer(envelope(correction()))), ctx(prior=[]))
        assert final.insights == []
        assert any(d.code == "capability_unavailable" and d.classification == "correction:missing_history" for d in final.diagnostics)

    def test_host_without_corrections_or_agent_without_flag(self):
        final, _ = turn(engine(fixer(envelope(correction()))), ctx(capabilities=caps(corrections=False)))
        assert any(d.classification == "correction_not_permitted" for d in final.diagnostics) and final.insights == []


# ---------------------------------------------------------------------------
# ITC-18.FW — target validation
# ---------------------------------------------------------------------------

class TestTargetValidation:
    def test_valid_self_correction_is_accepted(self):
        final, _ = turn(engine(fixer(envelope(correction()))))
        assert [i.type for i in final.insights] == [InsightType.CORRECTION]
        ins = final.insights[0]
        assert ins.correction == CorrectionPayload(target_insight_id="i-1", operation="replace", reason="The minutes show no approval.")
        assert ins.evidence_refs[0].ref_id == "minutes-3" and ins.id and ins.turn == 3

    def test_withdraw_is_accepted(self):
        final, _ = turn(engine(fixer(envelope(correction(operation="withdraw")))))
        assert final.insights[0].correction.operation == "withdraw"

    @pytest.mark.parametrize("prior,cls,code", [
        ([], "unknown_target", "invalid_correction_target"),
        ([record(rid="other")], "unknown_target", "invalid_correction_target"),
        ([record(turn=3)], "same_turn_deferred", "invalid_correction_target"),
        ([record(turn=5)], "same_turn_deferred", "invalid_correction_target"),
        ([record(status="superseded")], "target_superseded", "invalid_correction_target"),
        ([record(status="withdrawn")], "target_withdrawn", "invalid_correction_target"),
        ([record(principal="someone-else")], "principal_mismatch", "invalid_correction_target"),
        ([record(type_="error")], "target_not_human_facing", "invalid_correction_target"),
        ([record(agent_id="another_agent")], "not_authorized", "invalid_correction_target"),
        ([record(session="elsewhere")], "elsewhere", "cross_session_reference"),
    ])
    def test_invalid_targets_reject_whole_response(self, prior, cls, code):
        c = ctx(prior=prior) if prior else ctx(prior=[record(rid="unrelated")])
        if not prior:
            c = ctx(prior=[record(rid="unrelated")])
        final, c2 = turn(engine(fixer(envelope(correction(), facts=[{"type": "x", "key": "k", "value": 1, "confidence": 0.5}]))), c)
        if not prior:
            # empty history is capability_unavailable (tested above); here the target is simply unknown
            assert final.insights == []
            return
        assert final.insights == [] and "fact" not in [i.type.value for i in final.insights]
        d = next(d for d in final.diagnostics if d.code == code)
        assert d.classification == cls
        assert not c2.blackboard.has_fact("x", "k")   # whole response rejected

    def test_allowlisted_agent_may_repair_another_agents_insight(self):
        other_target = [record(agent_id="observer")]
        final, _ = turn(engine(fixer(envelope(correction()))),
                        ctx(prior=other_target, capabilities=caps(correction_agent_policy="allowlisted", correction_agent_ids=["fixer"])))
        assert [i.type for i in final.insights] == [InsightType.CORRECTION]
        # a non-listed agent under the same policy stays own-only
        final, _ = turn(engine(fixer(envelope(correction()))),
                        ctx(prior=other_target, capabilities=caps(correction_agent_policy="allowlisted", correction_agent_ids=["someone"])))
        assert any(d.classification == "not_authorized" for d in final.diagnostics)

    def test_model_cannot_grant_itself_authority(self):
        """NEGATIVE CONTROL: nothing in the payload or metadata widens authority."""
        body = correction(metadata={"authority": "all", "correction_agent_policy": "allowlisted"})
        final, _ = turn(engine(fixer(envelope(body))), ctx(prior=[record(agent_id="observer")]))
        assert any(d.classification == "not_authorized" for d in final.diagnostics) and final.insights == []

    def test_basis_is_required_and_must_resolve(self):
        final, _ = turn(engine(fixer(envelope(correction(refs=[])))))
        assert any(d.code == "missing_evidence" and d.classification == "correction_requires_basis" for d in final.diagnostics)
        final, _ = turn(engine(fixer(envelope(correction(refs=[{"kind": "document", "ref_id": "made-up", "revision": None}])))))
        assert "unknown_reference" in codes(final)

    def test_correction_payload_on_other_types_and_missing_payload_reject(self):
        final, _ = turn(engine(fixer(envelope(cand(type="fact", urgency="whenever",
                                                    correction={"target_insight_id": "i-1", "operation": "replace", "reason": "r"})))))
        assert any(d.classification == "payload_on_non_correction" for d in final.diagnostics)
        no_payload = dict(correction()); del no_payload["correction"]
        final, _ = turn(engine(fixer(envelope(no_payload))))
        assert "invalid_correction_target" in codes(final)

    def test_pure_validator_rules(self):
        payload = {"target_insight_id": "i-1", "operation": "replace", "reason": "r"}
        common = dict(prior_insights=[record()], session_id="s", principal_id="p-1", turn_count=3, agent_id="fixer")
        assert validate_correction_target(payload, **common) is None
        assert validate_correction_target(payload, **dict(common, agent_id="x")).classification == "not_authorized"
        assert validate_correction_target(payload, **dict(common, agent_id="x"), policy="allowlisted", allowlist=("x",)) is None
        assert validate_correction_target(payload, **dict(common, turn_count=1)).classification == "same_turn_deferred"

    def test_prompt_lists_own_correctable_messages_only(self):
        a = fixer(envelope()); engine(a)
        run(a.evaluate(ctx(prior=[record(rid="mine", agent_id="fixer"), record(rid="theirs", agent_id="observer"),
                                  record(rid="now", agent_id="fixer", turn=3)])))
        system = a.llm.calls[-1]["messages"][0]["content"]
        assert "mine (turn 1)" in system and "theirs" not in system and "now (turn 3)" not in system
        assert "repairs YOUR OWN earlier message" in system


# ---------------------------------------------------------------------------
# ITC-20.FW — whole-response buffering and arbitration
# ---------------------------------------------------------------------------

class TestArbitration:
    def test_higher_priority_wins_loser_commits_nothing(self):
        cb = Recording()
        low = Corrector("low", ["i-1"], priority=1)
        high = Corrector("high", ["i-1"], priority=5)
        both = ctx(prior=[record(agent_id="low")],
                   capabilities=caps(correction_agent_policy="allowlisted", correction_agent_ids=["low", "high"]))
        final, c = turn(engine(low, high, callbacks=[cb]), both)
        corrections = [i for i in final.insights if i.type is InsightType.CORRECTION]
        assert [i.agent_id for i in corrections] == ["high"]
        assert final.acceptance_by_agent == {"low": "rejected", "high": "accepted"}
        # the loser's siblings and state never committed; the winner's did
        assert [i.content for i in final.insights if i.type is InsightType.FACT] == ["high sibling fact"]
        assert c.blackboard.get_var("high_ran") is True and c.blackboard.get_var("low_ran") is None
        assert c.blackboard.has_fact("ran", "high") and not c.blackboard.has_fact("ran", "low")
        d = next(d for d in final.diagnostics if d.code == "correction_conflict")
        assert d.agent_id == "low" and d.classification == "target_already_reserved"
        assert [i.agent_id for i in cb.validation] == ["low"] and cb.validation[0].code == "correction_conflict"

    def test_equal_priority_later_registration_wins_independent_of_arrival(self):
        def both():
            return ctx(prior=[record(agent_id="first")],
                       capabilities=caps(correction_agent_policy="allowlisted", correction_agent_ids=["first", "second"]))
        first = Corrector("first", ["i-1"]); second = Corrector("second", ["i-1"])
        final, _ = turn(engine(first, second), both())
        assert final.acceptance_by_agent == {"first": "rejected", "second": "accepted"}
        # register in the other order → the other one wins: registration, not name or arrival
        final, _ = turn(engine(second, first), both())
        assert final.acceptance_by_agent == {"second": "rejected", "first": "accepted"}

    def test_multi_target_is_all_or_nothing(self):
        prior = [record(rid="i-1", agent_id="a"), record(rid="i-2", agent_id="a")]
        c = ctx(prior=prior, capabilities=caps(correction_agent_policy="allowlisted", correction_agent_ids=["a", "b"]))
        # b (higher) takes i-2; a wants both i-1 and i-2 → a loses whole, i-1 stays unreserved
        a = Corrector("a", ["i-1", "i-2"], priority=1); b = Corrector("b", ["i-2"], priority=5)
        final, _ = turn(engine(a, b), c)
        assert final.acceptance_by_agent == {"a": "rejected", "b": "accepted"}
        # with a higher, a reserves both together and b loses
        c = ctx(prior=prior, capabilities=caps(correction_agent_policy="allowlisted", correction_agent_ids=["a", "b"]))
        a = Corrector("a", ["i-1", "i-2"], priority=9); b = Corrector("b", ["i-2"], priority=5)
        final, _ = turn(engine(a, b), c)
        assert final.acceptance_by_agent == {"a": "accepted", "b": "rejected"}
        assert sorted(i.correction.target_insight_id for i in final.insights if i.type is InsightType.CORRECTION) == ["i-1", "i-2"]

    def test_duplicate_targets_within_one_response_reject_it(self):
        dup = Corrector("dup", ["i-1", "i-1"])
        final, c = turn(engine(dup), ctx(prior=[record(agent_id="dup")]))
        assert final.acceptance_by_agent == {"dup": "rejected"}
        assert any(d.classification == "duplicate_targets_in_response" for d in final.diagnostics)
        assert c.blackboard.get_var("dup_ran") is None

    def test_earlier_phase_reservation_cannot_be_overturned_by_phase_two(self):
        class Pinger(BaseAgent):
            def __init__(self):
                super().__init__(AgentConfig(name="pinger", cooldown=0, trigger_types=[TriggerType.TURN_BASED]))
            async def evaluate(self, context):
                return AgentResponse(events=[Event(name="ping", payload={}, source_agent="pinger", timestamp=1.0)])
        p1 = Corrector("p1", ["i-1"], priority=1)
        p2 = Corrector("p2", ["i-1"], priority=99, phase2=True)   # higher priority, but later phase
        c = ctx(prior=[record(agent_id="p1")], capabilities=caps(correction_agent_policy="allowlisted", correction_agent_ids=["p1", "p2"]))
        final, _ = turn(engine(Pinger(), p1, p2), c)
        assert final.acceptance_by_agent["p1"] == "accepted" and final.acceptance_by_agent["p2"] == "rejected"
        assert any(d.agent_id == "p2" and d.code == "correction_conflict" for d in final.diagnostics)

    def test_no_conflict_means_all_commit(self):
        a = Corrector("a", ["i-1"]); b = Corrector("b", ["i-2"])
        prior = [record(rid="i-1", agent_id="a"), record(rid="i-2", agent_id="b")]
        final, c = turn(engine(a, b), ctx(prior=prior))
        assert final.acceptance_by_agent == {"a": "accepted", "b": "accepted"}
        assert c.blackboard.get_var("a_ran") and c.blackboard.get_var("b_ran")

    def test_reservations_reset_each_turn(self):
        a = Corrector("a", ["i-1"])
        e = engine(a)
        for _ in range(2):
            final, _ = turn(e, ctx(prior=[record(agent_id="a")]))
            assert final.acceptance_by_agent == {"a": "accepted"}

    def test_dynamic_agents_arbitrate_too(self):
        low = fixer(envelope(correction(), facts=[{"type": "low", "key": "k", "value": 1, "confidence": 0.5}]), agent_id="low", priority=0)
        high = fixer(envelope(correction()), agent_id="high", priority=3)
        prior = [record(agent_id="low"), ]
        c = ctx(prior=prior, capabilities=caps(correction_agent_policy="allowlisted", correction_agent_ids=["high"]))
        final, c2 = turn(engine(low, high), c)
        assert final.acceptance_by_agent == {"low": "rejected", "high": "accepted"}
        assert not c2.blackboard.has_fact("low", "k")
