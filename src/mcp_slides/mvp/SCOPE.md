# Current MVP scope

The MVP lets a user connect the MCP in Vibe, authorize their own Google account,
and create and revise presentations in their own Google Drive through conversation.
This is the first feature-freeze candidate: the next work is acceptance testing,
fixes, OAuth publishing, repository cleanup, and code ownership. The remaining
submission work is tracked in [submission-plan.md](../../../submission-plan.md).

## Tools

Seven tools are exposed:

| Tool | Contract and purpose |
| --- | --- |
| `generate_presentation` | `topic?`, `slide_count=3`, `audience?`, `tone?`, `basis="topic"`, `source_content?`, `instructions?`. Creates a new deck. |
| `get_presentation` | `presentation_id`. Reads current text, slide/element IDs, revision, text editability, style support, and formatting metadata. |
| `edit_slide` | `presentation_id`, `slide_id`, `expected_revision_id`, `instructions`, `source_content?`. Revises supported text on one existing slide. |
| `get_default_style` | No arguments. Returns the connection's current colors/font and readable Markdown summary. |
| `set_default_style` | `settings`. Saves a complete validated default configuration; partial requests first read and merge existing settings. |
| `reset_default_style` | No arguments. Restores the built-in default settings for the connection. |
| `apply_default_style` | `presentation_id`, `expected_revision_id`. Applies the connection's current default to supported existing slides at the same URL. |

## Generation

- Topic mode develops a required topic. Content mode organizes required source
  text, preserving supplied claims and uncertainty; factual expansion requires
  explicit instructions. Both modes support all content slide types.
- The assistant supplies relevant conversation or notes as text. The server
  cannot retrieve conversation history, URLs, or uploaded files itself.
- Each generation creates 1–6 content slides plus an automatic opening title
  slide with a Mistral-generated background image. The default is four slides
  total. The cover image is required; preparation failure prevents deck creation.
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

## Default style sheet

- Styling uses one default configuration per connection, stored in SQLite.
  The style sheet is a readable Markdown representation of validated settings,
  not a physical editable `.md` file or executable Markdown instructions.
- Settings are background, title and body colors (`#RRGGBB`), plus Arial, Verdana,
  Georgia, or Trebuchet MS. Text colors require at least 4.5:1 background contrast.
- Before customization, defaults are white (`#FFFFFF`), blue titles (`#244B63`),
  charcoal body text (`#263238`), and Arial. There are no named style presets or
  per-deck style overrides.
- New decks automatically use the current default. Saving or resetting it does
  not modify existing decks. Applying it to an existing presentation requires
  an explicit request and a revision-protected call to `apply_default_style`.
- Applying defaults updates supported slide backgrounds, text colors/font and
  the cover title band. It preserves wording, sizes, emphasis, bullets, layout,
  order, and the cover image; that image is not regenerated or recolored.
- Slides containing unsupported elements are skipped entirely to avoid mismatched
  text/background contrast. Results report applied slide IDs and skipped reasons.
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
- Both mutation tools reread the deck and use Google's required revision check.
  Stale revisions prevent writes. Unconfirmed writes are not automatically retried;
  the caller must reread before deciding what to do next.
- Text edits report updated/unchanged and exact changes. Style application reports
  applied/unsupported with skipped slides; neither implies visual verification.
- Original briefs are not stored. Supply needed source facts and constraints again.

## Conversational UX

A creation request with a topic or source content should generate directly, using
defaults without a create/edit menu, mandatory outline approval, or style selector.
Ask only for missing required information or clarification of unsupported requests.

After success, copy the returned URL verbatim and briefly invite relevant wording
edits. Once per conversation, introduce default-style customization and its explicit
application to an existing deck. Generation results include current style guidance
so the assistant does not rely solely on cached metadata or old chat messages.
Refresh tool metadata and use a fresh conversation when testing contract changes;
client-generated wording still needs live verification.

Acknowledge unsupported requests. Do not silently save one-deck style requests,
drop unsupported operations from text edits, or create replacement decks without
being asked.

## Validation and release constraints

- Automated coverage: 49 passing tests covering schemas, API request construction,
  MCP discovery/invocation, authentication isolation, preferences, supported edits,
  style application, and revision/error handling.
- A live Mistral text-generation check successfully produced all four types.
  Earlier live Google authorization and generation were tested by the user.
- Live acceptance of the latest layouts and mutations remains pending: visual fit
  at text limits and across fonts, source fidelity, links, numbering preservation,
  cover image handling, skipped slides, and conversational feature discovery.
- Google OAuth remains in testing: accounts must be approved testers. Publishing
  is a submission task in [oauth-publishing-plan.md](../../../oauth-publishing-plan.md).
- Google access uses each connection's credentials and `drive.file`; no shared
  Google-account fallback. Mistral calls use the operator's API key.
- Deployment requires public HTTPS and persistent SQLite storage on the existing
  single-instance service. Temporary cover images use expiring capability URLs
  for Google's image fetch and are cleaned up after generation.

## Outside this freeze

- More layouts, arbitrary visual design, templates, native theme imports,
  content-slide images, and image editing/regeneration.
- Slide addition/removal/reordering, changing list counts, layout conversion,
  arbitrary/rich text editing, speaker notes, undo, folder selection, and export.
- Google-account-scoped preferences and persisted source briefs.
- Broad public-launch features such as usage quotas and further credential-storage
  hardening. Review operational limitations before expanding access.
