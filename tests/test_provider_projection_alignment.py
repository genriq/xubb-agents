"""Provider projection alignment (docs/SPEC_PROVIDER_PROJECTION_ALIGNMENT.md).

The per-run provider projection offers only what local validation can accept for
that run; the generated rules say where the conditional fields belong; queues are
lists; citations are copied exactly. Local validation stays authoritative: every
invalid shape still rejects when a provider ignores the schema.

Everything runs through the real engine and the real LLM client, with only the
SDK's completion call replaced; the schema a test inspects is the one the agent
actually sent on the wire.
"""
import asyncio
import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from xubb_agents import AgentEngine, AgentContext, Blackboard, DynamicAgent, HostInsightCapabilities
from xubb_agents.core.insight_validation import HUMAN_WIRE_VALUES, ReferenceContext, snapshot_ref
from xubb_agents.core.models import TranscriptSegment
from xubb_agents.core.provider_schema import compile_schema, encode_response, schema_issues

from tests.test_provider_schema_g2 import STRICT_ENVELOPE, make_client, ok_response
from tests.test_typed_acceptance_g1 import codes

NINE = list(HUMAN_WIRE_VALUES)
SIX = ["fact", "observation", "suggestion", "warning", "opportunity", "praise"]
CONSULTING_TYPES = ["fact", "observation", "suggestion", "warning"]
FIXTURES = Path(__file__).parent / "fixtures" / "insight_contract_1.2.0"


def agent(profile="general", allowed=None, agent_id="a"):
    insight_config = {"analysis_profile": profile}
    if allowed is not None:
        insight_config["allowed_types"] = list(allowed)
    return DynamicAgent({"id": agent_id, "name": agent_id, "text": "You advise.", "output_format": "insight_v1",
                         "trigger_config": {"cooldown": 0}, "insight_config": insight_config})


def ctx():
    return AgentContext(session_id="s", turn_count=1, blackboard=Blackboard(), principal_id="p",
                        recent_segments=[TranscriptSegment(speaker="C", text="Can we keep Friday?", timestamp=1.0)],
                        insight_capabilities=HostInsightCapabilities(supported_types=NINE))


def run(ag, body, mode="strict"):
    """One turn through the engine; returns (final response, the request the client sent)."""
    llm, comp = make_client([ok_response(body)], structured_outputs=mode)
    engine = AgentEngine(api_key="k", structured_outputs=mode)
    engine.register_agent(ag)
    ag.llm = llm
    final = asyncio.run(engine.process_turn(ctx()))
    return final, comp.calls[0]


def sent(profile="general", allowed=None):
    """The schema and system prompt the agent actually sends for this profile and type set."""
    _, call = run(agent(profile, allowed), wire())
    return call["response_format"]["json_schema"]["schema"], call["messages"][0]["content"]


def wire(**insight_over):
    """A complete strict-wire envelope (every bound channel present), insight overridden."""
    body = deepcopy(STRICT_ENVELOPE)
    body["insight"].update(insight_over)
    return body


def allows(schema, body):
    return not list(Draft202012Validator(schema).iter_errors(body))


QUESTION = {"reason": "Need the owner's name.", "response_format": "text"}
REFS = [{"kind": "segment", "ref_id": "snap:x:segment:0", "revision": None}]


# ---------------------------------------------------------------------------
# 3.1 — field availability per run, as the provider sees it
# ---------------------------------------------------------------------------

class TestGeneralProfileProjection:
    """A general agent can never have an observation kind, a validation step, or a
    question/correction payload it was not granted accepted: the projection it
    sends must not offer them."""

    def test_the_baseline_suggestion_is_offered(self):
        schema, _ = sent("general")
        assert allows(schema, wire(type="suggestion"))

    @pytest.mark.parametrize("over", [
        {"type": "suggestion", "observation_kind": "implication"},
        {"type": "observation", "observation_kind": "implication", "rationale": "r", "evidence_refs": REFS},
        {"type": "observation", "observation_kind": "hypothesis", "rationale": "r", "validation_step": "v",
         "evidence_refs": REFS},
        {"type": "suggestion", "validation_step": "Pilot it first."},
        {"type": "suggestion", "question": QUESTION},
    ], ids=["implication-on-suggestion", "implication-general", "hypothesis-general",
            "validation-step-on-suggestion", "question-payload-on-suggestion"])
    def test_shapes_local_validation_always_rejects_are_not_offered(self, over):
        schema, _ = sent("general")
        assert not allows(schema, wire(**over))


