# MCP Slides

Create and edit Google Slides through chat in Vibe. Mistral generates the content
and cover image; presentations are saved in your connected Google Drive.

## Connect and use

**Connector URL:** [https://mistral-slides-mcp-production.up.railway.app/mcp](https://mistral-slides-mcp-production.up.railway.app/mcp)

1. In Vibe, add a **Custom MCP Connector** named **Mistral Slides** using the URL above.
2. Leave authentication on **Auto-detect**. No API key or custom authorization header is needed.
3. Connect, choose your approved Google account, and grant access.
4. Enable the connector in a chat and ask: “Create a 3-slide presentation about a weekend in Paris.”
5. Open the returned Google Slides link.

Access is limited to approved company Google accounts and invited personal
accounts. If your account is denied, contact the operator for access.

Continue in the same chat:

- “Make slide 2 less technical.”
- “Add a slide about costs after slide 2.”
- “Make this deck's titles dark blue and use Georgia.”
- Attach an image and ask: “Add this image to slide 2.”
- “Use cream backgrounds and Georgia by default for future presentations.”

Generation supports 1–6 total slides, including an image cover. Content layouts
include key messages, bullets, comparisons, and numbered steps. Edits preserve
the same presentation link. Your own images can be added or explicitly replaced
on short key-message and bullet slides, with one image per slide.

This is a focused connector: arbitrary templates, slide removal/reordering, and
converting existing layouts are unsupported. See the [user guide](docs/user-guide.md)
for more examples and [capabilities](docs/capabilities.md) for precise limits.

## Set up your own instance

You need Python 3.12+, `uv`, a Mistral API key with access to the configured text
and image-generation models, and a Google Cloud project with a web OAuth client.

### 1. Install

```sh
git clone https://github.com/aamorel/mistral-slides-mcp.git
cd mistral-slides-mcp
uv sync --locked
cp .env.example .env
```

### 2. Configure Google and the server

Enable the Google Slides API in your Google Cloud project. Configure the OAuth
consent screen and create an OAuth client of type **Web application** with these
scopes:

- `https://www.googleapis.com/auth/drive.file`
- `openid`
- `https://www.googleapis.com/auth/userinfo.email`

Choose a public HTTPS origin for your server. For local development, forward a
public HTTPS tunnel to port `8000`. Google must reach the server's temporary image
URLs to insert generated covers and attachments; localhost alone does not support
that full flow.

Fill in `.env` with your own values:

```dotenv
GOOGLE_CLIENT_ID=your-google-web-client-id
GOOGLE_CLIENT_SECRET=your-google-web-client-secret
MISTRAL_API_KEY=your-mistral-api-key
PUBLIC_BASE_URL=https://your-public-host
TOKEN_DB_PATH=.secrets/tokens.sqlite3
GOOGLE_ALLOWED_DOMAIN=
GOOGLE_ALLOWED_EMAILS=you@example.com
```

`PUBLIC_BASE_URL` is the origin, without `/mcp`. Register
`https://your-public-host/auth/google/callback` as an authorized redirect URI in
your Google OAuth client. If the tunnel address changes, update both values.

Admission requires either a verified Google Workspace domain matching
`GOOGLE_ALLOWED_DOMAIN` or a verified email listed in `GOOGLE_ALLOWED_EMAILS`.
Replace the sample allowlists with your own; leaving both empty denies everyone.
If your Google OAuth app is in Testing, also add your account as a Google test user.
See [authentication setup](docs/auth.md#deployment-configuration) for consent-screen,
publishing, and troubleshooting details; substitute your own origin for the hosted
service's URLs.

### 3. Run and connect

```sh
uv run --env-file .env mcp-slides
```

The server listens on port `8000` by default (`PORT` overrides it). Check
`https://your-public-host/health`, then add `https://your-public-host/mcp` to Vibe
and follow the connection steps above. Start authentication from the MCP client;
opening the Google callback directly does not start a valid connection.

### 4. Run tests

```sh
uv run python -m unittest discover -s tests -v
```

Tests mock Google and Mistral and cover tool behavior, OAuth, account isolation,
usage limits, and safe presentation updates. The protocol test uses a temporary
localhost port. [CI](.github/workflows/tests.yml) runs the same suite. To check your
own provider configuration, connect, create a deck, open its link, and revise a slide.

## Deploy on Railway

1. Deploy the repository using [railway.json](railway.json), which starts
   `uv run mcp-slides` and checks `/health`.
2. Attach a persistent volume at `/data` and set `TOKEN_DB_PATH=/data/tokens.sqlite3`.
3. Set the variables from [.env.example](.env.example) in Railway using your own
   credentials and allowlists. Set `PUBLIC_BASE_URL` to your service's HTTPS origin.
4. Register that origin's `/auth/google/callback` URL in your Google OAuth client
   and configure the homepage (`/`) and privacy-policy (`/privacy`) URLs.
5. Keep one process/replica. Deploy, then connect to your service's `/mcp` URL.

Pushing `.env.example` does not change Railway variables. Preserve the database
across deployments and restart after changing access rules to purge excluded
accounts' connections.

## Pilot usage controls

All users share the operator's Mistral API key. Defaults allow **100 paid provider
call attempts over the database's lifetime** and **two concurrent paid calls**.
These count calls, not presentations or currency; failures and validation retries
count too. Reads, styling, and attachment placement do not use this allowance.

- `PILOT_MAX_PAID_CALLS`: raise the lifetime ceiling to grant more usage.
- `PILOT_MAX_CONCURRENT_CALLS`: limit concurrent paid calls.
- `PILOT_PAID_CALLS_ENABLED=false`: pause new paid calls after restart/redeployment.

## How it works

`server.py` exposes nine MCP tools. `presentation_service.py` coordinates creation:
Mistral produces validated content and a cover, then fixed layouts become Google
Slides API requests. Existing-deck operations read the current revision before
writing to avoid overwriting concurrent changes.

See [architecture](docs/architecture.md) for the component diagram, workflows,
storage model, and design tradeoffs.

Google credentials belong to each connection; there is no shared Drive account.
They are stored **unencrypted in the private SQLite volume**, so protect access
and backups. Source text goes to Mistral. Attached images are temporarily served
for Google to fetch and are not sent to Mistral. Disconnecting does not delete
presentations or revoke Google consent upstream.

If a write times out, check the returned presentation link or Google Drive before
retrying: the operation may have completed. Google writes are not automatically
replayed, and deck creation has no cross-request duplicate prevention.

## Further documentation

- [User guide](docs/user-guide.md)
- [Capabilities and limitations](docs/capabilities.md)
- [Authentication, storage, and troubleshooting](docs/auth.md)
- [Image placement behavior and limits](docs/image-editing-ux.md)
- [Original assignment](docs/assignment.md)

Application code lives in `src/mcp_slides/`, with tests in `tests/`. Release tasks
are tracked in [the submission checklist](docs/submission-checklist.md).
Development history and experiments live in `docs/history/` and
`scripts/investigation/`; they are not required to run the connector.
