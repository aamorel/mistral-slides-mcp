# Try the Google Slides connector

Generate from a topic or your notes, style a presentation, save defaults for future
decks, add slides, and revise wording through chat. Every new presentation uses your default style
automatically. Before customization, it uses white backgrounds with a faint blue corner gradient, blue titles,
charcoal body text, and Arial.

1. In Vibe, open **Connectors → Add Connector → Custom MCP Connector**.
2. Name it **Mistral Slides** and paste this server URL:
   `https://mistral-slides-mcp-production.up.railway.app/mcp`
3. Leave authentication on **Auto-detect**. No API key, custom header, client ID, or client secret is needed. Click **Create / Connect**.
4. Click **Continue with Google**, choose your Google account, and grant access. You’ll return to Vibe.
5. Enable the connector in a chat and ask:
   > Create a 3-slide presentation about a weekend in Paris using Mistral Slides.

Generation supports 1–6 content slides. Every new deck includes an extra title slide with a generated background image.
“Three slides” creates one cover plus three content slides. Image generation may
take a little longer; the title stays editable.

The connector chooses between a key message, 1–5 bullets, a two-column comparison,
and numbered steps to suit your material. You can ask for a specific structure:
“Compare feature phones and smartphones, then explain how a call connects.”
You can revise wording in each layout; adding/removing bullets or steps and
converting an existing slide to another layout are not supported yet.

New slides use a simple visual treatment: fine full-width header separators, light grey
dividers between comparison columns, and a subtle side rule for key messages.
These details are built in; style settings control the colors and font. Existing
slides keep their layout when you change their style.

Content slides also have a subtle gradient by default. Ask “Make the gradient
lavender” to change its tint, or “Remove the gradient” for a plain background.
To keep future decks plain, ask “Turn off gradients by default.” The cover keeps
its generated image. Gradient direction and intensity stay fixed and gentle.

The presentation should appear in **your Google Drive**. Open the returned link—or open it directly in Drive if the link doesn’t work.

For a different look on **this presentation**, ask: “Make this deck's titles dark
blue and use Georgia.” Its other formatting stays unchanged, and your saved
defaults do not change.

For **future presentations**, ask: “Use cream backgrounds and Georgia by default.”
Your other saved settings are preserved; existing presentations do not change.
To apply all saved defaults to an existing deck, ask: “Apply my default style to
the trees presentation.”

Deck styling keeps the same link, wording, layout, and cover image. Unsupported
slides or unreadable color combinations are skipped and reported. The cover image
is not recolored. Custom templates are not supported.

After creating a deck, try: “Make slide two less technical.” The connector can
revise supported text at the same link; it cannot rearrange slides or edit images.

To extend the same deck, try: “Add a slide about risks after slide two” or
“Append a conclusion using these notes.” One content slide is added per call;
existing slides and the link are preserved. It matches readable existing colors
and font, falling back to your current saved default with an explicit notice if
needed. Adding images, removing/reordering slides, and changing existing layouts
remain unsupported.

**Access:** this is a client-only pilot for approved company Google accounts and invited personal testers. The last recorded deployment uses Google Testing: until the production rollout is confirmed, send me the Google email you’ll use so I can add you as a tester. Google may show an “app not verified” warning because this is a test app; continue only if you recognize this invitation and are comfortable granting access.

Please tell me whether connecting, creating the deck, and opening it worked. If something fails, send me the error message—never passwords or tokens.


To personalize future decks, ask: “Save cream backgrounds, dark blue titles,
charcoal body text, and Georgia as my default style.” You can also ask “What is
my saved style?” or “Reset my default style.” Supported fonts: Arial, Verdana,
Georgia, and Trebuchet MS. Colors must remain readable. Settings apply to this
connection and apply automatically to future decks; updating an existing deck
requires a separate request. Reconnecting starts a new preference scope.

You can paste a Google Slides link when referring to a deck. Access is limited to
files available to this connector and your connected account. For implementation
limits, see the [current MVP scope](src/mcp_slides/mvp/SCOPE.md).

After the identity-policy upgrade, reconnect once with your approved account. If
generation is paused, busy, or the pilot allowance is exhausted, follow the tool
message; contact the operator for access or allowance changes.
