# Before submission

Goal: deliver a working deployed connector, a clear repository, and an
implementation I can explain and maintain confidently.

Keep the current feature scope: generate from a topic or source content, read a
deck, choose a built-in style for new decks, and revise supported text on one slide. Focus on finishing and validating
these flows rather than adding features.

## 1. Understand and own the code

- [ ] Trace generation: `server.py` → `outline.py` → `slides.py`.
  Explain inputs, Mistral instructions, validation, Google writes, and partial failures.
- [ ] Trace reading and editing: `server.py` → `editing.py`.
  Explain element IDs, supported text, paragraph preservation, revision checks,
  and why reading is both an exposed tool and an internal editing step.
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
- [ ] Update `USER-README.md` with a short generation-and-editing example and the
  actual supported editing boundaries.
- [ ] Update the package description in `pyproject.toml` and use `README.md` as
  the package README. Preserve `scope.md` as the original assignment.
- [ ] Include `editing.py` in the README's application module list.
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

- [ ] Confirm the configured Google scope matches the code: only `drive.file`.
- [ ] Review Audience, Branding, and Verification Center requirements, then
  publish the external OAuth app when ready.
- [ ] Connect through Vibe with a Google account that was never a test user.
- [ ] Verify that the created deck belongs to that account and its returned link opens.
- [ ] Verify reconnecting and credential refresh; reconnect older testing grants
  where necessary.
- [ ] Update user-facing tester instructions only after the new onboarding flow
  is confirmed. Describe any remaining prompts accurately.

Publishing is the preferred handoff. If it is blocked, explicitly arrange reviewer
test accounts and document that limitation; do not present onboarding as unrestricted.

## 5. Run the final deployed acceptance pass

Refresh Vibe's connector tool definitions after deployment. Automated tests mock
Google and Mistral; these checks exercise the real providers and conversation.

- [ ] Generate from a topic and open the exact returned link in the correct Drive.
- [ ] Ask “Create a presentation about phones” with no other details. Confirm
  immediate generation of three content slides plus one image cover using saved defaults without a create/edit menu or
  questions about optional inputs. Separately verify an explicit planning request
  stays in conversation until creation is requested.
- [ ] Save a custom style, generate without specifying a preset, and verify it
  is applied. Verify explicit presets override it only for one deck, reset works,
  and a second connection cannot read or change the first connection’s preference.
- [ ] Verify the automatic image cover, editable title, extra-slide count, and
  temporary image fetch from the deployed server.
- [ ] Generate from supplied content and check that facts and uncertainty are preserved.
- [ ] Confirm the post-generation chat invitation offers relevant wording edits.
- [ ] Generate with Minimal (default), Dark, and Warm. Check visual fit, contrast,
  bullets, and wording revisions in each. Confirm style discovery is brief and
  does not imply that existing decks can be restyled.
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
