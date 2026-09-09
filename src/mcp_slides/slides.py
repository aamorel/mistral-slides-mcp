"""Typed content slide rendering with the resolved default colors and font."""
from typing import Any
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from .layouts import content_boxes, color_role, decoration_boxes, DECORATION_COLOR
from .outline import validate_outline
from . import gradients
from .observability import operation


class DeckCreationError(RuntimeError):
    """Safe recovery guidance; Google may already have committed the write."""


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


def decoration_requests(kind: str, index: int) -> list[dict]:
    requests = []
    for role, geometry in decoration_boxes(kind):
        object_id = f'mvp_{role}_{index}'
        create = create_text_box_request(object_id, f'mvp_slide_{index}', *geometry)
        create['createShape']['shapeType'] = 'RECTANGLE'
        requests.extend([create, {'updateShapeProperties': {
            'objectId': object_id,
            'shapeProperties': {
                'shapeBackgroundFill': {'solidFill': {
                    'color': {'rgbColor': rgb(DECORATION_COLOR)}, 'alpha': 1}},
                'outline': {'propertyState': 'NOT_RENDERED'},
            },
            'fields': 'shapeBackgroundFill,outline',
        }}])
    return requests


def content_slide_requests(slide: dict, index: int, palette: dict, *, insertion_index: int | None = None, gradient_url: str | None = None) -> list[dict]:
    """Build only a new content slide; never mutate existing objects."""
    slide = validate_outline({"title": "Content", "slides": [slide]}, 1)["slides"][0]
    slide_id = f"mvp_slide_{index}"
    requests = []
    requests.extend([
        {"createSlide": {"objectId": slide_id, "slideLayoutReference": {"predefinedLayout": "BLANK"}}},
        {"updatePageProperties": {"objectId": slide_id,
            "pageProperties": {"pageBackgroundFill": {"solidFill": {
                "color": {"rgbColor": rgb(palette["background"])}, "alpha": 1}}},
            "fields": "pageBackgroundFill"}},
    ])
    requests.extend(decoration_requests(slide['type'], index))
    if palette.get('gradient', False):
        if not gradient_url:
            raise ValueError('A prepared gradient image is required.')
        requests.extend(gradients.requests(index, '#' + palette['background'],
                                          '#' + palette['gradient_color'], gradient_url))
    for role, text, geometry, size, bullet_style in content_boxes(slide):
        object_id = f"mvp_{role}_{index}"
        color = color_role(object_id)
        requests.extend([
            create_text_box_request(object_id, slide_id, *geometry),
            {'updateShapeProperties': {'objectId': object_id,
                'shapeProperties': {'outline': {'propertyState': 'NOT_RENDERED'},
                    'shapeBackgroundFill': {'propertyState': 'NOT_RENDERED'},
                    'contentAlignment': 'MIDDLE' if role == 'title' else 'TOP'},
                'fields': 'outline,shapeBackgroundFill,contentAlignment'}},
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
    if insertion_index is not None:
        requests[0]["createSlide"]["insertionIndex"] = insertion_index
    return requests


def create_deck(creds: Credentials, outline: dict[str, Any], *,
                palette: dict, cover_image_url: str, publish_gradient=None) -> dict[str, Any]:
    outline = validate_outline(outline, len(outline["slides"]))
    gradient_url = (publish_gradient('#' + palette['background'], '#' + palette['gradient_color'])
                    if palette.get('gradient', False) else None)
    title = outline["title"]

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
    requests.extend(decoration_requests('cover', 0))
    for index, slide in enumerate(outline["slides"], start=1):
        requests.extend(content_slide_requests(slide, index, palette, gradient_url=gradient_url))

    # Finish deterministic rendering before creating anything in Drive.
    service = build("slides", "v1", credentials=creds, cache_discovery=False)
    try:
        with operation("google_create_empty"):
            presentation = service.presentations().create(body={"title": title}).execute(num_retries=0)
            presentation_id = presentation["presentationId"]
    except Exception:
        raise DeckCreationError(
            "Google Slides creation could not be confirmed. A deck may already exist. "
            "Check your Google Drive for the requested title before retrying to avoid duplicates."
        ) from None

    if requests:
        try:
            # A newly created presentation can already contain a starter slide.
            # Read its actual IDs; remove those slides after adding our content,
            # in the same batch, so only the requested slides remain.
            with operation("google_read_initial"):
                initial = service.presentations().get(
                    presentationId=presentation_id, fields="slides(objectId)",
                ).execute(num_retries=2)
            requests.extend(
                {"deleteObject": {"objectId": slide["objectId"]}}
                for slide in initial.get("slides", [])
            )
            with operation("google_populate"):
                service.presentations().batchUpdate(
                    presentationId=presentation_id, body={"requests": requests},
                ).execute(num_retries=0)
        except Exception:
            raise DeckCreationError(
                "A deck was created but population could not be confirmed. "
                "It may be empty or complete. Check it before retrying: "
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
