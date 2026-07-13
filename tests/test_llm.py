"""
Tests for R-1 / INV-10 — LLM call-site resilience (core/llm.py).

INV-10: every external LLM call is time-bounded and fails with typed,
distinguishable outcomes (timeout vs rate-limit vs auth vs server vs malformed),
never an undifferentiated silent ``None``.

Contract preserved by these tests:
- ``generate_json`` NEVER raises into the turn.
- It still returns the parsed dict on success, or ``None`` on any failure.
- The failure *class* is surfaced via ``last_error_category`` and a logged
  ``[category=...]`` marker.
- ``timeout`` and ``max_tokens`` are actually passed to the underlying
  ``chat.completions.create`` call.

All fixtures are local to this file; the network is never touched — the
``AsyncOpenAI`` client's ``chat.completions.create`` is replaced with a mock.
"""

import asyncio
import json
import logging
from types import SimpleNamespace

import pytest

from xubb_agents.core.llm import (
    LLMClient,
    LLMResult,
    APITimeoutError,
    RateLimitError,
    AuthenticationError,
    APIStatusError,
    APIError,
)


# --------------------------------------------------------------------------- #
# Local helpers: lightweight typed-exception stand-ins.
#
# The real openai SDK exceptions require httpx Request/Response objects to
# construct. We only care that the wrapper's ``except`` blocks match by type
# (isinstance), so subclassing with a trivial constructor is sufficient and far
# less brittle than fabricating httpx objects.
# --------------------------------------------------------------------------- #
class FakeTimeout(APITimeoutError):
    def __init__(self, message="timed out"):
        Exception.__init__(self, message)


class FakeRateLimit(RateLimitError):
    def __init__(self, message="rate limited"):
        Exception.__init__(self, message)


class FakeAuth(AuthenticationError):
    def __init__(self, message="bad key"):
        Exception.__init__(self, message)


class FakeStatus(APIStatusError):
    def __init__(self, message="server error", status_code=503):
        Exception.__init__(self, message)
        self.status_code = status_code


class FakeAPIError(APIError):
    def __init__(self, message="connection blew up"):
        Exception.__init__(self, message)


# --------------------------------------------------------------------------- #
# Fake response objects for the success / malformed paths.
# --------------------------------------------------------------------------- #
class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content=None, choices=None):
        if choices is not None:
            self.choices = choices
        else:
            self.choices = [_Choice(content)]


class _FakeCompletions:
    """Stands in for ``client.chat.completions``; records call kwargs."""

    def __init__(self, *, result=None, raises=None):
        self._result = result
        self._raises = raises
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises
        return self._result


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


def _make_client(*, result=None, raises=None,
                 wire_max_tokens_param="max_completion_tokens"):
    """Build an LLMClient with its underlying create() mocked.

    We bypass real OpenAI construction by directly attaching a fake ``client``
    with the same ``chat.completions.create`` surface the wrapper uses.
    """
    client = LLMClient.__new__(LLMClient)
    # Mirror the defaults the real __init__ would set.
    client.timeout = 10.0
    client.max_retries = 2
    client.max_tokens = 1024
    client.wire_max_tokens_param = wire_max_tokens_param
    client.last_error_category = None

    completions = _FakeCompletions(result=result, raises=raises)

    class _FakeClient:
        pass

    fake = _FakeClient()
    fake.chat = _FakeChat(completions)
    client.client = fake
    return client, completions


MESSAGES = [{"role": "user", "content": "hi"}]


# --------------------------------------------------------------------------- #
# (a) Typed errors + timeout -> None, no raise, correct category logged.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc, expected_category",
    [
        (FakeTimeout(), "timeout"),
        (FakeRateLimit(), "rate_limit"),
        (FakeAuth(), "auth"),
        (FakeStatus(status_code=503), "server"),
        (FakeAPIError(), "server"),
        (ValueError("totally unexpected"), "unknown"),
        # OB-1 (INV-16): 4xx client errors are misconfiguration, not outages —
        # e.g. an unsupported parameter or an unknown model must not page the
        # "server spike" runbook.
        (FakeStatus(status_code=400), "misconfig"),
        (FakeStatus(status_code=404), "misconfig"),
        (FakeStatus(status_code=422), "misconfig"),
        # Missing/non-int status_code must fall to "server", never raise
        # (None < 500 would TypeError inside the handler).
        (FakeStatus(status_code=None), "server"),
    ],
)
async def test_typed_errors_return_none_and_log_category(exc, expected_category, caplog):
    client, _ = _make_client(raises=exc)

    with caplog.at_level(logging.ERROR, logger="AgentLLM"):
        result = await client.generate_json(model="gpt-4o-mini", messages=MESSAGES)

    assert result is None
    assert client.last_error_category == expected_category
    assert f"[category={expected_category}" in caplog.text


