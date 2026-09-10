# From a chat to a presentation

Create a deck in Vibe, open it in Google Slides, and refine it in the same chat.
Here is a typical flow.

## 1. Connect once

In Vibe, add a **Custom MCP Connector** named **Mistral Slides** with this URL:

```text
https://mistral-slides-mcp-production.up.railway.app/mcp
```

Leave authentication on **Auto-detect**, connect with your approved Google
account, then enable the connector in a chat. No API key is needed.
If access is denied, contact the operator with the Google email you want to use.

## 2. Create your deck

> Create a 3-slide presentation about a weekend in Paris. Use a short key message
> on slide 2 and three activity bullets on slide 3.

Open the returned link: the presentation is in **your Google Drive**, with an
image cover and two content slides.

You can also create the initial presentation from your own content. Paste your
notes or source text into the chat and ask:

> Create a 3-slide presentation from the content below. Keep the key facts and
> use only the information provided.
>
> [Paste your content here]

## 3. Refine it in the same chat

| What you want | What to say |
| --- | --- |
| Revise the wording | “Make slide 2 more inviting, keeping it to one short sentence.” |
| Add your own image | Attach a PNG, JPEG or WebP: “Add this image to slide 2.” |
| Replace that image | Attach another image: “Replace the image on slide 2 with this one.” |
| Extend the deck | “Append a slide with three practical travel tips.” |
| Change its appearance | “Make this deck's titles dark blue and use Georgia.” |
| Use plain backgrounds | “Remove the gradient from this deck.” |

These changes keep the **same presentation link**. You can paste that link into
chat whenever you need to identify the deck.

## 4. Keep your preferred style

> Use cream backgrounds and Georgia by default for future presentations.

New decks automatically use your saved style. Existing decks stay unchanged
unless you ask: “Apply my default style to this presentation.” You can also ask
“What is my saved style?” or “Reset my default style.” Defaults belong to this
connection; reconnecting starts fresh.

## A few limits

- New decks contain **1–6 slides including the cover**. Slide numbers count the
  cover as slide 1. You can add more content slides afterward.
- Images fit beside short key-message or bullet text, one image per slide.
  If the text is too long, shorten it first; if an attachment expires, upload it again.
- Text edits preserve the number of bullets or steps. Slide removal/reordering,
  layout conversion, and arbitrary templates are unsupported.
- If an update cannot be confirmed, inspect the deck before retrying.

For detailed boundaries, see [capabilities](capabilities.md) and
[image placement](capabilities.md#images-on-existing-slides).
