"""Small public information pages for the connector's Google OAuth branding."""
from html import escape

from starlette.responses import HTMLResponse

SUPPORT = "aurelien.morel.arthur@gmail.com"


def page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="MCP Slides: a client pilot for creating and editing Google Slides through Vibe.">
<title>{title} · MCP Slides</title>
<style>
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: #faf9f6; color: #25312b; font: 17px/1.65 system-ui, sans-serif; }}
main {{ max-width: 760px; margin: 0 auto; padding: 64px 24px; }}
nav, footer {{ font-size: 14px; }}
nav {{ display: flex; flex-wrap: wrap; gap: 24px; margin-bottom: 56px; }}
a {{ color: #285a41; text-underline-offset: 4px; overflow-wrap: anywhere; }}
a:focus-visible {{ outline: 3px solid #285a41; outline-offset: 4px; }}
h1 {{ font-size: clamp(32px, 7vw, 48px); line-height: 1.15; letter-spacing: -1px; margin: 12px 0 24px; }}
h2 {{ font-size: 21px; line-height: 1.35; margin-top: 32px; }}
p, ul {{ margin: 0 0 20px; }}
.tag {{ color: #536459; font-size: 13px; text-transform: uppercase; letter-spacing: 2px; }}
.connect {{ background: #fff; border: 1px solid #dce3db; border-radius: 24px; padding: clamp(24px, 5vw, 44px); box-shadow: 0 12px 40px #25312b08; }}
.connect h1 {{ font-size: clamp(30px, 6vw, 40px); letter-spacing: -1px; }}
.connect .intro {{ color: #536459; }}
.permissions {{ list-style: none; padding: 0; margin: 28px 0; }}
.permissions li {{ display: flex; gap: 14px; margin: 20px 0; }}
.check {{ color: #285a41; background: #edf4ed; border-radius: 50%; width: 26px; height: 26px; flex: 0 0 26px; text-align: center; font-size: 15px; }}
.permissions strong {{ display: block; font-size: 16px; }}
.permissions p {{ font-size: 14px; color: #536459; margin: 2px 0 0; }}
.connect button {{ display: block; width: 100%; border: 0; border-radius: 12px; padding: 16px 20px; background: #285a41; color: #fff; font: 600 16px/1.4 system-ui, sans-serif; cursor: pointer; }}
.connect button:hover {{ background: #1d4631; }}
.connect button:focus-visible, summary:focus-visible {{ outline: 3px solid #285a41; outline-offset: 4px; }}
.connect .note {{ text-align: center; font-size: 13px; color: #536459; margin: 12px 0 0; }}
.connection-details {{ border-top: 1px solid #e4e9e3; padding-top: 20px; margin-top: 28px; font-size: 13px; color: #536459; }}
.connection-details summary {{ cursor: pointer; font-weight: 600; }}
.connection-details p {{ margin: 12px 0 0; overflow-wrap: anywhere; }}
.client-name {{ overflow-wrap: anywhere; }}
footer {{ border-top: 1px solid #d8dfd8; margin-top: 48px; padding-top: 24px; }}
</style>
</head>
<body><main>
<nav aria-label="Main navigation"><a href="/">MCP Slides</a><a href="/privacy">Privacy policy</a></nav>
{body}
<footer>Operated by Aurélien Morel · <a href="mailto:{SUPPORT}">Contact support</a></footer>
</main></body></html>''', headers={
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
        "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
    })


def home() -> HTMLResponse:
    return page("Home", f'''
<p class="tag">Client pilot</p>
<h1>From a conversation<br>to Google Slides.</h1>
<p>MCP Slides is a connector for Vibe that creates presentations in your own
Google Drive. Describe a topic or provide source material, then revise text,
add a slide, place your own image beside short text, or adjust colors and fonts
through conversation.</p>
<h2>How it works</h2>
<p>Connect through Vibe, authorize your Google account, and ask for a presentation.
Mistral generates the text and cover image; Google Slides stores the deck in
your account. You receive a link to open and edit it.</p>
<p>After creation, attach an image in Vibe and ask to add it to an existing
key-message or bullet slide. Each supported slide has one image slot; the full
image fits beside the text. You can explicitly replace it later.</p>
<h2>Who can use it?</h2>
<p>This evaluation pilot is available to approved Mistral company Google accounts
and invited personal testers. Usage is limited during the pilot.</p>
<h2>Your data</h2>
<p>The connector requests access to files it creates or that you explicitly make
available to it, plus basic Google identity information to check access.
Read the <a href="/privacy">privacy policy</a> for details about data handling.</p>
<p>Questions or access requests? <a href="mailto:{SUPPORT}">{SUPPORT}</a></p>
''')


def privacy() -> HTMLResponse:
    return page("Privacy policy", f'''
<p class="tag">Last updated: 9 September 2026</p>
<h1>Privacy policy</h1>
<p>MCP Slides is an evaluation service operated by Aurélien Morel.
For privacy questions or deletion requests, contact
<a href="mailto:{SUPPORT}">{SUPPORT}</a>.</p>
<h2>Information we access</h2>
<p>When you connect, Google provides your account identifier, email address and
verification status, and company domain when available. We use these to check
whether your account is allowed to use the pilot.</p>
<p>We receive Google access and refresh credentials to act on your behalf.
The Google Drive permission is limited to files created by the app or explicitly
made available to it. We read and modify presentation content as needed to
fulfil your requests.</p>
<h2>How information is used and shared</h2>
<p>Your topics, source material, instructions, and relevant presentation text are
sent to the Mistral API to generate or revise slides. Cover generation sends the
presentation title and selected colors. Generated content is sent to Google
Slides and stored in your Google account.</p>
<p>When you ask to add an attached image, the connector retrieves it from the
attachment link, normalizes its orientation and size, and removes metadata. The
normalized image is temporarily stored for Google to fetch and embed in your
presentation. The connector does not send these attachments to the Mistral API.</p>
<p>Railway hosts the connector and its database. Google and Mistral process the
information needed to provide their services under their own terms and privacy
policies. Vibe also processes your conversation under its own service terms.</p>
<p>We use Google user data to provide the requested presentation features and
control access. We do not sell it, use it for advertising, or use it to train
our own AI models.</p>
<h2>Storage and retention</h2>
<p>The server stores your connection credentials, minimal verified identity
information, connector authorization records, and saved style preferences in
its database. Credentials are not encrypted separately within that database.
Connection data is retained until the connection is revoked, removed by the
access policy, or deleted following a request.</p>
<p>Source briefs and presentation text are processed during requests, rather than
saved as a content archive in the connector database. Decks remain in Google
Drive. Temporary images are served using unguessable links for Google to fetch;
links expire after ten minutes, with cleanup after use or during subsequent
database activity. This includes generated covers, gradients and normalized
attachments. Images already inserted remain in Google Slides after temporary
links expire or connector copies are deleted.</p>
<p>We keep a shared usage counter and operational logs for reliability and
troubleshooting. Application logs are designed to exclude tokens, email
addresses, source text, and presentation URLs. Hosting providers may retain
infrastructure logs under their own policies.</p>
<h2>Your choices and deletion</h2>
<p>You can remove the app's Google permission through
<a href="https://myaccount.google.com/connections">your Google Account connections</a>.
To request deletion of stored connector data, email the support address above.
Connector revocation removes the associated local credentials and preferences.
Deleting connector data does not delete your presentations: manage those directly
in Google Drive. Data retained by Google, Mistral, or Vibe is subject to their
respective controls and policies.</p>
<h2>Changes</h2>
<p>We will update this page if the service's data practices change.</p>
''')


def connection(client_name: str, callback: str, ticket: str, csrf: str) -> HTMLResponse:
    return page("Connect your Google account", f'''
<section class="connect" aria-labelledby="connect-title">
<p class="tag">Connect to MCP Slides</p>
<h1 id="connect-title">Your next presentation<br>starts here.</h1>
<p class="intro"><strong class="client-name">{escape(client_name)}</strong> is requesting access
through MCP Slides to create and work on presentations in your Google Drive.</p>
<ul class="permissions">
<li><span class="check" aria-hidden="true">✓</span><div><strong>Create and refine slides</strong>
<p>Generate a deck, read its content, revise text, add slides, and adjust colors and fonts.</p></div></li>
<li><span class="check" aria-hidden="true">✓</span><div><strong>Your files stay in your Google account</strong>
<p>Access is limited to files this app creates or that you explicitly make available to it.</p></div></li>
<li><span class="check" aria-hidden="true">✓</span><div><strong>Choose your account next</strong>
<p>Use your approved company Google account or an invited personal account.</p></div></li>
</ul>
<form method="post" action="/auth/google/start">
<input type="hidden" name="request" value="{escape(ticket, quote=True)}">
<input type="hidden" name="csrf" value="{escape(csrf, quote=True)}">
<button type="submit">Continue with Google <span aria-hidden="true">→</span></button>
</form>
<p class="note">Google will ask you to review permissions. Close this page to cancel.</p>
<details class="connection-details">
<summary>Connection details</summary>
<p>Google credentials stay on the MCP Slides server; the requesting connector receives its own access token.
Relevant content is sent to Mistral to generate or revise slides. See our <a href="/privacy">privacy policy</a>.</p>
<p>Return address: {escape(callback)}</p>
</details>
</section>
''')
