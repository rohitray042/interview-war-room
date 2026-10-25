import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.cloud import ACCESS, COOKIE_PATH, REFRESH
from app.config import Settings
from app.main import create_app

ORIGIN = "https://practice.example.com"
HEADERS = {"origin": ORIGIN, "x-workspace-user": "user-a"}
PASSWORD = "synthetic-test-password"


class SupabaseFake:
    def __init__(self):
        self.rows = {}
        self.deleted = set()
        self.calls = []
        self.conflict = False
        self.drafts = {}

    def handle(self, request):
        path = request.url.path
        self.calls.append(request)
        token = request.headers.get("authorization", "Bearer ").removeprefix("Bearer ")
        identity = token if token in {"user-a", "user-b"} else None
        body = json.loads(request.content) if request.content else {}
        if path == "/auth/v1/token":
            if "refresh_token" in body:
                identity = (
                    body["refresh_token"] if body["refresh_token"] in {"user-a", "user-b"} else None
                )
            elif body.get("password") == PASSWORD:
                identity = "user-a" if body["email"] == "a@example.com" else "user-b"
            else:
                return httpx.Response(400, json={"error": "invalid"})
            if identity:
                return httpx.Response(
                    200,
                    json={
                        "access_token": identity,
                        "refresh_token": identity,
                        "expires_in": 3600,
                        "user": {"id": identity, "email_confirmed_at": "yes"},
                    },
                )
        if path == "/auth/v1/verify" and body.get("token") == "123456":
            return httpx.Response(
                200, json={"access_token": "user-a", "refresh_token": "user-a", "expires_in": 3600}
            )
        if path == "/auth/v1/user" and identity and identity not in self.deleted:
            return httpx.Response(
                200,
                json={
                    "id": identity,
                    "email": identity[-1] + "@example.com",
                    "email_confirmed_at": "yes",
                },
            )
        if path == "/auth/v1/logout":
            return httpx.Response(204)
        if path in {"/auth/v1/signup", "/auth/v1/recover"}:
            return httpx.Response(200, json={})
        if path == "/rest/v1/account_workspaces" and identity:
            assert request.url.params["user_id"] == "eq." + identity
            return httpx.Response(200, json=[self.rows[identity]] if identity in self.rows else [])
        if path == "/rest/v1/rpc/save_account_workspace" and identity:
            revision = self.rows.get(identity, {}).get("revision", 0)
            if self.conflict or revision != body["expected_revision"]:
                return httpx.Response(400, json={"code": "P0001"})
            self.rows[identity] = {"workspace": body["payload"], "revision": revision + 1}
            return httpx.Response(200, json=revision + 1)
        if path == "/rest/v1/rpc/delete_own_account" and identity:
            self.deleted.add(identity)
            self.rows.pop(identity, None)
            return httpx.Response(204)
        if path == "/rest/v1/account_drafts" and identity:
            assert request.url.params["user_id"] == "eq." + identity
            key = (identity, request.url.params["turn_id"])
            return httpx.Response(200, json=[self.drafts[key]] if key in self.drafts else [])
        if path == "/rest/v1/rpc/save_account_draft" and identity:
            key = (identity, "eq." + body["turn"])
            revision = self.drafts.get(key, {}).get("revision", 0)
            if revision != body["expected_revision"]:
                return httpx.Response(400, json={"code": "P0001"})
            self.drafts[key] = {"answer": body["answer_text"], "revision": revision + 1}
            return httpx.Response(200, json=revision + 1)
        return httpx.Response(401, json={"error": "private-provider-error"})


@pytest.fixture
def cloud_app():
    settings = Settings(
        _env_file=None,
        llm_provider="disabled",
        public_access=True,
        public_url=ORIGIN,
        supabase_url="https://synthetic.supabase.co",
        supabase_anon_key="synthetic-publishable-key",
    )
    app = create_app(settings)
    fake = SupabaseFake()
    app.state.cloud.transport = httpx.MockTransport(fake.handle)
    with TestClient(app, base_url=ORIGIN) as client:
        yield client, fake


