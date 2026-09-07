"""Provider structured-output projection, codec and fallback policy (XUBB-ITC-1 §13.3, G2).

Everything provider-facing derives from ONE authoritative local contract shipped
with the package (``library/contract/normalized_insight.schema.json`` plus the
domain-envelope descriptor ``provider_response_contract.json``). No type or
field list is hand-maintained here: the projection is compiled from the local
schema, restricted to the run's effective type set, and the domain channels are
added from the descriptor. Local validation (``insight_validation``) remains
mandatory whatever the provider enforced — the projection is a structural
superset.

* :func:`compile_schema` — the conservative Structured Outputs subset: every
  object closed, every property required, optionals as nullable branches,
  local-only keywords (conditionals, lengths, patterns) stripped; open-ended
  dictionaries encoded as ``map_entries_v1``.
* :func:`schema_issues` — lint run BEFORE any call; a failing schema never
  reaches the wire.
* :func:`encode_value` / :func:`decode_value` — the lossless ``map_entries_v1``
  codec (``{"entries": [{"key", "value"}, ...]}``; nested maps recurse; duplicate
  keys, non-finite numbers, invalid envelopes and excessive depth reject).
* :func:`allow_schema_fallback` — A2-4: only ``auto`` may downgrade, once, after
  lint passed, and only on an EXACT match against an enabled signature backed by
  an evidence id. HTTP 400 alone, a generic misconfig, or message text never
  qualifies. The shipped registry enables no production signature.
* :class:`CapabilityCache` — downgrade decisions keyed by endpoint / model /
  adapter / schema version; never a global flag on a shared client.
"""
from __future__ import annotations

import json
import math
import os
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

CONTRACT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "library", "contract")
NORMALIZED_SCHEMA_FILE = os.path.join(CONTRACT_DIR, "normalized_insight.schema.json")
RESPONSE_CONTRACT_FILE = os.path.join(CONTRACT_DIR, "provider_response_contract.json")
REGISTRY_FILE = os.path.join(CONTRACT_DIR, "provider_capability_registry.json")

SCHEMA_VERSION = "1.2.0"
SCHEMA_NAME = "xubb_insight_v1"
FEATURE_JSON_SCHEMA = "response_format.json_schema"
STRUCTURED_OUTPUT_MODES: Tuple[str, ...] = ("strict", "auto", "json_object")
DEFAULT_STRUCTURED_OUTPUTS = "auto"
MAP_DEPTH_LIMIT = 32

# JSON Schema keywords the conservative provider subset does not carry; they are
# enforced LOCALLY after decoding (§13.3 "local-only constraint set").
LOCAL_ONLY = frozenset({
    "allOf", "if", "then", "else", "not", "minLength", "maxLength", "pattern",
    "minItems", "maxItems", "uniqueItems", "minimum", "maximum", "default",
    "$schema", "$comment", "title", "description",
})


