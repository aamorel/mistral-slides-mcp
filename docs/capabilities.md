# Current MVP scope

The MVP lets a user connect the MCP in Vibe, authorize their own Google account,
and create and revise presentations in their own Google Drive through conversation.
This document describes the current implementation, extending the
[original assignment](assignment.md). Remaining release and handoff tasks are
tracked in the [submission checklist](submission-checklist.md).

## Tools

Nine tools are exposed:

| Tool | Contract and purpose |
| --- | --- |
| `generate_presentation` | `topic?`, `slide_count=3`, `audience?`, `tone?`, `basis="topic"`, `source_content?`, `instructions?`. Creates a new deck. |
| `get_presentation` | `presentation_id`. Reads current text, slide/element IDs, revision, text editability, style support, and formatting metadata. |
| `set_slide_image` | `presentation_id`, `slide_id`, `expected_revision_id`, `image_url`, `replace=false`. Adds or explicitly replaces one attached image on a supported existing slide. |
| `edit_slide` | `presentation_id`, `slide_id`, `expected_revision_id`, `instructions`, `source_content?`. Revises supported text on one existing slide. |
| `add_slide` | `presentation_id`, `expected_revision_id`, `instructions`, `source_content?`, `after_slide_id?`. Inserts one content slide into the existing deck; appends by default. |
| `get_default_style` | No arguments. Returns the connection's current colors/font and readable Markdown summary. |
| `set_default_style` | `settings`. Saves partial colors/font changes for future decks; the server merges and validates atomically. |
| `reset_default_style` | No arguments. Restores the built-in default settings for the connection. |
| `set_presentation_style` | `presentation_id`, `expected_revision_id`, `changes?`, `use_default_style=false`. Changes this deck only. Supply partial changes or explicitly apply all saved defaults, never both. |

All `presentation_id` arguments accept a Google Slides URL or ID. Reading returns
per-slide `style` metadata separately from text editability. No new tools are
needed for partial style changes.

## Generation

- Topic mode develops a required topic. Content mode organizes required source
  text, preserving supplied claims and uncertainty; factual expansion requires
  explicit instructions. Both modes support all content slide types.
- The assistant supplies relevant conversation or notes as text. The server
  does not retrieve conversation history, linked documents, or uploaded source
  files for text generation. The separate image-placement tool retrieves a fresh
  image attachment reference supplied by the assistant.
- Each generation creates 1–6 total slides including an automatic opening title
  slide with a Mistral-generated background image. The default is three slides
  total (one title and two content slides); requesting one creates only the title slide. The cover image is required; preparation failure prevents deck creation.
- Mistral selects suitable slide types from the material and honors requested
  types through `instructions`. Variety must not require invented source facts.
- Strict schemas and text budgets constrain model output. The renderer controls
  fixed layouts and Google API requests; Mistral does not generate API calls.

| Content type | Structure and limits |
| --- | --- |
| Key message | Title and one unbulleted statement, at most 180 characters. |
| Bullets | Title and 1–5 bullets; at most 140 characters each, 420 combined. |
| Comparison | Title and two columns; each has a heading of at most 40 characters and 1–3 bullets, at most 80 characters each and 180 combined per column. |
| Steps | Title and 2–5 numbered steps; at most 100 characters each, 350 combined. |

Deck and content-slide titles are limited to 80 characters. Content is nonempty,
single-line plain text. Invalid outlines get one model retry, then fail; the
renderer validates again before creating a Google file.

## Presentation style and future defaults

- Future-deck defaults use one configuration per connection, stored in SQLite.
  The style sheet is a readable Markdown representation of validated settings,
  not a physical editable `.md` file or executable Markdown instructions.
- Settings are background, title and body colors (`#RRGGBB`), plus Arial, Verdana,
  Georgia, or Trebuchet MS, plus `gradient` (default true) and `gradient_color`
  (default `#93B4E8`). The corner tint has a fixed gentle intensity. Text colors
  require at least 4.5:1 contrast across every rendered gradient stop.