class TestConsultingProfileProjection:
    """A consulting agent may use the observation fields, but only in the shapes the
    contract admits; the projection discriminates them by type and kind."""

    def test_a_hypothesis_observation_with_its_validation_step_is_offered(self):
        schema, _ = sent("consulting", CONSULTING_TYPES)
        assert allows(schema, wire(type="observation", urgency="whenever", observation_kind="hypothesis",
                                   rationale="Approvals cluster.", validation_step="Ask finance.",
                                   evidence_refs=REFS))

    def test_an_implication_without_a_validation_step_is_offered(self):
        schema, _ = sent("consulting", CONSULTING_TYPES)
        assert allows(schema, wire(type="observation", observation_kind="implication", rationale="r",
                                   evidence_refs=REFS))

    def test_a_plain_suggestion_is_offered(self):
        schema, _ = sent("consulting", CONSULTING_TYPES)
        assert allows(schema, wire(type="suggestion"))

    @pytest.mark.parametrize("over", [
        {"type": "suggestion", "observation_kind": "implication", "rationale": "r", "evidence_refs": REFS},
        {"type": "warning", "validation_step": "Validate with a pilot."},
        {"type": "observation", "observation_kind": "implication", "rationale": "r",
         "validation_step": "Check it.", "evidence_refs": REFS},
        {"type": "observation", "observation_kind": None, "validation_step": "Check it."},
        {"type": "suggestion", "question": QUESTION},
    ], ids=["implication-on-suggestion", "validation-step-on-warning", "implication-with-validation-step",
            "validation-step-without-kind", "question-payload-on-suggestion"])
    def test_shapes_the_contract_forbids_are_not_offered(self, over):
        schema, _ = sent("consulting", CONSULTING_TYPES)
        assert not allows(schema, wire(**over))


class TestQueueProjection:
    def test_a_queue_holding_a_list_is_offered(self):
        schema, _ = sent("general")
        assert allows(schema, wire())   # STRICT_ENVELOPE's queue is ["ask finance"]

    def test_a_queue_holding_a_scalar_is_not_offered(self):
        schema, _ = sent("general")
        body = wire()
        body["queue_pushes"] = {"entries": [{"key": "next_move", "value": "ask for the workflow"}]}
        assert not allows(schema, body)

    def test_other_maps_keep_arbitrary_values(self):
        schema, _ = sent("general")
        body = wire()
        body["variable_updates"] = {"entries": [{"key": "phase", "value": "risk"}]}
        body["memory_updates"] = {"entries": [{"key": "seen", "value": True}]}
        assert allows(schema, body)


# ---------------------------------------------------------------------------
# Local validation stays authoritative: a provider that ignores the schema
# ---------------------------------------------------------------------------

class TestInvalidShapesStillReject:
    """json_object mode sends no schema, so these reach local validation unchanged
    and must still reject with today's codes."""

    @pytest.mark.parametrize("profile,allowed,over,expected", [
        ("general", None, {"type": "suggestion", "observation_kind": "implication"},
         {"subtype_on_non_observation", "consulting_profile_required"}),
        ("consulting", CONSULTING_TYPES, {"type": "suggestion", "validation_step": "Pilot it."},
         {"only_for_hypothesis"}),
        ("consulting", CONSULTING_TYPES,
         {"type": "observation", "observation_kind": "implication", "rationale": "r",
          "validation_step": "Check.", "evidence_refs": REFS},
         {"only_for_hypothesis"}),
        ("consulting", CONSULTING_TYPES,
         {"type": "observation", "observation_kind": None, "validation_step": "Check."},
         {"only_for_hypothesis"}),
    ], ids=["general-implication-on-suggestion", "consulting-validation-on-suggestion",
            "consulting-implication-with-validation-step", "consulting-null-kind-with-validation-step"])
    def test_invalid_candidates_reject_with_their_codes(self, profile, allowed, over, expected):
        body = {"has_insight": True, "insight": {"type": "warning", "content": "c", "confidence": 0.8,
                                                 "urgency": "now", **over}}
        final, _ = run(agent(profile, allowed), body, mode="json_object")
        assert final.acceptance_by_agent["a"] == "rejected"
        assert expected <= {d.classification for d in final.diagnostics}

    def test_a_scalar_queue_value_still_rejects(self):
        body = {"has_insight": False, "insight": None, "queue_pushes": {"next_move": "ask for the workflow"}}
        final, _ = run(agent(), body, mode="json_object")
        assert "invalid_domain_payload" in codes(final)


# ---------------------------------------------------------------------------
# 3.2 / 3.4 — the generated instructions
# ---------------------------------------------------------------------------

