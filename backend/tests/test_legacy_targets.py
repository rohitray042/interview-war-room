import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session
from test_questions import prepare

from app.main import create_app
from app.models import Analysis, Target


@pytest.mark.parametrize("invalid", [False, True])
def test_legacy_target_is_revalidated_not_hidden(settings, invalid):
    with TestClient(create_app(settings)) as client:
        identity = prepare(client)
        original = client.get("/api/v1/targets").json()[0]
        with Session(client.app.state.engine) as db:
            target = db.get(Target, identity)
            target.result = {"method": "evidence-comparison-v1", "items": []}
            db.add(target)
            if invalid:
                resume = db.get(Analysis, target.resume_id)
                resume.claims = [
                    {
                        **resume.claims[0],
                        "evidence": [
                            {
                                "document_id": resume.document_id,
                                "start": 0,
                                "end": 8,
                                "quote": "invented",
                            }
                        ],
                    }
                ]
                db.add(resume)
            db.commit()
        response = client.get("/api/v1/targets")
        if invalid:
            assert response.status_code == 409
            with Session(client.app.state.engine) as db:
                assert db.get(Target, identity).result["method"] == "evidence-comparison-v1"
        else:
            assert response.status_code == 200
            assert response.json()[0] == original
    if not invalid:
        with TestClient(create_app(settings)) as restarted:
            assert restarted.get("/api/v1/targets").json()[0] == original
