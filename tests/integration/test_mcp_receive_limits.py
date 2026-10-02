"""Real HTTP and official MCP client parser under malicious/slow server responses."""

import asyncio
import json
import time
from contextlib import asynccontextmanager

import httpx2
import pytest
import uvicorn
from mcp import MCPError
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from collective_intelligence_overlay.adapters.mcp import (
    MCPReceiveLimit,
    ReceiveLimits,
    invoke_registered,
)
from collective_intelligence_overlay.bindings import fingerprint
from collective_intelligence_overlay.demo import free_port

TOOL = {"name": "bounded", "inputSchema": {"type": "object"}, "outputSchema": {"type": "object"}}
INTERFACE = fingerprint(
    {"name": TOOL["name"], "input": TOOL["inputSchema"], "output": TOOL["outputSchema"]}
)


@asynccontextmanager
async def server(mode):
    observed = {"stream_chunks": 0, "stream_closed": False, "redirect_followed": 0, "methods": []}
    started = asyncio.Event()

    async def chunks(payload, *, slow=False):
        started.set()
        try:
            size = 1 if slow else 4096
            for offset in range(0, len(payload), size):
                if slow:
                    await asyncio.sleep(0.05)
                observed["stream_chunks"] += 1
                yield payload[offset : offset + size]
                await asyncio.sleep(0)
        finally:
            observed["stream_closed"] = True

    async def handle(request):
        if request.url.path == "/other":
            observed["redirect_followed"] += 1
        if request.method == "GET":
            return Response(status_code=405)
        if request.method == "DELETE":
            return Response(status_code=204)
        data = await request.json()
        method = data["method"]
        observed["methods"].append(method)
        if "id" not in data:
            return Response(status_code=202)
        if mode == "redirect":
            return Response(status_code=307, headers={"Location": "/other"})
        if method == "initialize":
            result = {
                "protocolVersion": data["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "finite-protocol-fixture", "version": "1"},
            }
        elif method == "tools/list":
            result = {"tools": [TOOL]}
            if mode == "tool-count":
                result = {"tools": [{**TOOL, "name": f"tool-{i}"} for i in range(200)]}
        elif method == "tools/call":
            result = {"content": [], "structuredContent": {"value": 1}, "isError": False}
            message = {"jsonrpc": "2.0", "id": data["id"], "result": result}
            if mode in {"json-bytes", "chunked-json", "sse-bytes", "slow", "cancel"}:
                result["structuredContent"]["padding"] = "x" * (2 * 1024 * 1024)
                payload = json.dumps(message).encode()
                if mode == "json-bytes":
                    return Response(payload, media_type="application/json")
                if mode == "sse-bytes":
                    return StreamingResponse(
                        chunks(b"data: " + payload + b"\n\n"), media_type="text/event-stream"
                    )
                return StreamingResponse(
                    chunks(payload, slow=mode in {"slow", "cancel"}), media_type="application/json"
                )
            if mode == "depth":
                payload = (
                    '{"jsonrpc":"2.0","id":'
                    + json.dumps(data["id"])
                    + ',"result":{"content":[],"structuredContent":{"deep":'
                    + "[" * 80
                    + "0"
                    + "]" * 80
                    + '},"isError":false}}'
                ).encode()
                return StreamingResponse(chunks(payload), media_type="application/json")
            if mode == "sse-depth":
                payload = (
                    '{"jsonrpc":"2.0","id":'
                    + json.dumps(data["id"])
                    + ',"result":{"content":[],"structuredContent":{"deep":'
                    + "[" * 80
                    + "0"
                    + "]" * 80
                    + '},"isError":false}}'
                ).encode()
                return StreamingResponse(
                    chunks(b'\xef\xbb\xbf: " } ] comment\ndata: ' + payload + b"\n\n"),
                    media_type="text/event-stream",
                )
            if mode == "string-sse":
                result["structuredContent"]["literal"] = '["\\]{' * 2000
                return StreamingResponse(
                    chunks(b': " } ] comment\ndata: ' + json.dumps(message).encode() + b"\n\n"),
                    media_type="text/event-stream",
                )
            if mode == "compression":
                return Response(
                    b"deliberately unparsed",
                    media_type="application/json",
                    headers={"Content-Encoding": "gzip"},
                )
        else:
            return Response(status_code=202)
        return JSONResponse({"jsonrpc": "2.0", "id": data["id"], "result": result})

    port = free_port()
    app = Starlette(
        routes=[
            Route("/mcp", handle, methods=["GET", "POST", "DELETE"]),
            Route("/other", handle, methods=["POST"]),
        ]
    )
    running = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="critical", access_log=False)
    )
    task = asyncio.create_task(running.serve())
    try:
        async with httpx2.AsyncClient(trust_env=False) as http:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    await http.get(f"http://127.0.0.1:{port}/mcp")
                    break
                except httpx2.ConnectError:
                    await asyncio.sleep(0.02)
            else:
                raise AssertionError("fixture did not start")
        yield f"http://127.0.0.1:{port}/mcp", observed, started
    finally:
        running.should_exit = True
        await asyncio.wait_for(task, 10)


