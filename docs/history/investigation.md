# Historical MCP Slides Investigation — 2026-09-08

This is an archived record of experiments and decisions before the current MVP.
The one-tool, static-bearer, separate-Google-link design below is superseded;
these setup commands and “next actions” are historical, not deployment guidance.
The current server uses per-connection OAuth. Its maintained tool list and
feature boundaries are documented in the current MVP scope linked below.

Use [README.md](../../README.md) for setup and the
[current MVP scope](../capabilities.md) for capabilities.
Reported experimental successes do not establish acceptance of the current release.

## Target MVP

Build a deployed MCP server that Vibe can register as a Connector. The Connector exposes one tool:

```ts
generate_presentation({
  topic: string,
  slide_count?: number,
  audience?: string,
  tone?: string
}) => {
  presentation_id: string,
  presentation_url: string,
  title: string
}
```

The tool should:

1. Validate the request.
2. Ask Mistral for a strict JSON outline.
3. Create a Google Slides deck in the authenticated user's Google Drive.
4. Populate plain title-and-bullet slides.
5. Return the deck ID, URL, and title.

For the MVP, slide design is intentionally out of scope.

## Account And Service Setup Needed

- Mistral account with API key.
- Mistral organisation ID for assignment credits.
- Vibe / AI Studio access.
- Google Cloud project.
- Google OAuth consent screen.
- OAuth client for a web application.
- Google Slides API enabled.
- Google Drive API enabled if needed by the selected scope or client library.
- Deployment account, likely Railway, Render, or Fly.io.

## Questions To Answer

### 1. What MCP transport does Vibe require for a custom Connector?

Why it matters:
The server shape depends on whether Vibe expects Streamable HTTP MCP, SSE, a specific endpoint path, or additional discovery metadata.

How to answer:
Build the smallest possible deployed MCP server with one no-op tool, such as `ping() -> { ok: true }`. Register it in Vibe as a custom Connector and verify whether tool discovery succeeds.

Expected test output:
- Connector registration succeeds or fails.
- Vibe lists the `ping` tool.
- A direct call or chat-triggered call returns the static result.

Prerequisites:
- Vibe / AI Studio access.
- Public HTTPS deployment URL.

Decision:
- Use the transport and endpoint shape that Vibe accepts.

### 2. What authentication modes does Vibe support for our MCP server?

Why it matters:
The assignment wants a clean Connector experience. We need to know whether we can start with no auth, static bearer auth, or whether Vibe requires OAuth 2.1 for a user-facing connection flow.

How to answer:
Test the no-op MCP server in three modes if supported:

1. No authentication.
2. Static bearer token.
3. OAuth 2.1 / dynamic client registration.

Use Vibe's Connector setup and debugger to observe what it detects.

Expected test output:
- Which modes are accepted.
- What Vibe asks the user to configure.
- Whether OAuth setup redirects correctly.

Prerequisites:
- Deployed no-op MCP server.
- Vibe Connector debugger access.

Decision:
- Pick the simplest accepted auth mode that still supports user-scoped Google authorization.

### 3. Can Vibe Connector OAuth directly represent Google OAuth?

Why it matters:
The ideal flow is:

```text
User connects MCP Connector in Vibe
  -> Vibe starts OAuth
  -> User authorizes Google
  -> MCP tool receives enough user-scoped credential context
  -> Server creates a deck in that user's Drive
```

But this only works if Vibe's MCP OAuth flow can be bridged cleanly to Google OAuth.

How to answer:
Implement a minimal OAuth endpoint that redirects to Google OAuth and handles the callback. Register it as the Connector auth flow. Inspect what Vibe expects from the authorization server and what it sends on later MCP tool calls.

Expected test output:
- Whether Vibe accepts Google as the upstream consent step.
- Whether the MCP server can associate the resulting Google tokens with later tool calls.
- What headers, access tokens, or subject identifiers appear during tool calls.

Prerequisites:
- Google OAuth client.
- Redirect URI configured in Google Cloud.
- Vibe OAuth Connector test flow.

Decision:
- If this works, use Vibe Connector OAuth as the user-facing auth path.
- If not, build a separate app-level Google auth flow and expose a clear setup path.

### 4. What user identity is available during an MCP tool call?

Why it matters:
If we store Google refresh tokens, we need a stable key for each connected user. Without that, we cannot safely map a Vibe user to the right Google account.

How to answer:
Add temporary request logging to the no-op MCP server. Capture headers, auth claims, session identifiers, and any MCP metadata during tool discovery and tool invocation.

Expected test output:
- A stable user or credential identifier, if one exists.
- Clear distinction between connector-level identity and end-user identity.
- Confirmation of whether different users produce different identifiers.

Prerequisites:
- Deployed MCP server.
- At least two test accounts if possible.

Decision:
- Use the stable user/credential subject as the database key.
- If no stable identity is available, we need another token association strategy.

### 5. Can `drive.file` alone create and edit Google Slides decks?

Why it matters:
`drive.file` is the narrowest likely useful scope and is preferable because it is non-sensitive. We should verify it empirically with the exact create-and-populate flow.

