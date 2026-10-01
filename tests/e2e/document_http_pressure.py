"""Real TLS authenticated body pressure, retaining the predeclared 16/4 limits."""

import asyncio
import json
from datetime import timedelta
from urllib.parse import urlsplit

import httpx
import jwt
from document_recovery_protocol import originals

from collective_intelligence_overlay.models import now


async def run(configs, identities, mesh, root):
    config = configs["producer"]
    assert config.max_owner_requests == 16 and config.max_caller_requests == 4
    destination = urlsplit(config.url)
    callers = {**identities, **mesh.http_clients}

    def token(name):
        identity = callers[name]
        timestamp = now()
        return jwt.encode(
            {
                "iss": name,
                "sub": name,
                "aud": config.url,
                "iat": timestamp,
                "exp": timestamp + timedelta(seconds=60),
            },
            identity.signer.private_bytes,
            algorithm="EdDSA",
            headers={"kid": identity.signer.public_key.keyid},
        )

    async def response(reader):
        headers = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
        lines = headers.decode("ascii").split("\r\n")
        return int(lines[0].split()[1]), {
            name.lower(): value.strip()
            for line in lines[1:]
            if ":" in line
            for name, value in [line.split(":", 1)]
        }

    before = await asyncio.to_thread(originals, config)
    effects = mesh.mcp_audit.read_bytes()
    sockets = []
    try:
        for name in ("producer", "receiver", "verifier", "capacity-client"):
            for _ in range(4):
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(
                        destination.hostname,
                        destination.port,
                        ssl=config.tls_context(),
                        server_hostname=destination.hostname,
                    ),
                    5,
                )
                sockets.append((reader, writer))
                writer.write(
                    (
                        f"POST / HTTP/1.1\r\nHost: {destination.netloc}\r\n"
                        f"Authorization: Bearer {token(name)}\r\n"
                        "Content-Type: application/json\r\n"
                        "Content-Length: 2\r\nConnection: close\r\n\r\n "
                    ).encode("ascii")
                )
                await writer.drain()
        # Keep the body incomplete through the actual proxy and authenticated
        # ASGI bounds. Additional requests must be refused before parsing/dispatch.
        async with httpx.AsyncClient(
            verify=config.tls_context(), trust_env=False, timeout=5
        ) as client:
            observations = []
            for caller, status in (("capacity-observer", 503), ("producer", 429)):
                value = await client.get(
                    config.url + ".well-known/agent-card.json",
                    headers={"Authorization": "Bearer " + token(caller)},
                )
                assert value.status_code == status and value.headers.get("Retry-After") == "1", {
                    "caller": caller,
                    "expected": status,
                    "observed": value.status_code,
                    "retry_after": value.headers.get("Retry-After"),
                }
                observations.append({"caller": caller, "status": status, "retry_after": "1"})
            # A complete invalid JSON body creates no SDK message or invocation.
            for _, writer in sockets:
                writer.write(b" ")
                await writer.drain()
            for reader, _ in sockets:
                status, headers = await response(reader)
                assert status == 200
                size = int(headers["content-length"])
                assert 0 < size <= 4096
                error = json.loads(await asyncio.wait_for(reader.readexactly(size), 5))
                assert error["error"]["code"] == -32700 and "result" not in error
            repaired = await client.get(
                config.url + ".well-known/agent-card.json",
                headers={"Authorization": "Bearer " + token("producer")},
            )
            assert repaired.status_code == 200
        assert await asyncio.to_thread(originals, config) == before
        assert mesh.mcp_audit.read_bytes() == effects
        (root / "http-pressure-observations.json").write_text(
            json.dumps(
                {
                    "injection": "HTTP 429 and 503 with Retry-After",
                    "owner_limit": 16,
                    "caller_limit": 4,
                    "incomplete_authenticated_bodies": 16,
                    "observations": observations,
                    "invalid_bodies_refused": 16,
                    "capacity_released_response": 200,
                    "new_effects": 0,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    finally:
        for _, writer in sockets:
            writer.close()
        for _, writer in sockets:
            try:
                await asyncio.wait_for(writer.wait_closed(), 5)
            except (OSError, TimeoutError):
                pass
