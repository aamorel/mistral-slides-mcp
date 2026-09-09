# MCP Slides MVP

Eight MCP tools create, read, revise, extend and style Google Slides presentations,
and manage saved defaults for future decks.
Generation uses a topic or supplied content, Mistral drafts the text, and
**each authenticated user's own Google account** provides access and storage.

MCP URL: https://mistral-slides-mcp-production.up.railway.app/mcp

## Documentation

- [User guide](USER-README.md): connect and try example requests.
- [Authentication reference](AUTH.md): frozen flow, access policy, tokens and operation.
- [Current MVP scope](src/mcp_slides/mvp/SCOPE.md): supported tools and limits.
- [Submission checklist](submission-plan.md): remaining acceptance and handoff work.
- [OAuth publishing plan](oauth-publishing-plan.md): client-only access and rollout.
- [Google Console rollout steps](google-oauth-rollout.md): deployment settings and UI checklist.
- [Original assignment](scope.md): preserved as supplied.
- [Historical investigation](investigation-questions.md): superseded experiments.

The code and current scope define capabilities; the historical log is not a setup
guide. Last local validation on 2026-09-09: all 77 automated tests passed. Deployment
of the latest commit and live acceptance still need confirmation; a Git push alone
is not evidence of either.

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
The start command remains `uv run mcp-slides`. Add the pilot access and usage
settings from `.env.example`; follow [the rollout checklist](google-oauth-rollout.md). `CONNECTOR_BEARER_TOKEN` is no longer
used by the MVP and may be removed from Railway.

**The old static-header connector must reconnect using OAuth.** Remove its static
Authorization header and reconnect. If Vibe retains its old authentication type,
add a new connector pointing at the same `/mcp` URL, without custom headers.
Existing decks are unaffected. Startup removes legacy grants without verified
identity and grants excluded by the current policy. Everyone, including the
owner, must reconnect once after this identity-policy upgrade; reconnecting also
starts fresh preferences.

Keep this exact redirect URI authorized in the existing Google client:

```text
https://mistral-slides-mcp-production.up.railway.app/auth/google/callback
```

Enable the Google Slides API. Google scopes are `drive.file`, `openid`, and
`https://www.googleapis.com/auth/userinfo.email` (the canonical `email` scope).
The last recorded Google configuration is Testing, which still requires each
account to be listed as a tester. After publishing, the server continues to admit
only the configured Workspace domain and verified personal email exceptions.
Publishing and deployed acceptance remain separate rollout steps.

`TOKEN_DB_PATH=/data/tokens.sqlite3` persists both Google credentials and connector
OAuth records. Keep one service instance and the volume attached across deploys.
The schema addition is automatic and preserves the investigation tables.
`GET /health` reports `"auth": "oauth"` after this version is deployed.

## Pilot usage controls

`PILOT_MAX_PAID_CALLS=100` permits 100 provider-call attempts over the lifetime of
this SQLite database, across all users. Outline generation, image conversations,
text edits, and generated insertions share the allowance. Explicit validation
retries and failures count; SDK retries are disabled. Reads and styling do not
consume this allowance. A deck normally takes two calls, but may take more after
validation retries. An image conversation can contain multiple internal steps,
so this is not a dollar/euro cap.

`PILOT_MAX_CONCURRENT_CALLS=2` bounds simultaneous paid provider requests within
the process. Keep one worker and one Railway replica. Budget exhaustion, busy
capacity, and paused generation return actionable tool errors.
`PILOT_PAID_CALLS_ENABLED=false` pauses new paid calls after redeployment; reads
and styling remain available to admitted users. Calls already started may finish.

The counter survives restarts. To grant more usage, raise the lifetime ceiling;
do not delete the token database. Review available Mistral credits/model costs
before increasing it. See [operation and rollout](google-oauth-rollout.md).

## Authentication design

Authentication is frozen for the pilot. Vibe receives connector tokens; the
server keeps separate Google credentials for each authorized connection and
checks the configured company domain or personal exceptions.

See [AUTH.md](AUTH.md) for the complete flow, security controls, token lifecycle,
storage tradeoffs, and troubleshooting. Use [the rollout checklist](google-oauth-rollout.md)
for Google Console and Railway configuration.

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

