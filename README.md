# MCP Slides MVP

One MCP tool creates a plain Google Slides deck from a topic, using Mistral for
its outline and **each authenticated user's own Google account** for storage.

MCP URL: https://mistral-slides-mcp-production.up.railway.app/mcp

## Connect from Vibe

1. Add a custom MCP connector using the URL above. Do not add a shared
   Authorization header or supply the Google client secret to Vibe.
2. Vibe discovers OAuth and registers its OAuth client with this server.
3. Click Connect/Authorize. Our page identifies the requesting client and its
   return address. Click **Continue with Google**.
4. Choose your Google account and grant the requested access.
5. You return to Vibe, which stores your personal connector credentials. Ask it
   to create a presentation; the deck is created in the Google Drive you chose.

Vibe controls when it opens authentication. Its documented OAuth flow completes
before listing/calling tools, so the prompt may appear during connection rather
than after the first generation request. Once authorized, calls need no extra
manual linking, copied bearer token, email address, or user ID.

## Upgrade the existing deployment

Reuse the existing Railway service, `/data` volume, and Google web OAuth client.
The start command remains `uv run mcp-slides`. No new environment variables are
needed; keep the values in `.env.example`. `CONNECTOR_BEARER_TOKEN` is no longer
used by the MVP and may be removed from Railway.

**The old static-header connector must reconnect using OAuth.** Remove its static
Authorization header and reconnect. If Vibe retains its old authentication type,
add a new connector pointing at the same `/mcp` URL, without custom headers.
Existing decks are unaffected. The old `default` token row remains in SQLite but
is deliberately never used by the multi-user server. Everyone, including the
original owner, authorizes their own connection once.

Keep this exact redirect URI authorized in the existing Google client:

```text
https://mistral-slides-mcp-production.up.railway.app/auth/google/callback
```

The Google Slides API must be enabled. The only Google scope is `drive.file`.
While the Google OAuth app is in testing mode, each account authorizing access
must be added as a test user. Publishing the Google OAuth app is a separate step
before unrestricted reviewer/user onboarding; implementing per-user OAuth does
not remove Google's test-user restrictions.

`TOKEN_DB_PATH=/data/tokens.sqlite3` persists both Google credentials and connector
OAuth records. Keep one service instance and the volume attached across deploys.
The schema addition is automatic and preserves the investigation tables.
`GET /health` reports `"auth": "oauth"` after this version is deployed.

## Authentication design

```text
Vibe -> /mcp -> 401 + OAuth discovery metadata
Vibe -> /register -> client registration
Vibe -> /authorize -> per-client consent page -> Google consent
Google -> /auth/google/callback -> connector authorization code -> Vibe
Vibe -> /token with PKCE verifier -> personal access/refresh tokens
Vibe -> /mcp with personal token -> that connection's Google credentials
```

The MCP SDK implements discovery, registration, client authentication, redirect
validation, PKCE verification, and the OAuth token/revocation endpoints. Our
provider handles Google consent and durable token storage. A connection gets an
opaque, server-generated subject; all users of one Vibe client still get separate
subjects. Reconnecting creates a fresh connection. Google identity/email scopes
are unnecessary for this mapping, and Google tokens are never forwarded to Vibe.

- Explicit consent for the requesting client precedes Google OAuth.
- Google state is browser-bound, single-use, and expires after 10 minutes.
- Both OAuth legs use S256 PKCE; connector codes expire after 60 seconds.
- Access tokens expire after one hour. Refresh tokens expire after 30 days of
  inactivity and rotate on use; replay revokes that connection's token family.
- Connector access/refresh tokens and authorization codes are stored by hash.
- Tokens are restricted to this server's MCP resource and `slides.generate` scope.
- `/revoke` disconnects only the relevant Google connection and its connector
  tokens. Revoking Google access also disables that connection when detected;
  the tool explains that the user must reconnect in Vibe. Later requests get 401
  to trigger normal connector authentication again.
