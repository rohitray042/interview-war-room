import asyncio
import copy
import json
import shutil

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlmodel import Session, select

from app.config import ROOT, Settings
from app.contracts import LLMRequest, LLMResult, ProviderUnavailable
from app.main import create_app
from app.models import Analysis, BankQuestion, Target
from app.providers import OpenAIProvider
from app.question_schemas import Catalog, GenerateInput
from app.questions import candidates, normalized, sync_catalog


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def prepare(client):
    ids = []
    for kind, text in [
        ("resume", "Test Candidate\nSKILLS\nPython\nEXPERIENCE\n- Built Snowflake pipelines."),
        ("jd", "Must have\nKafka\nPython\nSnowflake"),
    ]:
        bundle = client.post("/api/v1/documents/text", json={"kind": kind, "text": text}).json()
        a = bundle["analyses"][0]
        if a["status"] != "confirmed":
            assert (
                client.post(
                    "/api/v1/analyses/" + a["id"] + "/confirm", json={"revision": a["revision"]}
                ).status_code
                == 200
            )
        ids.append(a["id"])
    response = client.post("/api/v1/targets", json={"resume_id": ids[0], "jd_id": ids[1]})
    assert response.status_code == 200, response.text
    return response.json()["id"]


class FakeQuestions:
    def __init__(self, mode="valid"):
        self.mode = mode
        self.context = None

    async def generate_structured(self, request):
        self.context = json.loads(request.context)
        if self.context.get("mode") == "live_interview_v1":
            anchor = self.context["contexts"][0]
            questions = [
                {
                    "context_id": anchor["id"],
                    "category": anchor["category"],
                    "skill": anchor["skill"],
                    "question_text": (
                        f"Given a hypothetical workload {i + len(self.context['history'])}, "
                        "explain recovery trade-offs."
                    ),
                    "subcategory": "Recovery",
                    "difficulty": self.context["difficulty"] or "medium",
                    "question_type": self.context["allowed_types"][0],
                    "tags": [anchor["skill"]],
                    "expected_topics": [anchor["focus_topic"] or "Recovery"],
                    "evaluation_focus": "Explain a concrete recovery approach and its limitations.",
                }
                for i in range(self.context["count"])
            ]
            return LLMResult(
                data={"questions": questions}, provider="fake", model="fixture", request_id="test"
            )
        if self.context.get("mode") == "fresh_draft_v1":
            return LLMResult(
                data={
                    "questions": [
                        {
                            "candidate_id": self.context["anchors"][0]["candidate_id"],
                            "question_text": "Design a Kafka recovery scenario "
                            f"{len(self.context['history']) + i}. "
                            "Compare partition replay and failure recovery trade-offs.",
                        }
                        for i in range(self.context["count"])
                    ]
                },
                provider="fake",
                model="fixture",
                request_id="test",
            )
        data = {
            "questions": [
                copy.deepcopy(o["question"])
                for o in self.context["candidates"][: self.context["count"]]
            ]
        }
        if self.mode == "malformed":
            data = {"bad": "not a question set"}
        elif self.mode == "hallucination":
            data["questions"][0]["question_text"] = (
                "You implemented Kafka at Cisco. Explain your production system."
            )
        elif self.mode == "rationale":
            data["questions"][0]["rationale"] = "You are an expert Kafka engineer."
        elif self.mode == "metadata":
            data["questions"][0]["difficulty"] = "expert"
        elif self.mode == "duplicate":
            data["questions"] = data["questions"] * 2
        elif self.mode == "unavailable":
            raise ProviderUnavailable()
        elif self.mode == "timeout":
            raise TimeoutError()
        return LLMResult(data=data, provider="fake", model="fixture", request_id="test")


def test_catalog_metadata_and_retrieval(client):
    response = client.get("/api/v1/questions?limit=100").json()
    assert response["total"] == 36
    assert len({q["id"] for q in response["items"]}) == 36
    for q in response["items"]:
        assert q["expected_topics"] and q["tags"] and q["evaluation_focus"] and q["is_curated"]
        assert client.get("/api/v1/questions/" + q["id"]).json() == q
    assert client.get("/api/v1/questions/unknown").status_code == 404
    assert "Kafka" in client.get("/api/v1/questions/metadata").json()["skill"]


