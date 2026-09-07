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
# Contract selection and the effective type set (G1, spec §7)
# ---------------------------------------------------------------------------

INSIGHT_CONTRACTS: Tuple[str, ...] = ("legacy_v2", "typed_v1")
DEFAULT_INSIGHT_CONTRACT = "legacy_v2"

# Wire values of the nine human-facing purposes, canonical order (spec §3/§4).
# Kept as plain strings here so this module stays free of pydantic/enum imports;
# tests pin it against models.HUMAN_INSIGHT_TYPES.
HUMAN_WIRE_VALUES: Tuple[str, ...] = (
    "fact", "observation", "suggestion", "warning", "opportunity", "praise",
    "reply", "correction", "question",
)


# Types whose full lifecycle is implemented on the typed path in THIS release.
# The interactive purposes exist in the enum but stay unavailable (§15.2:
# "a type existing in the enum does not make it available before its supporting
# capability is implemented") until gate G3 lands their permission, reference
# and host-correlation paths.
IMPLEMENTED_TYPED_TYPES: Tuple[str, ...] = (
    "fact", "observation", "suggestion", "warning", "opportunity", "praise",
)

# Reasons that are RUN-SPECIFIC (a capability the run lacks) map to the
# ``capability_unavailable`` diagnostic; static reasons map to ``type_not_allowed``.
RUN_SPECIFIC_UNAVAILABLE_REASONS = frozenset({"missing_principal"})


@dataclass(frozen=True)
class EffectiveTypes:
    """The run's effective human-facing set plus why each other value is absent."""
    types: Tuple[str, ...]
    unavailable: Dict[str, str]   # wire value → reason (diagnostic classification)

    def __contains__(self, value: str) -> bool:
        return value in self.types

    def diagnostic_code_for(self, value: str) -> str:
        reason = self.unavailable.get(value, "")
        return "capability_unavailable" if reason in RUN_SPECIFIC_UNAVAILABLE_REASONS else "type_not_allowed"


def effective_insight_types(*, contract: str, allowed_types: List[str],
                            allow_reply: bool, allow_question: bool, allow_correction: bool,
                            schema_supported: Optional[List[str]],
                            host_supported: List[str], host_reply_drafts: bool,
                            host_text_questions: bool, host_corrections: bool,
                            principal_present: bool,
                            implemented: Tuple[str, ...] = IMPLEMENTED_TYPED_TYPES) -> EffectiveTypes:
    """Spec §7.2: framework ∩ agent ∩ schema ∩ host ∩ permission prerequisites.

    Pure and order-preserving (canonical order). On the legacy path the set is
    the host-safe five (§7.2 "safe host type set"); everything else is enforced
    only under ``typed_v1``. Flags never expand ``allowed_types``. Reasons use
    the diagnostic vocabulary so a caller can emit ``capability_unavailable``.
    ``implemented`` is the release's implementation gate (checked LAST so the
    permission reasons above stay observable).
    """
    if contract == DEFAULT_INSIGHT_CONTRACT:
        legacy = tuple(v for v in HUMAN_WIRE_VALUES if v in LEGACY_HUMAN_TYPES)
        return EffectiveTypes(legacy, {v: "typed_contract_required" for v in HUMAN_WIRE_VALUES if v not in legacy})
    if contract not in INSIGHT_CONTRACTS:
        raise ValueError(f"unknown insight_contract {contract!r}")

    unavailable: Dict[str, str] = {}
    kept: List[str] = []
    for value in HUMAN_WIRE_VALUES:
        if value not in allowed_types:
            unavailable[value] = "not_in_agent_allowed_types"
        elif schema_supported is not None and value not in schema_supported:
            unavailable[value] = "not_supported_by_schema"
        elif value not in host_supported:
            unavailable[value] = "not_supported_by_host"
        elif value == "reply" and not (allow_reply and host_reply_drafts and principal_present):
            unavailable[value] = ("missing_principal" if (allow_reply and host_reply_drafts)
                                  else "reply_not_permitted")
        elif value == "question" and not (allow_question and host_text_questions and principal_present):
            unavailable[value] = ("missing_principal" if (allow_question and host_text_questions)
                                  else "question_not_permitted")
        elif value == "correction" and not (allow_correction and host_corrections):
            unavailable[value] = "correction_not_permitted"
        elif value not in implemented:
            unavailable[value] = "not_implemented_in_this_release"
        else:
            kept.append(value)
    return EffectiveTypes(tuple(kept), unavailable)


