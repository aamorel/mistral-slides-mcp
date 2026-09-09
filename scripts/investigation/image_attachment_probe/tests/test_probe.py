import asyncio
import hashlib
import json
import logging
import os
import socket
import unittest
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import httpx2
import uvicorn
from PIL import Image
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from scripts.investigation.image_attachment_probe import probe, server


def png(size=(7, 5)):
    output = BytesIO()
    Image.new("RGB", size, "orange").save(output, format="PNG")
    return output.getvalue()


class ProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_classification_never_fetches_or_echoes_secret(self):
        with patch.object(probe, "download", new_callable=AsyncMock) as fetch:
            result = await probe.inspect_reference("https://files.example.com/private?sig=SENTINEL")
            self.assertEqual(result["status"], "reference_observed")
            self.assertEqual(result["hostname"], "files.example.com")
            fetch.assert_not_called()
            self.assertNotIn("SENTINEL", json.dumps(result))
            self.assertNotIn("private", json.dumps(result))
        self.assertEqual((await probe.inspect_reference())["status"], "no_reference")
        self.assertEqual((await probe.inspect_reference("file-123"))["kind"], "opaque_reference")

    async def test_rejects_bad_urls_hosts_and_oversized_references(self):
        for value in ("http://files.example.com/a", "https://user:secret@files.example.com/a",
                      "https://files.example.com:444/a", "https://files.example.com/a\r\nX:bad",
                      "data:image/png;base64,abc", "https://files.example.com/a#secret"):
            self.assertEqual((await probe.inspect_reference(value))["status"], "unsupported_reference")
        self.assertEqual((await probe.inspect_reference("x" * 16385))["status"], "limit_exceeded")
        with patch.object(probe, "download", new_callable=AsyncMock) as fetch:
            result = await probe.inspect_reference("https://evil.example.com/a", allowed_host="files.example.com")
            self.assertEqual(result["status"], "host_not_allowed")
            fetch.assert_not_called()

    async def test_hashes_match_independent_computation(self):
        data = png()
        with patch.object(probe, "download", new_callable=AsyncMock, return_value=data):
            result = await probe.inspect_reference("https://files.example.com/a", allowed_host="files.example.com")
        self.assertEqual(result["status"], "image_retrieved")
        self.assertEqual((result["width"], result["height"]), (7, 5))
        self.assertEqual(result["sha256_bytes"], hashlib.sha256(data).hexdigest())
        self.assertEqual(result["sha256_rgb"], hashlib.sha256(bytes((255, 165, 0)) * 35).hexdigest())

    async def test_limits_and_safe_failures(self):
        for data, status in ((b"not-image", "not_supported_image"),
                             (b"x" * (probe.MAX_BYTES + 1), "limit_exceeded"),
                             (png((2001, 1000)), "limit_exceeded")):
            with patch.object(probe, "download", new_callable=AsyncMock, return_value=data):
                result = await probe.inspect_reference("https://files.example.com/a", allowed_host="files.example.com")
                self.assertEqual(result["status"], status)
        with patch.object(probe, "download", new_callable=AsyncMock, side_effect=RuntimeError("SENTINEL")):
            result = await probe.inspect_reference("https://files.example.com/a", allowed_host="files.example.com")
            self.assertEqual(result["status"], "retrieval_failed")
            self.assertNotIn("SENTINEL", json.dumps(result))
        async def slow(*args):
            await asyncio.sleep(1)
        with patch.object(probe, "TIMEOUT", .01), patch.object(probe, "download", slow):
            self.assertEqual((await probe.inspect_reference("https://files.example.com/a",
                allowed_host="files.example.com"))["status"], "retrieval_failed")

    async def transport(self, response, ip="8.8.8.8"):
        reader = asyncio.StreamReader()
        reader.feed_data(response)
        reader.feed_eof()
        writer = MagicMock()
        writer.drain = AsyncMock()
        resolver = AsyncMock(return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))])
        connect = AsyncMock(return_value=(reader, writer))
        with patch.object(asyncio.get_running_loop(), "getaddrinfo", resolver), patch.object(asyncio, "open_connection", connect):
            result = await probe.inspect_reference("https://files.example.com/image?sig=SENTINEL", allowed_host="files.example.com")
        return result, connect, writer

    async def test_pinned_connection_keeps_tls_name_and_sends_no_credentials(self):
        data = png()
        result, connect, writer = await self.transport(b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(data)).encode() + b"\r\n\r\n" + data)
        self.assertEqual(result["status"], "image_retrieved")
        self.assertEqual(connect.call_args.args, ("8.8.8.8", 443))
        self.assertEqual(connect.call_args.kwargs["server_hostname"], "files.example.com")
        request = b"".join(call.args[0] for call in writer.write.call_args_list)
        self.assertIn(b"Host: files.example.com", request)
        self.assertNotIn(b"Authorization", request)
        self.assertNotIn(b"Cookie", request)
        writer.close.assert_called_once()

    async def test_private_addresses_redirects_denials_and_stream_limit(self):
        for ip in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "::ffff:127.0.0.1"):
            result, connect, _ = await self.transport(b"", ip)
            self.assertEqual(result["status"], "host_not_allowed")
            connect.assert_not_called()
        for response, status in (
            (b"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1/secret\r\nContent-Length: 0\r\n\r\n", "redirect_not_followed"),
            (b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n", "retrieval_denied"),
            (b"HTTP/1.1 200 OK\r\nContent-Length: 9999999\r\n\r\n", "limit_exceeded"),
            (b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n" + b"x" * (probe.MAX_BYTES + 1), "limit_exceeded")):
            result, connect, _ = await self.transport(response)
            self.assertEqual(result["status"], status)
            self.assertEqual(connect.await_count, 1)
            self.assertNotIn("SENTINEL", json.dumps(result))


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_http_auth_discovery_and_null_invocation(self):
        old_disable = logging.root.manager.disable
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        with patch.dict(os.environ, {"PROBE_BEARER_TOKEN": "test-secret-" * 4, "PROBE_ALLOWED_HOST": "", "HOST": "127.0.0.1"}):
            app = server.create_app()
        instance = uvicorn.Server(uvicorn.Config(app, access_log=False, log_level="critical"))
        task = asyncio.create_task(instance.serve(sockets=[sock]))
        try:
            for _ in range(100):
                if instance.started:
                    break
                await asyncio.sleep(.02)
            self.assertTrue(instance.started)
            async with httpx2.AsyncClient() as http:
                self.assertEqual((await http.get(f"http://127.0.0.1:{port}/health")).status_code, 200)
                self.assertEqual((await http.post(f"http://127.0.0.1:{port}/mcp", json={})).status_code, 401)
            async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + "test-secret-" * 4}) as http:
                async with Client(streamable_http_client(f"http://127.0.0.1:{port}/mcp", http_client=http)) as client:
                    listed = await client.list_tools()
                    self.assertEqual([t.name for t in listed.tools], ["inspect_attached_image"])
                    result = await client.call_tool("inspect_attached_image", {"image_reference": None})
                    self.assertFalse(result.is_error)
                    self.assertEqual(result.structured_content["status"], "no_reference")
        finally:
            instance.should_exit = True
            await task
            logging.disable(old_disable)

    def test_missing_secret_fails_closed(self):
        with patch.dict(os.environ, {"PROBE_BEARER_TOKEN": ""}):
            with self.assertRaises(ValueError):
                server.create_app()
