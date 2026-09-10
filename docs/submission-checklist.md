# Before submission

Goal: deliver a working deployed connector, a clear repository, and an
implementation I can explain and maintain confidently.

Feature-freeze candidate: generate from topic or source content using key messages,
flexible bullets, comparisons, and steps; read decks; revise supported text; insert
content slides; style an existing deck; save defaults for future decks; and
automatically generate an image cover; add or explicitly replace one attachment
on an existing supported key-message or bullet slide. The [current scope](capabilities.md)
defines the contract; [original assignment](assignment.md) remains the original assignment.
After acceptance testing these flows, freeze new features and focus on correctness,
visual fit, deployment, OAuth publishing, repository cleanup, and code ownership.
Adding/removing items and converting existing layouts remain deferred.

Documentation synchronized on 2026-09-10. Local automated validation recorded on
2026-09-09: 100 tests passed. The user confirmed completion of all live acceptance
tests on 2026-09-10. Checked live tests below reflect that confirmation; the exact
tested deployment commit was not supplied. Unchecked release and ownership tasks
remain pending.

Auth and the connection UI are frozen for the pilot; [auth reference](auth.md) is the
implementation reference. Configuration and removal of the friend exception
remain release tasks unless separately confirmed.

## 1. Understand and own the code

- [ ] Trace generation: `server.py` → `presentation_service.py` → `outline.py` → `layouts.py` / `slides.py`.
  Explain inputs, Mistral instructions, validation, Google writes, and partial failures.
- [ ] Trace reading and editing: `server.py` → `editing.py`.
  Explain element IDs, supported text, paragraph preservation, revision checks,
  and why reading is both an exposed tool and an internal editing step.
- [ ] Trace insertion: `server.py` → `insertion.py` → `slides.py`. Explain
  style inheritance, insertion position, revision checks and duplicate prevention.
- [ ] Trace styling: `server.py` → `styling.py` / `preferences.py`. Explain this
  deck versus future defaults, partial updates, contrast checks and skipped slides.
- [ ] Trace attachment placement: `server.py` → `slide_images.py` → `attachments.py`
  and `backgrounds.py`. Explain fresh references, layout validation, temporary
  publication/cleanup, explicit replacement and uncertain-write recovery.
- [ ] Trace authentication: `server.py` → `oauth.py` → `auth.py`.
  Explain the Vibe-to-server and server-to-Google OAuth relationships, per-user
  credential mapping, refresh, revocation, and the responsibilities of the MCP SDK.
- [ ] Read a success test and a failure test for each flow.
- [ ] Make a small useful change myself and predict its effects on the tests.
- [ ] Explain the main tradeoffs without relying on the code: narrow editing
  support, model instructions versus guaranteed validation, no stored source
  briefs, plaintext Google credentials in SQLite, and one service instance.

## 2. Clean up the repository

- [x] Keep the main README focused on capabilities, trying the connector, local
  setup, architecture, deployment, and known limitations.
- [ ] Reconcile historical validation notes with what has actually been tested;
  distinguish user-confirmed results from checks still pending.
- [x] Update `docs/user-guide.md` with a short generation-and-editing example and the
  actual supported editing boundaries.
- [x] Update the package description in `pyproject.toml` and use `README.md` as
  the package README. Preserve `docs/assignment.md` as the original assignment.
- [x] Include `editing.py` in the architecture module list linked from the README.
- [x] Move supporting documentation into `docs/`, preserve history under
  `docs/history/`, and label retained experiments in `scripts/investigation/`.
- [ ] Review tracked files and Git history for accidentally committed secrets
  or credentials. If found, revoke/rotate them and address repository exposure.
- [ ] Avoid unnecessary package renames or authentication refactors before submission.

## 3. Verify reproducibility and operation

- [ ] Install from a fresh checkout with `uv sync --locked` and run the documented tests.
- [x] Add a small CI workflow that installs from the lockfile and runs the test suite.
  Workflow added locally; confirm its first hosted run after pushing.
- [x] Confirm the setup instructions cover required environment variables,
  Google API/redirect configuration, Railway start command, and persistent volume.
- [x] Document the single-instance SQLite assumption and basic failure diagnosis.
- [x] Document shared Mistral call limits and the operator pause switch. These
  bound paid attempts, not currency spending; all users consume the operator's key.
- [ ] Confirm the deployed allowance is appropriate for evaluation.
- [x] Review and document credential storage and disconnection behavior. Keep
  broader public-launch hardening separate from the limited submission scope.

## 4. Verify Google OAuth and onboarding