How to answer:
Write a standalone Google OAuth script that requests only:

```text
https://www.googleapis.com/auth/drive.file
```

Then call:

1. `presentations.create`
2. `presentations.batchUpdate`

Expected test output:
- A new deck appears in the authenticated user's Google Drive.
- The deck contains a title slide and bullet slides.
- The returned URL opens successfully.

Prerequisites:
- Google Cloud project.
- OAuth client.
- Slides API enabled.
- Test Google account.

Decision:
- If `drive.file` works, use only that scope.
- If it fails, test `https://www.googleapis.com/auth/presentations` and document why the broader scope is required.

### 6. What Google OAuth publishing state is needed for reviewers?

Why it matters:
If the app remains in external testing mode, only allowlisted test users can authorize it. Reviewers may not be able to connect unless we add their emails.

How to answer:
After configuring the OAuth app, try authorization from:

1. A listed test user.
2. A Google account not listed as a test user.

If only `drive.file` is used, investigate whether publishing the app removes the test-user requirement without requiring sensitive-scope verification.

Expected test output:
- Whether non-test users can authorize.
- Whether Google shows an unverified/testing warning.
- Whether refresh tokens expire after the expected testing-mode window.

Prerequisites:
- Google OAuth consent screen.
- At least two Google accounts.

Decision:
- Either publish with non-sensitive scopes, or document that reviewer emails must be added as test users.

### 7. Does Google return refresh tokens reliably for this flow?

Why it matters:
Access tokens expire. If we cannot obtain or retain refresh tokens, users may need to reconnect frequently.

How to answer:
Run the standalone Google OAuth flow with:

```text
access_type=offline
prompt=consent
```

Then repeat authorization and token refresh tests.

Expected test output:
- Initial auth returns a refresh token.
- Stored refresh token can obtain a new access token.
- Repeated auth behavior is understood.

Prerequisites:
- Google OAuth client.
- Local or deployed callback URL.

Decision:
- Store encrypted refresh tokens if available.
- If refresh tokens are not reliable, design the UX around reconnecting.

### 8. What is the smallest reliable Google Slides batchUpdate payload?

Why it matters:
The MVP should avoid layout complexity. We need a stable sequence of create-slide and insert-text operations.

How to answer:
Create a script with a fixed outline:

```json
{
  "title": "Demo Deck",
  "slides": [
    { "title": "Slide 1", "bullets": ["A", "B", "C"] },
    { "title": "Slide 2", "bullets": ["D", "E", "F"] }
  ]
}
```

Generate a deck and inspect the result manually.

Expected test output:
- The script produces a readable deck.
- Batch updates are atomic and repeatable.
- Object IDs are deterministic enough for debugging.

Prerequisites:
- Working Google OAuth script.

Decision:
- Use this payload builder in the MCP implementation.

### 9. How should the MCP tool handle Mistral JSON generation?

Why it matters:
The tool must return a deck, not a malformed outline error caused by model drift.

How to answer:
Write a standalone Mistral script that asks for strict JSON and validates the result against a schema. Test a few topics, slide counts, audiences, and tones.

Expected test output:
- Valid JSON for common prompts.
- Validation catches malformed or overlong output.
- Retry-once behavior improves reliability.

Prerequisites:
- Mistral API key.
- Model selection.

Decision:
- Keep Mistral generation inside the MCP tool.
- Use schema validation before calling Google.

### 10. What deployment target gives the least friction?

Why it matters:
The assignment requires a deployed MCP server. The host needs stable HTTPS, env vars, logs, and ideally a small database.

How to answer:
Deploy the no-op MCP server to one candidate platform first, likely Railway or Render. Verify:

- HTTPS URL is stable.
- Env vars work.
- Logs are accessible.
- Server handles Vibe requests.
- Persistent storage option exists, if needed.

Expected test output:
- A public MCP URL that Vibe can reach.
- Repeatable deploy instructions.

Prerequisites:
- Deployment account.

Decision:
- Use the first platform that passes the no-op MCP registration test cleanly.

### 11. Do we need persistent token storage for the MVP?

Why it matters:
Persistent storage adds complexity, but without it the user may have to reconnect or the server may be unable to call Google after OAuth.

How to answer:
After understanding Vibe's auth behavior, test whether the tool call receives enough credential context to call Google immediately without server-side storage. If not, store refresh tokens keyed by the user identity discovered in question 4.

Expected test output:
- Either stateless calls work, or persistent refresh-token storage is required.

Prerequisites:
- Answers to questions 3, 4, and 7.

Decision:
- Prefer encrypted persistent storage if Vibe does not manage Google tokens directly for us.

### 12. What failure contract does Vibe display best?

Why it matters:
When auth, Mistral, or Google fails, the user should see a useful message instead of an opaque MCP failure.

How to answer:
Force controlled failures:

- Missing topic.
- Invalid slide count.
- Missing Google auth.
- Invalid Mistral API key.
- Google quota or permission failure, if easy to simulate.

Observe how Vibe displays tool errors.