def login(client, email="a@example.com"):
    response = client.post(
        "/api/v1/cloud/login",
        headers={"origin": ORIGIN},
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response


def operation(client, path="/api/v1/profile", headers=HEADERS):
    return client.post("/api/v1/cloud/operation", headers=headers, json={"path": path})


def test_optional_guest_mode_and_no_cloud_recursion(cloud_app):
    client, _ = cloud_app
    assert client.get("/api/v1/cloud/session").json() == {"enabled": True, "user": None}
    assert operation(client).status_code == 401
    guest = client.post(
        "/api/v1/device", headers={"origin": ORIGIN}, json={"path": "/api/v1/profile"}
    )
    assert guest.status_code == 200
    attack = client.post(
        "/api/v1/device", headers={"origin": ORIGIN}, json={"path": "/api/v1/cloud/workspace"}
    )
    assert attack.status_code == 422


def test_auth_cookies_origin_and_errors(cloud_app):
    client, _ = cloud_app
    body = {"email": "a@example.com", "password": PASSWORD}
    assert client.post("/api/v1/cloud/login", json=body).status_code == 403
    assert (
        client.post(
            "/api/v1/cloud/login", headers={"origin": "https://evil.example"}, json=body
        ).status_code
        == 403
    )
    bad = client.post(
        "/api/v1/cloud/login", headers=HEADERS, json={**body, "password": "bad-password-123"}
    )
    assert bad.status_code == 401 and "private-provider-error" not in bad.text
    response = login(client)
    assert "access_token" not in response.text and PASSWORD not in response.text
    for cookie in response.headers.get_list("set-cookie"):
        assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
        assert "Path=" + COOKIE_PATH in cookie
    assert client.get("/api/v1/cloud/session").json()["user"]["id"] == "user-a"
    assert operation(client, headers={**HEADERS, "x-workspace-user": "user-b"}).status_code == 409


def test_cloud_persistence_guest_import_and_two_user_isolation(cloud_app):
    client, fake = cloud_app
    guest = client.post(
        "/api/v1/device", headers={"origin": ORIGIN}, json={"path": "/api/v1/profile"}
    ).json()["workspace"]
    guest["tables"]["profiles"][0]["name"] = "Private candidate A"
    login(client)
    imported = client.post(
        "/api/v1/cloud/workspace", headers=HEADERS, json={"workspace": guest, "revision": 0}
    )
    assert imported.status_code == 200
    assert operation(client).json()["result"]["name"] == "Private candidate A"
    assert (
        client.post(
            "/api/v1/cloud/workspace", headers=HEADERS, json={"workspace": guest, "revision": 0}
        ).status_code
        == 409
    )
    assert client.post("/api/v1/cloud/logout", headers=HEADERS, json={}).status_code == 200
    assert operation(client).status_code == 401
    login(client, "b@example.com")
    b = operation(client, headers={**HEADERS, "x-workspace-user": "user-b"})
    assert b.status_code == 200 and b.json()["result"]["name"] == ""
    assert "Private candidate A" not in b.text
    login(client)
    assert operation(client).json()["result"]["name"] == "Private candidate A"
    fake.conflict = True
    assert (
        client.post(
            "/api/v1/cloud/workspace", headers=HEADERS, json={"workspace": guest, "revision": 1}
        ).status_code
        == 409
    )


def test_refresh_expiry_delete_and_invalid_backup(cloud_app):
    client, fake = cloud_app
    login(client)
    client.cookies.delete(ACCESS, domain="practice.example.com", path=COOKIE_PATH)
    assert client.get("/api/v1/cloud/session").json()["user"]["id"] == "user-a"
    assert (
        client.post(
            "/api/v1/cloud/workspace",
            headers=HEADERS,
            json={"workspace": {"tables": {}}, "revision": 0},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/cloud/delete-account",
            headers=HEADERS,
            json={"email": "b@example.com", "password": PASSWORD},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/cloud/delete-account",
            headers=HEADERS,
            json={"email": "a@example.com", "password": PASSWORD},
        ).status_code
        == 200
    )
    assert "user-a" in fake.deleted
    assert operation(client).status_code == 401
    client.cookies.set(REFRESH, "invalid", domain="practice.example.com", path=COOKIE_PATH)
    result = client.get("/api/v1/cloud/session")
    assert result.status_code == 200 and result.json()["expired"] is True


def test_account_attempt_throttle(cloud_app):
    client, _ = cloud_app
    for _ in range(10):
        result = client.post(
            "/api/v1/cloud/recover", headers=HEADERS, json={"email": "a@example.com"}
        )
        assert result.status_code == 200
    assert (
        client.post(
            "/api/v1/cloud/recover", headers=HEADERS, json={"email": "a@example.com"}
        ).status_code
        == 429
    )


def test_cloud_mutation_revisions_and_draft_isolation(cloud_app):
    client, _ = cloud_app
    login(client)
    assert operation(client).json()["revision"] == 0
    profile = operation(client).json()["result"]
    for metadata in ("id", "singleton_key", "created_at", "updated_at"):
        profile.pop(metadata)
    profile["name"] = "Synced account"
    body = {
        "path": "/api/v1/profile",
        "method": "PUT",
        "expected_revision": 0,
        "body": base64.b64encode(json.dumps(profile).encode()).decode(),
    }
    saved = client.post("/api/v1/cloud/operation", headers=HEADERS, json=body)
    assert saved.status_code == 200 and saved.json()["revision"] == 1
    assert saved.json()["status"] == 200
    assert client.post("/api/v1/cloud/operation", headers=HEADERS, json=body).status_code == 409
    assert operation(client).json()["result"]["name"] == "Synced account"
    turn = "00000000-0000-0000-0000-000000000001"
    draft = {"turn_id": turn, "answer": "Private answer draft", "revision": 0}
    assert client.post("/api/v1/cloud/draft", headers=HEADERS, json=draft).status_code == 200
    assert client.post("/api/v1/cloud/draft", headers=HEADERS, json=draft).status_code == 409
    assert client.get("/api/v1/cloud/draft/" + turn).json()["answer"] == draft["answer"]
    login(client, "b@example.com")
    assert client.get("/api/v1/cloud/draft/" + turn).json()["answer"] == ""


def test_email_verification_and_password_recovery(cloud_app):
    client, _ = cloud_app
    assert (
        client.post(
            "/api/v1/cloud/signup",
            headers=HEADERS,
            json={"email": "a@example.com", "password": PASSWORD},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/cloud/verify",
            headers=HEADERS,
            json={"email": "a@example.com", "token": "123456", "type": "recovery"},
        ).status_code
        == 422
    )
    verified = client.post(
        "/api/v1/cloud/verify",
        headers=HEADERS,
        json={"email": "a@example.com", "token": "123456", "type": "signup"},
    )
    assert verified.status_code == 200 and "access_token" not in verified.text
    reset = client.post(
        "/api/v1/cloud/verify",
        headers=HEADERS,
        json={
            "email": "a@example.com",
            "token": "123456",
            "type": "recovery",
            "password": PASSWORD,
        },
    )
    assert reset.status_code == 200
