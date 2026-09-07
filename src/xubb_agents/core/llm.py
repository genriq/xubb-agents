import json
import os
import logging
from dataclasses import dataclass, replace as _dc_replace
from typing import Optional, Dict, Any, List

from .provider_schema import (
    STRUCTURED_OUTPUT_MODES, DEFAULT_STRUCTURED_OUTPUTS, SCHEMA_VERSION, FEATURE_JSON_SCHEMA,
    CapabilityCache, allow_schema_fallback, response_format_for,
)

# Try to import openai, but don't crash if not present (graceful degradation or mocking)
try:
    from openai import (
        AsyncOpenAI,
        APITimeoutError,
        RateLimitError,
        AuthenticationError,
        APIStatusError,
        APIError,
    )
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    # Define placeholder exception types so the typed-except blocks below remain
    # valid even when the SDK is absent (they simply never fire in that case).
    class APITimeoutError(Exception):  # type: ignore
        pass

    class RateLimitError(Exception):  # type: ignore
        pass

    class AuthenticationError(Exception):  # type: ignore
        pass

    class APIStatusError(Exception):  # type: ignore
        pass

    class APIError(Exception):  # type: ignore
        pass

logger = logging.getLogger("AgentLLM")

# Defaults tuned for a real-time conversational copilot (INV-10):
# - A turn must not hang the HUD, so the per-request wall-clock budget is small.
# - Retries are bounded and cheap; the SDK applies exponential backoff + jitter
#   automatically on the transient classes (429 / 5xx / connection / timeout).
# - max_tokens caps the structured-JSON reply so a runaway generation can't blow
#   the latency budget or the cost.
DEFAULT_TIMEOUT = 10.0      # seconds, per request
DEFAULT_MAX_RETRIES = 2     # bounded retries on transient failures
DEFAULT_MAX_TOKENS = 1024   # output cap for the JSON object

# WC-1 (SPEC_LLM_MODERN_MODELS): the token cap ships on the wire as
# ``max_completion_tokens`` — the successor kwarg, accepted by non-reasoning
# models and REQUIRED by reasoning models (which 400 on ``max_tokens``). The
# legacy value exists only for old OpenAI-compatible proxies that predate the
# new kwarg. The Python parameter name (``max_tokens``) does not change.
WIRE_MAX_TOKENS_PARAMS = ("max_completion_tokens", "max_tokens")
DEFAULT_WIRE_MAX_TOKENS_PARAM = "max_completion_tokens"

# RC-2 (SPEC_LLM_MODERN_MODELS / INV-15): wire kwargs the framework owns.
# A model_params passthrough entry colliding with any of these is rejected at
# config-load time, and the call-site merge is defensive regardless — an
# unvalidated dict can never overwrite the wire essentials. BOTH token-cap
# spellings are owned, independent of the WC-1 wire mode.
FRAMEWORK_OWNED_PARAMS = frozenset({
    "model", "messages", "response_format",
    "max_tokens", "max_completion_tokens",
    "timeout", "reasoning_effort",
})

# XUBB-ITC-1 §13.3 (G2): the adapter identity a fallback signature must match
# EXACTLY. The version is the installed SDK's major.minor; a different SDK is a
# different adapter for signature purposes.
ADAPTER_ID = "openai-chat-completions"
ENDPOINT_FAMILY = "chat.completions"


def _adapter_version() -> str:
    try:
        import openai as _openai  # type: ignore
        parts = str(getattr(_openai, "__version__", "0")).split(".")
        return ".".join(parts[:2])
    except Exception:  # pragma: no cover - SDK absent
        return "unknown"


ADAPTER_VERSION = _adapter_version()