Expected test output:
- Best format for user-visible errors.
- Distinction between validation errors, auth errors, and upstream API errors.

Prerequisites:
- Registered no-op or partial MCP Connector.

Decision:
- Implement structured errors in the format Vibe handles most clearly.

## Proposed Investigation Order

1. No-op deployed MCP Connector.
2. Vibe authentication behavior.
3. Google OAuth standalone script.
4. `drive.file` Slides create/edit test.
5. Google reviewer/test-user behavior.
6. Mistral strict JSON script.
7. Combine Mistral + Google locally.
8. Add real MCP tool.
9. Solve persistent auth/token mapping.
10. Final deployment and README.

## Deliberately Out Of Scope For MVP

- Custom slide themes.
- Images.
- Speaker notes.
- Existing deck editing.
- Folder selection.
- Collaboration/sharing settings.
- Multiple tools.
- Presentation templates.
- Long-running progress updates.
- User-facing web dashboard.

## Investigation Log

### 2026-09-07 - Investigation 1 Started: No-Op MCP Connector

Question:
Can our account register and call a private custom MCP Connector from Vibe/Studio?

Current implementation:
- Added a minimal Python MCP server at `src/mcp_slides/ping_server.py`.
- Added `pyproject.toml` with the official `mcp[cli]` dependency.
- Added `scripts/smoke_ping_client.py` to test the MCP protocol locally.
- Exposed one tool: `ping() -> { ok, server, purpose }`.
- Intended transport: Streamable HTTP.
- Intended endpoint after local start: `http://127.0.0.1:8000/mcp`.

Local test command:

```sh
uv run mcp-slides-ping
```

Expected local behavior:
- Server starts on `0.0.0.0:8000`.
- MCP endpoint is available at `/mcp`.
- MCP Inspector or another MCP client can list and call the `ping` tool.

Local smoke client command:

```sh
uv run python scripts/smoke_ping_client.py
```

Deployed smoke client command:

```sh
uv run python scripts/smoke_ping_client.py https://<railway-domain>/mcp
```

Deployment test:
Deploy the same server with this start command:

```sh
uv run mcp-slides-ping
```

The hosting platform must provide:
- A public HTTPS URL.
- A `PORT` environment variable, or support port `8000`.

Expected deployed Connector URL:

```text
https://<deployment-host>/mcp
```

Vibe/Studio test steps:
1. Open the Connectors page.
2. Click `+ Add Connector`.
3. Choose the custom MCP Connector option.
4. Use a private connector name such as `mcp_slides_ping`.
5. Enter the deployed `/mcp` URL.
6. Confirm whether Vibe detects no-auth Streamable HTTP.
7. Confirm whether Vibe lists the `ping` tool.
8. Call `ping` directly if the debugger supports direct invocation.
9. Ask Vibe something like: "Use `mcp_slides_ping` to ping the test server."

What to record:
- Whether private custom Connector creation is available on the account.
- Whether admin permissions are required.
- Whether `/mcp` is the correct endpoint.
- Whether no-auth is accepted.
- Whether Streamable HTTP is accepted.
- Whether Vibe lists the tool schema correctly.
- Whether Vibe can invoke `ping`.
- Any error messages from the Connector debugger.

Status:
- Server scaffold created.
- Local dependency install completed.
- Local smoke test passed.
- Confirmed the installed MCP SDK is 2.x, so the server uses `MCPServer` from `mcp.server.mcpserver`, not the older `FastMCP` import path.
- Confirmed local Streamable HTTP endpoint at `/mcp`.
- Confirmed local MCP tool discovery returns `ping`.
- Confirmed local MCP tool invocation returns structured content:

```json
{
  "ok": true,
  "server": "mcp-slides-investigation",
  "purpose": "Validate Vibe can discover and call a custom MCP tool."
}
```

- Deployment and Vibe registration still pending.

Railway deployment guide for this investigation:

1. Push this workspace to a GitHub repository.
2. In Railway, create a new project.
3. Choose `Deploy from GitHub repo`.
4. Select the repository.
5. In the Railway service settings, set the start command to:

```sh
uv run mcp-slides-ping
```

6. Keep the root directory as the repository root.
7. Do not configure a healthcheck yet. The current server exposes MCP at `/mcp`, not a plain `GET /health` route.
8. Deploy the service.
9. In the service `Networking` settings, generate a public domain.
10. Use the public MCP endpoint in Vibe:

```text
https://<railway-domain>/mcp
```

Railway-specific notes:
- Railway provides a `PORT` environment variable at runtime.
- The server reads `PORT` and binds to `0.0.0.0`, which Railway requires for public traffic.
- Railway did not infer a start command from this minimal Python project, so `railway.json` now sets `deploy.startCommand` explicitly.
- No secrets are needed for investigation 1.

Observed Railway build issue:

```text
Railpack 0.39.0
Detected Python
Using uv
No start command detected.
```

Fix applied:

```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "build": {
    "builder": "RAILPACK"
  },
  "deploy": {
    "startCommand": "uv run mcp-slides-ping"
  }
}
```