class TestInstructions:
    def test_a_general_run_is_told_the_observation_fields_are_null(self):
        _, system = sent("general")
        assert "observation_kind and validation_step must be null" in system

    def test_a_consulting_run_is_told_where_each_field_belongs(self):
        _, system = sent("consulting", CONSULTING_TYPES)
        assert "observation_kind is only for an observation, and is null on every other type" in system
        assert "validation_step is null unless the type is observation and observation_kind is hypothesis" in system
        assert "also null on an observation whose observation_kind is null" in system
        assert "belongs in the content of a suggestion, not in validation_step" in system

    def test_a_run_offering_queues_is_told_they_hold_lists(self):
        _, system = sent("general")
        assert "Each queue in queue_pushes holds a list of items" in system

    def test_ungranted_payloads_are_null(self):
        _, system = sent("general")
        assert "question must be null" in system and "correction must be null" in system

    def test_no_rule_tells_the_model_to_omit_a_field(self):
        for profile, allowed in (("general", None), ("consulting", CONSULTING_TYPES)):
            _, system = sent(profile, allowed)
            assert "omit" not in system.lower()

    def test_citations_must_be_copied_exactly(self):
        _, system = sent("consulting", CONSULTING_TYPES)
        assert "Copy each id exactly as shown in the brackets" in system


class TestCitationResolutionUnchanged:
    """§3.4 changes the instruction only: resolution stays exact. A shortened or
    reconstructed id never resolves, and nothing guesses the nearest source."""

    def make(self):
        rc = ReferenceContext(session_id="s1", snapshot_id="snapA")
        rc.add("segment", snapshot_ref("snapA", "segment", 3), "snapA")
        return rc

    def test_the_exact_id_resolves(self):
        issue, _ = self.make().resolve({"kind": "segment", "ref_id": "snap:snapA:segment:3", "revision": None}, "p")
        assert issue is None

    @pytest.mark.parametrize("ref_id", ["segment:3", "snapA:segment:3", "snap:snapA:segment:03", "snap:snapA:seg:3"])
    def test_a_shortened_or_reconstructed_id_does_not_resolve(self, ref_id):
        issue, revision = self.make().resolve({"kind": "segment", "ref_id": ref_id, "revision": None}, "p")
        assert issue is not None and issue.code == "unknown_reference" and revision is None


# ---------------------------------------------------------------------------
# 3.1 — the compiled projection's structure
# ---------------------------------------------------------------------------

class TestSpecialisationStructure:
    def test_the_generic_projection_is_unchanged(self):
        packaged = json.loads((FIXTURES / "provider_agent_response.schema.json").read_text(encoding="utf-8"))
        assert compile_schema(full=True) == packaged
        assert compile_schema(full=True, analysis_profile=None) == packaged

    def test_a_general_run_is_one_candidate_with_null_only_conditional_fields(self):
        schema = compile_schema(full=True, allowed_types=SIX, analysis_profile="general")
        cand = schema["$defs"]["candidate"]
        for name in ("observation_kind", "validation_step", "question", "correction"):
            assert cand["properties"][name] == {"type": "null"} and name in cand["required"], name
        assert schema["properties"]["insight"] == {"anyOf": [{"$ref": "#/$defs/candidate"}, {"type": "null"}]}

    def test_a_consulting_run_branches_by_type_and_observation_kind(self):
        schema = compile_schema(full=True, allowed_types=["fact", "observation", "suggestion"],
                                analysis_profile="consulting")
        refs = [r["$ref"].rsplit("/", 1)[1] for r in schema["properties"]["insight"]["anyOf"][:-1]]
        assert refs == ["candidate_fact", "candidate_observation_plain", "candidate_observation_implication",
                        "candidate_observation_hypothesis", "candidate_suggestion"]
        assert schema["properties"]["insight"]["anyOf"][-1] == {"type": "null"}
        d = schema["$defs"]
        assert d["candidate_suggestion"]["properties"]["observation_kind"] == {"type": "null"}
        assert d["candidate_suggestion"]["properties"]["validation_step"] == {"type": "null"}
        assert d["candidate_observation_plain"]["properties"]["validation_step"] == {"type": "null"}
        assert d["candidate_observation_implication"]["properties"]["observation_kind"] == \
            {"type": "string", "enum": ["implication"]}
        assert d["candidate_observation_implication"]["properties"]["validation_step"] == {"type": "null"}
        assert d["candidate_observation_hypothesis"]["properties"]["validation_step"] == {"type": "string"}

    def test_a_consulting_run_without_observation_is_one_candidate(self):
        schema = compile_schema(full=True, allowed_types=["fact", "suggestion"], analysis_profile="consulting")
        assert schema["$defs"]["candidate"]["properties"]["observation_kind"] == {"type": "null"}

    def test_granted_payloads_are_required_in_their_own_branch_only(self):
        schema = compile_schema(full=True, allowed_types=["suggestion", "question", "correction"],
                                analysis_profile="general")
        d = schema["$defs"]
        assert d["candidate_question"]["properties"]["question"]["type"] == "object"
        assert d["candidate_question"]["properties"]["correction"] == {"type": "null"}
        assert d["candidate_correction"]["properties"]["correction"]["type"] == "object"
        assert d["candidate_correction"]["properties"]["question"] == {"type": "null"}
        assert d["candidate_suggestion"]["properties"]["question"] == {"type": "null"}
        assert d["candidate_suggestion"]["properties"]["correction"] == {"type": "null"}

    @pytest.mark.parametrize("profile", ["general", "consulting"])
    @pytest.mark.parametrize("allowed", [SIX, CONSULTING_TYPES, NINE, ["fact"], ["observation"], []],
                             ids=["six", "consulting-four", "nine", "fact-only", "observation-only", "silence"])
    @pytest.mark.parametrize("content_extension", [False, True])
    def test_every_specialised_projection_passes_the_subset_lint(self, profile, allowed, content_extension):
        schema = compile_schema(full=True, content_extension=content_extension, allowed_types=allowed,
                                analysis_profile=profile)
        assert schema_issues(schema) == []

    def test_only_the_marked_channel_carries_lists(self):
        schema = compile_schema(full=True, allowed_types=SIX, analysis_profile="general")
        p = schema["properties"]
        assert p["queue_pushes"] == {"$ref": "#/$defs/list_map"}
        assert p["variable_updates"] == {"$ref": "#/$defs/map"} and p["memory_updates"] == {"$ref": "#/$defs/map"}
        assert schema["$defs"]["candidate"]["properties"]["metadata"] == {"$ref": "#/$defs/map"}
        entry = schema["$defs"]["list_map"]["properties"]["entries"]["items"]["properties"]["value"]
        assert entry == {"type": "array", "items": {"$ref": "#/$defs/json_value"}}