The tool contract explains the two input modes; shared server instructions guide
Vibe to create immediately when a topic or source text is supplied.
A broad request such as “Create a presentation about phones” should call generation
with `topic="phones"`, using three content slides plus a generated image cover and the saved default style. Missing
optional details should not trigger questions, a create/edit menu, or outline
approval. Planning is reserved for explicit planning requests; missing required
source material or unsupported requirements warrant clarification. Actual conversational
behavior depends on the host model. Refresh the connector's tool definitions
after deploying this change. No additional authorization scopes are needed.

`slide_count` defaults to 3
and must be an integer from 1 to 6. Optional audience and tone are limited to 300
and 200 characters. Each content slide uses a key message, bullets, comparison, or steps layout. A new opening title slide
with a generated background image is always added: `slide_count=3` means four
slides total (one cover plus three content slides). The return value contains `presentation_id`, `presentation_url`,
`title`, the applied `style_settings`, current `style_guidance`, `content_slide_count`, `total_slide_count`, and
`cover_image="generated"`.

Generation results include current styling guidance so the client receives it even
when tool metadata or earlier chat messages are stale. Refresh connector metadata
and start a fresh conversation after contract changes; reconnecting authentication
alone may not refresh tool descriptions. Client wording is still model-generated.

Every new deck uses the connection's default colors and font automatically.
Generation has no `style` argument or named presets. Use `set_presentation_style` afterwards for deck-specific changes. Without saved
preferences, the default is a white background with a faint blue corner gradient, blue titles (`#244B63`), charcoal
body text (`#263238`), and Arial. `set_default_style` changes the defaults for
future decks; `reset_default_style` restores these built-in settings. Partial
changes are merged and validated by the server in one database transaction; no preliminary read is needed.
The renderer applies these settings directly; the cover image generator also
receives the resolved palette.

On the first successful generation in a conversation, the assistant briefly
mentions styling this deck or saving default colors and font for future presentations. This
optional discovery message belongs in chat; there is no mandatory selection step.
Once-per-conversation behavior depends on the client's context, not persisted
server state. A request to style only one deck must not silently change saved
defaults. Users can explicitly apply their current default to an existing deck
with `set_presentation_style(use_default_style=True)`; the assistant must not create a replacement without a user request.

Google access is checked before spending a Mistral request. Invalid model output
is retried once and validated before deck creation. If population fails after
creation, the error includes the created deck URL; review it before retrying.
Calls are not idempotent: repeated requests create another deck.

## Content slide types

The public generation arguments are unchanged. Mistral selects an internal `type`
for each content slide, based on the material. Users may request types through
`instructions`; there is no required layout-selection step. Both topic and content
mode support all types. Content mode must not invent facts to manufacture variety.

| Type | Content | Limits |
| --- | --- | --- |
| `key_message` | Title and a large unbulleted statement | Message ≤180 characters |
| `bullets` | Title and 1–5 bullets | Each ≤140 characters; total ≤420 |
| `comparison` | Title and two columns, each with a heading and 1–3 bullets | Heading ≤40; each bullet ≤80; total ≤180 per column |
| `steps` | Title and 2–5 numbered steps | Each ≤100 characters; total ≤350 |

Deck/slide titles are limited to 80 characters. Text must be single-line and
nonempty. Unknown types, extra fields, and over-budget content are rejected;
Mistral gets one retry before generation fails. The renderer validates again
before creating a Google file. `layouts.py` defines fixed geometry and stable text
roles, shared with reading, editing, and deck styling. Mistral supplies content,
never coordinates or Google API requests.

All four types support wording edits and deck styling. Existing simple
title/bullet decks remain editable. Edits preserve each box's paragraph
count and native bullet/number markers; adding/removing items and converting slide
types remain unsupported. Font sizes and text budgets are conservative, but live
visual fit still needs checking, especially with customized fonts and long words.

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

- `src/mcp_slides/mvp/`: application (`server`, `oauth`, `auth`, `outline`, `layouts`, `slides`, `editing`, `styling`, `preferences`, `backgrounds`, `insertion`).
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

