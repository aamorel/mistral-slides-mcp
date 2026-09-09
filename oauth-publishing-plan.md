# Plan: client-only OAuth pilot

Status: access policy and usage controls implemented locally; deployment and
live acceptance pending. No Google Console or Railway changes were made. Follow
[the Google Console rollout checklist](google-oauth-rollout.md) for the handoff.

## Goal and scope

Client reviewers connect in Vibe with their company Google account and create
slides in their own Drive without sending individual tester emails. Publish the
external Google OAuth app and restrict connector access on our server. Reuse the
existing Railway service, SQLite volume, Google OAuth client, and callback URL.
Presentation features remain as described in [the current MVP scope](src/mcp_slides/mvp/SCOPE.md).

| Audience | Admission rule | Duration |
| --- | --- | --- |
| Client | Validated Google identity with hosted-domain claim `hd` exactly `mistral.ai` | Pilot and submission |
| Owner | Exact verified email `aurelien.morel.arthur@gmail.com` | Pilot and submission |
| Friend | Exact verified email `vmaxmc2@gmail.com` | Testing only; remove before submission |
| Everyone else | Denied connector access | Always |

Owner confirmed `aurelien.morel.arthur@gmail.com`. The two personal exceptions
are provided in `.env.example`; set them explicitly in Railway.

Confirm that client accounts actually carry `hd=mistral.ai`. Google Testing has
no domain wildcard; Google Internal access would require the project to belong
to the client's Google organization.

## Minimum implementation

- Add `openid` and `email` alongside `drive.file`; no broader Drive permission.
- Validate Google's ID token with a supported library: signature, issuer,
  audience, expiry, and nonce bound to the authorization attempt. Preserve the
  existing state, browser binding, and PKCE checks.
- Allow an exact verified `hd` match OR an exact verified personal email
  exception. An email suffix or account-picker domain hint is not domain proof.
- Check admission before storing Google credentials or issuing connector access.
  Denied accounts receive a clear client-only message and trigger no model calls.
- Persist Google's stable `sub` and minimal verified policy claims alongside each
  connection. Preserve connection isolation and existing preferences.
- Recheck current admission policy on authenticated tool access and token renewal,
  so removed exceptions cannot continue with old tokens. Connections without
  verified identity data must reconnect.
- Configure domain and personal exceptions through deployment settings, not
  hardcoded email addresses. Provide an operator switch to disable paid operations.
- Add a persistent global paid-operation allowance and a small concurrency limit.
  Include outline, cover-image, and all other paid model calls, failures and
  retries. Reserve allowance atomically before calling providers; preserve it
  across restarts. Choose values against available credits and configured models.
  A request allowance is not an exact currency cap; document that limitation and
  use a provider hard cap if available.

Defer per-user quotas, billing, admin dashboards, account-merging changes, and
broader public-launch work. This is a bounded client evaluation.

## Steps to reach it

### 1. Confirm configuration

- [x] Confirm the owner's exact email.
- [ ] Confirm the client's Google Workspace domain with a live account.
- [x] Implement configurable defaults: 100 lifetime paid API calls and two
  concurrent calls. These are operation limits, not a currency cap.
- [ ] Review available credits and model costs before enabling paid use.
- [x] Document deployment settings and the operator disable switch.

### 2. Implement and test locally

- [x] Add verified identity handling, configurable admission policy, and minimal
  identity persistence without changing presentation behavior.
- [x] Add persistent usage enforcement and concurrency control.
- [x] Test allowed domain, both personal exceptions, unrelated accounts, missing
  or mismatched `hd`, unverified exception emails, and invalid ID tokens.
- [x] Test that denial creates no usable connection and triggers no model spend.
- [x] Test removal of an exception against existing access/refresh tokens and new
  login; verify legacy connections must reconnect.
- [x] Test allowance exhaustion, concurrent requests, restart persistence, and
  release of concurrency slots after failure.

### 3. Deploy the gate, then publish OAuth

- [ ] Deploy access and usage controls while Google remains in Testing. Owner
  and friend still need individual Google tester entries at this stage.
- [ ] Verify both personal accounts end to end in Vibe.
- [ ] Match Google Data Access configuration to `openid`, `email`, and `drive.file`.
- [ ] Review Audience, Branding, and Verification Center requirements, then
  switch the external app to **In production**.
- [ ] Verify a client account that was never a tester can connect, generate a deck
  in its own Drive, and open the returned link. Workspace admin restrictions may
  still require client action.
- [ ] Verify an unrelated account is denied by our server after Google sign-in.
- [ ] Verify reconnect and refresh. Older testing grants may require reconnecting;
  publishing does not retroactively guarantee their lifetime.

### 4. Close the pilot for submission

- [ ] Remove `vmaxmc2@gmail.com` from deployed personal exceptions and revoke its
  existing connector sessions and stored Google credentials. Removing it only
  from Google's tester list is insufficient after publication.
- [ ] Verify the friend is denied on old connections and new login, while owner
  and client remain allowed. Previously created Drive decks remain theirs.
- [ ] Update `USER-README.md` to say “Client-only pilot: connect with your company
  Google account,” describe actual consent prompts, and remove tester-email
  instructions only after the production flow is verified.
- [ ] Record deployed version, acceptance results, budget settings, and shutdown
  procedure. Share the repository and MCP URL with the client.

If publication or Workspace access is blocked, explicitly arrange individual
reviewer test accounts as a fallback and document seven-day testing expiry.

## Publishing and verification

Publishing removes Google's tester gate; our server still enforces client-only
access. It does not automatically list the connector in Vibe. The planned scopes
do not introduce sensitive/restricted Drive access. Brand verification remains
separate: inspect Google's requirements for homepage, privacy policy, support
contact, and domain ownership before claiming a verified name/logo.

## References

Audience and identity rules checked on 2026-09-09; review Console state at rollout.

- [Google: audience and publishing status](https://support.google.com/cloud/answer/15549945?hl=en)
- [Google: OpenID Connect and hosted-domain validation](https://developers.google.com/identity/openid-connect/openid-connect)
- [Google: Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)
- [Google: brand verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/brand-verification)
