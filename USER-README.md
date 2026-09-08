# Try the Google Slides connector

Generate from a topic or your notes, choose **Minimal**, **Dark**, or **Warm**
styling or save your preferred colors/font, then revise wording through chat.
Your saved style is used automatically, falling back to Minimal;
there is no style-selection step unless you ask for one.

1. In Vibe, open **Connectors → Add Connector → Custom MCP Connector**.
2. Name it **Mistral Slides** and paste this server URL:
   `https://mistral-slides-mcp-production.up.railway.app/mcp`
3. Leave authentication on **Auto-detect**. No API key, custom header, client ID, or client secret is needed. Click **Create / Connect**.
4. Click **Continue with Google**, choose your Google account, and grant access. You’ll return to Vibe.
5. Enable the connector in a chat and ask:
   > Create a 3-slide presentation about a weekend in Paris using Mistral Slides.

Every new deck includes an extra title slide with a generated background image.
“Three slides” creates one cover plus three content slides. Image generation may
take a little longer; the title stays editable.

The presentation should appear in **your Google Drive**. Open the returned link—or open it directly in Drive if the link doesn’t work.

For a different look, ask: “Create three slides about this topic using the Dark
style.” Minimal uses white with a blue accent, Dark uses a dark background with
light text, and Warm uses cream with a brown accent. Presets apply to new decks;
changing an existing deck's style and custom templates are not supported.

After creating a deck, try: “Make slide two less technical.” The connector can
revise supported text at the same link; it cannot rearrange slides or edit images.

**Before testing:** send me the Google email you’ll use so I can add you as a tester. Google may show an “app not verified” warning because this is a test app; continue only if you recognize this invitation and are comfortable granting access.

Please tell me whether connecting, creating the deck, and opening it worked. If something fails, send me the error message—never passwords or tokens.


To personalize future decks, ask: “Save cream backgrounds, dark blue titles,
charcoal body text, and Georgia as my default style.” You can also ask “What is
my saved style?” or “Reset my default style.” Supported fonts: Arial, Verdana,
Georgia, and Trebuchet MS. Colors must remain readable. Settings apply to this
connection and future decks only; reconnecting starts a new preference scope.
