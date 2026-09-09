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
from mcp_slides import server, auth, preferences
from mcp_slides.oauth import GoogleOAuthProvider, SCOPE

ENV = {'CONNECTOR_BEARER_TOKEN': 'protocol-secret', 'GOOGLE_CLIENT_ID': 'fake',
       'GOOGLE_CLIENT_SECRET': 'fake', 'PUBLIC_BASE_URL': 'http://127.0.0.1',
       'MISTRAL_API_KEY': 'fake', 'GOOGLE_ALLOWED_DOMAIN': 'example.com', 'GOOGLE_ALLOWED_EMAILS': ''}
RESULT = {'presentation_id': 'test123', 'presentation_url': 'https://docs.google.com/presentation/d/test123/edit', 'title': 'Test', 'style_settings': preferences.DEFAULT_STYLE.model_dump(), 'style_guidance': server.STYLE_GUIDANCE}


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_validation_and_generation(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {**ENV, 'TOKEN_DB_PATH': str(Path(temp) / 'tokens.db')}), patch.object(server.auth, 'load_credentials', side_effect=lambda subject: subject) as credentials, patch.object(server.outline, 'generate_outline', return_value={'title': 'Demo'}) as generate, patch.object(server.slides, 'create_deck', return_value=RESULT) as render, patch.object(server.backgrounds, 'generate_image', return_value=b'png') as image_generate, patch.object(server.backgrounds, 'publish_image', return_value=('token', 'https://example.com/cover.png')), patch.object(server.backgrounds, 'remove_image'):
            provider = GoogleOAuthProvider(ENV['PUBLIC_BASE_URL'])
            with closing(auth.connect()) as db:
                for subject in ('alice', 'bob'):
                    auth.save_identity(db, subject, {'sub': subject, 'hd': 'example.com'})
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
                        discovered = {t.name: t for t in tools.tools}
                        self.assertEqual(set(discovered), {'generate_presentation', 'get_presentation', 'edit_slide', 'add_slide', 'get_default_style', 'set_default_style', 'reset_default_style', 'set_presentation_style', 'set_slide_image'})
                        self.assertFalse(discovered['set_slide_image'].annotations.read_only_hint)
                        self.assertTrue(discovered['set_slide_image'].annotations.destructive_hint)
                        self.assertEqual(set(discovered['set_slide_image'].input_schema['required']),
                                         {'presentation_id', 'slide_id', 'expected_revision_id', 'image_url'})
                        self.assertTrue(discovered['get_presentation'].annotations.read_only_hint)
                        self.assertFalse(discovered['generate_presentation'].annotations.idempotent_hint)
                        self.assertFalse(discovered['generate_presentation'].annotations.destructive_hint)
                        self.assertFalse(discovered['edit_slide'].annotations.read_only_hint)
                        self.assertFalse(discovered['add_slide'].annotations.read_only_hint)
                        self.assertFalse(discovered['add_slide'].annotations.idempotent_hint)
                        self.assertEqual(set(discovered['add_slide'].input_schema['required']),
                                         {'presentation_id', 'expected_revision_id', 'instructions'})
                        self.assertIn('Repeated calls add separate slides', discovered['add_slide'].description)
                        self.assertIn('Preserves paragraph', discovered['edit_slide'].description)
                        with patch.object(server.insertion, 'add_deck_slide', return_value={'status': 'added'}) as add:
                            for args in ({'presentation_id': 'deck1', 'instructions': 'Add risks'},
                                         {'presentation_id': 'deck1', 'expected_revision_id': 'rev1', 'instructions': ' '},
                                         {'presentation_id': 'deck1', 'expected_revision_id': 'rev1', 'instructions': 'Add', 'after_slide_id': 'bad id'}):
                                self.assertTrue((await client.call_tool('add_slide', args)).is_error)
                            add.assert_not_called()
                            result = await client.call_tool('add_slide', {'presentation_id': 'deck1',
                                'expected_revision_id': 'rev1', 'instructions': 'Add risks', 'after_slide_id': 'slide1',
                                'source_content': 'Budget uncertain'})
                            self.assertFalse(result.is_error)
                            self.assertEqual(add.call_args.args[:6], ('alice', 'deck1', 'rev1', 'Add risks', 'Budget uncertain', 'slide1'))
                        credentials.reset_mock()
                        self.assertFalse(discovered['set_presentation_style'].annotations.read_only_hint)
                        schema = discovered['generate_presentation'].input_schema
                        self.assertEqual(schema['properties']['basis']['enum'], ['topic', 'content'])
                        self.assertEqual(schema['properties']['basis']['default'], 'topic')
                        self.assertIn('source_content', schema['properties'])
                        self.assertIn('instructions', schema['properties'])
                        self.assertNotIn('style', schema['properties'])
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
                        self.assertIn('stage=outline outcome=ok', diagnostic)
                        self.assertNotIn('request_id=local', diagnostic)
                        self.assertFalse(result.is_error)
                        self.assertEqual(result.structured_content, RESULT)
                        text_outputs = [part.text for part in result.content if part.type == 'text']
                        self.assertEqual(json.loads(text_outputs[0])['presentation_url'], RESULT['presentation_url'])
                        credentials.assert_called_with('alice')
                        self.assertEqual(render.call_args.args[0], 'alice')
                        self.assertEqual(render.call_args.kwargs['palette'], preferences.DEFAULT_STYLE.palette())
                        self.assertEqual(render.call_args.kwargs['cover_image_url'], 'https://example.com/cover.png')
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
                        settings = {'background': '#FAF5EB', 'title_color': '#244B63', 'body_color': '#263238', 'font_family': 'Georgia'}
                        result = await client.call_tool('set_default_style', {'settings': settings})
                        self.assertFalse(result.is_error)
                        self.assertTrue(result.structured_content['saved'])
                        settings = preferences.StyleSettings(**settings).model_dump()
                        result = await client.call_tool('get_default_style', {})
                        self.assertEqual(result.structured_content['settings'], settings)
                        result = await client.call_tool('generate_presentation', {'topic': 'Saved preference'})
                        self.assertFalse(result.is_error)
                        self.assertEqual(result.structured_content['style_settings'], settings)
                        self.assertEqual(render.call_args.kwargs['palette']['font_family'], 'Georgia')
                        with patch.object(server.styling, 'apply_style', return_value={'status': 'applied'}) as apply:
                            result = await client.call_tool('set_presentation_style', {'presentation_id': 'test123', 'expected_revision_id': 'rev1', 'use_default_style': True})
                            self.assertFalse(result.is_error)
                            self.assertEqual(apply.call_args.args[:3], ('alice', 'test123', 'rev1'))
                            self.assertEqual(apply.call_args.args[3].model_dump(), settings)
                            result = await client.call_tool('set_presentation_style', {
                                'presentation_id': 'https://docs.google.com/presentation/d/test123/edit#slide=id.slide1',
                                'expected_revision_id': 'rev1', 'changes': {'title_color': '#244B63'}})
                            self.assertFalse(result.is_error)
                            self.assertEqual(apply.call_args.args[1], 'test123')
                            self.assertEqual(apply.call_args.args[3].model_dump(exclude_unset=True), {'title_color': '#244B63'})
                            for reference in ('https://example.com/presentation/d/test123/edit', 'bad id'):
                                result = await client.call_tool('set_presentation_style', {
                                    'presentation_id': reference, 'expected_revision_id': 'rev1',
                                    'changes': {'title_color': '#244B63'}})
                                self.assertTrue(result.is_error)

                            for args in ({'presentation_id': 'test123'}, {'presentation_id': 'test123', 'expected_revision_id': ' '}):
                                self.assertTrue((await client.call_tool('set_presentation_style', args)).is_error)
                        result = await client.call_tool('set_default_style', {'settings': {'font_family': 'Verdana'}})
                        self.assertFalse(result.is_error)
                        self.assertEqual(result.structured_content['settings'], {**settings, 'font_family': 'Verdana'})
                        result = await client.call_tool('set_default_style', {'settings': {'gradient': False}})
                        self.assertFalse(result.is_error)
                        self.assertFalse(result.structured_content['settings']['gradient'])
                        result = await client.call_tool('generate_presentation', {'topic': 'Plain background'})
                        self.assertFalse(result.is_error)
                        self.assertFalse(render.call_args.kwargs['palette']['gradient'])
                        result = await client.call_tool('reset_default_style', {})
                        self.assertFalse(result.structured_content['saved'])
                        result = await client.call_tool('generate_presentation', {'topic': 'After reset'})
                        self.assertEqual(result.structured_content['style_settings'], preferences.DEFAULT_STYLE.model_dump())
                        self.assertEqual(render.call_args.kwargs['palette'], preferences.DEFAULT_STYLE.palette())
                        await client.call_tool('set_default_style', {'settings': settings})
                async with httpx2.AsyncClient(headers={'Authorization': 'Bearer ' + bob.access_token}) as http:
                    async with Client(streamable_http_client(f'http://127.0.0.1:{port}/mcp', http_client=http)) as client:
                        result = await client.call_tool('generate_presentation', {'topic': 'Bob deck'})
                        self.assertFalse(result.is_error)
                        credentials.assert_called_with('bob')
                        self.assertEqual(render.call_args.kwargs['palette'], preferences.DEFAULT_STYLE.palette())
                        preference = await client.call_tool('get_default_style', {})
                        self.assertFalse(preference.structured_content['saved'])
                        self.assertEqual(render.call_args.args[0], 'bob')
                        with patch.object(server.editing, 'get_deck', return_value={'revision_id': 'rev1', 'slides': []}) as read, patch.object(server.editing, 'edit_deck_slide', return_value={'status': 'unchanged', 'changes': []}) as edit:
                            for name, arguments in (
                                ('get_presentation', {'presentation_id': 'https://example.com/deck'}),
                                ('edit_slide', {'presentation_id': 'deck1', 'slide_id': 'slide1', 'instructions': 'Clarify'}),
                                ('edit_slide', {'presentation_id': 'deck1', 'slide_id': 'slide1', 'expected_revision_id': 'rev1', 'instructions': '   '}),
                            ):
                                self.assertTrue((await client.call_tool(name, arguments)).is_error)
                            read.assert_not_called()
                            edit.assert_not_called()
                            result = await client.call_tool('get_presentation', {'presentation_id': 'deck1'})
                            self.assertFalse(result.is_error)
                            read.assert_called_once_with('bob', 'deck1')
                            result = await client.call_tool('edit_slide', {
                                'presentation_id': 'deck1', 'slide_id': 'slide1',
                                'expected_revision_id': 'rev1', 'instructions': 'Clarify',
                                'source_content': 'Budget €5,000'})
                            self.assertFalse(result.is_error)
                            edit.assert_called_once_with('bob', 'deck1', 'slide1', 'rev1', 'Clarify', 'Budget €5,000')
            finally:
                http_server.should_exit = True
                await task
                sock.close()
