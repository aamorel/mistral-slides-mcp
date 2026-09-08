"""Title-and-bullet rendering with a small set of visual presets."""
from typing import Any
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Presets style the same editable boxes; these are not native Google themes.
STYLE_PRESETS = {
    "minimal": {"background": "FFFFFF", "title": "244B63", "body": "263238"},
    "dark": {"background": "18222E", "title": "9EDADB", "body": "F1F5F9"},
    "warm": {"background": "FAF5EB", "title": "854529", "body": "403B35"},
}


def rgb(hex_color: str) -> dict[str, float]:
    return dict(zip(("red", "green", "blue"),
                    (int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))))


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


def create_deck(creds: Credentials, outline: dict[str, Any], style: str = "minimal") -> dict[str, str]:
    if style not in STYLE_PRESETS:
        raise ValueError("Unknown style. Choose minimal, dark, or warm.")
    palette = STYLE_PRESETS[style]
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
                {"updatePageProperties": {
                    "objectId": slide_id,
                    "pageProperties": {"pageBackgroundFill": {"solidFill": {
                        "color": {"rgbColor": rgb(palette["background"])}, "alpha": 1}}},
                    "fields": "pageBackgroundFill",
                }},
                create_text_box_request(title_box_id, slide_id, 40, 32, 640, 88),
                insert_text_request(title_box_id, slide["title"]),
                create_text_box_request(body_box_id, slide_id, 62, 136, 590, 230),
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
        for kind, size in (("title", 26), ("body", 18)):
            requests.append({"updateTextStyle": {
                "objectId": f"mvp_{kind}_{index}", "textRange": {"type": "ALL"},
                "style": {"fontSize": {"magnitude": size, "unit": "PT"},
                          "fontFamily": "Arial", "bold": kind == "title",
                          "foregroundColor": {"opaqueColor": {"rgbColor": rgb(palette[kind])}}},
                "fields": "fontSize,fontFamily,bold,foregroundColor",
            }})
            requests.append({"updateParagraphStyle": {
                "objectId": f"mvp_{kind}_{index}", "textRange": {"type": "ALL"},
                "style": {"lineSpacing": 110, "spaceAbove": {"magnitude": 0, "unit": "PT"},
                          "spaceBelow": {"magnitude": 8 if kind == "body" else 0, "unit": "PT"}},
                "fields": "lineSpacing,spaceAbove,spaceBelow",
            }})

    if requests:
        try:
            # A newly created presentation can already contain a starter slide.
            # Read its actual IDs; remove those slides after adding our content,
            # in the same batch, so only the requested slides remain.
            initial = service.presentations().get(
                presentationId=presentation_id, fields="slides(objectId)",
            ).execute()
            requests.extend(
                {"deleteObject": {"objectId": slide["objectId"]}}
                for slide in initial.get("slides", [])
            )
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
        "style": style,
    }