Expected Railway validation:
- Deployment logs show the server listening on `0.0.0.0:<PORT>`.
- Vibe/Studio accepts the `/mcp` URL as a custom MCP Connector.
- Vibe/Studio can discover and invoke `ping`.

Railway deployment result:
- Public domain: `https://mistral-slides-mcp-production.up.railway.app`
- MCP endpoint: `https://mistral-slides-mcp-production.up.railway.app/mcp`
- External MCP smoke test passed.
- Discovered tools: `["ping"]`
- `ping` returned:

```json
{
  "ok": true,
  "server": "mcp-slides-investigation",
  "purpose": "Validate Vibe can discover and call a custom MCP tool."
}
```

Remaining Investigation 1 work:
- None.

Vibe/Studio Connector result:
- Connector name/id: `slides_generator_6776`.
- Vibe successfully connected to the deployed `/mcp` endpoint.
- Vibe successfully invoked `ping`.
- Vibe displayed the structured response cleanly as a field/value table.
- Vibe reported two exposed functions:
  - `ping`
  - `read_resource`

Investigation 1 decision:
- Private custom MCP Connector creation is available on the account.
- Deployed Streamable HTTP MCP at `/mcp` is accepted by Vibe.
- No-auth is accepted for the basic smoke-test Connector.
- This transport/deployment shape is viable for the MVP.
- Next investigation should focus on auth behavior and whether user-scoped Google OAuth can be represented cleanly through Vibe's Connector flow.

Investigation 1 status:
- Complete.

### 2026-09-08 - Investigation 2 Started: Vibe Authentication Behavior

Question:
What authentication modes does Vibe support for our MCP server, and what request metadata does it send during discovery and invocation?

Implementation changes:
- Added safe HTTP request logging around the MCP app.
- Added `GET /health` for deployment health checks.
- Added optional static bearer auth for `/mcp`.
- The bearer gate is controlled by the `CONNECTOR_BEARER_TOKEN` environment variable.
- No bearer token is logged. Logs only record whether `Authorization` is present and what scheme it uses.
- Updated `scripts/smoke_ping_client.py` to accept a URL argument and optional `MCP_BEARER_TOKEN`.

Safe request fields logged:
- `method`
- `path`
- `host`
- `user_agent`
- `origin`
- `referer`
- `x_forwarded_for`
- `authorization_present`
- `authorization_scheme`
- `mcp_session_id_present`

No-auth local validation:

```sh
uv run mcp-slides-ping
uv run python scripts/smoke_ping_client.py
```

Result:
- Passed.
- Tool discovery returned `ping`.
- Tool invocation returned the expected structured payload.
- Logs showed `authorization_present: false`.

Bearer-auth local validation:

```sh
CONNECTOR_BEARER_TOKEN=test-token uv run mcp-slides-ping
uv run python scripts/smoke_ping_client.py
MCP_BEARER_TOKEN=test-token uv run python scripts/smoke_ping_client.py
```

Result:
- No-token MCP client failed with `401 Unauthorized`.
- Token-authenticated MCP client passed.
- Logs showed `authorization_present: true` and `authorization_scheme: "Bearer"` for authorized calls.

Railway test plan:
1. Set a Railway variable:

```text
CONNECTOR_BEARER_TOKEN=<temporary-shared-secret>
```

2. Redeploy.
3. Confirm `/health` returns `{"ok": true}`.
4. In Vibe, edit or recreate the custom MCP Connector.
5. Configure bearer auth with the same token, if the UI supports it.
6. Confirm Vibe can discover and invoke `ping`.
7. Watch Railway logs to record whether Vibe sends `Authorization: Bearer ...`.

What to record from Vibe:
- Whether the Connector UI offers bearer-token auth.
- Whether auth is configured at registration time or connection time.
- Whether Vibe accepts the bearer-protected `/mcp` endpoint.
- Whether failed auth appears clearly in the UI.
- Whether Vibe still exposes `ping` and `read_resource`.

Status:
- Local no-auth mode passed.
- Local static bearer mode passed.
- Deployment update completed.
- Vibe bearer-mode test passed.

Deployed no-auth Vibe result:
- Vibe successfully called `ping` after the logging/auth deployment.
- Railway logs show `user_agent: "MistralAI-MCPClient/1.0"`.
- Railway logs show repeated `POST /mcp` calls with `200 OK` and `202 Accepted`.
- Railway logs show `authorization_present: false`.
- Railway logs show `authorization_scheme: null`.
- Railway logs show `mcp_session_id_present: false`.
- Observed `x_forwarded_for` values include Mistral-originating public IPs plus Railway forwarding context.

Interim decision:
- In no-auth mode, Vibe does not send a user-level identity or authorization header to the MCP server.
- No-auth remains viable only for public/demo tools, not for user-scoped Google Drive access.
- Next auth test should set `CONNECTOR_BEARER_TOKEN` on Railway and configure bearer auth in Vibe, if the Connector UI supports it.

