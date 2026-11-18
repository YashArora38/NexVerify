"""Additive security boundary for NexVerify.

The parent application opts in with ``install_security(app)`` and calls
``claim_resource(request, resource_id)`` immediately after creating a check or
batch.  This module deliberately does not change the existing store module:
resource ownership lives in its own table created through ``store.engine()``.

Production is fail-closed.  Development retains the existing anonymous public
workflow, but authenticated users still receive owner isolation when an owner
record exists.  No request bodies, cookies, tokens, or OAuth responses are
logged here.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import secrets
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import Column, DateTime, MetaData, String, Table, insert, select
from sqlalchemy.exc import IntegrityError
from starlette.types import ASGIApp, Message, Receive, Scope, Send


SESSION_COOKIE = "webdev_app_session"
STATE_COOKIE = "nexverify_oauth_state"
NONCE_COOKIE = "nexverify_oauth_nonce"
PROTECTED_PREFIXES = ("/api/",)
PUBLIC_PATHS = {
    "/api/health",
    "/api/rules",
    "/api/auth/status",
    "/api/auth/login",
    "/api/auth/callback",
    "/api/auth/logout",
}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
MAX_RATE_KEYS = 4096
_OWNER_META = MetaData()
_OWNER_TABLE = Table(
    "nexverify_resource_owners",
    _OWNER_META,
    Column("resource_type", String(32), primary_key=True),
    Column("resource_id", String(128), primary_key=True),
    Column("owner_id", String(256), nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
_OWNER_READY = False
_OWNER_LOCK = threading.Lock()


class SecurityConfigurationError(RuntimeError):
    """Raised before serving traffic when production security is incomplete."""


class _BodyTooLarge(Exception):
    pass


@dataclass(frozen=True)
class SecuritySettings:
    environment: str
    production: bool
    jwt_secret: str
    project_id: str
    frontend_origin: str
    allowed_origins: tuple[str, ...]
    secure_cookies: bool
    max_body_bytes: int
    rate_limit: int
    rate_window_seconds: int
    session_ttl_seconds: int
    oauth_authorize_url: str
    oauth_token_url: str
    oauth_userinfo_url: str
    oauth_client_id: str
    oauth_client_secret: str
    oauth_scope: str
    frontend_return_path: str

    @classmethod
    def from_env(cls) -> "SecuritySettings":
        env = os.getenv("NEXVERIFY_ENV", "development").strip().lower()
        if env not in {"development", "test", "production"}:
            raise SecurityConfigurationError("NEXVERIFY_ENV must be development, test or production")
        production = env == "production"
        secret = os.getenv("MANUS_JWT_SECRET", "")
        project_id = os.getenv("MANUS_PROJECT_ID", "").strip()
        origin = os.getenv("FRONTEND_ORIGIN", "").strip()
        if not origin and not production:
            origin = os.getenv("NEXVERIFY_FRONTEND_ORIGIN", "http://localhost:3000").strip()
        _validate_origin(origin, required=production)
        allowed = _origins(origin, os.getenv("NEXVERIFY_ALLOWED_ORIGINS", ""))
        if production:
            if not origin.startswith("https://"):
                raise SecurityConfigurationError("production FRONTEND_ORIGIN must use HTTPS")
            missing: list[str] = []
            if len(secret.encode("utf-8")) < 32:
                missing.append("MANUS_JWT_SECRET (at least 32 bytes)")
            if not project_id:
                missing.append("MANUS_PROJECT_ID")
            if not origin:
                missing.append("FRONTEND_ORIGIN (one explicit origin)")
            if missing:
                raise SecurityConfigurationError(
                    "production security configuration is incomplete: " + ", ".join(missing)
                )
        max_body = _bounded_int("NEXVERIFY_MAX_BODY_BYTES", 2 * 1024 * 1024, 1024, 10 * 1024 * 1024)
        rate_limit = _bounded_int("NEXVERIFY_RATE_LIMIT", 120, 5, 10_000)
        rate_window = _bounded_int("NEXVERIFY_RATE_WINDOW_SECONDS", 60, 1, 3600)
        ttl = _bounded_int("NEXVERIFY_SESSION_TTL_SECONDS", 8 * 3600, 300, 7 * 86400)
        return cls(
            environment=env,
            production=production,
            jwt_secret=secret,
            project_id=project_id,
            frontend_origin=origin,
            allowed_origins=tuple(allowed),
            secure_cookies=production or _bool_env("NEXVERIFY_SECURE_COOKIES", origin.startswith("https://")),
            max_body_bytes=max_body,
            rate_limit=rate_limit,
            rate_window_seconds=rate_window,
            session_ttl_seconds=ttl,
            oauth_authorize_url=(os.getenv("MANUS_OAUTH_PORTAL_URL", "").rstrip("/") + "/app-auth") if os.getenv("MANUS_OAUTH_PORTAL_URL") else "",
            oauth_token_url=(os.getenv("MANUS_OAUTH_API_URL", "").rstrip("/") + "/webdev.v1.WebDevAuthPublicService/ExchangeToken") if os.getenv("MANUS_OAUTH_API_URL") else "",
            oauth_userinfo_url=(os.getenv("MANUS_OAUTH_API_URL", "").rstrip("/") + "/webdev.v1.WebDevAuthPublicService/GetUserInfo") if os.getenv("MANUS_OAUTH_API_URL") else "",
            oauth_client_id=os.getenv("MANUS_OAUTH_CLIENT_ID", project_id).strip(),
            oauth_client_secret=os.getenv("MANUS_OAUTH_CLIENT_SECRET", ""),
            oauth_scope=os.getenv("MANUS_OAUTH_SCOPE", "openid profile").strip(),
            frontend_return_path=_return_path(os.getenv("FRONTEND_RETURN_PATH", "/")),
        )


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def _bounded_int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def _return_path(value: str) -> str:
    if not value.startswith("/") or value.startswith("//") or "\\" in value:
        raise SecurityConfigurationError("FRONTEND_RETURN_PATH must be a local path")
    return value


def _validate_origin(origin: str, *, required: bool) -> None:
    if not origin:
        if required:
            raise SecurityConfigurationError("FRONTEND_ORIGIN must be an explicit public origin")
        return
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise SecurityConfigurationError("FRONTEND_ORIGIN must be an exact http(s) origin")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment or origin == "*":
        raise SecurityConfigurationError("FRONTEND_ORIGIN must not contain a path, query, fragment, or wildcard")


def _origins(primary: str, extra: str) -> list[str]:
    values: list[str] = []
    for candidate in [primary, *extra.split(",")]:
        candidate = candidate.strip()
        if candidate and candidate not in values:
            _validate_origin(candidate, required=True)
            values.append(candidate.rstrip("/"))
    return values


def _b64url_decode(value: str) -> bytes:
    if not value or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for ch in value):
        raise ValueError("invalid base64url")
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def encode_session(payload: dict[str, Any], secret: str) -> str:
    """Create a compact HS256 session token for tests and the OAuth callback."""
    header = _b64url_encode(b'{"alg":"HS256","typ":"JWT"}')
    body = _b64url_encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode())
    signing_input = f"{header}.{body}".encode("ascii")
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{body}.{_b64url_encode(signature)}"


def decode_session(token: str, settings: SecuritySettings) -> dict[str, Any] | None:
    """Validate only the HS256 appId/openId/expiry claims accepted by this app."""
    try:
        if not isinstance(token, str) or len(token) > 8192:
            return None
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header = json.loads(_b64url_decode(parts[0]))
        if not isinstance(header, dict) or header.get("alg") != "HS256":
            return None
        signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
        expected = hmac.new(settings.jwt_secret.encode(), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(parts[2])):
            return None
        payload = json.loads(_b64url_decode(parts[1]))
        if not isinstance(payload, dict):
            return None
        if payload.get("appId") != settings.project_id or not isinstance(payload.get("openId"), str) or not payload["openId"]:
            return None
        exp = payload.get("exp")
        if not isinstance(exp, (int, float)) or isinstance(exp, bool) or not math.isfinite(exp) or exp <= time.time():
            return None
        return payload
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _cookie_options(settings: SecuritySettings, *, path: str = "/") -> dict[str, Any]:
    return {
        "httponly": True,
        "secure": settings.secure_cookies,
        "samesite": "none" if settings.secure_cookies and path == "/" else "lax",
        "path": path,
    }


def _redirect_uri(settings: SecuritySettings) -> str:
    return urlunsplit((settings.frontend_origin.split(":", 1)[0], urlsplit(settings.frontend_origin).netloc, "/api/auth/callback", "", ""))


class _RateLimiter:
    """Bounded fixed-window limiter; intentionally local to one worker."""

    def __init__(self, limit: int, window: int):
        self.limit = limit
        self.window = window
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def allowed(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits.get(key)
            if bucket is None:
                if len(self._hits) >= MAX_RATE_KEYS:
                    self._hits.popitem(last=False)
                bucket = deque()
                self._hits[key] = bucket
            else:
                self._hits.move_to_end(key)
            while bucket and bucket[0] <= now - self.window:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True


def _client_key(scope: Scope, user: dict[str, Any] | None) -> str:
    if user and user.get("openId"):
        return "user:" + str(user["openId"])
    client = scope.get("client")
    return "ip:" + str(client[0] if client else "unknown")


def _authenticate(scope: Scope, settings: SecuritySettings) -> dict[str, Any] | None:
    headers = {key.lower(): value for key, value in scope.get("headers", [])}
    cookie_header = headers.get(b"cookie", b"").decode("latin-1")
    token = None
    for item in cookie_header.split(";"):
        name, sep, value = item.strip().partition("=")
        if sep and name == SESSION_COOKIE:
            token = value
            break
    if not token or not settings.jwt_secret or not settings.project_id:
        return None
    return decode_session(token, settings)


def _resource_from_path(path: str) -> tuple[str, str] | None:
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 4 and parts[:3] == ["api", "check", "batch"]:
        return ("batch", parts[3])
    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "check":
        candidate = parts[2]
        if candidate.startswith("nv") or candidate.startswith("batch_"):
            return ("batch" if candidate.startswith("batch_") else "check", candidate)
    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "evidence":
        candidate = parts[2]
        if candidate.startswith("nv"):
            return ("check", candidate)
    return None


def _ensure_owner_table() -> None:
    global _OWNER_READY
    if _OWNER_READY:
        return
    from . import store

    with _OWNER_LOCK:
        if not _OWNER_READY:
            _OWNER_TABLE.create(store.engine(), checkfirst=True)
            _OWNER_READY = True


def _owner_id(request: Request) -> str | None:
    user = getattr(request.state, "user", None)
    return str(user["openId"]) if user and user.get("openId") else None


def claim_resource(request: Request, resource_id: str) -> bool:
    """Claim a newly created check/batch for the authenticated Manus user.

    Returns ``False`` for the anonymous development workflow.  In production,
    an absent user or an existing different owner raises a non-sensitive HTTP
    error.  Call this only after the parent has created the resource.
    """
    owner = _owner_id(request)
    settings: SecuritySettings = request.app.state.nexverify_security
    if not owner:
        if settings.production:
            raise HTTPException(401, "authentication required")
        return False
    resource_type = "batch" if str(resource_id).startswith("batch_") else "check"
    _ensure_owner_table()
    from . import store

    values = {
        "resource_type": resource_type,
        "resource_id": str(resource_id),
        "owner_id": owner,
        "created_at": datetime.now(timezone.utc),
    }
    with store.engine().begin() as conn:
        row = conn.execute(
            select(_OWNER_TABLE.c.owner_id).where(
                (_OWNER_TABLE.c.resource_type == resource_type)
                & (_OWNER_TABLE.c.resource_id == str(resource_id))
            )
        ).first()
        if row and row[0] != owner:
            raise HTTPException(403, "resource is owned by another user")
        if not row:
            try:
                conn.execute(insert(_OWNER_TABLE).values(**values))
            except IntegrityError:
                row = conn.execute(
                    select(_OWNER_TABLE.c.owner_id).where(
                        (_OWNER_TABLE.c.resource_type == resource_type)
                        & (_OWNER_TABLE.c.resource_id == str(resource_id))
                    )
                ).first()
                if not row or row[0] != owner:
                    raise HTTPException(403, "resource is owned by another user")
    return True


def _authorized_resource(request: Request, settings: SecuritySettings) -> bool:
    resource = _resource_from_path(request.url.path)
    if not resource:
        return True
    owner = _owner_id(request)
    if not owner:
        return not settings.production
    _ensure_owner_table()
    from . import store

    with store.engine().connect() as conn:
        row = conn.execute(
            select(_OWNER_TABLE.c.owner_id).where(
                (_OWNER_TABLE.c.resource_type == resource[0])
                & (_OWNER_TABLE.c.resource_id == resource[1])
            )
        ).first()
    if row is None:
        return not settings.production
    return hmac.compare_digest(str(row[0]), owner)


def filter_recent(request: Request, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter a recent-result list to the current owner in production."""
    settings: SecuritySettings = request.app.state.nexverify_security
    owner = _owner_id(request)
    if not owner:
        if settings.production:
            raise HTTPException(401, "authentication required")
        return items
    _ensure_owner_table()
    ids = [str(item.get("check_id", "")) for item in items if item.get("check_id")]
    if not ids:
        return []
    from . import store

    with store.engine().connect() as conn:
        rows = conn.execute(
            select(_OWNER_TABLE.c.resource_id).where(
                (_OWNER_TABLE.c.resource_type == "check")
                & (_OWNER_TABLE.c.owner_id == owner)
                & _OWNER_TABLE.c.resource_id.in_(ids)
            )
        ).all()
    owned = {str(row[0]) for row in rows}
    return [item for item in items if str(item.get("check_id", "")) in owned]


