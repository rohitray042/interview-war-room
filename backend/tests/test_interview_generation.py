import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlmodel import Session, select
from test_interviews import FakeInterview, act, evaluate, submit
from test_questions import FakeQuestions, prepare

from app.contracts import ProviderUnavailable
from app.main import create_app
from app.models import BankQuestion, InterviewSession, InterviewTurn


class FreshProvider(FakeQuestions):
    def __init__(self, failure=None):
        super().__init__()
        self.calls, self.failure = 0, failure

    async def generate_structured(self, request):
        self.calls += 1
        if self.failure == "unavailable":
            raise ProviderUnavailable()
        if self.failure == "timeout":
            raise TimeoutError()
        result = await super().generate_structured(request)
        rows = result.data["questions"]
        if self.failure == "count":
            rows.pop()
        elif self.failure == "duplicate":
            rows[1] = rows[0]
        elif self.failure == "category":
            rows[0]["category"] = "Wrong category"
        elif self.failure == "difficulty":
            rows[0]["difficulty"] = "hard"
        elif self.failure == "type":
            rows[0]["question_type"] = "behavioral"
        elif self.failure == "context":
            rows[0]["context_id"] = "unknown"
        elif self.failure == "experience":
            rows[0]["question_text"] = "Explain your previous Kafka project at an employer."
        elif self.failure == "schema":
            result.data["extra_score"] = 100
        return result


def empty_bank(app):
    with Session(app.state.engine) as db:
        db.exec(delete(BankQuestion))
        db.commit()


def test_fresh_questions_with_empty_bank_general_practice_and_retries(settings):
    provider = FreshProvider()
    with TestClient(create_app(settings, provider, FakeInterview("follow"))) as client:
        empty_bank(client.app)
        payload = {
            "request_id": str(uuid4()),
            "source": "ai_generated",
            "category": "Snowflake",
            "difficulty": "easy",
            "question_type": "coding",
            "number_of_questions": 2,
        }
        assert client.post("/api/v1/interviews/preview", json=payload).json()["available"] == 20
        assert provider.calls == 0
        created = client.post("/api/v1/interviews", json=payload)
        assert created.status_code == 200, created.text
        state = created.json()
        assert client.post("/api/v1/interviews", json=payload).json()["id"] == state["id"]
        assert provider.calls == 1
        with Session(client.app.state.engine) as db:
            assert db.exec(select(BankQuestion)).all() == []
            turns = db.exec(select(InterviewTurn)).all()
            assert len(turns) == 2
            assert all(t.snapshot["content"]["difficulty"] == "easy" for t in turns)
            assert all(t.snapshot["content"]["question_type"] == "coding" for t in turns)
            assert all(t.snapshot["context"] == {} for t in turns)
        state = act(client, state, "start")
        first = state["current_turn"]["question_text"]
        for _ in range(6):
            state = evaluate(client, submit(client, state))
            state = act(client, state, "finish" if state["next_action"] == "finish" else "next")
        assert state["status"] == "completed"
        assert client.get("/api/v1/interviews/stats").json()["answers"] == 6
        assert provider.context["contexts"][0]["evidence"] == {}
        assert provider.calls == 1
        identity = state["id"]
    with TestClient(create_app(settings)) as client:
        persisted = client.get(f"/api/v1/interviews/{identity}/summary")
        assert persisted.status_code == 200
        assert first in persisted.text


@pytest.mark.parametrize(
    "failure",
    [
        "unavailable",
        "timeout",
        "count",
        "duplicate",
        "category",
        "difficulty",
        "type",
        "context",
        "experience",
        "schema",
    ],
)
def test_bad_or_unavailable_generation_never_creates_partial_or_curated_session(settings, failure):
    with TestClient(create_app(settings, FreshProvider(failure))) as client:
        response = client.post(
            "/api/v1/interviews",
            json={
                "request_id": str(uuid4()),
                "source": "ai_generated",
                "category": "Snowflake",
                "difficulty": "easy",
                "question_type": "coding",
                "number_of_questions": 2,
            },
        )
        assert response.status_code == (503 if failure in {"unavailable", "timeout"} else 422)
        with Session(client.app.state.engine) as db:
            assert db.exec(select(InterviewSession)).all() == []
            assert db.exec(select(InterviewTurn)).all() == []


def test_target_context_generation_does_not_require_bank_and_checks_consent(settings):
    provider = FreshProvider()
    with TestClient(create_app(settings, provider, FakeInterview())) as client:
        target = prepare(client)
        empty_bank(client.app)
        client.app.state.external_llm = True
        payload = {
            "request_id": str(uuid4()),
            "source": "ai_generated",
            "target_id": target,
            "category": "Kafka",
            "number_of_questions": 1,
        }
        assert client.post("/api/v1/interviews", json=payload).status_code == 422
        assert provider.calls == 0
        state = client.post(
            "/api/v1/interviews", json={**payload, "allow_external_processing": True}
        )
        assert state.status_code == 200, state.text
        evidence = provider.context["contexts"][0]["evidence"]
        assert evidence["resume_claims"] == []
        assert evidence["jd_claims"][0]["evidence"][0]["quote"] == "Kafka"
        assert "Test Candidate" not in json.dumps(provider.context)


def test_generation_rejects_conflicting_filters_before_provider_call(settings):
    provider = FreshProvider()
    with TestClient(create_app(settings, provider)) as client:
        response = client.post(
            "/api/v1/interviews",
            json={
                "request_id": str(uuid4()),
                "source": "ai_generated",
                "interview_type": "sql",
                "category": "Kafka",
                "number_of_questions": 1,
            },
        )
        assert response.status_code == 422 and provider.calls == 0