def effective_types_for_run(*, contract: str, insight_config: Any, descriptor: Optional[Dict[str, Any]],
                            context: Any) -> EffectiveTypes:
    """Engine/agent-shared adapter over :func:`effective_insight_types` (duck-typed
    on ``InsightConfig`` / ``AgentContext`` so this module stays import-free).
    ``context`` may be None (no host declaration ⇒ safe defaults)."""
    caps = getattr(context, "insight_capabilities", None)
    desc = descriptor or {}
    # Typed adapters advertise the structurally supported set separately from
    # the legacy instruction's literal offering.
    schema_supported = desc.get("typed_supported_insight_types", desc.get("supported_insight_types")) \
        if contract != DEFAULT_INSIGHT_CONTRACT else desc.get("supported_insight_types")
    return effective_insight_types(
        contract=contract,
        allowed_types=list(getattr(insight_config, "allowed_types", []) or []),
        allow_reply=bool(getattr(insight_config, "allow_reply", False)),
        allow_question=bool(getattr(insight_config, "allow_question", False)),
        allow_correction=bool(getattr(insight_config, "allow_correction", False)),
        schema_supported=list(schema_supported) if schema_supported is not None else None,
        host_supported=list(caps.supported_types) if caps is not None else list(LEGACY_HUMAN_TYPES),
        host_reply_drafts=bool(caps and caps.reply_drafts),
        host_text_questions=bool(caps and caps.text_questions),
        host_corrections=bool(caps and caps.corrections),
        principal_present=bool(getattr(context, "principal_id", None)),
    )


# ---------------------------------------------------------------------------
# Urgency, confidence and ranking policy (spec §6.6, D-CR) — reference-compatible
# ---------------------------------------------------------------------------

MISSING = object()   # "field absent" sentinel, distinct from an explicit null

URGENCY_ORDER = {"now": 0, "soon": 1, "whenever": 2}

# Versioned per-type fallback priors (§6.6). Product priors, not type semantics.
TYPE_URGENCY_FALLBACK = {
    "fact": "whenever", "observation": "whenever",
    "suggestion": "soon", "praise": "soon", "question": "soon",
    "warning": "now", "opportunity": "now", "reply": "now", "correction": "now",
}


def resolve_urgency(kind: str, explicit: Any = MISSING, override: Optional[str] = None) -> str:
    """Valid explicit value → configured agent override → per-type fallback.

    An explicit value that is present but invalid (including null) raises
    ``ValueError("invalid_urgency")`` — it is never defaulted (§6.6).
    """
    if kind not in TYPE_URGENCY_FALLBACK:
        raise ValueError("unknown_type")
    if explicit is not MISSING:
        if not isinstance(explicit, str) or explicit not in URGENCY_ORDER:
            raise ValueError("invalid_urgency")
        return explicit
    if override is not None:
        if not isinstance(override, str) or override not in URGENCY_ORDER:
            raise ValueError("invalid_default_urgency")
        return override
    return TYPE_URGENCY_FALLBACK[kind]


def confidence_output(value: Any = MISSING) -> Dict[str, Any]:
    """D-CR public representation. Missing/null → placeholder 1.0 + provided False
    (NOT an estimate). A finite number in [0,1] → itself + True. Booleans,
    numeric strings, NaN, infinities and out-of-range values raise
    ``ValueError("invalid_confidence")``."""
    if value is MISSING or value is None:
        return {"confidence": 1.0, "confidence_provided": False}
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or value != value or value in (float("inf"), float("-inf")) or not 0 <= value <= 1:
        raise ValueError("invalid_confidence")
    return {"confidence": float(value), "confidence_provided": True}


def rank_key(urgency: str, agent_priority: int, merge_order: Tuple[int, ...]) -> Tuple:
    """D-CR fixed total key: ``(urgency_order, -agent_priority, stable_merge_order)``.
    Confidence is deliberately absent for every candidate (a conditional pairwise
    comparator is non-transitive)."""
    return (URGENCY_ORDER[urgency], -agent_priority, tuple(merge_order))


