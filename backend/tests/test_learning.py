from uuid import uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from test_interviews import FakeInterview, act, evaluate, start, submit
from test_questions import prepare

from app.db import migration_config
from app.learning_content import identity
from app.main import create_app
from app.models import BankQuestion, InterviewTurn, LearningEvidence, TurnEvaluation


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings, interview_provider=FakeInterview("follow"))) as c:
        yield c


def run_interview(client, mode="follow", **options):
    class Provider(FakeInterview):
        async def generate_structured(self, request):
            result = await super().generate_structured(request)
            if mode in {"partial", "incorrect"}:
                signal = result.data["topics"][0]
                signal["status"] = mode
                signal["evidence"] = result.data["dimensions"][0]["evidence"]
            return result

    client.app.state.interview_llm = Provider("follow" if mode == "follow" else "good")
    state = start(client, **options)
    while state["status"] == "active":
        state = evaluate(client, submit(client, state))
        state = act(client, state, "finish" if state["next_action"] == "finish" else "next")
    return state


def weak(client, **params):
    response = client.get("/api/v1/weaknesses", params=params)
    assert response.status_code == 200
    return next(r for r in response.json()["items"] if r["occurrence_count"])


def detail(client, key, **params):
    response = client.get("/api/v1/weaknesses/" + key, params=params)
    assert response.status_code == 200
    return response.json()


def test_detection_evidence_idempotency_and_followup_independence(client):
    state = run_interview(client)
    value = weak(client)
    assert value["occurrence_count"] == 3 and value["independent_interviews"] == 1
    assert value["severity"] == value["confidence"] == "low"
    assert weak(client) == value
    evidence = detail(client, value["id"])["evidence"]
    assert len(evidence) == 3
    assert all(e["session_id"] == state["id"] and e["absence_note"] for e in evidence)
    with Session(client.app.state.engine) as db:
        for e in evidence:
            evaluation = db.get(TurnEvaluation, e["evaluation_id"])
            assert evaluation.turn_id == e["turn_id"]
            assert db.get(InterviewTurn, e["turn_id"]).question_id == e["question_id"]
        assert (
            len(
                db.exec(
                    select(LearningEvidence).where(LearningEvidence.topic_id == value["id"])
                ).all()
            )
            == 3
        )


@pytest.mark.parametrize(
    "alias", ["Data skew", "Spark data skew", "Handling data skew", " DATA   SKEW "]
)
def test_normalization(alias):
    assert identity("Spark", alias)[0] == identity("Apache Spark", "Data skew")[0]
    assert identity("SQL", "Data skew")[0] != identity("Spark", alias)[0]


def test_no_weakness_from_positive_evidence(client):
    run_interview(client, "good")
    result = client.get("/api/v1/weaknesses").json()
    assert result["stats"]["active"] == 0
    assert all(v["status"] is None and v["strength_signal"] == "emerging" for v in result["items"])
    assert all(not v["recommendation"]["recommended"] for v in result["items"])


def test_improvement_resolution_and_recurrence(client):
    run_interview(client)
    key = weak(client)["id"]
    run_interview(client, "partial", focus_id=key)
    assert detail(client, key)["status"] == "improving"
    for count in range(1, 4):
        run_interview(client, "good", focus_id=key)
        v = detail(client, key)
        assert v["status"] == ("resolved" if count == 3 else "improving")
        assert v["strength_signal"] == ("emerging" if count == 1 else "repeated")
    assert not v["recommendation"]["recommended"]
    run_interview(client, "incorrect", focus_id=key)
    assert detail(client, key)["status"] == "detected"
    assert detail(client, key)["strength_signal"] is None


def test_severity_confidence_and_selected_jd_context(client):
    target = prepare(client)
    run_interview(client, "partial", target_id=target)
    key = weak(client)["id"]
    run_interview(client, "partial", focus_id=key, target_id=target)
    general, contextual = detail(client, key), detail(client, key, target_id=target)
    assert general["severity"] == "medium" and not general["jd_relevant"]
    assert contextual["severity"] == "high" and contextual["jd_required"]
    assert contextual["jd_evidence"][0]["evidence"][0]["quote"] == "Kafka"
    assert contextual["confidence"] == "medium"
    run_interview(client, "partial", focus_id=key)
    assert detail(client, key)["confidence"] == "high"
    assert "3 independent" in detail(client, key)["confidence_reason"]


