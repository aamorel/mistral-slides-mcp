"""Smoke-test the local no-op MCP server."""

from __future__ import annotations

import anyio
import sys
from mcp import Client


async def run() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/mcp"
    async with Client(url) as client:
        tool_result = await client.list_tools()
        print("tools:", [tool.name for tool in tool_result.tools])
        result = await client.call_tool("ping", {})
        print("ping:", result.structured_content)


if __name__ == "__main__":
    anyio.run(run)