@dataclass(frozen=True)
class LLMResult:
    """Per-call outcome of one LLM request (OB-2 / INV-17).

    Attribution-safe: everything about THIS call rides on the returned object,
    not on shared client state — agents run concurrently against one shared
    ``LLMClient`` (``asyncio.gather`` in the engine), so a shared attribute can
    only report the last writer. ``last_error_category`` remains as a
    deprecated best-effort mirror for that reason.

    ``usage`` holds plain ints (``prompt_tokens``, ``completion_tokens``, plus
    ``reasoning_tokens`` / ``cached_tokens`` when the API reports them). It is
    populated whenever a response object was received — including ``truncated``
    and ``malformed`` outcomes, which are billed even though they carry no
    usable content.
    """
    parsed: Optional[Dict[str, Any]] = None
    error_category: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    finish_reason: Optional[str] = None
    # G2 (§13.3): which transport the response came back on ("json_schema" |
    # "json_object"), whether a recognised downgrade happened on this call, and
    # the sanitized adapter failure record a fallback signature is matched
    # against (never message text).
    transport: Optional[str] = None
    downgraded: bool = False
    failure: Optional[Dict[str, Any]] = None
    # C1 (§14.7): trusted transport size of the message body in UTF-8 bytes, for
    # the content contract's byte ceiling (never the decoded character count).
    raw_bytes: Optional[int] = None


