# MCP Slides

A deployed MCP connector for Vibe that creates and edits Google Slides in each
user's own Google Drive. Mistral generates the content and cover image; users
receive a real presentation link they can open and edit.

**Connector URL:** https://mistral-slides-mcp-production.up.railway.app/mcp

## Try it

1. Add the URL as a custom MCP connector in Vibe, without a shared Authorization header.
2. Connect, review the MCP Slides consent page, and choose an approved Google account.
3. Ask: “Make me three slides about AI agents for sales teams.”
4. Open the returned link, then ask for a text revision, another slide, or a style change.

The pilot admits the configured company domain and invited personal accounts.
See the [user guide](docs/user-guide.md) for access details and example prompts.

## What it does

Eight tools cover presentation generation, reading, text revision, slide insertion,
deck styling, and reading/saving/resetting style defaults. Content supports key
messages, bullets, comparisons, and steps, with a generated cover image.

Editing is deliberately bounded: it preserves the existing deck and supported
structure. It is not a general-purpose slide editor. Exact contracts and limits
are in [capabilities](docs/capabilities.md).

## Repository

```text
src/mcp_slides/         Maintained application
tests/                Automated tests
scripts/investigation/ Historical runnable experiments and legacy server
docs/                 User guide, auth, capabilities, assignment and checklist
docs/history/         Investigation and implementation history
```

The application is a single Python package. `server.py` exposes the tools;
`oauth.py` and `auth.py` handle identity and credentials; the presentation modules
handle generation, layout, reading, editing and styling. `pages.py` serves the
public and connection pages. `usage.py` bounds paid provider calls.

Investigation tools are preserved for learning and reproducibility, outside the
installed package. They are not used by Railway. See their
[README](scripts/investigation/README.md) before running them.

## Local setup

Requires Python 3.12+ and `uv`.

```sh
uv sync --locked
cp .env.example .env
# Fill in .env with your own configuration.
uv run --env-file .env mcp-slides
```

For local OAuth, set `PUBLIC_BASE_URL=http://localhost:8000`,
`TOKEN_DB_PATH=.secrets/tokens.sqlite3`, and `OAUTHLIB_INSECURE_TRANSPORT=1` in your
local environment. Authorize `http://localhost:8000/auth/google/callback` in the
Google web client. Never enable insecure transport on Railway.

Connect an OAuth-capable MCP client to `http://localhost:8000/mcp`. Opening the
Google callback or connection-start URL directly does not initiate a valid flow.

## Deployment and authentication

Railway uses [railway.json](railway.json) and the unchanged command
`uv run mcp-slides`. Keep one worker/replica and the persistent `/data` volume;
set `TOKEN_DB_PATH=/data/tokens.sqlite3`. Configure variables from
[.env.example](.env.example) in Railway—pushing that file does not apply them.
`/health` is the deployment health check; `/` and `/privacy` are public pages.

Google credentials stay on the server. Vibe receives separate connector tokens,
with each connection isolated. Authentication is frozen for the pilot; see
[the auth reference](docs/auth.md) for the complete flow, Google Console setup,
access rules, token lifecycle, storage tradeoffs, and troubleshooting.

## Pilot usage controls

All users consume the operator's Mistral API key. The defaults allow **100 paid
provider-call attempts over the database's lifetime** and **two concurrent calls**.
Generation, cover images, edits, and insertions share this allowance. Failed calls
and explicit validation retries count; SDK retries are disabled. Reads and styling
consume no model allowance. This bounds operations, not exact monetary spending.

- `PILOT_MAX_PAID_CALLS`: lifetime ceiling; raise it to grant more usage.
- `PILOT_MAX_CONCURRENT_CALLS`: concurrent paid calls within the single process.
- `PILOT_PAID_CALLS_ENABLED=false`: pause new paid calls after redeployment.

Preserve the database across restarts. Calls already in progress may finish.
To inspect consumption in the service environment:

```sh
uv run python - <<'PY'
from contextlib import closing
from mcp_slides.auth import connect

with closing(connect()) as db:
    print(db.execute("SELECT calls FROM pilot_usage WHERE id=1").fetchone()[0])
PY
```

## Tests and release checks

```sh
uv run python -m unittest discover -s tests -v
```

Tests mock Google and Mistral; the protocol test opens a temporary localhost port.
They cover tool behavior, OAuth, account isolation, usage limits, and presentation
preservation. Live Vibe/Google acceptance is tracked separately in the
[submission checklist](docs/submission-checklist.md).

## Documentation

- [User guide](docs/user-guide.md)
- [Authentication](docs/auth.md)
- [Capabilities](docs/capabilities.md)
- [Original assignment](docs/assignment.md)
- [Submission checklist](docs/submission-checklist.md)
- [Investigation history](docs/history/investigation.md)
- [Implementation history](docs/history/implementation-notes.md)
