"""The output-format registry: one authoritative contract per format.

Everything structural about an output format — the gate, the insight key, the
allowed top-level keys, the channel bindings, the transports and the
deprecation schedule — is read from ONE shipped file,
``library/contract/output_formats.json``. The generated output instruction, the
provider projection and the parser are all derived from it, so a format cannot
tell the model one shape and read another (the class of defect this module
exists to end).

The packaged ``library/schemas/*.json`` files remain as documentation of each
format; their agreement with this registry is conformance-tested
(``tests/test_output_formats.py``), not trusted at run time.

Vocabulary:

* **envelope** — the input shape an adapter accepts: ``canonical`` (an explicit
  Boolean gate and a nested insight), ``flat`` (a Boolean gate with the insight
  fields at the top level) or ``root`` (presence of a nested object is the gate).
  Every envelope normalizes to ONE logical response with an explicit Boolean gate.
* **channel binding** — wire key → sink. A format may write a sink only if it
  binds it; presence in the framework's vocabulary grants nothing.
* **status** — ``supported`` or ``deprecated``. A deprecated name is a thin input
  adapter over the same validation and acceptance pipeline, never a second
  contract.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

CONTRACT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "library", "contract", "output_formats.json")

#: Sinks a bound channel may reach. ``private_memory`` is the ``default``
#: adapter's scratchpad alias: it stages the merged committed-plus-new view
#: under ``state_updates["memory_<agent id>"]``, which is how that format's
#: private memory has always reached the blackboard bridge.
CHANNEL_SINKS: Tuple[str, ...] = ("events", "variable_updates", "queue_pushes", "facts",
                                  "memory_updates", "private_memory", "ui_actions")


class OutputFormatError(ValueError):
    """An output format could not be resolved, or diverges from its contract.

    Raised during agent construction; ``DynamicAgent`` re-raises it as an
    ``AgentConfigurationError`` so an embedder sees one configuration-error type.
    """


@dataclass(frozen=True)
class FormatSpec:
    """One format's authoritative contract."""
    id: str
    status: str
    envelope: str                       # canonical | flat | root
    gate_kind: str                      # boolean | root_presence
    gate_key: Optional[str]
    insight_key: Optional[str]
    channels: Dict[str, str]            # wire key -> sink
    transports: Tuple[str, ...]
    content_contracts: Tuple[str, ...]
    insight_fields: Tuple[str, ...]
    insight_types: Tuple[str, ...]
    description: str = ""
    content_alias: Optional[str] = None            # flat adapters only (`default`)
    deprecation: Optional[Dict[str, str]] = None
    legacy_wire_shape: Optional["FormatSpec"] = field(default=None, repr=False)

    # -- derived helpers -------------------------------------------------
    @property
    def deprecated(self) -> bool:
        return self.status == "deprecated"

    def sink_for(self, wire_key: str) -> Optional[str]:
        return self.channels.get(wire_key)

    def wire_key_for(self, sink: str) -> Optional[str]:
        for wire, bound in self.channels.items():
            if bound == sink:
                return wire
        return None

    def offers(self, sink: str) -> bool:
        return self.wire_key_for(sink) is not None

    def envelope_keys(self) -> Tuple[str, ...]:
        """Top-level keys this envelope defines (excluding flat insight fields)."""
        keys: List[str] = []
        if self.gate_key:
            keys.append(self.gate_key)
        if self.insight_key:
            keys.append(self.insight_key)
        keys.extend(self.channels)
        return tuple(keys)

    def descriptor(self) -> Dict[str, Any]:
        """The legacy-shaped descriptor, DERIVED — never read from a schema file."""
        return {
            "gate_mode": self.gate_kind,
            "typed_adapter": self.envelope,
            "output_format": self.id,
            "status": self.status,
            "typed_supported_insight_types": list(self.insight_types),
            "supported_insight_fields": list(self.insight_fields),
            "supported_transports": list(self.transports),
            "supported_content_contracts": list(self.content_contracts),
            "channels": dict(self.channels),
        }

    def mapping(self) -> Dict[str, Any]:
        """The legacy-shaped mapping, DERIVED. Kept because the S-1 passthrough
        (``expiry`` / ``action_label``) and a few callers still read it; it is
        no longer an authority and cannot diverge from this spec."""
        m: Dict[str, Any] = {
            "root_key": self.insight_key if self.envelope != "flat" else None,
            "check_field": self.gate_key,
            "content_field": "content",
            "type_field": "type",
            "confidence_field": "confidence",
            "metadata_field": "metadata",
        }
        for wire, sink in self.channels.items():
            if sink == "events":
                m["events_field"] = wire
            elif sink == "variable_updates":
                m["variable_updates_field"] = wire
            elif sink == "queue_pushes":
                m["queue_field"] = wire
            elif sink == "facts":
                m["facts_field"] = wire
            elif sink == "memory_updates":
                m["memory_field"] = wire
            elif sink == "private_memory":
                m["state_field"] = wire
            elif sink == "ui_actions":
                m["data_field"] = wire
                m["data_key"] = wire
        return m


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: Optional[Dict[str, Any]] = None


