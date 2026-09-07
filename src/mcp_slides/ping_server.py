"""No-op MCP server for Vibe custom Connector investigation."""

from __future__ import annotations

import os
from typing import Any

from mcp.server.mcpserver import MCPServer


mcp = MCPServer(
    "mcp-slides-investigation",
    instructions=(
        "Investigation server for validating Vibe custom MCP Connector "
        "registration, transport, and tool invocation."
    ),
)


@mcp.tool()
def ping() -> dict[str, Any]:
    """Return a static health payload for Connector smoke tests."""
    return {
        "ok": True,
        "server": "mcp-slides-investigation",
        "purpose": "Validate Vibe can discover and call a custom MCP tool.",
    }


def main() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    mcp.run(
        transport="streamable-http",
        host=host,
        port=port,
        stateless_http=True,
        json_response=True,
    )


if __name__ == "__main__":
    main()
