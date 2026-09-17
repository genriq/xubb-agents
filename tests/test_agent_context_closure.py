"""SPEC_AGENT_CONTEXT_CLOSURE — the 3.2.0 warning stage.

`AgentContext` is the one input surface that still ignores unknown keys. Every
declaration nested inside it forbids them, so a caller is refused for
`insight_capabilities={"supported_tpyes": ...}` and accepted for
`insight_capabilties={...}` — which withdraws a capability for the whole run
with nothing said about the cause.

This file is the warning stage: warn in 3.2.0, refuse in 4.0.0. Each test pairs
with the negative control named in the spec's test plan, because a rule with no
failing case has not been tested.

The phase rows are the ones to read twice. The engine builds its second-phase
context with the CONSTRUCTOR (`engine.py:998`) — it never calls
`model_construct` — so the trusted fields are asserted as phase-2 agents
actually observe them, by driving `process_turn` through both phases. A
copy-based assertion would miss a field dropped on the way to phase 2.
"""

import asyncio
import time
import warnings

import pytest

from xubb_agents import AgentContext, Blackboard
from xubb_agents.core.input_keys import closest_name, unknown_keys
from xubb_agents.core.models import (
    AgentResponse,
    Event,
    HostInsightCapabilities,
    HostWidgetCapabilities,
    InsightReferenceContext,
)

#: The two misspellings the spec measured, and the field each resembles.
MEASURED_TYPOS = [
    ("principl_id", "principal_id"),
    ("widget_capabilties", "widget_capabilities"),
]


def _base(**extra):
    return dict(session_id="s", recent_segments=[], blackboard=Blackboard(), **extra)


