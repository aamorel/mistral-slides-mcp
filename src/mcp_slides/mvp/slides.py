"""Typed content slide rendering with the resolved default colors and font."""
from typing import Any
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from .layouts import content_boxes, color_role
from .outline import validate_outline

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


def create_deck(creds: Credentials, outline: dict[str, Any], *,
                palette: dict, cover_image_url: str) -> dict[str, Any]:
    outline = validate_outline(outline, len(outline["slides"]))
    service = build("slides", "v1", credentials=creds, cache_discovery=False)
    title = outline["title"]
    presentation = service.presentations().create(body={"title": title}).execute()
    presentation_id = presentation["presentationId"]

    requests: list[dict[str, Any]] = [
        {"createSlide": {"objectId": "mvp_slide_0", "slideLayoutReference": {"predefinedLayout": "BLANK"}}},
        {"createImage": {"objectId": "mvp_cover_image", "url": cover_image_url,
            "elementProperties": {"pageObjectId": "mvp_slide_0",
                "size": {"width": {"magnitude": 720, "unit": "PT"}, "height": {"magnitude": 405, "unit": "PT"}},
                "transform": {"scaleX": 1, "scaleY": 1, "translateX": 0, "translateY": 0, "unit": "PT"}}}},
        # Solid title band guarantees contrast regardless of generated image colors.
        create_text_box_request("mvp_cover_band", "mvp_slide_0", 0, 224, 720, 181),
        {"updateShapeProperties": {"objectId": "mvp_cover_band", "shapeProperties": {
            "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": rgb(palette["background"])}, "alpha": 1}},
            "outline": {"propertyState": "NOT_RENDERED"}}, "fields": "shapeBackgroundFill,outline"}},
        create_text_box_request("mvp_title_0", "mvp_slide_0", 40, 244, 640, 132),
        insert_text_request("mvp_title_0", title),
        {"updateTextStyle": {"objectId": "mvp_title_0", "textRange": {"type": "ALL"},
            "style": {"fontFamily": palette.get("font_family", "Arial"), "fontSize": {"magnitude": 30, "unit": "PT"},
                "bold": True, "foregroundColor": {"opaqueColor": {"rgbColor": rgb(palette["title"])}}},
            "fields": "fontFamily,fontSize,bold,foregroundColor"}},
    ]
    for index, slide in enumerate(outline["slides"], start=1):
        slide_id = f"mvp_slide_{index}"
        requests.extend([
            {"createSlide": {"objectId": slide_id, "slideLayoutReference": {"predefinedLayout": "BLANK"}}},
            {"updatePageProperties": {"objectId": slide_id,
                "pageProperties": {"pageBackgroundFill": {"solidFill": {
                    "color": {"rgbColor": rgb(palette["background"])}, "alpha": 1}}},
                "fields": "pageBackgroundFill"}},
        ])
        for role, text, geometry, size, bullet_style in content_boxes(slide):
            object_id = f"mvp_{role}_{index}"
            color = color_role(object_id)
            requests.extend([
                create_text_box_request(object_id, slide_id, *geometry),
                insert_text_request(object_id, text),
                {"updateTextStyle": {"objectId": object_id, "textRange": {"type": "ALL"},
                    "style": {"fontSize": {"magnitude": size, "unit": "PT"},
                        "fontFamily": palette["font_family"], "bold": color == "title",
                        "foregroundColor": {"opaqueColor": {"rgbColor": rgb(palette[color])}}},
                    "fields": "fontSize,fontFamily,bold,foregroundColor"}},
                {"updateParagraphStyle": {"objectId": object_id, "textRange": {"type": "ALL"},
                    "style": {"lineSpacing": 110, "spaceAbove": {"magnitude": 0, "unit": "PT"},
                        "spaceBelow": {"magnitude": 8 if bullet_style else 0, "unit": "PT"}},
                    "fields": "lineSpacing,spaceAbove,spaceBelow"}},
            ])
            if bullet_style:
                requests.append({"createParagraphBullets": {"objectId": object_id,
                    "textRange": {"type": "ALL"}, "bulletPreset": bullet_style}})

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
        "content_slide_count": len(outline["slides"]),
        "total_slide_count": len(outline["slides"]) + 1,
        "cover_image": "generated",
    }
