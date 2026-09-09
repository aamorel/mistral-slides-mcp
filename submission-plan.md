# Before submission

Goal: deliver a working deployed connector, a clear repository, and an
implementation I can explain and maintain confidently.

Feature-freeze candidate: generate from topic or source content using key messages,
flexible bullets, comparisons, and steps; read decks; revise supported text; insert
content slides; style an existing deck; save defaults for future decks; and
automatically generate an image cover. The [current scope](src/mcp_slides/mvp/SCOPE.md)
defines the contract; [scope.md](scope.md) remains the original assignment.
After acceptance testing these flows, freeze new features and focus on correctness,
visual fit, deployment, OAuth publishing, repository cleanup, and code ownership.
Adding/removing items and converting existing layouts remain deferred.

Documentation synchronized on 2026-09-09. Local automated validation: 77 tests
passed. Unchecked live, publishing and ownership tasks below remain pending.

Auth and the connection UI are frozen for the pilot; [AUTH.md](AUTH.md) is the
implementation reference. Configuration, acceptance, and removal of the friend
exception remain release tasks.

## 1. Understand and own the code

- [ ] Trace generation: `server.py` → `outline.py` → `layouts.py` / `slides.py`.
  Explain inputs, Mistral instructions, validation, Google writes, and partial failures.
- [ ] Trace reading and editing: `server.py` → `editing.py`.
  Explain element IDs, supported text, paragraph preservation, revision checks,
  and why reading is both an exposed tool and an internal editing step.
- [ ] Trace insertion: `server.py` → `insertion.py` → `slides.py`. Explain
  style inheritance, insertion position, revision checks and duplicate prevention.
- [ ] Trace styling: `server.py` → `styling.py` / `preferences.py`. Explain this
  deck versus future defaults, partial updates, contrast checks and skipped slides.
- [ ] Trace authentication: `server.py` → `oauth.py` → `auth.py`.
  Explain the Vibe-to-server and server-to-Google OAuth relationships, per-user
  credential mapping, refresh, revocation, and the responsibilities of the MCP SDK.
- [ ] Read a success test and a failure test for each flow.
- [ ] Make a small useful change myself and predict its effects on the tests.
- [ ] Explain the main tradeoffs without relying on the code: narrow editing
  support, model instructions versus guaranteed validation, no stored source
  briefs, plaintext Google credentials in SQLite, and one service instance.

## 2. Clean up the repository

- [ ] Keep the main README focused on capabilities, trying the connector, local
  setup, architecture, deployment, and known limitations.
- [ ] Reconcile historical validation notes with what has actually been tested;
  distinguish user-confirmed results from checks still pending.
- [x] Update `USER-README.md` with a short generation-and-editing example and the
  actual supported editing boundaries.
- [x] Update the package description in `pyproject.toml` and use `README.md` as
  the package README. Preserve `scope.md` as the original assignment.
- [x] Include `editing.py` in the README's application module list.
- [ ] Move investigation and migration history into `docs/` where it improves
  navigation; update links. Clearly label any retained investigation scripts.
- [ ] Review tracked files and Git history for accidentally committed secrets
  or credentials. If found, revoke/rotate them and address repository exposure.
- [ ] Avoid unnecessary package renames or authentication refactors before submission.

## 3. Verify reproducibility and operation

- [ ] Install from a fresh checkout with `uv sync --locked` and run the documented tests.
- [ ] Add a small CI workflow that installs from the lockfile and runs the test suite.
- [ ] Confirm the setup instructions cover required environment variables,
  Google API/redirect configuration, Railway start command, and persistent volume.
- [ ] Document the single-instance SQLite assumption and basic failure diagnosis.
- [ ] Decide and document how Mistral spending is bounded during evaluation,
  including how to disable access if needed. All users consume the operator's key.
- [ ] Review and document credential storage and disconnection behavior. Keep
  broader public-launch hardening separate from the limited submission scope.

## 4. Publish Google OAuth and verify onboarding

Follow [the OAuth publishing plan](oauth-publishing-plan.md) for detailed steps.

- [ ] Implement and deploy the client-domain gate, owner exception, temporary
  friend exception, and global usage controls before publishing.
- [ ] Confirm Google scopes match the planned code: `openid`, `email`, and
  `drive.file`; validate Google identity claims on the server.
- [ ] Review Audience, Branding, and Verification Center requirements, then
  publish the external OAuth app when ready.
- [ ] Connect through Vibe with an allowed client account that was never a test
  user; confirm unrelated accounts are denied.