def test_absence_only_confidence_never_high(client):
    run_interview(client)
    key = weak(client)["id"]
    run_interview(client, focus_id=key)
    run_interview(client, focus_id=key)
    assert detail(client, key)["confidence"] == "medium"


def test_targeted_practice_reuses_m3_and_m4(client):
    run_interview(client)
    row = weak(client)
    key = row["id"]
    rec = detail(client, key)["recommendation"]
    assert rec["recommended"] and rec["evidence_ids"]
    assert rec["available"] >= 1 and "1 interviews" in rec["reason"]
    questions = client.get("/api/v1/questions", params={"focus_id": key}).json()["items"]
    assert {q["id"] for q in questions} == {q["id"] for q in rec["questions"]}
    assert all(
        any(identity(q["skill"], t)[0] == key for t in q["expected_topics"]) for q in questions
    )
    payload = {"request_id": str(uuid4()), "mode": "interview", "number_of_questions": 1}
    url = f"/api/v1/weaknesses/{key}/practice"
    response = client.post(url, json=payload)
    assert response.status_code == 200
    planned = response.json()["interview"]
    assert client.post(url, json=payload).json()["interview"]["id"] == planned["id"]
    assert detail(client, key)["status"] == "practicing"
    client.app.state.interview_llm = FakeInterview("good")
    state = act(client, planned, "start")
    state = act(client, evaluate(client, submit(client, state)), "finish")
    assert state["status"] == "completed"
    assert detail(client, key)["status"] == "improving"


def test_no_exact_question_no_random_fallback(client):
    run_interview(client)
    key = weak(client)["id"]
    with Session(client.app.state.engine) as db:
        for q in db.exec(select(BankQuestion)).all():
            q.active = False
            db.add(q)
        db.commit()
    assert detail(client, key)["recommendation"]["available"] == 0
    response = client.post(f"/api/v1/weaknesses/{key}/practice", json={"request_id": str(uuid4())})
    assert response.status_code == 422


@pytest.mark.parametrize("corruption", ["missing", "unknown_topic", "quote", "public", "score"])
def test_unverified_stored_evaluation_cannot_create_signals(client, corruption):
    run_interview(client, "partial")
    key = weak(client)["id"]
    with Session(client.app.state.engine) as db:
        evaluation = db.exec(select(TurnEvaluation)).first()
        import copy

        result = copy.deepcopy(evaluation.result)
        if corruption == "missing":
            del result["judgment"]["dimensions"]
        elif corruption == "unknown_topic":
            result["judgment"]["topics"][0]["topic"] = "Invented technology"
        elif corruption == "quote":
            result["judgment"]["topics"][0]["evidence"][0]["quote"] = "fabricated"
        elif corruption == "public":
            result["public"]["weaknesses"] = ["Invented employment claim"]
        else:
            evaluation.score = 0
        evaluation.result = result
        db.add(evaluation)
        db.commit()
    result = client.get("/api/v1/weaknesses").json()
    assert result["items"] == [] and result["excluded_evaluations"] == 1
    assert client.get("/api/v1/weaknesses/" + key).status_code == 404


def test_status_validation_filters_and_restart(settings):
    with TestClient(create_app(settings, interview_provider=FakeInterview("follow"))) as client:
        run_interview(client)
        value = weak(client)
        url = f"/api/v1/weaknesses/{value['id']}/status"
        payload = {"revision": value["revision"], "status": "practicing"}
        assert client.patch(url, json=payload).status_code == 200
        assert client.patch(url, json=payload).status_code == 409
        assert client.patch(url, json={**payload, "status": "resolved"}).status_code == 422
    with TestClient(create_app(settings)) as client:
        assert detail(client, value["id"])["status"] == "practicing"
        for params in (
            {"status": "active"},
            {"category": "Kafka"},
            {"severity": "low"},
            {"search": value["topic"]},
        ):
            assert client.get("/api/v1/weaknesses", params=params).json()["items"]
        assert client.get("/api/v1/weaknesses", params={"status": "resolved"}).json()["items"] == []
        assert (
            client.get("/api/v1/weaknesses", params={"status": "jd_relevant"}).json()["items"] == []
        )
        assert client.get("/api/v1/weaknesses", params={"target_id": "unknown"}).status_code == 422


