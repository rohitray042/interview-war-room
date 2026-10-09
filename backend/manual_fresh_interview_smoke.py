"""Opt-in Gemini smoke: synthetic general-practice session held only in memory."""

import argparse
import base64
import json
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-live", action="store_true")
    if not parser.parse_args().allow_live:
        raise SystemExit("Requires --allow-live; uses Gemini API quota.")
    settings = Settings()
    if settings.llm_provider != "gemini":
        raise SystemExit("This smoke is restricted to the configured Gemini provider.")
    settings.storage_mode = "browser"
    settings.serve_frontend = False
    workspace = None
    with TestClient(create_app(settings)) as client:

        def call(method, path, body=None):
            nonlocal workspace
            result = client.post(
                "/api/v1/device",
                json={
                    "path": "/api/v1" + path,
                    "method": method,
                    "workspace": workspace,
                    "body": base64.b64encode(json.dumps(body).encode()).decode()
                    if body is not None
                    else "",
                },
            )
            if result.status_code != 200 or result.json()["status"] != 200:
                raise RuntimeError("Fresh interview smoke request failed")
            data = result.json()
            workspace = data["workspace"]
            return data["result"]

        state = call(
            "POST",
            "/interviews",
            {
                "request_id": str(uuid4()),
                "source": "ai_generated",
                "category": "Snowflake",
                "difficulty": "easy",
                "question_type": "conceptual",
                "number_of_questions": 1,
                "allow_external_processing": True,
            },
        )
        url = "/interviews/" + state["id"]
        state = call("POST", url + "/actions", {"revision": state["revision"], "action": "start"})
        turn_url = url + "/turns/" + state["current_turn"]["id"]
        state = call(
            "POST",
            turn_url + "/answer",
            {
                "revision": state["revision"],
                "submission_id": str(uuid4()),
                "answer_text": "A Snowflake virtual warehouse provides compute. Auto-suspend stops "
                "idle compute consumption. Storage remains separate. I would measure query latency "
                "and credit usage before adjusting warehouse size.",
            },
        )
        state = call("POST", turn_url + "/evaluate", {"allow_external_processing": True})
        if state["current_turn"]["evaluation_state"] != "succeeded":
            raise RuntimeError("Live evaluation did not pass validation")
        restored = call("GET", url)
        assert restored["current_turn"]["answer_text"] == state["current_turn"]["answer_text"]
        print(
            json.dumps(
                {
                    "passed": True,
                    "provider": "gemini",
                    "data": "synthetic in-memory workspace",
                    "fresh_question": True,
                    "evaluation": True,
                    "saved_answer_roundtrip": True,
                    "next_action": state["next_action"],
                }
            )
        )


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(json.dumps({"passed": False, "error_type": type(exc).__name__}))
        raise SystemExit(1) from None