def messages(error):
    if isinstance(error, BaseExceptionGroup):
        return " ".join(messages(child) for child in error.exceptions)
    return str(error)


@pytest.mark.parametrize(
    "mode, reason",
    [
        ("json-bytes", "BYTES"),
        ("chunked-json", "BYTES"),
        ("sse-bytes", "BYTES"),
        ("depth", "DEPTH"),
        ("sse-depth", "DEPTH"),
        ("tool-count", "TOOL_COUNT"),
        ("compression", "COMPRESSED"),
        ("redirect", "REDIRECT"),
    ],
)
async def test_official_sdk_rejects_bounded_receive_before_unlimited_decode(
    mode, reason, monkeypatch
):
    import mcp.client.streamable_http as sdk

    parsed_sizes = []
    original = sdk.jsonrpc_message_adapter.validate_json

    def observe_parse(payload, *args, **kwargs):
        parsed_sizes.append(len(payload))
        return original(payload, *args, **kwargs)  # The actual SDK/Pydantic parser.

    monkeypatch.setattr(sdk.jsonrpc_message_adapter, "validate_json", observe_parse)
    clients = []

    def factory():
        client = httpx2.AsyncClient(timeout=2, follow_redirects=False, trust_env=False)
        clients.append(client)
        return client

    async with server(mode) as (endpoint, observed, _):
        with pytest.raises((MCPError, MCPReceiveLimit, ValueError, ExceptionGroup)) as caught:
            await invoke_registered(
                endpoint,
                "bounded",
                INTERFACE,
                {},
                http_client_factory=factory,
                receive_limits=ReceiveLimits(bytes=32768, seconds=2),
            )
        assert reason in messages(caught.value)
        assert all(size <= 32768 for size in parsed_sizes)
        assert observed["redirect_followed"] == 0
        if mode in {"chunked-json", "sse-bytes", "depth", "sse-depth"}:
            assert observed["stream_closed"]
        assert all(client.is_closed for client in clients)


async def test_slow_chunks_have_total_deadline_and_close_stream():
    async with server("slow") as (endpoint, observed, _):
        started = time.monotonic()
        with pytest.raises((TimeoutError, MCPError, ExceptionGroup)):
            await invoke_registered(
                endpoint, "bounded", INTERFACE, {}, receive_limits=ReceiveLimits(seconds=0.4)
            )
        assert time.monotonic() - started < 2
        assert observed["stream_chunks"] < 10 and observed["stream_closed"]


async def test_early_cancel_closes_real_slow_stream_without_tool_retry():
    async with server("cancel") as (endpoint, observed, started):
        task = asyncio.create_task(
            invoke_registered(
                endpoint, "bounded", INTERFACE, {}, receive_limits=ReceiveLimits(seconds=2)
            )
        )
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert observed["methods"].count("tools/call") == 1
        assert observed["stream_closed"]


async def test_normal_official_protocol_remains_valid():
    async with server("normal") as (endpoint, _, _):
        assert await invoke_registered(endpoint, "bounded", INTERFACE, {}) == {"value": 1}


async def test_sse_comments_and_brackets_inside_chunked_strings_remain_valid():
    async with server("string-sse") as (endpoint, _, _):
        result = await invoke_registered(endpoint, "bounded", INTERFACE, {})
        assert result == {"value": 1, "literal": '["\\]{' * 2000}


async def test_current_sdk_json_decode_has_no_small_pre_receive_byte_bound(monkeypatch):
    import mcp.client.streamable_http as sdk
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client

    sizes = []
    original = sdk.jsonrpc_message_adapter.validate_json

    def observe_parse(payload, *args, **kwargs):
        sizes.append(len(payload))
        return original(payload, *args, **kwargs)

    monkeypatch.setattr(sdk.jsonrpc_message_adapter, "validate_json", observe_parse)
    # Bounded 2 MiB test payload: inspect the actual SDK, without our hook.
    async with server("json-bytes") as (endpoint, _, _):
        async with httpx2.AsyncClient(timeout=2, trust_env=False) as http:
            async with Client(streamable_http_client(endpoint, http_client=http)) as client:
                result = await client.call_tool("bounded", {})
                assert len(result.structured_content["padding"]) == 2 * 1024 * 1024
    assert max(sizes) > 2 * 1024 * 1024