class SecurityMiddleware:
    def __init__(self, app: ASGIApp, settings: SecuritySettings):
        self.app = app
        self.settings = settings
        self.limiter = _RateLimiter(settings.rate_limit, settings.rate_window_seconds)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        method = scope.get("method", "GET").upper()
        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return
        user = _authenticate(scope, self.settings)
        scope.setdefault("state", {})["user"] = user
        is_public = path in PUBLIC_PATHS or path.startswith("/api/auth/")
        is_api = path.startswith(PROTECTED_PREFIXES)

        if is_api and not is_public and self.settings.production and not user:
            await self._error(send, 401, "authentication required")
            return
        if is_api and not self.limiter.allowed(_client_key(scope, user)):
            await self._error(send, 429, "rate limit exceeded", headers={"Retry-After": str(self.settings.rate_window_seconds)})
            return
        if method not in SAFE_METHODS and path != "/api/auth/callback":
            if not self._csrf_allowed(scope, user):
                await self._error(send, 403, "origin not allowed")
                return
        if self._content_length_too_large(scope):
            await self._error(send, 413, "request body too large")
            return
        if is_api and not is_public and not _authorized_resource_from_scope(scope, self.settings):
            await self._error(send, 403, "resource access denied")
            return

        async def limited_receive() -> Message:
            message = await receive()
            if message.get("type") == "http.request":
                limited_receive.seen += len(message.get("body", b""))
                if limited_receive.seen > self.settings.max_body_bytes:
                    raise _BodyTooLarge
            return message

        limited_receive.seen = 0  # type: ignore[attr-defined]

        async def secured_send(message: Message) -> None:
            if message.get("type") == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {key.lower() for key, _ in headers}
                additions = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                ]
                if is_api:
                    additions.append((b"cache-control", b"private, no-store"))
                if self.settings.production and self.settings.frontend_origin.startswith("https://"):
                    additions.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                headers.extend((key, value) for key, value in additions if key not in existing)
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, limited_receive, secured_send)
        except _BodyTooLarge:
            await self._error(send, 413, "request body too large")

    def _csrf_allowed(self, scope: Scope, user: dict[str, Any] | None) -> bool:
        headers = {key.lower(): value.decode("latin-1") for key, value in scope.get("headers", [])}
        origin = headers.get(b"origin")
        cookie_present = b"cookie" in {key.lower() for key, _ in scope.get("headers", [])}
        if origin is None and not (self.settings.production and cookie_present):
            return True
        return origin is not None and origin.rstrip("/") in self.settings.allowed_origins

    def _content_length_too_large(self, scope: Scope) -> bool:
        for key, value in scope.get("headers", []):
            if key.lower() == b"content-length":
                try:
                    return int(value) > self.settings.max_body_bytes
                except ValueError:
                    return True
        return False

    async def _error(self, send: Send, status: int, detail: str, headers: dict[str, str] | None = None) -> None:
        response_headers = {
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Cache-Control": "no-store",
            **(headers or {}),
        }
        if self.settings.production and self.settings.frontend_origin.startswith("https://"):
            response_headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        response = JSONResponse({"detail": detail}, status_code=status, headers=response_headers)
        await send({"type": "http.response.start", "status": status, "headers": response.raw_headers})
        await send({"type": "http.response.body", "body": response.body, "more_body": False})


