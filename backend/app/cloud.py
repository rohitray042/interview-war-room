"""Optional Supabase accounts; all database requests use the verified user's JWT."""

import time
from collections import OrderedDict
from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import Field, SecretStr

from app.contracts import StrictModel
from app.device_storage import DeviceOperation, Snapshot, process_operation

router = APIRouter(prefix="/api/v1/cloud", tags=["accounts"])
ACCESS, REFRESH = "wr_account_access", "wr_account_refresh"
MARKER = "wr_account_selected"
COOKIE_PATH = "/api/v1/cloud"


class Credentials(StrictModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: SecretStr = Field(min_length=8, max_length=128)


class Email(StrictModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class Verification(Email):
    token: str = Field(pattern=r"^\d{6,10}$")
    type: Literal["signup", "recovery"]
    password: SecretStr | None = Field(default=None, min_length=8, max_length=128)


class WorkspaceInput(StrictModel):
    workspace: Snapshot
    revision: int = Field(ge=0)


class CloudOperation(DeviceOperation):
    expected_revision: int | None = Field(default=None, ge=0)


class DraftInput(StrictModel):
    turn_id: str = Field(
        pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    )
    answer: str = Field(max_length=20000)
    revision: int = Field(ge=0)


class Cloud:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport
        self.attempts = OrderedDict()

    def throttle(self, request):
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        times = [value for value in self.attempts.pop(key, []) if now - value < 60]
        self.attempts[key] = times
        if len(times) >= 10:
            raise HTTPException(429, "Too many account attempts. Wait one minute and retry.")
        times.append(now)
        if len(self.attempts) > 10000:
            self.attempts.popitem(last=False)

    @property
    def enabled(self):
        return bool(
            self.settings.supabase_url and self.settings.supabase_anon_key.get_secret_value()
        )

    async def call(self, method, path, body=None, token=None):
        if not self.enabled:
            raise HTTPException(503, "Cloud accounts are not configured. Guest mode is available.")
        headers = {"apikey": self.settings.supabase_anon_key.get_secret_value()}
        if token:
            headers["Authorization"] = "Bearer " + token
        try:
            async with httpx.AsyncClient(timeout=15, transport=self.transport) as client:
                result = await client.request(
                    method, self.settings.supabase_url + path, headers=headers, json=body
                )
        except httpx.HTTPError:
            raise HTTPException(503, "Account service unavailable. Please retry.") from None
        if result.status_code >= 400:
            # Never expose Supabase payloads, passwords, tokens or database diagnostics.
            if result.status_code == 429:
                raise HTTPException(429, "Too many requests. Please wait before retrying.")
            if result.status_code >= 500:
                raise HTTPException(503, "Account service unavailable. Please retry.")
            if path.startswith("/rest/"):
                if result.status_code == 400 and result.json().get("code") == "P0001":
                    raise HTTPException(
                        409, "Workspace changed on another device. Reload before retrying."
                    )
                raise HTTPException(503, "Cloud save unavailable. No success has been recorded.")
            raise HTTPException(401, "Login or verification failed. Check your details and retry.")
        return result.json() if result.content else None

    def cookies(self, response, tokens):
        for name, value, lifetime in (
            (ACCESS, tokens["access_token"], min(int(tokens.get("expires_in", 3600)), 3600)),
            (REFRESH, tokens["refresh_token"], 30 * 86400),
            (MARKER, "1", 365 * 86400),
        ):
            response.set_cookie(
                name,
                value,
                httponly=True,
                secure=bool(self.settings.public_url),
                samesite="strict",
                path=COOKIE_PATH,
                max_age=lifetime,
            )

    def clear(self, response, keep_marker=False):
        for name in (ACCESS, REFRESH) if keep_marker else (ACCESS, REFRESH, MARKER):
            response.delete_cookie(
                name,
                path=COOKIE_PATH,
                httponly=True,
                secure=bool(self.settings.public_url),
                samesite="strict",
            )

    async def user(self, request, response):
        token = request.cookies.get(ACCESS)
        user = None
        if token:
            try:
                user = await self.call("GET", "/auth/v1/user", token=token)
            except HTTPException as exc:
                if exc.status_code != 401:
                    raise
        if user is None and request.cookies.get(REFRESH):
            tokens = await self.call(
                "POST",
                "/auth/v1/token?grant_type=refresh_token",
                {"refresh_token": request.cookies[REFRESH]},
            )
            self.cookies(response, tokens)
            token = tokens["access_token"]
            user = await self.call("GET", "/auth/v1/user", token=token)
        if not user or not user.get("email_confirmed_at"):
            raise HTTPException(401, "Please log in with a verified email to continue.")
        expected = request.headers.get("x-workspace-user")
        if expected and expected != user["id"]:
            raise HTTPException(409, "Account changed in another tab. Reload to continue.")
        return user, token

    async def workspace(self, user, token):
        rows = await self.call(
            "GET",
            "/rest/v1/account_workspaces?select=workspace,revision&user_id=eq." + user["id"],
            token=token,
        )
        return rows[0] if rows else {"workspace": None, "revision": 0}

    async def save(self, workspace, revision, token):
        return await self.call(
            "POST",
            "/rest/v1/rpc/save_account_workspace",
            {"payload": workspace, "expected_revision": revision},
            token,
        )


def service(request):
    return request.app.state.cloud


@router.get("/session")
async def session(request: Request, response: Response):
    cloud = service(request)
    if not cloud.enabled:
        return {"enabled": False, "user": None}
    if not request.cookies.get(ACCESS) and not request.cookies.get(REFRESH):
        return {
            "enabled": True,
            "user": None,
            **({"expired": True} if request.cookies.get(MARKER) else {}),
        }
    try:
        user, _ = await cloud.user(request, response)
    except HTTPException as exc:
        if exc.status_code != 401:
            raise
        cloud.clear(response, keep_marker=True)
        return {"enabled": True, "user": None, "expired": True}
    return {"enabled": True, "user": {"id": user["id"], "email": user["email"]}}


@router.post("/signup")
async def signup(payload: Credentials, request: Request):
    service(request).throttle(request)
    await service(request).call(
        "POST",
        "/auth/v1/signup",
        {"email": payload.email, "password": payload.password.get_secret_value()},
    )
    return {"message": "Check your email for a verification code. If already registered, log in."}


@router.post("/login")
async def login(payload: Credentials, request: Request, response: Response):
    cloud = service(request)
    cloud.throttle(request)
    tokens = await cloud.call(
        "POST",
        "/auth/v1/token?grant_type=password",
        {"email": payload.email, "password": payload.password.get_secret_value()},
    )
    if not tokens.get("user", {}).get("email_confirmed_at"):
        raise HTTPException(401, "Verify your email before logging in.")
    cloud.cookies(response, tokens)
    return {"ok": True}


@router.post("/recover")
async def recover(payload: Email, request: Request):
    service(request).throttle(request)
    await service(request).call("POST", "/auth/v1/recover", {"email": payload.email})
    return {"message": "If an account exists, check your email for a recovery code."}


@router.post("/verify")
async def verify(payload: Verification, request: Request, response: Response):
    cloud = service(request)
    cloud.throttle(request)
    if payload.type == "recovery" and payload.password is None:
        raise HTTPException(422, "A new password is required.")
    tokens = await cloud.call(
        "POST",
        "/auth/v1/verify",
        {"email": payload.email, "token": payload.token, "type": payload.type},
    )
    if payload.type == "recovery":
        await cloud.call(
            "PUT",
            "/auth/v1/user",
            {"password": payload.password.get_secret_value()},
            tokens["access_token"],
        )
    cloud.cookies(response, tokens)
    return {"ok": True}


@router.post("/logout")
async def logout(request: Request, response: Response):
    cloud = service(request)
    try:
        _, token = await cloud.user(request, response)
        await cloud.call("POST", "/auth/v1/logout?scope=local", token=token)
    except HTTPException as exc:
        if exc.status_code != 401:
            raise
    cloud.clear(response)
    return {"ok": True}


@router.get("/workspace")
async def workspace(request: Request, response: Response):
    cloud = service(request)
    user, token = await cloud.user(request, response)
    return await cloud.workspace(user, token)


@router.post("/workspace")
async def replace(payload: WorkspaceInput, request: Request, response: Response):
    cloud = service(request)
    _, token = await cloud.user(request, response)
    checked = await process_operation(
        DeviceOperation(workspace=payload.workspace, path="/api/v1/profile"), request
    )
    if checked["status"] != 200:
        raise HTTPException(422, "Invalid workspace.")
    revision = await cloud.save(checked["workspace"], payload.revision, token)
    return {"revision": revision}


@router.post("/operation")
async def operation(payload: CloudOperation, request: Request, response: Response):
    cloud = service(request)
    user, token = await cloud.user(request, response)
    if payload.workspace is not None:
        raise HTTPException(422, "Use explicit import to upload browser data.")
    stored = await cloud.workspace(user, token)
    writes = payload.method != "GET" and payload.path != "/api/v1/interviews/preview"
    if writes and payload.expected_revision != stored["revision"]:
        raise HTTPException(409, "Workspace changed on another device. Reload before retrying.")
    result = await process_operation(
        DeviceOperation(
            **payload.model_dump(exclude={"expected_revision", "workspace"}),
            workspace=Snapshot.model_validate(stored["workspace"]) if stored["workspace"] else None,
        ),
        request,
    )
    revision = stored["revision"]
    if writes:
        revision = await cloud.save(result["workspace"], stored["revision"], token)
    return {"status": result["status"], "result": result["result"], "revision": revision}


@router.post("/delete-account")
async def delete_account(payload: Credentials, request: Request, response: Response):
    cloud = service(request)
    cloud.throttle(request)
    user, token = await cloud.user(request, response)
    if payload.email.lower() != user["email"].lower():
        raise HTTPException(401, "Check your account details.")
    confirmed = await cloud.call(
        "POST",
        "/auth/v1/token?grant_type=password",
        {"email": payload.email, "password": payload.password.get_secret_value()},
    )
    if confirmed["user"]["id"] != user["id"]:
        raise HTTPException(401, "Check your account details.")
    await cloud.call("POST", "/rest/v1/rpc/delete_own_account", {}, token)
    cloud.clear(response)
    return {"ok": True}


@router.get("/draft/{turn_id}")
async def draft(turn_id: UUID, request: Request, response: Response):
    cloud = service(request)
    user, token = await cloud.user(request, response)
    rows = await cloud.call(
        "GET",
        "/rest/v1/account_drafts?select=answer,revision&user_id=eq."
        + user["id"]
        + "&turn_id=eq."
        + str(turn_id),
        token=token,
    )
    return rows[0] if rows else {"answer": "", "revision": 0}


@router.post("/draft")
async def save_draft(payload: DraftInput, request: Request, response: Response):
    cloud = service(request)
    _, token = await cloud.user(request, response)
    revision = await cloud.call(
        "POST",
        "/rest/v1/rpc/save_account_draft",
        {
            "turn": str(payload.turn_id),
            "answer_text": payload.answer,
            "expected_revision": payload.revision,
        },
        token,
    )
    return {"revision": revision}