- Before customization, defaults are white (`#FFFFFF`), blue titles (`#244B63`),
  charcoal body text (`#263238`), and Arial. There are no named style presets.
- `set_presentation_style(changes=...)` changes only the supplied colors/font on
  this deck, preserving unspecified formatting on each slide. It never saves defaults.
- `set_default_style(settings=...)` merges supplied fields with current defaults
  in one transaction. Empty updates, nulls and invalid combinations are rejected.
- New decks automatically use the current default. Saving or resetting it does
  not modify existing decks. Applying it to an existing presentation requires
  an explicit request and a revision-protected call to
  `set_presentation_style(use_default_style=True)`.
- Deck styling can update supported slide backgrounds, text colors/font and
  the cover title band. It preserves wording, sizes, emphasis, bullets, layout,
  order, the cover image, and managed attachments; images are not regenerated or recolored.
- Slides containing unsupported elements, unreadable colors needed for validation,
  or insufficient resulting contrast are skipped entirely with reasons. Partial
  color changes are checked against retained colors; font-only changes do not
  require color inference. No model call is needed for styling.
- Settings survive restarts and token refresh, but belong to the connection,
  not the Google account. Reconnecting starts a new preference scope;
  disconnect/revocation deletes that connection's preferences.

## Reading and iteration

- Reading reflects actual Google Slides elements, including manual changes.
  It does not flatten decks into the generation schema. Images, charts, tables,
  and groups are listed but not visually interpreted.
- Wording edits support recognized original ungrouped text boxes in all four
  layouts and the cover title, including older title/bullet decks. Mixed-style
  paragraphs, linked text, and automatic text fields are unsupported.
- Text edits preserve each box's paragraph/item count and surrounding formatting.
  They cannot add/remove bullets or steps, or convert an existing slide's layout.
- All tools that mutate existing decks reread the deck and use Google's required revision check.
  Stale revisions prevent writes. Unconfirmed writes are not automatically retried;
  the caller must reread before deciding what to do next.
- Edit, insertion, image placement and styling results share `status`, `presentation_url`,
  `revision_id`, `changes` and `warnings`, plus operation-specific fields. Writes
  return the updated revision from Google when supplied, otherwise null. Reuse it
  only with sufficient context; missing revisions or conflicts require a fresh read.
- Text edits report updated/unchanged; insertion reports added; styling reports
  applied/unsupported with skipped slides; image placement reports added/replaced. None implies visual verification.
- `add_slide` inserts one content slide at the end or after an existing slide,
  preserving existing objects, manual edits and the same URL. All four content
  types are supported. Original 720 × 405 point page size is required; serialized
  deck text context is capped at 60,000 characters. Later additions are not capped
  by the six-total-slide generation limit (including the cover).
- Added slides match the nearest readable supported content slide's colors/font;
  otherwise use the saved default and return a warning the assistant must report.
  Added objects retain the naming convention required by text editing and styling.
- Unconfirmed insertions identify the proposed slide ID for duplicate checks on
  reread. No automatic retries or replacement generation.
- Original briefs are not stored. Supply needed source facts and constraints again.

## Conversational UX

### Images on existing slides

Reading exposes `image_placement` support and whether a managed image is present.
`set_slide_image` accepts a fresh Vibe attachment URL on the configured storage
host. It supports original key-message and bullet slides: title remains full
width, text narrows on the left, and one contained image is centered on the right.
Text IDs, wording, formatting, the same deck and neighboring slides are preserved.
The original 720 × 405 point page size, supported text geometry and original font
sizes are required. Manual layout changes are rejected. Standard Google bullet
indentation up to 36 pt is accepted, including PT/EMU conversion tolerance.
Unsupported paragraph formatting is reported separately from text that does not
fit: shortening text does not fix a formatting rejection.

Text limits beside images: 90 characters for a message, or 1–3 bullets with 55
characters per item and 150 total, plus a conservative wrapping check. Wide text
can be rejected below those limits. Font sizes are preserved, not automatically reduced. Wording edits retain these limits; styling
preserves the image. Slide insertion can inherit its style without copying it.

