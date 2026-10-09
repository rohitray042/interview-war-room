"""Browser-owned snapshots; each operation gets an independent in-memory database."""

import asyncio
import base64
import json
from contextvars import ContextVar
from typing import Literal
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from pydantic import Field
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, SQLModel, select
from starlette.datastructures import State

from app import models
from app.contracts import StrictModel
from app.db import memory_engine
from app.questions import sync_catalog

MAX_REQUEST = 24 * 1024 * 1024
MAX_WORKSPACE = 12 * 1024 * 1024
MAX_OPERATION = 6 * 1024 * 1024
PUBLIC_PATHS = {
    "/api/v1/health",
    "/api/v1/storage",
    "/api/v1/capabilities",
    "/api/v1/ai/status",
    "/api/v1/content/manifest",
}
device_engine = ContextVar("device_engine", default=None)
MODEL_TYPES = {
    cls.__tablename__: cls
    for cls in vars(models).values()
    if isinstance(cls, type) and issubclass(cls, SQLModel) and cls is not SQLModel
}
TABLES = [table for table in SQLModel.metadata.sorted_tables if table.name in MODEL_TYPES]


class WorkspaceState(State):
    def __getattr__(self, key):
        if key == "engine" and (engine := device_engine.get()) is not None:
            return engine
        return super().__getattr__(key)


class Snapshot(StrictModel):
    version: Literal[1] = 1
    schema_revision: Literal["0005"] = "0005"
    tables: dict[str, list[dict]]


class DeviceOperation(StrictModel):
    workspace: Snapshot | None = None
    path: str = Field(max_length=2048)
    method: Literal["GET", "POST", "PUT", "PATCH"] = "GET"
    body: str = Field(default="", max_length=8 * 1024 * 1024)
    content_type: str = Field(default="application/json", max_length=200)


def restore(engine, snapshot):
    if set(snapshot.tables) != set(MODEL_TYPES):
        raise ValueError("Workspace tables do not match")
    if sum(len(rows) for rows in snapshot.tables.values()) > 20000:
        raise ValueError("Workspace has too many records")
    if len(snapshot.tables["profiles"]) != 1:
        raise ValueError("Workspace must have one profile")
    with Session(engine) as db:
        # Deferred checks allow parent/follow-up rows to arrive in any order.
        db.connection().exec_driver_sql("PRAGMA defer_foreign_keys=ON")
        for table in reversed(TABLES):
            db.exec(delete(table))
        for table in TABLES:
            model = MODEL_TYPES[table.name]
            for row in snapshot.tables[table.name]:
                if set(row) != set(model.model_fields):
                    raise ValueError("Workspace fields do not match")
                validated = model.model_validate(row)
                db.execute(table.insert().values(**validated.model_dump()))
        db.commit()


def snapshot(engine):
    with Session(engine) as db:
        return Snapshot(
            tables={
                name: [row.model_dump(mode="json") for row in db.exec(select(model)).all()]
                for name, model in MODEL_TYPES.items()
            }
        ).model_dump()


async def process_operation(payload: DeviceOperation, request: Request):
    parsed = urlsplit(payload.path)
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.fragment
        or not parsed.path.startswith("/api/v1/")
        or parsed.path.rstrip("/") in {"/api/v1/device", "/api/v1/storage"}
        or ".." in parsed.path
        or "%" in parsed.path
        or "\\" in parsed.path
    ):
        raise HTTPException(422, "Invalid workspace operation.")
    try:
        body = base64.b64decode(payload.body, validate=True)
    except ValueError:
        raise HTTPException(422, "Invalid operation body.") from None
    if len(body) > MAX_OPERATION:
        raise HTTPException(413, "Upload exceeds the request limit.")
    if payload.workspace and len(payload.workspace.model_dump_json().encode()) > MAX_WORKSPACE:
        raise HTTPException(413, "Workspace exceeds 12 MB. Export a backup before clearing data.")
    engine = memory_engine()
    token = None
    try:
        # The template contains only migrated schema and public curated content.
        with request.app.state.engine.connect() as source, engine.connect() as target:
            source.connection.driver_connection.backup(target.connection.driver_connection)
        if payload.workspace is not None:
            try:
                restore(engine, payload.workspace)
                sync_catalog(engine, request.app.state.content_path)
            except ValueError, TypeError, SQLAlchemyError:
                raise HTTPException(
                    422, "Invalid workspace backup. Saved browser data is unchanged."
                ) from None
        token = device_engine.set(engine)
        scope = dict(request.scope)
        scope.update(
            path=parsed.path,
            raw_path=parsed.path.encode(),
            query_string=parsed.query.encode(),
            method=payload.method,
            headers=[
                (b"host", b"localhost"),
                (b"content-type", payload.content_type.encode()),
                (b"content-length", str(len(body)).encode()),
            ],
            state={},
        )
        messages = []
        delivered = False

        async def receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            # ASGI 2.4 responses do not poll disconnect after consuming the body.
            await asyncio.Future()

        async def send(message):
            messages.append(message)

        scope["asgi"] = {"version": "3.0", "spec_version": "2.4"}
        await request.app(scope, receive, send)
        start = next(m for m in messages if m["type"] == "http.response.start")
        response_body = b"".join(m.get("body", b"") for m in messages)
        state = snapshot(engine)
        if len(json.dumps(state).encode()) > MAX_WORKSPACE:
            raise HTTPException(413, "Workspace exceeds 12 MB. Saved browser data is unchanged.")
        return {"status": start["status"], "result": json.loads(response_body), "workspace": state}
    finally:
        if token is not None:
            device_engine.reset(token)
        engine.dispose()
