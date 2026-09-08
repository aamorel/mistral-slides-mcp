"""Google linking and compatible SQLite storage for the single-account MVP."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
import hmac
from contextlib import closing
from google.auth.transport.requests import Request as GoogleRequest
from pathlib import Path
from typing import Any

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response


DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"


def get_database_path() -> Path:
    return Path(os.getenv("TOKEN_DB_PATH", ".secrets/tokens.sqlite3"))


def get_base_url(request: Request) -> str:
    configured = os.getenv("PUBLIC_BASE_URL")
    if configured:
        return configured.rstrip("/")
    return str(request.base_url).rstrip("/")


def get_connection_id(request: Request) -> str:
    return "default"


def get_client_config() -> dict[str, Any]:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("Missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET")

    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def connect() -> sqlite3.Connection:
    db_path = get_database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_path)
    db.execute(
        """
        create table if not exists oauth_states (
            state text primary key,
            connection_id text not null,
            code_verifier text,
            created_at integer not null
        )
        """
    )
    columns = {
        row[1]
        for row in db.execute("pragma table_info(oauth_states)").fetchall()
    }
    if "code_verifier" not in columns:
        db.execute("alter table oauth_states add column code_verifier text")
    db.execute(
        """
        create table if not exists google_tokens (
            connection_id text primary key,
            credentials_json text not null,
            updated_at integer not null
        )
        """
    )
    db.commit()
    return db


def create_flow(redirect_uri: str) -> Flow:
    flow = Flow.from_client_config(
        get_client_config(),
        scopes=[DRIVE_FILE_SCOPE],
        redirect_uri=redirect_uri,
    )
    return flow


def token_status(connection_id: str) -> dict[str, Any]:
    with closing(connect()) as db:
        row = db.execute(
            "select credentials_json, updated_at from google_tokens where connection_id = ?",
            (connection_id,),
        ).fetchone()

    if not row:
        return {"linked": False, "connection_id": connection_id}

    creds = Credentials.from_authorized_user_info(json.loads(row[0]), [DRIVE_FILE_SCOPE])
    return {
        "linked": True,
        "connection_id": connection_id,
        "has_refresh_token": bool(creds.refresh_token),
        "scopes": creds.scopes,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
        "updated_at": row[1],
    }


def google_auth_start(request: Request) -> Response:
    connection_id = get_connection_id(request)
    base_url = get_base_url(request)
    redirect_uri = f"{base_url}/auth/google/callback"
    state = uuid.uuid4().hex

    flow = create_flow(redirect_uri)
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
    )
    with closing(connect()) as db:
        db.execute("delete from oauth_states where created_at < ?", (int(time.time()) - 600,))
        db.execute(
            """
            insert into oauth_states (state, connection_id, code_verifier, created_at)
            values (?, ?, ?, ?)
            """,
            (state, connection_id, flow.code_verifier, int(time.time())),
        )
        db.commit()

    response = RedirectResponse(authorization_url)
    response.set_cookie("google_oauth_state", state, max_age=600, httponly=True,
                        secure=base_url.startswith("https://"), samesite="lax")
    return response


def google_auth_callback(request: Request) -> Response:
    state = request.query_params.get("state")
    if not state or not hmac.compare_digest(state, request.cookies.get("google_oauth_state", "")):
        return JSONResponse({"error": "missing_state"}, status_code=400)

    with closing(connect()) as db:
        row = db.execute(
            "delete from oauth_states where state = ? returning connection_id, code_verifier, created_at",
            (state,),
        ).fetchone()
        db.commit()
        if not row:
            return JSONResponse({"error": "invalid_state"}, status_code=400)

        connection_id = row[0]
        code_verifier = row[1]
        if int(time.time()) - int(row[2]) > 600:
            return JSONResponse({"error": "expired_state"}, status_code=400)

        base_url = get_base_url(request)
        redirect_uri = f"{base_url}/auth/google/callback"
        query_string = request.url.query
        authorization_response = redirect_uri
        if query_string:
            authorization_response = f"{authorization_response}?{query_string}"

        flow = create_flow(redirect_uri)
        flow.code_verifier = code_verifier
        try:
            flow.fetch_token(authorization_response=authorization_response)
        except Exception:
            return JSONResponse({"error": "Google authorization failed. Start linking again."}, status_code=400)

        credentials_json = flow.credentials.to_json()
        db.execute(
            """
            insert into google_tokens (connection_id, credentials_json, updated_at)
            values (?, ?, ?)
            on conflict(connection_id) do update set
                credentials_json = excluded.credentials_json,
                updated_at = excluded.updated_at
            """,
            (connection_id, credentials_json, int(time.time())),
        )
        db.execute("delete from oauth_states where state = ?", (state,))
        db.commit()

    return HTMLResponse(
        """
        <!doctype html>
        <html>
          <head><title>Google connected</title></head>
          <body>
            <h1>Google Slides access connected</h1>
            <p>You can close this tab and return to Vibe.</p>
          </body>
        </html>
        """
    )


def google_auth_status(request: Request) -> Response:
    connection_id = get_connection_id(request)
    return JSONResponse(token_status(connection_id))


def load_credentials() -> Credentials:
    with closing(connect()) as db:
        row = db.execute("select credentials_json from google_tokens where connection_id = 'default'").fetchone()
    if not row:
        raise RuntimeError("Google is not linked. Open /auth/google/start on this server first.")
    creds = Credentials.from_authorized_user_info(json.loads(row[0]), [DRIVE_FILE_SCOPE])
    if not creds.valid:
        try:
            creds.refresh(GoogleRequest())
        except Exception:
            raise RuntimeError("Google access expired or was revoked. Reconnect at /auth/google/start.") from None
        with closing(connect()) as db:
            db.execute("update google_tokens set credentials_json = ?, updated_at = ? where connection_id = 'default'",
                       (creds.to_json(), int(time.time())))
            db.commit()
    return creds