- Safe HTTP logs contain fixed route labels, response status and auth outcomes,
  never raw tokens, fingerprints, callback query strings, or request bodies.

Google credentials and OAuth client secrets remain plaintext in the private
SQLite volume, matching the MVP storage tradeoff. Encryption at rest, abuse
limits, and administration/cleanup of inactive connections are future hardening
work. Mistral usage is charged to the server owner's configured API key even
though decks belong to the individual users.

## Tool contract

```json
{
  "topic": "AI agents for sales teams",
  "slide_count": 3,
  "audience": "Sales leaders",
  "tone": "Practical"
}
```

`topic` is required (1–1,000 characters, not blank). `slide_count` defaults to 3
and must be an integer from 1 to 6. Optional audience and tone are limited to 300
and 200 characters. Each slide has a title and three bullets; there is no extra
cover slide. The return value contains `presentation_id`, `presentation_url`, and
`title`.

Google access is checked before spending a Mistral request. Invalid model output
is retried once and validated before deck creation. If population fails after
creation, the error includes the created deck URL; review it before retrying.
Calls are not idempotent: repeated requests create another deck.

## Code and local tests

- `src/mcp_slides/mvp/`: application (`server`, `oauth`, `auth`, `outline`, `slides`).
- `scripts/`, `src/mcp_slides/ping_server.py`, `src/mcp_slides/google_auth.py`:
  preserved investigation code, never imported by the MVP.
- `tests/`: Google consent/PKCE/refresh/revocation tests through HTTP, credential
  isolation, and real local MCP requests that verify per-user tool routing.

```sh
uv sync --locked
uv run python -m unittest discover -s tests -v
uv run --env-file .env mcp-slides
```

Use `.env.example` to populate `.env` without committing secrets. For local work,
set `PUBLIC_BASE_URL=http://localhost:8000` and
`TOKEN_DB_PATH=.secrets/mvp-tokens.sqlite3`. Authorize
`http://localhost:8000/auth/google/callback` in the Google client and set
`OAUTHLIB_INSECURE_TRANSPORT=1` for local HTTP only; never set it on Railway.
Use an OAuth-capable MCP client to connect to `http://localhost:8000/mcp`.
Opening `/auth/google/start` directly no longer links an account; it needs the
transaction created by the connector's authorization flow.

Tests mock Google/Mistral and make no external API calls. The protocol test binds
a temporary localhost port. Real Vibe interoperability and consent from a second
Google account must also be checked on the deployed version.

## Live validation — 2026-09-08

Registered **Mistral Slides Personal** (`mistral_slides_personal_4365`) through
Studio's custom connector UI against the deployed `/mcp` endpoint. Studio detected
OAuth 2.1 and dynamically registered `mistral-mcp-client` without manually entered
client credentials. Its return URI was
`https://callback.mistral.ai/v1/integrations_auth/oauth2_callback`.

The live browser flow reached our consent page, Google's account chooser, and
Google's testing-mode warning for the existing test account. Completion of Google
consent, return to Vibe, and a real per-user deck creation remain to be verified.
The previous **mistral-slides-mcp-mvp** connector remains registered with its old
`None` authentication type; use the personal OAuth connector for this test.

Two browser-only issues were fixed during this test: the consent page uses
`strict-origin` referrer policy so a form POST retains its origin, and its CSP
explicitly permits the Google authorization redirect. Origin checks, CSRF
validation, and browser-bound OAuth state remain enforced.

## References

- [Mistral: MCP connector authentication](https://docs.mistral.ai/vibe/work/connectors/mcp-connectors)
- [Mistral: connector management and user authentication](https://docs.mistral.ai/studio/connectors/management)
- [MCP: authorization and per-client proxy consent](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)
- [Google: web-server OAuth](https://developers.google.com/identity/protocols/oauth2/web-server)
