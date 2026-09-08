"""Generate and validate a strict JSON slide outline with Mistral."""

from __future__ import annotations

import json
import os
from typing import Any

from mistralai.client import Mistral


DEFAULT_MODEL = "mistral-medium-latest"


def build_prompt(topic: str, slide_count: int, audience: str | None, tone: str | None) -> str:
    audience_text = audience or "a general professional audience"
    tone_text = tone or "clear, concise, and practical"
    return f"""
Return only a valid JSON object for a short slide presentation.

Schema:
{{
  "title": "string",
  "slides": [
    {{
      "title": "string",
      "bullets": ["string", "string", "string"]
    }}
  ]
}}

Rules:
- Topic: {topic}
- Audience: {audience_text}
- Tone: {tone_text}
- Produce exactly {slide_count} slides.
- Each slide must have exactly 3 bullets.
- Each title must be 80 characters or fewer.
- Each bullet must be 140 characters or fewer.
- Do not include markdown.
- Do not include commentary outside the JSON object.
""".strip()


def validate_outline(value: Any, slide_count: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("outline must be a JSON object")

    title = value.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("outline.title must be a non-empty string")
    if len(title) > 100:
        raise ValueError("outline.title is too long")

    slides = value.get("slides")
    if not isinstance(slides, list):
        raise ValueError("outline.slides must be a list")
    if len(slides) != slide_count:
        raise ValueError(f"outline.slides must contain exactly {slide_count} slides")

    normalized_slides: list[dict[str, Any]] = []
    for index, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            raise ValueError(f"slide {index} must be an object")

        slide_title = slide.get("title")
        if not isinstance(slide_title, str) or not slide_title.strip():
            raise ValueError(f"slide {index}.title must be a non-empty string")
        if len(slide_title) > 100:
            raise ValueError(f"slide {index}.title is too long")

        bullets = slide.get("bullets")
        if not isinstance(bullets, list):
            raise ValueError(f"slide {index}.bullets must be a list")
        if len(bullets) != 3:
            raise ValueError(f"slide {index}.bullets must contain exactly 3 bullets")

        normalized_bullets: list[str] = []
        for bullet_index, bullet in enumerate(bullets, start=1):
            if not isinstance(bullet, str) or not bullet.strip():
                raise ValueError(f"slide {index}.bullets[{bullet_index}] must be a non-empty string")
            if len(bullet) > 180:
                raise ValueError(f"slide {index}.bullets[{bullet_index}] is too long")
            normalized_bullets.append(bullet.strip())

        normalized_slides.append(
            {
                "title": slide_title.strip(),
                "bullets": normalized_bullets,
            }
        )

    return {
        "title": title.strip(),
        "slides": normalized_slides,
    }


def generate_outline(
    topic: str,
    slide_count: int,
    audience: str | None,
    tone: str | None,
    model: str,
) -> dict[str, Any]:
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("Missing MISTRAL_API_KEY environment variable")

    client = Mistral(api_key=api_key, timeout_ms=60000)
    messages = [
        {
            "role": "system",
            "content": "You generate concise presentation outlines as strict JSON objects.",
        },
        {
            "role": "user",
            "content": build_prompt(topic, slide_count, audience, tone),
        },
    ]

    with client:
        for attempt in range(2):
            response = client.chat.complete(
                model=model, messages=messages, temperature=0.2,
                response_format={"type": "json_object"},
            )
            try:
                content = response.choices[0].message.content
                if not isinstance(content, str):
                    raise ValueError("Expected JSON text")
                return validate_outline(json.loads(content), slide_count)
            except (ValueError, IndexError, AttributeError, TypeError):
                if attempt:
                    raise ValueError("Mistral returned an invalid outline twice") from None
                messages.append({"role": "user", "content":
                    "Try again. Follow the JSON schema, exact slide count and length limits strictly."})
    raise ValueError("No outline generated")
