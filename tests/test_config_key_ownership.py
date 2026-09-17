"""SPEC_CONFIG_KEY_OWNERSHIP — the 3.2.0 warning stage.

`model_config` and `trigger_config` are the engine's own vocabulary, and until
now an unknown key in either was accepted, discarded, and never mentioned again.
The spec's measured case: sixteen agents carry `model_config.temperature`, the
engine reads only `model_config.model_params`, so that sampling temperature has
never reached a model. Someone configured a real behaviour and got silence.

Warn in 3.2.0, refuse in 4.0.0. The top level stays OPEN — a host catalogue
legitimately carries its own fields there.

The conformance test in this file is the part that matters most. Spec §6:

    The 3.1.1 repair failed because it walked a hand-maintained list of "the
    structural keys" and everything outside the list kept the old behaviour. A
    list of read keys would fail the same way the first time someone adds a
    `model_config` field.

So the declared sets are checked against the code that reads them, in both
directions, and the parse fails loudly rather than skipping when it cannot
reach a read.
"""

import ast
import io
import warnings
from pathlib import Path

import pytest

from xubb_agents import DynamicAgent
from xubb_agents.library.dynamic import MODEL_CONFIG_KEYS, TRIGGER_CONFIG_KEYS

DYNAMIC = Path(__file__).resolve().parent.parent / "src" / "xubb_agents" / "library" / "dynamic.py"
SOURCE = io.open(DYNAMIC, encoding="utf-8").read()
TREE = ast.parse(SOURCE)

BASE = dict(id="a", name="a", text="t", output_format="insight_v1")


def _warnings_for(config):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        DynamicAgent(config)
    return [str(w.message) for w in caught if "unknown key" in str(w.message)]


def _reads(var):
    """Every read of `var`, split into literal keys and unresolvable reads.

    An AST walk rather than a regex: a regex over the file text also matches
    prose, and the comment in `dynamic.py` that *describes* this very check
    contains the literal `model_conf.get(...)`. Parsing the code means only code
    is inspected.
    """
    literal, unresolved = set(), []
    for node in ast.walk(TREE):
        # var.get("key") / var.get(expr)
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == var):
            first = node.args[0] if node.args else None
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                literal.add(first.value)
            else:
                unresolved.append(ast.dump(first) if first else "get()")
        # var["key"] / var[expr]
        if (isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Name)
                and node.value.id == var):
            key = node.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                literal.add(key.value)
            else:
                unresolved.append(ast.dump(key))
    return literal, unresolved


def _read_keys(var):
    return _reads(var)[0]


def _unreachable_reads(var):
    """Reads the parse cannot resolve to a literal key.

    Spec §6: where the parse cannot reach — a key read through a variable, say —
    the test fails loudly rather than skipping.
    """
    return _reads(var)[1]


# --------------------------------------------------------------------------
# §6 — derivation, not enumeration
# --------------------------------------------------------------------------

@pytest.mark.parametrize("var,declared,block", [
    ("model_conf", MODEL_CONFIG_KEYS, "model_config"),
    ("trigger_conf", TRIGGER_CONFIG_KEYS, "trigger_config"),
])
def test_declared_keys_equal_the_keys_the_loader_reads(var, declared, block):
    """Both directions. A read that is not declared would warn a caller about a
    key the engine actually uses; a declaration nothing reads is a key the
    engine promises to honour and does not."""
    read = _read_keys(var)
    assert read, f"the parse found no {block} reads at all — it has stopped working"
    assert set(declared) == read, (
        f"{block} declaration has drifted from the reader.\n"
        f"  read but not declared: {sorted(read - set(declared))}\n"
        f"  declared but not read: {sorted(set(declared) - read)}")


@pytest.mark.parametrize("var", ["model_conf", "trigger_conf"])
def test_every_read_is_reachable_by_the_parse(var):
    """A key read through a variable would silently escape the conformance
    check above, so the parse must find none."""
    unreachable = _unreachable_reads(var)
    assert unreachable == [], (
        f"{var} has reads the conformance parse cannot resolve: {unreachable}. "
        f"Refactor the reader, or record the exception in the declaration with "
        f"its reason (spec §6).")


def test_control_the_conformance_check_can_fail():
    """NEGATIVE CONTROL. The two tests above pass if the comparison were a
    tautology. Prove drift is detected."""
    read = _read_keys("model_conf")
    assert set(MODEL_CONFIG_KEYS) | {"invented_key"} != read
    assert set(MODEL_CONFIG_KEYS) - {"model"} != read


# --------------------------------------------------------------------------
# The warning itself
# --------------------------------------------------------------------------

def test_the_measured_temperature_case_warns():
    """The spec's headline finding: sixteen agents set a temperature the engine
    never read. From 3.2.0 they are told."""
    found = _warnings_for({**BASE, "model_config": {"temperature": 0.9}})
    assert len(found) == 1, found
    assert "temperature" in found[0]
    assert "model_config" in found[0]
    assert "4.0.0" in found[0]
    assert "Agent 'a'" in found[0], "the warning must name the agent"


def test_temperature_is_not_offered_model_params_as_a_hint():
    """Moving `temperature` into `model_params` makes an ignored setting
    effective and changes provider behaviour — the spec requires a per-agent
    decision, so the engine must not nudge toward a mechanical move."""
    found = _warnings_for({**BASE, "model_config": {"temperature": 0.9}})
    assert "Did you mean" not in found[0], found[0]


def test_a_trigger_config_typo_warns_with_a_hint():
    found = _warnings_for({**BASE, "trigger_config": {"keyord": ["x"]}})
    assert len(found) == 1
    assert "keywords" in found[0]
    assert "not repaired" in found[0]


def test_the_nested_output_block_warns():
    """`model_config.output` is host data inside an engine-owned block. It is
    read by nothing, and closing the block refuses it at 4.0.0."""
    found = _warnings_for({**BASE, "model_config": {"output": {"format": "insight_v1"}}})
    assert len(found) == 1
    assert "output" in found[0]


def test_control_every_declared_key_is_accepted_in_silence():
    """NEGATIVE CONTROL: if the detector warned on everything, the tests above
    would pass while the feature was unusable."""
    found = _warnings_for({
        **BASE,
        "model_config": {k: ({} if k == "model_params" else 1) for k in MODEL_CONFIG_KEYS},
        "trigger_config": {k: ([] if k in ("keywords", "subscribed_events") else 1)
                           for k in TRIGGER_CONFIG_KEYS},
    })
    assert found == [], found


def test_the_top_level_stays_open():
    """105 of 105 catalogue records carry `type`; 70 carry `description`. A host
    catalogue is not the engine's business and a blanket refusal would reject
    every maintained configuration."""
    found = _warnings_for({**BASE, "type": "agent", "description": "d",
                           "anything_the_host_wants": 1})
    assert found == [], found


def test_a_hint_never_repairs_a_config_key():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        agent = DynamicAgent({**BASE, "trigger_config": {"keyord": ["x"], "cooldown": 0}})
    default = DynamicAgent({**BASE, "trigger_config": {"cooldown": 0}})
    assert agent.config.trigger_keywords == default.config.trigger_keywords, (
        "'keyord' was repaired into 'keywords' — a guess made a setting effective "
        "that the caller never successfully declared")


def test_the_warning_never_carries_the_supplied_value():
    secret = "sk-do-not-log-this"
    found = _warnings_for({**BASE, "model_config": {"api_ky": secret}})
    assert secret not in found[0]
