"""Plain title-and-bullet Google Slides rendering."""
from typing import Any
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

def create_text_box_request(
    object_id: str,
    slide_id: str,
    x: float,
    y: float,
    width: float,
    height: float,
) -> dict[str, Any]:
    return {
        "createShape": {
            "objectId": object_id,
            "shapeType": "TEXT_BOX",
            "elementProperties": {
                "pageObjectId": slide_id,
                "size": {
                    "width": {"magnitude": width, "unit": "PT"},
                    "height": {"magnitude": height, "unit": "PT"},
                },
                "transform": {
                    "scaleX": 1,
                    "scaleY": 1,
                    "translateX": x,
                    "translateY": y,
                    "unit": "PT",
                },
            },
        }
    }


def insert_text_request(object_id: str, text: str) -> dict[str, Any]:
    return {
        "insertText": {
            "objectId": object_id,
            "insertionIndex": 0,
            "text": text,
        }
    }


def create_deck(creds: Credentials, outline: dict[str, Any]) -> dict[str, str]:
    service = build("slides", "v1", credentials=creds, cache_discovery=False)
    title = outline["title"]
    presentation = service.presentations().create(body={"title": title}).execute()
    presentation_id = presentation["presentationId"]

    requests: list[dict[str, Any]] = []
    for index, slide in enumerate(outline["slides"], start=1):
        slide_id = f"mvp_slide_{index}"
        title_box_id = f"mvp_title_{index}"
        body_box_id = f"mvp_body_{index}"
        body_text = "\n".join(slide["bullets"])

        requests.extend(
            [
                {
                    "createSlide": {
                        "objectId": slide_id,
                        "slideLayoutReference": {"predefinedLayout": "BLANK"},
                    }
                },
                create_text_box_request(title_box_id, slide_id, 40, 32, 640, 56),
                insert_text_request(title_box_id, slide["title"]),
                create_text_box_request(body_box_id, slide_id, 62, 112, 590, 230),
                insert_text_request(body_box_id, body_text),
                {
                    "createParagraphBullets": {
                        "objectId": body_box_id,
                        "textRange": {"type": "ALL"},
                        "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                    }
                },
            ]
        )

    for index in range(1, len(outline["slides"]) + 1):
        for kind, size in (("title", 28), ("body", 20)):
            requests.append({"updateTextStyle": {
                "objectId": f"mvp_{kind}_{index}", "textRange": {"type": "ALL"},
                "style": {"fontSize": {"magnitude": size, "unit": "PT"}},
                "fields": "fontSize",
            }})

    if requests:
        try:
            service.presentations().batchUpdate(
                presentationId=presentation_id, body={"requests": requests},
            ).execute()
        except Exception:
            raise RuntimeError(
                "A deck was created but could not be populated. Check it before retrying: "
                f"https://docs.google.com/presentation/d/{presentation_id}/edit"
            ) from None

    return {
        "presentation_id": presentation_id,
        "presentation_url": f"https://docs.google.com/presentation/d/{presentation_id}/edit",
        "title": title,
    }

