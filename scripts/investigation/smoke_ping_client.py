"""Smoke-test the local no-op MCP server."""

from __future__ import annotations

import anyio
import os
import sys
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


async def run() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/mcp"
    bearer_token = os.getenv("MCP_BEARER_TOKEN")
    if bearer_token:
        http_client = httpx2.AsyncClient(headers={"Authorization": f"Bearer {bearer_token}"})
        server = streamable_http_client(url, http_client=http_client)
    else:
        server = url

    async with Client(server) as client:
        tool_result = await client.list_tools()
        print("tools:", [tool.name for tool in tool_result.tools])
        result = await client.call_tool("ping", {})
        print("ping:", result.structured_content)


if __name__ == "__main__":
    anyio.run(run)
