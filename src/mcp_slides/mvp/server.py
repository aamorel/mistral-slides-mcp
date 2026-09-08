"""Presentation generator with per-user connector OAuth."""
from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Annotated, Literal
from urllib.parse import urlparse

import uvicorn
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.middleware.client_auth import ClientAuthenticator
from mcp.server.auth.routes import cors_middleware
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import RequestBodyLimitMiddleware
from pydantic import Field
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import auth, outline, slides
from .oauth import GoogleOAuthProvider, SCOPE, ResourceTokenHandler

async def generate_presentation(
    topic: Annotated[str | None, Field(min_length=1, max_length=1000)] = None,
    slide_count: Annotated[int, Field(ge=1, le=6, strict=True)] = 3,
    audience: Annotated[str | None, Field(max_length=300)] = None,
    tone: Annotated[str | None, Field(max_length=200)] = None,
    basis: Literal["topic", "content"] = "topic",
    source_content: Annotated[str | None, Field(min_length=1, max_length=20000)] = None,
    instructions: Annotated[str | None, Field(max_length=2000)] = None,
) -> dict[str, str]:
    """Create 1–6 slides in the authenticated user's Google Drive.

    Use basis="topic" to develop a presentation from a required topic.
    Use basis="content" to organize supplied material; source_content is required
    and topic is optional context. Copy relevant notes or conversation content
    into source_content: this tool cannot see the conversation or fetch URLs/files.
    Content mode preserves supplied claims without adding facts unless instructions
    explicitly request an expansion. Put purpose, emphasis, constraints, and any
    requested expansion in instructions. Infer the basis from the user's intent;
    ask only if ambiguity would materially change the result. Briefly state the
    chosen approach in chat without requiring an extra confirmation.

    After a successful call, copy presentation_url from the result verbatim into
    the user's clickable link. Never invent a URL, reconstruct the opaque Google
    presentation ID, or add query parameters. Only report a created presentation
    when this tool actually returns a successful result.
    """
    if basis not in ("topic", "content"):
        raise ToolError('Basis must be "topic" or "content".')
    if basis == "topic":
        if not topic or not topic.strip():
            raise ToolError("Topic is required and must not be blank for topic basis.")
        if source_content is not None:
            raise ToolError('Use basis="content" when supplying source_content.')
    elif not source_content or not source_content.strip():
        raise ToolError("Source content is required and must not be blank for content basis.")
    if topic is not None and not topic.strip():
        raise ToolError("Topic must not be blank when supplied.")
    token = get_access_token()
    if not token or not token.subject or token.subject == "default":
        raise ToolError("Connect this connector to your Google account in Vibe first.")
    try:
        creds = await run_in_threadpool(auth.load_credentials, token.subject)
    except RuntimeError as exc:
        raise ToolError(str(exc)) from None
    except Exception:
        raise ToolError("Google credentials could not be loaded. Check the token database and reconnect Google.") from None
    try:
        content = await run_in_threadpool(
            outline.generate_outline, topic.strip() if topic else None, slide_count, audience, tone,
            os.getenv("MISTRAL_MODEL", outline.DEFAULT_MODEL),
            basis=basis, source_content=source_content, instructions=instructions,
        )
    except Exception:
        raise ToolError("Mistral could not generate a valid outline. Check the API key or try again.") from None
    try:
        result = await run_in_threadpool(slides.create_deck, creds, content)
        # Correlate the exact returned URL with a reported link without exposing
        # private deck IDs, titles, URLs or Google credentials in Railway logs.
        logger.info("presentation_result url_sha256=%s",
                    hashlib.sha256(result["presentation_url"].encode()).hexdigest())
        return result
    except RuntimeError as exc:
        raise ToolError(str(exc)) from None
    except Exception:
        raise ToolError("Google Slides could not create the deck. Check Google access and API availability.") from None


logger = logging.getLogger("uvicorn.error")


