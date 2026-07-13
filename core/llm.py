import json
import os
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

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
                 wire_max_tokens_param: str = DEFAULT_WIRE_MAX_TOKENS_PARAM):
        # WC-1: validate the wire knob FIRST — loud at load time, regardless of
        # key/SDK availability (the two documented values only).
        if wire_max_tokens_param not in WIRE_MAX_TOKENS_PARAMS:
            raise ValueError(
                f"wire_max_tokens_param must be one of {WIRE_MAX_TOKENS_PARAMS}, "
                f"got {wire_max_tokens_param!r}"
            )
        self.client = None
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self.wire_max_tokens_param = wire_max_tokens_param
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
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            timeout=timeout,
            max_retries=max_retries,
        )

    def _finish(self, parsed: Optional[Dict[str, Any]] = None,
                error_category: Optional[str] = None,
                usage: Optional[Dict[str, int]] = None,
                finish_reason: Optional[str] = None) -> "LLMResult":
        """Build the per-call result and write the deprecated mirror.

        OB-2 / INV-17: ``generate()`` assigns ``last_error_category`` exactly
        once per call, here, on the way out — both entry points keep the
        mirror live, but per-call attribution belongs to the returned object.
        """
        self.last_error_category = error_category
        return LLMResult(parsed=parsed, error_category=error_category,
                         usage=usage, finish_reason=finish_reason)

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
                            timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Generate a structured JSON response from the LLM.

        Thin delegate over :meth:`generate` (OB-2). The public contract is
        unchanged: never raises into the turn; returns the parsed dict on
        success, or ``None`` on any failure; ``self.last_error_category``
        records the failure class and a categorized error is logged. Callers
        needing per-call usage/attribution use :meth:`generate` instead.
        """
        result = await self.generate(model=model, messages=messages,
                                     max_tokens=max_tokens, timeout=timeout)
        return result.parsed

    async def generate(self, model: str, messages: list,
                       max_tokens: Optional[int] = None,
                       timeout: Optional[float] = None) -> "LLMResult":
        """Run one structured-JSON LLM call and return the per-call result.

        Resilient per INV-10: time-bounded (per-request ``timeout`` override or
        the client default), output-capped (``max_tokens`` override or default),
        and transparently retried with backoff on transient failures by the SDK.
        Never raises into the turn; every outcome — success, typed failure,
        truncated, malformed — comes back as an :class:`LLMResult` (INV-17).
        """
        if not self.client:
            logger.error("LLM Client not initialized (missing key or package).")
            return self._finish(error_category="not_initialized")

        effective_max_tokens = max_tokens if max_tokens is not None else self.max_tokens
        # Per-request timeout override; the SDK accepts ``timeout=`` on the call
        # and falls back to the client-level budget when omitted.
        call_kwargs: Dict[str, Any] = dict(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            timeout=timeout if timeout is not None else self.timeout,
        )
        # WC-1: token cap under the configured wire name (max_completion_tokens
        # by default; legacy max_tokens for old OpenAI-compatible proxies).
        call_kwargs[self.wire_max_tokens_param] = effective_max_tokens

        try:
            response = await self.client.chat.completions.create(**call_kwargs)
        except APITimeoutError as e:
            logger.error(f"LLM call failed [category=timeout]: {e}")
            return self._finish(error_category="timeout")
        except RateLimitError as e:
            logger.error(f"LLM call failed [category=rate_limit]: {e}")
            return self._finish(error_category="rate_limit")
        except AuthenticationError as e:
            logger.error(f"LLM call failed [category=auth]: {e}")
            return self._finish(error_category="auth")
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
                return self._finish(error_category="misconfig")
            logger.error(
                f"LLM call failed [category=server status={status if status is not None else '?'}]: {e}"
            )
            return self._finish(error_category="server")
        except APIError as e:
            # Catch-all for remaining SDK-level transport/protocol errors
            # (connection errors, etc.) that aren't APIStatusError.
            logger.error(f"LLM call failed [category=server]: {e}")
            return self._finish(error_category="server")
        except Exception as e:
            # Defensive: anything not classified above must still not raise into
            # the turn (preserves the never-raise contract).
            logger.error(f"LLM call failed [category=unknown]: {e}")
            return self._finish(error_category="unknown")

        # A response object arrived: usage is billable and reportable even when
        # the content below turns out to be truncated/malformed (OB-2).
        usage = self._extract_usage(response)

        # --- Response shape / parse validation (malformed category) ---
        try:
            if not response.choices:
                logger.warning("LLM call failed [category=malformed]: empty choices "
                               "(content may have been filtered)")
                return self._finish(error_category="malformed", usage=usage)
            choice = response.choices[0]
            finish_reason = getattr(choice, "finish_reason", None)
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
                                    finish_reason=finish_reason)
            content = choice.message.content
            if content is None:
                logger.warning("LLM call failed [category=malformed]: null message content")
                return self._finish(error_category="malformed", usage=usage,
                                    finish_reason=finish_reason)
            parsed = json.loads(content)
        except (json.JSONDecodeError, AttributeError, TypeError, IndexError) as e:
            logger.warning(f"LLM call failed [category=malformed]: {e}")
            return self._finish(error_category="malformed", usage=usage)

        return self._finish(parsed=parsed, usage=usage, finish_reason=finish_reason)
