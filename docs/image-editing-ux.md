# Image editing UX

Status: implemented; deployed Google/Vibe acceptance remains pending.
Attachment feasibility evidence lives in
[the isolated investigation](../scripts/investigation/image_attachment_probe/RESULTS.md).

## Implemented first slice

Add one user-supplied image to an existing key-message or bullet slide, using
a common text-left/image-right composition. Attachments are an edit-only feature. A deck may have images on multiple slides,
but each slide has one image slot and each request handles one image/target pair.

Creation support is a later extension: the same renderer could accept an image
at creation time, but selecting its slide, reserving space in the outline, and
reporting partial failures need their own contract.

## User flow

1. User attaches an image and says "Add this to slide 2."
2. Resolve slide 2 by its current visible order, counting the cover as slide 1.
   Read current state and revision; do not infer an ID from a slide number.
3. Validate the slide before downloading; retrieve and validate the fresh attachment
   before writing.
4. Apply text geometry and insert the image together in a revision-checked batch.
5. Return the same deck URL and a concrete summary: "Added your image to slide 2,
   beside the text. Kept the full image visible."

No position/crop questionnaire for this ordinary request. Ask only if the deck,
target slide or attachment is ambiguous. If a slot is occupied, "replace the
image" replaces it; "add another image" is unsupported and must not silently
replace the first. Multiple attachments with unclear mapping require clarification.

## Placement and sizing

Keep the title full width. Use one bounded text region on the left and an image
frame on the right, with fixed outer margins and a clear gutter. Reuse existing
text shapes/IDs and retain wording, list counts, font and colors. Validate text
against narrower layout budgets; do not silently shorten it, shrink it to fit,
or assume existing full-width budgets remain safe. Limits are 90 message characters
or up to 3 bullets of 55 characters each (150 total), with a conservative wrapping
check. Local layout approximations were inspected across all four fonts; actual
Google rendering remains a live acceptance check.

Default to contain: preserve aspect ratio, show the full image, center it in the
frame, and let unused space match the slide background. No stretching. This is
appropriate for screenshots, diagrams, logos, and portraits as well as photos.
Honor orientation and preserve transparency during normalization.

An optional later "fill the frame" command could use center crop, explicitly
reporting that edges were cropped. Do not initially add focal-point selection,
subject detection, free positioning or arbitrary dimensions.

## Support boundaries

| Slide state | Implemented behavior |
| --- | --- |
| Recognized key-message or bullets; text fits narrower budget | Add image and reflow existing text. |
| Same supported slide with an existing managed image | Explicit replacement keeps frame and text geometry. |
| Unsupported paragraph formatting | Explain the formatting issue; shortening text will not fix it. Leave the deck unchanged. |
| Too much text | Explain that there is insufficient room; offer a separate wording edit before retrying. |
| Comparison or steps | Explain image placement is not yet supported for that layout; do not convert it automatically. |
| Cover, grouped/custom elements, or altered geometry we cannot preserve | Reject with a precise reason and leave the deck unchanged. |
| Reference unavailable or invalid image | Request re-upload; leave the deck unchanged. |
| Revision conflict | Reread before deciding whether to retry. |
| Unconfirmed Google write | Return target/object identity and recovery guidance; reread to avoid duplicates. |

An image-containing slide remains text-editable under its new budgets; styling
preserves its image. Subsequent slide insertion inherits supported styling without
copying the image. Image removal/restoring previous geometry is unsupported.

Ordinary Google level-zero bullet indentation is supported (up to 36 pt, with
tolerance for PT/EMU conversion). Custom paragraph spacing, changed font sizes
and altered geometry can still be rejected. Automatic font shrinking and larger
text budgets are future options, not implemented behavior.

The server temporarily publishes the normalized image for Google to fetch, then
cleans it up. Google Slides retains the inserted image after that URL expires.
The attachment is not sent to the Mistral API and placement uses no model allowance.

## Why not an image variant of every layout yet?

Key-message and bullet layouts share a straightforward single-column text
structure. Comparisons already use two columns, while steps can consume most of
the body height. Adding an image to those layouts demands different compositions
and capacity rules. Four variants also multiply the visual validation needed for
editing, insertion and styling. Start with one composition and two text types.

## Demo and acceptance

Generate a short key-message/bullet deck, attach a screenshot or photo, add it to
slide 2, revise the wording, then replace the image explicitly. Check that the
same presentation and neighboring slides are preserved. Validate landscape,
portrait, transparent and text-bearing images; short and maximum supported text;
re-upload recovery; and an unsupported layout. A controlled demo should exercise
real supported behavior while unsupported requests fail clearly.