# ---------------------------------------------------------------------------
# 3.1 (f) — per-run superset: nothing locally acceptable is lost
# ---------------------------------------------------------------------------

def _allowed_for_run(envelope, profile, allowed):
    ins = envelope["insight"]
    if ins is None:
        return True
    t = ins["type"]
    if t not in allowed:
        return False
    if ins.get("observation_kind") is not None and not (profile == "consulting" and t == "observation"):
        return False
    if ins.get("question") is not None and "question" not in allowed:
        return False
    if ins.get("correction") is not None and "correction" not in allowed:
        return False
    return True


class TestPerRunSuperset:
    @pytest.mark.parametrize("profile,allowed", [
        ("general", SIX), ("consulting", SIX), ("general", NINE), ("consulting", NINE),
        ("consulting", CONSULTING_TYPES),
    ], ids=["general-six", "consulting-six", "general-nine", "consulting-nine", "consulting-four"])
    def test_every_packaged_valid_example_allowed_for_the_run_stays_representable(self, profile, allowed):
        examples = json.loads((FIXTURES / "examples.json").read_text(encoding="utf-8"))["fixtures"]
        kept = [f for f in examples if f["expected_valid"] and _allowed_for_run(f["envelope"], profile, allowed)]
        assert kept, "the configuration must exercise at least one packaged example"
        validator = Draft202012Validator(compile_schema(full=True, allowed_types=allowed, analysis_profile=profile))
        for f in kept:
            data = deepcopy(f["envelope"])
            data.update(variable_updates={"phase": "risk"}, queue_pushes={"pending": [{"question": "Who approves?"}]},
                        memory_updates={}, facts=[], events=[], ui_actions=[])
            assert validator.is_valid(encode_response(data, full=True)), (f["id"], profile)


# ---------------------------------------------------------------------------
# The real path: what the agent sends decodes and is accepted
# ---------------------------------------------------------------------------

class TestRealPath:
    def test_a_list_valued_queue_decodes_and_is_accepted(self):
        final, call = run(agent(), wire(type="suggestion"))
        assert final.acceptance_by_agent["a"] == "accepted"
        assert call["response_format"]["json_schema"]["schema"]["properties"]["queue_pushes"] == \
            {"$ref": "#/$defs/list_map"}

    def test_a_consulting_hypothesis_passes_the_branched_schema_and_the_shape_rules(self):
        # No evidence id is exposed in this context, so the reference rules still apply
        # to evidence; what this asserts is the SHAPE: no placement diagnostic.
        body = wire(type="observation", urgency="whenever", observation_kind="hypothesis",
                    rationale="Approvals cluster.", validation_step="Ask finance.", evidence_refs=[])
        final, call = run(agent("consulting", CONSULTING_TYPES), body)
        assert allows(call["response_format"]["json_schema"]["schema"], body)
        assert {"only_for_hypothesis", "subtype_on_non_observation",
                "consulting_profile_required"}.isdisjoint({d.classification for d in final.diagnostics})