Deployed bearer-gated Vibe result:
- Railway variable `CONNECTOR_BEARER_TOKEN` was set.
- Railway redeployed successfully.
- Logs show `static bearer auth enabled for /mcp`.
- Vibe called the same `/mcp` endpoint without an `Authorization` header.
- Server correctly returned `401 Unauthorized`.
- Vibe surfaced this as:

```text
Error: Tool call failed: 502 - {"detail":"Upstream MCP server unavailable"}
```

Observed request metadata:
- `user_agent: "MistralAI-MCPClient/1.0"`
- `authorization_present: false`
- `authorization_scheme: null`
- `mcp_session_id_present: false`
- HTTP response: `401 Unauthorized`

Interim decision:
- The existing `slides_generator_6776` Connector is still configured as no-auth.
- Vibe does not automatically retry or prompt for bearer auth when the MCP server starts requiring it.
- A 401 from the upstream MCP server appears to the chat user as a 502/unavailable error.
- Next test is Connector-side bearer auth configuration: edit or recreate the custom Connector and provide the bearer token in Vibe's auth settings.

Bearer-token troubleshooting update:
- A direct deployed smoke test using `Authorization: Bearer test-vibe-bearer-2026` also returned `401 Unauthorized`.
- The Railway `CONNECTOR_BEARER_TOKEN` value did not exactly equal `test-vibe-bearer-2026`.
- Actual cause found: the Railway value was `test-vibe-bearer-2026 5`.
- Server auth was updated to normalize both server-side and client-side values:
  - `CONNECTOR_BEARER_TOKEN=test-vibe-bearer-2026`
  - `CONNECTOR_BEARER_TOKEN=Bearer test-vibe-bearer-2026`
  - `Authorization: Bearer test-vibe-bearer-2026`
  - `Authorization: test-vibe-bearer-2026`
- On auth failure, logs now include short SHA-256 fingerprints of expected/provided values, not the raw tokens.
- Local validation passed with a server env var containing the `Bearer ` prefix and a client header using the standard `Authorization: Bearer ...` format.

Deployed bearer-token mismatch result:
- Vibe sent an `Authorization` header.
- Logs showed `authorization_present: true` and `authorization_scheme: "Bearer"`.
- Vibe's provided token fingerprint was `0f90b65c2a3e`.
- Local fingerprint check confirmed `0f90b65c2a3e` is `test-vibe-bearer-2026`.
- Railway's expected token fingerprint was `e58cd8538776`.
- Conclusion: Vibe is configured correctly, but Railway's `CONNECTOR_BEARER_TOKEN` value is different from `test-vibe-bearer-2026`.
- Next action: update Railway's `CONNECTOR_BEARER_TOKEN` value to exactly `test-vibe-bearer-2026`, then redeploy.

Deployed bearer-auth Vibe success:
- Railway `CONNECTOR_BEARER_TOKEN` was corrected to exactly `test-vibe-bearer-2026`.
- Vibe Connector auth was configured with:

```text
Authorization: Bearer test-vibe-bearer-2026
```

- Vibe successfully connected and called `ping`.
- Expected log pattern: `authorization_present: true`, `authorization_scheme: "Bearer"`, and no `bearer_auth_failed` warning.

Investigation 2 decision:
- Vibe supports a static custom connection header for private MCP Connectors.
- The header must be configured explicitly in the Connector connection settings.
- Vibe does not infer or prompt for bearer auth after receiving an upstream `401`.
- A static bearer token is viable for protecting the MCP server from unauthenticated public access.
- Static bearer auth does not solve user-scoped Google authorization by itself; it only authenticates Vibe-to-MCP traffic.

Investigation 2 status:
- Complete for no-auth and static bearer auth.
- Full OAuth behavior remains a separate investigation.

### 2026-09-08 - Investigation 3 Started: Standalone Google OAuth And Slides API

Question:
Can a standalone script request `drive.file`, authenticate as a real Google user, create a Google Slides deck in that user's Drive, and populate simple slides?

Implementation changes:
- Added Google API dependencies:
  - `google-api-python-client`
  - `google-auth-oauthlib`
- Added `scripts/google_slides_smoke.py`.
- The script uses `google-auth-client.json` as the local OAuth client config.
- The user token cache is written to `.secrets/google-token-drive-file.json`.
- `.gitignore` now ignores both OAuth client filename variants and `.secrets/`.

Local run command:

```sh
uv run python scripts/google_slides_smoke.py
```

Expected behavior:
- Browser opens a Google OAuth consent flow.
- Requested scope is:

```text
https://www.googleapis.com/auth/drive.file
```

- Local callback uses:

```text
http://localhost:8081/
```

- Script creates a presentation titled `MCP Slides Smoke Test`.
- Script inserts two plain slides with title text boxes and bullet text boxes.
- Script prints:
  - `presentation_id`
  - `presentation_url`
  - `title`

Google Cloud prerequisites:
- Google Slides API enabled.
- Google Drive API enabled.
- OAuth consent configured with the user as a test user.
- OAuth client type: web application.
- Authorized redirect URI:

```text
http://localhost:8081/
```

