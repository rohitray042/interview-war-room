"""Same-origin hosting and a shared access gate for a personal deployment."""

import base64
import hmac
from urllib.parse import urlsplit

from fastapi.staticfiles import StaticFiles

from app.config import ROOT


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