def _load() -> Dict[str, Any]:
    global _REGISTRY
    if _REGISTRY is None:
        with open(CONTRACT_FILE, "r", encoding="utf-8") as fh:
            _REGISTRY = json.load(fh)
    return _REGISTRY


def _build(fid: str, body: Dict[str, Any], shared: Dict[str, Any]) -> FormatSpec:
    gate = body.get("gate") or {}
    channels = dict(body.get("channels") or {})
    for wire, sink in channels.items():
        if sink not in CHANNEL_SINKS:     # pragma: no cover - shipped-file defect
            raise OutputFormatError(f"output_formats.json: format '{fid}' binds '{wire}' to unknown sink '{sink}'")
    legacy = body.get("legacy_wire_shape")
    return FormatSpec(
        id=fid,
        status=body.get("status", "supported"),
        envelope=body["envelope"],
        gate_kind=gate.get("kind", "boolean"),
        gate_key=gate.get("key"),
        insight_key=body.get("insight_key"),
        channels=channels,
        transports=tuple(body.get("transports") or ["json_object"]),
        content_contracts=tuple(body.get("content_contracts") or ()),
        insight_fields=tuple(shared["insight_fields"]),
        insight_types=tuple(shared["insight_types"]),
        description=body.get("description", ""),
        content_alias=body.get("content_alias"),
        deprecation=body.get("deprecation"),
        legacy_wire_shape=(_build(fid, {**legacy, "status": body.get("status", "supported")}, shared)
                           if legacy else None),
    )


def all_formats() -> Dict[str, FormatSpec]:
    reg = _load()
    return {fid: _build(fid, body, reg) for fid, body in reg["formats"].items()}


def supported_names() -> List[str]:
    return sorted(f for f, s in all_formats().items() if s.status == "supported")


def deprecated_names() -> List[str]:
    return sorted(f for f, s in all_formats().items() if s.status == "deprecated")


def implicit_default() -> str:
    return _load()["implicit_default"]


def removal_release() -> str:
    return _load()["removal_release"]


def known_channel_wire_keys() -> Tuple[str, ...]:
    return tuple(_load()["known_channel_wire_keys"])


_MISSING = object()

#: Names removed in an earlier release. Refused BY NAME before anything else:
#: a removed schema must not resolve to a different envelope by accident.
REMOVED_FORMATS: Dict[str, str] = {
    "custom1": ("custom1 was removed in 3.0.0 with the legacy_v2 insight contract: it "
                "declared no typed adapter, so it can no longer be registered."),
}


def resolve(raw: Any = _MISSING) -> FormatSpec:
    """Resolve a configured ``output_format`` value to its contract.

    Resolution order (spec §9 item 1):

    1. an **omitted** key resolves to the implicit runtime default, then follows
       the same path as an explicit name — so an omitted key inherits that
       format's deprecation warning rather than being a silent third state;
    2. every other unresolved case raises: an explicit ``None``, an empty or
       whitespace-only string, a non-string value, a removed name, an unknown
       name. There is no fallback to another contract, because falling back is
       the defect (a typo used to re-home an agent into a different envelope).
    """
    formats = all_formats()
    names = ", ".join(sorted(formats))
    if raw is _MISSING:
        raw = implicit_default()
    if raw is None:
        raise OutputFormatError(
            f"output_format is null. Omit the key to inherit the current default "
            f"('{implicit_default()}'), or name a format explicitly: {names}.")
    if not isinstance(raw, str):
        raise OutputFormatError(
            f"output_format must be a string, got {type(raw).__name__}. Supported formats: {names}.")
    name = raw.strip()
    if not name:
        raise OutputFormatError(
            f"output_format is empty. Omit the key to inherit the current default "
            f"('{implicit_default()}'), or name a format explicitly: {names}.")
    removed = REMOVED_FORMATS.get(name)
    if removed:
        raise OutputFormatError(
            f"{removed} Re-point this agent at a supported format "
            f"({', '.join(supported_names())}) and republish it.")
    spec = formats.get(name)
    if spec is None:
        raise OutputFormatError(
            f"Unknown output_format '{raw}'. Supported: {', '.join(supported_names())}. "
            f"Deprecated (removed in {removal_release()}): {', '.join(deprecated_names())}. "
            f"An unrecognised name is refused rather than resolved to another format, "
            f"because silently registering under a different envelope is what this rule prevents.")
    return spec


