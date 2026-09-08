# MCP Slides MVP

Three MCP tools create, read, and revise plain Google Slides presentations.
Generation uses a topic or supplied content, Mistral drafts the text, and
**each authenticated user's own Google account** provides access and storage.

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

`basis` is `"topic"` (the default, preserving existing calls) or `"content"`.
Topic mode requires `topic` (1–1,000 characters, not blank) and develops a story
from it. Supplying `source_content` in topic mode returns an error instead of
silently ignoring the material.

Content mode requires `source_content` (1–20,000 characters, not blank); `topic`
is optional framing. The assistant must pass the actual text from the user's
notes or relevant conversation: the tool cannot read chat history, fetch links,
or extract files itself. For example:

```json
{
  "basis": "content",
  "source_content": "The pilot involved 10 sales reps. Feedback was positive, but time savings have not been measured. The proposed next phase costs €5,000.",
  "slide_count": 3,
  "audience": "Sales leaders",
  "instructions": "Lead with the funding decision. Preserve the uncertainty about time savings."
}
```

`instructions` is optional in both modes (up to 2,000 characters) and goes directly
into the Mistral brief for purpose, emphasis, constraints, or explicit expansion
requests. Content mode prompts Mistral to preserve the supplied meaning and
qualifications, avoid adding facts, and omit gaps or identify missing information.
An instruction such as "Add a general introduction explaining AI agents" permits
that specific expansion. Source material is framed as data, not instructions.
These are model instructions, not a factual verification guarantee; validation
checks the output structure and lengths, not whether every claim is supported.

The tool description guides Vibe to infer the basis from user intent, briefly
state its approach, and clarify only material ambiguity. Actual conversational
behavior depends on the host model. Refresh the connector's tool definitions
after deploying this change. No additional authorization scopes are needed.

`slide_count` defaults to 3
and must be an integer from 1 to 6. Optional audience and tone are limited to 300
and 200 characters. Each slide has a title and three bullets; there is no extra
cover slide. The return value contains `presentation_id`, `presentation_url`, and
`title`.

Google access is checked before spending a Mistral request. Invalid model output
is retried once and validated before deck creation. If population fails after
creation, the error includes the created deck URL; review it before retrying.
Calls are not idempotent: repeated requests create another deck.

## Diagnosing an incorrect link in a chat answer

Open the presentation directly in Drive and compare its address with the raw
`generate_presentation` tool result's `presentation_url`. The tool uses Google's
returned `presentationId` directly and returns a URL ending in `/edit`. The model
is instructed to copy this URL verbatim; this is guidance, not a guarantee that
its final answer will preserve it.

On each successful tool call, Railway logs `presentation_result url_sha256=...`.
This is the SHA-256 hash of the exact UTF-8 URL returned by the tool. Compare a
candidate URL locally without writing the private deck link to server logs:

```sh
python -c 'import hashlib; print(hashlib.sha256(input("URL: ").encode()).hexdigest())'
```

A mismatch means that candidate URL differs from the tool's return value. It does
not by itself prove who changed it. Refresh the connector's tool definitions after
deployment to pick up the verbatim-link guidance.

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

## Read and revise an existing slide

The connector now exposes three tools: `generate_presentation`,
`get_presentation`, and `edit_slide`. Reading is annotated as read-only; editing
is explicitly a mutation. The existing Google `drive.file` permission remains
sufficient for accessible decks. The internal connector scope `slides.generate`
retains its name for compatibility and covers all three tools; it is not a
separate read-only permission. The consent page describes creation, reading and
text revision.

Call `get_presentation(presentation_id)` first. It reads the current Google deck,
including manual changes, and returns `revision_id`, ordered slides with stable
`slide_id` values, and normalized elements with `element_id`, `type`, `editable`,
and `unsupported_reason` where applicable. Text is represented per element, not
as a fixed title/bullets slide schema. Groups list their children; images, tables,
charts and other elements are acknowledged without pretending their contents
were interpreted. Image alt text is returned only when provided by Google.
Speaker notes, inherited master/layout contents and visual previews are omitted
explicitly in the returned limitations.