The implementation is frozen in [auth reference](auth.md); use its
[deployment configuration](auth.md#deployment-configuration) for Google and Railway.
Keep the following live checks open until their outcomes are recorded.

- [x] Implement the client-domain gate, owner and temporary friend exceptions,
  and global usage controls.
- [ ] Confirm the deployed version and Railway allowlists/usage settings match
  the frozen implementation before handoff.
- [ ] Confirm Google Data Access matches the implemented scopes in `docs/auth.md`.
- [ ] Review Audience, Branding, and Verification Center requirements, then
  publish the external OAuth app when ready.
- [x] Verify the owner can connect with the submission allowlist.
- [x] Connect through Vibe with a client account that was never a test user;
  confirm its verified domain is admitted and unrelated accounts are denied.
- [x] Verify that the created deck belongs to that account and its returned link opens.
- [x] Verify reconnecting and credential refresh; reconnect older testing grants
  where necessary.
- [ ] Update user-facing tester instructions only after the new onboarding flow
  is confirmed. Describe any remaining prompts accurately.

- [ ] Before submission, set Railway `GOOGLE_ALLOWED_EMAILS` to
  `aurelien.morel.arthur@gmail.com` and restart to purge the friend's connections.
  Verify both old tokens and new login are denied for the friend, while owner
  and client retain access. Removing a Google tester entry alone is insufficient.

Publishing with server-enforced client-only access is the preferred handoff. If
blocked, arrange reviewer test accounts and document the limitation; do not
present onboarding as unrestricted.

## 5. Run the final deployed acceptance pass

Refresh Vibe's connector tool definitions after deployment. Automated tests mock
Google and Mistral; these checks exercise the real providers and conversation.

- [x] Add a fresh attachment to short message/bullet slides, then explicitly
  replace it. Verify full-image fit, transparency/orientation, preserved wording,
  fonts and deck URL. Revise wording/style afterward. Check crowded text,
  unsupported layouts, occupied slots and re-upload recovery. Local geometry
  previews and mocked tests do not replace this Google acceptance.

- [x] Verify standard generated bullet indentation accepts “What Are Frogs?” with
  “Amphibians with smooth, moist skin”, “Live in water and on land”, and
  “Undergo metamorphosis from tadpoles to adults”. Confirm a genuine formatting rejection is not presented as
  a request to shorten text. Confirm fonts remain the same size.
- [x] Verify an inserted image remains visible after temporary URL expiry and
  inserting a neighboring slide does not copy its image.

- [x] Generate from a topic and open the exact returned link in the correct Drive.
- [x] Ask “Create a presentation about phones” with no other details. Confirm
  immediate generation of three total slides including one image cover using saved defaults without a create/edit menu or
  questions about optional inputs. Separately verify an explicit planning request
  stays in conversation until creation is requested.
- [x] Save a default style, generate a deck, and verify it
  is applied. Verify partial changes preserve other settings, reset works,
  and a second connection cannot read or change the first connection’s preference.
- [x] Verify the automatic image cover, editable title, extra-slide count, and
  temporary image fetch from the deployed server.
- [x] Generate from supplied content and check that facts and uncertainty are preserved.
- [x] Confirm the post-generation chat invitation offers relevant wording edits.
- [x] Generate with built-in defaults and customized colors/font. Check visual fit,
  contrast, bullets, and wording revisions in each. Confirm style discovery is brief and
  distinguishes styling this deck from saving defaults for future decks.
- [x] Generate all four content types in topic and content mode. Check short and
  maximum-length content, 1 and 5 bullets, asymmetric comparisons, and numbered
  steps in each supported font. Inspect overflow, column spacing and readability.
- [x] Revise a comparison column and a numbered step; verify neighboring text,
  paragraph counts and numbering remain intact. Apply defaults to all four types.
- [x] Confirm unsupported requests to add/remove items or convert layouts are
  acknowledged without silently rewriting or creating a replacement deck.
- [x] Change only a deck's title color, then only its font. Verify unspecified
  formatting and saved defaults are preserved, including slides with different
  existing colors. Check low-contrast and unreadable-color skips.
- [x] Pass a Google Slides URL directly when reading or styling a deck.
- [x] Apply saved defaults to an existing deck. Verify the same URL, updated
  colors/font and cover band, unchanged text/layout/image, and skipped-slide
  reporting. Check revision conflicts and readback of actual formatting.
- [x] Insert after slide two and append a conclusion. Verify slide order, the
  same URL, unchanged existing slides, inherited style and explicit fallback warnings.
  Revise the inserted slide; check that an uncertain insertion is read before retrying.
- [x] Chain supported mutations using returned revisions when context is sufficient;
  confirm stale revisions still reject writes and missing revisions require a read.
- [x] Revise one slide; verify the same deck URL and unchanged surrounding slides.
- [x] Check that fonts, bullets, positions, and unsupported elements survive the edit.
- [x] Manually edit text in Google Slides, then revise it through Vibe; verify the
  tool uses the current wording. Include an emoji to exercise Unicode handling.
- [x] Request an unsupported operation, such as adding a second image to one slide or reordering
  slides; verify a clear explanation and no unintended changes.
- [x] Submit an edit with a stale revision; verify rejection and preservation of
  the intervening manual change.
- [x] Try an inaccessible deck from another account; verify access is denied.
- [x] Redeploy/restart the service and verify the connection survives through the
  persistent volume.
- [ ] Record the exact tested deployment commit and any remaining limitations.
  Live acceptance completion was confirmed by the user on 2026-09-10.

## 6. Prepare and send the submission

- [ ] Confirm the final commit is pushed, deployed, and matches the tested version.
- [ ] Confirm reviewers can access the GitHub repository and deployed MCP URL.
- [ ] Prepare a short demo: connect → generate → attach an image to slide 2 → revise → explain one limitation.
- [ ] Optionally record the demo as a fallback and quick overview.
- [ ] Prepare a concise handoff containing the repository link, deployed MCP URL,
  connection instructions, example prompts, and known limitations.
- [ ] Rehearse explaining the architecture and key tradeoffs in my own words.
- [ ] Send the submission.

## Defer until after submission

- Richer visual design, arbitrary slide structures, and a general presentation editor.
- Stored generation briefs, undo, and deck version management.
- Broad public-launch scaling and hardening beyond the agreed evaluation needs.
