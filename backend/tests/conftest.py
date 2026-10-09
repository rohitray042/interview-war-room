import httpx
import pytest
from alembic import command

from app.config import Settings
from app.db import migration_config


@pytest.fixture(autouse=True)
def no_live_ai(monkeypatch):
    async def blocked(*args, **kwargs):
        raise AssertionError("Automated tests must use a mocked HTTP transport")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked)


@pytest.fixture
def settings(tmp_path):
    settings = Settings(
        database_path=tmp_path / "test.db",
        llm_provider="disabled",
        storage_mode="local_sqlite",
        _env_file=None,
    )
    command.upgrade(migration_config(settings), "head")
    return settings
