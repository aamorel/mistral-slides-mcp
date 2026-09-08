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
    def test_auth_gate_and_health(self):
        with patch.dict(os.environ, ENV), TestClient(server.create_app()) as client:
            self.assertEqual(client.get('/health').status_code, 200)
            for path in ('/mcp', '/auth/status', '/auth/google/start'):
                self.assertEqual(client.get(path).status_code, 401)
            self.assertEqual(client.get('/auth/google/callback?state=invalid').status_code, 400)
            with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"TOKEN_DB_PATH": str(Path(temp) / 'tokens.db')}):
                result = client.get('/auth/status', auth=('admin', 'test-secret'))
                self.assertEqual(result.json()['linked'], False)
                result = client.get('/auth/google/start', auth=('admin', 'test-secret'), follow_redirects=False)
                self.assertEqual(result.status_code, 307)
                self.assertIn('code_challenge=', result.headers['location'])
                self.assertIn('HttpOnly', result.headers['set-cookie'])

    def test_connector_header_compatibility_and_safe_logs(self):
        from starlette.responses import JSONResponse
        from starlette.applications import Starlette
        from starlette.routing import Route

        async def endpoint(request):
            return JSONResponse({"ok": True})

        app = Starlette(routes=[Route('/{path:path}', endpoint, methods=['GET', 'POST'])])
        with TestClient(server.Authentication(app, 'test-secret')) as client:
            with self.assertLogs('uvicorn.error', level='INFO') as logs:
                for header in ('Bearer test-secret', 'test-secret', '  bearer   test-secret  '):
                    self.assertEqual(client.post('/mcp', headers={'Authorization': header}).status_code, 200)
                self.assertEqual(client.post('/mcp').status_code, 401)
                self.assertEqual(client.post('/mcp', headers={'Authorization': 'Bearer wrong-private-token'}).status_code, 401)
                client.get('/auth/google/callback?code=private-google-code&state=private-state')
            output = '\n'.join(logs.output)
            for secret in ('test-secret', 'wrong-private-token', 'private-google-code', 'private-state'):
                self.assertNotIn(secret, output)
            for outcome in ('auth=accepted', 'auth=missing', 'auth=invalid', 'status=200', 'status=401'):
                self.assertIn(outcome, output)

    def test_callback_state_pkce_and_replay(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {**ENV, "TOKEN_DB_PATH": str(Path(temp) / 'tokens.db')}), TestClient(server.create_app(), base_url='https://example.com') as client:
            client.get('/auth/google/start', auth=('admin', 'test-secret'), follow_redirects=False)
            state = client.cookies.get('google_oauth_state')
            db = auth.connect()
            verifier = db.execute('select code_verifier from oauth_states where state = ?', (state,)).fetchone()[0]
            db.close()
            flow = MagicMock()
            flow.credentials.to_json.return_value = '{"refresh_token": "fake"}'
            with patch.object(auth, 'create_flow', return_value=flow):
                response = client.get(f'/auth/google/callback?state={state}&code=fake')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(flow.code_verifier, verifier)
                self.assertTrue(flow.fetch_token.call_args.kwargs['authorization_response'].startswith('https://example.com/'))
                self.assertEqual(client.get(f'/auth/google/callback?state={state}&code=fake').status_code, 400)
                flow.fetch_token.assert_called_once()
            db = auth.connect()
            self.assertEqual(db.execute("select connection_id from google_tokens").fetchone()[0], 'default')
            db.close()

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
        with patch.object(auth, 'load_credentials', side_effect=RuntimeError('Google is not linked')), patch.object(outline, 'generate_outline') as generate:
            with self.assertRaisesRegex(ToolError, 'not linked'):
                asyncio.run(server.generate_presentation('Demo'))
            generate.assert_not_called()

    def test_success_contract_and_partial_failure(self):
        service = MagicMock()
        service.presentations.return_value.create.return_value.execute.return_value = {'presentationId': 'deck123'}
        with patch.object(slides, 'build', return_value=service):
            result = slides.create_deck(MagicMock(), OUTLINE)
            self.assertEqual(result, {'presentation_id': 'deck123', 'presentation_url': 'https://docs.google.com/presentation/d/deck123/edit', 'title': 'Demo'})
            requests = service.presentations.return_value.batchUpdate.call_args.kwargs['body']['requests']
            self.assertEqual(sum('createSlide' in r for r in requests), 1)
            service.presentations.return_value.batchUpdate.return_value.execute.side_effect = Exception('private upstream detail')
            with self.assertRaisesRegex(RuntimeError, 'deck123/edit') as caught:
                slides.create_deck(MagicMock(), OUTLINE)
            self.assertNotIn('private upstream detail', str(caught.exception))

    def test_old_database_and_refresh_persistence(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'TOKEN_DB_PATH': str(Path(temp) / 'tokens.db')}):
            db = auth.connect()
            db.execute("insert into google_tokens values ('default', '{}', 1)")
            db.commit()
            db.close()
            creds = MagicMock(valid=False)
            creds.to_json.return_value = '{"refreshed": true}'
            with patch.object(auth.Credentials, 'from_authorized_user_info', return_value=creds):
                self.assertIs(auth.load_credentials(), creds)
            creds.refresh.assert_called_once()
            db = auth.connect()
            self.assertEqual(json.loads(db.execute('select credentials_json from google_tokens').fetchone()[0]), {'refreshed': True})
            db.close()


if __name__ == '__main__':
    unittest.main()
