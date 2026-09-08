# Try the Google Slides connector

1. In Vibe, open **Connectors → Add Connector → Custom MCP Connector**.
2. Name it **Mistral Slides** and paste this server URL:
   `https://mistral-slides-mcp-production.up.railway.app/mcp`
3. Leave authentication on **Auto-detect**. No API key, custom header, client ID, or client secret is needed. Click **Create / Connect**.
4. Click **Continue with Google**, choose your Google account, and grant access. You’ll return to Vibe.
5. Enable the connector in a chat and ask:
   > Create a 3-slide presentation about a weekend in Paris using Mistral Slides.

The presentation should appear in **your Google Drive**. Open the returned link—or open it directly in Drive if the link doesn’t work.

**Before testing:** send me the Google email you’ll use so I can add you as a tester. Google may show an “app not verified” warning because this is a test app; continue only if you recognize this invitation and are comfortable granting access.

Please tell me whether connecting, creating the deck, and opening it worked. If something fails, send me the error message—never passwords or tokens.