@pytest.mark.asyncio
async def test_server_category_includes_status_code(caplog):
    client, _ = _make_client(raises=FakeStatus(status_code=502))

    with caplog.at_level(logging.ERROR, logger="AgentLLM"):
        result = await client.generate_json(model="m", messages=MESSAGES)

    assert result is None
    assert client.last_error_category == "server"
    assert "status=502" in caplog.text


# --------------------------------------------------------------------------- #
# (b) Malformed / empty responses -> None, no raise, "malformed" category.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_empty_choices_is_malformed(caplog):
    client, _ = _make_client(result=_Resp(choices=[]))

    with caplog.at_level(logging.WARNING, logger="AgentLLM"):
        result = await client.generate_json(model="m", messages=MESSAGES)

    assert result is None
    assert client.last_error_category == "malformed"
    assert "[category=malformed]" in caplog.text


@pytest.mark.asyncio
async def test_null_content_is_malformed():
    client, _ = _make_client(result=_Resp(content=None))
    result = await client.generate_json(model="m", messages=MESSAGES)
    assert result is None
    assert client.last_error_category == "malformed"


@pytest.mark.asyncio
async def test_non_json_content_is_malformed():
    client, _ = _make_client(result=_Resp(content="this is not json"))
    result = await client.generate_json(model="m", messages=MESSAGES)
    assert result is None
    assert client.last_error_category == "malformed"


# --------------------------------------------------------------------------- #
# OB-1 (INV-16): length-stopped output -> "truncated", not "malformed".
# --------------------------------------------------------------------------- #
class _ChoiceWithFinish(_Choice):
    def __init__(self, content, finish_reason=None):
        super().__init__(content)
        self.finish_reason = finish_reason


@pytest.mark.asyncio
async def test_length_stopped_null_content_is_truncated(caplog):
    """Starved reasoning output: finish_reason=length with no content."""
    resp = _Resp(choices=[_ChoiceWithFinish(None, finish_reason="length")])
    client, _ = _make_client(result=resp)

    with caplog.at_level(logging.WARNING, logger="AgentLLM"):
        result = await client.generate_json(model="m", messages=MESSAGES)

    assert result is None
    assert client.last_error_category == "truncated"
    assert "[category=truncated]" in caplog.text


@pytest.mark.asyncio
async def test_length_stopped_partial_content_is_truncated():
    """Deliberate inertness deviation (spec §6.2): a length-stopped response
    whose partial content happens to parse is still not trustworthy."""
    resp = _Resp(choices=[_ChoiceWithFinish('{"ok": true}', finish_reason="length")])
    client, _ = _make_client(result=resp)

    result = await client.generate_json(model="m", messages=MESSAGES)

    assert result is None
    assert client.last_error_category == "truncated"


@pytest.mark.asyncio
async def test_normal_stop_is_not_truncated():
    resp = _Resp(choices=[_ChoiceWithFinish('{"ok": true}', finish_reason="stop")])
    client, _ = _make_client(result=resp)

    result = await client.generate_json(model="m", messages=MESSAGES)

    assert result == {"ok": True}
    assert client.last_error_category is None


# --------------------------------------------------------------------------- #
# Success path: returns parsed dict and clears the error category.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_success_returns_parsed_dict():
    payload = {"insight": "hello", "confidence": 0.8}
    client, _ = _make_client(result=_Resp(content=json.dumps(payload)))

    result = await client.generate_json(model="m", messages=MESSAGES)

    assert result == payload
    assert client.last_error_category is None