PNG/JPEG/WebP attachments must be single-frame, at most 5 MiB and 20 megapixels.
Normalization honors orientation, retains transparency, strips metadata and bounds
the longest side to 1600 pixels. Temporary publication uses existing connection
storage and cleanup; Google Slides retains the inserted image after cleanup.
The connector does not send attachments to the Mistral API, and placement consumes
no model allowance. Failed retrieval leaves the deck unchanged and requests
re-upload. Uncertain Google writes require rereading the reported image ID before
retrying. Occupied slots require an explicit replacement request and `replace=true`.

Fresh attachment forwarding was verified in the
[isolated probe](../scripts/investigation/image_attachment_probe/RESULTS.md).

### Requests and defaults

A creation request with a topic or source content should generate directly, using
defaults without a create/edit menu, mandatory outline approval, or style selector.
Ask only for missing required information or clarification of unsupported requests.

After success, copy the returned URL verbatim and briefly invite relevant wording
edits or adding a content slide. Once per conversation, introduce styling this
deck or saving preferences for future decks. “Make the titles blue” applies to
the current deck; “Use blue titles by default” changes future preferences. A
request to do both uses both tools. Generation results include current style guidance
so the assistant does not rely solely on cached metadata or old chat messages.
Refresh tool metadata and use a fresh conversation when testing contract changes;
client-generated wording still needs live verification.

Acknowledge unsupported requests. Do not silently save one-deck style requests,
drop unsupported operations from text edits, or create replacement decks without
being asked.

## Validation and release constraints

Authentication and the connection UI are frozen for the pilot as of 2026-09-09.
[auth reference](auth.md) defines the accepted behavior; remaining work is
configuration, release checks, and bug fixes, not auth feature expansion.

- Automated validation on 2026-09-09: all 100 tests passed, covering schemas, API request construction,
  MCP discovery/invocation, authentication isolation, preferences, supported edits,
  partial style updates, URL normalization, and revision/error handling.
  This is local mocked-provider evidence, not deployed acceptance.
- A live Mistral text-generation check successfully produced all four types.
  Earlier live Google authorization and generation were tested by the user.
- Live acceptance of the latest layouts and mutations was confirmed by the user
  on 2026-09-10: visual fit
  at text limits and across fonts, source fidelity, links, numbering preservation,
  cover image handling, skipped slides, and conversational feature discovery.
- If the Google OAuth app is in Testing, accounts must also be approved Google
  test users. Publishing and deployment configuration are tracked in the [submission checklist](submission-checklist.md#4-verify-google-oauth-and-onboarding).
  Client-only admission and global usage controls are implemented locally, with
  deployed admission acceptance confirmed by the user on 2026-09-10. Configure verified `mistral.ai` Workspace access
  and personal exceptions; remove the friend exception before submission.
  Defaults: 100 lifetime paid provider calls, two concurrent calls, and an operator
  pause switch. These are operation limits, not a currency spending cap.
- Google access uses each connection's credentials and `drive.file`, plus
  `openid` and email identity scopes for admission; no shared
  Google-account fallback. Mistral calls use the operator's API key.
- Deployment requires public HTTPS and persistent SQLite storage on the existing
  single-instance service. Temporary covers, gradients and normalized attachments
  use expiring capability URLs for Google's image fetch and are cleaned up after
  the operation, with expiry as a backstop.

## Outside this freeze

- More layouts, arbitrary visual design, templates, native theme imports,
  creation-time attachments, multiple images per slide, cropping, image removal,
  placement on comparisons/steps/covers, and image content editing/regeneration.
- Slide removal/reordering, changing list counts, layout conversion,
  arbitrary/rich text editing, speaker notes, undo, folder selection, and export.
- Google-account-scoped preferences and persisted source briefs.
- Broad public-launch features such as per-user quotas and further credential-storage
  hardening. Review operational limitations before expanding access.