def test_migration_preserves_m4_and_backfills_without_provider(settings):
    with TestClient(create_app(settings)) as client:
        run_interview(client)
        original = client.get("/api/v1/interviews").json()
    config = migration_config(settings)
    command.downgrade(config, "0004")
    command.upgrade(config, "head")
    command.check(config)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/interviews").json() == original
        assert weak(client)["occurrence_count"] == 3


def test_empty_and_offline_answers_do_not_create_learning_signals(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/weaknesses").json()["items"] == []
        state = evaluate(client, submit(client, start(client)))
        assert state["current_turn"]["evaluation_state"] == "failed"
        assert client.get("/api/v1/weaknesses").json()["items"] == []


def test_aliases_collapse_in_persisted_evidence(client):
    with Session(client.app.state.engine) as db:
        q = db.get(BankQuestion, "curated:spark-skew")
        q.content = {**q.content, "expected_topics": ["Data skew", "Handling data skew"]}
        db.add(q)
        for other in db.exec(select(BankQuestion).where(BankQuestion.id != q.id)).all():
            other.active = False
            db.add(other)
        db.commit()
    run_interview(client, category="Apache Spark")
    rows = client.get("/api/v1/weaknesses").json()["items"]
    assert len(rows) == 1 and rows[0]["topic"] == "Data skew"
    assert rows[0]["evidence_count"] == rows[0]["occurrence_count"] == 3


def test_followup_recovery_is_not_independent_improvement(client):
    import json

    class RecoveryProvider(FakeInterview):
        async def generate_structured(self, request):
            mode = "good" if json.loads(request.context)["follow_up_depth"] else "follow"
            return await FakeInterview(mode).generate_structured(request)

    client.app.state.interview_llm = RecoveryProvider()
    state = start(client)
    while state["status"] == "active":
        state = evaluate(client, submit(client, state))
        state = act(client, state, "finish" if state["next_action"] == "finish" else "next")
    row = weak(client)
    assert row["status"] == "detected"
    assert row["independent_interviews"] == 1 and row["evidence_count"] == 2
    assert row["timeline"][0]["follow_up_recovery"]


def test_concurrent_learning_sync_is_idempotent(client):
    from concurrent.futures import ThreadPoolExecutor

    run_interview(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.get("/api/v1/weaknesses").json(), range(2)))
    assert results[0] == results[1]


def test_evidence_excerpt_is_bounded_and_recommendations_reflect_question_status(client):
    client.app.state.interview_llm = FakeInterview("good")
    state = start(client)
    state = evaluate(client, submit(client, state, answer="An answer with exact evidence. " * 100))
    row = client.get("/api/v1/weaknesses").json()["items"][0]
    d = detail(client, row["id"])
    assert all(len(q["quote"]) <= 240 for e in d["evidence"] for q in e["evidence"])
    question = d["recommendation"]["questions"][0]
    response = client.patch(
        "/api/v1/questions/" + question["id"], json={"status": "needs_review", "bookmarked": True}
    )
    assert response.status_code == 200
    assert detail(client, row["id"])["recommendation"]["questions"][0]["status"] == "needs_review"
    assert detail(client, row["id"])["recommendation"]["questions"][0]["times_asked"] == 1


def test_pre_m5_creation_keys_remain_idempotent(client):
    payload = {"request_id": str(uuid4()), "number_of_questions": 1}
    first = client.post("/api/v1/interviews", json=payload).json()
    assert "focus_id" not in first["configuration"]
    retry = client.post("/api/v1/interviews", json={**payload, "focus_id": None})
    assert retry.status_code == 200 and retry.json()["id"] == first["id"]
