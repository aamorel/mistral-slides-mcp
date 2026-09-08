"""Deployed single-account presentation generator."""
from __future__ import annotations

import base64
import hmac
import logging
import time
import os
from typing import Annotated
from urllib.parse import urlparse

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from . import auth, outline, slides

mcp = MCPServer("mcp-slides", instructions="Create plain Google Slides presentations in the owner's linked Google account.")


@mcp.tool()
async def generate_presentation(
    topic: Annotated[str, Field(min_length=1, max_length=1000)],
    slide_count: Annotated[int, Field(ge=1, le=6, strict=True)] = 3,
    audience: Annotated[str | None, Field(max_length=300)] = None,
    tone: Annotated[str | None, Field(max_length=200)] = None,
) -> dict[str, str]:
    """Generate 1–6 title-and-bullet slides and return the Google Slides URL. All calls use the same linked Google account."""
    if not topic.strip():
        raise ToolError("Topic must not be blank.")
    try:
        creds = await run_in_threadpool(auth.load_credentials)
    except RuntimeError as exc:
        raise ToolError(str(exc)) from None
    except Exception:
        raise ToolError("Google credentials could not be loaded. Check the token database and reconnect Google.") from None
    try:
        content = await run_in_threadpool(
            outline.generate_outline, topic.strip(), slide_count, audience, tone,
            os.getenv("MISTRAL_MODEL", outline.DEFAULT_MODEL),
        )
    except Exception:
        raise ToolError("Mistral could not generate a valid outline. Check the API key or try again.") from None
    try:
        return await run_in_threadpool(slides.create_deck, creds, content)
    except RuntimeError as exc:
        raise ToolError(str(exc)) from None
    except Exception:
        raise ToolError("Google Slides could not create the deck. Check Google access and API availability.") from None


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    return JSONResponse({"ok": True, "server": "mcp-slides"})


# Synchronous Google SDK work runs outside the event loop.
@mcp.custom_route("/auth/google/start", methods=["GET"])
async def start(request):
    return await run_in_threadpool(auth.google_auth_start, request)


@mcp.custom_route("/auth/google/callback", methods=["GET"])
async def callback(request):
    return await run_in_threadpool(auth.google_auth_callback, request)


@mcp.custom_route("/auth/status", methods=["GET"])
async def status(request):
    return await run_in_threadpool(auth.google_auth_status, request)


logger = logging.getLogger("uvicorn.error")


def connector_token(header: str) -> str:
    """Keep the investigation connector's bare-token and whitespace compatibility."""
    value = header.strip()
    if value.lower().startswith("bearer "):
        return value.split(" ", 1)[1].strip()
    return value


class Authentication:
    def __init__(self, app, token):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        admin = path in ("/auth/google/start", "/auth/status")
        protected = admin or path.startswith("/mcp")
        header = dict(scope.get("headers", [])).get(b"authorization", b"").decode("latin-1").strip()
        scheme, _, value = header.partition(" ")
        auth_format = (scheme.lower() if scheme.lower() in ("bearer", "basic")
                       else "custom" if header else "none")
        auth_result = "not_required"
        if protected:
            provided = connector_token(header)
            if scheme.lower() == "basic":
                provided = ""
                if admin:
                    try:
                        user, _, password = base64.b64decode(value, validate=True).decode().partition(":")
                        provided = password if user == "admin" else ""
                    except (ValueError, UnicodeError):
                        pass
            auth_result = ("accepted" if hmac.compare_digest(provided.encode(), self.token.encode())
                           else "missing" if not header else "invalid")

        # Only fixed route labels and authentication outcomes: no query strings,
        # header values, token fingerprints, request bodies or Google codes.
        route = path if path in ("/mcp", "/mcp/", "/health", "/auth/google/start",
                                 "/auth/google/callback", "/auth/status") else "other"
        method = scope.get("method", "")
        method = method if method in ("GET", "POST", "DELETE", "HEAD", "OPTIONS", "PUT", "PATCH") else "other"
        started = time.monotonic()
        if path != "/health":
            logger.info("http_request method=%s route=%s auth=%s format=%s",
                        method, route, auth_result, auth_format)

        async def logged_send(message):
            if message["type"] == "http.response.start" and path != "/health":
                logger.info("http_response method=%s route=%s status=%s auth=%s elapsed_ms=%d",
                            method, route, message["status"], auth_result,
                            int((time.monotonic() - started) * 1000))
            await send(message)

        if auth_result in ("missing", "invalid"):
            challenge = 'Basic realm="Google linking", charset="UTF-8"' if admin else "Bearer"
            await JSONResponse({"error": "Authentication required"}, status_code=401,
                               headers={"WWW-Authenticate": challenge})(scope, receive, logged_send)
            return
        await self.app(scope, receive, logged_send)


def create_app():
    required = ("CONNECTOR_BEARER_TOKEN", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "PUBLIC_BASE_URL", "MISTRAL_API_KEY")
    missing = [name for name in required if not os.getenv(name, "").strip()]
    if missing:
        raise RuntimeError("Missing configuration: " + ", ".join(missing))
    base = urlparse(os.environ["PUBLIC_BASE_URL"])
    if base.scheme != "https" and not (base.scheme == "http" and base.hostname in ("localhost", "127.0.0.1")):
        raise RuntimeError("PUBLIC_BASE_URL must use HTTPS (HTTP allowed only on localhost).")
    token = os.environ["CONNECTOR_BEARER_TOKEN"].strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise RuntimeError("CONNECTOR_BEARER_TOKEN must not be empty")
    return Authentication(mcp.streamable_http_app(streamable_http_path="/mcp", json_response=True,
                          stateless_http=True, host=os.getenv("HOST", "0.0.0.0")), token)


def main():
    uvicorn.run(create_app(), host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")),
                access_log=False)


if __name__ == "__main__":
    main()
