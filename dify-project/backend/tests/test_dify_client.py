"""Tests for Dify's HTTP contract and classified provider errors."""

import httpx
import pytest

from app.agents.dify_client import (
    DifyAuthenticationError,
    DifyClient,
    DifyConfigurationError,
    DifyConnectionError,
    DifyForbiddenError,
    DifyProviderError,
    DifyRequestError,
    DifyResponseError,
    DifyTimeoutError,
)
from app.core.config import Settings

INTERACTION_CONTEXT = '{"mode":"private_reply","channel":"private"}'


def test_dify_client_sends_blocking_request_and_parses_answer(monkeypatch) -> None:
    request_data = {}

    def fake_post(url, *, headers, json, timeout):
        request_data.update(
            {"url": url, "headers": headers, "json": json, "timeout": timeout}
        )
        return httpx.Response(200, json={"answer": "我当时在仓库。"})

    monkeypatch.setattr("app.agents.dify_client.httpx.post", fake_post)
    client = DifyClient("https://dify.example/v1/", "private-test-key", 12.5)

    answer = client.chat(
        '{"character":"safe"}',
        INTERACTION_CONTEXT,
        "你在哪里？",
        "game-1-character-2",
    )

    assert answer == "我当时在仓库。"
    assert request_data == {
        "url": "https://dify.example/v1/chat-messages",
        "headers": {"Authorization": "Bearer private-test-key"},
        "json": {
            "inputs": {
                "character_context": '{"character":"safe"}',
                "interaction_context": INTERACTION_CONTEXT,
            },
            "query": "你在哪里？",
            "response_mode": "blocking",
            "conversation_id": "",
            "user": "game-1-character-2",
        },
        "timeout": 12.5,
    }


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (401, DifyAuthenticationError),
        (403, DifyForbiddenError),
        (422, DifyRequestError),
        (503, DifyProviderError),
    ],
)
def test_dify_http_errors_are_classified(
    monkeypatch, status_code: int, error_type: type[Exception]
) -> None:
    monkeypatch.setattr(
        "app.agents.dify_client.httpx.post",
        lambda *_args, **_kwargs: httpx.Response(status_code),
    )
    client = DifyClient("https://dify.example/v1", "test-key")

    with pytest.raises(error_type):
        client.chat("{}", INTERACTION_CONTEXT, "query", "game-1-character-2")


def test_dify_malformed_and_empty_responses_are_rejected(monkeypatch) -> None:
    client = DifyClient("https://dify.example/v1", "test-key")
    monkeypatch.setattr(
        "app.agents.dify_client.httpx.post",
        lambda *_args, **_kwargs: httpx.Response(200, text="not json"),
    )
    with pytest.raises(DifyResponseError, match="malformed JSON"):
        client.chat("{}", INTERACTION_CONTEXT, "query", "user")

    monkeypatch.setattr(
        "app.agents.dify_client.httpx.post",
        lambda *_args, **_kwargs: httpx.Response(200, json={"answer": "  "}),
    )
    with pytest.raises(DifyResponseError, match="did not contain an answer"):
        client.chat("{}", INTERACTION_CONTEXT, "query", "user")


def test_dify_timeout_and_connection_failures_are_classified(monkeypatch) -> None:
    client = DifyClient("https://dify.example/v1", "test-key")
    monkeypatch.setattr(
        "app.agents.dify_client.httpx.post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(httpx.ReadTimeout("slow")),
    )
    with pytest.raises(DifyTimeoutError):
        client.chat("{}", INTERACTION_CONTEXT, "query", "user")

    monkeypatch.setattr(
        "app.agents.dify_client.httpx.post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(httpx.ConnectError("offline")),
    )
    with pytest.raises(DifyConnectionError):
        client.chat("{}", INTERACTION_CONTEXT, "query", "user")

    monkeypatch.setattr(
        "app.agents.dify_client.httpx.post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("bad proxy")),
    )
    with pytest.raises(DifyConnectionError, match="check proxy settings"):
        client.chat("{}", INTERACTION_CONTEXT, "query", "user")


def test_dify_requires_url_and_key_without_requesting_network(monkeypatch) -> None:
    called = False

    def fake_post(*_args, **_kwargs):
        nonlocal called
        called = True
        return httpx.Response(200, json={"answer": "reply"})

    monkeypatch.setattr("app.agents.dify_client.httpx.post", fake_post)
    with pytest.raises(DifyConfigurationError):
        DifyClient("", "").chat("{}", INTERACTION_CONTEXT, "query", "user")
    assert called is False


def test_character_api_key_accepts_new_name_and_legacy_name(monkeypatch) -> None:
    monkeypatch.delenv("DIFY_CHARACTER_API_KEY", raising=False)
    monkeypatch.delenv("DIFY_API_KEY", raising=False)
    monkeypatch.setenv("DIFY_API_URL", "https://dify.example/v1")
    monkeypatch.setenv("DIFY_API_KEY", "legacy-key")
    legacy_settings = Settings(_env_file=None)
    assert legacy_settings.dify_character_api_key == "legacy-key"

    monkeypatch.setenv("DIFY_CHARACTER_API_KEY", "character-key")
    new_settings = Settings(_env_file=None)
    assert new_settings.dify_character_api_key == "character-key"
    assert new_settings.dify_character_configured is True
