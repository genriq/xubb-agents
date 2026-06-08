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

import json
import logging

import pytest

from xubb_agents.core.llm import (
    LLMClient,
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


def _make_client(*, result=None, raises=None):
    """Build an LLMClient with its underlying create() mocked.

    We bypass real OpenAI construction by directly attaching a fake ``client``
    with the same ``chat.completions.create`` surface the wrapper uses.
    """
    client = LLMClient.__new__(LLMClient)
    # Mirror the defaults the real __init__ would set.
    client.timeout = 10.0
    client.max_retries = 2
    client.max_tokens = 1024
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
    assert kwargs["max_tokens"] == 1024
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
    assert kwargs["max_tokens"] == 256


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