# --------------------------------------------------------------------------- #
# (c) timeout and max_tokens are actually forwarded to create().
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_defaults_passed_to_create():
    payload = {"ok": True}
    client, completions = _make_client(result=_Resp(content=json.dumps(payload)))

    await client.generate_json(model="gpt-4o-mini", messages=MESSAGES)

    assert len(completions.calls) == 1
    kwargs = completions.calls[0]
    assert kwargs["timeout"] == 10.0
    # WC-1: the token cap ships on the wire as max_completion_tokens (the
    # successor kwarg; accepted by non-reasoning models, required by reasoning
    # models). The Python parameter name stays max_tokens.
    assert kwargs["max_completion_tokens"] == 1024
    assert "max_tokens" not in kwargs
    assert kwargs["model"] == "gpt-4o-mini"
    assert kwargs["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_per_call_overrides_passed_to_create():
    payload = {"ok": True}
    client, completions = _make_client(result=_Resp(content=json.dumps(payload)))

    await client.generate_json(
        model="m", messages=MESSAGES, max_tokens=256, timeout=3.5
    )

    kwargs = completions.calls[0]
    assert kwargs["timeout"] == 3.5
    assert kwargs["max_completion_tokens"] == 256


# --------------------------------------------------------------------------- #
# WC-1 (SPEC_LLM_MODERN_MODELS): token-cap wire kwarg + legacy opt-out knob.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_wc1_legacy_wire_mode_sends_max_tokens():
    """Old OpenAI-compatible proxies can pin the legacy kwarg."""
    payload = {"ok": True}
    client, completions = _make_client(
        result=_Resp(content=json.dumps(payload)),
        wire_max_tokens_param="max_tokens",
    )

    await client.generate_json(model="m", messages=MESSAGES)

    kwargs = completions.calls[0]
    assert kwargs["max_tokens"] == 1024
    assert "max_completion_tokens" not in kwargs


def _ctor_env(monkeypatch):
    import xubb_agents.core.llm as llm_mod

    monkeypatch.setattr(llm_mod, "OPENAI_AVAILABLE", True)
    monkeypatch.setattr(llm_mod, "AsyncOpenAI", lambda **kw: object())


def test_wc1_constructor_rejects_unknown_wire_param(monkeypatch):
    """Loud at load time: an unknown wire-param value is a ValueError."""
    _ctor_env(monkeypatch)
    with pytest.raises(ValueError):
        LLMClient(api_key="sk-test", wire_max_tokens_param="max_output_tokens")


def test_wc1_constructor_accepts_both_wire_values(monkeypatch):
    _ctor_env(monkeypatch)
    for value in ("max_completion_tokens", "max_tokens"):
        client = LLMClient(api_key="sk-test", wire_max_tokens_param=value)
        assert client.wire_max_tokens_param == value


# --------------------------------------------------------------------------- #
# Uninitialized client -> None, "not_initialized" category, no raise.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_uninitialized_client_returns_none():
    client = LLMClient.__new__(LLMClient)
    client.client = None
    client.timeout = 10.0
    client.max_tokens = 1024
    client.last_error_category = None

    result = await client.generate_json(model="m", messages=MESSAGES)

    assert result is None
    assert client.last_error_category == "not_initialized"


# --------------------------------------------------------------------------- #
# Constructor wiring: timeout / max_retries / max_tokens are configurable.
# --------------------------------------------------------------------------- #
def test_constructor_configures_resilience_params(monkeypatch):
    captured = {}

    import xubb_agents.core.llm as llm_mod

    def fake_async_openai(**kwargs):
        captured.update(kwargs)

        class _C:
            pass

        return _C()

    monkeypatch.setattr(llm_mod, "OPENAI_AVAILABLE", True)
    monkeypatch.setattr(llm_mod, "AsyncOpenAI", fake_async_openai)

    client = LLMClient(api_key="sk-test", timeout=4.0, max_retries=5, max_tokens=512)

    assert client.timeout == 4.0
    assert client.max_retries == 5
    assert client.max_tokens == 512
    # Resilience budget propagated to the underlying AsyncOpenAI client.
    assert captured["timeout"] == 4.0
    assert captured["max_retries"] == 5


# --------------------------------------------------------------------------- #
# OB-2 (INV-17): per-call LLMResult path + usage telemetry.
# --------------------------------------------------------------------------- #

def _usage_obj(prompt=10, completion=20, reasoning=None, cached=None):
    """Fake SDK usage object; nested details only when values provided."""
    u = SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion)
    if reasoning is not None:
        u.completion_tokens_details = SimpleNamespace(reasoning_tokens=reasoning)
    if cached is not None:
        u.prompt_tokens_details = SimpleNamespace(cached_tokens=cached)
    return u


def _resp_with_usage(content, usage, finish_reason="stop"):
    resp = _Resp(choices=[_ChoiceWithFinish(content, finish_reason=finish_reason)])
    resp.usage = usage
    return resp


@pytest.mark.asyncio
async def test_generate_success_returns_llmresult_with_flattened_usage():
    payload = {"ok": True}
    usage = _usage_obj(prompt=11, completion=7, reasoning=3, cached=2)
    client, _ = _make_client(result=_resp_with_usage(json.dumps(payload), usage))

    result = await client.generate(model="m", messages=MESSAGES)

    assert isinstance(result, LLMResult)
    assert result.parsed == payload
    assert result.error_category is None
    assert result.finish_reason == "stop"
    assert result.usage == {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "reasoning_tokens": 3,
        "cached_tokens": 2,
    }