def _read(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_normalized_schema() -> Dict[str, Any]:
    return _read(NORMALIZED_SCHEMA_FILE)


def load_response_contract() -> Dict[str, Any]:
    return _read(RESPONSE_CONTRACT_FILE)


def load_registry(path: Optional[str] = None) -> Dict[str, Any]:
    """The shipped registry enables NO production signature (§13.3)."""
    return _read(path or REGISTRY_FILE)


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------

def closed(properties: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def project(node: Any) -> Any:
    """Strip local-only keywords, close objects, require every property."""
    if isinstance(node, list):
        return [project(x) for x in node]
    if not isinstance(node, dict):
        return deepcopy(node)
    out: Dict[str, Any] = {}
    for k, v in node.items():
        if k in LOCAL_ONLY:
            continue
        if k == "const":
            out["enum"] = [v]
        elif k in {"properties", "$defs"}:
            out[k] = {name: project(s) for name, s in v.items()}
        else:
            out[k] = project(v)
    if "enum" in out and "type" not in out:
        types: List[str] = []
        for value in out["enum"]:
            t = ("null" if value is None else "boolean" if type(value) is bool
                 else "string" if isinstance(value, str) else "number")
            if t not in types:
                types.append(t)
        out["type"] = types[0] if len(types) == 1 else types
    if out.get("type") == "object":
        out["required"] = list(out.get("properties", {}))
        out["additionalProperties"] = False
    return out


def compile_schema(*, full: bool = False, content_extension: bool = True,
                   allowed_types: Optional[List[str]] = None) -> Dict[str, Any]:
    """The provider projection for one run.

    ``allowed_types`` restricts the type enum to the effective set (None = the
    contract's nine). An EMPTY set produces a silence-only envelope
    (``insight: null``, ``has_insight: false``) — never an empty enum (§7.3).
    ``full`` adds the domain channels from the response-contract descriptor.
    """
    local = load_normalized_schema()
    source = local["$defs"]["candidate"]
    human = source["properties"]["type"]["enum"]
    allowed = human if allowed_types is None else list(allowed_types)
    if len(allowed) != len(set(allowed)) or any(x not in human for x in allowed):
        raise ValueError("invalid_effective_types")
    value = {"anyOf": [{"type": "null"}, {"type": "boolean"}, {"type": "number"}, {"type": "string"},
                       {"type": "array", "items": {"$ref": "#/$defs/json_value"}},
                       {"$ref": "#/$defs/map"}]}
    map_def = closed({"entries": {"type": "array", "items": closed({
        "key": {"type": "string"}, "value": {"$ref": "#/$defs/json_value"}})}})
    defs: Dict[str, Any] = {"json_value": value, "map": map_def}
    props: Dict[str, Any] = {"has_insight": {"type": "boolean"}, "insight": {"type": "null"}}
    if allowed:
        candidate = project(source)
        candidate["properties"]["type"]["enum"] = list(allowed)
        candidate["properties"]["metadata"] = {"$ref": "#/$defs/map"}
        if not content_extension:
            for name in ("preview", "content_format"):
                candidate["properties"].pop(name, None)
            candidate["required"] = list(candidate["properties"])
        defs["candidate"] = candidate
        props["insight"] = {"anyOf": [{"$ref": "#/$defs/candidate"}, {"type": "null"}]}
    else:
        props["has_insight"]["enum"] = [False]
    if full:
        descriptor = load_response_contract()
        for name, item in descriptor["domain_channels"].items():
            if item["encoding"] == "map_entries_v1":
                props[name] = {"$ref": "#/$defs/map"}
            else:
                props[name] = project(item["provider_shape"])
    result = closed(props)
    result["$defs"] = defs
    return result


def schema_issues(schema: Dict[str, Any]) -> List[str]:
    """Structural lint against the conservative subset. Empty list = clean."""
    issues: List[str] = []

    def walk(node: Any, path: str = "$") -> None:
        if isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, dict):
            for key in LOCAL_ONLY & set(node):
                issues.append(f"{path}: local-only keyword {key}")
            if node.get("type") == "object":
                if node.get("additionalProperties") is not False:
                    issues.append(f"{path}: object not closed")
                if set(node.get("required", [])) != set(node.get("properties", {})):
                    issues.append(f"{path}: properties not required")
            if node.get("enum") == []:
                issues.append(f"{path}: empty enum")
            for k, v in node.items():
                if k in ("properties", "$defs"):
                    for name, child in v.items():
                        walk(child, f"{path}.{k}.{name}")
                elif k not in ("required", "enum"):
                    walk(v, f"{path}.{k}")

    walk(schema)
    return issues


def response_format_for(schema: Dict[str, Any], name: str = SCHEMA_NAME) -> Dict[str, Any]:
    """The wire ``response_format`` for a strict structured-output request."""
    return {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}}


# ---------------------------------------------------------------------------
# map_entries_v1 codec
# ---------------------------------------------------------------------------

def encode_value(value: Any, depth: int = 0) -> Any:
    if depth > MAP_DEPTH_LIMIT:
        raise ValueError("map_depth_limit")
    if value is None or type(value) in (bool, str):
        return value
    if type(value) in (int, float):
        if not math.isfinite(value):
            raise ValueError("nonfinite_json")
        return value
    if isinstance(value, list):
        return [encode_value(v, depth + 1) for v in value]
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise ValueError("nonstring_map_key")
        return {"entries": [{"key": k, "value": encode_value(v, depth + 1)} for k, v in value.items()]}
    raise ValueError("unsupported_json_value")


def decode_value(value: Any, depth: int = 0) -> Any:
    if depth > MAP_DEPTH_LIMIT:
        raise ValueError("map_depth_limit")
    if value is None or type(value) in (bool, str):
        return value
    if type(value) in (int, float):
        if not math.isfinite(value):
            raise ValueError("nonfinite_json")
        return value
    if isinstance(value, list):
        return [decode_value(v, depth + 1) for v in value]
    if not isinstance(value, dict) or set(value) != {"entries"} or not isinstance(value["entries"], list):
        raise ValueError("invalid_map_encoding")
    out: Dict[str, Any] = {}
    for entry in value["entries"]:
        if not isinstance(entry, dict) or set(entry) != {"key", "value"} or not isinstance(entry["key"], str):
            raise ValueError("invalid_map_entry")
        if entry["key"] in out:
            raise ValueError("duplicate_map_key")
        out[entry["key"]] = decode_value(entry["value"], depth + 1)
    return out


