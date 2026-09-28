import asyncio

import httpx
import pytest

from collective_intelligence_overlay.adapters.http_limits import BoundedA2ATransport
from collective_intelligence_overlay.security import MAX_RECORD_BYTES


@pytest.mark.parametrize("mode", ["oversized", "compressed", "valid"])
async def test_a2a_transport_bounds_real_chunked_http_before_parsing(mode):
    requests = []

    async def serve(reader, writer):
        try:
            header = await reader.readuntil(b"\r\n\r\n")
            requests.append(header)
            encoding = b"Content-Encoding: gzip\r\n" if mode == "compressed" else b""
            writer.write(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n" + encoding + b"\r\n")
            count = MAX_RECORD_BYTES // 8192 + 1 if mode == "oversized" else 1
            for _ in range(count):
                payload = b"x" * 8192 if mode == "oversized" else b"{}"
                writer.write(f"{len(payload):x}\r\n".encode() + payload + b"\r\n")
                await writer.drain()
            writer.write(b"0\r\n\r\n")
            await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    endpoint = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
    async with server, httpx.AsyncClient(transport=BoundedA2ATransport(endpoint)) as client:
        with pytest.raises(ValueError, match="configured service boundary"):
            await client.get(endpoint + "/unregistered")
        assert not requests
        for method, url in (
            ("GET", endpoint + "/.well-known/agent-card.json"),
            ("POST", endpoint),
        ):
            if mode == "valid":
                assert (await client.request(method, url)).json() == {}
            else:
                with pytest.raises(ValueError, match="byte bound|compressed"):
                    await client.request(method, url)
    assert len(requests) == 2
    assert all(b"accept-encoding: identity" in header.lower() for header in requests)
