# Live attachment transfer result — 2026-09-09

## Setup and provenance

User ran the standalone local probe through a temporary HTTPS tunnel and supplied
the raw Vibe tool results in the development conversation. The assistant compared
the successful result against the local fixture's `expected.json`.

Production base commit: `411cf43`. Probe files were uncommitted investigation
files at test time; there is no committed probe revision to cite. Eight isolated
local tests passed, including real localhost MCP discovery, bearer authentication
and null invocation. Live transfer evidence below is separate from those tests.

The test used a non-sensitive 317 × 193 PNG with colored regions and random
pixels. No attachment URL, signature, bearer token or private conversation URL
is retained in this record. Exact Vibe model/version was not recorded.

## Observations

| Probe ID | Result | Meaning |
| --- | --- | --- |
| `964597455c7fc984176dd88e` | `reference_observed`, HTTPS URL, query present | Vibe forwarded a reference on `mistralaichatupprodswe.blob.core.windows.net`. No retrieval attempted. |
| `6e142a18e590782ec6483b59` | `retrieval_denied`, HTTP 403 | Retrieval was refused. The safe result does not establish why. |
| `7b707f185352f1aa9b50231a` | `image_retrieved`, after user attached the image again | Server downloaded and decoded a PNG. |

| Evidence | Local original | Retrieved image |
| --- | --- | --- |
| Dimensions | 317 × 193 | 317 × 193 |
| Bytes | 4,253 | 5,369 |
| SHA-256 of bytes | `4161354c6678cddee86489fd2c8e67ba02ae2dd0c9e8e0736edddd74b0dcf077` | `5633594e7a0cfb420df2228387a402b284ffaac05ecda5705aae8f2f4e0c9000` |
| SHA-256 of decoded RGB | `1bcbafd7afc98d512f8f954918ec1eed3e8004e0820ddfed3e8581a513562fc6` | `1bcbafd7afc98d512f8f954918ec1eed3e8004e0820ddfed3e8581a513562fc6` |

## Conclusion and limits

The tested Vibe flow can forward a fresh attachment reference to a remote MCP
tool, which retrieves equivalent decoded RGB pixels without browser cookies,
Google credentials or a Mistral API key. Different PNG bytes indicate different
encoding or metadata somewhere in the path; the test does not identify which
component changed them. RGB comparison does not validate alpha channels, color
profiles, EXIF orientation or arbitrary formats.

The first 403 remains unexplained. Expiry or stale/malformed references are
hypotheses, not established causes. No TTL, cross-account behavior, large-image
behavior or permanent API guarantee was established. No image was inserted into
Google Slides by this probe.

For a product implementation, retrieve fresh references promptly, finish image
validation before changing the deck, and give a re-upload instruction if access
fails. Keep the original attachment URL out of logs and the Slides source URL;
use our own short-lived asset URL for Google's copy.

## Retention and cleanup

The reproducible experiment is retained entirely in this directory, with one
parent README link. Generated fixture, token and tunnel binary remain gitignored
under `.secrets/image-attachment-probe/`.

The user was instructed to stop the server and tunnel after testing. Their final
process state and removal of the Vibe test connector have not been verified.
When no longer needed, stop those processes, remove the test connector, discard
the dedicated token and delete the ignored fixture/binary directory. None of
these cleanup actions is claimed as performed here.
