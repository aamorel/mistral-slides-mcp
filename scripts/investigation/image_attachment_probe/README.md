# Disposable Vibe attachment probe

Experiment completed: [live results, 2026-09-09](RESULTS.md). A freshly uploaded
PNG reached the probe with identical decoded RGB pixels; original PNG bytes
differed. This verifies the tested path, not a documented attachment API contract.

One standalone MCP tool tests whether Vibe can pass an uploaded image reference
to our server. It neither imports nor changes the Slides application. See
[DESIGN.md](DESIGN.md) for the experiment and evidence criteria.

Everything needed is in this directory, using dependencies already in the root
lockfile (MCP, Uvicorn, h11 and Pillow). Tests are run separately from the main
application suite. Commands below run from the repository root after
`uv sync --locked`.

## Prepare and run

### Local laptop + temporary tunnel (preferred for this experiment)

The local helper stores its token, fixture and tunnel binary under the ignored
`.secrets/image-attachment-probe/` directory. No background service is installed.
The token is reused across restarts and readable only by its owner.

```sh
uv run python -m scripts.investigation.image_attachment_probe.local prepare
uv run python -m scripts.investigation.image_attachment_probe.local serve
```

Leave that terminal running. In a second terminal, validate locally:

```sh
uv run python -m scripts.investigation.image_attachment_probe.local check
```

When ready for Vibe, open the tunnel in the second terminal:

```sh
uv run python -m scripts.investigation.image_attachment_probe.local tunnel
```

Copy the printed `https://…trycloudflare.com` URL and append `/mcp` for the
connector URL. The URL changes when the tunnel is restarted. In another terminal:

```sh
uv run python -m scripts.investigation.image_attachment_probe.local copy-token
```

Paste the copied value into Vibe's bearer-token authentication field. Attach
`.secrets/image-attachment-probe/attachment-probe.png` in a new conversation and
use the prompt below. Do not attach the token or `expected.json`.

For phase two, stop only the server with Ctrl-C and restart it with:

```sh
uv run python -m scripts.investigation.image_attachment_probe.local serve --allowed-host ACTUAL_STORAGE_HOST
```

Keep the tunnel running to preserve its URL. Stop both terminals with Ctrl-C
after testing. Leaving only the local server running does not publish it.

The tunnel helper checks the MCP endpoint before starting and rewrites the
upstream Host header to localhost, preserving the SDK's host validation.
[Cloudflare Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/)
provide temporary public HTTPS without an account. They do not support SSE;
this probe uses stateless JSON responses. Actual Vibe compatibility still needs
the live check. Requests pass through Cloudflare; use only the disposable fixture.

Local setup installed the official Apple Silicon `cloudflared` 2026.9.0 binary
under `.secrets/image-attachment-probe/bin/`, after verifying the archive SHA-256
against GitHub release metadata. On another machine, obtain the matching binary
from [Cloudflare's official releases](https://github.com/cloudflare/cloudflared/releases),
verify its checksum and place it at that location. It is not committed to Git.

### Manual setup or separate deployment

Create a harmless fixture and its local expected hashes (do not attach the JSON):

```sh
uv run python -m scripts.investigation.image_attachment_probe.fixture .secrets/image-attachment-probe
```

The generator refuses to overwrite an existing fixture. Keep the generated PNG
and `expected.json` together for the test. `.secrets/` is already gitignored.

Generate a dedicated secret locally, keep it private, and configure the same
value in Vibe's connector authentication settings:

```sh
export PROBE_BEARER_TOKEN="$(uv run python -c 'import secrets; print(secrets.token_urlsafe(32))')"
HOST=127.0.0.1 PORT=8002 uv run python -m scripts.investigation.image_attachment_probe.server
```

Use a separate temporary HTTPS service for Vibe. Install with `uv sync --locked`,
set `HOST=0.0.0.0`, `PORT` to the platform's port, and `PROBE_BEARER_TOKEN` in that
service's private environment. Start command:

```sh
uv run python -m scripts.investigation.image_attachment_probe.server
```

Health endpoint: `/health`. Connector endpoint: `https://<probe-host>/mcp`.
Authentication: static bearer token, entered in Vibe's authentication UI, never
in the chat prompt. No Google authorization or Mistral API key is needed.
Do not change the production Railway service's start command or environment.

Leave `PROBE_ALLOWED_HOST` unset for the first invocation. Start a fresh Vibe
Work conversation with only this connector enabled, attach the PNG, and send:

> Use inspect_attached_image to inspect this attached image. Pass the actual
> image URL or file reference available to you. If none is available, call the
> tool with null. Do not describe or recreate the image.

The result classifies the reference without making an outbound request. If it
reports an appropriate HTTPS storage hostname, configure that exact hostname in
`PROBE_ALLOWED_HOST` and restart the probe service. No wildcards or URL paths.
Only then repeat the tool request for the same attachment. Expired references
may require attaching the fixture again.

Compare `sha256_bytes` and `sha256_rgb` from the tool result against
`.secrets/image-attachment-probe/expected.json`. Matching byte hashes prove exact
transfer; matching pixel hashes prove identical decoded RGB content. Dimensions
alone do not prove that the intended image was received.

## Limits and evidence

- Reference length: 16,384 characters; MCP request body: 32 KiB.
- Downloads: HTTPS/443, exact allowed host, public IP addresses only, validated
  numeric connection address with original TLS hostname verification.
- No redirects, proxies, cookies, API keys, or compressed HTTP response bodies.
- 15 seconds for DNS/TLS/HTTP retrieval, 2 MiB streamed body, two million pixels.
- PNG/JPEG/WebP, single frame only. Decoding occurs after retrieval and is not
  part of the 15-second network deadline.
- The process suppresses all application/SDK logs. Evidence comes from tool
  results; errors contain safe statuses, never raw upstream exception messages.
- Vibe itself can retain tool arguments in its conversation. Only use the
  disposable non-sensitive fixture. The server stores no reference or image.

A blocked host, redirect, null input, or failed download is an inconclusive
result with a specific obstacle, not proof that all attachment transfer is
unsupported. This probe specifically tests reference forwarding. Do not broaden
the download policy just to make an unknown reference work.

## Test and remove

```sh
uv run python -m unittest discover -s scripts/investigation/image_attachment_probe/tests -v
```

The protocol test opens a localhost port. All outbound image retrieval is mocked;
the tests make no provider calls. No Vibe behavior is claimed by local tests.

After the live experiment, disable/delete its dedicated service and connector,
discard the dedicated secret, and remove this directory plus the generated
`.secrets/image-attachment-probe/` fixture directory if no longer needed. Remove
the single index link from the parent investigation README. No production code,
dependency files or deployment files need reverting.
