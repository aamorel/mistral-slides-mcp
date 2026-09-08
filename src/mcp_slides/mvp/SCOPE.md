# MVP scope

The MVP proves that a user can connect the MCP in Vibe, authorize their own Google account, and generate an editable presentation in their own Google Drive.

## Included

- Per-user Google authorization through the connector, with persisted credentials.
- One tool: `generate_presentation(topic, slide_count=3, audience?, tone?)`.
- Mistral-generated content: 1–6 slides, each with a title and three bullets, using a simple layout.
- Creation of a new Google Slides deck and return of its title, ID, and URL.
- Separate MVP code in this package; investigation scripts remain separate.

## Acceptance criteria

- A user can complete Google consent and return to Vibe.
- A generation request creates the requested number of populated slides in that user's Drive, without an extra empty slide.
- The returned URL opens the created deck; the chat should copy it verbatim.
- Each connection uses its own Google credentials, with no shared-account fallback.
- Authentication or generation failures produce an error rather than a claimed success.

The user has tested the live authorization and generation flow successfully. A bad link was reported despite the deck existing in Drive; verbatim-link instructions were added, and opening the chat's final link remains an acceptance check.

## Deferred

- Public onboarding without adding Google tester emails: see the [OAuth publishing plan](../../../oauth-publishing-plan.md).
- Richer design, images, templates, and improvements to slide content.
- Editing existing decks, folder selection, and export formats.
- Broad public-launch readiness, including usage limits and further credential-storage review.

Current constraint: Google OAuth remains in testing mode. Users create decks in their own Drive, but generation uses the operator's Mistral API key.
