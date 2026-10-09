import hmac
import logging
from contextlib import asynccontextmanager
from typing import Annotated, Literal
from urllib.parse import parse_qs

from alembic import command
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import Field as ValidatedField
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select
from starlette.formparsers import MultiPartParser

from app.analyzer_api import router as analyzer_router
from app.config import Settings
from app.content import ContentCatalog
from app.contracts import DisabledProvider, StrictModel
from app.db import make_engine, memory_engine, migration_config
from app.device_storage import (
    MAX_OPERATION,
    MAX_REQUEST,
    PUBLIC_PATHS,
    DeviceOperation,
    WorkspaceState,
    device_engine,
    process_operation,
)
from app.hosting import (
    COOKIE,
    authorized,
    hosting_origins,
    login_page,
    mount_frontend,
    session_token,
    valid_session,
)
from app.interview_api import router as interview_router
from app.interview_content import InterviewContent
from app.learning_api import router as learning_router
from app.learning_content import mappings
from app.models import Profile, utc_now
from app.providers import make_provider
from app.question_api import router as question_router
from app.questions import sync_catalog

logger = logging.getLogger("war_room")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


class ProfileInput(StrictModel):
    name: str = ValidatedField(max_length=100)
    background: str = ValidatedField(max_length=4000)
    target_role: str = ValidatedField(min_length=1, max_length=120)
    skills: list[Annotated[str, ValidatedField(min_length=1, max_length=80)]] = ValidatedField(
        max_length=50
    )
    learning_skills: list[Annotated[str, ValidatedField(min_length=1, max_length=80)]] = (
        ValidatedField(max_length=50)
    )
    daily_study_minutes: int = ValidatedField(ge=5, le=480)