- [ ] Verify that the created deck belongs to that account and its returned link opens.
- [ ] Verify reconnecting and credential refresh; reconnect older testing grants
  where necessary.
- [ ] Update user-facing tester instructions only after the new onboarding flow
  is confirmed. Describe any remaining prompts accurately.

- [ ] Remove the friend's exception and revoke existing access before submission;
  verify owner and client retain access. Owner email confirmed as
  `aurelien.morel.arthur@gmail.com`.

Publishing with server-enforced client-only access is the preferred handoff. If
blocked, arrange reviewer test accounts and document the limitation; do not
present onboarding as unrestricted.

## 5. Run the final deployed acceptance pass

Refresh Vibe's connector tool definitions after deployment. Automated tests mock
Google and Mistral; these checks exercise the real providers and conversation.

- [ ] Generate from a topic and open the exact returned link in the correct Drive.
- [ ] Ask “Create a presentation about phones” with no other details. Confirm
  immediate generation of three content slides plus one image cover using saved defaults without a create/edit menu or
  questions about optional inputs. Separately verify an explicit planning request
  stays in conversation until creation is requested.
- [ ] Save a default style, generate a deck, and verify it
  is applied. Verify partial changes preserve other settings, reset works,
  and a second connection cannot read or change the first connection’s preference.
- [ ] Verify the automatic image cover, editable title, extra-slide count, and
  temporary image fetch from the deployed server.
- [ ] Generate from supplied content and check that facts and uncertainty are preserved.
- [ ] Confirm the post-generation chat invitation offers relevant wording edits.
- [ ] Generate with built-in defaults and customized colors/font. Check visual fit,
  contrast, bullets, and wording revisions in each. Confirm style discovery is brief and
  distinguishes styling this deck from saving defaults for future decks.
- [ ] Generate all four content types in topic and content mode. Check short and
  maximum-length content, 1 and 5 bullets, asymmetric comparisons, and numbered
  steps in each supported font. Inspect overflow, column spacing and readability.
- [ ] Revise a comparison column and a numbered step; verify neighboring text,
  paragraph counts and numbering remain intact. Apply defaults to all four types.
- [ ] Confirm unsupported requests to add/remove items or convert layouts are
  acknowledged without silently rewriting or creating a replacement deck.
- [ ] Change only a deck's title color, then only its font. Verify unspecified
  formatting and saved defaults are preserved, including slides with different
  existing colors. Check low-contrast and unreadable-color skips.
- [ ] Pass a Google Slides URL directly when reading or styling a deck.
- [ ] Apply saved defaults to an existing deck. Verify the same URL, updated
  colors/font and cover band, unchanged text/layout/image, and skipped-slide
  reporting. Check revision conflicts and readback of actual formatting.
- [ ] Insert after slide two and append a conclusion. Verify slide order, the
  same URL, unchanged existing slides, inherited style and explicit fallback warnings.
  Revise the inserted slide; check that an uncertain insertion is read before retrying.
- [ ] Chain supported mutations using returned revisions when context is sufficient;
  confirm stale revisions still reject writes and missing revisions require a read.
- [ ] Revise one slide; verify the same deck URL and unchanged surrounding slides.
- [ ] Check that fonts, bullets, positions, and unsupported elements survive the edit.
- [ ] Manually edit text in Google Slides, then revise it through Vibe; verify the
  tool uses the current wording. Include an emoji to exercise Unicode handling.
- [ ] Request an unsupported operation, such as adding an image or reordering
  slides; verify a clear explanation and no unintended changes.
- [ ] Submit an edit with a stale revision; verify rejection and preservation of
  the intervening manual change.
- [ ] Try an inaccessible deck from another account; verify access is denied.
- [ ] Redeploy/restart the service and verify the connection survives through the
  persistent volume.
- [ ] Record the tested commit, date, results, and any remaining limitations.

## 6. Prepare and send the submission

- [ ] Confirm the final commit is pushed, deployed, and matches the tested version.
- [ ] Confirm reviewers can access the GitHub repository and deployed MCP URL.
- [ ] Prepare a short demo: connect → generate → revise → explain one limitation.
- [ ] Optionally record the demo as a fallback and quick overview.
- [ ] Prepare a concise handoff containing the repository link, deployed MCP URL,
  connection instructions, example prompts, and known limitations.
- [ ] Rehearse explaining the architecture and key tradeoffs in my own words.
- [ ] Send the submission.

## Defer until after submission

- Richer visual design, arbitrary slide structures, and a general presentation editor.
- Stored generation briefs, undo, and deck version management.
- Broad public-launch scaling and hardening beyond the agreed evaluation needs.
