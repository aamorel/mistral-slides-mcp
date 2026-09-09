"""Small public information pages for the connector's Google OAuth branding."""
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
add a slide, or adjust colors and fonts through conversation.</p>
<h2>How it works</h2>
<p>Connect through Vibe, authorize your Google account, and ask for a presentation.
Mistral generates the text and cover image; Google Slides stores the deck in
your account. You receive a link to open and edit it.</p>
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
database activity.</p>
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
