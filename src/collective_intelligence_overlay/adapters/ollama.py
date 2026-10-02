"""Explicit loopback connection using the public MAF/native Ollama integration."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from ipaddress import ip_address
from urllib.parse import urlsplit

import httpx
from agent_framework.ollama import OllamaChatClient
from ollama import AsyncClient


@asynccontextmanager
async def local_ollama_client(
    host: str,
    *,
    model: str,
    seconds: float = 300,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AsyncIterator[OllamaChatClient]:
    """Own and close the public HTTP transport; no retries or environment proxy.

    The operator must separately disable cloud on their server and pin its model
    digest. Loopback alone is not proof of local inference. This function neither
    starts a server nor discovers credentials, pulls weights or changes a model.
    Native options belong to the SDK's public get_response options dictionary.
    A supplied observation transport is also closed at context exit.
    """
    url = urlsplit(host)
    if (
        url.scheme != "http"
        or url.hostname is None
        or not ip_address(url.hostname).is_loopback
        or url.port is None
        or url.path not in {"", "/"}
        or url.username is not None
        or url.password is not None
        or url.query
        or url.fragment
        or not model
        or len(model) > 128
        or not 1 <= seconds <= 600
    ):
        raise ValueError("explicit loopback host, model and finite timeout required")
    owned = transport if transport is not None else httpx.AsyncHTTPTransport(retries=0)
    try:
        native = AsyncClient(
            host=host,
            transport=owned,
            timeout=httpx.Timeout(seconds, connect=5),
            trust_env=False,
            follow_redirects=False,
        )
        yield OllamaChatClient(host=host, model=model, client=native)
    finally:
        # Ollama 0.5.3 does not expose public AsyncClient.aclose. Owning its
        # injected public transport closes the connection pool without touching
        # client internals or patching an SDK method.
        await owned.aclose()
