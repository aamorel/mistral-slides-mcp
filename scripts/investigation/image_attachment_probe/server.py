"""Run with python -m scripts.investigation.image_attachment_probe.server."""
import hmac
import logging
import os
from typing import Any

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from starlette.responses import JSONResponse

from .probe import inspect_reference


class BearerAuth:
    def __init__(self, app, token):
        self.app, self.expected = app, ("Bearer " + token).encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            if scope["path"] == "/health" and scope["method"] == "GET":
                return await JSONResponse({"ok": True})(scope, receive, send)
            supplied = dict(scope.get("headers", [])).get(b"authorization", b"")
            if not hmac.compare_digest(supplied, self.expected):
                return await JSONResponse({"error": "unauthorized"}, status_code=401,
                    headers={"WWW-Authenticate": "Bearer"})(scope, receive, send)
        await self.app(scope, receive, send)


def create_app():
    token = os.environ.get("PROBE_BEARER_TOKEN", "")
    if len(token) < 32 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError("PROBE_BEARER_TOKEN must contain at least 32 ASCII characters without whitespace.")
    allowed_host = os.environ.get("PROBE_ALLOWED_HOST", "").strip().lower() or None
    if allowed_host and ("." not in allowed_host or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for c in allowed_host)):
        raise ValueError("PROBE_ALLOWED_HOST must be one exact DNS hostname.")
    mcp = MCPServer("image-attachment-probe", log_level="CRITICAL",
                    instructions="Inspect only the user-selected attachment. Never invent references or reconstruct image bytes.")

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False,
                                         idempotent_hint=True, open_world_hint=True))
    async def inspect_attached_image(image_reference: str | None = None) -> dict[str, Any]:
        """Inspect the attached image. Pass its actual downloadable URL or exact file
        reference only if available in context; otherwise call with null. Never
        invent URLs, reconstruct bytes, substitute descriptions, or send cookies,
        API keys or session credentials. This tool does not modify slides.
        """
        return await inspect_reference(image_reference, allowed_host=allowed_host)

    # Suppress SDK/transport exception payloads, including validation inputs.
    logging.disable(logging.CRITICAL)
    app = mcp.streamable_http_app(streamable_http_path="/mcp", json_response=True,
        stateless_http=True, max_request_body_size=32768, host=os.getenv("HOST", "127.0.0.1"))
    return BearerAuth(app, token)


if __name__ == "__main__":
    uvicorn.run(create_app(), host=os.getenv("HOST", "127.0.0.1"),
                port=int(os.getenv("PORT", "8002")), access_log=False, log_level="critical")
