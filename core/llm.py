import json
import os
import logging
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
        # "server", "malformed", "not_initialized", "unknown".
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

    async def generate_json(self, model: str, messages: list,
                            max_tokens: Optional[int] = None,
                            timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Generate a structured JSON response from the LLM.

        Resilient per INV-10: time-bounded (per-request ``timeout`` override or
        the client default), output-capped (``max_tokens`` override or default),
        and transparently retried with backoff on transient failures by the SDK.

        Never raises into the turn. Returns the parsed dict on success, or
        ``None`` on any failure. On failure, ``self.last_error_category`` records
        the failure class and a categorized error is logged.
        """
        if not self.client:
            logger.error("LLM Client not initialized (missing key or package).")
            self.last_error_category = "not_initialized"
            return None

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
            self.last_error_category = "timeout"
            logger.error(f"LLM call failed [category=timeout]: {e}")
            return None
        except RateLimitError as e:
            self.last_error_category = "rate_limit"
            logger.error(f"LLM call failed [category=rate_limit]: {e}")
            return None
        except AuthenticationError as e:
            self.last_error_category = "auth"
            logger.error(f"LLM call failed [category=auth]: {e}")
            return None
        except APIStatusError as e:
            # Non-2xx that isn't already a more specific subclass (e.g. 5xx that
            # outlived the retry budget). status_code aids operator triage.
            self.last_error_category = "server"
            status = getattr(e, "status_code", "?")
            logger.error(f"LLM call failed [category=server status={status}]: {e}")
            return None
        except APIError as e:
            # Catch-all for remaining SDK-level transport/protocol errors
            # (connection errors, etc.) that aren't APIStatusError.
            self.last_error_category = "server"
            logger.error(f"LLM call failed [category=server]: {e}")
            return None
        except Exception as e:
            # Defensive: anything not classified above must still not raise into
            # the turn (preserves the never-raise contract).
            self.last_error_category = "unknown"
            logger.error(f"LLM call failed [category=unknown]: {e}")
            return None

        # --- Response shape / parse validation (malformed category) ---
        try:
            if not response.choices:
                logger.warning("LLM call failed [category=malformed]: empty choices "
                               "(content may have been filtered)")
                self.last_error_category = "malformed"
                return None
            content = response.choices[0].message.content
            if content is None:
                logger.warning("LLM call failed [category=malformed]: null message content")
                self.last_error_category = "malformed"
                return None
            parsed = json.loads(content)
        except (json.JSONDecodeError, AttributeError, TypeError, IndexError) as e:
            logger.warning(f"LLM call failed [category=malformed]: {e}")
            self.last_error_category = "malformed"
            return None

        self.last_error_category = None
        return parsed
