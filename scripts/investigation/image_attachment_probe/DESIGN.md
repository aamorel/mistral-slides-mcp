# Vibe image attachment feasibility probe

Status: live attachment transfer verified on 2026-09-09 using the local server
and a temporary HTTPS tunnel. See [RESULTS.md](RESULTS.md) for evidence and limits.

## Question and boundary

Can Vibe Work pass a reference to an image attached in the current conversation
to a remote MCP tool, and can that server retrieve the actual image without
browser cookies or the user's Mistral credentials?

Use a separate temporary connector and deployment, with one tool and a dedicated
bearer secret configured through the connector's authentication settings. Do not
modify the production Slides connector or require Google OAuth. The probe needs
no Google credentials, Mistral API key, SQLite storage, or model calls of its own.

## Tool contract

```python
inspect_attached_image(image_reference: str | None = None)
```

Proposed description:

> Inspect the image attached by the user for this test. Supply its actual
> downloadable URL or exact file reference only if available in your context.
> If no reference is available, call with null. Do not invent a URL, reconstruct
> image bytes, substitute a description, or send cookies, API keys, or session
> credentials. This tool does not create or modify slides.

Allow null so an inability to provide a reference produces a measurable tool
result. Accept up to 16,384 characters; reject larger inputs. Do not accept
base64/data URLs in this first experiment. A host-side binary transfer mechanism,
if discovered later, needs a separate test; this probe cannot disprove it.

## Two stages, using the same tool

First run in classification-only mode. Classify the input as absent, HTTPS URL,
file ID, local/internal reference, or unsupported. For an HTTPS URL return only
its hostname and whether it has query parameters. Never echo the
full URL, path, query values, or raw file ID. Do not fetch anything in this mode.
This discovers the actual reference shape without creating an unrestricted URL
fetcher or guessing a Mistral storage hostname.

Then, if the hostname and reference are suitable, configure the exact permitted
hostname and enable retrieval. Repeat the prompt with the same attachment or a
fresh upload if necessary. Budget two Vibe messages; reference discovery may be
completed beforehand by inspecting an existing attachment, reducing this to one.
The first URL is not retained, so enabling retrieval cannot replay it silently.

Retrieval uses HTTPS on port 443, verifies certificates, rejects userinfo in URLs,
and sends no browser cookies, Google credentials, or Mistral API credentials.
Reject redirects in this first version and return a distinct result. Permit only
the configured exact hostname, reject non-public resolved IP addresses, and bind
the connection to a validated address while preserving hostname/TLS verification
so validation and connection cannot resolve to different destinations. Do not
use ambient proxy configuration. If this cannot be implemented correctly with
the chosen client, keep classification-only mode until it is resolved.

Limit the complete retrieval to 15 seconds and 2 MiB of streamed bytes. Decode
only PNG/JPEG/WebP, with a two-million-pixel limit checked before full decoding.
Treat any network exception as a safe status; never return its raw text.

## Evidence returned

Every invocation returns a server-generated probe ID and a status. Successful
retrieval returns format, dimensions, byte count, SHA-256 of the received bytes,
and SHA-256 of decoded RGB pixels. Expected hashes remain local to the operator;
do not include them in the prompt or tool arguments.

Example result shape (values below are illustrative):

```json
{
  "probe_id": "server-generated-id",
  "status": "image_retrieved",
  "format": "PNG",
  "width": 317,
  "height": 193,
  "byte_count": 12345,
  "sha256_bytes": "computed-by-server",
  "sha256_rgb": "computed-by-server"
}
```

Statuses: `no_reference`, `reference_observed`, `unsupported_reference`,
`host_not_allowed`, `redirect_not_followed`, `retrieval_denied`,
`retrieval_failed`, `limit_exceeded`, `not_supported_image`, `image_retrieved`.
Report HTTP 401/403/404 as evidence of that response, not proof of a particular
cause. An expired or incorrectly selected URL can also fail retrieval.

Keep image bytes in memory for the request only. Disable application logging
entirely for this disposable process. Disable access/provider logs that could
expose bearer URLs, request arguments, response bodies, or authorization headers.
The operator compares returned hashes locally and records only the conclusion.

## Fixture and live prompt

Prepare a non-sensitive 317 × 193 PNG with distinct colored regions and a small
random pattern. Record its byte and decoded RGB hashes locally. It contains no
personal data. Use a fresh Vibe Work conversation with only the probe connector
enabled, and confirm its tool schema has been refreshed.

Attach the fixture and send:

> Use inspect_attached_image to inspect this attached image. Pass the actual
> image URL or file reference available to you. If none is available, call the
> tool with null. Do not describe or recreate the image.

In classification-only mode, inspect the result and decide whether retrieval
is possible. After enabling retrieval for the verified hostname, send:

> Call inspect_attached_image again for the same attached image, using its actual
> reference. The probe is now configured to attempt retrieval.

## Interpretation and stopping rule

| Observation | Conclusion |
| --- | --- |
| Byte hash matches | Exact original file reached the server. |
| Byte hash differs but RGB hash and dimensions match | Equivalent decoded pixels reached the server with different encoding or metadata. |
| Valid image but hashes differ | Some image was retrieved; compare locally before claiming attachment transfer. Vibe may transform uploads. |
| File ID or internal/local reference | A retrieval or host-side transfer mechanism is still missing. |
| Null, failed retrieval, blocked hostname, or redirect | Inconclusive about general platform support; record the specific obstacle. |
| No tool call | Inconclusive about transport; first check tool visibility and invocation. |

Success establishes observed behavior for the tested Vibe mode/account and date;
it does not establish a stable, supported platform contract. Confirm support
before depending on an undocumented internal endpoint for the submission.

Stop after the two-stage experiment and record date, probe commit, Vibe mode,
statuses, hash comparison, and remaining uncertainty. Disable the test service
and remove its connector/secret when finished. Do not implement slide placement
until transfer succeeds.

## Local validation before spending messages

- Real MCP discovery and invocation expose precisely this tool and null input.
- Classification does not make a network request or echo private references.
- Download policy rejects disallowed destinations and redirects, enforces time,
  byte and pixel limits, and does not forward credentials.
- Valid fixture produces the independently calculated hashes; invalid image and
  HTTP failures yield safe statuses.
- Logs/results never contain a sentinel secret placed in a test URL query.

## Research basis

- [Vibe files and canvas](https://docs.mistral.ai/vibe/work/files-and-canvas):
  image uploads and analysis, without a documented custom-MCP attachment handoff.
- [Custom MCP connectors](https://docs.mistral.ai/vibe/work/connectors/mcp-connectors):
  connector setup and limitations.
- [Workflow file forms](https://docs.mistral.ai/studio/workflows/interacting-with-workflows/conversational_workflows/forms_and_confirmations):
  signed file URLs are documented for Workflows; this does not establish the
  same mechanism for ordinary MCP tools.