@pytest.mark.asyncio
async def test_generate_usage_omits_absent_detail_keys():
    usage = _usage_obj(prompt=5, completion=9)  # no nested details
    client, _ = _make_client(result=_resp_with_usage('{"a": 1}', usage))

    result = await client.generate(model="m", messages=MESSAGES)

    assert result.usage == {"prompt_tokens": 5, "completion_tokens": 9}


@pytest.mark.asyncio
async def test_generate_typed_failure_carries_category():
    client, _ = _make_client(raises=FakeRateLimit())

    result = await client.generate(model="m", messages=MESSAGES)

    assert result.parsed is None
    assert result.error_category == "rate_limit"
    assert result.usage is None


@pytest.mark.asyncio
async def test_generate_truncated_still_reports_usage():
    """Truncated calls are BILLED — usage must survive the failure."""
    usage = _usage_obj(prompt=8, completion=1024, reasoning=1000)
    client, _ = _make_client(result=_resp_with_usage(None, usage, finish_reason="length"))

    result = await client.generate(model="m", messages=MESSAGES)

    assert result.parsed is None
    assert result.error_category == "truncated"
    assert result.usage["reasoning_tokens"] == 1000


@pytest.mark.asyncio
async def test_generate_json_delegates_and_mirror_matches():
    """generate_json is a thin delegate; the deprecated mirror stays live for
    both entry points (single write site in generate())."""
    payload = {"ok": True}
    client, _ = _make_client(result=_Resp(content=json.dumps(payload)))

    assert await client.generate_json(model="m", messages=MESSAGES) == payload
    assert client.last_error_category is None

    client_fail, _ = _make_client(raises=FakeAuth())
    assert await client_fail.generate_json(model="m", messages=MESSAGES) is None
    assert client_fail.last_error_category == "auth"


# --------------------------------------------------------------------------- #
# OB-2 named concurrency tests (spec §6.3).
# --------------------------------------------------------------------------- #

class _GatedCompletions:
    """First call parks on an event then raises FakeTimeout; second call
    raises FakeRateLimit immediately. Deterministic interleaving harness."""

    def __init__(self):
        self.first_call_gate = asyncio.Event()
        self._calls = 0

    async def create(self, **kwargs):
        self._calls += 1
        if self._calls == 1:
            await self.first_call_gate.wait()
            raise FakeTimeout()
        raise FakeRateLimit()


def _make_gated_client():
    client = LLMClient.__new__(LLMClient)
    client.timeout = 10.0
    client.max_retries = 2
    client.max_tokens = 1024
    client.wire_max_tokens_param = "max_completion_tokens"
    client.last_error_category = None

    completions = _GatedCompletions()

    class _FakeClient:
        pass

    fake = _FakeClient()
    fake.chat = _FakeChat(completions)
    client.client = fake
    return client, completions


@pytest.mark.asyncio
async def test_ob2_baseline_mirror_race_reports_last_writer_only():
    """INV-17 baseline pin: the DEPRECATED shared-client mirror cannot
    attribute per-call failures. Call A fails with timeout AFTER call B failed
    with rate_limit; once both settle, the mirror holds only A's category —
    B's outcome is unrecoverable from shared state. (This documents why
    per-call attribution lives on LLMResult, next test.)"""
    client, completions = _make_gated_client()

    async def call_a():
        return await client.generate_json(model="m", messages=MESSAGES)

    async def call_b():
        result = await client.generate_json(model="m", messages=MESSAGES)
        completions.first_call_gate.set()  # release A only after B finished
        return result

    task_a = asyncio.create_task(call_a())
    await asyncio.sleep(0)  # let A reach the gate (first create() call)
    result_b = await call_b()
    result_a = await task_a

    assert result_a is None and result_b is None
    # Last writer (A, timeout) wins; B's rate_limit is gone from the mirror.
    assert client.last_error_category == "timeout"


@pytest.mark.asyncio
async def test_ob2_llmresult_attributes_categories_per_call():
    """INV-17: the same interleaving, via generate() — each caller gets ITS
    category on its own result object regardless of write order."""
    client, completions = _make_gated_client()

    async def call_a():
        return await client.generate(model="m", messages=MESSAGES)

    async def call_b():
        result = await client.generate(model="m", messages=MESSAGES)
        completions.first_call_gate.set()
        return result

    task_a = asyncio.create_task(call_a())
    await asyncio.sleep(0)
    result_b = await call_b()
    result_a = await task_a

    assert result_a.error_category == "timeout"
    assert result_b.error_category == "rate_limit"
