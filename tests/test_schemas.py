"""
Schema-config tests for v2.2 hardening items S-2 and S-3.

S-2: `is_state_at_root` is dead config (never read by library/dynamic.py).
     It must be removed from every schema that contained it.

S-3: The v2 schemas (v2_raw, ui_control, widget_control) previously routed
     state ONLY through the legacy `state_field` (-> response.state_updates).
     They are standardized onto `variable_updates_field` (-> response.variable_updates),
     consistent with default_v2.json, so v2-only hosts reading `variable_updates`
     see their updates.

All fixtures are local to this file; the LLM is mocked.
"""

import os
import json

import pytest

from xubb_agents.library.dynamic import DynamicAgent
from xubb_agents.core.models import AgentContext, TriggerType


# --------------------------------------------------------------------------- #
# Helpers / local fixtures
# --------------------------------------------------------------------------- #

SCHEMA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "library",
    "schemas",
)

# Schemas that historically carried the dead `is_state_at_root` key (S-2).
SCHEMAS_WITH_DEAD_KEY = [
    "default_v2",
    "v2_raw",
    "ui_control",
    "widget_control",
]

# v2 schemas standardized onto variable_updates_field (S-3).
V2_STATE_SCHEMAS = [
    "v2_raw",
    "ui_control",
    "widget_control",
]

# Every schema file shipped in library/schemas/.
ALL_SCHEMA_NAMES = [
    "default",
    "default_v2",
    "custom1",
    "v2_raw",
    "ui_control",
    "widget_control",
]


def _load_schema(name: str) -> dict:
    """Load a schema JSON file directly from disk (no DynamicAgent involved)."""
    path = os.path.join(SCHEMA_DIR, f"{name}.json")
    with open(path, "r") as f:
        return json.load(f)


class _FakeLLM:
    """Minimal async stand-in for core.llm.LLMClient.generate_json."""

    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    async def generate_json(self, model: str, messages: list):
        self.calls.append({"model": model, "messages": messages})
        return self._payload


def _make_agent(output_format: str, llm_payload: dict) -> DynamicAgent:
    agent = DynamicAgent({
        "id": "test_agent",
        "name": "Test Agent",
        "text": "You are a test agent.",
        "output_format": output_format,
        "include_context": False,
    })
    agent.llm = _FakeLLM(llm_payload)
    return agent


def _minimal_context() -> AgentContext:
    return AgentContext(
        session_id="schema_test_session",
        recent_segments=[],
        shared_state={},
        trigger_type=TriggerType.TURN_BASED,
        turn_count=1,
        phase=1,
    )


# --------------------------------------------------------------------------- #
# S-2: `is_state_at_root` removed
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("schema_name", SCHEMAS_WITH_DEAD_KEY)
def test_s2_is_state_at_root_removed(schema_name):
    """S-2: the dead `is_state_at_root` key must no longer appear in any schema."""
    schema = _load_schema(schema_name)
    mapping = schema.get("mapping", {})
    assert "is_state_at_root" not in mapping, (
        f"{schema_name}.json still declares dead config 'is_state_at_root'"
    )


def test_s2_no_schema_anywhere_has_is_state_at_root():
    """S-2: defensive sweep — no schema file at all retains the dead key."""
    for name in ALL_SCHEMA_NAMES:
        schema = _load_schema(name)
        assert "is_state_at_root" not in schema.get("mapping", {}), (
            f"{name}.json unexpectedly declares 'is_state_at_root'"
        )


# --------------------------------------------------------------------------- #
# S-3: v2 schemas standardized onto variable_updates_field
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("schema_name", V2_STATE_SCHEMAS)
def test_s3_declares_variable_updates_field(schema_name):
    """S-3: each affected v2 schema declares a non-null `variable_updates_field`."""
    mapping = _load_schema(schema_name).get("mapping", {})
    var_field = mapping.get("variable_updates_field")
    assert var_field, (
        f"{schema_name}.json must declare a non-null 'variable_updates_field'"
    )
    # It routes the schema's own state object (state_snapshot) into variable_updates.
    assert var_field == "state_snapshot", (
        f"{schema_name}.json should route 'state_snapshot' through variable_updates_field"
    )


@pytest.mark.parametrize("schema_name", V2_STATE_SCHEMAS)
def test_s3_no_longer_relies_solely_on_state_field(schema_name):
    """S-3: the legacy `state_field` no longer carries state for these schemas."""
    mapping = _load_schema(schema_name).get("mapping", {})
    # state_field must be null/absent so state is no longer routed to state_updates.
    assert not mapping.get("state_field"), (
        f"{schema_name}.json must not route state via legacy 'state_field' anymore"
    )


def test_s3_consistent_with_default_v2_convention():
    """S-3: default_v2.json is the reference — state_field null, variable_updates used."""
    default_v2 = _load_schema("default_v2").get("mapping", {})
    assert not default_v2.get("state_field")
    assert default_v2.get("variable_updates_field") == "variable_updates"
    # The affected v2 schemas mirror the same shape (null state_field + var field set).
    for name in V2_STATE_SCHEMAS:
        mapping = _load_schema(name).get("mapping", {})
        assert not mapping.get("state_field")
        assert mapping.get("variable_updates_field")


# --------------------------------------------------------------------------- #
# JSON validity: every schema file still parses
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("schema_name", ALL_SCHEMA_NAMES)
def test_all_schemas_are_valid_json(schema_name):
    """Every schema file must still be syntactically valid JSON with a mapping."""
    schema = _load_schema(schema_name)
    assert isinstance(schema, dict)
    assert isinstance(schema.get("mapping", {}), dict)


# --------------------------------------------------------------------------- #
# S-3 integration: state lands in variable_updates, not state_updates
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_s3_v2_raw_state_lands_in_variable_updates():
    """
    Integration: a DynamicAgent using the v2_raw schema must surface its
    `state_snapshot` object in response.variable_updates (the v2 path), and
    NOT in the legacy response.state_updates.
    """
    payload = {
        "insight": {
            "type": "fact",
            "content": "Customer mentioned a $50k budget.",
            "confidence": 0.9,
        },
        "state_snapshot": {"phase": "negotiation", "budget": 50000},
    }
    agent = _make_agent("v2_raw", payload)

    response = await agent.evaluate(_minimal_context())

    assert response is not None
    # v2 path: state landed in variable_updates.
    assert response.variable_updates == {"phase": "negotiation", "budget": 50000}
    # legacy path: nothing routed to state_updates for this schema.
    assert response.state_updates == {} or response.state_updates is None
    # insight still parsed correctly.
    assert len(response.insights) == 1
    assert response.insights[0].content == "Customer mentioned a $50k budget."


@pytest.mark.asyncio
@pytest.mark.parametrize("schema_name", ["ui_control", "widget_control"])
async def test_s3_ui_schemas_state_lands_in_variable_updates(schema_name):
    """ui_control / widget_control also route state_snapshot to variable_updates."""
    payload = {
        "insight": {
            "type": "suggestion",
            "content": "Try updating the goals widget.",
            "confidence": 0.8,
        },
        "ui_actions": [
            {"target_widget": "goals_widget", "action": "update", "payload": {"x": 1}}
        ],
        "state_snapshot": {"active_widget": "goals_widget"},
    }
    agent = _make_agent(schema_name, payload)

    response = await agent.evaluate(_minimal_context())

    assert response is not None
    assert response.variable_updates == {"active_widget": "goals_widget"}
    assert response.state_updates == {} or response.state_updates is None
    # sidecar data still flows through the data_field mapping.
    assert response.data.get("ui_actions")
