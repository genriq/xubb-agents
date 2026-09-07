"""Pure validators for the insight contract (XUBB-ITC-1).

G0 — legacy safety (``legacy_v2``). This module owns the *decisions*; it never
touches an agent, the Blackboard, or a callback, so every rule is unit-testable
with plain dicts and reusable by ``DynamicAgent`` and by the engine boundary
check for custom ``BaseAgent`` subclasses.

Rules implemented here (spec §8.2, §8.6, FINAL_DECISIONS.md D-LR):

* **Gates are declared, never truthiness.** A Boolean gate speaks only on an
  actual ``True``; ``False`` is valid silence; anything else (``"false"``,
  ``1``, ``None``, missing) is ``invalid_gate``. Presence-gated adapters speak
  on a non-empty root object; content-presence adapters (``custom1``) speak
  on a non-empty content string. Gate-less schemas stay silent unless
  ``speak_without_gate`` opts in (A-1 / INV-11, unchanged).
* **Unknown classifications are rejected, never relabelled.** A type label
  that is not a permitted wire value rejects the insight. Nothing here maps
  an unknown label to suggestion, observation or any other purpose.
* **Recoverable insight errors are insight-only in legacy mode.** The
  response's independently validated, authorized domain channels may still
  commit, with an explicit ``partial`` status; action-bearing sidecars are
  withheld. Fatal errors (invalid domain payload, reserved-state write,
  unparseable envelope) reject the whole response.
* **No relabel, no guess, no silent drop**: every rejection produces a
  sanitized :class:`~xubb_agents.core.models.InsightDiagnostic`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

# The host-safe legacy set (spec §7.2): the five existing non-error wire values.
# In legacy_v2 this is the effective human-facing set regardless of schema;
# schema-level restriction becomes active with typed_v1 (G1).
LEGACY_HUMAN_TYPES: Tuple[str, ...] = ("suggestion", "warning", "opportunity", "fact", "praise")

# Wire values the framework knows about but which are NOT permitted on the
# legacy path: the framework-manufactured diagnostic and the four purposes that
# require the negotiated typed contract (§8.6). A model writing one of these is
# ``type_not_allowed`` (recognised, disallowed) rather than ``unknown_type``.
RESERVED_WIRE_VALUES: Tuple[str, ...] = ("error", "observation", "reply", "correction", "question")

# Legacy adapters historically defaulted an ABSENT type to "suggestion" (the
# ``default`` schema's parser did so since v1). That is a declared adapter
# default for an omitted field, not a relabel of an unknown label, and is kept
# on the legacy path only. Typed mode (G1) requires an explicit type.
LEGACY_DEFAULT_TYPE = "suggestion"

# Spec §14 required categories, plus ``invalid_envelope`` (an LLM result that
# never produced a JSON object at all — malformed / null / non-dict).
DIAGNOSTIC_CODES: Tuple[str, ...] = (
    "invalid_gate", "inconsistent_gate", "unknown_type", "type_not_allowed",
    "invalid_field", "invalid_metadata", "invalid_confidence", "invalid_urgency",
    "missing_evidence", "unknown_reference", "cross_session_reference",
    "missing_principal", "capability_unavailable", "invalid_correction_target",
    "correction_conflict", "invalid_question_contract", "invalid_input_reference",
    "no_supported_insight_types", "invalid_domain_payload", "reserved_state_write",
    "partial_legacy_response", "unsupported_structured_output", "provider_schema_error",
    "content_execution_not_allowed", "invalid_content_execution_context",
    "content_contract_unavailable", "invalid_content_policy", "unsupported_depth",
    "unsupported_content_format", "content_too_large", "preview_too_large",
    "response_too_large", "content_extension_not_enabled", "incomplete_generation",
    "completion_unknown",
    # framework additions (documented in CHANGELOG)
    "invalid_envelope",
)

GATE_MODES: Tuple[str, ...] = ("boolean", "root_presence", "content_presence", "gateless", "state_only")

# Engine-reserved variable namespace (INV-4). A model proposing a write here is
# a fatal ``reserved_state_write`` under D-LR (the whole response rejects).
RESERVED_VAR_PREFIX = "sys."
# Legacy memory routing prefix in v1 ``state_updates`` (E-3); not reserved.
LEGACY_MEMORY_PREFIX = "memory_"

_CLASSIFICATION_MAX = 64
_MISSING = object()


# ---------------------------------------------------------------------------
# Issue record
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Issue:
    """One validation finding. ``fatal`` issues reject the whole response."""
    code: str
    field_path: str = ""
    classification: Optional[str] = None
    fatal: bool = False

    def __post_init__(self) -> None:
        if self.code not in DIAGNOSTIC_CODES:  # pragma: no cover - programming error
            raise ValueError(f"unknown diagnostic code {self.code!r}")


def bounded(value: Any) -> Optional[str]:
    """A bounded classification string for diagnostics — never raw content."""
    if value is None:
        return None
    text = value if isinstance(value, str) else type(value).__name__
    return text[:_CLASSIFICATION_MAX]


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------

def resolve_gate_mode(mapping: Dict[str, Any], descriptor: Optional[Dict[str, Any]] = None) -> str:
    """Resolve the declared gate mode for a schema (§8.2).

    A versioned descriptor wins. Otherwise the mode is inferred from the
    mapping exactly as the A-1 precedence documented it: ``check_field`` ⇒
    boolean; ``root_key`` ⇒ root presence; ``speak_without_gate`` ⇒ content
    presence (the explicit opt-in); nothing ⇒ gate-less (silent).
    """
    declared = (descriptor or {}).get("gate_mode")
    # A declared mode is honoured only when the mapping can support it: a
    # "boolean" descriptor without a check_field (or "root_presence" without a
    # root_key) is a mis-declaration, and the safe answer is the A-1 inference,
    # never a gate that can only ever read "missing".
    if declared == "boolean" and mapping.get("check_field"):
        return declared
    if declared == "root_presence" and mapping.get("root_key"):
        return declared
    if declared == "content_presence" and (mapping.get("check_field") or mapping.get("content_field")):
        return declared
    if declared in ("gateless", "state_only"):
        return declared
    if mapping.get("check_field"):
        return "boolean"
    if mapping.get("root_key"):
        return "root_presence"
    if mapping.get("speak_without_gate"):
        return "content_presence"
    return "gateless"


def evaluate_gate(mode: str, mapping: Dict[str, Any], result: Dict[str, Any],
                  root_data: Dict[str, Any]) -> Tuple[bool, Optional[Issue]]:
    """Return ``(speak, issue)``.

    ``speak`` is True only for an unambiguous gate. An ``issue`` (always
    ``invalid_gate``) means the gate was present but malformed; the response
    then follows the recoverable-insight-error path (never speaks).
    """
    if mode == "boolean":
        key = mapping.get("check_field") or "has_insight"
        value = root_data.get(key, _MISSING)
        if value is True:
            return True, None
        if value is False:
            return False, None
        classification = "missing" if value is _MISSING else bounded(value)
        return False, Issue("invalid_gate", key, classification)

    if mode == "root_presence":
        key = mapping.get("root_key") or "insight"
        root = result.get(key, _MISSING)
        if root is _MISSING or root is None or root == {}:
            return False, None
        if isinstance(root, dict):
            return True, None
        return False, Issue("invalid_gate", key, bounded(root))

    if mode == "content_presence":
        key = mapping.get("check_field") or mapping.get("content_field") or "content"
        value = root_data.get(key, _MISSING)
        if value is _MISSING or value is None or value == "":
            return False, None
        if isinstance(value, str) and value.strip():
            return True, None
        return False, Issue("invalid_gate", key, bounded(value))

    # "gateless" and "state_only": there is no structural gate — silence.
    return False, None


# ---------------------------------------------------------------------------
# Candidate (insight) fields — legacy adapter rules
# ---------------------------------------------------------------------------

@dataclass
class LegacyCandidate:
    type_value: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)


def normalize_legacy_type(raw_type: Any, allowed: Tuple[str, ...] = LEGACY_HUMAN_TYPES,
                          field_path: str = "type") -> Tuple[Optional[str], Optional[Issue]]:
    """Resolve a model-authored type label on the legacy path.

    * absent/None → the declared legacy default (``suggestion``);
    * a string is case-folded and stripped (a declared legacy normalisation,
      ``"Warning"`` unambiguously names warning — this is not a relabel);
    * a recognised-but-disallowed value → ``type_not_allowed``;
    * anything else → ``unknown_type``.
    Never maps an unknown label onto another purpose.
    """
    if raw_type is None:
        return LEGACY_DEFAULT_TYPE, None
    if not isinstance(raw_type, str):
        return None, Issue("unknown_type", field_path, bounded(raw_type))
    value = raw_type.strip().casefold()
    if value in allowed:
        return value, None
    if value in RESERVED_WIRE_VALUES:
        return None, Issue("type_not_allowed", field_path, bounded(value))
    return None, Issue("unknown_type", field_path, bounded(value))


def validate_legacy_candidate(root_data: Dict[str, Any], mapping: Dict[str, Any],
                              allowed: Tuple[str, ...] = LEGACY_HUMAN_TYPES
                              ) -> Tuple[Optional[LegacyCandidate], List[Issue]]:
    """Validate the insight fields of a speaking legacy response.

    Confidence / expiry / action_label keep their documented legacy coercions
    (A-3, S-1) and are applied by the caller; this function only decides the
    classification, the content and the metadata shape.
    """
    issues: List[Issue] = []
    type_key = mapping.get("type_field", "type")
    type_value, issue = normalize_legacy_type(root_data.get(type_key), allowed, type_key)
    if issue:
        issues.append(issue)

    content_key = mapping.get("content_field", "content")
    content = root_data.get(content_key)
    if not isinstance(content, str) or len(content.strip()) < 2:
        issues.append(Issue("invalid_field", content_key, bounded(content) if content is not None else "missing"))

    metadata: Dict[str, Any] = {}
    meta_key = mapping.get("metadata_field")
    if meta_key:
        raw_meta = root_data.get(meta_key)
        if raw_meta is None:
            metadata = {}
        elif isinstance(raw_meta, dict):
            metadata = dict(raw_meta)
        else:
            issues.append(Issue("invalid_metadata", meta_key, bounded(raw_meta)))

    if issues:
        return None, issues
    assert type_value is not None and isinstance(content, str)
    return LegacyCandidate(type_value=type_value, content=content, metadata=metadata, raw=root_data), []


# ---------------------------------------------------------------------------
# Domain channels — independent validation and write authorization
# ---------------------------------------------------------------------------

@dataclass
class DomainChannels:
    """Shape-validated domain proposals (still untrusted content)."""
    events: List[Any] = field(default_factory=list)
    variable_updates: Dict[str, Any] = field(default_factory=dict)
    queue_pushes: Dict[str, List[Any]] = field(default_factory=dict)
    facts: List[Dict[str, Any]] = field(default_factory=list)
    memory_updates: Dict[str, Any] = field(default_factory=dict)
    state: Optional[Dict[str, Any]] = None       # legacy ``state_field`` payload
    state_is_memory: bool = False                # state_field == "memory_updates"
    data: Any = None                             # action-bearing sidecar (never partial)

    def retained_names(self) -> List[str]:
        names = []
        if self.events: names.append("events")
        if self.variable_updates: names.append("variable_updates")
        if self.queue_pushes: names.append("queue_pushes")
        if self.facts: names.append("facts")
        if self.memory_updates: names.append("memory_updates")
        if self.state: names.append("state_updates")
        return names

    def has_domain(self) -> bool:
        """Non-sidecar channels present (sidecars never count for partial)."""
        return bool(self.retained_names())


def _reserved_keys(mapping_dict: Dict[str, Any], exclude_memory: bool = False) -> List[str]:
    keys = []
    for key in mapping_dict:
        if not isinstance(key, str):
            continue
        if exclude_memory and key.startswith(LEGACY_MEMORY_PREFIX):
            continue
        if key.startswith(RESERVED_VAR_PREFIX):
            keys.append(key)
    return keys


def validate_domain_channels(result: Dict[str, Any], mapping: Dict[str, Any]
                             ) -> Tuple[DomainChannels, List[Issue]]:
    """Shape-check every mapped domain channel independently of the insight.

    Absent or ``None`` channels are simply empty. A channel that is present
    with the wrong shape is ``invalid_domain_payload`` (fatal). A proposed
    write to the engine-reserved ``sys.*`` namespace is ``reserved_state_write``
    (fatal). Presence-validated content stays an untrusted proposal.
    """
    issues: List[Issue] = []
    ch = DomainChannels()

    def fatal(code: str, path: str, value: Any = None) -> None:
        issues.append(Issue(code, path, bounded(value), fatal=True))

    # events: list of dict (with a string name) or plain strings
    events_field = mapping.get("events_field", "events")
    raw_events = result.get(events_field)
    if raw_events is not None:
        if not isinstance(raw_events, list):
            fatal("invalid_domain_payload", events_field, raw_events)
        else:
            for i, evt in enumerate(raw_events):
                if isinstance(evt, str):
                    continue
                if not isinstance(evt, dict) or not isinstance(evt.get("name", ""), str):
                    fatal("invalid_domain_payload", f"{events_field}[{i}]", evt)
            ch.events = list(raw_events)

    # variable_updates: dict; sys.* keys are reserved
    var_field = mapping.get("variable_updates_field", "variable_updates")
    raw_vars = result.get(var_field)
    if raw_vars is not None:
        if not isinstance(raw_vars, dict):
            fatal("invalid_domain_payload", var_field, raw_vars)
        else:
            for key in _reserved_keys(raw_vars):
                fatal("reserved_state_write", f"{var_field}.{key}", key)
            ch.variable_updates = dict(raw_vars)

    # queue_pushes: dict[str, list]
    queue_field = mapping.get("queue_field", "queue_pushes")
    raw_queues = result.get(queue_field)
    if raw_queues is not None:
        if not isinstance(raw_queues, dict):
            fatal("invalid_domain_payload", queue_field, raw_queues)
        else:
            for name, items in raw_queues.items():
                if not isinstance(items, list):
                    fatal("invalid_domain_payload", f"{queue_field}.{name}", items)
            ch.queue_pushes = {k: list(v) for k, v in raw_queues.items() if isinstance(v, list)}

    # facts: list of dicts; confidence (if present) must be a finite number in [0,1]
    facts_field = mapping.get("facts_field", "facts")
    raw_facts = result.get(facts_field)
    if raw_facts is not None:
        if not isinstance(raw_facts, list):
            fatal("invalid_domain_payload", facts_field, raw_facts)
        else:
            for i, f in enumerate(raw_facts):
                if not isinstance(f, dict):
                    fatal("invalid_domain_payload", f"{facts_field}[{i}]", f)
                    continue
                conf = f.get("confidence", 1.0)
                if isinstance(conf, bool) or not isinstance(conf, (int, float)) \
                        or conf != conf or not (0.0 <= conf <= 1.0):
                    fatal("invalid_domain_payload", f"{facts_field}[{i}].confidence", conf)
                if "type" in f and not isinstance(f["type"], str):
                    fatal("invalid_domain_payload", f"{facts_field}[{i}].type", f["type"])
            ch.facts = [dict(f) for f in raw_facts if isinstance(f, dict)]

    # memory_updates (v2): dict
    memory_field = mapping.get("memory_field", "memory_updates")
    raw_memory = result.get(memory_field)
    if raw_memory is not None:
        if not isinstance(raw_memory, dict):
            fatal("invalid_domain_payload", memory_field, raw_memory)
        else:
            ch.memory_updates = dict(raw_memory)

    # legacy state_field: dict; when it is not the memory alias, sys.* is reserved
    state_key = mapping.get("state_field")
    if state_key:
        raw_state = result.get(state_key)
        if raw_state is not None:
            if not isinstance(raw_state, dict):
                fatal("invalid_domain_payload", state_key, raw_state)
            else:
                ch.state = dict(raw_state)
                ch.state_is_memory = state_key == "memory_updates"
                if not ch.state_is_memory:
                    for key in _reserved_keys(raw_state, exclude_memory=True):
                        fatal("reserved_state_write", f"{state_key}.{key}", key)

    # data sidecar: any shape; it is action-bearing and never partially accepted
    data_field = mapping.get("data_field")
    if data_field:
        payload = result.get(data_field)
        if payload:
            ch.data = payload

    return ch, issues


# ---------------------------------------------------------------------------
# D-LR decision
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Decision:
    status: str            # AcceptanceStatus
    emit_insight: bool
    commit_domain: bool


def decide_legacy(speak: bool, insight_issues: List[Issue], domain_issues: List[Issue],
                  has_domain: bool) -> Decision:
    """The D-LR table (FINAL_DECISIONS.md), legacy_v2 only.

    * any fatal domain issue → ``rejected`` (nothing commits);
    * an insight error (malformed gate, unknown type, invalid insight field)
      → all insights rejected; ``partial`` when independently valid channels
      remain, otherwise ``rejected``;
    * otherwise ``accepted`` (spoke) or ``accepted_silent``.
    """
    if any(i.fatal for i in domain_issues):
        return Decision("rejected", False, False)
    if insight_issues:
        if has_domain:
            return Decision("partial", False, True)
        return Decision("rejected", False, False)
    if speak:
        return Decision("accepted", True, True)
    return Decision("accepted_silent", False, True)
