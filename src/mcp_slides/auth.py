"""Google credentials keyed by an authenticated connector subject."""
from __future__ import annotations

import hmac
import json
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow

DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"
GOOGLE_SCOPES = [DRIVE_FILE_SCOPE, "openid", "https://www.googleapis.com/auth/userinfo.email"]


def connect() -> sqlite3.Connection:
    path = Path(os.getenv("TOKEN_DB_PATH", ".secrets/tokens.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.execute("""create table if not exists google_tokens (
        connection_id text primary key, credentials_json text not null, updated_at integer not null
    )""")
    db.execute("""create table if not exists connector_oauth (
        kind text not null, key text not null, value text not null,
        expires_at integer not null, subject text,
        primary key (kind, key)
    )""")
    db.execute("create index if not exists connector_oauth_subject on connector_oauth(subject)")
    db.execute('create table if not exists style_preferences (subject text primary key, settings_json text not null)')
    db.execute('create table if not exists temporary_images (token_hash text primary key, subject text not null, data blob not null, expires_at integer not null)')
    db.execute('create table if not exists google_identities (connection_id text primary key, claims text not null)')
    db.execute('create table if not exists pilot_usage (id integer primary key check(id=1), calls integer not null)')
    db.execute('insert or ignore into pilot_usage values (1, 0)')
    db.execute("delete from temporary_images where expires_at<=?", (int(time.time()),))
    db.commit()
    return db


def create_flow(redirect_uri: str) -> Flow:
    return Flow.from_client_config({"web": {
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }}, scopes=GOOGLE_SCOPES, redirect_uri=redirect_uri)


def save_credentials(db, subject: str, creds: Credentials) -> None:
    db.execute("""insert into google_tokens values (?, ?, ?)
        on conflict(connection_id) do update set
        credentials_json=excluded.credentials_json, updated_at=excluded.updated_at""",
        (subject, creds.to_json(), int(time.time())))


def revoke_subject(db, subject: str) -> None:
    db.execute('delete from google_identities where connection_id=?', (subject,))
    db.execute('delete from style_preferences where subject=?', (subject,))
    db.execute('delete from temporary_images where subject=?', (subject,))
    db.execute("delete from connector_oauth where subject = ?", (subject,))
    db.execute("delete from google_tokens where connection_id = ?", (subject,))


def load_credentials(subject: str) -> Credentials:
    # Never fall back to the investigation's shared `default` account.
    if not subject or subject == "default":
        raise RuntimeError("Connect this connector to your Google account in Vibe first.")
    with closing(connect()) as db:
        if not connection_allowed(db, subject):
            raise RuntimeError("Client-only pilot. Reconnect with an approved Google account.")
        row = db.execute("select credentials_json from google_tokens where connection_id = ?", (subject,)).fetchone()
    if not row:
        raise RuntimeError("Reconnect this connector in Vibe to authorize your Google account.")
    creds = Credentials.from_authorized_user_info(json.loads(row[0]), [DRIVE_FILE_SCOPE])
    if not creds.valid:
        try:
            creds.refresh(GoogleRequest())
        except RefreshError as exc:
            if not exc.retryable:
                with closing(connect()) as db:
                    revoke_subject(db, subject)
                    db.commit()
                raise RuntimeError("Google access expired or was revoked. Reconnect this connector in Vibe.") from None
            raise RuntimeError("Google authorization is temporarily unavailable. Try again shortly.") from None
        except Exception:
            raise RuntimeError("Google authorization is temporarily unavailable. Try again shortly.") from None
        with closing(connect()) as db:
            # Do not recreate credentials if a concurrent disconnect revoked them.
            db.execute("update google_tokens set credentials_json = ?, updated_at = ? where connection_id = ?",
                       (creds.to_json(), int(time.time()), subject))
            db.commit()
    return creds


def allowed_identity(claims: dict) -> bool:
    """Only call with claims verified by Google, or loaded from our identity table."""
    domain = os.getenv("GOOGLE_ALLOWED_DOMAIN", "").strip().lower()
    emails = {value.strip().lower() for value in os.getenv("GOOGLE_ALLOWED_EMAILS", "").split(",") if value.strip()}
    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        return False
    return bool((domain and claims.get("hd") == domain) or
                (claims.get("email_verified") is True and
                 isinstance(claims.get("email"), str) and claims["email"].lower() in emails))


def verify_identity(raw_token: str, nonce: str) -> dict:
    if not isinstance(raw_token, str) or not raw_token or not nonce:
        raise ValueError("Missing Google identity")
    claims = id_token.verify_oauth2_token(raw_token, GoogleRequest(), os.environ["GOOGLE_CLIENT_ID"])
    if not isinstance(claims.get("nonce"), str) or not hmac.compare_digest(claims["nonce"], nonce):
        raise ValueError("Invalid Google nonce")
    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise ValueError("Missing Google subject")
    return {key: claims[key] for key in ("sub", "hd", "email", "email_verified") if key in claims}


def save_identity(db, subject: str, claims: dict) -> None:
    db.execute('insert into google_identities values (?, ?)', (subject, json.dumps(claims)))


def connection_allowed(db, subject: str) -> bool:
    row = db.execute('select claims from google_identities where connection_id=?', (subject,)).fetchone()
    return bool(row and allowed_identity(json.loads(row[0])) and
                db.execute('select 1 from google_tokens where connection_id=?', (subject,)).fetchone())


def purge_disallowed_connections() -> int:
    """Run at startup after changing policy; also removes legacy unverified grants."""
    with closing(connect()) as db:
        db.execute('begin immediate')
        subjects = [row[0] for row in db.execute('select connection_id from google_tokens')]
        removed = 0
        for subject in subjects:
            if not connection_allowed(db, subject):
                revoke_subject(db, subject)
                removed += 1
        db.commit()
    return removed
