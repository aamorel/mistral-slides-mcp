"""Failure boundaries: no premature writes, no replay, actionable private recovery."""
import asyncio
import logging
import unittest
from unittest.mock import MagicMock, patch

from mcp_slides import observability, preferences, presentation_service, server, slides

CONTENT = {"title": "Private title", "slides": [
    {"type": "key_message", "title": "Summary", "message": "Private content"}]}
PALETTE = preferences.DEFAULT_STYLE.model_copy(update={"gradient": False}).palette()


class RobustnessTests(unittest.TestCase):
    def create(self):
        return slides.create_deck("credentials", CONTENT, palette=PALETTE,
                                  cover_image_url="https://example.com/private-image")

    def service(self):
        service = MagicMock()
        service.presentations.return_value.create.return_value.execute.return_value = {
            "presentationId": "private-deck"}
        service.presentations.return_value.get.return_value.execute.return_value = {}
        return service

    def test_render_failure_precedes_any_google_call(self):
        with patch.object(slides, "build") as build, patch.object(
                slides, "content_slide_requests", side_effect=ValueError("bad geometry")):
            with self.assertRaises(ValueError):
                self.create()
        build.assert_not_called()

    def test_lost_creation_response_does_not_replay_or_populate(self):
        service = self.service()
        service.presentations.return_value.create.return_value.execute.side_effect = TimeoutError("secret")
        with patch.object(slides, "build", return_value=service):
            with self.assertRaisesRegex(slides.DeckCreationError, "Check your Google Drive") as caught:
                self.create()
        self.assertNotIn("secret", str(caught.exception))
        service.presentations.return_value.create.return_value.execute.assert_called_once_with(num_retries=0)
        service.presentations.return_value.batchUpdate.assert_not_called()

    def test_population_timeout_returns_recovery_link_without_replaying(self):
        service = self.service()
        service.presentations.return_value.batchUpdate.return_value.execute.side_effect = TimeoutError("secret")
        with patch.object(slides, "build", return_value=service):
            with self.assertRaisesRegex(slides.DeckCreationError, "empty or complete") as caught:
                self.create()
        self.assertIn("/private-deck/edit", str(caught.exception))
        self.assertNotIn("secret", str(caught.exception))
        service.presentations.return_value.batchUpdate.return_value.execute.assert_called_once_with(num_retries=0)
        service.presentations.return_value.get.return_value.execute.assert_called_once_with(num_retries=2)

    def test_style_failure_stops_before_paid_work_and_logs_only_safe_details(self):
        with patch.object(preferences, "get_style", side_effect=RuntimeError("oauth-secret")), patch.object(
                presentation_service.outline, "generate_outline") as generate:
            with self.assertLogs("uvicorn.error", level="INFO") as logs:
                with self.assertRaises(presentation_service.GenerationError):
                    asyncio.run(presentation_service.create_presentation(
                        "creds", "private-user", "Private topic", 3, None, None,
                        basis="topic", source_content=None, instructions=None))
        generate.assert_not_called()
        diagnostic = "\n".join(logs.output)
        self.assertIn("stage=load_style outcome=failed error_type=RuntimeError", diagnostic)
        for secret in ("oauth-secret", "private-user", "Private topic"):
            self.assertNotIn(secret, diagnostic)

    def test_request_ids_are_unique_isolated_and_not_copied_from_client(self):
        async def run():
            async def app(scope, receive, send):
                await asyncio.sleep(0)
                with observability.operation("test"):
                    await send({"type": "http.response.start", "status": 200, "headers": []})
            middleware = server.RequestLog(app)

            async def request():
                messages = []
                async def send(message):
                    messages.append(message)
                await middleware({"type": "http", "path": "/mcp", "method": "POST",
                                  "headers": [(b"x-request-id", b"private-input")]}, None, send)
                self.assertEqual(observability.request_id.get(), "local")
                return dict(messages[0]["headers"])[b"x-request-id"].decode()
            return await asyncio.gather(request(), request())

        with self.assertLogs("uvicorn.error", level="INFO") as logs:
            ids = asyncio.run(run())
        self.assertNotEqual(*ids)
        for correlation in ids:
            self.assertEqual(len(correlation), 32)
            self.assertTrue(any(f"request_id={correlation} stage=test" in line for line in logs.output))
        self.assertNotIn("private-input", "\n".join(logs.output))

    def test_provider_and_sdk_info_logs_are_suppressed(self):
        observability.configure_logging()
        for name in ("httpx", "httpx2", "httpcore", "mcp.server.mcpserver.server"):
            self.assertFalse(logging.getLogger(name).isEnabledFor(logging.INFO))
        self.assertFalse(logging.getLogger("googleapiclient.http").isEnabledFor(logging.WARNING))
