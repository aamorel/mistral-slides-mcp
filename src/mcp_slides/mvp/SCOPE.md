# MVP scope

The MVP proves that a user can connect the MCP in Vibe, authorize their own Google account, and generate an editable presentation in their own Google Drive.

## Included

- Per-user Google authorization through the connector, with persisted credentials.
- One tool: `generate_presentation(topic?, slide_count=3, audience?, tone?, basis="topic", source_content?, instructions?)`.
- Topic mode drafts from a required topic. Content mode organizes required source
  text and prompts the model to preserve its claims; expansion requires explicit
  instructions. Existing topic-only calls remain supported.
- Optional instructions are passed to Mistral in both modes. The calling assistant
  supplies relevant conversation or notes as text; the tool cannot retrieve them.
- Mistral-generated content: 1–6 slides, each with a title and three bullets, using a simple layout.
- Creation of a new Google Slides deck and return of its title, ID, and URL.
- Separate MVP code in this package; investigation scripts remain separate.

## Acceptance criteria

- A user can complete Google consent and return to Vibe.
- A generation request creates the requested number of populated slides in that user's Drive, without an extra empty slide.
- The returned URL opens the created deck; the chat should copy it verbatim.
- Each connection uses its own Google credentials, with no shared-account fallback.
- Authentication or generation failures produce an error rather than a claimed success.
- Missing/blank mode-specific input, unknown modes, oversized input, or source
  content supplied in topic mode return errors before upstream API calls.
- Both modes and instructions reach Mistral through the MCP tool; automated tests
  verify routing and prompt construction. Source fidelity and host mode selection
  still require live evaluation.

The user has tested the live authorization and generation flow successfully. A bad link was reported despite the deck existing in Drive; verbatim-link instructions were added, and opening the chat's final link remains an acceptance check.

## Deferred

- Public onboarding without adding Google tester emails: see the [OAuth publishing plan](../../../oauth-publishing-plan.md).
- Richer design, images, templates, and improvements to slide content.
- Editing existing decks, folder selection, and export formats.
- Broad public-launch readiness, including usage limits and further credential-storage review.

Current constraint: Google OAuth remains in testing mode. Users create decks in their own Drive, but generation uses the operator's Mistral API key.
