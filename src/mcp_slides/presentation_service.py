"""Creation workflow; independent of MCP transport and OAuth request context."""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

from starlette.concurrency import run_in_threadpool
from . import outline, slides, preferences, backgrounds, gradients, usage
from .observability import operation, request_id

logger = logging.getLogger("uvicorn.error")


class GenerationError(RuntimeError):
    """A safe, actionable creation failure suitable for the caller."""


STYLE_GUIDANCE = (
    "Use set_presentation_style for this deck's colors/font/gradient; it never saves defaults. "
    "A subtle blue gradient is on by default for content slides. Set gradient=false to remove it; "
    "set gradient=true and gradient_color to enable a different tint. The cover image is preserved. "
    "Use set_default_style only for preferences for future decks. Both accept partial changes. "
    "Use set_presentation_style(use_default_style=True) to apply saved defaults explicitly."
)


async def create_presentation(
    creds, subject: str, topic: str | None, slide_count: int,
    audience: str | None, tone: str | None, *, basis: str,
    source_content: str | None, instructions: str | None,
) -> dict[str, Any]:
    try:
        with operation("load_style"):
            saved = await run_in_threadpool(preferences.get_style, subject)
            palette = preferences.StyleSettings.model_validate(saved["settings"]).palette()
    except Exception:
        raise GenerationError("Could not load the saved style. Try again before creating the deck.") from None
    try:
        with operation("outline"):
            content = await run_in_threadpool(
                outline.generate_outline, topic.strip() if topic else None, slide_count - 1, audience, tone,
                os.getenv("MISTRAL_MODEL", outline.DEFAULT_MODEL),
                basis=basis, source_content=source_content, instructions=instructions,
            )
    except usage.UsageLimitError as exc:
        raise GenerationError(str(exc)) from None
    except Exception:
        raise GenerationError("Mistral could not generate a valid outline. Check the API key or try again.") from None
    try:
        with operation("cover"):
            data = await run_in_threadpool(backgrounds.generate_image, content["title"], palette)
            image_token, image_url = await run_in_threadpool(backgrounds.publish_image, subject, data)
    except usage.UsageLimitError as exc:
        raise GenerationError(str(exc)) from None
    except Exception:
        raise GenerationError("The title background could not be generated or prepared. No deck was created. Check Mistral image-generation access and try again.") from None
    try:
        with operation("google_create"):
            result = await run_in_threadpool(gradients.with_images, subject, slides.create_deck, creds, content,
                palette=palette, cover_image_url=image_url)
            result = {**result, "style_settings": saved["settings"], "style_guidance": STYLE_GUIDANCE}
            # Correlate the exact returned URL with a reported link without exposing
            # private deck IDs, titles, URLs or Google credentials in Railway logs.
            logger.info("presentation_result request_id=%s url_sha256=%s", request_id.get(),
                        hashlib.sha256(result["presentation_url"].encode()).hexdigest())
            return result
    except slides.DeckCreationError as exc:
        raise GenerationError(str(exc)) from None
    except Exception:
        raise GenerationError("Google Slides could not create the deck. Check Google access and API availability.") from None
    finally:
        try:
            await run_in_threadpool(backgrounds.remove_image, image_token)
        except Exception:
            logger.warning("temporary_image_cleanup_failed")
