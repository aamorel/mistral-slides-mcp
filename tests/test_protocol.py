"""Exercise discovery and invocation over real Streamable HTTP with mocked APIs."""
import asyncio
import hashlib
import json
import os
import socket
import tempfile
from pathlib import Path
from contextlib import closing
import unittest
from unittest.mock import patch

import httpx2
import uvicorn
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp_slides.mvp import server, auth
from mcp_slides.mvp.oauth import GoogleOAuthProvider, SCOPE

ENV = {'CONNECTOR_BEARER_TOKEN': 'protocol-secret', 'GOOGLE_CLIENT_ID': 'fake',
       'GOOGLE_CLIENT_SECRET': 'fake', 'PUBLIC_BASE_URL': 'http://127.0.0.1',
       'MISTRAL_API_KEY': 'fake'}
RESULT = {'presentation_id': 'test123', 'presentation_url': 'https://docs.google.com/presentation/d/test123/edit', 'title': 'Test'}


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_validation_and_generation(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {**ENV, 'TOKEN_DB_PATH': str(Path(temp) / 'tokens.db')}), patch.object(server.auth, 'load_credentials', side_effect=lambda subject: subject) as credentials, patch.object(server.outline, 'generate_outline', return_value={}) as generate, patch.object(server.slides, 'create_deck', return_value=RESULT) as render:
            provider = GoogleOAuthProvider(ENV['PUBLIC_BASE_URL'])
            with closing(auth.connect()) as db:
                for subject in ('alice', 'bob'):
                    db.execute('insert into google_tokens values (?, ?, ?)', (subject, '{}', 1))
                alice = provider.issue_tokens(db, 'shared-vibe-client', 'alice', [SCOPE])
                bob = provider.issue_tokens(db, 'shared-vibe-client', 'bob', [SCOPE])
                db.commit()
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
                async with httpx2.AsyncClient(headers={'Authorization': 'Bearer ' + alice.access_token}) as http:
                    async with Client(streamable_http_client(f'http://127.0.0.1:{port}/mcp', http_client=http)) as client:
                        tools = await client.list_tools()
                        self.assertEqual([t.name for t in tools.tools], ['generate_presentation'])
                        schema = tools.tools[0].input_schema
                        self.assertEqual(schema['properties']['basis']['enum'], ['topic', 'content'])
                        self.assertEqual(schema['properties']['basis']['default'], 'topic')
                        self.assertIn('source_content', schema['properties'])
                        self.assertIn('instructions', schema['properties'])
                        for arguments in ({'topic': 'Demo', 'slide_count': 7}, {'topic': '   '}, {'topic': 'Demo', 'slide_count': True},
                                          {}, {'basis': 'content'},
                                          {'basis': 'content', 'source_content': '   '},
                                          {'basis': 'content', 'source_content': 'Notes', 'topic': '   '},
                                          {'topic': 'Demo', 'source_content': 'Notes'},
                                          {'topic': 'Demo', 'basis': 'unknown'},
                                          {'basis': 'content', 'source_content': 'x' * 20001},
                                          {'topic': 'Demo', 'instructions': 'x' * 2001}):
                            result = await client.call_tool('generate_presentation', arguments)
                            self.assertTrue(result.is_error, arguments)
                        generate.assert_not_called()
                        credentials.assert_not_called()
                        render.assert_not_called()
                        with self.assertLogs('uvicorn.error', level='INFO') as logs:
                            result = await client.call_tool('generate_presentation', {'topic': 'Demo'})
                        diagnostic = '\n'.join(logs.output)
                        self.assertIn(hashlib.sha256(RESULT['presentation_url'].encode()).hexdigest(), diagnostic)
                        self.assertNotIn(RESULT['presentation_url'], diagnostic)
                        self.assertFalse(result.is_error)
                        self.assertEqual(result.structured_content, RESULT)
                        text_outputs = [part.text for part in result.content if part.type == 'text']
                        self.assertEqual(json.loads(text_outputs[0])['presentation_url'], RESULT['presentation_url'])
                        credentials.assert_called_with('alice')
                        self.assertEqual(render.call_args.args[0], 'alice')
                        self.assertEqual(generate.call_args.args[:4], ('Demo', 3, None, None))
                        self.assertEqual(generate.call_args.kwargs,
                                         {'basis': 'topic', 'source_content': None, 'instructions': None})
                        for framing in ({}, {'topic': 'Pilot recommendation'}):
                            result = await client.call_tool('generate_presentation', {
                                'basis': 'content', 'source_content': 'Pilot budget is €5,000.',
                                'instructions': 'Lead with the decision.', 'slide_count': 1,
                                'audience': 'Managers', 'tone': 'Direct', **framing})
                            self.assertFalse(result.is_error)
                            self.assertEqual(result.structured_content, RESULT)
                            self.assertEqual(generate.call_args.args[:4],
                                             (framing.get('topic'), 1, 'Managers', 'Direct'))
                            self.assertEqual(generate.call_args.kwargs, {
                                'basis': 'content', 'source_content': 'Pilot budget is €5,000.',
                                'instructions': 'Lead with the decision.'})
                            self.assertEqual(render.call_args.args[0], 'alice')
                async with httpx2.AsyncClient(headers={'Authorization': 'Bearer ' + bob.access_token}) as http:
                    async with Client(streamable_http_client(f'http://127.0.0.1:{port}/mcp', http_client=http)) as client:
                        result = await client.call_tool('generate_presentation', {'topic': 'Bob deck'})
                        self.assertFalse(result.is_error)
                        credentials.assert_called_with('bob')
                        self.assertEqual(render.call_args.args[0], 'bob')
            finally:
                http_server.should_exit = True
                await task
                sock.close()