## Historical live validation — 2026-09-08

Registered **Mistral Slides Personal** (`mistral_slides_personal_4365`) through
Studio's custom connector UI against the deployed `/mcp` endpoint. Studio detected
OAuth 2.1 and dynamically registered `mistral-mcp-client` without manually entered
client credentials. Its return URI was
`https://callback.mistral.ai/v1/integrations_auth/oauth2_callback`.

This recorded session predates the latest tool changes. It is not acceptance
evidence for the current release. Earlier standalone Google authorization and
generation were reported successful in the investigation log.

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

The deck workflow uses `generate_presentation`, `get_presentation`, and
`edit_slide`, `add_slide`, and `set_presentation_style`; three additional tools manage saved styles. Reading is annotated as read-only; editing
is explicitly a mutation. The existing Google `drive.file` permission remains
sufficient for accessible decks. The internal connector scope `slides.generate`
retains its name for compatibility and covers all eight tools; it is not a
separate read-only permission. The consent page describes creation, reading and
text revision, adding content slides, and changing presentation colors/font.

`get_presentation` is a separate tool because reading is useful on its own
("What's on slide two?") and helps Vibe choose an edit. It provides the current
slide IDs, supported elements, and revision needed by `edit_slide`.

For "Make slide two clearer," the intended flow is:

1. Vibe reads the deck and identifies the second slide and its editable text.
2. Vibe calls `edit_slide` with that slide's ID, the revision, and the request.
3. The server rereads the deck, rejects a stale revision, and prepares the edit.
   Google also checks the revision when applying the update.
4. Vibe returns the same deck link and briefly describes what changed.

The user does not need to request the read step or handle IDs. The exposed read
helps the assistant understand the request; the internal read and validation
protect the write. Editing does not rely on the assistant having read correctly.

Call `get_presentation(presentation_id)` first. It reads the current Google deck,
including manual changes, and returns `revision_id`, ordered slides with stable
`slide_id` values, and normalized elements with `element_id`, `type`, `editable`,
and `unsupported_reason` where applicable. Text is represented per element, not
as a fixed title/bullets slide schema. Groups list their children; images, tables,
charts and other elements are acknowledged without pretending their contents
were interpreted. Image alt text is returned only when provided by Google.
Speaker notes, inherited master/layout contents and visual previews are omitted
explicitly in the returned limitations.

After successful generation, shared server instructions guide Vibe to show the
deck link followed by a brief optional invitation, such as
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

### Adding a slide to an existing deck

Use `get_presentation`, then `add_slide(presentation_id, expected_revision_id,
instructions, source_content?, after_slide_id?)`. Omitting `after_slide_id` appends;
supplying an existing ID inserts immediately after it. Positions include the cover.
Each call adds one content slide, using the same four layouts and text budgets as
generation. It keeps the same URL and preserves all existing elements and manual
edits. It does not create a cover, regenerate the deck, or change existing layouts.
The generation limit of six content slides does not cap later additions.

The new slide inherits colors/font from the closest supported content slide.
If no readable supported style exists, it uses the connection's current saved
default and returns a warning that the new slide may differ. The assistant must
report that warning. Defaults are loaded only when this fallback is needed.
Only the original 720 × 405 point page size is supported; deck text context is
limited to 60,000 serialized characters. Original source briefs are not stored.

The server validates the new slide and sends creation, text and styling together
with a required revision check. Existing object IDs are never write targets.
Results include `status=added`, the same `presentation_url`, `slide_id`, one-based
`position`, `total_slide_count`, new slide content, `style_source` and `warnings`.
If a write is unconfirmed, the error identifies the expected new slide ID: reread
and check it before deciding to retry. Never blindly retry a non-idempotent addition.

Shared server instructions route wording to `edit_slide`, additions to
`add_slide`, and deck style changes to `set_presentation_style`. They require
checking the entire request before mutation: unsupported requirements must be
explained and scope clarified, not silently discarded or tested by calling a tool.
Failure never authorizes a replacement deck. Refresh client tool metadata after
deployment; conversational adherence still requires live acceptance testing.

Editing is deliberately narrow:

