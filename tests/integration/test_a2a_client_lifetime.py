"""Actual official SDK/ASGI exchange completes its iterator and owned client."""

import asyncio

import httpx
import pytest
from pydantic import SecretStr

from collective_intelligence_overlay.adapters import a2a, http_limits
from collective_intelligence_overlay.config import Config, Peer, TrustedIdentity


@pytest.mark.parametrize("fail", [False, True])
async def test_sdk_exchange_finalizes_request_and_client_before_return(
    identities, tmp_path, monkeypatch, fail
):
    identity = identities["producer"]
    endpoint = "http://127.0.0.1:1234/"
    config = Config(
        owner="producer",
        url=endpoint,
        local_development=True,
        database_url=SecretStr("unused"),
        private_key=tmp_path / "unused",
        artifact_directory=tmp_path,
        opa_binary="unused",
        peers=(Peer(identity="producer", url=endpoint),),
        identities={
            "producer": TrustedIdentity(
                keyid=identity.signer.public_key.keyid,
                key=identity.signer.public_key.to_dict(),
                trust_group="producer",
            )
        },
    )

    async def handler(caller, data):
        return {"caller": caller, "observed": data["operation"]}

    app = a2a.application(config, handler)
    monkeypatch.setattr(
        http_limits,
        "BoundedA2ATransport",
        lambda *args, **kwargs: httpx.ASGITransport(app=app),
    )
    create_client = a2a.create_client
    finalized, closed, owned_http = [], [], []

    async def instrumented_create(card, client_config):
        client = await create_client(card, client_config)
        send_message, close = client.send_message, client.close
        owned_http.append(client_config.httpx_client)

        async def observe_iterator(request):
            try:
                if fail:
                    raise RuntimeError("owned fixture failure after client construction")
                async for response in send_message(request):
                    yield response
            finally:
                finalized.append(True)

        async def observe_close():
            await close()
            closed.append(True)

        monkeypatch.setattr(client, "send_message", observe_iterator)
        monkeypatch.setattr(client, "close", observe_close)
        return client

    monkeypatch.setattr(a2a, "create_client", instrumented_create)
    if fail:
        with pytest.raises(RuntimeError, match="owned fixture failure"):
            await a2a.send(config, identity, "producer", {"operation": "observe"})
    else:
        result = await a2a.send(config, identity, "producer", {"operation": "observe"})
        assert result == {"caller": "producer", "observed": "observe"}
    # No intervening event-loop turn or collection hides a retained request frame.
    assert finalized == [True]
    assert closed == [True]
    assert len(owned_http) == 1 and owned_http[0].is_closed
    await asyncio.sleep(0)


async def test_message_only_exchange_leaves_no_sdk_physical_tasks(
    identities, tmp_path, monkeypatch
):
    """A completed Message reply cannot leave a producer waiting for another call."""
    identity = identities["producer"]
    endpoint = "http://127.0.0.1:1234/"
    config = Config(
        owner="producer",
        url=endpoint,
        local_development=True,
        database_url=SecretStr("unused"),
        private_key=tmp_path / "unused",
        artifact_directory=tmp_path,
        opa_binary="unused",
        peers=(Peer(identity="producer", url=endpoint),),
        identities={
            "producer": TrustedIdentity(
                keyid=identity.signer.public_key.keyid,
                key=identity.signer.public_key.to_dict(),
                trust_group="producer",
            )
        },
    )
    created = []
    constructor = a2a.LegacyRequestHandler

    def observe_handler(*args, **kwargs):
        handler = constructor(*args, **kwargs)
        created.append(handler)
        return handler

    monkeypatch.setattr(a2a, "LegacyRequestHandler", observe_handler)

    async def handler(caller, data):
        return {"caller": caller, "id": data["id"]}

    app = a2a.application(config, handler)
    monkeypatch.setattr(
        http_limits,
        "BoundedA2ATransport",
        lambda *args, **kwargs: httpx.ASGITransport(app=app),
    )
    baseline = asyncio.all_tasks()
    try:
        for index in range(6):
            assert await a2a.send(
                config, identity, "producer", {"operation": "observe", "id": index}
            ) == {"caller": "producer", "id": index}
        for _ in range(10):
            await asyncio.sleep(0)
        pending = asyncio.all_tasks() - baseline
        assert not pending, [(task.get_name(), str(task.get_coro())) for task in pending]
    finally:
        # This public method closes the original failing V2 diagnostic fixture.
        # It is not used to make the above no-work assertion pass.
        for request_handler in created:
            close = getattr(request_handler, "aclose", None)
            if close is not None:
                await close()
