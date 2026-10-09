import asyncio
import json
import shutil
import sqlite3

import pytest
from alembic import command
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import ROOT, Settings
from app.content import ContentCatalog
from app.contracts import (
    DisabledProvider,
    Evaluation,
    Evidence,
    InterviewPolicy,
    LLMRequest,
    LLMResult,
    ProviderUnavailable,
    SupportedClaim,
)
from app.db import make_engine, migration_config
from app.main import create_app


def test_health_content_and_no_secrets(settings):
    settings.llm_api_key = "private-test-value"
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/health").json()["schema_revision"] == "0005"
        capabilities = client.get("/api/v1/capabilities")
        assert capabilities.json()["llm"]["enabled"] is False
        assert "private-test-value" not in capabilities.text
        manifest = client.get("/api/v1/content/manifest").json()
        assert len(manifest["questions"]) == 3
        assert len(manifest["rubrics"]) == 1
        assert "expected_concepts" not in json.dumps(manifest)
        assert "weights" not in json.dumps(manifest)


def test_profile_persists_after_app_restart(settings):
    with TestClient(create_app(settings)) as client:
        profile = client.get("/api/v1/profile").json()
        payload = {
            key: profile[key]
            for key in [
                "name",
                "background",
                "target_role",
                "skills",
                "learning_skills",
                "daily_study_minutes",
            ]
        }
        payload.update(name="Test Candidate", skills=["SQL", "Spark"], daily_study_minutes=90)
        assert client.put("/api/v1/profile", json=payload).status_code == 200
    with TestClient(create_app(settings)) as restarted:
        saved = restarted.get("/api/v1/profile").json()
        assert saved["name"] == "Test Candidate"
        assert saved["skills"] == ["SQL", "Spark"]
        assert saved["id"] == profile["id"]
    with sqlite3.connect(settings.resolved_database_path) as db:
        assert db.execute("SELECT count(*) FROM profiles").fetchone()[0] == 1


def test_validation_and_origin_protection(settings):
    with TestClient(create_app(settings)) as client:
        response = client.put("/api/v1/profile", json={"name": "private input", "extra": "secret"})
        assert response.status_code == 422
        assert "private input" not in response.text
        assert "secret" not in response.text
        assert (
            client.put(
                "/api/v1/profile", headers={"origin": "https://evil.example"}, json={}
            ).status_code
            == 403
        )
        assert client.get("/api/v1/health", headers={"host": "evil.example"}).status_code == 400


def test_migration_upgrade_idempotent_and_reversible(settings):
    config = migration_config(settings)
    command.upgrade(config, "head")
    with sqlite3.connect(settings.resolved_database_path) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("0005",)
    command.downgrade(config, "base")
    with sqlite3.connect(settings.resolved_database_path) as db:
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='profiles'").fetchall()
    command.upgrade(config, "head")


def test_foreign_keys_enabled(settings):
    engine = make_engine(settings)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    engine.dispose()


def test_unmigrated_startup_fails(tmp_path):
    with pytest.raises(Exception):
        with TestClient(
            create_app(
                Settings(
                    database_path=tmp_path / "empty.db", storage_mode="local_sqlite", _env_file=None
                )
            )
        ):
            pass


def test_content_rejects_missing_rubric_and_duplicate_ids(tmp_path):
    shutil.copytree(ROOT / "content", tmp_path / "content")
    target = tmp_path / "content/questions/sql-dedup-v1.json"
    value = json.loads(target.read_text())
    value["rubric_id"] = "missing"
    target.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="Unknown rubric"):
        ContentCatalog(tmp_path / "content")
    value["rubric_id"] = "technical-v1"
    target.write_text(json.dumps(value))
    shutil.copy(target, target.with_name("duplicate.json"))
    with pytest.raises(ValueError, match="Duplicate"):
        ContentCatalog(tmp_path / "content")


def test_evidence_and_followup_contracts():
    evidence = Evidence(document_id="resume-1", start=0, end=5, quote="Spark")
    assert evidence.verify("resume-1", "Spark developer")
    assert not evidence.verify("jd-1", "Spark developer")
    assert not evidence.verify("resume-1", "Scala developer")
    with pytest.raises(ValidationError):
        SupportedClaim(claim="Invented skill", source_kind="resume", evidence=[])
    assert InterviewPolicy().max_follow_ups == 2
    with pytest.raises(ValidationError):
        InterviewPolicy(max_follow_ups=4)


class FakeProvider:
    async def generate_structured(self, request: LLMRequest) -> LLMResult:
        dimension = {"score": 2, "rationale": "Fixture evidence"}
        return LLMResult(
            data={
                "accuracy": dimension,
                "depth": dimension,
                "reasoning": dimension,
                "clarity": dimension,
                "missing_concepts": ["Partitioning"],
                "mistakes": [],
                "feedback": "Fixture feedback",
                "follow_up_recommended": True,
            },
            provider="fake",
            model="test",
            request_id="fixture-1",
        )


def test_fake_provider_and_strict_evaluation():
    request = LLMRequest(
        task="evaluation",
        instructions="fixture",
        context="fixture",
        output_schema=Evaluation.model_json_schema(),
    )
    response = asyncio.run(FakeProvider().generate_structured(request))
    assert Evaluation.model_validate(response.data).accuracy.score == 2
    with pytest.raises(ValidationError):
        Evaluation.model_validate({**response.data, "arbitrary_readiness": 98})
    response.data["accuracy"] = {"score": "4", "rationale": "Not an integer"}
    with pytest.raises(ValidationError):
        Evaluation.model_validate(response.data)
    with pytest.raises(ProviderUnavailable):
        asyncio.run(DisabledProvider().generate_structured(request))
