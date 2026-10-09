import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from test_questions import FakeQuestions, prepare

from app.contracts import LLMResult, ProviderUnavailable
from app.db import migration_config
from app.main import create_app
from app.models import BankQuestion, InterviewSession, InterviewTurn, TurnEvaluation, utc_now


class FakeInterview:
    def __init__(self, mode="good"):
        self.mode, self.calls, self.context = mode, 0, None

    async def generate_structured(self, request):
        self.calls += 1
        self.context = context = json.loads(request.context)
        if self.mode == "unavailable":
            raise ProviderUnavailable()
        if self.mode == "timeout":
            raise TimeoutError()
        if self.mode == "slow":
            await asyncio.sleep(0.15)
        answer = context["answer"]
        evidence = [{"start": 0, "end": len(answer), "quote": answer}]
        topics = context["question"]["expected_topics"]
        gap = self.mode == "follow"
        data = {
            "dimensions": [
                {"dimension": d, "score": 2 if gap else 3, "evidence": evidence}
                for d in context["rubric"]["weights"]
            ],
            "topics": [
                {
                    "topic": t,
                    "status": "not_demonstrated" if gap and i == 0 else "demonstrated",
                    "evidence": [] if gap and i == 0 else evidence,
                }
                for i, t in enumerate(topics)
            ],
            "follow_up_topic": topics[0] if gap else None,
        }
        if self.mode == "invalid":
            data = {"score": 99, "feedback": "Since you implemented Kafka at Cisco..."}
        elif self.mode == "bad_quote":
            data["dimensions"][0]["evidence"] = [{"start": 0, "end": 8, "quote": "invented"}]
        elif self.mode == "bad_score":
            data["dimensions"][0]["score"] = 99
        elif self.mode == "wrong_topic":
            data["topics"][0]["topic"] = "Invented production experience"
        elif self.mode == "bad_follow_up":
            data["follow_up_topic"] = "Invented project at Cisco"
        elif self.mode == "missing_dimensions":
            data["dimensions"] = data["dimensions"][:-1]
        return LLMResult(data=data, provider="fake", model="interview-fixture", request_id="test")


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings, interview_provider=FakeInterview())) as client:
        yield client


