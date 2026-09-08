"""Exercise both legs of OAuth through HTTP; Google token exchange is mocked."""
import base64
import hashlib
import json
import os
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from unittest.mock import MagicMock, patch

from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
from starlette.testclient import TestClient

from mcp_slides.mvp import auth, oauth, server

BASE = 'https://slides.example.com'
CALLBACK = 'https://vibe.example.com/oauth/callback'
VERIFIER = 'a' * 64
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).decode().rstrip('=')
ENV = {'GOOGLE_CLIENT_ID': 'google-client', 'GOOGLE_CLIENT_SECRET': 'google-secret',
       'PUBLIC_BASE_URL': BASE, 'MISTRAL_API_KEY': 'mistral-secret'}


def google_credentials(account='alice'):
    return Credentials(token=f'google-access-{account}', refresh_token=f'google-refresh-{account}',
                       token_uri='https://oauth2.googleapis.com/token', client_id='google-client',
                       client_secret='google-secret', scopes=[auth.DRIVE_FILE_SCOPE],
                       expiry=datetime.now() + timedelta(hours=1))


class OAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {**ENV, 'TOKEN_DB_PATH': str(Path(self.temp.name) / 'tokens.db')})
        self.env.start()
        self.client = TestClient(server.create_app(), base_url=BASE)
        self.client.__enter__()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.env.stop)
        self.addCleanup(self.client.__exit__, None, None, None)
        response = self.client.post('/register', json={
            'client_name': 'Vibe', 'redirect_uris': [CALLBACK],
            'grant_types': ['authorization_code', 'refresh_token'],
            'response_types': ['code'], 'token_endpoint_auth_method': 'client_secret_post',
        })
        self.assertEqual(response.status_code, 201, response.text)
        self.registration = response.json()

    def begin(self, **overrides):
        params = dict(client_id=self.registration['client_id'], redirect_uri=CALLBACK, response_type='code',
                      code_challenge=CHALLENGE, code_challenge_method='S256', scope=oauth.SCOPE,
                      state='vibe-state', resource=BASE + '/mcp')
        response = self.client.get('/authorize', params={**params, **overrides}, follow_redirects=False)
        return response

    def google_redirect(self):
        response = self.begin()
        self.assertEqual(response.status_code, 302, response.text)
        url = response.headers['location']
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertIn('Continue with Google', page.text)
        self.assertIn(CALLBACK, page.text)
        ticket = parse_qs(urlparse(url).query)['request'][0]
        csrf = self.client.cookies.get(oauth.COOKIE)
        response = self.client.post('/auth/google/start', data={'request': ticket, 'csrf': csrf}, follow_redirects=False)
        self.assertEqual(response.status_code, 303, response.text)
        query = parse_qs(urlparse(response.headers['location']).query)
        self.assertEqual(query['scope'], [auth.DRIVE_FILE_SCOPE])
        self.assertEqual(query['redirect_uri'], [BASE + '/auth/google/callback'])
        self.assertIn('code_challenge', query)
        return query['state'][0]

    def code(self, account='alice'):
        state = self.google_redirect()
        with closing(auth.connect()) as db:
            pending = oauth.get(db, 'google_state', oauth.digest(state))
        flow = MagicMock()
        flow.credentials = google_credentials(account)
        with patch.object(auth, 'create_flow', return_value=flow):
            response = self.client.get('/auth/google/callback', params={'state': state, 'code': 'google-code-private'}, follow_redirects=False)
        self.assertEqual(response.status_code, 303, response.text)
        self.assertEqual(flow.code_verifier, pending['verifier'])
        self.assertTrue(flow.fetch_token.call_args.kwargs['authorization_response'].startswith(BASE))
        result = parse_qs(urlparse(response.headers['location']).query)
        self.assertEqual(result['state'], ['vibe-state'])
        self.assertNotIn('google-', response.headers['location'])
        return result['code'][0]

    def exchange(self, code, **overrides):
        return self.client.post('/token', data={
            'grant_type': 'authorization_code', 'code': code, 'code_verifier': VERIFIER,
            'client_id': self.registration['client_id'], 'client_secret': self.registration['client_secret'],
            'redirect_uri': CALLBACK, 'resource': BASE + '/mcp', **overrides})

    def tokens(self, account='alice'):
        response = self.exchange(self.code(account))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def refresh(self, token, **overrides):
        return self.client.post('/token', data={
            'grant_type': 'refresh_token', 'refresh_token': token,
            'client_id': self.registration['client_id'], 'client_secret': self.registration['client_secret'], **overrides})

    def status(self, token):
        return self.client.get('/auth/status', headers={'Authorization': f'Bearer {token}'})

    def test_discovery_and_shared_token_rejection(self):
        response = self.client.post('/mcp')
        self.assertEqual(response.status_code, 401)
        self.assertIn(BASE + '/.well-known/oauth-protected-resource/mcp', response.headers['www-authenticate'])
        metadata = self.client.get('/.well-known/oauth-authorization-server').json()
        self.assertEqual(metadata['registration_endpoint'], BASE + '/register')
        self.assertEqual(metadata['code_challenge_methods_supported'], ['S256'])
        self.assertEqual(self.client.get('/.well-known/oauth-protected-resource/mcp').json()['resource'], BASE + '/mcp')
        self.assertEqual(self.status('old-shared-secret').status_code, 401)
        self.assertEqual(self.client.get('/auth/google/start').status_code, 400)

    def test_two_users_one_client_separate_credentials_and_persistence(self):
        alice, bob = self.tokens('alice'), self.tokens('bob')
        self.assertNotEqual(alice['access_token'], bob['access_token'])
        with closing(auth.connect()) as db:
            a = oauth.get(db, 'access', oauth.digest(alice['access_token']))
            b = oauth.get(db, 'access', oauth.digest(bob['access_token']))
            self.assertNotEqual(a['subject'], b['subject'])
            self.assertEqual(a['client_id'], b['client_id'])
            saved = db.execute("select value from connector_oauth where kind in ('code', 'access', 'refresh')").fetchall()
            self.assertNotIn(alice['access_token'], str(saved))
        self.assertEqual(auth.load_credentials(a['subject']).refresh_token, 'google-refresh-alice')
        self.assertEqual(auth.load_credentials(b['subject']).refresh_token, 'google-refresh-bob')
        with TestClient(server.create_app(), base_url=BASE) as restarted:
            self.assertEqual(restarted.get('/auth/status', headers={'Authorization': 'Bearer '+alice['access_token']}).status_code, 200)

    def test_code_pkce_redirect_client_target_and_single_use(self):
        code = self.code()
        for override in ({'code_verifier': 'wrong'}, {'redirect_uri': 'https://evil.example.com/'},
                         {'client_id': 'unknown'}, {'resource': 'https://evil.example.com/mcp'}):
            self.assertGreaterEqual(self.exchange(code, **override).status_code, 400)
        self.assertEqual(self.exchange(code).status_code, 200)
        self.assertEqual(self.exchange(code).status_code, 400)
        code = self.code()
        with closing(auth.connect()) as db:
            db.execute("update connector_oauth set expires_at=0 where kind='code'")
            db.commit()
        self.assertEqual(self.exchange(code).status_code, 400)

    def test_refresh_rotation_scope_replay_and_revocation_isolation(self):
        alice, bob = self.tokens(), self.tokens('bob')
        self.assertEqual(self.refresh(alice['refresh_token'], scope='admin').status_code, 400)
        self.assertEqual(self.refresh(alice['refresh_token'], resource='https://evil.example.com/mcp').status_code, 400)
        response = self.refresh(alice['refresh_token'])
        self.assertEqual(response.status_code, 200, response.text)
        rotated = response.json()
        self.assertNotEqual(rotated['refresh_token'], alice['refresh_token'])
        self.assertEqual(self.status(alice['access_token']).status_code, 401)
        self.assertEqual(self.status(rotated['access_token']).status_code, 200)
        self.assertEqual(self.refresh(alice['refresh_token']).status_code, 400)
        self.assertEqual(self.status(rotated['access_token']).status_code, 401)
        self.assertEqual(self.status(bob['access_token']).status_code, 200)
        response = self.client.post('/revoke', data={'token': bob['refresh_token'],
            'client_id': self.registration['client_id'], 'client_secret': self.registration['client_secret']})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.status(bob['access_token']).status_code, 401)

    def test_browser_binding_expiry_and_callback_replay(self):
        state = self.google_redirect()
        cookie = self.client.cookies.get(oauth.COOKIE)
        self.client.cookies.clear()
        with patch.object(auth, 'create_flow') as create:
            self.assertEqual(self.client.get('/auth/google/callback', params={'state': state, 'code': 'fake'}).status_code, 400)
            create.assert_not_called()
        self.client.cookies.set(oauth.COOKIE, cookie, domain='slides.example.com', path='/')
        flow = MagicMock(credentials=google_credentials())
        with patch.object(auth, 'create_flow', return_value=flow):
            for expected in (303, 400):
                self.assertEqual(self.client.get('/auth/google/callback', params={'state': state, 'code': 'fake'}, follow_redirects=False).status_code, expected)
            flow.fetch_token.assert_called_once()
        state = self.google_redirect()
        with closing(auth.connect()) as db:
            db.execute("update connector_oauth set expires_at=0 where kind='google_state'")
            db.commit()
        self.assertEqual(self.client.get('/auth/google/callback', params={'state': state, 'code': 'fake'}).status_code, 400)

    def test_csrf_and_unapproved_redirects(self):
        url = self.begin().headers['location']
        self.client.get(url)
        ticket = parse_qs(urlparse(url).query)['request'][0]
        response = self.client.post('/auth/google/start', data={'request': ticket, 'csrf': 'wrong'})
        self.assertEqual(response.status_code, 400)
        response = self.begin(redirect_uri='https://evil.example.com/callback')
        self.assertEqual(response.status_code, 400)
        for uri in ('https://example.com/callback#fragment', 'http://example.com/callback', 'javascript:alert(1)'):
            response = self.client.post('/register', json={'redirect_uris': [uri]})
            self.assertEqual(response.status_code, 400)

    def test_google_denial_and_missing_refresh_token_do_not_issue_grants(self):
        state = self.google_redirect()
        response = self.client.get('/auth/google/callback', params={'state': state, 'error': 'access_denied'}, follow_redirects=False)
        self.assertIn('error=access_denied', response.headers['location'])
        state = self.google_redirect()
        flow = MagicMock(credentials=SimpleNamespace(refresh_token=None))
        with patch.object(auth, 'create_flow', return_value=flow):
            response = self.client.get('/auth/google/callback', params={'state': state, 'code': 'fake'})
        self.assertEqual(response.status_code, 400)
        with closing(auth.connect()) as db:
            self.assertEqual(db.execute('select count(*) from google_tokens').fetchone()[0], 0)

    def test_revoked_google_access_revokes_only_that_connection(self):
        alice, bob = self.tokens(), self.tokens('bob')
        with closing(auth.connect()) as db:
            subject = oauth.get(db, 'access', oauth.digest(alice['access_token']))['subject']
        creds = MagicMock(valid=False)
        creds.refresh.side_effect = RefreshError('invalid_grant')
        with patch.object(auth.Credentials, 'from_authorized_user_info', return_value=creds):
            with self.assertRaisesRegex(RuntimeError, 'Reconnect'):
                auth.load_credentials(subject)
        self.assertEqual(self.status(alice['access_token']).status_code, 401)
        self.assertEqual(self.status(bob['access_token']).status_code, 200)
        with self.assertRaises(RuntimeError):
            auth.load_credentials('default')

    def test_request_logs_do_not_contain_secrets(self):
        with self.assertLogs('uvicorn.error', level='INFO') as logs:
            self.client.post('/mcp', headers={'Authorization': 'Bearer private-header'})
            self.client.get('/auth/google/callback?code=private-code&state=private-state')
        output = '\n'.join(logs.output)
        for secret in ('private-header', 'private-code', 'private-state'):
            self.assertNotIn(secret, output)
        self.assertIn('auth=invalid', output)