- Only recognized original ungrouped text boxes (titles, bodies, key messages,
  comparison headings/columns, and steps) with supported text
  structure can be revised. These IDs identify the MVP layout, not ownership;
  Google permissions enforce access. Missing/replaced/grouped boxes are not
  reconstructed. A slide may contain additional unsupported elements; those
  remain untouched.
- Each paragraph must have uniform text styling and no hyperlinks or automatic
  text fields. Boxes must have 1–10 nonempty paragraphs and at most 2,000 text
  characters. Paragraph count stays fixed. New text is limited to the greater
  of the current paragraph length and its role-specific limit, while respecting
  a total box budget (or its current total length when already longer).
- Revisions change only the specified text ranges. Newlines carrying paragraph
  and bullet structure remain intact, and insertion occurs before deletion so
  neighboring text styling is retained. Shapes and their geometry are not
  rebuilt. Visual fit and live formatting still need manual verification.
- `edit_slide` does not add slides; use `add_slide` for that. No slide removal, reordering, layout conversion, image/chart/table
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
acknowledged write, not a later readback or visual verification. Reuse the returned
`revision_id` only when it is available and sufficient context is already known;
otherwise read again before a subsequent edit. Errors do not claim success or
create replacement decks.

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
6. Ask “Add a slide about risks after slide two.” Confirm one slide is inserted,
   the URL stays the same, and the original slides and cover remain unchanged.
   Then revise the new slide's title and check that the revision succeeds.
7. Change the saved default, then append a slide to the old deck. Confirm it
   matches the existing readable style. For a deck without readable supported
   style, confirm the saved-default fallback is explicitly reported.
8. Ask “Add a slide with an image” or “Add another bullet to slide two.” Confirm
   the assistant explains the limitation before calling a mutation tool and never
   regenerates the deck as a fallback.

Automated tests mock both providers; they do not substitute for these live checks.


## Saved default styles

`get_default_style()` returns this connection's settings and a readable Markdown
summary. `set_default_style(settings)` accepts only the fields to change;
`reset_default_style()` removes it. These tools do not execute Markdown or edit a
filesystem file. SQLite stores structured settings keyed by the authenticated
connection subject, never a user-supplied identity.

```json
{
  "settings": {
    "background": "#FAF5EB",
    "title_color": "#244B63",
    "body_color": "#263238",
    "font_family": "Georgia",
    "gradient": true,
    "gradient_color": "#93B4E8"
  }
}
```

Supply at least one field; omitted fields are preserved. Empty updates and explicit nulls are rejected. Fonts are limited to Arial, Verdana,
Georgia, and Trebuchet MS. Colors must be six-digit hex values; title and body
text each need at least 4.5:1 contrast across the entire background gradient. Unsupported fields
and unreadable combinations are rejected. The server merges partial requests with the saved settings and validates the complete result before saving.

Content slides use a deterministic PNG corner gradient at a fixed 28% maximum
tint, generated locally without a model call. `gradient` defaults to `true` and
`gradient_color` to `#93B4E8`, including for saved settings from older versions.
Set `gradient=false` to remove it from a deck or disable it for future decks.
On an existing deck, `gradient_color` alone enables the new tint; when saving
defaults, also set `gradient=true` if gradients were previously disabled.
The cover keeps its generated image and solid title band. Gradient assets use
the existing temporary image hosting and are cleaned up after Google's write.
Their original source URL retains rendering settings for reading and insertion;
unrecognized or replaced background images conservatively block slide styling.
Inserted slides inherit the nearest supported slide's gradient or plain background.

Only an explicit request such as “Save these colors as my default for future
presentations” should save preferences. One-deck requests never change defaults.
Generation resolves them internally; no preliminary read tool call is needed.
Preferences survive restarts and token refresh, but a new OAuth connection has a
new subject. Disconnect/revocation deletes its preferences. Saving alone does not
change existing decks. Saved styles do not support arbitrary layouts or imported templates.

## Style this presentation or save preferences

These are separate actions with separate effects:

