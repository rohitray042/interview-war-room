import asyncio
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.contracts import DisabledProvider, LLMRequest, ProviderUnavailable
from app.gemini_provider import GeminiProvider, gemini_schema
from app.main import create_app
from app.providers import OpenAIProvider, make_provider


def provider(handler):
    settings = Settings(
        llm_provider="gemini",
        gemini_model="gemini-fixture",
        gemini_api_key="private-gemini-secret",
        _env_file=None,
    )
    result = make_provider(settings)
    result.transport = httpx.MockTransport(handler)
    return result


def request():
    return LLMRequest(
        task="evaluation",
        instructions="private instructions",
        context="private answer",
        output_schema={"type": "object"},
    )


def response(data):
    return httpx.Response(
        200,
        json={
            "candidates": [
                {"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(data)}]}}
            ],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
        },
    )


def test_gemini_structured_request_and_safe_logs(caplog):
    def handler(req):
        assert "private-gemini-secret" not in str(req.url)
        assert req.headers["x-goog-api-key"] == "private-gemini-secret"
        payload = json.loads(req.content)
        assert payload["generationConfig"]["responseMimeType"] == "application/json"
        assert payload["systemInstruction"]["parts"][0]["text"] == "private instructions"
        return response({"valid": True})

    p = provider(handler)
    with caplog.at_level(logging.INFO):
        assert asyncio.run(p.generate_structured(request())).data == {"valid": True}
    assert p.last_status == "connected"
    assert all(
        value not in caplog.text
        for value in ["private-gemini-secret", "private answer", "private instructions"]
    )


@pytest.mark.parametrize(
    "status,count", [(400, 1), (401, 1), (403, 1), (404, 1), (429, 2), (503, 2)]
)
def test_gemini_http_errors(status, count):
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(status, text="private-provider-body")

    p = provider(handler)
    with pytest.raises(ProviderUnavailable) as error:
        asyncio.run(p.generate_structured(request()))
    assert len(calls) == count
    assert "private-provider-body" not in str(error.value)
    assert p.last_status == "unavailable"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"candidates": []},
        {"candidates": [{"finishReason": "MAX_TOKENS"}]},
        {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "invalid"}]}}]},
        {"promptFeedback": {"blockReason": "SAFETY"}},
    ],
)
def test_gemini_invalid_response(body):
    p = provider(lambda _: httpx.Response(200, json=body))
    with pytest.raises(ValueError):
        asyncio.run(p.generate_structured(request()))


@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.ConnectError])
def test_gemini_network_errors(error):
    calls = []

    def handler(req):
        calls.append(req)
        raise error("private details")

    with pytest.raises(ProviderUnavailable):
        asyncio.run(provider(handler).generate_structured(request()))
    assert len(calls) == 2


def test_switching_and_no_cross_provider_fallback(monkeypatch):
    for name in ("LLM_PROVIDER", "WAR_ROOM_LLM_PROVIDER", "GEMINI_API_KEY", "GEMINI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    assert isinstance(make_provider(Settings(_env_file=None)), DisabledProvider)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-fixture")
    assert isinstance(make_provider(Settings(_env_file=None)), GeminiProvider)
    s = Settings(
        llm_provider="openai",
        openai_model="openai-fixture",
        openai_api_key="openai-test",
        _env_file=None,
    )
    assert isinstance(make_provider(s), OpenAIProvider)
    assert isinstance(
        make_provider(Settings(llm_provider="disabled", _env_file=None)), DisabledProvider
    )


def test_gemini_status_never_exposes_keys(settings):
    from pydantic import SecretStr

    settings.llm_provider = "gemini"
    settings.gemini_model = "gemini-fixture"
    settings.gemini_api_key = SecretStr("private-gemini-secret")
    with TestClient(create_app(settings)) as c:
        data = c.get("/api/v1/ai/status").json()
        assert data["provider"] == "gemini" and data["status"] == "unverified"
        assert "private-gemini-secret" not in c.get("/api/v1/capabilities").text


def test_gemini_mock_http_m3_m4_followups_and_m5(settings):
    from test_interviews import FakeInterview, act, evaluate, start, submit
    from test_questions import FakeQuestions, prepare

    async def handler(req):
        payload = json.loads(req.content)
        schema = payload["generationConfig"]["responseSchema"]
        task = "question_generation" if "questions" in schema["properties"] else "evaluation"
        llm_request = LLMRequest(
            task=task,
            instructions=payload["systemInstruction"]["parts"][0]["text"],
            context=payload["contents"][0]["parts"][0]["text"],
            output_schema=schema,
        )
        fake = FakeQuestions() if task == "question_generation" else FakeInterview("follow")
        result = await fake.generate_structured(llm_request)
        return response(result.data)

    p = provider(handler)
    with TestClient(create_app(settings, question_provider=p, interview_provider=p)) as c:
        target = prepare(c)
        result = c.post(
            "/api/v1/questions/generate",
            json={
                "target_id": target,
                "category": "Kafka",
                "number_of_questions": 1,
            },
        )
        assert result.status_code == 200
        state = start(c, target_id=target, source="personalized")
        for depth in range(3):
            assert state["current_turn"]["follow_up_depth"] == depth
            state = evaluate(c, submit(c, state))
            assert state["current_turn"]["evaluation_state"] == "succeeded"
            state = act(c, state, "next" if depth < 2 else "finish")
        assert state["status"] == "completed"
        learning = c.get("/api/v1/weaknesses").json()
        assert any(item["occurrence_count"] == 3 for item in learning["items"])


def test_native_schema_conversion_preserves_labels_and_original_validation():
    from app.interview_evaluation import evaluation_schema
    from app.interview_schemas import InterviewEvaluation

    original = evaluation_schema(
        {
            "rubric": {"weights": {"correctness": 100}},
            "content": {"expected_topics": ["Credit usage"]},
        }
    )
    before = json.dumps(original)
    converted = gemini_schema(original)
    assert "$ref" not in json.dumps(converted)
    assert "$defs" not in converted
    assert converted["properties"]["dimensions"]["items"]["properties"]["dimension"]["enum"] == [
        "correctness"
    ]
    assert converted["properties"]["follow_up_topic"] == {
        "type": "string",
        "enum": ["Credit usage"],
        "nullable": True,
    }
    assert json.dumps(original) == before
    with pytest.raises(ValueError):
        InterviewEvaluation.model_validate(
            {"dimensions": [], "topics": [], "follow_up_topic": None}
        )


def test_native_schema_preserves_property_names_and_rejects_cycles():
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "maxLength": 10},
            "required": {"type": "boolean"},
        },
        "required": ["title", "required"],
        "additionalProperties": False,
    }
    result = gemini_schema(schema)
    assert set(result["properties"]) == {"title", "required"}
    assert "maxLength" not in result["properties"]["title"]
    with pytest.raises(ValueError):
        gemini_schema({"$defs": {"Loop": {"$ref": "#/$defs/Loop"}}, "$ref": "#/$defs/Loop"})
