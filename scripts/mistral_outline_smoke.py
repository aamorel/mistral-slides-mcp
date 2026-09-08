"""Generate and validate a strict JSON slide outline with Mistral."""

from __future__ import annotations

import argparse
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
        raise SystemExit("Missing MISTRAL_API_KEY environment variable")

    client = Mistral(api_key=api_key)
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

    response = client.chat.complete(
        model=model,
        messages=messages,
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    if not isinstance(content, str):
        raise ValueError("Mistral response content was not a string")

    parsed = json.loads(content)
    return validate_outline(parsed, slide_count)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topic", nargs="?", default="AI agents for sales operations")
    parser.add_argument("--slide-count", type=int, default=3)
    parser.add_argument("--audience")
    parser.add_argument("--tone")
    parser.add_argument("--model", default=os.getenv("MISTRAL_MODEL", DEFAULT_MODEL))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.slide_count < 1 or args.slide_count > 10:
        raise SystemExit("--slide-count must be between 1 and 10")

    outline = generate_outline(
        topic=args.topic,
        slide_count=args.slide_count,
        audience=args.audience,
        tone=args.tone,
        model=args.model,
    )
    print(json.dumps(outline, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
