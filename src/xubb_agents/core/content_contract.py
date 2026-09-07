"""The negotiated long-form content contract ``long_form_v1`` (XUBB-ITC-1 §14.4–§14.10, C1).

Reference-compatible policy: :func:`execution_admission` and
:func:`check_content_contract` are ports of the package's reference checkers,
so the 62 packaged content fixtures reproduce against the framework. They are
PURE — the adapter runs admission BEFORE generation and the full check AFTER,
against trusted runtime telemetry (completion status, transport bytes) and
host/runtime declarations (execution context), never model metadata.

Rules (spec):
* an insight may be brief or extended; its TYPE describes purpose, not length;
* the complete accepted body lives in ``content``; ``preview`` is an optional
  plain-text entry point that never replaces or truncates it;
* depth (brief | standard | detailed) is an objective, not a minimum length;
  the effective limits are the most restrictive of profile, host and operator;
  characters are decoded code points, bytes are a separate UTF-8 ceiling;
* only a COMPLETE generation whose whole response validates may emit an
  extended insight — a parseable fragment is not a complete body;
* extended generation during an ACTIVE session needs the isolated content path
  (C2); otherwise paused (declared) or post-session only. FORCE is neither
  authorization nor isolation.
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Mapping, Optional

CONTRACT = "long_form_v1"
DEPTHS = frozenset({"brief", "standard", "detailed"})
FORMATS = frozenset({"plain_text", "markdown"})
SESSION_MODES = frozenset({"active", "paused", "post_session"})
EXECUTION_PATHS = frozenset({"live_turn", "isolated_content", "offline_content"})
EXTENDED_DEPTHS = frozenset({"standard", "detailed"})


def positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def positive_number(value: Any) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value > 0)


def _result(accepted: bool, codes: List[str], **details: Any) -> Dict[str, Any]:
    return {"accepted": accepted, "codes": codes, **details}


# ---------------------------------------------------------------------------
# §14.6.1 admission (reference-compatible)
# ---------------------------------------------------------------------------

def execution_admission(depth: str, profile: Mapping[str, Any], context: Any,
                        operator: Mapping[str, Any], *, candidate_type: Optional[str] = None,
                        domain_effects_present: bool = False) -> Dict[str, Any]:
    """Admission against trusted DECLARATIONS (host/runtime facts). Booleans
    asserting isolation never replace actual concurrency tests (C2)."""
    def no(code: str) -> Dict[str, Any]:
        return {"accepted": False, "code": code}
    if not isinstance(context, Mapping):
        return no("invalid_content_execution_context")
    mode, path = context.get("session_mode"), context.get("execution_path")
    if mode not in SESSION_MODES or path not in EXECUTION_PATHS:
        return no("invalid_content_execution_context")
    if mode == "paused" and context.get("pause_declared") is not True:
        return no("content_execution_not_allowed")
    if mode == "active" and path == "offline_content":
        return no("content_execution_not_allowed")
    if mode == "active" and path == "isolated_content":
        required_ids = (context.get("request_id"), context.get("source_snapshot_id"))
        if not all(isinstance(x, str) and x.strip() for x in required_ids):
            return no("invalid_content_execution_context")
        if (context.get("holds_live_turn_lock") is not False
                or context.get("writes_live_blackboard") is not False
                or context.get("task_isolation_verified") is not True):
            return no("content_execution_not_allowed")
        if domain_effects_present or candidate_type in {"correction", "question"}:
            return no("content_execution_not_allowed")
    if mode == "active" and path == "live_turn":
        cap = operator.get("live_max_output_tokens")
        timeout = operator.get("live_max_timeout_seconds")
        if (type(cap) is not int or cap <= 0 or isinstance(timeout, bool)
                or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0):
            return no("invalid_content_execution_context")
        if (depth != "brief" or profile["max_output_tokens"] > cap
                or profile["llm_timeout_seconds"] > timeout):
            return no("content_execution_not_allowed")
    return {"accepted": True, "code": None}


# ---------------------------------------------------------------------------
# §14.5–§14.7 content policy (reference-compatible)
# ---------------------------------------------------------------------------

def check_content_contract(envelope: Mapping[str, Any], configuration: Mapping[str, Any], *,
                           request: Optional[Mapping[str, Any]] = None,
                           execution: Optional[Mapping[str, Any]] = None,
                           serialized_response: Optional[bytes] = None) -> Dict[str, Any]:
    """Policy decision for one normalized envelope. Character units are decoded
    code points (``len(str)``); the byte ceiling counts the supplied transport
    bytes, else the compact UTF-8 serialization of the envelope."""
    agent = configuration.get("agent_content", {})
    host = configuration.get("host_content", {})
    operator = configuration.get("operator_limits", {})
    schema_contracts = configuration.get("schema_content_contracts", [])
    if not all(isinstance(x, Mapping) for x in (agent, host, operator)):
        return _result(False, ["invalid_content_policy"])
    candidate = envelope.get("insight")
    selected_contract = agent.get("contract")

    # A base typed_v1 payload is never silently upgraded.
    if selected_contract is None:
        if isinstance(candidate, Mapping) and ("preview" in candidate or "content_format" in candidate):
            return _result(False, ["content_extension_not_enabled"])
        return _result(True, [], mode="base_contract_unchanged")
    if selected_contract != CONTRACT:
        return _result(False, ["invalid_content_policy"])

    if (not isinstance(schema_contracts, list) or CONTRACT not in schema_contracts
            or not isinstance(host.get("content_contracts"), list)
            or CONTRACT not in host["content_contracts"]
            or host.get("expanded_reading") is not True):
        return _result(False, ["content_contract_unavailable"])

    profiles = agent.get("profiles")
    if not isinstance(profiles, Mapping) or not profiles:
        return _result(False, ["invalid_content_policy"])
    for name, profile in profiles.items():
        if name not in DEPTHS or not isinstance(profile, Mapping):
            return _result(False, ["invalid_content_policy"])
        if not positive_int(profile.get("max_content_chars")):
            return _result(False, ["invalid_content_policy"])
        if not positive_int(profile.get("max_output_tokens")):
            return _result(False, ["invalid_content_policy"])
        if not positive_number(profile.get("llm_timeout_seconds")):
            return _result(False, ["invalid_content_policy"])
    if agent.get("default_depth") not in profiles:
        return _result(False, ["invalid_content_policy"])
    if not all(positive_int(v) for v in (agent.get("max_preview_chars"), host.get("max_content_chars"),
                                         host.get("max_preview_chars"), operator.get("max_response_bytes"))):
        return _result(False, ["invalid_content_policy"])

    a_formats, h_formats = agent.get("formats"), host.get("content_formats")
    if not all(isinstance(v, list) and v and all(isinstance(x, str) and x in FORMATS for x in v)
               for v in (a_formats, h_formats)):
        return _result(False, ["invalid_content_policy"])
    effective_formats = set(a_formats) & set(h_formats)
    if not effective_formats:
        return _result(False, ["unsupported_content_format"])

    if request is not None:
        if not isinstance(request, Mapping) or set(request) - {"depth", "request_id"}:
            return _result(False, ["invalid_content_policy"])
        if not isinstance(request.get("depth"), str) or request["depth"] not in DEPTHS or request["depth"] not in profiles:
            return _result(False, ["unsupported_depth"])
        request_id = request.get("request_id")
        if request_id is not None and (not isinstance(request_id, str) or not request_id.strip()):
            return _result(False, ["invalid_content_policy"])
        depth = request["depth"]
    else:
        depth = agent["default_depth"]
        request_id = None

    if execution is not None and not isinstance(execution, Mapping):
        return _result(False, ["completion_unknown"])
    completion = (execution or {}).get("completion_status", "unknown")
    if not isinstance(completion, str) or completion == "unknown" or completion not in {"complete", "incomplete", "failed"}:
        return _result(False, ["completion_unknown"])
    if completion != "complete":
        return _result(False, ["incomplete_generation"])

    admission = execution_admission(
        depth, profiles[depth], (execution or {}).get("content_execution_context"), operator,
        candidate_type=candidate.get("type") if isinstance(candidate, Mapping) else None,
        domain_effects_present=bool((execution or {}).get("domain_effects_present", False)))
    if not admission["accepted"]:
        return _result(False, [admission["code"]])

    execution_context = (execution or {}).get("content_execution_context", {})
    if execution_context.get("session_mode") == "active" and execution_context.get("execution_path") == "isolated_content":
        isolated_request_id = execution_context["request_id"]
        if request_id is not None and request_id != isolated_request_id:
            return _result(False, ["invalid_content_execution_context"])
        request_id = isolated_request_id

    max_content = min(profiles[depth]["max_content_chars"], host["max_content_chars"])
    max_preview = min(agent["max_preview_chars"], host["max_preview_chars"])
    for key in ("max_content_chars", "max_preview_chars"):
        if key in operator and not positive_int(operator[key]):
            return _result(False, ["invalid_content_policy"])
    if "max_content_chars" in operator:
        max_content = min(max_content, operator["max_content_chars"])
    if "max_preview_chars" in operator:
        max_preview = min(max_preview, operator["max_preview_chars"])

    if serialized_response is None:
        serialized_response = json.dumps(envelope, ensure_ascii=False, separators=(",", ":"),
                                         allow_nan=False).encode("utf-8")
    if not isinstance(serialized_response, bytes):
        return _result(False, ["invalid_content_policy"])
    codes: List[str] = []
    if len(serialized_response) > operator["max_response_bytes"]:
        codes.append("response_too_large")
    if candidate is None:
        return _result(not codes, codes, mode="valid_silence", effective_depth=depth)
    if not isinstance(candidate, Mapping) or not isinstance(candidate.get("content"), str):
        return _result(False, ["invalid_field"])
    content = candidate["content"]
    preview = candidate.get("preview")
    content_format = candidate.get("content_format", "plain_text")
    if content_format not in effective_formats:
        codes.append("unsupported_content_format")
    if len(content) > max_content:
        codes.append("content_too_large")
    if preview is not None and (not isinstance(preview, str) or not preview.strip()):
        codes.append("invalid_field")
    elif preview is not None and len(preview) > max_preview:
        codes.append("preview_too_large")
    if codes:
        return _result(False, codes, effective_depth=depth)

    return _result(
        True, [], mode=CONTRACT, effective_depth=depth,
        effective_max_content_chars=max_content, effective_max_preview_chars=max_preview,
        max_output_tokens=profiles[depth]["max_output_tokens"],
        llm_timeout_seconds=profiles[depth]["llm_timeout_seconds"],
        content_request_id=request_id, source_snapshot_id=execution_context.get("source_snapshot_id"),
        content_format=content_format, canonical_content=content, preview=preview,
        content_chars=len(content), serialized_response_bytes=len(serialized_response),
    )


# ---------------------------------------------------------------------------
# Framework adapters over the reference policy
# ---------------------------------------------------------------------------

def build_configuration(agent_content: Any, host_caps: Any, operator_limits: Optional[Mapping[str, Any]],
                        schema_content_contracts: Optional[List[str]]) -> Dict[str, Any]:
    """Assemble the policy configuration from the framework's typed objects
    (``InsightConfig.content``, ``HostInsightCapabilities``, the engine's
    ``content_limits`` and the schema descriptor)."""
    agent = agent_content.model_dump() if agent_content is not None else {}
    host = {
        "content_contracts": list(getattr(host_caps, "content_contracts", []) or []),
        "content_formats": list(getattr(host_caps, "content_formats", []) or []),
        "expanded_reading": bool(getattr(host_caps, "expanded_reading", False)),
        "max_content_chars": getattr(host_caps, "max_content_chars", None),
        "max_preview_chars": getattr(host_caps, "max_preview_chars", None),
    }
    return {
        "agent_content": agent,
        "host_content": host,
        "operator_limits": dict(operator_limits or {}),
        "schema_content_contracts": list(schema_content_contracts or []),
    }


def completion_status_from(finish_reason: Optional[str], error_category: Optional[str]) -> str:
    """Trusted adapter telemetry → completion status (§14.7). Only a normal stop
    is complete; a length stop or a truncated failure is incomplete; a failed
    call is failed; anything unreported is unknown (rejects)."""
    if error_category in ("truncated",):
        return "incomplete"
    if error_category is not None:
        return "failed"
    if finish_reason == "stop":
        return "complete"
    if finish_reason == "length":
        return "incomplete"
    return "unknown"
