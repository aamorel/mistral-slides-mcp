# Plan: Google authorization without a tester list

Status: deferred. No Google Console or Railway changes made.

## Goal

A new user can connect the MCP in Vibe, choose their Google account, and create slides in their own Drive without us first adding their email as a Google OAuth tester.

## Minimum rollout

- [ ] Confirm that Google Auth Platform's Data Access configuration matches the code: only `https://www.googleapis.com/auth/drive.file` for Google access.
- [ ] Review the current Audience, Branding, and Verification Center settings for any outstanding requirements.
- [ ] Switch the external OAuth app from **Testing** to **In production** using **Publish app**.
- [ ] Connect from Vibe with a Google account that has never been on the tester list. Confirm account selection and consent work, the deck belongs to that account, and the returned link opens it.
- [ ] Confirm reconnecting and refreshing credentials work. Existing testing grants may need reconnection; do not assume publishing extends their lifetime.
- [ ] Remove the tester-email requirement from `USER-README.md` once the flow is verified, and describe any actual remaining Google prompts.

Expected infrastructure impact: reuse the current Railway service, persistent volume, Google web OAuth client, and callback URL. No authentication rewrite is expected just to publish the app. Publishing Google OAuth does not automatically distribute the connector in Vibe.

## Publishing versus verification

Publishing removes the tester allowlist requirement. Google account and Workspace administrator restrictions can still apply. New production grants are no longer subject to the special seven-day testing expiry, although credentials can still expire or be revoked.

Our current `drive.file` scope is non-sensitive. It does not require sensitive/restricted-scope verification or the security assessment associated with restricted scopes. Reassess this if we add broader permissions.

Brand verification is separate. For a verified app name/logo, plan a public homepage, privacy policy describing actual data handling, support contact, and domain ownership verification. Check whether the current Railway hostname can meet Google's domain requirements; if a custom domain is needed, update the base URL and Google callback configuration accordingly. Review timing depends on Google's checks.

## Before sharing widely

- [ ] Add per-user usage limits and a spending cap strategy: all users currently consume our Mistral API key.
- [ ] Complete branding work and review credential storage and account disconnection/deletion before a broader public launch.

These are separate readiness tasks, not prerequisites imposed by the `drive.file` scope for removing the tester list.

## References

Investigated on 2026-09-08; recheck requirements before rollout.

- [Google: audience and publishing status](https://support.google.com/cloud/answer/15549945?hl=en)
- [Google: Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)
- [Google: brand verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification)