| Request | Tool call | Effect |
| --- | --- | --- |
| “Make this deck's titles blue” | `set_presentation_style(..., changes={"title_color": "#244B63"})` | This deck only |
| “Use blue titles by default” | `set_default_style(settings={"title_color": "#244B63"})` | Future decks only |
| “Apply my defaults to this deck” | `set_presentation_style(..., use_default_style=True)` | Applies all saved colors/font to this deck |

`set_presentation_style` replaces `apply_default_style`. Refresh Vibe's connector
metadata after deployment. It requires `presentation_id` and
`expected_revision_id`, plus either `changes` or `use_default_style=true`, never
both. All presentation tools accept a Google Slides URL or ID. Read with
`get_presentation` for current IDs, revision and each slide's `style` support.
Saving preferences never changes an existing deck; editing a deck never saves preferences.

Partial deck updates write only supplied fields, preserving each slide's remaining
formatting. The server checks the resulting contrast against actual text colors
and backgrounds (the title band for covers). Unsupported slides, unreadable
inherited colors, or combinations below 4.5:1 contrast are skipped with reasons.
Font-only updates do not require color inference. Full defaults can replace all
colors without inferring old ones. No Mistral call is needed for styling.

Supported original slides preserve wording, sizes, emphasis, bullets, positions,
order and the cover image. The image is not recolored. Results report
`applied_slide_ids`, `skipped_slides`, `changes` and `warnings`; `status=unsupported`
means no slides were styled. `status=applied` acknowledges applying the settings,
even if some values already matched; it does not claim visual verification.

Edit, insertion and styling results share `status`, `presentation_url`,
`revision_id`, `changes` and `warnings`, plus operation-specific details. A successful
write returns Google's updated revision when provided; otherwise `revision_id`
is null and another read is required. A revision can be reused only when the
assistant already has the necessary context. The server still checks the revision
before writing. Conflicts and uncertain outcomes require a fresh read; never
blindly retry an insertion.

## Why eight tools?

Following the working-MVP focus in [scope.md](scope.md), tools represent distinct
user actions: create, read, revise, insert, style a deck, and read/save/reset
preferences. The server owns URL parsing, preference merging, content generation,
validation and Google API requests. This keeps the assistant's job focused on
intent and source context without introducing a second general-purpose agent.
The implementation uses the existing modules, with no new dependencies, database
migrations or Google scopes.

## Automatic title-slide image

Every generation requests one image through Mistral's Conversations API with the
`image_generation` tool, using the generated presentation title and resolved
palette. The full source document is not included in the image request. The
existing Mistral API key is used; image generation adds latency and API usage.
`MISTRAL_IMAGE_MODEL` optionally selects the image-capable orchestrating model
(default `mistral-medium-latest`), independently of the text model.

Downloaded PNG/JPEG/WebP data is decoded, size-checked and normalized to a 1600×900
PNG. The cover displays it behind an opaque title band with separately editable
text (`mvp_title_0`). Only the opening slide has an image; content slides use the
resolved colors/font. The requested content count remains 1–6, making 2–7 slides
total. Read current slide positions before editing: position 1 is now the cover.
Image changes remain unsupported by `edit_slide`.

Google fetches the image from a temporary `/assets/<random-token>.png` URL on the
same deployed server. This route is unauthenticated because Google must fetch it;
the 256-bit random token grants access only to that image. SQLite stores the token
hash, image bytes, connection subject, and ten-minute expiry. The image is removed
after deck creation finishes or fails; expired rows are cleaned during database
access, and revocation removes connection images. Tokens and image paths are not
included in application request logs. Google retains its inserted copy; the temporary
URL is not a permanent asset host. Mistral provider-side retention is separate;
conversation storage is disabled in the request.

If image generation or preparation fails, no Google deck is created and the tool
returns an error. If Google fails after creating a deck, the existing partial-deck
error returns its URL. Do not silently retry generation: repeated calls can incur
additional image charges and create duplicate decks. Image format checks are not
a visual-quality guarantee; verify covers and title fit in a live deck.

The existing Railway volume supports the new SQLite tables automatically. No new
Google scope or required environment variable is needed. The service must be
publicly reachable at `PUBLIC_BASE_URL` for Google's image fetch; a localhost-only
server needs a public tunnel for the complete image flow.
