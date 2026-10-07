from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.llm.client import GeminiClient, OpenAICompatClient, create_llm


class FakeResponse:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"candidates": [{"content": {"parts": [{"text": "{\"ok\": "}, {"text": "true}"}]}}]}


class FakeAsyncClient:
    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout
        self.post = AsyncMock(return_value=FakeResponse())

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None


def test_gemini_client_sends_json_request_and_reads_response() -> None:
    client = FakeAsyncClient(timeout=30)
    with patch("app.llm.client.httpx.AsyncClient", return_value=client):
        result = asyncio.run(GeminiClient("test-key", "test-model", 30).complete("system", "user", "code"))

    assert result == '{"ok": true}'
    args, kwargs = client.post.call_args
    assert args == (
        "https://generativelanguage.googleapis.com/v1beta/models/test-model:generateContent",
    )
    assert kwargs["headers"]["x-goog-api-key"] == "test-key"
    assert kwargs["json"]["systemInstruction"]["parts"][0]["text"] == "system"
    assert kwargs["json"]["contents"][0]["parts"][0]["text"] == "user"
    assert kwargs["json"]["generationConfig"]["responseMimeType"] == "application/json"


def test_auto_provider_selects_openai_before_gemini() -> None:
    settings = SimpleNamespace(
        llm_provider="auto",
        openai_api_key="openai-key",
        openai_model="openai-model",
        gemini_api_key="gemini-key",
        gemini_model="gemini-model",
        ollama_api_key="",
        ollama_model="gpt-oss:120b-cloud",
        groq_api_key="",
        anthropic_api_key="",
        llm_timeout=30,
    )
    with patch("app.llm.client.get_settings", return_value=settings):
        provider = create_llm()

    assert provider.name == "openai"


def test_explicit_gemini_provider_uses_gemini_key() -> None:
    settings = SimpleNamespace(
        llm_provider="gemini",
        openai_api_key="openai-key",
        openai_model="openai-model",
        gemini_api_key="gemini-key",
        gemini_model="gemini-model",
        groq_api_key="",
        anthropic_api_key="",
        llm_timeout=30,
    )
    with patch("app.llm.client.get_settings", return_value=settings):
        provider = create_llm()

    assert isinstance(provider, GeminiClient)
    assert provider.api_key == "gemini-key"
    assert provider.model == "gemini-model"


def test_explicit_ollama_provider_uses_cloud_compatible_endpoint() -> None:
    settings = SimpleNamespace(
        llm_provider="ollama",
        openai_api_key="",
        openai_model="openai-model",
        gemini_api_key="",
        gemini_model="gemini-model",
        ollama_api_key="ollama-key",
        ollama_model="gpt-oss:120b-cloud",
        groq_api_key="",
        anthropic_api_key="",
        llm_timeout=30,
    )
    with patch("app.llm.client.get_settings", return_value=settings):
        provider = create_llm()

    assert isinstance(provider, OpenAICompatClient)
    assert provider.name == "ollama"
    assert provider.base_url == "https://ollama.com/v1"
    assert provider.api_key == "ollama-key"
    assert provider.model == "gpt-oss:120b-cloud"
