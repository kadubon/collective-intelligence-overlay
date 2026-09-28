import asyncio
import sys

import httpx
import pytest
from agent_framework import (
    Agent,
    BaseChatClient,
    ChatResponse,
    Content,
    FunctionInvocationLayer,
    Message,
    MiddlewareFailure,
    tool,
)

from collective_intelligence_overlay.adapters.maf import AdmissionMiddleware
from collective_intelligence_overlay.adapters.mcp import call_tool
from collective_intelligence_overlay.demo import free_port
from collective_intelligence_overlay.models import UseRequest


class DeterministicClient(FunctionInvocationLayer, BaseChatClient):
    async def _inner_get_response(self, *, messages, stream, options, **kwargs):
        if any(m.role == "tool" for m in messages):
            return ChatResponse(messages=Message("assistant", ["completed"]))
        return ChatResponse(
            messages=Message(
                "assistant",
                [Content.from_function_call(call_id="check-1", name="approved", arguments={})],
            )
        )


async def test_actual_maf_agent_tool_middleware(overlay, records):
    called = []

    @tool
    def approved() -> str:
        """A configured local tool."""
        called.append(True)
        return "ok"

    cap = records[0]
    req = UseRequest(
        receiver="receiver", subject=cap.subject, scope=cap.scope, semantic_fit="confirmed"
    )
    agent = Agent(
        client=DeterministicClient(),
        tools=[approved],
        middleware=[AdmissionMiddleware(overlay, {"approved": req})],
    )
    result = await agent.run("invoke the registered tool")
    assert called == [True]
    assert result.text == "completed"
    called.clear()
    denied = Agent(
        client=DeterministicClient(),
        tools=[approved],
        middleware=[AdmissionMiddleware(overlay, {})],
    )
    with pytest.raises(MiddlewareFailure):
        await denied.run("invoke the tool")
    assert not called


async def test_actual_mcp_http(overlay, records):
    port = free_port()
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "collective_intelligence_overlay.reference_mcp",
        "--port",
        str(port),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    endpoint = f"http://127.0.0.1:{port}/mcp"
    try:
        async with httpx.AsyncClient() as client:
            for _ in range(60):
                if process.returncode is not None:
                    raise RuntimeError((await process.stderr.read()).decode())
                try:
                    await client.get(endpoint)
                    break
                except httpx.ConnectError:
                    await asyncio.sleep(0.1)
        cap = records[0]
        req = UseRequest(
            receiver="receiver", subject=cap.subject, scope=cap.scope, semantic_fit="confirmed"
        )
        result = await call_tool(
            overlay,
            req,
            endpoint,
            "csv_sum",
            {"source": "category,amount\na,1.25\nb,2.75\n"},
            endpoints=frozenset({endpoint}),
            tools=frozenset({"csv_sum"}),
            local=True,
        )
        assert result == {"rows": 2, "total": "4.00"}
        with pytest.raises(ValueError, match="not authorized"):
            await call_tool(
                overlay,
                req,
                endpoint,
                "delete",
                {},
                endpoints=frozenset({endpoint}),
                tools=frozenset({"csv_sum"}),
                local=True,
            )
    finally:
        if process.returncode is None:
            process.terminate()
        await asyncio.wait_for(process.wait(), 10)