class RequestLog:
    """Fixed route labels and outcomes only; never log headers, bodies or query strings."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope["path"]
        known = {"/mcp", "/mcp/", "/health", "/auth/google/start", "/auth/google/callback",
                 "/auth/status", "/authorize", "/token", "/register", "/revoke",
                 "/.well-known/oauth-authorization-server", "/.well-known/oauth-protected-resource",
                 "/.well-known/oauth-protected-resource/mcp"}
        route = path if path in known else "other"
        method = scope.get("method", "")
        method = method if method in {"GET", "POST", "DELETE", "HEAD", "OPTIONS", "PUT", "PATCH"} else "other"
        present = bool(dict(scope.get("headers", [])).get(b"authorization"))
        started = time.monotonic()
        if path != "/health":
            logger.info("http_request method=%s route=%s authorization_present=%s", method, route, present)

        async def logged_send(message):
            if message["type"] == "http.response.start" and path != "/health":
                user = scope.get("user")
                result = ("accepted" if getattr(user, "is_authenticated", False) else
                          "invalid" if present else "missing") if path.startswith('/mcp') else "not_required"
                logger.info("http_response method=%s route=%s status=%s auth=%s elapsed_ms=%d",
                            method, route, message["status"], result, int((time.monotonic()-started)*1000))
            await send(message)
        await self.app(scope, receive, logged_send)


def create_app():
    required = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "PUBLIC_BASE_URL", "MISTRAL_API_KEY")
    missing = [name for name in required if not os.getenv(name, "").strip()]
    if missing:
        raise RuntimeError("Missing configuration: " + ", ".join(missing))
    base_url = os.environ["PUBLIC_BASE_URL"].rstrip('/')
    base = urlparse(base_url)
    if (base.query or base.fragment or base.username or base.password or base.path or not base.hostname or
        not (base.scheme == "https" or (base.scheme == "http" and base.hostname in ("localhost", "127.0.0.1", "::1")))):
        raise RuntimeError("PUBLIC_BASE_URL must be an HTTPS origin (HTTP allowed only on localhost).")
    provider = GoogleOAuthProvider(base_url)
    mcp = MCPServer(
        "mcp-slides", instructions=("Create Google Slides presentations in the authenticated user's own Google Drive. "
                      "Copy presentation_url verbatim from a successful generate_presentation result. "
                      "Never fabricate or rewrite presentation IDs or URLs."),
        auth_server_provider=provider,
        auth=AuthSettings(issuer_url=base_url, resource_server_url=provider.resource,
            required_scopes=[SCOPE], validate_token_resource=True,
            client_registration_options=ClientRegistrationOptions(enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE]),
            revocation_options=RevocationOptions(enabled=True)),
    )
    mcp.tool()(generate_presentation)

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request):
        return JSONResponse({"ok": True, "server": "mcp-slides", "auth": "oauth"})

    @mcp.custom_route("/auth/google/start", methods=["GET", "POST"])
    async def start(request):
        if request.method == "POST":
            return await provider.consent_submit(request)
        return await run_in_threadpool(provider.consent_page, request)

    @mcp.custom_route("/auth/google/callback", methods=["GET"])
    async def callback(request):
        return await run_in_threadpool(provider.google_callback, request)

    @mcp.custom_route("/auth/status", methods=["GET"])
    async def status(request):
        token = get_access_token()
        if not token:
            return JSONResponse({"linked": False, "action": "Connect this connector in Vibe to authorize Google."}, status_code=401)
        return JSONResponse({"linked": True}, headers={"Cache-Control": "no-store"})

    @mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])
    async def resource_metadata(request):
        return JSONResponse({"resource": provider.resource, "authorization_servers": [base_url],
                             "scopes_supported": [SCOPE], "bearer_methods_supported": ["header"]})

    app = mcp.streamable_http_app(streamable_http_path="/mcp", json_response=True,
                                   stateless_http=True, host=os.getenv("HOST", "0.0.0.0"))
    # This SDK version validates PKCE/client/redirect/scope but does not check
    # the token request's resource parameter. Reject resource substitution.
    handler = ResourceTokenHandler(provider, ClientAuthenticator(provider))
    for index, route in enumerate(app.routes):
        if getattr(route, 'path', None) == '/token':
            app.routes[index] = Route('/token', endpoint=RequestBodyLimitMiddleware(
                cors_middleware(handler.handle, ['POST', 'OPTIONS']), 65536), methods=['POST', 'OPTIONS'])
    return RequestLog(app)


def main():
    uvicorn.run(create_app(), host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")),
                access_log=False)


if __name__ == "__main__":
    main()
