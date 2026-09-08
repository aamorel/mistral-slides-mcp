# MCP Slides MVP

One MCP tool creates a plain Google Slides deck from a topic, using Mistral for
its outline and the owner's linked Google account for storage.

Current MCP URL: https://mistral-slides-mcp-production.up.railway.app/mcp

## Code separation

- `src/mcp_slides/mvp/`: independent application (`server`, `auth`, `outline`, `slides`).
- `src/mcp_slides/ping_server.py`, `src/mcp_slides/google_auth.py`, and `scripts/`:
  preserved investigation code; the MVP does not import these.
- `tests/`: automated MVP tests, including real local MCP HTTP requests with mocked upstream APIs.
- `investigation-questions.md`: findings and decisions behind the MVP.

## Reuse the existing deployment

No new Railway service or Google OAuth client is needed. `railway.json` now starts
`uv run mcp-slides` and checks `/health`. The old entry point,
`uv run mcp-slides-ping`, remains available for investigation or rollback.

1. Keep the existing Railway service, public domain, and Google web OAuth client.
2. Set the variables in `.env.example` in Railway. Add `MISTRAL_API_KEY` if missing.
   Use a long random `CONNECTOR_BEARER_TOKEN`; do not reuse the investigation's
   publicly documented test token. Update the Vibe header to match.
3. Confirm a persistent Railway volume is mounted at `/data`, with
   `TOKEN_DB_PATH=/data/tokens.sqlite3`. Use one service instance. Existing token
   rows are compatible and the `default` connection is reused. An ephemeral
   database will lose its credentials when replaced.
4. Deploy the updated repository. There is no deployment or secret upload as part
   of the local build. Check `/health` after deployment.
5. If Google is already linked in this database, no new consent is needed.
   Otherwise open `/auth/google/start`. In the browser login prompt, use username
   `admin` and the connector bearer token as password. Complete Google consent.
   `/auth/status` uses the same login and confirms linking.
6. Refresh/reconnect the Vibe Connector so it discovers `generate_presentation`
   instead of `ping`. Keep the MCP URL and header:
   `Authorization: Bearer <CONNECTOR_BEARER_TOKEN>`.
7. Ask Vibe: “Create a 3-slide presentation about AI agents for sales teams.”

Keep this exact authorized redirect URI on the existing Google OAuth client:

```text
https://mistral-slides-mcp-production.up.railway.app/auth/google/callback
```

Google Slides API must be enabled. The only requested scope is `drive.file`.
While the OAuth app is in testing mode, add each account that needs to authorize
as a test user. All tool calls create decks in the **same linked Google account**;
this is an owner-only MVP, not a multi-user connector.

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
is retried once and validated before deck creation. Tool failures return MCP
errors with actionable messages. If population fails after creation, the error
includes the created deck URL; review it before retrying. Calls are not idempotent:
a repeated request creates another deck. A lost network response may also require
checking Drive before retrying.

## Local development and tests

```sh
uv sync --locked
uv run python -m unittest discover -s tests -v
uv run --env-file .env mcp-slides
```

Populate `.env` from `.env.example` without committing secrets. For local use,
set `PUBLIC_BASE_URL=http://localhost:8000` and
`TOKEN_DB_PATH=.secrets/mvp-tokens.sqlite3`. Add
`http://localhost:8000/auth/google/callback` to the existing Google client.
For local HTTP OAuth testing only, set `OAUTHLIB_INSECURE_TRANSPORT=1`;
never set it on Railway. Open `http://localhost:8000/auth/google/start` to link.

The test suite uses fake credentials and makes no external API calls. Its protocol
test binds a temporary localhost port. Server startup requires all five credential
and URL variables; it never silently exposes an unauthenticated MCP endpoint.

SQLite credentials remain plaintext, matching the investigated MVP tradeoff.
Protect the volume and secrets. OAuth state is short-lived, single-use, bound to
the initiating browser, and stores the PKCE verifier. HTTP access logging is
turned off to avoid logging callback codes. Multi-user OAuth, token encryption,
themes, images, and templates are deferred.