def deprecation_message(spec: FormatSpec, agent_id: Any) -> str:
    dep = spec.deprecation or {}
    return (f"Agent '{agent_id}': output_format '{spec.id}' is deprecated since "
            f"{dep.get('deprecated_in', '3.1.0')} and is removed in {dep.get('removed_in', removal_release())}. "
            f"Move to '{dep.get('replacement', 'insight_v1')}'. See docs/MIGRATION_OUTPUT_FORMATS.md.")


# ---------------------------------------------------------------------------
# Structural-override detection (spec §9 item 2)
# ---------------------------------------------------------------------------

#: Mapping keys that decide the wire shape. An agent that sets one of these to
#: something its format's contract does not declare is refused at registration:
#: an override either controls generation AND parsing, or it fails loudly.
STRUCTURAL_MAPPING_KEYS: Tuple[str, ...] = (
    "root_key", "check_field", "content_field", "type_field",
    "events_field", "variable_updates_field", "queue_field", "facts_field",
    "memory_field", "state_field", "data_field", "data_key",
)

#: Removed opt-in. It was accepted and ignored for three releases (F3); the
#: canonical contract uses an explicit Boolean gate and nothing else.
RETIRED_MAPPING_KEYS: Dict[str, str] = {
    "speak_without_gate": (
        "`speak_without_gate` is not supported: it was accepted and silently inert, and the "
        "canonical contract uses an explicit Boolean gate instead. Remove it and use a format "
        "whose gate is declared (insight_v1 or widget_control)."),
}


def override_violations(spec: FormatSpec, mapping: Optional[Dict[str, Any]],
                        descriptor: Optional[Dict[str, Any]]) -> List[str]:
    """Structural divergences between a live agent and its format's contract."""
    problems: List[str] = []
    mapping = mapping or {}
    contract_mapping = spec.mapping()
    for key, why in RETIRED_MAPPING_KEYS.items():
        if key in mapping:
            problems.append(why)
    for key in STRUCTURAL_MAPPING_KEYS:
        if key not in mapping:
            continue
        expected = contract_mapping.get(key)
        if mapping.get(key) != expected:
            problems.append(
                f"mapping['{key}'] is {mapping.get(key)!r}, but format '{spec.id}' declares "
                f"{expected!r}. Structural overrides are not supported: they changed the parser "
                f"without changing the generated prompt. Use a format whose contract is the shape "
                f"you need ({', '.join(supported_names())}).")
    descriptor = descriptor or {}
    adapter = descriptor.get("typed_adapter")
    if adapter is not None and adapter != spec.envelope:
        problems.append(
            f"descriptor['typed_adapter'] is {adapter!r}, but format '{spec.id}' declares "
            f"{spec.envelope!r}. Unknown or mismatched adapter identifiers are refused.")
    return problems


# ---------------------------------------------------------------------------
# Envelope normalization
# ---------------------------------------------------------------------------

def select_shape(spec: FormatSpec, result: Dict[str, Any]) -> Tuple[FormatSpec, bool]:
    """Pick the shape to parse ``result`` with.

    Only ``widget_control`` has two during the compatibility window, and the
    rule is deterministic and total: a top-level ``has_insight`` selects the
    canonical envelope, its absence selects the legacy root-presence one.
    Returns ``(spec, legacy_used)``.
    """
    legacy = spec.legacy_wire_shape
    if legacy is not None and spec.gate_key and spec.gate_key not in result:
        return legacy, True
    return spec, False


def envelope_key_kind(spec: FormatSpec, key: str) -> str:
    """Classify a top-level key: ``defined``, ``channel`` (known channel wire
    name this format does not bind) or ``unknown``."""
    if key in spec.envelope_keys():
        return "defined"
    if key in known_channel_wire_keys():
        return "channel"
    return "unknown"
