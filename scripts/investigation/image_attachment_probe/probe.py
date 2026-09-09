"""Disposable attachment probe; no imports from the production application."""
import asyncio
import hashlib
import ipaddress
import secrets
import socket
import ssl
from io import BytesIO
from urllib.parse import urlsplit

import h11
from PIL import Image

MAX_BYTES = 2 * 1024 * 1024
MAX_PIXELS = 2_000_000
TIMEOUT = 15


class ProbeFailure(Exception):
    def __init__(self, status, **details):
        self.status, self.details = status, details


def classify(reference):
    if not reference:
        return {"status": "no_reference"}, None
    if len(reference) > 16384:
        raise ProbeFailure("limit_exceeded")
    if any(ord(c) < 33 or ord(c) > 126 for c in reference):
        raise ProbeFailure("unsupported_reference")
    try:
        parts = urlsplit(reference)
        if parts.scheme == "https" and parts.hostname:
            if parts.username or parts.password or parts.port not in (None, 443) or parts.fragment:
                raise ProbeFailure("unsupported_reference")
            return {"status": "reference_observed", "kind": "https_url",
                    "hostname": parts.hostname, "has_query": bool(parts.query)}, parts
    except ValueError:
        raise ProbeFailure("unsupported_reference") from None
    kind = "internal_reference" if parts.scheme or reference.startswith("/") else "opaque_reference"
    return {"status": "unsupported_reference", "kind": kind}, None


async def download(parts):
    """Resolve once and connect to a validated numeric address, retaining TLS SNI."""
    addresses = await asyncio.get_running_loop().getaddrinfo(
        parts.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ProbeFailure("host_not_allowed")
    address = addresses[0][4][0]
    reader, writer = await asyncio.open_connection(
        address, 443, ssl=ssl.create_default_context(), server_hostname=parts.hostname)
    try:
        conn = h11.Connection(h11.CLIENT, max_incomplete_event_size=16384)
        target = (parts.path or "/") + ("?" + parts.query if parts.query else "")
        writer.write(conn.send(h11.Request(method="GET", target=target, headers=[
            ("Host", parts.hostname), ("Accept", "image/png,image/jpeg,image/webp"),
            ("Accept-Encoding", "identity"), ("Connection", "close")])))
        writer.write(conn.send(h11.EndOfMessage()))
        await writer.drain()
        data = bytearray()
        while True:
            event = conn.next_event()
            if event is h11.NEED_DATA:
                chunk = await reader.read(16384)
                conn.receive_data(chunk)
            elif isinstance(event, h11.Response):
                status = event.status_code
                if 300 <= status < 400:
                    raise ProbeFailure("redirect_not_followed", http_status=status)
                if status != 200:
                    raise ProbeFailure("retrieval_denied" if status in (401, 403, 404)
                                       else "retrieval_failed", http_status=status)
                headers = dict(event.headers)
                if headers.get(b"content-encoding", b"identity") != b"identity":
                    raise ProbeFailure("not_supported_image")
                if int(headers.get(b"content-length", b"0")) > MAX_BYTES:
                    raise ProbeFailure("limit_exceeded")
            elif isinstance(event, h11.Data):
                data.extend(event.data)
                if len(data) > MAX_BYTES:
                    raise ProbeFailure("limit_exceeded")
            elif isinstance(event, h11.EndOfMessage):
                return bytes(data)
            elif isinstance(event, h11.ConnectionClosed):
                raise ProbeFailure("retrieval_failed")
    finally:
        writer.close()


def inspect_bytes(data):
    if len(data) > MAX_BYTES:
        raise ProbeFailure("limit_exceeded")
    try:
        with Image.open(BytesIO(data)) as source:
            if source.width * source.height > MAX_PIXELS:
                raise ProbeFailure("limit_exceeded")
            if source.format not in ("PNG", "JPEG", "WEBP") or getattr(source, "n_frames", 1) != 1:
                raise ProbeFailure("not_supported_image")
            rgb = source.convert("RGB")
            return {"status": "image_retrieved", "format": source.format,
                    "width": source.width, "height": source.height, "byte_count": len(data),
                    "sha256_bytes": hashlib.sha256(data).hexdigest(),
                    "sha256_rgb": hashlib.sha256(rgb.tobytes()).hexdigest()}
    except ProbeFailure:
        raise
    except Exception:
        raise ProbeFailure("not_supported_image") from None


async def inspect_reference(reference=None, *, allowed_host=None):
    probe_id = secrets.token_hex(12)
    try:
        result, parts = classify(reference)
        if parts and allowed_host:
            if parts.hostname != allowed_host:
                raise ProbeFailure("host_not_allowed")
            async with asyncio.timeout(TIMEOUT):
                data = await download(parts)
            result = inspect_bytes(data)
    except ProbeFailure as exc:
        result = {"status": exc.status, **exc.details}
    except Exception:
        result = {"status": "retrieval_failed"}
    return {"probe_id": probe_id, **result}
