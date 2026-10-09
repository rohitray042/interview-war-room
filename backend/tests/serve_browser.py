"""Isolated real API for browser tests. Never opens the personal database."""

import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from alembic import command

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from persisted_data import copy_database  # noqa: E402
from test_interviews import FakeInterview  # noqa: E402
from test_questions import FakeQuestions  # noqa: E402

from app.config import Settings  # noqa: E402
from app.db import migration_config  # noqa: E402
from app.main import create_app  # noqa: E402


class BrowserInterview(FakeInterview):
    async def generate_structured(self, request):
        if json.loads(request.context)["answer"].startswith("[verification:strong]"):
            return await FakeInterview("good").generate_structured(request)
        return await super().generate_structured(request)


if __name__ == "__main__":
    with TemporaryDirectory(prefix="war-room-browser-") as directory:
        settings = Settings(
            database_path=Path(directory) / "test.db",
            llm_provider="disabled",
            _env_file=None,
            storage_mode=os.environ.get("WAR_ROOM_BROWSER_STORAGE", "local_sqlite"),
        )
        source = os.environ.get("WAR_ROOM_VERIFY_DATABASE")
        if source:
            copy_database(source, settings.resolved_database_path)
        command.upgrade(migration_config(settings), "head")
        offline = os.environ.get("WAR_ROOM_VERIFY_OFFLINE") == "1"
        uvicorn.run(
            create_app(
                settings,
                question_provider=None if offline else FakeQuestions(),
                interview_provider=None if offline else BrowserInterview("follow"),
                test_data="persisted-copy" if source else "fixtures",
            ),
            host="127.0.0.1",
            port=8001,
            access_log=False,
        )