@pytest.mark.parametrize(
    "query,field,value",
    [
        ("category=Kafka", "category", "Kafka"),
        ("skill=Python", "skill", "Python"),
        ("difficulty=hard", "difficulty", "hard"),
        ("question_type=coding", "question_type", "coding"),
        ("source=curated", "source", "curated"),
        ("status=new", "status", "new"),
    ],
)
def test_filters(client, query, field, value):
    data = client.get("/api/v1/questions?" + query).json()
    assert data["items"] and all(q[field] == value for q in data["items"])


def test_search_tags_pagination(client):
    assert client.get("/api/v1/questions?search=MICRO-PARTITIONING").json()["total"] == 1
    assert client.get("/api/v1/questions?tag=partitions").json()["total"] == 1
    assert client.get("/api/v1/questions?search=impossible-nonsense").json()["total"] == 0
    assert len(client.get("/api/v1/questions?offset=34&limit=2").json()["items"]) == 2
    assert client.get("/api/v1/questions?limit=0").status_code == 422


def test_state_and_restart(settings):
    with TestClient(create_app(settings)) as c:
        identity = c.get("/api/v1/questions").json()["items"][0]["id"]
        assert (
            c.patch(
                "/api/v1/questions/" + identity, json={"status": "mastered", "bookmarked": True}
            ).status_code
            == 200
        )
        assert (
            c.patch(
                "/api/v1/questions/" + identity, json={"status": "expert", "bookmarked": True}
            ).status_code
            == 422
        )
    with TestClient(create_app(settings)) as c:
        assert (
            c.get("/api/v1/questions?saved=true&status=mastered").json()["items"][0]["id"]
            == identity
        )
        assert c.get("/api/v1/questions/stats").json()["saved"] == 1
        assert c.get("/api/v1/questions/stats").json()["statuses"]["mastered"] == 1


@pytest.mark.parametrize(
    "mode,status",
    [
        ("malformed", 422),
        ("hallucination", 422),
        ("rationale", 422),
        ("metadata", 422),
        ("duplicate", 422),
        ("unavailable", 503),
        ("timeout", 503),
    ],
)
def test_bad_generation_is_atomic(client, mode, status, caplog):
    target = prepare(client)
    client.app.state.question_llm = FakeQuestions(mode)
    response = client.post(
        "/api/v1/questions/generate", json={"target_id": target, "number_of_questions": 1}
    )
    assert response.status_code == status, response.text
    assert client.get("/api/v1/questions?source=generated").json()["total"] == 0
    assert "Cisco" not in caplog.text and "Test Candidate" not in caplog.text


def test_personalization_duplicate_and_evidence(client):
    target = prepare(client)
    fake = FakeQuestions()
    client.app.state.question_llm = fake
    with Session(client.app.state.engine) as session:
        options = candidates(session, GenerateInput(target_id=target))
    coverage = {o["question"]["skill"]: (o["evidence"]["coverage"], o["priority"]) for o in options}
    assert coverage["Kafka"][0] == "missing"
    assert coverage["Python"][0] == "partial"
    assert coverage["Snowflake"][0] == "strong"
    assert coverage["Kafka"][1] > coverage["Python"][1] > coverage["Snowflake"][1]
    body = {"target_id": target, "number_of_questions": 2, "category": "Kafka"}
    first = client.post("/api/v1/questions/generate", json=body)
    assert first.status_code == 200, first.text
    assert first.json()["created"] == 2
    again = client.post("/api/v1/questions/generate", json=body).json()
    assert again["created"] == 0 and again["reused"] == 2
    assert [q["id"] for q in again["items"]] == [q["id"] for q in first.json()["items"]]
    for question in again["items"]:
        source = question["source_reference"]["targets"][0]
        assert source["jd_claims"][0]["evidence"][0]["quote"] == "Kafka"
        assert source["resume_claims"] == [] and source["absence_check"]
        assert "prior experience is not assumed" in question["question_text"]
    assert "Test Candidate" not in json.dumps(fake.context)


