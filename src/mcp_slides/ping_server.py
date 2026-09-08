"""No-op MCP server for Vibe custom Connector investigation."""

from __future__ import annotations

import os
import json
import logging
from typing import Any

import uvicorn
from mcp.server.mcpserver import MCPServer
from starlette.types import ASGIApp, Receive, Scope, Send


mcp = MCPServer(
    "mcp-slides-investigation",
    instructions=(
        "Investigation server for validating Vibe custom MCP Connector "
        "registration, transport, and tool invocation."
    ),
)


logger = logging.getLogger("mcp_slides.investigation")


@mcp.tool()
def ping() -> dict[str, Any]:
    """Return a static health payload for Connector smoke tests."""
    return {
        "ok": True,
        "server": "mcp-slides-investigation",
        "purpose": "Validate Vibe can discover and call a custom MCP tool.",
    }


class InvestigationMiddleware:
    """Log safe request metadata and optionally enforce static bearer auth."""

    def __init__(self, app: ASGIApp, bearer_token: str | None) -> None:
        self.app = app
        self.bearer_token = bearer_token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        method = str(scope.get("method", ""))

        if method == "GET" and path == "/health":
            await self._send_json(send, 200, {"ok": True})
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        auth_header = headers.get("authorization", "")
        auth_scheme = auth_header.split(" ", 1)[0] if auth_header else None

        logger.info(
            "http_request %s",
            json.dumps(
                {
                    "method": method,
                    "path": path,
                    "host": headers.get("host"),
                    "user_agent": headers.get("user-agent"),
                    "origin": headers.get("origin"),
                    "referer": headers.get("referer"),
                    "x_forwarded_for": headers.get("x-forwarded-for"),
                    "authorization_present": bool(auth_header),
                    "authorization_scheme": auth_scheme,
                    "mcp_session_id_present": "mcp-session-id" in headers,
                },
                sort_keys=True,
            ),
        )

        if self.bearer_token and path.startswith("/mcp"):
            expected = f"Bearer {self.bearer_token}"
            if auth_header != expected:
                await self._send_json(
                    send,
                    401,
                    {
                        "error": "invalid_token",
                        "error_description": "Bearer authentication required",
                    },
                    [(b"www-authenticate", b'Bearer error="invalid_token"')],
                )
                return

        await self.app(scope, receive, send)

    async def _send_json(
        self,
        send: Send,
        status: int,
        payload: dict[str, Any],
        extra_headers: list[tuple[bytes, bytes]] | None = None,
    ) -> None:
        body = json.dumps(payload).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
        ]
        headers.extend(extra_headers or [])
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})


def create_app() -> ASGIApp:
    base_app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        host=os.getenv("HOST", "0.0.0.0"),
    )
    bearer_token = os.getenv("CONNECTOR_BEARER_TOKEN")
    if bearer_token:
        logger.info("static bearer auth enabled for /mcp")
    else:
        logger.info("static bearer auth disabled")
    return InvestigationMiddleware(base_app, bearer_token)


def main() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    uvicorn.run(
        create_app(),
        host=host,
        port=port,
        log_level=os.getenv("LOG_LEVEL", "INFO").lower(),
    )


if __name__ == "__main__":
    main()
