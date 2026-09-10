"""Client admission, signed Google identity validation, and durable usage limits."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, MagicMock, patch

from google.auth import crypt, jwt, exceptions
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from mcp_slides import auth, oauth, usage, outline, editing, insertion, backgrounds


class PilotTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        env = patch.dict(os.environ, {
            'TOKEN_DB_PATH': str(Path(temp.name) / 'tokens.db'),
            'GOOGLE_CLIENT_ID': 'pilot-client', 'GOOGLE_ALLOWED_DOMAIN': 'mistral.ai',
            'GOOGLE_ALLOWED_EMAILS': 'aurelien.morel.arthur@gmail.com,friend@example.com',
            'PILOT_MAX_PAID_CALLS': '3', 'PILOT_MAX_CONCURRENT_CALLS': '2',
            'PILOT_PAID_CALLS_ENABLED': 'true'})
        env.start()
        self.addCleanup(temp.cleanup)
        self.addCleanup(env.stop)

    def count(self):
        with closing(auth.connect()) as db:
            return db.execute('select calls from pilot_usage').fetchone()[0]

    def test_admission_requires_hosted_domain_or_verified_exact_exception(self):
        for claims in ({'hd': 'mistral.ai'},
                       {'email': 'aurelien.morel.arthur@gmail.com', 'email_verified': True},
                       {'email': 'friend@example.com', 'email_verified': True}):
            self.assertTrue(auth.allowed_identity({'sub': 'google-user', **claims}))
        for claims in ({'email': 'someone@mistral.ai', 'email_verified': True},
                       {'hd': 'evil.mistral.ai'}, {'hd': 'mistral.ai.evil.com'}, {},
                       {'email': 'friend@example.com', 'email_verified': 'true'},
                       {'email': 'friend@example.com', 'email_verified': False},
                       {'email': 'friend+other@example.com', 'email_verified': True}):
            self.assertFalse(auth.allowed_identity({'sub': 'google-user', **claims}))
        self.assertFalse(auth.allowed_identity({'hd': 'mistral.ai'}))
        with patch.dict(os.environ, {'GOOGLE_ALLOWED_DOMAIN': '', 'GOOGLE_ALLOWED_EMAILS': ''}):
            self.assertFalse(auth.allowed_identity({'sub': 'user', 'hd': 'mistral.ai'}))

    def test_real_signed_id_token_validation(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption())
        public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        signer = crypt.RSASigner.from_string(private, key_id='test-key')
        claims = {'iss': 'https://accounts.google.com', 'aud': 'pilot-client',
                  'iat': int(time.time()), 'exp': int(time.time()) + 300,
                  'nonce': 'expected-nonce', 'sub': 'stable-user', 'hd': 'mistral.ai'}
        request = Mock(return_value=Mock(status=200, data=json.dumps({'test-key': public.decode()}).encode()))
        with patch.object(auth, 'GoogleRequest', return_value=request):
            token = jwt.encode(signer, claims).decode()
            identity = auth.verify_identity(token, 'expected-nonce')
            self.assertEqual(identity, {'sub': 'stable-user', 'hd': 'mistral.ai'})
            for override in ({'aud': 'another-client'}, {'iss': 'https://evil.example.com'},
                             {'exp': int(time.time()) - 1}, {'nonce': 'wrong'}, {'sub': ''}):
                with self.subTest(override=override), self.assertRaises((ValueError, exceptions.GoogleAuthError)):
                    auth.verify_identity(jwt.encode(signer, {**claims, **override}).decode(), 'expected-nonce')
            parts = token.split('.')
            parts[2] = ('A' if parts[2][0] != 'A' else 'B') + parts[2][1:]
            with self.assertRaises((ValueError, exceptions.GoogleAuthError)):
                auth.verify_identity('.'.join(parts), 'expected-nonce')
            with self.assertRaises((ValueError, exceptions.GoogleAuthError)):
                auth.verify_identity(token, '')

    def test_removing_friend_blocks_existing_tokens_and_purges_only_disallowed(self):
        provider = oauth.GoogleOAuthProvider('https://slides.example.com')
        with closing(auth.connect()) as db:
            tokens = {}
            for subject, claims in {
                'friend': {'sub': 'friend', 'email': 'friend@example.com', 'email_verified': True},
                'owner': {'sub': 'owner', 'email': 'aurelien.morel.arthur@gmail.com', 'email_verified': True},
                'client': {'sub': 'client', 'hd': 'mistral.ai'},
            }.items():
                db.execute('insert into google_tokens values (?, ?, ?)', (subject, '{}', 1))
                auth.save_identity(db, subject, claims)
                tokens[subject] = provider.issue_tokens(db, 'vibe', subject, [oauth.SCOPE])
            db.execute('insert into google_tokens values (?, ?, ?)', ('legacy', '{}', 1))
            db.commit()
        client = Mock(client_id='vibe')
        friend = tokens['friend']
        loaded_refresh = asyncio.run(provider.load_refresh_token(client, friend.refresh_token))
        with patch.dict(os.environ, {'GOOGLE_ALLOWED_EMAILS': 'aurelien.morel.arthur@gmail.com'}):
            self.assertIsNone(asyncio.run(provider.load_access_token(friend.access_token)))
            self.assertIsNone(asyncio.run(provider.load_refresh_token(client, friend.refresh_token)))
            with self.assertRaises(oauth.TokenError):
                asyncio.run(provider.exchange_refresh_token(client, loaded_refresh, [oauth.SCOPE]))
            with self.assertRaisesRegex(RuntimeError, 'approved'):
                auth.load_credentials('friend')
            self.assertEqual(auth.purge_disallowed_connections(), 2)
            self.assertEqual(auth.purge_disallowed_connections(), 0)
            for subject in ('owner', 'client'):
                self.assertIsNotNone(asyncio.run(provider.load_access_token(tokens[subject].access_token)))
            with closing(auth.connect()) as db:
                self.assertIsNone(db.execute('select 1 from google_identities where connection_id="friend"').fetchone())
                self.assertIsNone(db.execute('select 1 from connector_oauth where subject="friend"').fetchone())

    def test_failed_calls_count_retries_disabled_and_allowance_persists(self):
        call = Mock(side_effect=[RuntimeError('upstream'), 'second', 'third'])
        with self.assertRaises(RuntimeError):
            usage.paid_call(call)
        self.assertEqual(usage.paid_call(call), 'second')
        # New DB connections and module users share the same lifetime allowance.
        self.assertEqual(self.count(), 2)
        self.assertEqual(usage.paid_call(call), 'third')
        with self.assertRaisesRegex(usage.UsageLimitError, 'exhausted'):
            usage.paid_call(call)
        self.assertEqual(self.count(), 3)
        self.assertEqual(call.call_count, 3)
        self.assertTrue(all(c.kwargs['retries'] is None for c in call.call_args_list))

    def test_pause_and_busy_do_not_spend_and_slot_recovers(self):
        call = Mock()
        with patch.dict(os.environ, {'PILOT_PAID_CALLS_ENABLED': 'false'}):
            with self.assertRaisesRegex(usage.UsageLimitError, 'paused'):
                usage.paid_call(call)
        call.assert_not_called()
        self.assertEqual(self.count(), 0)
        entered, release = threading.Event(), threading.Event()
        def blocking(**kwargs):
            entered.set()
            if not release.wait(5):
                raise AssertionError('test timed out')
            raise RuntimeError('upstream failed')
        with patch.dict(os.environ, {'PILOT_MAX_CONCURRENT_CALLS': '1'}), ThreadPoolExecutor(1) as pool:
            first = pool.submit(usage.paid_call, blocking)
            try:
                self.assertTrue(entered.wait(5))
                with self.assertRaisesRegex(usage.UsageLimitError, 'busy'):
                    usage.paid_call(call)
            finally:
                release.set()
            with self.assertRaises(RuntimeError):
                first.result()
        self.assertEqual(self.count(), 1)
        usage.paid_call(call)
        self.assertEqual(self.count(), 2)

    def test_atomic_allowance_under_parallel_requests(self):
        def attempt(_):
            try:
                usage.paid_call(lambda **kwargs: None)
                return True
            except usage.UsageLimitError:
                return False
        with patch.dict(os.environ, {'PILOT_MAX_CONCURRENT_CALLS': '10'}), ThreadPoolExecutor(10) as pool:
            self.assertEqual(sum(pool.map(attempt, range(10))), 3)
        self.assertEqual(self.count(), 3)

    def test_all_paid_features_stop_before_provider_when_budget_exhausted(self):
        operations = [
            (outline, lambda: outline.generate_outline('Demo', 1, None, None, 'test')),
            (editing, lambda: editing.propose_edit({}, {}, 'Revise', None)),
            (insertion, lambda: insertion.propose_slide({}, 'Add', None)),
            (backgrounds, lambda: backgrounds.generate_image('Demo', {})),
        ]
        with patch.dict(os.environ, {'PILOT_MAX_PAID_CALLS': '0', 'MISTRAL_API_KEY': 'mock'}):
            for module, operation in operations:
                fake = MagicMock()
                fake.__enter__.return_value = fake
                with self.subTest(feature=module.__name__), patch.object(module, 'Mistral', return_value=fake):
                    with self.assertRaisesRegex(usage.UsageLimitError, 'exhausted'):
                        operation()
                    fake.chat.complete.assert_not_called()
                    fake.beta.conversations.start.assert_not_called()
        self.assertEqual(self.count(), 0)
