import asyncio

import httpx
from starlette.applications import Starlette
from starlette.authentication import SimpleUser
from starlette.responses import JSONResponse
from starlette.routing import Route

from collective_intelligence_overlay.adapters.http_limits import BodyLimit, RequestCapacity


async def test_finite_caller_owner_capacity_and_retry_after():
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def app(scope, receive, send):
        calls.append(scope["user"].display_name)
        entered.set()
        await release.wait()
        await JSONResponse({"ok": True})(scope, receive, send)

    limit = RequestCapacity(app, owner_limit=2, caller_limit=1)

    async def request(caller):
        messages = []

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message):
            messages.append(message)

        await limit({"type": "http", "user": SimpleUser(caller)}, receive, send)
        return messages[0]

    first = asyncio.create_task(request("a"))
    await entered.wait()
    refused = await request("a")
    assert refused["status"] == 429 and (b"retry-after", b"1") in refused["headers"]
    entered.clear()
    second = asyncio.create_task(request("b"))
    await entered.wait()
    overloaded = await request("c")
    assert overloaded["status"] == 503 and len(calls) == 2
    second.cancel()
    try:
        await second
    except asyncio.CancelledError:
        pass
    assert limit.active == 1 and limit.callers == {"a": 1}
    release.set()
    assert (await first)["status"] == 200
    assert limit.active == 0 and limit.callers == {}


async def test_streaming_body_bound_and_receive_deadline():
    async def endpoint(request):
        return JSONResponse({"bytes": len(await request.body())})

    app = BodyLimit(Starlette(routes=[Route("/", endpoint, methods=["POST"])]), seconds=0.02)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:

        async def chunks(count, delayed=False):
            for _ in range(count):
                if delayed:
                    await asyncio.sleep(0.04)
                yield b"x" * 32768

        exact = await client.post("/", content=chunks(8))
        assert exact.status_code == 200 and exact.json()["bytes"] == 262144
        too_large = await client.post("/", content=chunks(9))
        assert too_large.status_code == 413
        stalled = await client.post("/", content=chunks(1, True))
        assert stalled.status_code == 408 and stalled.json()["error"] == "REQUEST_BODY_TIMEOUT"
