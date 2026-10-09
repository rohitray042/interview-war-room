import test_persisted_integration
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from test_learning import detail, run_interview
from test_persisted_integration import verified_target

from app.main import create_app
from app.models import InterviewSession, InterviewTurn, TurnEvaluation

persisted_settings = test_persisted_integration.persisted_settings


def test_learning_from_real_persisted_sources_without_changing_existing_session(persisted_settings):
    settings = persisted_settings
    with TestClient(create_app(settings, test_data="persisted-copy")) as client:
        target, _ = verified_target(client)
        with Session(client.app.state.engine) as db:
            before_sessions = {
                s.id: s.model_dump() for s in db.exec(select(InterviewSession)).all()
            }
            before_turns = {t.id: t.model_dump() for t in db.exec(select(InterviewTurn)).all()}
            existing_evaluations = db.exec(select(TurnEvaluation)).all()
        baseline = client.get("/api/v1/weaknesses").json()
        if not existing_evaluations:
            assert baseline["items"] == []
        state = run_interview(client, target_id=target, category=None)
        rows = client.get("/api/v1/weaknesses", params={"target_id": target}).json()["items"]
        row = next(
            v
            for v in rows
            if v["occurrence_count"] and any(p["session_id"] == state["id"] for p in v["timeline"])
        )
        assert row["jd_relevant"] and row["recommendation"]["available"]
        key = row["id"]
        d = detail(client, key, target_id=target)
        assert d["jd_evidence"] and any(e["session_id"] == state["id"] for e in d["evidence"])
        run_interview(client, "good", category=None, target_id=target, focus_id=key)
        assert detail(client, key)["status"] == "improving"
    with TestClient(create_app(settings, test_data="persisted-copy")) as client:
        assert detail(client, key)["status"] == "improving"
        with Session(client.app.state.engine) as db:
            assert all(
                db.get(InterviewSession, id).model_dump() == value
                for id, value in before_sessions.items()
            )
            assert all(
                db.get(InterviewTurn, id).model_dump() == value
                for id, value in before_turns.items()
            )
