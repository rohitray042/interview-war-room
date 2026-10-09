"""Run explicitly with WAR_ROOM_VERIFY_DATABASE; no personal data in test fixtures."""

import os
from collections import Counter
from pathlib import Path
from statistics import mean

import pytest
from fastapi.testclient import TestClient
from persisted_data import copy_database, fingerprint
from sqlmodel import Session, select
from test_interviews import FakeInterview, act, evaluate, start, submit
from test_questions import FakeQuestions

from app.analyzer import compare
from app.analyzer_schemas import Claim
from app.config import Settings
from app.main import create_app
from app.models import Analysis, BankQuestion, Document, InterviewTurn, Target, TurnEvaluation


@pytest.fixture
def persisted_settings(tmp_path):
    source = os.environ.get("WAR_ROOM_VERIFY_DATABASE")
    if not source:
        pytest.skip("Opt-in: set WAR_ROOM_VERIFY_DATABASE to verify a read-only database copy")
    before = fingerprint(source)
    destination = tmp_path / "persisted-verification.db"
    copy_database(source, destination)
    from alembic import command

    from app.db import migration_config

    command.upgrade(migration_config(Settings(database_path=destination, _env_file=None)), "head")
    yield Settings(
        database_path=destination,
        llm_provider="disabled",
        storage_mode="local_sqlite",
        _env_file=None,
    )
    assert fingerprint(source) == before, "Verification changed the original workspace"


def verified_target(client):
    targets = client.get("/api/v1/targets").json()
    assert targets, "No persisted M2 target available; do not substitute a demo target"
    target_id = targets[0]["id"]
    with Session(client.app.state.engine) as db:
        target = db.get(Target, target_id)
        resume, jd = db.get(Analysis, target.resume_id), db.get(Analysis, target.jd_id)
        assert resume.status == jd.status == "confirmed"
        rd, jdd = db.get(Document, resume.document_id), db.get(Document, jd.document_id)
        assert rd.kind == "resume" and jdd.kind == "jd"
        assert rd.filename.lower().endswith((".pdf", ".docx", ".txt"))
        recalculated = compare(
            [Claim.model_validate(c) for c in resume.claims],
            [Claim.model_validate(c) for c in jd.claims],
            rd,
            jdd,
        )
        assert target.result == recalculated
        assert Counter(row["status"] for row in target.result["items"])
        for analysis, document in ((resume, rd), (jd, jdd)):
            for claim in analysis.claims:
                for e in claim["evidence"]:
                    assert e["document_id"] == document.id
                    assert document.text[e["start"] : e["end"]] == e["quote"]
        source_ids = {"resume": resume.id, "jd": jd.id}
    return target_id, source_ids