def _authorized_resource_from_scope(scope: Scope, settings: SecuritySettings) -> bool:
    resource = _resource_from_path(scope.get("path", ""))
    if not resource:
        return True
    user = scope.get("state", {}).get("user")
    if not user:
        return not settings.production
    try:
        _ensure_owner_table()
        from . import store

        with store.engine().connect() as conn:
            row = conn.execute(
                select(_OWNER_TABLE.c.owner_id).where(
                    (_OWNER_TABLE.c.resource_type == resource[0])
                    & (_OWNER_TABLE.c.resource_id == resource[1])
                )
            ).first()
        return bool(row and hmac.compare_digest(str(row[0]), str(user.get("openId", ""))))
    except Exception:
        return False if settings.production else True


def _auth_router(settings: SecuritySettings) -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"])
    state_lock = threading.Lock()
    states: OrderedDict[str, tuple[str, float]] = OrderedDict()

    def remember_state(state: str, nonce: str) -> None:
        now = time.time()
        with state_lock:
            for key, (_, created) in list(states.items()):
                if created < now - 600:
                    states.pop(key, None)
            if len(states) >= 1024:
                states.popitem(last=False)
            states[state] = (nonce, now)

    def consume_state(state: str) -> str | None:
        with state_lock:
            pair = states.pop(state, None)
        if not pair or pair[1] < time.time() - 600:
            return None
        return pair[0]

    @router.get("/status")
    async def auth_status(request: Request) -> dict[str, Any]:
        user = getattr(request.state, "user", None)
        return {"authenticated": bool(user), "required": settings.production,
                "configured": bool(settings.jwt_secret and settings.project_id and settings.oauth_authorize_url),
                "user": {"openId": user["openId"], "appId": user["appId"], "name": user.get("name")} if user else None}

    @router.get("/login")
    async def auth_login() -> RedirectResponse:
        if not settings.oauth_authorize_url or not settings.oauth_client_id or len(settings.jwt_secret.encode()) < 32:
            raise HTTPException(503, "OAuth is not configured")
        nonce = secrets.token_urlsafe(32)
        state = base64.b64encode(json.dumps({"redirectUri": _redirect_uri(settings), "nonce": nonce}, separators=(",", ":")).encode()).decode()
        remember_state(state, nonce)
        params = {
            "appId": settings.oauth_client_id,
            "redirectUri": _redirect_uri(settings),
            "responseType": "code",
            "state": state,
        }
        separator = "&" if "?" in settings.oauth_authorize_url else "?"
        response = RedirectResponse(settings.oauth_authorize_url + separator + urlencode(params), status_code=307)
        options = _cookie_options(settings, path="/api/auth")
        response.set_cookie(STATE_COOKIE, state, max_age=600, **options)
        response.set_cookie(NONCE_COOKIE, nonce, max_age=600, **options)
        return response

    @router.get("/callback")
    async def auth_callback(request: Request, code: str = "", state: str = "") -> RedirectResponse:
        cookie_state = request.cookies.get(STATE_COOKIE, "")
        cookie_nonce = request.cookies.get(NONCE_COOKIE, "")
        expected_nonce = consume_state(state) if state and cookie_state and hmac.compare_digest(state, cookie_state) else None
        if not expected_nonce or not cookie_nonce or not hmac.compare_digest(expected_nonce, cookie_nonce):
            raise HTTPException(400, "invalid OAuth state")
        if not code or not settings.oauth_token_url or not settings.oauth_userinfo_url:
            raise HTTPException(503, "OAuth provider is not configured")
        form = {
            "grantType": "authorization_code",
            "code": code,
            "clientId": settings.oauth_client_id,
            "redirectUri": _redirect_uri(settings),
        }
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
                token_response = await client.post(settings.oauth_token_url, json=form, headers={"Accept": "application/json"})
                token_response.raise_for_status()
                token_body = token_response.json()
                access_token = token_body.get("accessToken")
                if not isinstance(access_token, str) or not access_token:
                    raise ValueError("missing OAuth access token")
                info_response = await client.post(
                    settings.oauth_userinfo_url,
                    json={"accessToken": access_token}, headers={"Accept": "application/json"},
                )
                info_response.raise_for_status()
                info = info_response.json()
        except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError):
            raise HTTPException(502, "OAuth provider unavailable")
        if isinstance(info, dict) and isinstance(info.get("user"), dict):
            info = info["user"]
        if not isinstance(info, dict):
            raise HTTPException(502, "OAuth provider returned invalid user data")
        open_id = info.get("openId") or info.get("open_id") or info.get("sub") or info.get("id")
        provider_app = info.get("appId") or info.get("app_id") or info.get("projectId")
        if not open_id or (provider_app and str(provider_app) != settings.project_id):
            raise HTTPException(502, "OAuth provider returned incomplete user data")
        now = int(time.time())
        token = encode_session(
            {"appId": settings.project_id, "openId": str(open_id), "name": str(info.get("name") or "")[:100],
             "iat": now, "exp": now + settings.session_ttl_seconds},
            settings.jwt_secret,
        )
        response = RedirectResponse(settings.frontend_origin.rstrip("/") + settings.frontend_return_path, status_code=303)
        response.delete_cookie(STATE_COOKIE, path="/api/auth")
        response.delete_cookie(NONCE_COOKIE, path="/api/auth")
        response.set_cookie(SESSION_COOKIE, token, max_age=settings.session_ttl_seconds, **_cookie_options(settings))
        return response

    @router.post("/logout")
    async def auth_logout() -> JSONResponse:
        response = JSONResponse({"ok": True})
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    return router


def install_security(app: Any) -> SecuritySettings:
    """Install middleware and auth routes; call once during app construction."""
    settings = SecuritySettings.from_env()
    app.state.nexverify_security = settings
    app.add_middleware(SecurityMiddleware, settings=settings)
    app.include_router(_auth_router(settings))
    return settings


__all__ = [
    "SecurityConfigurationError",
    "SecuritySettings",
    "claim_resource",
    "decode_session",
    "encode_session",
    "filter_recent",
    "install_security",
]