@pytest.mark.parametrize("missing", ["resume", "jd"])
def test_missing_confirmed_context(client, missing):
    target_id = prepare(client)
    with Session(client.app.state.engine) as session:
        target = session.get(Target, target_id)
        a = session.get(Analysis, target.resume_id if missing == "resume" else target.jd_id)
        a.status = "draft"
        session.add(a)
        session.commit()
    client.app.state.question_llm = FakeQuestions()
    assert (
        client.post(
            "/api/v1/questions/generate", json={"target_id": target_id, "number_of_questions": 1}
        ).status_code
        == 422
    )


def test_invalid_target_disabled_and_limits(client):
    assert (
        client.post("/api/v1/questions/generate", json={"target_id": "unknown"}).status_code == 422
    )
    target = prepare(client)
    assert (
        client.post(
            "/api/v1/questions/generate", json={"target_id": target, "number_of_questions": 1}
        ).status_code
        == 503
    )
    client.app.state.question_llm = FakeQuestions()
    assert (
        client.post(
            "/api/v1/questions/generate", json={"target_id": target, "number_of_questions": 21}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/questions/generate",
            json={"target_id": target, "category": "Kafka", "number_of_questions": 20},
        ).status_code
        == 422
    )
    client.app.state.external_llm = True
    assert (
        client.post(
            "/api/v1/questions/generate", json={"target_id": target, "number_of_questions": 1}
        ).status_code
        == 422
    )


def test_generated_restart(settings):
    with TestClient(create_app(settings)) as client:
        target = prepare(client)
        client.app.state.question_llm = FakeQuestions()
        data = client.post(
            "/api/v1/questions/generate", json={"target_id": target, "number_of_questions": 1}
        ).json()
    with TestClient(create_app(settings)) as client:
        assert (
            client.get("/api/v1/questions?source=generated").json()["items"][0]["id"]
            == data["items"][0]["id"]
        )


def test_catalog_validation_and_version_rules(client, tmp_path):
    content = json.loads((ROOT / "content/question-bank.json").read_text())
    content["questions"][0]["difficulty"] = "impossible"
    with pytest.raises(ValidationError):
        Catalog.model_validate(content)
    shutil.copy(ROOT / "content/question-bank.json", tmp_path)
    content = json.loads((tmp_path / "question-bank.json").read_text())
    content["questions"][0]["question_text"] += " Changed?"
    (tmp_path / "question-bank.json").write_text(json.dumps(content))
    with pytest.raises(ValueError, match="version increment"):
        sync_catalog(client.app.state.engine, tmp_path)
    content["questions"][0]["version"] += 1
    (tmp_path / "question-bank.json").write_text(json.dumps(content))
    sync_catalog(client.app.state.engine, tmp_path)
    assert client.get("/api/v1/questions/curated:sql-window").json()["version"] == 2
    content["questions"].append(content["questions"][0])
    (tmp_path / "question-bank.json").write_text(json.dumps(content))
    with pytest.raises(ValueError, match="Duplicate"):
        sync_catalog(client.app.state.engine, tmp_path)


def test_normalization_and_constraint(client):
    assert normalized("  SQL\n  Joins ") == normalized("sql joins")
    from sqlalchemy.exc import IntegrityError

    with Session(client.app.state.engine) as session:
        question = session.exec(select(BankQuestion)).first()
        duplicate = BankQuestion(**question.model_dump(exclude={"id"}))
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            session.commit()


def test_preview_and_empty_context(client):
    target = prepare(client)
    body = {"target_id": target, "category": "Kafka"}
    preview = client.post("/api/v1/questions/generation-preview", json=body)
    assert preview.json() == {"available": 3, "topics": ["Kafka"]}
    assert client.get("/api/v1/questions?source=generated").json()["total"] == 0
    with Session(client.app.state.engine) as session:
        row = session.get(Target, target)
        analysis = session.get(Analysis, row.resume_id)
        analysis.claims = []
        session.add(analysis)
        session.commit()
    assert client.post("/api/v1/questions/generation-preview", json=body).status_code == 422