def rank_candidates(records: List[Dict[str, Any]]) -> List[str]:
    """Reference-compatible: sort ``{id, urgency, priority, merge_order}`` records
    by the D-CR key. Duplicate stable orders are a programming error."""
    if len({tuple(r["merge_order"]) for r in records}) != len(records):
        raise ValueError("duplicate_stable_merge_order")
    return [r["id"] for r in sorted(records, key=lambda r: rank_key(r["urgency"], r["priority"], r["merge_order"]))]


def acceptance_decision(mode: str, *, insight_valid: bool, gate: Any, domain_valid: bool,
                        has_domain: bool, envelope_complete: bool = True,
                        authorized: bool = True) -> Dict[str, Any]:
    """Reference-compatible scope decision (D-LR for legacy, §8.4 for typed).

    ``domain_valid`` / ``authorized`` are prior validator results; this is the
    disposition only. ``typed_v1``: any insight error or malformed gate rejects
    the whole response. ``legacy_v2``: see :func:`decide_legacy`.
    """
    if mode not in INSIGHT_CONTRACTS:
        raise ValueError("unknown_mode")
    fatal = not envelope_complete or not domain_valid or not authorized
    valid_gate = type(gate) is bool
    insight_error = not valid_gate or (gate is True and not insight_valid)
    if fatal or (mode == "typed_v1" and insight_error):
        return {"status": "rejected", "emit_insight": False, "commit_domain": False}
    if insight_error:
        return {"status": "partial" if has_domain else "rejected",
                "emit_insight": False, "commit_domain": has_domain}
    return {"status": "accepted" if gate else "accepted_silent",
            "emit_insight": gate is True, "commit_domain": has_domain}


# ---------------------------------------------------------------------------
# Evidence catalog and reference resolution (spec §6.3–§6.4, G2)
# ---------------------------------------------------------------------------

def snapshot_ref(snapshot_id: str, kind: str, ordinal: int) -> str:
    """``snap:<opaque-snapshot-id>:<kind>:<ordinal>`` — a position inside ONE
    retained invocation snapshot, never a durable identity across windows."""
    return f"snap:{snapshot_id}:{kind}:{ordinal}"


def snapshot_catalog(exposed_segments: List[Dict[str, Any]], snapshot_id: str) -> List[Dict[str, Any]]:
    """Reference-compatible: catalog entries for the segments ACTUALLY exposed to
    the agent (build it after context trimming). Each occurrence gets its own
    ordinal — two identical segments are two references. Sources are copied so
    later mutation of the live transcript cannot change the snapshot."""
    if not isinstance(snapshot_id, str) or not snapshot_id.strip():
        raise ValueError("invalid_snapshot_id")
    from copy import deepcopy
    return [{"kind": "segment", "ref_id": snapshot_ref(snapshot_id, "segment", i),
             "revision": snapshot_id, "source": deepcopy(segment)}
            for i, segment in enumerate(exposed_segments)]


@dataclass
class ReferenceContext:
    """Everything a reference may resolve against in ONE run: the framework's
    snapshot entries plus the host's supplied records for THIS session.
    Entries owned by another session are tracked so a reference to them is a
    ``cross_session_reference`` rather than merely unknown."""
    session_id: str
    snapshot_id: str
    entries: Dict[Tuple[str, str], Optional[str]] = field(default_factory=dict)   # (kind, ref_id) → revision
    foreign: Dict[Tuple[str, str], str] = field(default_factory=dict)             # (kind, ref_id) → other session

    def add(self, kind: str, ref_id: str, revision: Optional[str], session_id: Optional[str] = None) -> None:
        key = (kind, ref_id)
        if session_id is not None and session_id != self.session_id:
            self.foreign[key] = session_id
        else:
            self.entries[key] = revision

    def resolve(self, ref: Dict[str, Any], field_path: str) -> Tuple[Optional[Issue], Optional[str]]:
        """→ (issue, resolved revision). A null revision resolves to the catalog's
        current revision; a stated revision must match exactly (§6.4: pruned or
        revised evidence is unavailable, never a guess)."""
        key = (ref.get("kind"), ref.get("ref_id"))
        if key in self.entries:
            expected = self.entries[key]
            stated = ref.get("revision")
            if stated is not None and expected is not None and stated != expected:
                return Issue("unknown_reference", field_path, "revision_mismatch"), None
            return None, stated if stated is not None else expected
        if key in self.foreign:
            return Issue("cross_session_reference", field_path, bounded(self.foreign[key])), None
        return Issue("unknown_reference", field_path, bounded(ref.get("ref_id"))), None


