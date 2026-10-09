import asyncio
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.contracts import DisabledProvider, LLMRequest, ProviderUnavailable
from app.main import create_app
from app.providers import OpenAIProvider, make_provider, strict_schema


def request():
    return LLMRequest(
        task="evaluation",
        instructions="private instructions",
        context="private answer",
        output_schema={},
    )


def completed():
    return httpx.Response(
        200,
        json={
            "status": "completed",
            "id": "test",
            "usage": {"input_tokens": 12, "output_tokens": 3},
            "output": [{"content": [{"type": "output_text", "text": '{"ok":true}'}]}],
        },
    )


@pytest.mark.parametrize("status,attempts", [(401, 1), (403, 1), (400, 1), (429, 2), (503, 2)])
def test_http_failures_bounded(status, attempts, caplog):
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(status, text="secret-provider-error")

    provider = OpenAIProvider(
        Settings(llm_api_key="test-secret", llm_model="test-model", _env_file=None),
        httpx.MockTransport(handler),
    )
    with caplog.at_level(logging.INFO), pytest.raises(ProviderUnavailable):
        asyncio.run(provider.generate_structured(request()))
    assert len(calls) == attempts
    assert provider.last_status == "unavailable"
    assert "test-secret" not in caplog.text
    assert "secret-provider-error" not in caplog.text
    assert "private answer" not in caplog.text


def test_retry_success_metadata(caplog):
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(429) if len(calls) == 1 else completed()

    provider = OpenAIProvider(
        Settings(llm_api_key="test-secret", llm_model="test-model", _env_file=None),
        httpx.MockTransport(handler),
    )
    assert provider.last_status == "unverified"
    with caplog.at_level(logging.INFO):
        assert asyncio.run(provider.generate_structured(request())).data == {"ok": True}
    event = json.loads([r.message for r in caplog.records if r.name == "war_room.ai"][0])
    assert event["attempts"] == 2
    assert event["input_tokens"] == 12
    assert event["model"] == "test-model"
    assert provider.last_status == "connected"


@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.ConnectError])
def test_transport_errors(error):
    calls = []

    def handler(req):
        calls.append(req)
        raise error("private transport details")

    provider = OpenAIProvider(
        Settings(llm_api_key="test-secret", llm_model="test-model", _env_file=None),
        httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderUnavailable, match="Provider request failed"):
        asyncio.run(provider.generate_structured(request()))
    assert len(calls) == 2


def test_disabled_and_status(settings):
    settings.llm_provider = "openai"
    settings.llm_api_key = Settings(llm_api_key="", _env_file=None).llm_api_key
    assert isinstance(make_provider(settings), DisabledProvider)
    with TestClient(create_app(settings)) as client:
        data = client.get("/api/v1/ai/status").json()
        assert data["status"] == "disabled"
        assert "key" not in json.dumps(data)


def test_strict_schema():
    source = {"type": "object", "properties": {"value": {"type": "string", "default": ""}}}
    result = strict_schema(source)
    assert result["required"] == ["value"]
    assert result["additionalProperties"] is False
    assert "default" not in result["properties"]["value"]
    assert "default" in source["properties"]["value"]


def test_live_status_and_m2_consent_no_secret(settings):
    from pydantic import SecretStr

    settings.llm_provider = "openai"
    settings.llm_model = "test-model"
    settings.llm_api_key = SecretStr("private-test-secret")
    with TestClient(create_app(settings)) as client:
        status = client.get("/api/v1/ai/status").json()
        assert status["status"] == "unverified"
        assert status["mode"] == "live"
        assert status["model"] == "test-model"
        assert "private-test-secret" not in client.get("/api/v1/capabilities").text
        assert client.post("/api/v1/documents/nonexistent/ai-analysis").status_code == 409
        client.app.state.llm.last_status = "unavailable"
        assert client.get("/api/v1/ai/status").json()["status"] == "unavailable"


def test_model_metadata_masks_misplaced_key():
    provider = OpenAIProvider(Settings(llm_model="sk-accidental", _env_file=None))
    assert provider.safe_model == "configured"