def test_source_revalidated_instead_of_trusting_snapshot(client):
    target = prepare(client)
    with Session(client.app.state.engine) as session:
        row = session.get(Target, target)
        row.result = {"items": [{"topic": "Kafka", "status": "strong"}]}
        session.add(row)
        session.commit()
        options = candidates(session, GenerateInput(target_id=target, category="Kafka"))
        assert all(o["evidence"]["coverage"] == "missing" for o in options)


def test_java_spark_does_not_imply_pyspark_experience(client):
    ids = []
    for kind, text in [
        ("resume", "Candidate\nEXPERIENCE\n- Built Apache Spark jobs using Java."),
        ("jd", "Must have\nPySpark"),
    ]:
        a = client.post("/api/v1/documents/text", json={"kind": kind, "text": text}).json()[
            "analyses"
        ][0]
        client.post("/api/v1/analyses/" + a["id"] + "/confirm", json={"revision": a["revision"]})
        ids.append(a["id"])
    target = client.post("/api/v1/targets", json={"resume_id": ids[0], "jd_id": ids[1]}).json()[
        "id"
    ]
    client.app.state.question_llm = FakeQuestions()
    response = client.post(
        "/api/v1/questions/generate",
        json={
            "target_id": target,
            "category": "PySpark",
            "difficulty": "medium",
            "number_of_questions": 1,
        },
    )
    assert response.status_code == 200
    q = response.json()["items"][0]
    assert "hypothetical migration" in q["question_text"]
    assert q["source_reference"]["targets"][0]["coverage"] == "missing"
    assert q["source_reference"]["targets"][0]["resume_claims"] == []


def test_needs_review_boost_is_deterministic(client):
    target = prepare(client)
    client.app.state.question_llm = FakeQuestions()
    q = client.post(
        "/api/v1/questions/generate",
        json={"target_id": target, "category": "Kafka", "number_of_questions": 1},
    ).json()["items"][0]
    before = q["source_reference"]["targets"][0]["priority"]
    client.patch(
        "/api/v1/questions/" + q["id"], json={"status": "needs_review", "bookmarked": False}
    )
    with Session(client.app.state.engine) as session:
        options = candidates(session, GenerateInput(target_id=target, category="Kafka"))
        assert options[0]["priority"] == before + 2


def test_m3_migration_preserves_analyzer(settings):
    from alembic import command

    from app.db import migration_config

    with TestClient(create_app(settings)) as client:
        target = prepare(client)
    config = migration_config(settings)
    command.downgrade(config, "0002")
    command.upgrade(config, "head")
    command.check(config)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/targets").json()[0]["id"] == target
        assert client.get("/api/v1/questions/stats").json()["curated"] == 36


@pytest.mark.parametrize("mode", ["valid", "malformed", "refusal", "http_error"])
def test_provider_transport(mode):
    def handler(request):
        body = json.loads(request.content)
        assert body["store"] is False
        assert body["text"]["format"]["strict"] is True
        if mode == "http_error":
            return httpx.Response(429)
        return httpx.Response(
            200,
            json={
                "id": "fixture",
                "status": "completed",
                "output": [
                    {
                        "content": [
                            {
                                "type": "refusal" if mode == "refusal" else "output_text",
                                "text": "{broken" if mode == "malformed" else '{"questions": []}',
                            }
                        ]
                    }
                ],
            },
        )

    settings = Settings(llm_api_key="test-secret", llm_model="fixture-model", _env_file=None)
    provider = OpenAIProvider(settings, httpx.MockTransport(handler))
    request = LLMRequest(
        task="question_generation", instructions="test", context="test", output_schema={}
    )
    if mode == "valid":
        assert asyncio.run(provider.generate_structured(request)).data == {"questions": []}
    else:
        with pytest.raises(ProviderUnavailable if mode == "http_error" else ValueError):
            asyncio.run(provider.generate_structured(request))
