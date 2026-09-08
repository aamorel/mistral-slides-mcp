"""Exercise discovery and invocation over real Streamable HTTP with mocked APIs."""
import asyncio
import os
import socket
import unittest
from unittest.mock import patch

import httpx2
import uvicorn
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp_slides.mvp import server

ENV = {'CONNECTOR_BEARER_TOKEN': 'protocol-secret', 'GOOGLE_CLIENT_ID': 'fake',
       'GOOGLE_CLIENT_SECRET': 'fake', 'PUBLIC_BASE_URL': 'http://127.0.0.1',
       'MISTRAL_API_KEY': 'fake'}
RESULT = {'presentation_id': 'test123', 'presentation_url': 'https://docs.google.com/presentation/d/test123/edit', 'title': 'Test'}


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_validation_and_generation(self):
        with patch.dict(os.environ, ENV), patch.object(server.auth, 'load_credentials', return_value=object()), patch.object(server.outline, 'generate_outline', return_value={}) as generate, patch.object(server.slides, 'create_deck', return_value=RESULT):
            sock = socket.socket()
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
            http_server = uvicorn.Server(uvicorn.Config(server.create_app(), log_level='error', access_log=False))
            task = asyncio.create_task(http_server.serve(sockets=[sock]))
            try:
                for _ in range(100):
                    if http_server.started:
                        break
                    await asyncio.sleep(.02)
                self.assertTrue(http_server.started)
                async with httpx2.AsyncClient(headers={'Authorization': 'Bearer protocol-secret'}) as http:
                    async with Client(streamable_http_client(f'http://127.0.0.1:{port}/mcp', http_client=http)) as client:
                        tools = await client.list_tools()
                        self.assertEqual([t.name for t in tools.tools], ['generate_presentation'])
                        for arguments in ({'topic': 'Demo', 'slide_count': 7}, {'topic': '   '}, {'topic': 'Demo', 'slide_count': True}):
                            result = await client.call_tool('generate_presentation', arguments)
                            self.assertTrue(result.is_error)
                        generate.assert_not_called()
                        result = await client.call_tool('generate_presentation', {'topic': 'Demo'})
                        self.assertFalse(result.is_error)
                        self.assertEqual(result.structured_content, RESULT)
            finally:
                http_server.should_exit = True
                await task
                sock.close()
