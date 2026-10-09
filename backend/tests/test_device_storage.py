import base64
import copy
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from test_interviews import FakeInterview, act, evaluate, start, submit
from test_questions import FakeQuestions, prepare

from app.config import Settings
from app.main import create_app
from app.models import Document


class Browser:
    def __init__(self, client, workspace=None):
        self.client, self.workspace = client, workspace

    def request(self, method, path, **kwargs):
        outbound = httpx.Request(method, "http://localhost" + path, **kwargs)
        result = self.client.post(
            "/api/v1/device",
            json={
                "path": path,
                "method": method,
                "workspace": self.workspace,
                "body": base64.b64encode(outbound.read()).decode(),
                "content_type": outbound.headers.get("content-type", "application/json"),
            },
        )
        assert result.status_code == 200, result.text
        envelope = result.json()
        self.workspace = envelope["workspace"]
        return httpx.Response(envelope["status"], json=envelope["result"])

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)


@pytest.fixture
def device_settings(tmp_path):
    return Settings(
        database_path=tmp_path / "must-not-exist.db",
        storage_mode="browser",
        llm_provider="disabled",
        _env_file=None,
    )


def test_devices_are_isolated_and_legacy_database_is_not_opened(device_settings):
    device_settings.resolved_database_path.write_bytes(b"Existing private database untouched")
    with TestClient(create_app(device_settings)) as client:
        a, b = Browser(client), Browser(client)
        uploaded = a.post(
            "/api/v1/documents/text",
            json={
                "kind": "resume",
                "text": "Alice Private\nSKILLS\nSQL",
                "filename": "alice.txt",
            },
        ).json()
        identity = uploaded["document"]["id"]
        assert b.get("/api/v1/documents").json() == []
        assert b.get("/api/v1/documents/" + identity).status_code == 404
        assert "Alice Private" in a.get("/api/v1/documents/" + identity).text
        assert client.get("/api/v1/documents").status_code == 403
        assert client.get("/api/v1/documents/" + identity).status_code == 403
        with Session(client.app.state.engine) as db:
            assert db.exec(select(Document)).all() == []
    assert (
        device_settings.resolved_database_path.read_bytes()
        == b"Existing private database untouched"
    )


def test_uploaded_file_and_restart_persistence(device_settings):
    with TestClient(create_app(device_settings)) as client:
        browser = Browser(client)
        uploaded = browser.post(
            "/api/v1/documents/upload",
            data={"kind": "resume"},
            files={
                "file": ("private.txt", b"Private Candidate\nSKILLS\nSQL", "text/plain"),
            },
        )
        assert uploaded.status_code == 200
        backup = browser.workspace
    with TestClient(create_app(device_settings)) as restarted:
        assert (
            Browser(restarted, backup).get("/api/v1/documents").json()[0]["filename"]
            == "private.txt"
        )
        assert Browser(restarted).get("/api/v1/documents").json() == []
    assert not device_settings.resolved_database_path.exists()


def test_full_target_interview_evaluation_and_followups(device_settings):
    provider = FakeInterview("follow")
    with TestClient(create_app(device_settings, FakeQuestions(), provider)) as client:
        browser = Browser(client)
        target = prepare(browser)
        state = start(browser, target_id=target)
        other = Browser(client)
        assert other.get("/api/v1/interviews/" + state["id"]).status_code == 404
        for depth in range(3):
            state = submit(browser, state)
            state = evaluate(browser, state)
            assert state["current_turn"]["evaluation"]["score"] == 5.0
            assert state["current_turn"]["follow_up_depth"] == depth
            state = act(browser, state, "next")
        assert state["status"] == "completed"
        result = browser.get(f"/api/v1/interviews/{state['id']}/summary")
        assert result.status_code == 200
        assert browser.get("/api/v1/interviews/stats").json()["answers"] == 3
        assert other.get("/api/v1/interviews/stats").json()["answers"] == 0
        assert browser.get("/api/v1/weaknesses").status_code == 200
        assert provider.context["source_context"]


