import asyncio
import os
import secrets
import subprocess
import sys
from pathlib import Path

import httpx
import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from process_control import stop_owned_process

from collective_intelligence_overlay.adapters.mcp import invoke_registered
from collective_intelligence_overlay.bindings import (
    Binding,
    ExecutionContext,
    Registry,
    Target,
    fingerprint,
)
from collective_intelligence_overlay.demo import free_port
from collective_intelligence_overlay.models import Capability, Evidence, Subject


async def test_registered_mcp_uses_explicit_public_authenticated_client(
    overlay, records, identities
):
    port = free_port()
    endpoint = f"http://127.0.0.1:{port}/mcp"
    token = secrets.token_urlsafe(24)
    environment = {**os.environ, "CIO_TEST_MCP_TOKEN": token}
    process = await asyncio.to_thread(
        subprocess.Popen,
        [
            sys.executable,
            str(Path(__file__).with_name("authenticated_mcp_application.py")),
            "--port",
            str(port),
        ],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    clients = []

    def authenticated_client():
        client = httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
            follow_redirects=False,
            trust_env=False,
        )
        clients.append(client)
        return client

    try:
        async with httpx.AsyncClient() as public:
            for _ in range(200):
                try:
                    response = await public.get(endpoint)
                    assert response.status_code == 401
                    break
                except httpx.ConnectError:
                    if process.poll() is not None:
                        raise AssertionError("authenticated MCP process failed") from None
                    await asyncio.sleep(0.05)
            else:
                raise AssertionError("authenticated MCP did not start")
        async with authenticated_client() as http:
            async with Client(streamable_http_client(endpoint, http_client=http)) as client:
                tool = (await client.list_tools()).tools[0]
        original, checked = records
        binding = Binding(
            id="auth-mcp",
            revision="1",
            issuer="producer",
            registrar="receiver",
            subject=Subject(id="auth-csv", version="1", digest=fingerprint({"service": endpoint})),
            scope=original.scope,
            target=Target(
                kind="mcp",
                name=tool.name,
                endpoint=endpoint,
                interface_digest=fingerprint(
                    {"name": tool.name, "input": tool.input_schema, "output": tool.output_schema}
                ),
                implementation_identity="remote-unknown",
            ),
            input_schema=tool.input_schema,
            output_schema=tool.output_schema,
            callers=("receiver",),
            effects="read-only",
        )
        for template, model in ((original, Capability), (checked, Evidence)):
            record = model.model_validate(
                {
                    **template.model_dump(),
                    **({"id": "auth-mcp-check"} if model is Evidence else {}),
                    "schema_version": "2",
                    "subject": binding.subject,
                    "binding_digest": binding.digest,
                }
            )
            overlay.store.put(identities[record.issuer].sign(record))
        registry = Registry(overlay)
        registry.register_mcp(
            binding,
            lambda args: args["source"].startswith("category,amount\n"),
            local=True,
            http_client_factory=authenticated_client,
        )
        result = await registry.execute(
            binding.id,
            binding.digest,
            {"source": "category,amount\na,2.00\nb,3.00\n"},
            ExecutionContext(caller="receiver", environment=original.scope.environment),
        )
        assert result == {"rows": 2, "total": "5.00"}
        assert all(client.is_closed for client in clients)
        assert token not in binding.model_dump_json()
        # The default client has no authority; it cannot inherit an A2A token.
        with pytest.raises(ExceptionGroup):
            await invoke_registered(
                endpoint,
                tool.name,
                binding.target.interface_digest,
                {"source": "category,amount\na,2.00\n"},
            )
    finally:
        await asyncio.to_thread(stop_owned_process, process)