@pytest.mark.parametrize("mocked", [False, True], ids=["disabled-provider", "mocked-provider"])
def test_real_m2_m3_to_m4_with_restart(persisted_settings, mocked):
    fake = FakeInterview("follow")

    def app():
        return create_app(
            persisted_settings,
            question_provider=FakeQuestions() if mocked else None,
            interview_provider=fake if mocked else None,
            test_data="persisted-copy",
        )

    with TestClient(app()) as client:
        target, analyses = verified_target(client)
        baseline_weaknesses = client.get("/api/v1/interviews/weaknesses").json()
        preview = client.post("/api/v1/questions/generation-preview", json={"target_id": target})
        assert preview.status_code == 200 and preview.json()["available"] >= 3
        if mocked:
            generated = client.post(
                "/api/v1/questions/generate",
                json={
                    "target_id": target,
                    "number_of_questions": 3,
                },
            )
            assert generated.status_code == 200
            assert len(generated.json()["items"]) == 3
        state = start(
            client,
            target_id=target,
            category=None,
            number_of_questions=3,
            source="personalized" if mocked else "curated",
        )
        url = f"/api/v1/interviews/{state['id']}"
        with Session(client.app.state.engine) as db:
            turns = db.exec(
                select(InterviewTurn).where(InterviewTurn.session_id == state["id"])
            ).all()
            assert len({t.question_id for t in turns}) == 3
            for turn in turns:
                assert db.get(BankQuestion, turn.question_id)
                context = turn.snapshot["context"]
                assert context["target_id"] == target
                assert context["resume_analysis_id"] == analyses["resume"]
                assert context["jd_analysis_id"] == analyses["jd"]
                assert context["jd_claims"]
                for kind in ("resume", "jd"):
                    analysis = db.get(Analysis, analyses[kind])
                    document = db.get(Document, analysis.document_id)
                    for claim in context[f"{kind}_claims"]:
                        for e in claim["evidence"]:
                            assert e["document_id"] == document.id
                            assert document.text[e["start"] : e["end"]] == e["quote"]
        state = submit(
            client,
            state,
            answer="Verification answer 1: I would validate source records, "
            "use idempotent incremental loads, and monitor failures.",
        )
        first_turn = state["current_turn"]["id"]
        first_answer = state["current_turn"]["answer_text"]

    # Fresh app/engine, same on-disk SQLite file, before evaluating the saved answer.
    with TestClient(app()) as client:
        state = client.get(url).json()
        assert state["current_turn"]["id"] == first_turn
        assert state["current_turn"]["answer_text"] == first_answer
        answers = 0
        while state["status"] == "active":
            if state["current_turn"]["answer_text"] is None:
                state = submit(
                    client,
                    state,
                    answer=f"Verification answer {answers + 1}: I would test retries, "
                    "reconcile row counts and explain the trade-offs before deployment.",
                )
            state = evaluate(client, state)
            answers += 1
            turn = state["current_turn"]
            if mocked:
                assert turn["evaluation_state"] == "succeeded"
                assert fake.context["answer"] == turn["answer_text"]
                assert fake.context["question"]["question_text"] == turn["question_text"]
                assert fake.context["source_context"]["target_id"] == target
                assert fake.context["source_context"]["jd_claims"]
                assert set(fake.context) == {
                    "question",
                    "rubric",
                    "answer",
                    "follow_up_depth",
                    "source_context",
                }
            else:
                assert turn["evaluation_state"] == "failed" and turn["evaluation"] is None
                assert "no LLM provider is configured" in turn["evaluation_error"]
                state = act(client, state, "defer_evaluation")
            assert answers <= 9
            state = act(client, state, "finish" if state["next_action"] == "finish" else "next")
        result = client.get(url + "/summary").json()
        assert result["session"]["id"] == state["id"]
        assert result["primary_answered"] == 3
        assert result["answers_submitted"] == answers
        assert result["follow_ups"] == (6 if mocked else 0)
        with Session(client.app.state.engine) as db:
            stored = db.exec(
                select(TurnEvaluation)
                .join(InterviewTurn, TurnEvaluation.turn_id == InterviewTurn.id)
                .where(InterviewTurn.session_id == state["id"])
            ).all()
            assert len(stored) == (answers if mocked else 0)
            assert result["average_score"] == (
                round(mean(e.score for e in stored), 2) if stored else None
            )
            evaluations = {e.id: e for e in stored}
            for row in result["weak_areas"]:
                assert row["count"] == len(row["occurrences"])
                for occurrence in row["occurrences"]:
                    assert occurrence["session_id"] == state["id"]
                    evaluation = evaluations[occurrence["evaluation_id"]]
                    assert occurrence["turn_id"] == evaluation.turn_id
                    assert any(
                        t["topic"] == row["topic"] and t["status"] == occurrence["assessment"]
                        for t in evaluation.result["public"]["topics"]
                    )
        if mocked:
            assert result["weak_areas"] and result["suggested_practice"]
        else:
            assert result["weak_areas"] == result["suggested_practice"] == []
            assert client.get("/api/v1/interviews/weaknesses").json() == baseline_weaknesses
        saved_summary = result
    with TestClient(app()) as client:
        assert client.get(url + "/summary").json() == saved_summary
        assert client.get(url).json()["status"] == "completed"


def test_original_resume_upload_reuses_persisted_document(persisted_settings):
    path = os.environ.get("WAR_ROOM_VERIFY_RESUME")
    if not path:
        pytest.skip("Set WAR_ROOM_VERIFY_RESUME to verify the original upload again")
    with TestClient(create_app(persisted_settings, test_data="persisted-copy")) as client:
        target, _ = verified_target(client)
        response = client.post(
            "/api/v1/documents/upload",
            data={"kind": "resume"},
            files={
                "file": (Path(path).name, Path(path).read_bytes(), "application/pdf"),
            },
        )
        assert response.status_code == 200
        assert response.json()["duplicate"] is True
        assert target in {t["id"] for t in client.get("/api/v1/targets").json()}


def test_workspace_provenance_and_no_production_fake_provider(settings):
    with TestClient(create_app(settings)) as client:
        capabilities = client.get("/api/v1/capabilities").json()
        assert capabilities["workspace"] == {"data": "user", "simulated_ai": False}
        assert capabilities["interview_evaluation"]["enabled"] is False
        assert client.get("/api/v1/targets").json() == []
        assert client.get("/api/v1/interviews").json() == []
        assert client.get("/api/v1/interviews/weaknesses").json() == []
    with TestClient(create_app(settings, interview_provider=FakeInterview())) as client:
        assert client.get("/api/v1/capabilities").json()["workspace"] == {
            "data": "fixtures",
            "simulated_ai": True,
        }