What to record:
- Whether Google allows the `drive.file` scope without adding it manually in the Auth Platform UI.
- Whether the consent screen appears for the test user.
- Whether the script receives a refresh token.
- Whether `presentations.create` succeeds with only `drive.file`.
- Whether `presentations.batchUpdate` succeeds with only `drive.file`.
- Whether the created deck appears in the authenticated user's Google Drive.

Status:
- Script created.
- Compile check passed.
- OAuth/API run passed.

First OAuth run result:
- Google opened the consent URL but blocked it with `Error 400: redirect_uri_mismatch`.
- The script generated this redirect URI:

```text
http://localhost:8081/
```

- The Google OAuth client had been configured with:

```text
http://localhost:8081/oauth2callback
```

- Next action: add `http://localhost:8081/` exactly to the Google OAuth client's Authorized redirect URIs, then rerun the script.

Second OAuth run result:
- The redirect URI mismatch was resolved.
- Google then blocked authorization with `Error 403: access_denied`.
- Error message said the app is still in testing and only approved testers can access it.
- This confirms the OAuth app is in testing mode and the signing-in Google account must be explicitly added as a test user.

Next action:
- In Google Auth Platform, open `Audience`.
- Add this account as a test user:

```text
aurelien.morel.arthur@gmail.com
```

- Save the audience/test-user settings.
- Rerun:

```sh
uv run python scripts/google_slides_smoke.py
```

Successful OAuth/API run result:
- After adding the Google account as a test user, OAuth completed successfully.
- The script requested only:

```text
https://www.googleapis.com/auth/drive.file
```

- The script created and populated a real Google Slides deck.
- Created presentation:

```text
title: MCP Slides Smoke Test
presentation_id: 1YpurXOxYIEFZj0NGwlFBajpzWXAXJeQ7oBbp0DO2T-Q
presentation_url: https://docs.google.com/presentation/d/1YpurXOxYIEFZj0NGwlFBajpzWXAXJeQ7oBbp0DO2T-Q/edit
```

- Token cache was created at `.secrets/google-token-drive-file.json`.
- The cached token JSON includes a `refresh_token`.

Investigation 3 decision:
- `drive.file` is sufficient for creating a new Google Slides presentation.
- `drive.file` is sufficient for populating that presentation via `presentations.batchUpdate`.
- Google OAuth testing mode requires the signing-in user to be added under Auth Platform `Audience`.
- Before project review/submission, we should exit Google OAuth testing mode or explicitly add reviewer/examiner emails as test users.
- Preferred final path is publishing the OAuth app with only non-sensitive scopes, so reviewers can authorize with their own Google accounts without being allowlisted.
- `google-auth-oauthlib` local server flow uses `http://localhost:8081/` as the redirect URI for this script.
- For the MVP, user-owned deck creation through user-scoped Google OAuth is feasible.

Investigation 3 status:
- Complete for standalone Google OAuth, refresh token retrieval, `presentations.create`, and `presentations.batchUpdate`.

### 2026-09-08 - Investigation 4 Started: Mistral Strict JSON Outline

Question:
Can Mistral reliably generate a strict JSON presentation outline that we can validate before calling Google Slides?

Implementation changes:
- Added the official Mistral Python SDK dependency: `mistralai`.
- Added `scripts/mistral_outline_smoke.py`.
- The script requests JSON mode with:

```python
response_format={"type": "json_object"}
```

- The prompt still explicitly requests only a JSON object, matching Mistral's JSON mode guidance.
- The script validates:
  - top-level object
  - non-empty title
  - exact slide count
  - each slide title
  - exactly 3 bullets per slide
  - simple length limits

Local run command:

```sh
MISTRAL_API_KEY=<key> uv run python scripts/mistral_outline_smoke.py
```

Optional variants:

```sh
MISTRAL_API_KEY=<key> uv run python scripts/mistral_outline_smoke.py "Post-quantum cryptography for product leaders" --slide-count 3 --audience "B2B SaaS executives" --tone "direct and pragmatic"
MISTRAL_API_KEY=<key> MISTRAL_MODEL=mistral-medium-latest uv run python scripts/mistral_outline_smoke.py "Carbon accounting basics" --slide-count 5
```

Expected behavior:
- Script prints a valid JSON object with `title` and `slides`.
- Validation passes.
- Output can be passed directly to the Google Slides payload builder.

What to record:
- Which model was used.
- Whether JSON mode returned parseable JSON.
- Whether validation passed on the first attempt.
- Any validation failures or shape drift.
- Whether retry-once logic is needed before integrating into the MCP tool.

Status:
- Script created.
- Compile check passed.
- API run passed after adding `MISTRAL_API_KEY` to local `.env`.

Mistral API run results:
- `.env` is used locally for `MISTRAL_API_KEY`; it is gitignored.
- Default topic run passed.
- Variant run with `topic`, `audience`, and `tone` passed.
- JSON mode returned parseable JSON in both runs.
- Schema validation passed on the first attempt in both runs.
- Each run returned exactly 3 slides with exactly 3 bullets per slide.

Default run title:

```text
AI Agents for Sales Operations
```

Variant run command:

