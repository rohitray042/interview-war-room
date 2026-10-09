from fastapi.testclient import TestClient
from sqlmodel import Session, select
from test_interviews import FakeInterview, evaluate, start, submit
from test_questions import FakeQuestions, prepare

from app.main import create_app
from app.models import BankQuestion


def test_fresh_drafts_follow_filters_exceed_catalog_count_and_persist(settings):
    fake = FakeQuestions()
    with TestClient(
        create_app(settings, question_provider=fake, interview_provider=FakeInterview())
    ) as c:
        target = prepare(c)
        payload = {
            "target_id": target,
            "generation_mode": "draft",
            "category": "Kafka",
            "difficulty": "hard",
            "question_type": "scenario",
            "number_of_questions": 5,
        }
        assert (
            c.post("/api/v1/questions/generation-preview", json=payload).json()["available"] == 20
        )
        result = c.post("/api/v1/questions/generate", json=payload)
        assert result.status_code == 200, result.text
        items = result.json()["items"]
        assert len(items) == 5 and len({q["question_text"] for q in items}) == 5
        assert all(
            q["difficulty"] == "hard"
            and q["question_type"] == "scenario"
            and q["category"] == "Kafka"
            for q in items
        )
        assert all(q["source_reference"]["generation_mode"] == "fresh_draft_v1" for q in items)
        assert all(q["source_reference"]["targets"][0]["coverage"] == "missing" for q in items)
        assert "Test Candidate" not in str(fake.context)
        state = start(c, target_id=target, source="personalized", difficulty="hard")
        assert evaluate(c, submit(c, state))["current_turn"]["evaluation_state"] == "succeeded"
    with TestClient(create_app(settings)) as c:
        assert c.get("/api/v1/questions?source=generated").json()["total"] == 5


def test_invalid_draft_preserves_catalog(settings):
    class Bad(FakeQuestions):
        async def generate_structured(self, request):
            result = await super().generate_structured(request)
            result.data["questions"][0]["question_text"] = (
                "You implemented Kafka at Cisco. Explain it."
            )
            return result

    with TestClient(create_app(settings, question_provider=Bad())) as c:
        target = prepare(c)
        result = c.post(
            "/api/v1/questions/generate",
            json={"target_id": target, "generation_mode": "draft", "number_of_questions": 1},
        )
        assert result.status_code == 422
        assert c.get("/api/v1/questions/stats").json()["generated"] == 0
        with Session(c.app.state.engine) as db:
            assert (
                len(db.exec(select(BankQuestion).where(BankQuestion.source == "curated")).all())
                == 36
            )


def test_draft_consent_and_missing_category(settings):
    with TestClient(create_app(settings, question_provider=FakeQuestions())) as c:
        target = prepare(c)
        payload = {"target_id": target, "generation_mode": "draft", "number_of_questions": 1}
        c.app.state.external_llm = True
        assert c.post("/api/v1/questions/generate", json=payload).status_code == 422
        assert (
            c.post(
                "/api/v1/questions/generate",
                json={**payload, "allow_external_processing": True, "category": "Unknown"},
            ).status_code
            == 422
        )
