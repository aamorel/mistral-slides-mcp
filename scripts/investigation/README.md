# Investigation tools

Completed disposable experiment: [Vibe image attachment probe](image_attachment_probe/README.md).
[Live results](image_attachment_probe/RESULTS.md) confirm transfer of a freshly
uploaded image with identical decoded RGB pixels. Its server, tests, design and
fixture generator are isolated here; none is part of the Slides application.

These experiments helped validate Google Slides, Mistral, and Vibe independently
before the current connector was built. They are retained as historical examples,
not maintained production entry points. Their auth and output contracts differ
from the application in `src/mcp_slides/`.

| Tool | What it established |
| --- | --- |
| `google_slides_smoke.py` | User OAuth with `drive.file` can create a real Slides deck. Uses a local browser callback and a separate token file. |
| `mistral_outline_smoke.py` | Mistral can return and validate a small structured outline. |
| `smoke_ping_client.py` | An MCP client can discover and invoke the legacy server's `ping` tool. |
| `legacy_server/ping_server.py` | Early deployed transport and optional static-bearer authentication experiment. |
| `legacy_server/google_auth.py` | Early separate Google-linking flow used only by that server. |

Run commands **from the repository root**, after `uv sync --locked`.

## Provider experiments

```sh
uv run python scripts/investigation/google_slides_smoke.py --help
uv run python scripts/investigation/mistral_outline_smoke.py --help
```

The Google script needs a suitable OAuth client JSON and opens a local callback
on port 8081 by default; `--credentials`, `--token`, and `--port` select its inputs.
It writes a real deck. Use separate test credentials and a token file under
`.secrets/`, never the deployed token database.

The Mistral script needs `MISTRAL_API_KEY` and makes paid API calls when run beyond
`--help`. These old scripts bypass the current pilot allowance and admission policy.
They are not acceptance tests for the current application.

## Legacy transport experiment

Start the historical server locally with its own port and database:

```sh
HOST=127.0.0.1 PORT=8001 PUBLIC_BASE_URL=http://localhost:8001 \
TOKEN_DB_PATH=.secrets/investigation-tokens.sqlite3 \
uv run python -m scripts.investigation.legacy_server.ping_server
```

Then, in another terminal:

```sh
uv run python scripts/investigation/smoke_ping_client.py http://localhost:8001/mcp
```

If `CONNECTOR_BEARER_TOKEN` is set on the server, pass the same value as
`MCP_BEARER_TOKEN` to the client. The optional legacy Google-linking routes also
need Google client credentials and their matching callback configuration.
Do not point the legacy server at the application's database or deploy it as
the current service. The old `mcp-slides-ping` installed command has been removed;
use the module command above for this experiment.

For historical observations, see [the investigation record](../../docs/history/investigation.md).
For the current setup, see [the repository README](../../README.md).
