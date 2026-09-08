"""Create a minimal Google Slides deck using user OAuth and drive.file scope."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"
DEFAULT_OUTLINE = {
    "title": "MCP Slides Smoke Test",
    "slides": [
        {
            "title": "What This Proves",
            "bullets": [
                "OAuth can grant user-scoped access",
                "drive.file can create a Google Slides deck",
                "The app can populate simple slide content",
            ],
        },
        {
            "title": "MVP Direction",
            "bullets": [
                "Keep slide design intentionally plain",
                "Generate a strict JSON outline first",
                "Return the created presentation URL",
            ],
        },
    ],
}


def load_credentials(credentials_path: Path, token_path: Path, port: int) -> Credentials:
    creds: Credentials | None = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), [DRIVE_FILE_SCOPE])

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), [DRIVE_FILE_SCOPE])
        creds = flow.run_local_server(
            host="localhost",
            port=port,
            authorization_prompt_message=(
                "Open this URL to authorize Google Slides access:\n{url}\n"
            ),
            success_message="Authorization complete. You can close this tab.",
            open_browser=True,
            access_type="offline",
            prompt="consent",
        )

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


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
    service = build("slides", "v1", credentials=creds)
    title = outline["title"]
    presentation = service.presentations().create(body={"title": title}).execute()
    presentation_id = presentation["presentationId"]

    requests: list[dict[str, Any]] = []
    for index, slide in enumerate(outline["slides"], start=1):
        slide_id = f"smoke_slide_{index}"
        title_box_id = f"smoke_title_{index}"
        body_box_id = f"smoke_body_{index}"
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

    if requests:
        service.presentations().batchUpdate(
            presentationId=presentation_id,
            body={"requests": requests},
        ).execute()

    return {
        "presentation_id": presentation_id,
        "presentation_url": f"https://docs.google.com/presentation/d/{presentation_id}/edit",
        "title": title,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--credentials",
        type=Path,
        default=Path("google-auth-client.json"),
        help="Path to the Google OAuth client JSON.",
    )
    parser.add_argument(
        "--token",
        type=Path,
        default=Path(".secrets/google-token-drive-file.json"),
        help="Path for the cached user OAuth token.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8081,
        help="Local OAuth callback port. Must match the Google OAuth redirect URI.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.credentials.exists():
        raise SystemExit(f"Missing Google OAuth client JSON: {args.credentials}")

    creds = load_credentials(args.credentials, args.token, args.port)
    result = create_deck(creds, DEFAULT_OUTLINE)
    print("Created presentation:")
    print(f"  title: {result['title']}")
    print(f"  presentation_id: {result['presentation_id']}")
    print(f"  presentation_url: {result['presentation_url']}")


if __name__ == "__main__":
    main()