# ---------------------------------------------------------------------------
# Typed candidate validation (typed_v1, spec §6.2, §8.2–§8.4)
# ---------------------------------------------------------------------------

# The normalized candidate vocabulary (docs/reference/insight_types_1.2.0/
# normalized_insight.schema.json). Anything else at the candidate root is
# ``invalid_field`` — a strict local check, whatever the provider enforced.
TYPED_CANDIDATE_FIELDS: Tuple[str, ...] = (
    "type", "content", "confidence", "urgency", "observation_kind", "evidence_refs",
    "rationale", "validation_step", "assumptions", "correction", "question", "metadata",
    "preview", "content_format",
)
CONTENT_EXTENSION_FIELDS: Tuple[str, ...] = ("preview", "content_format")
ENGINE_OWNED_CANDIDATE_KEYS: Tuple[str, ...] = (
    "id", "turn", "contract_version", "confidence_provided", "content_contract",
    "response_depth", "content_request_id", "source_snapshot_id", "acceptance_status",
    "origin", "agent_id", "agent_name",
)
# Legacy pass-through extras a declared typed adapter may carry (S-1); they are
# normalised OFF the candidate before strict validation.
ADAPTER_PASSTHROUGH_FIELDS: Tuple[str, ...] = ("expiry", "action_label")


@dataclass
class TypedCandidate:
    type_value: str
    content: str
    confidence: float
    confidence_provided: bool
    urgency: str
    observation_kind: Optional[str] = None
    evidence_refs: List[Dict[str, Any]] = field(default_factory=list)
    rationale: Optional[str] = None
    validation_step: Optional[str] = None
    assumptions: List[str] = field(default_factory=list)
    correction: Optional[Dict[str, Any]] = None
    question: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def _nonblank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _optional_nonblank(value: Any) -> bool:
    return value is None or _nonblank(value)


def evaluate_typed_gate(gate_mode: str, gate_value: Any, candidate: Any
                        ) -> Tuple[bool, Optional[Issue]]:
    """Typed gates (§8.2). Boolean: only ``True`` speaks; ``False`` with a null
    candidate is silence; ``False`` + non-null candidate is ``inconsistent_gate``;
    ``True`` + null candidate is ``inconsistent_gate``; anything else is
    ``invalid_gate``. Root presence: null/absent/{} silence, dict speaks, other
    ``invalid_gate``. In typed mode every gate issue rejects the response."""
    if gate_mode == "boolean":
        if gate_value is True:
            if candidate is None:
                return False, Issue("inconsistent_gate", "insight", "null_candidate_with_true_gate")
            return True, None
        if gate_value is False:
            if candidate is not None:
                return False, Issue("inconsistent_gate", "insight", "candidate_with_false_gate")
            return False, None
        return False, Issue("invalid_gate", "has_insight",
                            "missing" if gate_value is MISSING else bounded(gate_value))
    if gate_mode == "root_presence":
        if candidate is MISSING or candidate is None or candidate == {}:
            return False, None
        if isinstance(candidate, dict):
            return True, None
        return False, Issue("invalid_gate", "insight", bounded(candidate))
    return False, None


