# MVP scope

The MVP proves that a user can connect the MCP in Vibe, authorize their own Google account, and generate an editable presentation in their own Google Drive.

## Included

- Per-user Google authorization through the connector, with persisted credentials.
- Generation: `generate_presentation(topic?, slide_count=3, audience?, tone?, basis="topic", source_content?, instructions?, style="default")`.
- Saved connection-scoped colors/font in SQLite, with get/set/reset tools and a
  readable Markdown summary. Validated configuration, not executable Markdown.
- An automatic new title slide with a Mistral-generated image on every generation.
  `slide_count` counts content slides; total is `slide_count + 1`.
- Three built-in visual presets: Minimal (default), Dark, and Warm. The renderer
  applies consistent typography and colors to the same editable text boxes.
  Style selection is optional and applies only when creating a new deck.
- Reading: `get_presentation(presentation_id)` returns current slide/element IDs,
  text, revision ID, and explicit editability/unsupported reasons. It does not
  flatten slides into the generation schema or interpret visual elements.
- Revision: `edit_slide(presentation_id, slide_id, expected_revision_id,
  instructions, source_content?)` revises supported text on one slide at the same
  URL, preserving paragraph count and surrounding elements. Original briefs are
  not stored; needed source context and constraints must be supplied again.
- Topic mode drafts from a required topic. Content mode organizes required source
  text and prompts the model to preserve its claims; expansion requires explicit
  instructions. Existing topic-only calls remain supported.
- Optional instructions are passed to Mistral in both modes. The calling assistant
  supplies relevant conversation or notes as text; the tool cannot retrieve them.
- Mistral-generated content: 1–6 content slides, each with a title and three bullets, using a simple layout.
- Creation of a new Google Slides deck and return of its title, ID, and URL.
- Separate MVP code in this package; investigation scripts remain separate.

## Acceptance criteria

- A user can complete Google consent and return to Vibe.
- A generation request creates the requested content slides plus one populated title slide in that user's Drive, without an extra empty slide.
- The returned URL opens the created deck; the chat should copy it verbatim.
- Each connection uses its own Google credentials, with no shared-account fallback.
- Authentication or generation failures produce an error rather than a claimed success.
- Missing/blank mode-specific input, unknown modes, oversized input, or source
  content supplied in topic mode return errors before upstream API calls.
- Both modes and instructions reach Mistral through the MCP tool; automated tests
  verify routing and prompt construction. Source fidelity and host mode selection
  still require live evaluation.
- Reading includes manual Google Slides edits. Revision IDs guard against
  concurrent changes, and unsupported/invalid proposals cause no write.
- Revision results distinguish updated versus unchanged and include exact text
  changes. Uncertain write outcomes direct the caller to reread before retrying.
- Live iteration acceptance checks (including formatting preservation) are listed
  in README.md and remain pending for this extension.

The user has tested the live authorization and generation flow successfully. A bad link was reported despite the deck existing in Drive; verbatim-link instructions were added, and opening the chat's final link remains an acceptance check.

## Deferred

- Public onboarding without adding Google tester emails: see the [OAuth publishing plan](../../../oauth-publishing-plan.md).
- Richer layouts, content-slide images, image editing, user templates, native theme import, and restyling existing decks.
- Structural or visual editing, arbitrary/richly styled text boxes, speaker notes,
  source-brief persistence, undo, folder selection, and export formats.
- Broad public-launch readiness, including usage limits and further credential-storage review.

Current constraint: Google OAuth remains in testing mode. Users create decks in their own Drive, but generation uses the operator's Mistral API key.