def test_concurrent_device_requests_do_not_cross_context(device_settings):
    with TestClient(create_app(device_settings)) as client:

        def work(name):
            browser = Browser(client)
            browser.post(
                "/api/v1/documents/text",
                json={
                    "kind": "resume",
                    "text": name + "\nSKILLS\nSQL",
                    "filename": name + ".txt",
                },
            )
            return browser.get("/api/v1/documents").json()

        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = list(pool.map(work, ["Alice", "Bob"]))
        assert [d["filename"] for d in a] == ["Alice.txt"]
        assert [d["filename"] for d in b] == ["Bob.txt"]


@pytest.mark.parametrize("mutation", ["unknown_table", "unknown_field", "broken_fk", "version"])
def test_invalid_snapshots_are_rejected(device_settings, mutation):
    with TestClient(create_app(device_settings)) as client:
        browser = Browser(client)
        prepare(browser)
        bad = copy.deepcopy(browser.workspace)
        if mutation == "unknown_table":
            bad["tables"]["arbitrary_sql"] = []
        elif mutation == "unknown_field":
            bad["tables"]["profiles"][0]["unexpected"] = "private-secret"
        elif mutation == "broken_fk":
            bad["tables"]["analyses"][0]["document_id"] = "other-device-document"
        else:
            bad["version"] = 999
        response = client.post("/api/v1/device", json={"workspace": bad, "path": "/api/v1/profile"})
        assert response.status_code == 422
        assert "private-secret" not in response.text
        assert len(browser.get("/api/v1/documents").json()) == 2


@pytest.mark.parametrize(
    "path", ["/api/v1/device", "https://evil.test/api/v1/profile", "/api/v1/../device"]
)
def test_gateway_cannot_recurse_or_forward_external_requests(device_settings, path):
    with TestClient(create_app(device_settings)) as client:
        assert client.post("/api/v1/device", json={"path": path}).status_code == 422


def test_private_text_not_logged_and_origin_guard(device_settings, caplog):
    with TestClient(create_app(device_settings)) as client:
        browser = Browser(client)
        browser.post(
            "/api/v1/documents/text", json={"kind": "resume", "text": "SECRET-CANDIDATE\nSQL"}
        )
        assert "SECRET-CANDIDATE" not in caplog.text
        assert (
            client.post(
                "/api/v1/device",
                headers={"origin": "https://evil.test"},
                json={
                    "path": "/api/v1/profile",
                    "workspace": browser.workspace,
                },
            ).status_code
            == 403
        )
        assert "SECRET-CANDIDATE" not in json.dumps(Browser(client).get("/api/v1/profile").json())


def test_large_upload_does_not_spool_to_disk(device_settings, monkeypatch):
    def forbidden_rollover(_):
        raise AssertionError("Browser uploads must not spill onto disk")

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "rollover", forbidden_rollover)
    with TestClient(create_app(device_settings)) as client:
        browser = Browser(client)
        response = browser.post(
            "/api/v1/documents/upload",
            data={"kind": "resume"},
            files={"file": ("large.txt", b"x" * (1024 * 1024 + 1), "text/plain")},
        )
        assert response.status_code == 413  # Existing extracted-text limit, no disk spill.
        assert browser.get("/api/v1/documents").json() == []


def test_external_ai_consent_and_context_isolation(device_settings):
    provider = FakeInterview()
    with TestClient(create_app(device_settings, interview_provider=provider)) as client:
        client.app.state.external_llm = True
        browser = Browser(client)
        browser.post(
            "/api/v1/documents/text",
            json={
                "kind": "resume",
                "text": "UNRELATED PRIVATE RESUME\nSQL",
            },
        )
        state = submit(browser, start(browser))
        path = f"/api/v1/interviews/{state['id']}/turns/{state['current_turn']['id']}/evaluate"
        assert browser.post(path, json={}).status_code == 422
        assert provider.calls == 0
        assert browser.post(path, json={"allow_external_processing": True}).status_code == 200
        assert provider.calls == 1
        assert "UNRELATED PRIVATE RESUME" not in json.dumps(provider.context)