def validate_typed_candidate(candidate: Any, *, effective: EffectiveTypes,
                             analysis_profile: str = "general",
                             default_urgency: Optional[str] = None,
                             reference_context_available: bool = False,
                             content_extension_enabled: bool = False,
                             reference_context: Optional[ReferenceContext] = None
                             ) -> Tuple[Optional[TypedCandidate], List[Issue]]:
    """Strict local validation of a normalized candidate (§8.3).

    Returns ``(candidate, [])`` or ``(None, issues)``; every issue is fatal
    under typed atomicity. No coercion: unknown keys, engine-owned keys,
    display-name types, non-finite confidence, invalid urgency, subtype
    conflicts, unresolvable evidence and un-negotiated content-extension
    fields all reject. Evidence resolves against ``reference_context`` when
    given (G2); ``reference_context_available=True`` without a context accepts
    any well-formed reference (shape-level comparison only).
    """
    if reference_context is not None:
        reference_context_available = True
    issues: List[Issue] = []
    if not isinstance(candidate, dict):
        return None, [Issue("invalid_field", "insight", bounded(candidate))]

    # 1. Key discipline
    for key in candidate:
        if key in ENGINE_OWNED_CANDIDATE_KEYS:
            issues.append(Issue("invalid_field", f"insight.{key}", "engine_owned"))
        elif key in CONTENT_EXTENSION_FIELDS and not content_extension_enabled:
            issues.append(Issue("content_extension_not_enabled", f"insight.{key}"))
        elif key not in TYPED_CANDIDATE_FIELDS:
            issues.append(Issue("invalid_field", f"insight.{key}", "unexpected_key"))

    # 2. Type — exact wire value, in the effective set
    raw_type = candidate.get("type")
    type_value: Optional[str] = None
    if not isinstance(raw_type, str):
        issues.append(Issue("invalid_field", "insight.type", "missing" if raw_type is None else bounded(raw_type)))
    elif raw_type not in HUMAN_WIRE_VALUES:
        issues.append(Issue("unknown_type", "insight.type", bounded(raw_type)))
    elif raw_type not in effective:
        issues.append(Issue(effective.diagnostic_code_for(raw_type), "insight.type",
                            effective.unavailable.get(raw_type, bounded(raw_type))))
    else:
        type_value = raw_type

    # 3. Content
    content = candidate.get("content")
    if not (isinstance(content, str) and len(content) >= 2 and content.strip()):
        issues.append(Issue("invalid_field", "insight.content", "missing" if content is None else bounded(content)))

    # 4. Confidence (strict; missing/null = not provided)
    try:
        conf = confidence_output(candidate.get("confidence", MISSING))
    except ValueError:
        conf = None
        issues.append(Issue("invalid_confidence", "insight.confidence", bounded(candidate.get("confidence"))))

    # 5. Urgency (explicit valid → agent override → type fallback; invalid rejects)
    urgency: Optional[str] = None
    if type_value is not None:
        explicit = candidate["urgency"] if "urgency" in candidate else MISSING
        try:
            urgency = resolve_urgency(type_value, explicit, default_urgency)
        except ValueError as e:
            issues.append(Issue("invalid_urgency", "insight.urgency", bounded(candidate.get("urgency")) if str(e) == "invalid_urgency" else str(e)))

    # 6. Metadata (dict; no engine-owned keys smuggled in)
    metadata = candidate.get("metadata", {})
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        issues.append(Issue("invalid_metadata", "insight.metadata", bounded(metadata)))
        metadata = {}
    else:
        for key in metadata:
            if key in ENGINE_OWNED_CANDIDATE_KEYS:
                issues.append(Issue("invalid_metadata", f"insight.metadata.{key}", "engine_owned"))

    # 7. Analytical fields
    kind = candidate.get("observation_kind")
    rationale = candidate.get("rationale")
    validation_step = candidate.get("validation_step")
    assumptions = candidate.get("assumptions", [])
    refs = candidate.get("evidence_refs", [])
    if kind not in (None, "hypothesis", "implication"):
        issues.append(Issue("invalid_field", "insight.observation_kind", bounded(kind)))
        kind = None
    if kind is not None and type_value is not None and type_value != "observation":
        issues.append(Issue("invalid_field", "insight.observation_kind", "subtype_on_non_observation"))
    if kind is not None and analysis_profile != "consulting":
        issues.append(Issue("capability_unavailable", "insight.observation_kind", "consulting_profile_required"))
    if not _optional_nonblank(rationale):
        issues.append(Issue("invalid_field", "insight.rationale", bounded(rationale)))
    if not _optional_nonblank(validation_step):
        issues.append(Issue("invalid_field", "insight.validation_step", bounded(validation_step)))
    if validation_step is not None and kind != "hypothesis":
        issues.append(Issue("invalid_field", "insight.validation_step", "only_for_hypothesis"))
    if not isinstance(assumptions, list) or not all(_nonblank(a) for a in assumptions):
        issues.append(Issue("invalid_field", "insight.assumptions", bounded(assumptions)))
        assumptions = []
    resolved_refs: List[Dict[str, Any]] = []
    if not isinstance(refs, list):
        issues.append(Issue("invalid_field", "insight.evidence_refs", bounded(refs)))
        refs = []
    else:
        for i, ref in enumerate(refs):
            path = f"insight.evidence_refs[{i}]"
            ok = (isinstance(ref, dict) and set(ref) <= {"kind", "ref_id", "revision"}
                  and ref.get("kind") in ("segment", "document", "fact", "insight")
                  and _nonblank(ref.get("ref_id")) and _optional_nonblank(ref.get("revision")))
            if not ok:
                issues.append(Issue("invalid_field", path, bounded(ref)))
            elif reference_context is not None:
                issue, revision = reference_context.resolve(ref, path)
                if issue:
                    issues.append(issue)
                else:
                    resolved_refs.append({"kind": ref["kind"], "ref_id": ref["ref_id"], "revision": revision})
            elif not reference_context_available:
                # No catalog can vouch for this reference in this run. Never
                # accept a reference nothing exposed.
                issues.append(Issue("unknown_reference", path, "no_reference_context"))
            else:
                resolved_refs.append({"kind": ref["kind"], "ref_id": ref["ref_id"], "revision": ref.get("revision")})
    refs = resolved_refs if not issues else refs
    if kind == "hypothesis":
        if not refs:
            issues.append(Issue("missing_evidence", "insight.evidence_refs", "hypothesis_requires_evidence"))
        if rationale is None:
            issues.append(Issue("invalid_field", "insight.rationale", "hypothesis_requires_rationale"))
        if validation_step is None:
            issues.append(Issue("invalid_field", "insight.validation_step", "hypothesis_requires_validation_step"))
    if kind == "implication":
        if not refs:
            issues.append(Issue("missing_evidence", "insight.evidence_refs", "implication_requires_evidence"))
        if rationale is None:
            issues.append(Issue("invalid_field", "insight.rationale", "implication_requires_rationale"))

    # 8. Interactive payloads: present only for their own type, required there,
    #    and shape-checked (§6.3 normative shapes; unexpected keys rejected)
    correction = candidate.get("correction")
    question = candidate.get("question")
    if correction is not None and type_value != "correction":
        issues.append(Issue("invalid_field", "insight.correction", "payload_on_non_correction"))
    if question is not None and type_value != "question":
        issues.append(Issue("invalid_question_contract", "insight.question", "payload_on_non_question"))
    if type_value == "correction":
        ok = (isinstance(correction, dict) and set(correction) == {"target_insight_id", "operation", "reason"}
              and _nonblank(correction.get("target_insight_id"))
              and correction.get("operation") in ("replace", "withdraw") and _nonblank(correction.get("reason")))
        if not ok:
            issues.append(Issue("invalid_correction_target", "insight.correction",
                                "missing" if correction is None else bounded(correction)))
    if type_value == "question":
        ok = (isinstance(question, dict) and set(question) == {"reason", "response_format"}
              and _nonblank(question.get("reason")) and question.get("response_format") == "text")
        if not ok:
            issues.append(Issue("invalid_question_contract", "insight.question",
                                "missing" if question is None else bounded(question)))

    # 9. Content-extension fields: shape only (limits/negotiation are the C1
    #    content contract); reachable only when the extension is enabled.
    if content_extension_enabled:
        if "preview" in candidate and not _optional_nonblank(candidate.get("preview")):
            issues.append(Issue("invalid_field", "insight.preview", bounded(candidate.get("preview"))))
        if "content_format" in candidate and candidate.get("content_format") not in ("plain_text", "markdown"):
            issues.append(Issue("unsupported_content_format", "insight.content_format",
                                bounded(candidate.get("content_format"))))

    if issues:
        return None, issues
    assert type_value and conf is not None and urgency is not None and isinstance(content, str)
    return TypedCandidate(
        type_value=type_value, content=content,
        confidence=conf["confidence"], confidence_provided=conf["confidence_provided"],
        urgency=urgency, observation_kind=kind, evidence_refs=list(refs),
        rationale=rationale, validation_step=validation_step, assumptions=list(assumptions),
        correction=correction, question=question, metadata=dict(metadata),
    ), []


def decide_typed(speak: bool, insight_issues: List[Issue], domain_issues: List[Issue]) -> Decision:
    """§8.4 typed atomicity: any insight or domain issue makes the whole
    response non-committable. Valid silence still commits its channels."""
    if insight_issues or domain_issues:
        return Decision("rejected", False, False)
    return Decision("accepted" if speak else "accepted_silent", speak, True)


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