def _context_warnings(build):
    """Engine deprecation warnings raised while building a context."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = build()
    return result, [str(w.message) for w in caught
                    if issubclass(w.category, DeprecationWarning)
                    and "unknown key" in str(w.message)]


# --------------------------------------------------------------------------
# Row 1 — an unknown key warns, naming the key and the refusal target
# --------------------------------------------------------------------------

@pytest.mark.parametrize("typo,real", MEASURED_TYPOS)
def test_unknown_key_warns_naming_key_and_target(typo, real):
    _, found = _context_warnings(lambda: AgentContext(**_base(**{typo: "x"})))
    assert len(found) == 1, found
    assert typo in found[0]
    assert "4.0.0" in found[0], "the warning must name the release that refuses"
    assert "AgentContext" in found[0], "the warning must name the surface"


def test_control_a_correctly_spelled_context_warns_about_nothing():
    """NEGATIVE CONTROL for row 1. If detection fired on everything, the tests
    above would pass while the feature was useless."""
    _, found = _context_warnings(
        lambda: AgentContext(**_base(
            principal_id="p",
            insight_capabilities=HostInsightCapabilities(),
            widget_capabilities=HostWidgetCapabilities(),
            insight_reference_context=InsightReferenceContext(),
        )))
    assert found == [], found


# --------------------------------------------------------------------------
# Row 2 — a hint never repairs
# --------------------------------------------------------------------------

@pytest.mark.parametrize("typo,real", MEASURED_TYPOS)
def test_a_hint_never_repairs_the_field_it_names(typo, real):
    """The message may suggest `real`. The field must still hold its default:
    guessing would silently grant a capability nobody successfully declared."""
    context, found = _context_warnings(
        lambda: AgentContext(**_base(**{typo: HostWidgetCapabilities(widgets=[])
                                        if "widget" in typo else "p"})))
    assert real in found[0], "the hint should name the nearest real field"
    assert "not repaired" in found[0], "the message must say the key was not repaired"

    default = AgentContext(**_base())
    assert getattr(context, real) == getattr(default, real), (
        f"{real} was repaired from {typo} — a guess granted what the caller "
        f"never successfully declared")


def test_an_unrecognisable_key_warns_without_a_hint():
    _, found = _context_warnings(lambda: AgentContext(**_base(zzzzzz=1)))
    assert len(found) == 1
    assert "Did you mean" not in found[0], (
        "a bad guess is worse than no guess; nothing is close to 'zzzzzz'")


# --------------------------------------------------------------------------
# Row 3 — allowed names are derived, never a second list
# --------------------------------------------------------------------------

def test_allowed_names_are_derived_from_the_model():
    """Every declared field must be accepted without appearing in any list this
    implementation maintains. Adding a field to `AgentContext` must need no edit
    here or in the detector."""
    declared = set(AgentContext.model_fields)
    assert unknown_keys(declared, declared) == [], (
        "a declared field was reported unknown — the detector is not deriving "
        "its allowed set from the model")
    assert len(declared) >= 19, "sanity: the model should declare its full surface"


def test_control_the_detector_reports_a_name_the_model_does_not_declare():
    """NEGATIVE CONTROL for row 3: prove the derived set can still say no."""
    assert unknown_keys(["session_id", "not_a_field"], AgentContext.model_fields) == [
        "not_a_field"]


def test_the_hint_helper_declines_when_nothing_is_close():
    assert closest_name("principl_id", AgentContext.model_fields) == "principal_id"
    assert closest_name("zzzzzz", AgentContext.model_fields) is None


# --------------------------------------------------------------------------
# Row 4 — every public entry point is covered
# --------------------------------------------------------------------------

def test_every_public_validation_entry_point_warns():
    raw = {"session_id": "s", "recent_segments": [], "principl_id": "p"}
    entries = {
        "constructor": lambda: AgentContext(**raw),
        "model_validate": lambda: AgentContext.model_validate(raw),
        "model_validate_json": lambda: AgentContext.model_validate_json(
            '{"session_id":"s","recent_segments":[],"principl_id":"p"}'),
    }
    for name, build in entries.items():
        _, found = _context_warnings(build)
        assert len(found) == 1, f"{name} did not warn: {found}"


def test_control_model_copy_is_exempt_and_does_not_validate():
    """CTX-10. `model_copy(update=...)` is a trusted internal operation on an
    already-validated context — the engine uses it at `engine.py:1095` for the
    narrowed content-admission view. It does not validate at either stage, so it
    must not warn, and it cannot be used as evidence of phase propagation."""
    context = AgentContext(**_base())
    _, found = _context_warnings(lambda: context.model_copy(update={"bogus": 1}))
    assert found == [], "model_copy must stay exempt; it is not a boundary"


# --------------------------------------------------------------------------
# Rows 5 and 6 — one notice per key, and nothing sensitive in the message
# --------------------------------------------------------------------------

def test_one_notice_per_unknown_key_per_validation():
    """Two unknown keys produce exactly two notices — not one, and not four
    through nested validation of the declarations the context carries."""
    _, found = _context_warnings(
        lambda: AgentContext(**_base(
            principl_id="p",
            widget_capabilties=HostWidgetCapabilities(),
            insight_capabilities=HostInsightCapabilities(),   # validates nested
        )))
    assert len(found) == 2, found
    assert len({f for f in found}) == 2, "the two notices must be distinct"


def test_the_warning_never_carries_the_supplied_value():
    """This surface carries principal identity and capability declarations."""
    secret = "principal-1234-do-not-log"
    _, found = _context_warnings(lambda: AgentContext(**_base(principl_id=secret)))
    assert secret not in found[0], "the supplied value must never be logged"
    assert "recent_segments" not in found[0], "the context must not be serialized"


# --------------------------------------------------------------------------
# Row 7 — the warning stage relaxes nothing
# --------------------------------------------------------------------------

def test_a_nested_unknown_key_still_raises_at_the_warning_stage():
    """`insight_capabilities` forbids extras today and must keep raising. The
    warning window is a grace period for new behaviour, never a downgrade of
    behaviour that exists."""
    with pytest.raises(Exception) as exc:
        AgentContext(**_base(insight_capabilities={"supported_tpyes": ["fact"]}))
    assert "supported_tpyes" in str(exc.value)


def test_a_malformed_known_field_still_raises():
    with pytest.raises(Exception):
        AgentContext(session_id="s", recent_segments="not a list")


# --------------------------------------------------------------------------
# Rows 9-11 — the trusted fields survive, observed inside phase 2
# --------------------------------------------------------------------------

def test_trusted_fields_are_observed_by_agents_in_phase_two():
    """The engine builds the second-phase context with the CONSTRUCTOR
    (`engine.py:998`), so closure will apply to it. Drive `process_turn` through
    both phases and assert the trusted fields as a phase-2 agent sees them — a
    field dropped on the way to phase 2 is exactly what a copy-based assertion
    would miss."""
    from xubb_agents.core.agent import AgentConfig, BaseAgent
    from xubb_agents.core.engine import AgentEngine
    from xubb_agents.core.models import TriggerType

    seen = {}

    class Emitter(BaseAgent):
        async def evaluate(self, context):
            return AgentResponse(events=[Event(
                name="ping", payload={}, source_agent=self.config.id,
                timestamp=time.time())])

    class Observer(BaseAgent):
        async def evaluate(self, context):
            seen["phase"] = context.phase
            seen["principal_id"] = context.principal_id
            seen["insight_capabilities"] = context.insight_capabilities
            seen["widget_capabilities"] = context.widget_capabilities
            seen["insight_reference_context"] = context.insight_reference_context
            seen["blackboard"] = context.blackboard
            return AgentResponse()

    emitter = Emitter(AgentConfig(name="emitter",
                                 trigger_types=[TriggerType.TURN_BASED]))
    observer = Observer(AgentConfig(name="observer",
                                    trigger_types=[TriggerType.EVENT],
                                    subscribed_events=["ping"]))
    observer.config.cooldown = 0

    caps = HostInsightCapabilities(supported_types=["fact"])
    widgets = HostWidgetCapabilities()
    refs = InsightReferenceContext()

    engine = AgentEngine(api_key="test-key")
    engine.register_agent(emitter)
    engine.register_agent(observer)

    context = AgentContext(**_base(
        principal_id="principal-1",
        insight_capabilities=caps,
        widget_capabilities=widgets,
        insight_reference_context=refs,
    ))
    asyncio.run(engine.process_turn(context))

    assert seen, "the phase-2 agent never ran — the test proves nothing"
    assert seen["phase"] == 2, f"expected a phase-2 observation, saw {seen['phase']}"
    assert seen["principal_id"] == "principal-1"
    assert seen["insight_capabilities"] == caps
    assert seen["widget_capabilities"] == widgets
    assert seen["insight_reference_context"] == refs
    assert seen["blackboard"] is not None, "Blackboard must reach phase 2"


def test_arbitrary_types_allowed_stays_enabled():
    """`Blackboard` is itself a pydantic model, so its acceptance cannot detect
    the removal of this setting. Assert the setting directly."""
    assert AgentContext.model_config.get("arbitrary_types_allowed") is True


def test_blackboard_is_still_accepted():
    board = Blackboard()
    assert AgentContext(**_base()).blackboard is not None
    assert AgentContext(session_id="s", recent_segments=[],
                        blackboard=board).blackboard is board
