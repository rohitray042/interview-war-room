"""Explicit opt-in live verification; never collected by pytest."""

import argparse
import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from alembic import command
from fastapi.testclient import TestClient

from app.config import Settings
from app.contracts import DisabledProvider
from app.db import migration_config
from app.main import create_app
from app.providers import make_provider


class SafeCapture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []
        self.usage = []

    def emit(self, record):
        message = record.getMessage()
        self.messages.append(message)
        if record.name == "war_room.ai":
            self.usage.append(json.loads(message))


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-live", action="store_true")
    if not parser.parse_args().allow_live:
        raise SystemExit("Requires --allow-live. This makes billable API requests.")
    settings = Settings()
    provider = make_provider(settings)
    if isinstance(provider, DisabledProvider):
        raise SystemExit("Live provider is not configured.")
    key = provider.settings.llm_api_key.get_secret_value()
    capture = SafeCapture()
    logging.getLogger().addHandler(capture)
    report = {"data": "synthetic isolated smoke", "passed": False}
    with TemporaryDirectory(prefix="war-room-live-smoke-") as directory:
        # This historical smoke verifies the optional local SQLite installation.
        settings.storage_mode = "local_sqlite"
        settings.database_path = Path(directory) / "smoke.db"
        command.upgrade(migration_config(settings), "head")
        with TestClient(create_app(settings)) as client:

            def call(method, path, payload=None):
                response = client.request(method, "/api/v1" + path, json=payload)
                assert key not in response.text, "Secret exposed in API response"
                if response.status_code != 200:
                    raise RuntimeError(f"Smoke step {path} failed: HTTP {response.status_code}")
                return response.json()

            analyses = []
            for kind, source in [
                (
                    "resume",
                    "Synthetic Smoke Candidate\nSKILLS\nPython\nEXPERIENCE\n"
                    "- Built Python pipelines.",
                ),
                ("jd", "Must have\nKafka\nPython"),
            ]:
                bundle = call("POST", "/documents/text", {"kind": kind, "text": source})
                analysis = bundle["analyses"][0]
                call(
                    "POST",
                    f"/analyses/{analysis['id']}/confirm",
                    {"revision": analysis["revision"]},
                )
                analyses.append(analysis["id"])
            target = call("POST", "/targets", {"resume_id": analyses[0], "jd_id": analyses[1]})
            generated = call(
                "POST",
                "/questions/generate",
                {
                    "target_id": target["id"],
                    "category": "Kafka",
                    "number_of_questions": 1,
                    "allow_external_processing": True,
                },
            )
            assert len(generated["items"]) == 1
            assert call("GET", "/ai/status")["status"] == "connected"
            report["generated_questions"] = 1
            state = call(
                "POST",
                "/interviews",
                {
                    "request_id": str(uuid4()),
                    "target_id": target["id"],
                    "category": "Kafka",
                    "number_of_questions": 1,
                    "source": "personalized",
                    "allow_external_processing": True,
                },
            )
            identity = state["id"]

            def action(state, name):
                return call(
                    "POST",
                    f"/interviews/{identity}/actions",
                    {"revision": state["revision"], "action": name},
                )

            state = action(state, "start")
            for _ in range(3):
                turn = state["current_turn"]["id"]
                state = call(
                    "POST",
                    f"/interviews/{identity}/turns/{turn}/answer",
                    {
                        "revision": state["revision"],
                        "submission_id": str(uuid4()),
                        "answer_text": "I would use a Kafka topic and a consumer. "
                        "I cannot yet explain recovery or delivery guarantees.",
                    },
                )
                state = call(
                    "POST",
                    f"/interviews/{identity}/turns/{turn}/evaluate",
                    {"allow_external_processing": True},
                )
                if state["current_turn"]["evaluation_state"] != "succeeded":
                    raise RuntimeError(
                        "Live evaluation failed validation or availability; "
                        "saved answer retained in isolated DB until cleanup."
                    )
                state = action(state, "finish" if state["next_action"] == "finish" else "next")
                if state["status"] == "completed":
                    break
            assert state["status"] == "completed"
            summary = call("GET", f"/interviews/{identity}/summary")
            learning = call("GET", "/weaknesses")
            assert learning["items"], "No validated learning evidence"
            report.update(
                {
                    "answers": summary["answers_submitted"],
                    "follow_ups": summary["follow_ups"],
                    "learning_topics": len(learning["items"]),
                    "passed": True,
                }
            )
        with TestClient(create_app(settings)) as client:
            assert client.get(f"/api/v1/interviews/{identity}").json()["status"] == "completed"
            report["restart_persistence"] = True
    assert all(key not in message for message in capture.messages), "Secret exposed in logs"
    report["usage"] = capture.usage
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        # Never print exception bodies that could contain provider/user payloads.
        print(json.dumps({"passed": False, "error_type": type(exc).__name__}))
        raise SystemExit(1) from None