class LLMClient:
    """OpenAI / OpenAI-compatible async client wrapper.

    R-1 / INV-10: every external LLM call is time-bounded, retries transient
    failures with backoff, caps output tokens, and maps failures onto *typed,
    distinguishable* categories that are logged. The public contract is
    preserved: ``generate_json`` never raises into the turn and returns the
    parsed dict on success or ``None`` on any failure. The failure *class* is
    surfaced via the logged category and the ``last_error_category`` attribute
    so the B4 cooldown and operators can react differently from a "bad schema".
    """

    def __init__(self, api_key: Optional[str] = None,
                 timeout: float = DEFAULT_TIMEOUT,
                 max_retries: int = DEFAULT_MAX_RETRIES,
                 max_tokens: int = DEFAULT_MAX_TOKENS,
                 wire_max_tokens_param: str = DEFAULT_WIRE_MAX_TOKENS_PARAM,
                 base_url: Optional[str] = None,
                 structured_outputs: str = DEFAULT_STRUCTURED_OUTPUTS,
                 fallback_signatures: Optional[List[Dict[str, Any]]] = None):
        # WC-1: validate the wire knob FIRST — loud at load time, regardless of
        # key/SDK availability (the two documented values only).
        if wire_max_tokens_param not in WIRE_MAX_TOKENS_PARAMS:
            raise ValueError(
                f"wire_max_tokens_param must be one of {WIRE_MAX_TOKENS_PARAMS}, "
                f"got {wire_max_tokens_param!r}"
            )
        # G2 / §13.3: transport policy. "strict" never downgrades; "auto" may
        # downgrade ONCE per capability key on an exact enabled signature;
        # "json_object" never sends a schema. The shipped registry enables no
        # production signature; an operator supplies evidence-backed ones here.
        if structured_outputs not in STRUCTURED_OUTPUT_MODES:
            raise ValueError(
                f"structured_outputs must be one of {STRUCTURED_OUTPUT_MODES}, got {structured_outputs!r}")
        self.structured_outputs = structured_outputs
        self.fallback_registry: Dict[str, Any] = {"enabled_signatures": list(fallback_signatures or [])}
        self.capability_cache = CapabilityCache()
        self.client = None
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self.wire_max_tokens_param = wire_max_tokens_param
        # EN-1: OpenAI-compatible endpoint override (proxies, vLLM, Ollama).
        # None = the SDK default (api.openai.com / OPENAI_BASE_URL env).
        self.base_url = base_url
        # Category of the most recent failure (None when last call succeeded or
        # no call has been made). Values: "timeout", "rate_limit", "auth",
        # "server", "misconfig", "truncated", "malformed", "not_initialized",
        # "unknown". (OB-1 / INV-16: "misconfig" = 4xx client error such as an
        # unsupported parameter or unknown model — an operator problem, not an
        # outage; "truncated" = the model stopped on the token cap, so the
        # output is untrustworthy AND billed — raise the cap or lower effort.)
        self.last_error_category: Optional[str] = None

        if not OPENAI_AVAILABLE:
            logger.warning("OpenAI package not found. Agents requiring LLM will fail.")
            return

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning("No OpenAI API Key provided. LLM features disabled.")
            return

        # Bind the timeout/retry budget at the client level so the SDK's built-in
        # exponential backoff handles transient (429 / 5xx / connection / timeout)
        # failures for us.
        client_kwargs: Dict[str, Any] = dict(
            api_key=self.api_key,
            timeout=timeout,
            max_retries=max_retries,
        )
        if base_url is not None:
            client_kwargs["base_url"] = base_url
        self.client = AsyncOpenAI(**client_kwargs)

    def _finish(self, parsed: Optional[Dict[str, Any]] = None,
                error_category: Optional[str] = None,
                usage: Optional[Dict[str, int]] = None,
                finish_reason: Optional[str] = None,
                transport: Optional[str] = None,
                failure: Optional[Dict[str, Any]] = None) -> "LLMResult":
        """Build the per-call result and write the deprecated mirror.

        OB-2 / INV-17: ``generate()`` assigns ``last_error_category`` exactly
        once per call, here, on the way out — both entry points keep the
        mirror live, but per-call attribution belongs to the returned object.
        """
        self.last_error_category = error_category
        return LLMResult(parsed=parsed, error_category=error_category,
                         usage=usage, finish_reason=finish_reason,
                         transport=transport, failure=failure)

    @staticmethod
    def _extract_usage(response: Any) -> Optional[Dict[str, int]]:
        """Flatten SDK usage into plain ints (fake-safe: pure getattr).

        Nested details map: ``reasoning_tokens`` ←
        ``completion_tokens_details.reasoning_tokens``; ``cached_tokens`` ←
        ``prompt_tokens_details.cached_tokens``. Absent values → key omitted.
        """
        u = getattr(response, "usage", None)
        if u is None:
            return None
        out: Dict[str, int] = {}
        for key in ("prompt_tokens", "completion_tokens"):
            v = getattr(u, key, None)
            if isinstance(v, int):
                out[key] = v
        details = getattr(u, "completion_tokens_details", None)
        v = getattr(details, "reasoning_tokens", None)
        if isinstance(v, int):
            out["reasoning_tokens"] = v
        details = getattr(u, "prompt_tokens_details", None)
        v = getattr(details, "cached_tokens", None)
        if isinstance(v, int):
            out["cached_tokens"] = v
        return out or None

    async def generate_json(self, model: str, messages: list,
                            max_tokens: Optional[int] = None,
                            timeout: Optional[float] = None,
                            reasoning_effort: Optional[str] = None,
                            extra_params: Optional[Dict[str, Any]] = None
                            ) -> Optional[Dict[str, Any]]:
        """Generate a structured JSON response from the LLM.

        Thin delegate over :meth:`generate` (OB-2). The public contract is
        unchanged: never raises into the turn; returns the parsed dict on
        success, or ``None`` on any failure; ``self.last_error_category``
        records the failure class and a categorized error is logged. Callers
        needing per-call usage/attribution use :meth:`generate` instead.
        """
        result = await self.generate(model=model, messages=messages,
                                     max_tokens=max_tokens, timeout=timeout,
                                     reasoning_effort=reasoning_effort,
                                     extra_params=extra_params)
        return result.parsed

    async def generate(self, model: str, messages: list,
                       max_tokens: Optional[int] = None,
                       timeout: Optional[float] = None,
                       reasoning_effort: Optional[str] = None,
                       extra_params: Optional[Dict[str, Any]] = None,
                       response_schema: Optional[Dict[str, Any]] = None,
                       schema_version: str = SCHEMA_VERSION,
                       schema_lint_passed: bool = True,
                       ) -> "LLMResult":
        """Run one structured-JSON LLM call and return the per-call result.

        Resilient per INV-10: time-bounded (per-request ``timeout`` override or
        the client default), output-capped (``max_tokens`` override or default),
        and transparently retried with backoff on transient failures by the SDK.
        Never raises into the turn; every outcome — success, typed failure,
        truncated, malformed — comes back as an :class:`LLMResult` (INV-17).

        G2 (§13.3): with ``response_schema`` the transport follows the client's
        ``structured_outputs`` policy — ``json_schema`` (strict) unless the mode
        is ``json_object`` or the capability cache already recorded a downgrade
        for this endpoint/model/adapter/schema-version key. Under ``auto`` a
        4xx that the adapter classifies as an unsupported-capability failure
        AND that exactly matches an enabled, evidence-backed signature triggers
        ONE recorded downgrade and one JSON-object retry with the same prompt.
        Anything else fails closed. Local validation is untouched either way.
        """
        if not self.client:
            logger.error("LLM Client not initialized (missing key or package).")
            return self._finish(error_category="not_initialized")

        transport = "json_object"
        key = None
        if response_schema is not None and self.structured_outputs != "json_object":
            key = CapabilityCache.key(self.base_url, model, ADAPTER_ID, ADAPTER_VERSION, schema_version)
            if not self.capability_cache.is_downgraded(key):
                transport = "json_schema"

        result = await self._call_once(model, messages, max_tokens, timeout, reasoning_effort,
                                       extra_params, transport, response_schema)
        if (transport == "json_schema" and result.failure is not None and key is not None
                and self.structured_outputs == "auto"):
            attempted = self.capability_cache.attempted.get(key, 0) > 0
            if allow_schema_fallback(result.failure, self.fallback_registry, mode="auto",
                                     schema_lint_passed=schema_lint_passed, fallback_attempted=attempted):
                self.capability_cache.record_attempt(key)
                self.capability_cache.record_downgrade(key, result.failure)
                logger.warning(
                    "Structured outputs unsupported [adapter=%s/%s status=%s code=%s param=%s evidence=%s]; "
                    "recorded downgrade to json_object for model=%s (once per capability key).",
                    ADAPTER_ID, ADAPTER_VERSION, result.failure.get("http_status"),
                    result.failure.get("code"), result.failure.get("param"),
                    result.failure.get("evidence_id"), model)
                retry = await self._call_once(model, messages, max_tokens, timeout, reasoning_effort,
                                              extra_params, "json_object", None)
                return _dc_replace(retry, downgraded=True)
        return result

    async def _call_once(self, model: str, messages: list, max_tokens: Optional[int],
                         timeout: Optional[float], reasoning_effort: Optional[str],
                         extra_params: Optional[Dict[str, Any]], transport: str,
                         response_schema: Optional[Dict[str, Any]]) -> "LLMResult":
        """One request on one transport; every outcome as an LLMResult."""
        effective_max_tokens = max_tokens if max_tokens is not None else self.max_tokens
        # RC-2 / INV-15: passthrough params go in FIRST so the framework-owned
        # keys below always win — an unvalidated dict can never overwrite the
        # wire essentials (defensive even though config load rejects collisions).
        call_kwargs: Dict[str, Any] = dict(extra_params) if extra_params else {}
        # Per-request timeout override; the SDK accepts ``timeout=`` on the call
        # and falls back to the client-level budget when omitted.
        call_kwargs.update(
            model=model,
            messages=messages,
            response_format=(response_format_for(response_schema) if transport == "json_schema"
                             else {"type": "json_object"}),
            timeout=timeout if timeout is not None else self.timeout,
        )
        # WC-1: token cap under the configured wire name (max_completion_tokens
        # by default; legacy max_tokens for old OpenAI-compatible proxies).
        call_kwargs[self.wire_max_tokens_param] = effective_max_tokens
        # WC-1 corollary: the passthrough must not smuggle the OTHER token-cap
        # spelling around the configured wire name.
        for spelling in WIRE_MAX_TOKENS_PARAMS:
            if spelling != self.wire_max_tokens_param:
                call_kwargs.pop(spelling, None)
        # RC-1 / INV-15: sent ONLY when the operator configured it — the
        # framework never injects, and omission leaves the model's default.
        if reasoning_effort is not None:
            call_kwargs["reasoning_effort"] = reasoning_effort

        try:
            response = await self.client.chat.completions.create(**call_kwargs)
        except APITimeoutError as e:
            logger.error(f"LLM call failed [category=timeout]: {e}")
            return self._finish(error_category="timeout", transport=transport)
        except RateLimitError as e:
            logger.error(f"LLM call failed [category=rate_limit]: {e}")
            return self._finish(error_category="rate_limit", transport=transport,
                                failure=self._failure_record(e, 429, transport))
        except AuthenticationError as e:
            logger.error(f"LLM call failed [category=auth]: {e}")
            return self._finish(error_category="auth", transport=transport,
                                failure=self._failure_record(e, 401, transport))
        except APIStatusError as e:
            # Non-2xx that isn't already a more specific subclass (401/429 raise
            # their own subclasses and never reach here). OB-1 / INV-16: a 4xx
            # is a client/config problem (unsupported parameter, unknown model,
            # bad request shape) — distinguishable from a 5xx outage so the
            # operator runbooks diverge. Missing/non-int status falls to
            # "server" (never compare None < 500 inside the handler).
            status = getattr(e, "status_code", None)
            if isinstance(status, int) and status < 500:
                logger.error(f"LLM call failed [category=misconfig status={status}]: {e}")
                return self._finish(error_category="misconfig", transport=transport,
                                    failure=self._failure_record(e, status, transport))
            logger.error(
                f"LLM call failed [category=server status={status if status is not None else '?'}]: {e}"
            )
            return self._finish(error_category="server", transport=transport)
        except APIError as e:
            # Catch-all for remaining SDK-level transport/protocol errors
            # (connection errors, etc.) that aren't APIStatusError.
            logger.error(f"LLM call failed [category=server]: {e}")
            return self._finish(error_category="server", transport=transport)
        except Exception as e:
            # Defensive: anything not classified above must still not raise into
            # the turn (preserves the never-raise contract).
            logger.error(f"LLM call failed [category=unknown]: {e}")
            return self._finish(error_category="unknown", transport=transport)

        # A response object arrived: usage is billable and reportable even when
        # the content below turns out to be truncated/malformed (OB-2).
        usage = self._extract_usage(response)

        # --- Response shape / parse validation (malformed category) ---
        try:
            if not response.choices:
                logger.warning("LLM call failed [category=malformed]: empty choices "
                               "(content may have been filtered)")
                return self._finish(error_category="malformed", usage=usage, transport=transport)
            choice = response.choices[0]
            finish_reason = getattr(choice, "finish_reason", None)
            # G2 / §13.3: a structured-output REFUSAL is its own outcome — billed,
            # not malformed, and never evidence that the schema is unsupported.
            if getattr(getattr(choice, "message", None), "refusal", None):
                logger.warning("LLM call failed [category=refusal]: model refused the structured request")
                return self._finish(error_category="refusal", usage=usage,
                                    finish_reason=finish_reason, transport=transport)
            # OB-1 / INV-16: length-stopped output is checked BEFORE the
            # null-content/parse branches — starved reasoning output arrives as
            # finish_reason="length" with null/partial content and must not be
            # misdiagnosed as "malformed" (you paid for tokens; the cap ate the
            # answer). A partial body that happens to parse is still rejected:
            # a truncated JSON object is not a trustworthy whisper.
            if finish_reason == "length":
                logger.warning(
                    "LLM call failed [category=truncated]: finish_reason=length "
                    f"(output hit the token cap; configured cap={effective_max_tokens})"
                )
                return self._finish(error_category="truncated", usage=usage,
                                    finish_reason=finish_reason, transport=transport)
            content = choice.message.content
            if content is None:
                logger.warning("LLM call failed [category=malformed]: null message content")
                return self._finish(error_category="malformed", usage=usage,
                                    finish_reason=finish_reason, transport=transport)
            parsed = json.loads(content)
        except (json.JSONDecodeError, AttributeError, TypeError, IndexError) as e:
            logger.warning(f"LLM call failed [category=malformed]: {e}")
            return self._finish(error_category="malformed", usage=usage, transport=transport)

        result = self._finish(parsed=parsed, usage=usage, finish_reason=finish_reason, transport=transport)
        return _dc_replace(result, raw_bytes=len(content.encode("utf-8")))

    @staticmethod
    def _failure_record(exc: Any, status: Optional[int], transport: str) -> Dict[str, Any]:
        """The sanitized, adapter-classified failure a fallback signature is
        matched against (§13.3). Structured fields only — never message text.
        ``unsupported_capability`` is claimed ONLY for a 400 on a json_schema
        request whose rejected parameter is under ``response_format``."""
        code = getattr(exc, "code", None)
        param = getattr(exc, "param", None)
        unsupported = (transport == "json_schema" and status == 400
                       and isinstance(param, str) and param.startswith("response_format"))
        return {
            "origin": "trusted_adapter",
            "adapter_id": ADAPTER_ID,
            "adapter_version": ADAPTER_VERSION,
            "endpoint_family": ENDPOINT_FAMILY,
            "http_status": status,
            "code": code if isinstance(code, str) else None,
            "param": param if isinstance(param, str) else None,
            "feature": FEATURE_JSON_SCHEMA if transport == "json_schema" else None,
            "category": "unsupported_capability" if unsupported else "misconfig",
        }
