import asyncio

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from collective_intelligence_overlay.adapters.http_limits import BoundedA2ATransport
from collective_intelligence_overlay.demo import free_port


async def test_real_http_readonly_429_503_retry_preserves_request_effect_never_retried():
    received = []

    async def endpoint(request):
        received.append((request.method, await request.body()))
        if len(received) <= 2:
            return JSONResponse(
                {"error": "temporarily unavailable"},
                status_code=429 if len(received) == 1 else 503,
                headers={"Retry-After": "0"},
            )
        return JSONResponse({"result": "observed"})

    port = free_port()
    started = asyncio.Event()
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(_):
        started.set()
        yield

    app = Starlette(routes=[Route("/", endpoint, methods=["POST"])], lifespan=lifespan)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="critical"))
    task = asyncio.create_task(server.serve())
    url = f"http://127.0.0.1:{port}/"
    try:
        await asyncio.wait_for(started.wait(), 5)
        # Lifespan completion precedes the listener binding by one event-loop turn.
        await asyncio.sleep(0.02)
        async with httpx.AsyncClient(
            transport=BoundedA2ATransport(url, readonly_post=True)
        ) as client:
            body = b'{"operation":"invocation","invocation_id":"original-id"}'
            response = await client.post(url, content=body)
            assert response.status_code == 200 and received == [("POST", body)] * 3
        received.clear()
        async with httpx.AsyncClient(transport=BoundedA2ATransport(url)) as client:
            body = b'{"operation":"invoke","invocation_id":"original-id"}'
            response = await client.post(url, content=body)
            assert response.status_code == 429 and received == [("POST", body)]
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 5)
