"""Retrieve fresh Vibe image attachments without forwarding user credentials."""
import asyncio
import ipaddress
import os
import socket
import ssl
from io import BytesIO
from urllib.parse import urlsplit

import h11
from PIL import Image, ImageOps

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 20_000_000
DEFAULT_HOST = 'mistralaichatupprodswe.blob.core.windows.net'


class AttachmentError(ValueError):
    """Safe error that must never contain a signed URL or upstream response."""


def validate_url(url):
    try:
        if not isinstance(url, str) or not 1 <= len(url) <= 16384 or any(ord(c) < 33 or ord(c) > 126 for c in url):
            raise ValueError()
        parts = urlsplit(url)
        # Exact host only; do not allow all Azure tenants or follow redirects.
        host = os.getenv('VIBE_IMAGE_HOST', DEFAULT_HOST).strip().lower()
        if (not host or parts.scheme != 'https' or parts.hostname != host or parts.port not in (None, 443)
                or parts.username or parts.password or parts.fragment):
            raise ValueError()
        return parts
    except ValueError:
        raise AttachmentError('Use the exact HTTPS reference of a fresh Vibe image attachment. Public image URLs and local file paths are not supported.') from None


async def download(parts):
    addresses = await asyncio.get_running_loop().getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise AttachmentError('The attachment storage address is not permitted.')
    reader, writer = await asyncio.open_connection(addresses[0][4][0], 443,
        ssl=ssl.create_default_context(), server_hostname=parts.hostname)
    try:
        connection = h11.Connection(h11.CLIENT, max_incomplete_event_size=16384)
        target = (parts.path or '/') + ('?' + parts.query if parts.query else '')
        writer.write(connection.send(h11.Request(method='GET', target=target, headers=[
            ('Host', parts.hostname), ('Accept', 'image/png,image/jpeg,image/webp'),
            ('Accept-Encoding', 'identity'), ('Connection', 'close')])))
        writer.write(connection.send(h11.EndOfMessage()))
        await writer.drain()
        data = bytearray()
        while True:
            event = connection.next_event()
            if event is h11.NEED_DATA:
                connection.receive_data(await reader.read(16384))
            elif isinstance(event, h11.Response):
                if event.status_code != 200:
                    raise AttachmentError('The image could not be retrieved. Attach it again and retry with its fresh reference; no slide was changed.')
                headers = dict(event.headers)
                if headers.get(b'content-encoding', b'identity') != b'identity':
                    raise AttachmentError('Compressed HTTP image responses are unsupported. Attach the image again.')
                if int(headers.get(b'content-length', b'0')) > MAX_BYTES:
                    raise AttachmentError('Images must be at most 5 MiB.')
            elif isinstance(event, h11.Data):
                data.extend(event.data)
                if len(data) > MAX_BYTES:
                    raise AttachmentError('Images must be at most 5 MiB.')
            elif isinstance(event, h11.EndOfMessage):
                return bytes(data)
            elif isinstance(event, h11.ConnectionClosed):
                raise AttachmentError('The image download was incomplete. Attach it again.')
    finally:
        writer.close()


def normalize(data):
    try:
        if len(data) > MAX_BYTES:
            raise AttachmentError('Images must be at most 5 MiB.')
        with Image.open(BytesIO(data)) as source:
            if (source.format not in ('PNG', 'JPEG', 'WEBP') or source.width * source.height > MAX_PIXELS
                    or getattr(source, 'n_frames', 1) != 1):
                raise AttachmentError('Use a single-frame PNG, JPEG or WebP image up to 20 megapixels.')
            image = ImageOps.exif_transpose(source).convert('RGBA')
            image.thumbnail((1600, 1600))
            image.info.clear()
            output = BytesIO()
            image.save(output, format='PNG')
            if output.tell() > 10 * 1024 * 1024:
                raise AttachmentError('The normalized image is too large.')
            return output.getvalue(), image.size
    except AttachmentError:
        raise
    except Exception:
        raise AttachmentError('The attachment is not a supported image. Use PNG, JPEG or WebP.') from None


async def retrieve(url):
    parts = validate_url(url)
    try:
        async with asyncio.timeout(15):
            data = await download(parts)
        return await asyncio.to_thread(normalize, data)
    except AttachmentError:
        raise
    except Exception:
        raise AttachmentError('The image download could not be completed. Attach it again and retry; no slide was changed.') from None
