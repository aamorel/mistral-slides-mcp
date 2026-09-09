"""Production attachment fetch is bounded and never forwards credentials."""
import asyncio
import socket
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_slides import attachments

URL = 'https://' + attachments.DEFAULT_HOST + '/image?sig=PRIVATE_SIGNATURE'


class AttachmentTests(unittest.IsolatedAsyncioTestCase):
    async def transport(self, response, ip='8.8.8.8'):
        reader = asyncio.StreamReader()
        reader.feed_data(response)
        reader.feed_eof()
        writer = MagicMock()
        writer.drain = AsyncMock()
        resolver = AsyncMock(return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443))])
        connect = AsyncMock(return_value=(reader, writer))
        with patch.object(asyncio.get_running_loop(), 'getaddrinfo', resolver), patch.object(asyncio, 'open_connection', connect):
            try:
                data = await attachments.download(attachments.validate_url(URL))
                return data, connect, writer
            except attachments.AttachmentError as exc:
                return exc, connect, writer

    async def test_exact_host_scheme_and_no_userinfo(self):
        for url in (URL.replace('https:', 'http:'), URL.replace(attachments.DEFAULT_HOST, 'attacker.example'),
                    URL.replace('/image', ':444/image'), URL.replace('https://', 'https://user:secret@'),
                    URL + '#fragment', URL + '\r\nHeader: injected', 'file:///etc/passwd'):
            with patch.object(attachments, 'download', new_callable=AsyncMock) as fetch:
                with self.assertRaises(attachments.AttachmentError):
                    await attachments.retrieve(url)
                fetch.assert_not_awaited()

    async def test_resolves_once_pins_public_ip_and_keeps_tls_hostname(self):
        data, connect, writer = await self.transport(b'HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nabc')
        self.assertEqual(data, b'abc')
        self.assertEqual(connect.call_args.args, ('8.8.8.8', 443))
        self.assertEqual(connect.call_args.kwargs['server_hostname'], attachments.DEFAULT_HOST)
        request = b''.join(call.args[0] for call in writer.write.call_args_list)
        self.assertIn(b'?sig=PRIVATE_SIGNATURE', request)
        self.assertNotIn(b'Authorization', request)
        self.assertNotIn(b'Cookie', request)
        writer.close.assert_called_once()

    async def test_private_addresses_redirects_and_oversize_stream_rejected(self):
        for ip in ('127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', '::ffff:127.0.0.1'):
            result, connect, _ = await self.transport(b'', ip)
            self.assertIsInstance(result, attachments.AttachmentError)
            connect.assert_not_awaited()
        for response in (
            b'HTTP/1.1 302 Found\r\nLocation: https://evil.example/PRIVATE_SIGNATURE\r\nContent-Length: 0\r\n\r\n',
            b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n',
            b'HTTP/1.1 200 OK\r\nContent-Length: 99999999\r\n\r\n',
            b'HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n' + b'x' * (attachments.MAX_BYTES + 1),
            b'HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: 0\r\n\r\n'):
            result, connect, _ = await self.transport(response)
            self.assertIsInstance(result, attachments.AttachmentError)
            self.assertNotIn('PRIVATE_SIGNATURE', str(result))
            self.assertEqual(connect.await_count, 1)

    async def test_upstream_exception_is_safe(self):
        with patch.object(attachments, 'download', side_effect=TimeoutError('PRIVATE_SIGNATURE')):
            with self.assertRaises(attachments.AttachmentError) as caught:
                await attachments.retrieve(URL)
        self.assertNotIn('PRIVATE_SIGNATURE', str(caught.exception))
        self.assertIn('Attach it again', str(caught.exception))
