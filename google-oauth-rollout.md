# Client-only pilot: deployment and Google Console steps

Local implementation completed on 2026-09-09; all 77 automated tests passed with
Google and Mistral mocked. Google publication, Railway deployment, and live
client-domain acceptance have not been performed in this task.

## 1. Set Railway variables and deploy the access gate

Keep the existing Google client credentials, Mistral key, public base URL, and
persistent `/data` volume. Add these service variables:

```dotenv
GOOGLE_ALLOWED_DOMAIN=mistral.ai
GOOGLE_ALLOWED_EMAILS=aurelien.morel.arthur@gmail.com,vmaxmc2@gmail.com
PILOT_MAX_PAID_CALLS=100
PILOT_MAX_CONCURRENT_CALLS=2
PILOT_PAID_CALLS_ENABLED=true
```

Keep `TOKEN_DB_PATH=/data/tokens.sqlite3` and one worker/replica. The 100-call
allowance is shared across users and persists across restarts. Review the
available Mistral credits before enabling it; it is not an exact monetary cap.

Deploy the tested code before publishing Google OAuth. At startup, legacy grants
without verified identity and connections excluded by the policy are removed,
including their saved preferences and temporary images. Existing Drive decks
are unaffected. Everyone must reconnect once after this upgrade.

Missing allowlist settings deny everyone. The example settings do not apply
until you actually configure the deployment; the server has no hardcoded emails.

## 2. Update the existing Google project

Open [Google Cloud Console](https://console.cloud.google.com/) and select the
project containing the existing OAuth web client.

1. **APIs & Services → Library:** confirm **Google Slides API** is enabled.
2. **Google Auth Platform → Data Access → Add or remove scopes:** retain
   `https://www.googleapis.com/auth/drive.file` and add:
   - `openid`
   - `https://www.googleapis.com/auth/userinfo.email` (the email identity scope)
   Save/update the selection. Do not add full Drive access or `userinfo.profile`.
3. **Google Auth Platform → Clients → existing Web application client:** confirm
   this exact **Authorized redirect URI**, then save if changed:

   ```text
   https://mistral-slides-mcp-production.up.railway.app/auth/google/callback
   ```

   If `PUBLIC_BASE_URL` differs, use that origin plus `/auth/google/callback`.
   Reuse the current client ID/secret; no new client or JavaScript origin is needed
   for this server-side flow.
4. **Google Auth Platform → Audience:** keep **External**. While still in
   **Testing**, add both personal addresses as individual test users:
   `aurelien.morel.arthur@gmail.com` and `vmaxmc2@gmail.com`.
5. **Branding:** after deploying the public pages, enter these URLs:
   - Homepage: `https://mistral-slides-mcp-production.up.railway.app/`
   - Privacy policy: `https://mistral-slides-mcp-production.up.railway.app/privacy`
   Both pages are public and require no Google login. Review the privacy text
   against actual deployment/provider settings before submitting branding.
6. **Branding / Verification Center:** check for outstanding requirements and
   accurate app/support details. Follow any requirements shown for your project.
   Publishing status and brand verification are separate; don't claim a verified
   name/logo until Google confirms it.

The identity permissions let our server check who is connecting. The domain and
personal allowlist belong in Railway, not in Google's “Authorized domains” field;
that branding field does not control which users may use the connector.

Sources: [Google's consent configuration](https://developers.google.com/workspace/guides/configure-oauth-consent),
[Google's OpenID Connect setup](https://developers.google.com/identity/openid-connect/openid-connect).

## 3. Test personally, then publish

1. Reconnect in Vibe with the owner's Google account. Generate a deck and open
   the returned link in that account's Drive. Repeat with the friend.
2. In **Google Auth Platform → Audience → Publishing status**, choose
   **Publish app** and confirm **In production**. This removes Google's individual
   tester gate; our server's client-only admission stays active.
3. Have a client reviewer who was never a Google tester connect with their company
   account. Verify admission, deck ownership, the returned link, reconnect, and
   refresh. This confirms that Google's actual `hd` claim matches `mistral.ai`.
4. Try an unrelated Google account: it must receive the client-only denial and
   must not obtain usable connector access. Google may still show its consent
   screen before our server rejects the account.

Client Workspace administrator restrictions can still block authorization. If
publication is blocked, arrange individual reviewer test accounts as a documented
fallback. Testing grants expire after seven days; older grants may need
reconnection even after publication.

Source: [Google's audience and publishing rules](https://support.google.com/cloud/answer/15549945?hl=en).

## 4. Before submission: remove the friend

Change the Railway variable to:

```dotenv
GOOGLE_ALLOWED_EMAILS=aurelien.morel.arthur@gmail.com
```

Redeploy/restart. Startup deletes excluded connections, stored Google credentials,
connector tokens, preferences, and temporary images. Verify the friend's existing
connection and new login both fail, while the owner and client still work.
Removing the friend only from Google's test-user list does not block production
access. Removing local credentials does not delete the friend's Drive decks or
revoke Google's upstream consent; the friend can separately remove that consent
in their Google Account's third-party connections.

Update `USER-README.md` to remove its Testing instructions after production
acceptance is confirmed. Record the tested commit and actual Google prompts.

## Operation

- Pause new model calls: set `PILOT_PAID_CALLS_ENABLED=false` and redeploy. Existing
  calls may finish; reading and styling remain available to allowed accounts.
- Grant more usage: raise `PILOT_MAX_PAID_CALLS` and redeploy. It is a lifetime
  ceiling, not a daily reset. Do not delete the database to reset usage.
- Inspect consumed calls in the service environment without printing credentials:

  ```sh
  uv run python - <<'PYTHON'
  from contextlib import closing
  from mcp_slides.mvp.auth import connect

  with closing(connect()) as db:
      print(db.execute("SELECT calls FROM pilot_usage WHERE id=1").fetchone()[0])
  PYTHON
  ```

No automatic deployment, Google Console edits, or submission messages are part
of the local implementation verification recorded above.
