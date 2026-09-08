"""Google credentials keyed by an authenticated connector subject."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"


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
    db.execute("delete from temporary_images where expires_at<=?", (int(time.time()),))
    db.commit()
    return db


def create_flow(redirect_uri: str) -> Flow:
    return Flow.from_client_config({"web": {
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }}, scopes=[DRIVE_FILE_SCOPE], redirect_uri=redirect_uri)


def save_credentials(db, subject: str, creds: Credentials) -> None:
    db.execute("""insert into google_tokens values (?, ?, ?)
        on conflict(connection_id) do update set
        credentials_json=excluded.credentials_json, updated_at=excluded.updated_at""",
        (subject, creds.to_json(), int(time.time())))


def revoke_subject(db, subject: str) -> None:
    db.execute('delete from style_preferences where subject=?', (subject,))
    db.execute('delete from temporary_images where subject=?', (subject,))
    db.execute("delete from connector_oauth where subject = ?", (subject,))
    db.execute("delete from google_tokens where connection_id = ?", (subject,))


def load_credentials(subject: str) -> Credentials:
    # Never fall back to the investigation's shared `default` account.
    if not subject or subject == "default":
        raise RuntimeError("Connect this connector to your Google account in Vibe first.")
    with closing(connect()) as db:
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