```sh
uv run python scripts/mistral_outline_smoke.py "Post-quantum cryptography for product leaders" --slide-count 3 --audience "B2B SaaS executives" --tone "direct and pragmatic"
```

Variant run title:

```text
Post-Quantum Cryptography for Product Leaders
```

Investigation 4 decision:
- Mistral JSON mode is sufficient for the MVP outline-generation step.
- We should still keep server-side validation and a retry-once path in the final MCP tool.
- The output shape can feed the Google Slides payload builder directly.

Investigation 4 status:
- Complete for strict JSON generation and validation.

### 2026-09-08 - Investigation 5 Started: Deployed Google OAuth Linking

Question:
Can the deployed MCP server host its own Google OAuth start/callback/status flow and persist user-scoped Google credentials server-side?

Why this matters:
This is the pragmatic fallback if Vibe's full OAuth Connector flow is hard to bridge directly to Google. It proves users can link Google to our deployed server, after which the MCP tool can create user-owned decks with stored Google refresh tokens.

Implementation changes:
- Added `src/mcp_slides/google_auth.py`.
- Added HTTP routes alongside `/mcp`:
  - `GET /auth/google/start`
  - `GET /auth/google/callback`
  - `GET /auth/status`
- Routes use `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` from environment variables.
- Routes request only `https://www.googleapis.com/auth/drive.file`.
- Tokens are stored in SQLite at `TOKEN_DB_PATH`, defaulting to `.secrets/tokens.sqlite3`.
- Connection id defaults to `default` and can be overridden with `?connection_id=...`.

Required Railway variables:

```text
GOOGLE_CLIENT_ID=<web-oauth-client-id>
GOOGLE_CLIENT_SECRET=<web-oauth-client-secret>
PUBLIC_BASE_URL=https://mistral-slides-mcp-production.up.railway.app
TOKEN_DB_PATH=/data/tokens.sqlite3
```

Railway storage note:
- `/data/tokens.sqlite3` requires a Railway volume mounted at `/data`.
- For a temporary investigation, a non-volume path may work until redeploy, but it is not durable.

Google Cloud prerequisites:
- Add this Authorized redirect URI to the same web OAuth client:

```text
https://mistral-slides-mcp-production.up.railway.app/auth/google/callback
```

- Keep the tester account allowlisted while the app is in testing mode.

Manual test flow:
1. Deploy the new code.
2. Open:

```text
https://mistral-slides-mcp-production.up.railway.app/auth/status
```

Expected before auth:

```json
{
  "linked": false,
  "connection_id": "default"
}
```

3. Open:

```text
https://mistral-slides-mcp-production.up.railway.app/auth/google/start
```

4. Complete Google OAuth.
5. Open `/auth/status` again.

Expected after auth:

```json
{
  "linked": true,
  "connection_id": "default",
  "has_refresh_token": true,
  "scopes": ["https://www.googleapis.com/auth/drive.file"]
}
```

What to record:
- Whether Google accepts the deployed callback URI.
- Whether testing-mode allowlisting still works.
- Whether the callback stores credentials.
- Whether `/auth/status` confirms `has_refresh_token: true`.
- Whether persistence survives a Railway restart or redeploy when using `/data`.

Status:
- Routes created.
- Compile check passed.
- Local route validation passed.
- Deployed OAuth run passed.

Local validation:
- Initial custom Starlette mounting broke `/mcp` because the MCP Streamable HTTP session manager lifespan was not initialized.
- Fix: use `mcp.custom_route(...)` for OAuth/status routes and let the MCP SDK own the Streamable HTTP app lifecycle.
- Confirmed locally:
  - `GET /health` returns `{"ok": true}`.
  - `GET /auth/status` returns `{"linked": false, "connection_id": "default"}` before auth.
  - MCP smoke client still discovers and calls `ping`.

First deployed OAuth run result:
- `GET /auth/status` returned `200 OK`.
- `GET /auth/google/start` redirected to Google successfully.
- Google redirected back to `/auth/google/callback` with an authorization code.
- Callback failed with:

```text
oauthlib.oauth2.rfc6749.errors.InsecureTransportError: OAuth 2 MUST utilize https.
```

Cause:
- Railway terminates HTTPS at the edge and forwards to the app internally.
- Starlette's `request.url` appeared as `http://...` inside the container.
- OAuthlib rejected the token exchange because the authorization response URL was reconstructed from the internal HTTP URL.

Fix:
- Reconstruct the callback authorization response URL from `PUBLIC_BASE_URL` plus the callback query string.
- This keeps the URL passed to OAuthlib as `https://mistral-slides-mcp-production.up.railway.app/auth/google/callback?...`.

Second deployed OAuth run result:
- The HTTPS reconstruction fix worked.
- Callback then failed during token exchange with:

```text
oauthlib.oauth2.rfc6749.errors.InvalidGrantError: (invalid_grant) Missing code verifier.
```

Cause:
- `google-auth-oauthlib` automatically generates a PKCE `code_verifier` when creating the authorization URL.
- The deployed callback created a new `Flow` instance and did not restore the original verifier.
- Google requires the original verifier to exchange the authorization code.

