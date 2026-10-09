"""Same-origin hosting and a shared access gate for a personal deployment."""

import base64
import hashlib
import hmac
import time
from urllib.parse import urlsplit

from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import ROOT

COOKIE = "warroom_access"


def session_token(password, expires=None):
    expiry = str(expires if expires is not None else int(time.time()) + 86400)
    signature = hmac.new(
        password.encode(), ("browser-session:" + expiry).encode(), hashlib.sha256
    ).hexdigest()
    return expiry + "." + signature


def valid_session(token, password):
    if not password or not token:
        return False
    try:
        expiry = int(token.split(".", 1)[0])
        return int(time.time()) < expiry <= int(time.time()) + 86400 and hmac.compare_digest(
            token, session_token(password, expiry)
        )
    except ValueError, TypeError:
        return False


def login_page(failed=False):
    error = "Incorrect password. Try again." if failed else ""
    return HTMLResponse(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Interview War Room</title><style>"
        "body{font:16px system-ui;margin:0;padding:24px;color:#171717;background:#fafafa}"
        "main{max-width:400px;margin:12vh auto}h1{font-size:28px}"
        "input,button{box-sizing:border-box;width:100%;padding:14px;margin:12px 0;font:inherit}"
        "button{background:#171717;color:white;border:0;cursor:pointer}"
        "</style><main><h1>Interview War Room</h1>"
        '<form method="post" action="/auth/login">'
        '<label for="password">Workspace access password</label>'
        '<input id="password" name="password" type="password" '
        'autocomplete="current-password" required maxlength="1024">'
        '<button type="submit">Open workspace</button><p role="alert">'
        + error
        + "</p></form></main></html>",
        status_code=401 if failed else 200,
        headers={
            "Cache-Control": "no-store",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; "
                "form-action 'self'; frame-ancestors 'none'"
            ),
        },
    )


def hosting_origins(settings):
    origins = {
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
    }
    hosts = {"127.0.0.1", "localhost", "testserver"}
    if settings.public_url:
        origins.add(settings.public_url)
        hosts.add(urlsplit(settings.public_url).hostname)
    return sorted(hosts), sorted(origins)


def authorized(header, password):
    if not password:
        return True
    try:
        scheme, encoded = header.split(" ", 1)
        if scheme.lower() != "basic":
            return False
        username, supplied = base64.b64decode(encoded, validate=True).decode().split(":", 1)
        return hmac.compare_digest(username.encode(), b"warroom") and hmac.compare_digest(
            supplied.encode(), password.encode()
        )
    except ValueError, UnicodeError:
        return False


def mount_frontend(app, settings):
    if settings.serve_frontend:
        app.mount("/", StaticFiles(directory=ROOT / "frontend/dist", html=True), name="frontend")
