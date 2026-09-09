import asyncio
import copy
import json
import os
import struct
from io import BytesIO
from PIL import Image
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import ValidationError
from starlette.testclient import TestClient
from mcp.server.mcpserver.exceptions import ToolError
from mcp_slides.mvp import auth, backgrounds, preferences, server, slides

SETTINGS = dict(background='#FAF5EB', title_color='#244B63', body_color='#263238', font_family='Georgia', gradient=False, gradient_color='#93B4E8')
buffer = BytesIO()
Image.new('RGB', (1600, 900), '#FAF5EB').save(buffer, format='PNG')
PNG = buffer.getvalue()
ENV = {'GOOGLE_CLIENT_ID': 'test', 'GOOGLE_CLIENT_SECRET': 'test',
       'PUBLIC_BASE_URL': 'https://example.com', 'MISTRAL_API_KEY': 'test',
       'GOOGLE_ALLOWED_DOMAIN': 'example.com', 'GOOGLE_ALLOWED_EMAILS': ''}
OUTLINE = {'title': 'Phones', 'slides': [{'type': 'bullets', 'title': 'History', 'bullets': ['A', 'B', 'C']}]}


class PreferenceAndImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {**ENV, 'TOKEN_DB_PATH': str(Path(self.temp.name) / 'tokens.db')})
        self.env.start()
        self.addCleanup(self.env.stop)
        with closing(auth.connect()) as db:
            for subject in ('alice', 'bob'):
                auth.save_identity(db, subject, {'sub': subject, 'hd': 'example.com'})
                db.execute('insert into google_tokens values (?, ?, ?)', (subject, '{}', 1))
            db.commit()

    def test_preferences_persist_and_are_isolated_reset_and_revoked(self):
        self.assertFalse(preferences.get_style('alice')['saved'])
        preferences.set_style('alice', preferences.StyleSettings(**SETTINGS))
        self.assertEqual(preferences.get_style('alice')['settings'], SETTINGS)
        self.assertIn('Georgia', preferences.get_style('alice')['markdown'])
        self.assertFalse(preferences.get_style('bob')['saved'])
        preferences.reset_style('alice')
        self.assertFalse(preferences.get_style('alice')['saved'])
        preferences.set_style('alice', preferences.StyleSettings(**SETTINGS))
        with closing(auth.connect()) as db:
            auth.revoke_subject(db, 'alice')
            db.commit()
        self.assertFalse(preferences.get_style('alice')['saved'])
        with self.assertRaises(RuntimeError):
            preferences.set_style('alice', preferences.StyleSettings(**SETTINGS))

    def test_style_validation_rejects_unknown_settings_and_poor_contrast(self):
        for settings in ({**SETTINGS, 'background': 'cream'}, {**SETTINGS, 'font_family': 'Unknown'},
                         {**SETTINGS, 'body_color': '#FAF5EB'}, {**SETTINGS, 'layout': 'magazine'}, {}):
            with self.assertRaises(ValidationError):
                preferences.StyleSettings(**settings)

    def test_temporary_image_route_expiry_cleanup_and_revocation(self):
        token, url = backgrounds.publish_image('alice', PNG)
        self.assertTrue(url.endswith(token + '.png'))
        app = server.create_app()
        with TestClient(app) as client:
            result = client.get('/assets/' + token + '.png')
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.content, PNG)
            self.assertEqual(result.headers['cache-control'], 'no-store')
            self.assertEqual(client.get('/assets/wrong.png').status_code, 404)
            with patch.object(backgrounds.time, 'time', return_value=9999999999):
                self.assertEqual(client.get('/assets/' + token + '.png').status_code, 404)
        token, _ = backgrounds.publish_image('alice', PNG)
        backgrounds.remove_image(token)
        self.assertIsNone(backgrounds.read_image(token))
        token, _ = backgrounds.publish_image('alice', PNG)
        with closing(auth.connect()) as db:
            auth.revoke_subject(db, 'alice')
            db.commit()
        self.assertIsNone(backgrounds.read_image(token))

    def test_mistral_image_download_and_payload_checks(self):
        for data, succeeds in ((PNG, True), (b'html', False), (PNG[:16] + struct.pack('>II', 99999, 99999), False)):
            fake = MagicMock()
            fake.__enter__.return_value = fake
            fake.beta.conversations.start.return_value = SimpleNamespace(outputs=[SimpleNamespace(content=[
                SimpleNamespace(type='tool_file', tool='image_generation', file_id='file1')])])
            download = fake.files.download.return_value
            download.iter_bytes.return_value = iter([data])
            with patch.object(backgrounds, 'Mistral', return_value=fake):
                if succeeds:
                    self.assertTrue(backgrounds.generate_image('Phones', {}).startswith(b'\x89PNG'))
                else:
                    with self.assertRaises((ValueError, OSError)):
                        backgrounds.generate_image('Phones', {})
            download.close.assert_called_once()
            self.assertFalse(fake.beta.conversations.start.call_args.kwargs['store'])

    def test_missing_image_and_oversize_download_fail(self):
        fake = MagicMock()
        fake.__enter__.return_value = fake
        fake.beta.conversations.start.return_value = SimpleNamespace(outputs=[])
        with patch.object(backgrounds, 'Mistral', return_value=fake):
            with self.assertRaises(ValueError):
                backgrounds.generate_image('Phones', {})
        fake.beta.conversations.start.return_value = SimpleNamespace(outputs=[SimpleNamespace(content=[
            SimpleNamespace(type='tool_file', tool='image_generation', file_id='file1')])])
        fake.files.download.return_value.iter_bytes.return_value = iter([PNG])
        with patch.object(backgrounds, 'Mistral', return_value=fake), patch.object(backgrounds, 'MAX_BYTES', 1):
            with self.assertRaises(ValueError):
                backgrounds.generate_image('Phones', {})

    def test_generation_uses_saved_style_and_cleans_up(self):
        preferences.set_style('alice', preferences.StyleSettings(**SETTINGS))
        with patch.object(server, 'get_access_token', return_value=SimpleNamespace(subject='alice')), patch.object(auth, 'load_credentials', return_value='creds'), patch.object(server.outline, 'generate_outline', return_value=OUTLINE), patch.object(backgrounds, 'generate_image', return_value=PNG) as image, patch.object(slides, 'create_deck', return_value={'presentation_url': 'https://example.com/deck'}) as render:
            result = asyncio.run(server.generate_presentation('Phones'))
            palette = preferences.StyleSettings(**SETTINGS).palette()
            self.assertEqual(render.call_args.kwargs['palette'], palette)
            image.assert_called_once_with('Phones', palette)
            self.assertEqual(result['style_settings'], SETTINGS)
            with closing(auth.connect()) as db:
                self.assertEqual(db.execute('select count(*) from temporary_images').fetchone()[0], 0)
        self.assertEqual(preferences.get_style('alice')['settings'], SETTINGS)

    def test_image_failure_prevents_deck_creation_and_google_failure_cleans_image(self):
        with patch.object(server, 'get_access_token', return_value=SimpleNamespace(subject='alice')), patch.object(auth, 'load_credentials', return_value='creds'), patch.object(server.outline, 'generate_outline', return_value=OUTLINE), patch.object(backgrounds, 'generate_image', side_effect=ValueError('private')) as generate, patch.object(slides, 'create_deck') as render:
            with self.assertRaisesRegex(ToolError, 'No deck was created'):
                asyncio.run(server.generate_presentation('Phones'))
            render.assert_not_called()
            generate.side_effect = None
            generate.return_value = PNG
            render.side_effect = RuntimeError('A deck was created but could not be populated: example')
            with self.assertRaisesRegex(ToolError, 'could not be populated'):
                asyncio.run(server.generate_presentation('Phones'))
            with closing(auth.connect()) as db:
                self.assertEqual(db.execute('select count(*) from temporary_images').fetchone()[0], 0)

    def test_cover_only_has_one_image_and_editable_title(self):
        fake = MagicMock()
        fake.presentations.return_value.create.return_value.execute.return_value = {'presentationId': 'deck1'}
        fake.presentations.return_value.get.return_value.execute.return_value = {}
        with patch.object(slides, 'build', return_value=fake):
            result = slides.create_deck(None, OUTLINE, palette=preferences.StyleSettings(**SETTINGS).palette(), cover_image_url='https://example.com/image.png')
        requests = fake.presentations.return_value.batchUpdate.call_args.kwargs['body']['requests']
        images = [r['createImage'] for r in requests if 'createImage' in r]
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]['elementProperties']['pageObjectId'], 'mvp_slide_0')
        self.assertEqual(result['total_slide_count'], 2)
        palette = preferences.StyleSettings(**SETTINGS).palette()
        background = next(r['updatePageProperties'] for r in requests if 'updatePageProperties' in r)
        self.assertEqual(background['pageProperties']['pageBackgroundFill']['solidFill']['color']['rgbColor'], slides.rgb(palette['background']))
        for request in (r['updateTextStyle'] for r in requests if 'updateTextStyle' in r):
            kind = 'body' if request['objectId'] == 'mvp_body_1' else 'title'
            self.assertEqual(request['style']['fontFamily'], 'Georgia')
            self.assertEqual(request['style']['foregroundColor']['opaqueColor']['rgbColor'], slides.rgb(palette[kind]))

        titles = [r['insertText'] for r in requests if 'insertText' in r]
        self.assertIn({'objectId': 'mvp_title_0', 'insertionIndex': 0, 'text': 'Phones'}, titles)

    def test_partial_preferences_merge_and_invalid_merge_leaves_saved_state_intact(self):
        preferences.set_style('alice', preferences.StyleSettings(**SETTINGS))
        updated = preferences.set_style('alice', preferences.StyleChanges(title_color='#112233'))
        expected = {**SETTINGS, 'title_color': '#112233'}
        self.assertEqual(updated['settings'], expected)
        with self.assertRaises(ValidationError):
            preferences.set_style('alice', preferences.StyleChanges(background='#112233'))
        self.assertEqual(preferences.get_style('alice')['settings'], expected)
        self.assertEqual(preferences.get_style('bob')['settings'], preferences.DEFAULT_STYLE.model_dump())
        for changes in ({}, {'title_color': None}, {'font_family': 'Unknown'}, {'extra': 'value'}):
            with self.assertRaises(ValidationError):
                preferences.StyleChanges(**changes)