Fix:
- Store `flow.code_verifier` in the `oauth_states` table with the OAuth `state`.
- Restore `flow.code_verifier` in `/auth/google/callback` before `fetch_token(...)`.
- Added a small SQLite migration for existing `oauth_states` tables without the `code_verifier` column.

Successful deployed OAuth result:
- After deploying the PKCE verifier fix, `/auth/google/start` completed successfully.
- Google redirected back to `/auth/google/callback`.
- The callback exchanged the authorization code for credentials.
- Credentials were persisted in the deployed SQLite token store.
- `/auth/status` confirmed the Google account is linked.

Investigation 5 decision:
- The deployed MCP server can host a working Google OAuth linking flow.
- The server can persist user-scoped Google credentials, including refresh tokens.
- This is a viable fallback architecture if Vibe's full OAuth Connector flow is not worth implementing for the MVP.
- Static bearer auth can protect Vibe-to-MCP traffic while Google OAuth links the user's Google account separately.

Investigation 5 status:
- Complete for deployed Google OAuth linking and token persistence.

## Investigation Close-Out

### Proven Facts

- Vibe can register a private custom MCP Connector.
- Vibe accepts a deployed Streamable HTTP MCP endpoint at `/mcp`.
- Vibe can discover and invoke MCP tools from the Railway deployment.
- Railway can deploy the Python/uv MCP server with `uv run mcp-slides-ping`.
- Static bearer auth works for Vibe-to-MCP traffic when configured as:

```text
Authorization: Bearer <token>
```

- In no-auth mode, Vibe does not send a useful user identity or authorization header to the MCP server.
- Google OAuth with `drive.file` works for a real Google account.
- `drive.file` is sufficient for `presentations.create`.
- `drive.file` is sufficient for `presentations.batchUpdate`.
- Google OAuth returns a refresh token with the tested flow.
- The deployed server can host `/auth/google/start`, `/auth/google/callback`, and `/auth/status`.
- The deployed server can persist Google credentials in SQLite.
- Mistral JSON mode can generate validated slide outlines.

### Remaining Unknowns

- Whether Vibe's full OAuth 2.1 Connector flow can be used as the primary user-facing auth flow.
- Whether Vibe exposes a stable user identity during authenticated MCP calls.
- How to map multiple Vibe users cleanly to distinct Google OAuth tokens.
- Whether the final Google OAuth app can be published out of testing mode without extra verification using only `drive.file`.
- Whether reviewer/examiner accounts must be added manually as test users if the app remains in testing mode.
- Whether the Railway volume-mounted SQLite token store survives all relevant redeploy/restart scenarios.
- Whether token storage needs encryption for the expected project quality bar.
- How Vibe best displays structured MCP tool errors for Google auth failures, validation failures, and upstream API failures.
- Whether Google Workspace's official MCP servers could replace some direct REST API calls later.

### Non-Blocking For MVP

These unknowns should not block building the super-minimal working version:

- Full Vibe OAuth 2.1 integration.
- Multi-user identity mapping.
- OAuth app publication out of testing mode.
- Token encryption.
- Rich error UX.
- Google Workspace MCP server evaluation.

### Recommended MVP Build Path

Use the proven pragmatic architecture:

```text
Vibe -> MCP server: static Authorization bearer header
User -> MCP server: separate Google OAuth link at /auth/google/start
MCP server -> Google Slides: stored user refresh token
MCP server -> Mistral: server-side API key from env
```

Implement one MCP tool:

```ts
generate_presentation({
  topic: string,
  slide_count?: number,
  audience?: string,
  tone?: string
}) => {
  presentation_id: string,
  presentation_url: string,
  title: string
}
```

Recommended MVP behavior:
1. Validate arguments.
2. Check that Google is linked via the default connection id.
3. Generate a strict JSON outline with Mistral.
4. Validate the outline.
5. Refresh Google credentials if needed.
6. Create a Google Slides deck.
7. Populate plain title-and-bullet slides.
8. Return the deck URL and metadata.

Recommended MVP constraints:
- Single linked Google account via `connection_id=default`.
- Static bearer auth for MCP traffic.
- `slide_count` default `3`, max `6`.
- Plain slides only.
- No images.
- No templates.
- No folder selection.
- No multi-user routing yet.

### Setup Notes For Next Thread

Required Railway variables:

```text
CONNECTOR_BEARER_TOKEN=<shared-secret-for-vibe>
GOOGLE_CLIENT_ID=<google-web-oauth-client-id>
GOOGLE_CLIENT_SECRET=<google-web-oauth-client-secret>
PUBLIC_BASE_URL=https://mistral-slides-mcp-production.up.railway.app
TOKEN_DB_PATH=/data/tokens.sqlite3
MISTRAL_API_KEY=<mistral-api-key>
```

Required Google OAuth redirect URIs:

```text
http://localhost:8081/
https://mistral-slides-mcp-production.up.railway.app/auth/google/callback
```

Known local files that must stay uncommitted:

```text
.env
google-auth-client.json
.secrets/
```