def _row_field(channel: str) -> str:
    return "value" if channel == "facts" else "payload"


def encode_response(response: Dict[str, Any], *, full: bool = False,
                    content_extension: bool = True) -> Dict[str, Any]:
    out = deepcopy(response)
    candidate = out.get("insight")
    if candidate is not None:
        candidate["metadata"] = encode_value(candidate.get("metadata", {}))
        if content_extension:
            candidate.setdefault("preview", None)
            candidate.setdefault("content_format", "plain_text")
    if full:
        for name, item in load_response_contract()["domain_channels"].items():
            if item["encoding"] == "map_entries_v1":
                out[name] = encode_value(out.get(name, {}))
            else:
                out.setdefault(name, [])
                for row in out[name]:
                    row[_row_field(name)] = encode_value(row[_row_field(name)])
    return out


def decode_response(response: Dict[str, Any], *, full: bool = False) -> Dict[str, Any]:
    """Inverse of :func:`encode_response`. Raises ``ValueError`` with the codec
    code on any malformed map — the caller turns that into a fatal
    ``invalid_domain_payload`` (nothing is silently dropped)."""
    out = deepcopy(response)
    if isinstance(out.get("insight"), dict) and "metadata" in out["insight"]:
        out["insight"]["metadata"] = decode_value(out["insight"]["metadata"])
    if full:
        for name, item in load_response_contract()["domain_channels"].items():
            if name not in out:
                continue
            if item["encoding"] == "map_entries_v1":
                out[name] = decode_value(out[name])
            elif isinstance(out[name], list):
                for row in out[name]:
                    if isinstance(row, dict) and _row_field(name) in row:
                        row[_row_field(name)] = decode_value(row[_row_field(name)])
    return out


# ---------------------------------------------------------------------------
# Fallback policy (A2-4) and capability cache
# ---------------------------------------------------------------------------

SIGNATURE_FIELDS: Tuple[str, ...] = ("adapter_id", "adapter_version", "endpoint_family",
                                     "http_status", "code", "param", "feature")


def allow_schema_fallback(failure: Dict[str, Any], registry: Dict[str, Any], *, mode: str,
                          schema_lint_passed: bool, fallback_attempted: bool = False) -> bool:
    """Exactly the reference policy: ``auto`` only, lint passed, first attempt,
    adapter-classified unsupported-capability failure for the json_schema
    feature, and an EXACT match on every signature field of an ENABLED entry
    that carries an evidence id."""
    if mode != "auto" or not schema_lint_passed or fallback_attempted:
        return False
    if failure.get("origin") != "trusted_adapter" or failure.get("category") != "unsupported_capability":
        return False
    if failure.get("feature") != FEATURE_JSON_SCHEMA:
        return False
    for rule in registry.get("enabled_signatures", []):
        if rule.get("evidence_id") and all(failure.get(k) == rule.get(k) for k in SIGNATURE_FIELDS):
            return True
    return False


CacheKey = Tuple[str, str, str, str, str]   # (endpoint, model, adapter_id, adapter_version, schema_version)


@dataclass
class CapabilityCache:
    """Per-client record of recognised downgrades, keyed by the identity the
    decision was made for. A different endpoint/model/adapter/schema version is
    a different key; changing any of them invalidates the decision naturally."""
    downgraded: Dict[CacheKey, Dict[str, Any]] = field(default_factory=dict)
    attempted: Dict[CacheKey, int] = field(default_factory=dict)

    @staticmethod
    def key(endpoint: Optional[str], model: str, adapter_id: str, adapter_version: str,
            schema_version: str = SCHEMA_VERSION) -> CacheKey:
        return (endpoint or "default", model, adapter_id, adapter_version, schema_version)

    def is_downgraded(self, key: CacheKey) -> bool:
        return key in self.downgraded

    def record_attempt(self, key: CacheKey) -> int:
        self.attempted[key] = self.attempted.get(key, 0) + 1
        return self.attempted[key]

    def record_downgrade(self, key: CacheKey, failure: Dict[str, Any]) -> None:
        self.downgraded[key] = {k: failure.get(k) for k in SIGNATURE_FIELDS + ("evidence_id",)}