def create(client, **overrides):
    payload = {
        "request_id": str(uuid4()),
        "number_of_questions": 1,
        "category": "Kafka",
        **overrides,
    }
    response = client.post("/api/v1/interviews", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def act(client, state, action):
    response = client.post(
        f"/api/v1/interviews/{state['id']}/actions",
        json={"revision": state["revision"], "action": action},
    )
    assert response.status_code == 200, response.text
    return response.json()


def start(client, **overrides):
    return act(client, create(client, **overrides), "start")


def submit(
    client,
    state,
    answer="Use partition keys and idempotent writes; test replay after a crash.",
    key=None,
):
    response = client.post(
        f"/api/v1/interviews/{state['id']}/turns/{state['current_turn']['id']}/answer",
        json={
            "revision": state["revision"],
            "submission_id": key or str(uuid4()),
            "answer_text": answer,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def evaluate(client, state):
    response = client.post(
        f"/api/v1/interviews/{state['id']}/turns/{state['current_turn']['id']}/evaluate", json={}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_create_start_hidden_data_and_creation_retry(client):
    key = str(uuid4())
    s = create(client, number_of_questions=2, request_id=key)
    assert s["status"] == "not_started" and s["current_turn"] is None
    assert create(client, number_of_questions=2, request_id=key)["id"] == s["id"]
    assert (
        client.post(
            "/api/v1/interviews", json={"request_id": key, "number_of_questions": 1}
        ).status_code
        == 409
    )
    s = act(client, s, "start")
    assert s["current_turn"]["primary_number"] == 1
    text = json.dumps(s)
    assert all(
        k not in text for k in ("expected_topics", "snapshot", "weights", "evaluation_focus")
    )
    with Session(client.app.state.engine) as db:
        turns = db.exec(
            select(InterviewTurn)
            .where(InterviewTurn.session_id == s["id"])
            .order_by(InterviewTurn.primary_number)
        ).all()
        assert turns[1].snapshot["content"]["question_text"] not in text
        assert len({t.question_id for t in turns}) == 2
    assert client.get(f"/api/v1/interviews/{s['id']}/summary").status_code == 409


@pytest.mark.parametrize(
    "kind,category",
    [
        ("technical", "Kafka"),
        ("sql", "SQL"),
        ("system_design", "System Design"),
        ("behavioral", "Behavioral"),
        ("data_engineering", "Snowflake"),
        ("project_deep_dive", "Apache Spark"),
        ("mixed", None),
    ],
)
def test_types_and_rubric_selection(client, kind, category):
    s = start(client, interview_type=kind, category=category)
    if kind == "project_deep_dive":
        assert "hypothetical" in s["current_turn"]["question_text"]
    s = evaluate(client, submit(client, s))
    evaluation = s["current_turn"]["evaluation"]
    assert evaluation["score"] == 7.5
    expected = kind if kind in {"sql", "system_design", "behavioral"} else "technical"
    if kind != "mixed":
        assert evaluation["rubric_id"] == f"interview-{expected}-v1"


def test_duplicate_answer_and_concurrent_submission(client):
    s = start(client)
    turn = s["current_turn"]["id"]
    body = {"revision": s["revision"], "submission_id": str(uuid4()), "answer_text": "Saved once."}
    url = f"/api/v1/interviews/{s['id']}/turns/{turn}/answer"
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(url, json=body), range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert client.post(url, json={**body, "answer_text": "Changed"}).status_code == 409
    assert client.post(url, json={**body, "submission_id": str(uuid4())}).status_code == 409
    with Session(client.app.state.engine) as db:
        assert (
            len(db.exec(select(InterviewTurn).where(InterviewTurn.answer_text.is_not(None))).all())
            == 1
        )


@pytest.mark.parametrize(
    "mode",
    [
        "invalid",
        "bad_quote",
        "bad_score",
        "wrong_topic",
        "bad_follow_up",
        "missing_dimensions",
        "unavailable",
        "timeout",
    ],
)
def test_failed_evaluation_preserves_answer(client, mode, caplog):
    client.app.state.interview_llm = FakeInterview(mode)
    s = evaluate(client, submit(client, start(client), answer="Private answer fixture 4812"))
    assert s["current_turn"]["evaluation_state"] == "failed"
    assert s["current_turn"]["answer_text"] == "Private answer fixture 4812"
    assert s["current_turn"]["evaluation"] is None and s["current_turn"]["retryable"]
    assert "Private answer fixture" not in caplog.text and "Cisco" not in caplog.text
    assert (
        client.post(
            f"/api/v1/interviews/{s['id']}/actions",
            json={"revision": s["revision"], "action": "next"},
        ).status_code
        == 409
    )
    client.app.state.interview_llm = FakeInterview()
    assert evaluate(client, s)["current_turn"]["evaluation_state"] == "succeeded"


def test_offline_flow_is_explicit_unscored(settings):
    with TestClient(create_app(settings)) as c:
        s = evaluate(c, submit(c, start(c)))
        assert "no LLM provider is configured" in s["current_turn"]["evaluation_error"]
        s = act(c, s, "defer_evaluation")
        s = act(c, s, "finish")
        result = c.get(f"/api/v1/interviews/{s['id']}/summary").json()
        assert result["unscored_answers"] == 1 and result["average_score"] is None
        assert result["weak_areas"] == [] and result["suggested_practice"] == []


def test_follow_up_cap_relationships_completion_and_summary(client):
    client.app.state.interview_llm = FakeInterview("follow")
    s = start(client)
    previous = None
    for depth in range(3):
        assert s["current_turn"]["follow_up_depth"] == depth
        assert s["current_turn"]["parent_turn_id"] == previous
        previous = s["current_turn"]["id"]
        s = evaluate(client, submit(client, s))
        assert s["current_turn"]["evaluation"]["follow_up_required"] == (depth < 2)
        s = act(client, s, "next" if depth < 2 else "finish")
    assert s["status"] == "completed"
    result = client.get(f"/api/v1/interviews/{s['id']}/summary").json()
    assert result["follow_ups"] == 2 and result["answers_submitted"] == 3
    assert result["primary_answered"] == 1 and result["average_score"] == 5
    assert result["weak_areas"][0]["count"] == 3
    assert len(result["weak_areas"][0]["occurrences"]) == 3
    assert client.get("/api/v1/interviews/weaknesses").json()[0]["count"] == 3
    assert client.get("/api/v1/interviews/stats").json()["completed_sessions"] == 1
    assert (
        client.post(
            f"/api/v1/interviews/{s['id']}/actions",
            json={"revision": s["revision"], "action": "resume"},
        ).status_code
        == 409
    )


def test_invalid_transitions_and_order(client):
    s = start(client, number_of_questions=2)
    url = f"/api/v1/interviews/{s['id']}"
    for action in ["start", "finish", "next", "defer_evaluation", "resume"]:
        assert (
            client.post(
                url + "/actions", json={"revision": s["revision"], "action": action}
            ).status_code
            == 409
        )
    assert client.post(url + "/turns/nonexistent/evaluate", json={}).status_code == 409
    s = act(client, s, "pause")
    assert (
        client.post(
            url + f"/turns/{s['current_turn']['id']}/answer",
            json={"revision": s["revision"], "submission_id": str(uuid4()), "answer_text": "No"},
        ).status_code
        == 409
    )
    s = act(client, s, "resume")
    s = evaluate(client, submit(client, s))
    assert (
        client.post(
            url + "/actions", json={"revision": s["revision"], "action": "finish"}
        ).status_code
        == 409
    )
    s = act(client, s, "next")
    assert s["current_turn"]["primary_number"] == 2


def test_evaluation_single_lease_and_idempotency(client):
    fake = FakeInterview("slow")
    client.app.state.interview_llm = fake
    s = submit(client, start(client))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: evaluate(client, s), range(2)))
    assert fake.calls == 1
    assert any(r["current_turn"]["evaluation_state"] == "succeeded" for r in results)
    s = evaluate(client, s)
    assert fake.calls == 1 and s["current_turn"]["evaluation"]
    with Session(client.app.state.engine) as db:
        assert len(db.exec(select(TurnEvaluation)).all()) == 1


def test_restart_and_expired_lease(settings):
    with TestClient(create_app(settings)) as c:
        s = submit(c, start(c))
        with Session(c.app.state.engine) as db:
            turn = db.get(InterviewTurn, s["current_turn"]["id"])
            turn.evaluation_state = "evaluating"
            turn.lease_token = "old-token"
            turn.lease_until = utc_now() - timedelta(seconds=1)
            db.add(turn)
            db.commit()
    with TestClient(create_app(settings, interview_provider=FakeInterview())) as c:
        reopened = c.get(f"/api/v1/interviews/{s['id']}").json()
        assert reopened["current_turn"]["answer_text"] == s["current_turn"]["answer_text"]
        assert reopened["current_turn"]["retryable"]
        assert evaluate(c, reopened)["current_turn"]["evaluation"]


def test_deleted_bank_question_and_corrupt_pointer(client):
    s = start(client)
    with Session(client.app.state.engine) as db:
        turn = db.get(InterviewTurn, s["current_turn"]["id"])
        question = db.get(BankQuestion, turn.question_id)
        db.delete(question)
        db.commit()
    assert evaluate(client, submit(client, s))["current_turn"]["evaluation"]
    with Session(client.app.state.engine) as db:
        interview = db.get(InterviewSession, s["id"])
        interview.current_turn_id = "missing"
        db.add(interview)
        db.commit()
    assert client.get(f"/api/v1/interviews/{s['id']}").status_code == 409
    with Session(client.app.state.engine) as db:
        assert db.get(InterviewTurn, s["current_turn"]["id"]).answer_text


def test_jd_personalization_no_duplicates_or_invented_context(client):
    target = prepare(client)
    client.app.state.question_llm = FakeQuestions()
    s = start(client, target_id=target, source="ai_generated", number_of_questions=2)
    with Session(client.app.state.engine) as db:
        turns = db.exec(select(InterviewTurn).where(InterviewTurn.session_id == s["id"])).all()
        assert len({t.snapshot["content"]["question_text"] for t in turns}) == 2
        assert all(t.snapshot["context"]["coverage"] == "missing" for t in turns)
    s = evaluate(client, submit(client, s))
    context = client.app.state.interview_llm.context
    assert context["source_context"]["resume_claims"] == []
    assert context["source_context"]["jd_claims"][0]["evidence"][0]["quote"] == "Kafka"
    assert "Test Candidate" not in json.dumps(context)
    mixed = start(client, target_id=target, source="mixed", number_of_questions=3)
    with Session(client.app.state.engine) as db:
        turns = db.exec(select(InterviewTurn).where(InterviewTurn.session_id == mixed["id"])).all()
        texts = [
            t.snapshot["content"]["question_text"].removeprefix(
                "Target-role practice (prior experience is not assumed). "
            )
            for t in turns
        ]
        assert len(set(texts)) == 3


def test_consent_and_insufficient_questions(client):
    assert (
        client.post(
            "/api/v1/interviews", json={"request_id": str(uuid4()), "category": "Unknown"}
        ).status_code
        == 422
    )
    s = submit(client, start(client))
    client.app.state.external_llm = True
    response = client.post(
        f"/api/v1/interviews/{s['id']}/turns/{s['current_turn']['id']}/evaluate", json={}
    )
    assert response.status_code == 422
    assert client.get(f"/api/v1/interviews/{s['id']}").json()["current_turn"]["answer_text"]
    assert (
        client.post(
            f"/api/v1/interviews/{s['id']}/turns/{s['current_turn']['id']}/evaluate",
            json={"allow_external_processing": True},
        ).status_code
        == 200
    )


def test_migration_preserves_question_bank(settings):
    with TestClient(create_app(settings)) as client:
        q = client.get("/api/v1/questions").json()["items"][0]
        client.patch(
            "/api/v1/questions/" + q["id"], json={"status": "practiced", "bookmarked": True}
        )
    config = migration_config(settings)
    command.downgrade(config, "0003")
    command.upgrade(config, "head")
    command.check(config)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/questions/" + q["id"]).json()["bookmarked"]


def test_concurrent_progression_cannot_skip_question(client):
    s = evaluate(client, submit(client, start(client, number_of_questions=3)))
    url = f"/api/v1/interviews/{s['id']}/actions"
    body = {"revision": s["revision"], "action": "next"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(url, json=body), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    current = client.get(f"/api/v1/interviews/{s['id']}").json()
    assert current["current_turn"]["primary_number"] == 2


def test_stale_evaluator_cannot_overwrite_retry(client):
    import threading

    started = threading.Event()

    class SlowProvider(FakeInterview):
        async def generate_structured(self, request):
            started.set()
            await asyncio.sleep(0.3)
            return await super().generate_structured(request)

    client.app.state.interview_llm = SlowProvider()
    s = submit(client, start(client))
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(evaluate, client, s)
        assert started.wait(2)
        with Session(client.app.state.engine) as db:
            turn = db.get(InterviewTurn, s["current_turn"]["id"])
            turn.lease_until = utc_now() - timedelta(seconds=1)
            db.add(turn)
            db.commit()
        client.app.state.interview_llm = FakeInterview("follow")
        second = evaluate(client, s)
        assert second["current_turn"]["evaluation"]["score"] == 5
        first.result()
    with Session(client.app.state.engine) as db:
        evaluations = db.exec(select(TurnEvaluation)).all()
        assert len(evaluations) == 1 and evaluations[0].score == 5


def test_closed_session_rejects_answer_and_evaluation_and_abandon_preserves_answer(client):
    s = submit(client, start(client))
    answer = s["current_turn"]["answer_text"]
    s = act(client, s, "abandon")
    url = f"/api/v1/interviews/{s['id']}/turns/{s['current_turn']['id']}"
    assert (
        client.post(
            url + "/answer",
            json={
                "revision": s["revision"],
                "submission_id": str(uuid4()),
                "answer_text": "changed",
            },
        ).status_code
        == 409
    )
    assert client.post(url + "/evaluate", json={}).status_code == 409
    assert (
        client.get(f"/api/v1/interviews/{s['id']}/summary").json()["turns"][0]["answer_text"]
        == answer
    )


def test_unexpected_provider_error_and_unsupported_experience_field(client):
    class BrokenProvider:
        async def generate_structured(self, request):
            raise RuntimeError("private provider payload must not be exposed")

    client.app.state.interview_llm = BrokenProvider()
    s = evaluate(client, submit(client, start(client)))
    assert s["current_turn"]["evaluation_state"] == "failed"
    assert "private provider payload" not in json.dumps(s)


def test_snapshot_and_followup_relationship_survive_restart(settings):
    with TestClient(create_app(settings, interview_provider=FakeInterview("follow"))) as client:
        s = act(client, evaluate(client, submit(client, start(client))), "next")
        parent = s["current_turn"]["parent_turn_id"]
    with TestClient(create_app(settings, interview_provider=FakeInterview())) as client:
        reopened = client.get(f"/api/v1/interviews/{s['id']}").json()
        assert reopened["current_turn"]["follow_up_depth"] == 1
        assert reopened["current_turn"]["parent_turn_id"] == parent
        s = act(client, evaluate(client, submit(client, reopened)), "finish")
        assert s["status"] == "completed"