def create_app(
    settings: Settings | None = None,
    question_provider=None,
    interview_provider=None,
    *,
    test_data: Literal["fixtures", "persisted-copy"] | None = None,
) -> FastAPI:
    settings = settings or Settings()
    injected = question_provider is not None or interview_provider is not None

    @asynccontextmanager
    async def lifespan(app):
        engine = memory_engine() if settings.storage_mode == "browser" else make_engine(settings)
        try:
            if settings.storage_mode == "browser":
                config = migration_config(settings)
                with engine.begin() as connection:
                    config.attributes["connection"] = connection
                    command.upgrade(config, "head")
                MultiPartParser.spool_max_size = MAX_OPERATION
            with engine.connect() as connection:
                revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar()
                if revision != "0005":
                    raise RuntimeError("Run alembic upgrade head before starting the API")
            app.state.engine = engine
            app.state.content_path = settings.content_path
            provider = DisabledProvider() if injected else make_provider(settings)
            app.state.llm = provider
            app.state.external_llm = not isinstance(provider, DisabledProvider)
            app.state.question_llm = question_provider or provider
            app.state.interview_llm = interview_provider or provider
            app.state.interview_content = InterviewContent.load(settings.content_path)
            mappings()
            app.state.catalog = ContentCatalog(settings.content_path)
            sync_catalog(engine, settings.content_path)
            with Session(engine) as session:
                if not session.exec(select(Profile)).first():
                    session.add(Profile())
                    session.commit()
            logger.info("Learning workspace ready: database revision 0005; content validated")
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="Interview War Room", version="0.6.0", lifespan=lifespan)
    app.state = WorkspaceState()
    app.include_router(analyzer_router)
    app.include_router(question_router)
    app.include_router(interview_router)
    app.include_router(learning_router)
    hosts, origins = hosting_origins(settings)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "PUT", "POST", "PATCH"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        gateway = request.url.path == "/api/v1/device"
        password = settings.access_password.get_secret_value()
        if request.url.path == "/auth/login" and request.method == "POST":
            if request.headers.get("origin") not in origins:
                return JSONResponse(status_code=403, content={"detail": "Invalid login origin."})
            body = b""
            async for chunk in request.stream():
                body += chunk
                if len(body) > 4096:
                    return JSONResponse(
                        status_code=413, content={"detail": "Login request too large."}
                    )
            supplied = parse_qs(body.decode("utf-8", errors="replace")).get("password", [""])[0]
            if not password or not hmac.compare_digest(supplied.encode(), password.encode()):
                return login_page(failed=True)
            response = RedirectResponse("/", status_code=303)
            response.set_cookie(
                COOKIE,
                session_token(password),
                max_age=86400,
                httponly=True,
                secure=bool(settings.public_url),
                samesite="strict",
                path="/",
            )
            response.headers["Cache-Control"] = "no-store"
            return response
        if device_engine.get() is None and request.url.path != "/api/v1/health":
            if not authorized(
                request.headers.get("authorization", ""),
                settings.access_password.get_secret_value(),
            ) and not valid_session(request.cookies.get(COOKIE), password):
                if request.method == "GET" and request.url.path == "/":
                    return login_page()
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Enter your workspace access password."},
                    headers={
                        "WWW-Authenticate": 'Basic realm="Interview War Room", charset="UTF-8"',
                        "Cache-Control": "no-store",
                    },
                )
        if settings.storage_mode == "browser" and device_engine.get() is None:
            if (
                request.url.path.startswith("/api/")
                and request.url.path not in PUBLIC_PATHS | {"/api/v1/device"}
            ) or request.url.path in {"/docs", "/redoc", "/openapi.json"}:
                return JSONResponse(
                    status_code=403, content={"detail": "Open your browser workspace to continue."}
                )
        size = request.headers.get("content-length")
        if size:
            try:
                if int(size) > (MAX_REQUEST if gateway else MAX_OPERATION):
                    return JSONResponse(
                        status_code=413, content={"detail": "Request exceeds the size limit."}
                    )
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid content length."})
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and origin not in origins:
                return JSONResponse(status_code=403, content={"error": {"code": "origin_denied"}})
        if gateway:
            chunks, length = [], 0
            async for chunk in request.stream():
                length += len(chunk)
                if length > MAX_REQUEST:
                    return JSONResponse(status_code=413, content={"detail": "Request too large."})
                chunks.append(chunk)
            request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        logger.info("%s %s %s", request.method, request.url.path, response.status_code)
        return response

    @app.get("/api/v1/storage")
    def storage():
        return {"mode": settings.storage_mode, "version": 1}

    @app.post("/api/v1/device")
    async def device(payload: DeviceOperation, request: Request):
        if settings.storage_mode != "browser":
            raise HTTPException(404, "Browser storage is not enabled.")
        return await process_operation(payload, request)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, exc):
        # Do not echo private submitted text in validation errors or logs.
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "fields": [
                        {"location": list(e["loc"]), "message": e["msg"]} for e in exc.errors()
                    ],
                }
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_request, _exc):
        logger.error("Database operation failed")
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "database_unavailable",
                    "message": "Could not save or load data. Try again.",
                }
            },
        )

    @app.get("/api/v1/health")
    def health():
        with Session(app.state.engine) as session:
            session.exec(text("SELECT 1"))
        return {"status": "ok", "milestone": 6, "database": "ready", "schema_revision": "0005"}

    @app.get("/api/v1/capabilities")
    def capabilities():
        return {
            "workspace": {
                "data": test_data or ("fixtures" if injected else "user"),
                "simulated_ai": injected,
            },
            "profile": True,
            "sample_content": True,
            "resume_analysis": True,
            "analysis_method": "local-evidence-extraction",
            "question_bank": True,
            "question_generation": {
                "enabled": not isinstance(app.state.question_llm, DisabledProvider),
                "provider": settings.llm_provider,
                "mode": "bounded-evidence-v1",
            },
            "mock_interview": True,
            "evaluation": True,
            "weaknesses": True,
            "adaptive_learning": True,
            "interview_evaluation": {
                "enabled": not isinstance(app.state.interview_llm, DisabledProvider),
                "external": app.state.external_llm,
                "provider": settings.llm_provider,
            },
            "analytics": False,
            "llm": ai_status(),
        }

    @app.get("/api/v1/ai/status")
    def ai_status():
        if injected:
            return {"enabled": True, "mode": "mock", "provider": "mock", "status": "mock"}
        if isinstance(app.state.llm, DisabledProvider):
            return {
                "enabled": False,
                "mode": "disabled",
                "provider": "disabled",
                "status": "disabled",
            }
        return {
            "enabled": True,
            "mode": "live",
            "provider": app.state.llm.provider_name,
            "status": app.state.llm.last_status,
            "model": app.state.llm.safe_model,
        }

    @app.get("/api/v1/content/manifest")
    def content_manifest():
        catalog = app.state.catalog
        return {
            "questions": [
                {
                    "id": q.id,
                    "version": q.version,
                    "topic": q.topic,
                    "difficulty": q.difficulty,
                    "type": q.type,
                }
                for q in catalog.questions.values()
            ],
            "rubrics": [{"id": r.id, "version": r.version} for r in catalog.rubrics.values()],
        }

    @app.get("/api/v1/profile", response_model=Profile)
    def get_profile():
        with Session(app.state.engine) as session:
            return session.exec(select(Profile)).one()

    @app.put("/api/v1/profile", response_model=Profile)
    def save_profile(payload: ProfileInput):
        with Session(app.state.engine) as session:
            profile = session.exec(select(Profile)).first()
            if profile is None:
                raise HTTPException(503, "Profile is unavailable")
            for name, value in payload.model_dump().items():
                setattr(profile, name, value)
            profile.updated_at = utc_now()
            session.add(profile)
            session.commit()
            session.refresh(profile)
            return profile

    mount_frontend(app, settings)
    return app


app = create_app()
