import base64

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app

PASSWORD = "synthetic-deployment-password"


def hosted(**overrides):
    return Settings(
        llm_provider="disabled",
        _env_file=None,
        public_url="https://practice.example.com",
        access_password=PASSWORD,
        **overrides,
    )


def test_public_configuration_refuses_unsafe_storage_or_missing_password():
    with pytest.raises(ValidationError):
        hosted(storage_mode="local_sqlite")
    with pytest.raises(ValidationError):
        Settings(public_url="https://practice.example.com", _env_file=None)
    with pytest.raises(ValidationError):
        Settings(public_url="http://practice.example.com", access_password=PASSWORD, _env_file=None)


def test_hosted_app_access_origin_and_device_gateway(tmp_path, monkeypatch):
    frontend = tmp_path / "frontend/dist"
    frontend.mkdir(parents=True)
    (frontend / "index.html").write_text("<html><body>Interview War Room</body></html>")
    (frontend / "bundle.js").write_text("window.hostingTest = true;")
    monkeypatch.setattr("app.hosting.ROOT", tmp_path)
    with TestClient(
        create_app(hosted(serve_frontend=True)), base_url="https://practice.example.com"
    ) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert 'action="/auth/login"' in client.get("/").text
        assert client.get("/").headers["referrer-policy"] == "same-origin"
        for path in ["/bundle.js", "/api/v1/storage", "/api/v1/ai/status"]:
            denied = client.get(path)
            assert denied.status_code == 401
            assert denied.headers["www-authenticate"].startswith("Basic ")
        assert 'action="/auth/login"' in client.get("/", auth=("warroom", "wrong")).text
        client.auth = ("warroom", PASSWORD)
        home = client.get("/")
        assert home.status_code == 200 and "Interview War Room" in home.text
        assert home.headers["x-frame-options"] == "DENY"
        assert client.get("/bundle.js").status_code == 200
        assert client.get("/api/v1/storage").json()["mode"] == "browser"
        assert client.get("/api/v1/documents").status_code == 403
        response = client.post(
            "/api/v1/device",
            json={"path": "/api/v1/profile"},
            headers={"origin": "https://practice.example.com"},
        )
        assert response.status_code == 200
        assert response.json()["result"]["name"] == ""
        assert PASSWORD not in response.text
        assert (
            client.post(
                "/api/v1/device",
                json={"path": "/api/v1/profile"},
                headers={"origin": "https://evil.example"},
            ).status_code
            == 403
        )
        assert client.get("/", headers={"host": "evil.example"}).status_code == 400


def test_malformed_access_credentials_fail_closed():
    with TestClient(create_app(hosted())) as client:
        for header in [
            "Basic !!!",
            "Bearer wrong",
            "Basic " + base64.b64encode("\u00e9:secret".encode()).decode(),
        ]:
            assert (
                client.get("/api/v1/storage", headers={"authorization": header}).status_code == 401
            )


def test_browser_login_cookie_and_rejected_credentials():
    with TestClient(create_app(hosted()), base_url="https://practice.example.com") as client:
        headers = {"origin": "https://practice.example.com"}
        assert client.post("/auth/login", data={"password": PASSWORD}).status_code == 403
        wrong = client.post("/auth/login", data={"password": "wrong"}, headers=headers)
        assert wrong.status_code == 401 and "Incorrect password" in wrong.text
        response = client.post(
            "/auth/login", data={"password": PASSWORD}, headers=headers, follow_redirects=False
        )
        assert response.status_code == 303
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
        assert PASSWORD not in cookie
        assert client.get("/api/v1/storage").status_code == 200
        assert (
            client.post(
                "/api/v1/device", json={"path": "/api/v1/profile"}, headers=headers
            ).status_code
            == 200
        )
        client.cookies.clear()
        client.cookies.set("warroom_access", "123.invalid")
        assert client.get("/api/v1/storage").status_code == 401


def test_expired_session_and_password_rotation():
    from app.hosting import session_token, valid_session

    assert not valid_session(session_token(PASSWORD, 1), PASSWORD)
    assert not valid_session(session_token(PASSWORD), "changed-password")
    assert not valid_session("bad", PASSWORD)
