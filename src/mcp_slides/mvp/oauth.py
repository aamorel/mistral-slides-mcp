"""MCP OAuth provider bridging each connector grant to its own Google consent."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from contextlib import closing
from html import escape
from urllib.parse import urlencode, urlparse

from mcp.server.auth.handlers.token import TokenHandler
from mcp.server.auth.provider import (
    AccessToken, AuthorizationCode, AuthorizationParams, AuthorizeError,
    OAuthAuthorizationServerProvider, RefreshToken, RegistrationError, TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import auth

SCOPE = "slides.generate"
FLOW_TTL = 600
ACCESS_TTL = 3600
REFRESH_TTL = 30 * 86400
COOKIE = "slides_consent"
SAFE_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY", "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self' https://accounts.google.com; frame-ancestors 'none'; base-uri 'none'"}


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def put(db, kind, key, value, expires, subject=None):
    db.execute("insert or replace into connector_oauth values (?, ?, ?, ?, ?)",
               (kind, key, json.dumps(value), expires, subject))


def get(db, kind, key):
    row = db.execute("select value from connector_oauth where kind=? and key=? and expires_at>?",
                     (kind, key, int(time.time()))).fetchone()
    return json.loads(row[0]) if row else None


def delete(db, kind, key):
    db.execute("delete from connector_oauth where kind=? and key=?", (kind, key))


def failure(message="This connection link expired or is invalid. Start connecting again in Vibe.", reason="invalid_flow"):
    logging.getLogger("uvicorn.error").warning("oauth_failure reason=%s", reason)
    return HTMLResponse(f"<!doctype html><title>Connection not completed</title><h1>Connection not completed</h1><p>{escape(message)}</p>",
                        status_code=400, headers=SAFE_HEADERS)


class GoogleOAuthProvider(OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]):
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.resource = self.base_url + '/mcp'
        self.callback_url = self.base_url + '/auth/google/callback'

    async def get_client(self, client_id):
        with closing(auth.connect()) as db:
            value = get(db, 'client', client_id)
        return OAuthClientInformationFull.model_validate(value) if value else None

    async def register_client(self, client_info):
        if not client_info.redirect_uris or len(client_info.redirect_uris) > 10:
            raise RegistrationError('invalid_redirect_uri', 'Register 1–10 exact redirect URLs.')
        for value in client_info.redirect_uris:
            url = urlparse(str(value))
            if (url.fragment or url.username or url.password or not url.hostname or
                not (url.scheme == 'https' or (url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1', '::1')))):
                raise RegistrationError('invalid_redirect_uri', 'Use HTTPS or a local loopback callback without fragments or credentials.')
        with closing(auth.connect()) as db:
            db.execute('delete from connector_oauth where expires_at < ?', (int(time.time()),))
            put(db, 'client', client_info.client_id, client_info.model_dump(mode='json'), 2**62)
            db.commit()

    async def authorize(self, client, params):
        if params.resource not in (None, self.resource):
            raise AuthorizeError('invalid_target', 'This server only authorizes its own MCP endpoint.')
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', params.code_challenge):
            raise AuthorizeError('invalid_request', 'A valid S256 PKCE challenge is required.')
        scopes = params.scopes if params.scopes is not None else [SCOPE]
        if scopes != [SCOPE]:
            raise AuthorizeError('invalid_scope', f'Request {SCOPE}.')
        params = params.model_copy(update={'scopes': scopes, 'resource': self.resource})
        ticket = secrets.token_urlsafe(32)
        with closing(auth.connect()) as db:
            db.execute('delete from connector_oauth where expires_at < ?', (int(time.time()),))
            put(db, 'pending', digest(ticket), {
                'client_id': client.client_id, 'client_name': client.client_name or 'MCP client',
                'params': params.model_dump(mode='json'), 'expires': int(time.time()) + FLOW_TTL,
            }, int(time.time()) + FLOW_TTL)
            db.commit()
        return self.base_url + '/auth/google/start?' + urlencode({'request': ticket})

    def consent_page(self, request):
        ticket = request.query_params.get('request', '')
        with closing(auth.connect()) as db:
            pending = get(db, 'pending', digest(ticket))
        if not pending:
            return failure()
        csrf = request.cookies.get(COOKIE) or secrets.token_urlsafe(32)
        callback = escape(pending['params']['redirect_uri'])
        name = escape(pending['client_name'])
        # Explicit per-client consent is required for a dynamically registered
        # OAuth client using our static upstream Google client.
        response = HTMLResponse(f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Connect Google Slides</title>
<style>body{{font:18px/1.5 system-ui;max-width:620px;margin:10vh auto;padding:24px;color:#18202a}}button{{font:inherit;padding:12px 20px;cursor:pointer}}small{{overflow-wrap:anywhere}}</style>
<h1>Connect your Google account</h1>
<p><strong>{name}</strong> is requesting permission to create and read presentations, revise supported text, add content slides, and change presentation colors and fonts in your Google Drive through MCP Slides.</p>
<p>This client-only pilot accepts approved company accounts and invited personal testers.</p>
<p>You will choose your Google account next. Google credentials stay on this server; the connector receives its own access token.</p>
<p><small>Return address: {callback}</small></p>
<form method="post" action="/auth/google/start">
<input type="hidden" name="request" value="{escape(ticket)}">
<input type="hidden" name="csrf" value="{escape(csrf)}">
<button type="submit">Continue with Google</button></form>
<p>You can close this page to cancel.</p></html>''', headers={**SAFE_HEADERS, "Referrer-Policy": "strict-origin"})
        # no-referrer turns a browser form POST's Origin into 'null'. Send only
        # the origin (never the authorization ticket) while preserving CSRF checks.
        response.set_cookie(COOKIE, csrf, max_age=FLOW_TTL, secure=self.base_url.startswith('https://'), httponly=True, samesite='lax')
        return response

    async def consent_submit(self, request):
        form = await request.form()
        cookie, csrf = request.cookies.get(COOKIE, ''), str(form.get('csrf', ''))
        if not cookie:
            return failure('Your browser did not retain the connection cookie. Enable cookies and reconnect in Vibe.', reason='missing_consent_cookie')
        if not hmac.compare_digest(cookie.encode(), csrf.encode()):
            return failure(reason='csrf_mismatch')
        if request.headers.get('origin') not in (None, self.base_url):
            return failure('The browser could not verify the connection page. Start connecting again in Vibe.', reason='invalid_origin')
        return await run_in_threadpool(self.start_google, str(form.get('request', '')), cookie)

    def start_google(self, ticket, cookie):
        with closing(auth.connect()) as db:
            db.execute('begin immediate')
            pending = get(db, 'pending', digest(ticket))
            if not pending:
                return failure()
            delete(db, 'pending', digest(ticket))
            flow = auth.create_flow(self.callback_url)
            state = secrets.token_urlsafe(32)
            nonce = secrets.token_urlsafe(32)
            url, _ = flow.authorization_url(access_type='offline', prompt='consent select_account', state=state, nonce=nonce)
            put(db, 'google_state', digest(state), {
                **pending, 'browser': digest(cookie), 'verifier': flow.code_verifier, 'nonce': nonce,
            }, pending['expires'])
            db.commit()
        return RedirectResponse(url, status_code=303, headers=SAFE_HEADERS)

    def google_callback(self, request):
        state = request.query_params.get('state', '')
        cookie = request.cookies.get(COOKIE, '')
        with closing(auth.connect()) as db:
            db.execute('begin immediate')
            pending = get(db, 'google_state', digest(state))
            if not pending or not cookie or not hmac.compare_digest(pending['browser'], digest(cookie)):
                return failure()
            delete(db, 'google_state', digest(state))
            db.commit()
        params = AuthorizationParams.model_validate(pending['params'])
        def redirect_error():
            return RedirectResponse(construct_redirect_uri(str(params.redirect_uri), error='access_denied', state=params.state),
                                    status_code=303, headers=SAFE_HEADERS)
        if request.query_params.get('error') or not request.query_params.get('code'):
            return redirect_error()
        try:
            flow = auth.create_flow(self.callback_url)
            flow.code_verifier = pending['verifier']
            flow.fetch_token(authorization_response=self.callback_url + '?' + request.url.query)
            creds = flow.credentials
            if not creds.refresh_token or not creds.has_scopes([auth.DRIVE_FILE_SCOPE]):
                return failure('Google did not grant persistent Slides access. Reconnect in Vibe and approve the requested access.')
            identity = auth.verify_identity(creds.id_token, pending.get('nonce', ''))
            if not auth.allowed_identity(identity):
                return failure('This client-only pilot is available to approved company accounts and invited personal testers.', reason='account_not_allowed')
        except Exception:
            return failure('Google authorization failed. Reconnect in Vibe and try again.')
        # A subject identifies this consented connection, not a caller-supplied
        # email, session ID, or OAuth client ID shared by multiple users.
        subject = secrets.token_hex(24)
        code = secrets.token_urlsafe(32)
        authorization = AuthorizationCode(
            code=code, client_id=pending['client_id'], subject=subject,
            expires_at=int(time.time()) + 60, **params.model_dump(exclude={'state'}),
        )
        with closing(auth.connect()) as db:
            auth.save_credentials(db, subject, creds)
            auth.save_identity(db, subject, identity)
            put(db, 'code', digest(code), authorization.model_dump(mode='json', exclude={'code'}),
                int(authorization.expires_at), subject)
            db.commit()
        return RedirectResponse(construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state),
                                status_code=303, headers=SAFE_HEADERS)

    async def load_authorization_code(self, client, authorization_code):
        with closing(auth.connect()) as db:
            value = get(db, 'code', digest(authorization_code))
        if not value or value['client_id'] != client.client_id:
            return None
        return AuthorizationCode(code=authorization_code, **value)

    def issue_tokens(self, db, client_id, subject, scopes, with_refresh=True):
        if not auth.connection_allowed(db, subject):
            raise TokenError('invalid_grant', 'Reconnect with an approved Google account.')
        now = int(time.time())
        access = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(32) if with_refresh else None
        common = dict(client_id=client_id, scopes=scopes, resource=self.resource, subject=subject)
        put(db, 'access', digest(access), {**common, 'expires_at': now + ACCESS_TTL}, now + ACCESS_TTL, subject)
        if refresh:
            put(db, 'refresh', digest(refresh), {**common, 'expires_at': now + REFRESH_TTL}, now + REFRESH_TTL, subject)
        return OAuthToken(access_token=access, token_type='Bearer', expires_in=ACCESS_TTL,
                          refresh_token=refresh, scope=' '.join(scopes))

    async def exchange_authorization_code(self, client, authorization_code):
        with closing(auth.connect()) as db:
            db.execute('begin immediate')
            value = get(db, 'code', digest(authorization_code.code))
            if not value or value['client_id'] != client.client_id:
                raise TokenError('invalid_grant', 'Authorization code expired or was already used.')
            delete(db, 'code', digest(authorization_code.code))
            token = self.issue_tokens(db, client.client_id, value['subject'], value['scopes'],
                                      'refresh_token' in client.grant_types)
            db.commit()
            return token

    async def load_access_token(self, token):
        with closing(auth.connect()) as db:
            value = get(db, 'access', digest(token))
            if value and not auth.connection_allowed(db, value['subject']):
                return None
        return AccessToken(token=token, claims={'iss': self.base_url}, **value) if value else None

    async def load_refresh_token(self, client, refresh_token):
        with closing(auth.connect()) as db:
            retired = get(db, 'used_refresh', digest(refresh_token))
            if retired and retired['client_id'] == client.client_id:
                auth.revoke_subject(db, retired['subject'])
                db.commit()
                return None
            value = get(db, 'refresh', digest(refresh_token))
            if value and not auth.connection_allowed(db, value['subject']):
                return None
        if not value or value['client_id'] != client.client_id:
            return None
        return RefreshToken(token=refresh_token, **value)

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        with closing(auth.connect()) as db:
            db.execute('begin immediate')
            value = get(db, 'refresh', digest(refresh_token.token))
            if not value or value['client_id'] != client.client_id:
                retired = get(db, 'used_refresh', digest(refresh_token.token))
                if retired and retired['client_id'] == client.client_id:
                    auth.revoke_subject(db, retired['subject'])
                    db.commit()
                raise TokenError('invalid_grant', 'Refresh token expired or was already used.')
            delete(db, 'refresh', digest(refresh_token.token))
            put(db, 'used_refresh', digest(refresh_token.token), value, value['expires_at'], value['subject'])
            db.execute("delete from connector_oauth where kind='access' and subject=?", (value['subject'],))
            tokens = self.issue_tokens(db, client.client_id, value['subject'], scopes)
            db.commit()
            return tokens

    async def revoke_token(self, token):
        with closing(auth.connect()) as db:
            auth.revoke_subject(db, token.subject)
            db.commit()


class ResourceTokenHandler(TokenHandler):
    async def handle(self, request):
        resources = (await request.form()).getlist('resource')
        if resources and resources != [self.provider.resource]:
            return JSONResponse({'error': 'invalid_target'}, status_code=400,
                                headers={'Cache-Control': 'no-store'})
        return await super().handle(request)
