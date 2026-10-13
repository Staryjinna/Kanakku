"""CSRF (double-submit token + Origin check), security headers and log redaction."""

import json
import logging
import secrets
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any
from urllib.parse import urlparse

from app.llm.redact import redact

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

SESSION_COOKIE = "kanakku_session"
CSRF_COOKIE = "kanakku_csrf"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_EXEMPT = {"/api/auth/login", "/api/auth/signup"}  # no session yet


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def _headers(scope: Scope) -> dict[str, str]:
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}


def _cookies(header: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in header.split(";"):
        name, _, value = part.strip().partition("=")
        if name:
            out[name] = value
    return out


async def _forbidden(send: Send, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 403,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class CSRFMiddleware:
    """Cookie-authenticated unsafe requests must echo the CSRF cookie in a header, and any Origin
    header must match the Host. Requests without a session cookie are left to the 401 path."""

    def __init__(self, app: ASGIApp, enabled: bool = True) -> None:
        self.app = app
        self.enabled = enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or not self.enabled
            or scope["method"] in SAFE_METHODS
            or not scope["path"].startswith("/api/")
            or scope["path"] in CSRF_EXEMPT
        ):
            return await self.app(scope, receive, send)
        headers = _headers(scope)
        origin = headers.get("origin")
        if origin and urlparse(origin).netloc != headers.get("host", ""):
            return await _forbidden(send, "Cross-site request blocked")
        cookies = _cookies(headers.get("cookie", ""))
        if SESSION_COOKIE in cookies:
            cookie_token = cookies.get(CSRF_COOKIE, "")
            header_token = headers.get(CSRF_HEADER, "")
            if not cookie_token or not secrets.compare_digest(cookie_token, header_token):
                return await _forbidden(send, "CSRF token missing or invalid")
        await self.app(scope, receive, send)


CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; connect-src 'self'; frame-src 'self'; object-src 'none'; "
    "base-uri 'self'; form-action 'self'; frame-ancestors 'self'"
)
# The PDF viewer needs object-src for the document itself, so uploaded files get a tighter policy
# that only differs there.
FILE_CSP = "default-src 'none'; img-src 'self'; object-src 'self'; frame-ancestors 'self'"


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, prod: bool = False) -> None:
        self.app = app
        self.prod = prod

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path: str = scope["path"]

        async def send_wrapper(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message["headers"]]
                have = {k.lower() for k, _ in headers}
                extra = {
                    b"x-content-type-options": b"nosniff",
                    b"x-frame-options": b"SAMEORIGIN",
                    b"referrer-policy": b"same-origin",
                    b"permissions-policy": b"camera=(), microphone=(), geolocation=()",
                    b"content-security-policy": (
                        FILE_CSP if path.endswith("/file") else CSP
                    ).encode(),
                }
                if path.startswith("/api/"):
                    extra[b"cache-control"] = b"no-store"  # authenticated data is never cached
                if self.prod:
                    extra[b"strict-transport-security"] = b"max-age=31536000; includeSubDomains"
                for k, v in extra.items():
                    if k not in have:
                        headers.append((k, v))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)


class RedactingFilter(logging.Filter):
    """Strip PAN/GSTIN/phone/email/account numbers from every log record (hard rule 7).

    Arguments are redacted in place and keep their shape: uvicorn's access formatter unpacks
    `record.args` as a tuple, so it must not be replaced with a pre-formatted string."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {
                k: redact(v) if isinstance(v, str) else v for k, v in record.args.items()
            }
        return True


def install_log_redaction() -> None:
    """Filters on handlers apply to every record they emit, including propagated ones."""
    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access"):
        for handler in logging.getLogger(name).handlers:
            if not any(isinstance(f, RedactingFilter) for f in handler.filters):
                handler.addFilter(RedactingFilter())
    logging.getLogger("httpx").setLevel(logging.WARNING)
