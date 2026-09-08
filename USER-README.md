# Try the Google Slides connector

Generate from a topic or your notes, customize your default colors and font,
and revise wording through chat. Every new presentation uses your default style
automatically. Before customization, it uses white backgrounds, blue titles,
charcoal body text, and Arial.

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

For a different look, ask: “Change my default background to cream and my font to
Georgia.” The assistant preserves your other settings. Changes apply to future
presentations. To update an existing deck too, ask: “Apply my default style to
the trees presentation.” It keeps the same link, wording, layout, and cover image.
Unsupported slides are skipped and reported. Custom templates are not supported.

After creating a deck, try: “Make slide two less technical.” The connector can
revise supported text at the same link; it cannot rearrange slides or edit images.

**Before testing:** send me the Google email you’ll use so I can add you as a tester. Google may show an “app not verified” warning because this is a test app; continue only if you recognize this invitation and are comfortable granting access.

Please tell me whether connecting, creating the deck, and opening it worked. If something fails, send me the error message—never passwords or tokens.


To personalize future decks, ask: “Save cream backgrounds, dark blue titles,
charcoal body text, and Georgia as my default style.” You can also ask “What is
my saved style?” or “Reset my default style.” Supported fonts: Arial, Verdana,
Georgia, and Trebuchet MS. Colors must remain readable. Settings apply to this
connection and apply automatically to future decks; updating an existing deck
requires a separate request. Reconnecting starts a new preference scope.