After successful generation, the server instructions and generation tool description
guide Vibe to show the deck link followed by a brief optional invitation, such as
"You can ask me to revise a slide—for example, make slide two less technical or
shorten the conclusion." Examples must fit the actual deck and the user's language.
This appears in chat, not on the slides. It does not require a response or trigger
an edit: the assistant waits for a user revision request. Actual wording and
compliance depend on Vibe and should be checked live after refreshing its tools.

```json
{
  "presentation_id": "ID_FROM_THE_CREATED_DECK",
  "slide_id": "mvp_slide_2",
  "expected_revision_id": "REVISION_FROM_GET_PRESENTATION",
  "instructions": "Make the uncertainty explicit. Keep the budget unchanged.",
  "source_content": "Feedback was positive, but time savings have not been measured. The budget is €5,000."
}
```

Pass these arguments to `edit_slide`. Instructions are required (1–2,000
characters); source text is optional (1–20,000 characters). No original brief or
source text is persisted: supply any needed facts and constraints again. Without
additional source text, Mistral is instructed to stay grounded in the current
slide. These are model instructions, not factual verification.

Editing is deliberately narrow:

- Only ungrouped `mvp_title_N` and `mvp_body_N` text boxes with supported text
  structure can be revised. These IDs identify the MVP layout, not ownership;
  Google permissions enforce access. Missing/replaced/grouped boxes are not
  reconstructed. A slide may contain additional unsupported elements; those
  remain untouched.
- Each paragraph must have uniform text styling and no hyperlinks or automatic
  text fields. Boxes must have 1–10 nonempty paragraphs and at most 2,000 text
  characters. Paragraph count stays fixed. New text is limited to the greater
  of the current paragraph length and 100 characters for titles / 180 for body.
- Revisions change only the specified text ranges. Newlines carrying paragraph
  and bullet structure remain intact, and insertion occurs before deletion so
  neighboring text styling is retained. Shapes and their geometry are not
  rebuilt. Visual fit and live formatting still need manual verification.
- No slide addition, removal, reordering, layout/design changes, image/chart/table
  edits, notes edits, undo, or visual assessment. The assistant is instructed to
  explain unsupported requests. Mistral can also decline a request; unsupported
  and invalid proposals cause no write. Model IDs, paragraph counts and lengths
  are validated before any write, with one retry for malformed model output.
- A stale/missing revision fails before generation. The final atomic Google batch
  uses `requiredRevisionId` to reject concurrent edits during generation. Writes
  are never automatically retried. If the outcome is uncertain, read the deck
  before deciding whether to retry.

The result reports `status` (`updated` or `unchanged`), the same presentation URL,
slide ID/position and exact `before`/`after` paragraph changes. It describes the
acknowledged write, not a later readback or visual verification. Read again for
any subsequent edit. Errors do not claim success or create replacement decks.

Implementation references: [Google text editing](https://developers.google.com/workspace/slides/api/guides/styling)
and [atomic batches and revision control](https://developers.google.com/workspace/slides/api/reference/rest/v1/presentations/batchUpdate).

### Live acceptance checks for iteration

Refresh Vibe's connector tools after deployment, then:

1. Generate a deck and confirm the chat includes the link and a brief invitation
   to request wording changes, with examples that fit its actual slide count.
   Then ask “Make slide two less technical; keep the budget.”
   Confirm the same link is returned and only the requested text changes.
2. Manually change a slide in Google Slides, then request a wording revision.
   Confirm the revision uses the manual wording and preserves bullets, fonts,
   images, positions, and the other slides. Include an emoji in one paragraph.
3. Request an unsupported operation, such as adding an image or reordering slides.
   Confirm the assistant explains the limitation and makes no changes.
4. Change the deck after reading its revision, then submit an edit with that old
   revision. Confirm it is rejected and the manual change survives.
5. Try an inaccessible deck from another Google account. Confirm access is denied.

Automated tests mock both providers; they do not substitute for these live checks.
