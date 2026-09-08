import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from starlette.testclient import TestClient
from mcp.server.mcpserver.exceptions import ToolError
from mcp_slides.mvp import auth, outline, server, slides

OUTLINE = {"title": "Demo", "slides": [{"title": "First", "bullets": ["A", "B", "C"]}]}
ENV = {"CONNECTOR_BEARER_TOKEN": "test-secret", "GOOGLE_CLIENT_ID": "test-client",
       "GOOGLE_CLIENT_SECRET": "test-client-secret", "PUBLIC_BASE_URL": "https://example.com",
       "MISTRAL_API_KEY": "test-key"}


class MVPTests(unittest.TestCase):
    def test_missing_config_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                server.create_app()

    def test_outline_validation(self):
        self.assertEqual(outline.validate_outline(OUTLINE, 1), OUTLINE)
        for bad in ({}, {**OUTLINE, 'slides': []}, {**OUTLINE, 'slides': [{'title': 'A', 'bullets': ['a']}]}):
            with self.assertRaises(ValueError):
                outline.validate_outline(bad, 1)

    def test_outline_retries_invalid_json_once(self):
        fake = MagicMock()
        fake.__enter__.return_value = fake
        def response(content):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
        fake.chat.complete.side_effect = [response('bad'), response(json.dumps(OUTLINE))]
        with patch.dict(os.environ, ENV), patch.object(outline, 'Mistral', return_value=fake):
            self.assertEqual(outline.generate_outline('Demo', 1, None, None, 'test'), OUTLINE)
        self.assertEqual(fake.chat.complete.call_count, 2)

    def test_missing_google_does_not_call_mistral(self):
        with patch.object(server, 'get_access_token', return_value=SimpleNamespace(subject='user-a')), patch.object(auth, 'load_credentials', side_effect=RuntimeError('Google is not linked')), patch.object(outline, 'generate_outline') as generate:
            with self.assertRaisesRegex(ToolError, 'not linked'):
                asyncio.run(server.generate_presentation('Demo'))
            generate.assert_not_called()

    def test_success_contract_and_partial_failure(self):
        service = MagicMock()
        service.presentations.return_value.create.return_value.execute.return_value = {'presentationId': 'deck123'}
        service.presentations.return_value.get.return_value.execute.return_value = {}
        with patch.object(slides, 'build', return_value=service):
            result = slides.create_deck(MagicMock(), OUTLINE)
            self.assertEqual(result, {'presentation_id': 'deck123', 'presentation_url': 'https://docs.google.com/presentation/d/deck123/edit', 'title': 'Demo'})
            requests = service.presentations.return_value.batchUpdate.call_args.kwargs['body']['requests']
            self.assertEqual(sum('createSlide' in r for r in requests), 1)
            service.presentations.return_value.batchUpdate.return_value.execute.side_effect = Exception('private upstream detail')
            with self.assertRaisesRegex(RuntimeError, 'deck123/edit') as caught:
                slides.create_deck(MagicMock(), OUTLINE)
            self.assertNotIn('private upstream detail', str(caught.exception))

    def test_generated_deck_has_exact_count_with_or_without_starter_slides(self):
        for initial_ids in ([], ['google_starter'], ['google_starter', 'google_second']):
            with self.subTest(initial_ids=initial_ids):
                service = MagicMock()
                service.presentations.return_value.create.return_value.execute.return_value = {'presentationId': 'deck123'}
                service.presentations.return_value.get.return_value.execute.return_value = {
                    'slides': [{'objectId': slide_id} for slide_id in initial_ids]}
                content = {'title': 'Six slides', 'slides': OUTLINE['slides'] * 6}
                with patch.object(slides, 'build', return_value=service):
                    slides.create_deck(MagicMock(), content)
                requests = service.presentations.return_value.batchUpdate.call_args.kwargs['body']['requests']
                final_ids = list(initial_ids)
                deleted = []
                for request in requests:
                    if 'createSlide' in request:
                        final_ids.append(request['createSlide']['objectId'])
                    elif 'deleteObject' in request:
                        slide_id = request['deleteObject']['objectId']
                        deleted.append(slide_id)
                        final_ids.remove(slide_id)
                self.assertEqual(final_ids, [f'mvp_slide_{i}' for i in range(1, 7)])
                self.assertEqual(deleted, initial_ids)
                self.assertEqual(sum('insertText' in r for r in requests), 12)
                service.presentations.return_value.batchUpdate.assert_called_once()

    def test_old_database_and_refresh_persistence(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'TOKEN_DB_PATH': str(Path(temp) / 'tokens.db')}):
            db = auth.connect()
            db.execute("insert into google_tokens values ('user-a', '{}', 1)")
            db.commit()
            db.close()
            creds = MagicMock(valid=False)
            creds.to_json.return_value = '{"refreshed": true}'
            with patch.object(auth.Credentials, 'from_authorized_user_info', return_value=creds):
                self.assertIs(auth.load_credentials('user-a'), creds)
            creds.refresh.assert_called_once()
            db = auth.connect()
            self.assertEqual(json.loads(db.execute('select credentials_json from google_tokens').fetchone()[0]), {'refreshed': True})
            db.close()


if __name__ == '__main__':
    unittest.main()
