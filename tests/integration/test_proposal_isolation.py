"""Uncooperative, authenticated peers through actual A2A HTTP and PostgreSQL."""

import asyncio
import base64
from urllib.parse import urlsplit

import pytest
import uvicorn
from pydantic import SecretStr
from starlette.responses import JSONResponse, Response
from test_opportunities import configured_steps

from collective_intelligence_overlay.adapters.a2a import application
from collective_intelligence_overlay.config import Config, Peer, TrustedIdentity
from collective_intelligence_overlay.demo import free_port
from collective_intelligence_overlay.models import Event
from collective_intelligence_overlay.proposal_exchange import collect
from collective_intelligence_overlay.queries import RecordQuery
from collective_intelligence_overlay.security import verify


def configured_http_peers(tmp_path, identities):
    peers = tuple(
        Peer(identity=name, url=f"http://127.0.0.1:{free_port()}/") for name in identities
    )
    trusted = {
        name: TrustedIdentity(
            keyid=identity.signer.public_key.keyid,
            key=identity.signer.public_key.to_dict(),
            trust_group=name,
            methods=("csv-check",),
        )
        for name, identity in identities.items()
    }
    return {
        name: Config(
            owner=name,
            database_url=SecretStr("unused"),
            private_key=tmp_path / "unused",
            artifact_directory=tmp_path,
            opa_binary="unused",
            url=next(p.url for p in peers if p.identity == name),
            peers=peers,
            identities=trusted,
            local_development=True,
        )
        for name in identities
    }


@pytest.mark.parametrize(
    "mode",
    [
        "normal",
        "mixed",
        "reverse",
        "malformed",
        "oversized",
        "rpc_structure",
        "rpc_json",
        "card_structure",
        "allbad",
        "unavailable",
    ],
)
async def test_cio_030_02_hostile_http_reply_preserves_valid_siblings_and_peers(
    overlay, identities, records, tmp_path, mode
):
    steps, opportunity, valid = await configured_steps(overlay, identities, records)
    goal = steps.opportunities.goal(opportunity.goal_id)
    config = configured_http_peers(tmp_path, identities)
    original = verify(valid[0][1], overlay.store.principals)
    bad = original.model_copy(
        update={
            "id": "unapproved",
            "builder": original.builder.model_copy(update={"id": "not-installed"}),
        }
    )
    bad_signature = identities["producer"].sign(original.model_copy(update={"id": "bad-signature"}))
    bad_signature["signatures"][0]["sig"] = base64.b64encode(b"x" * 64).decode()
    other = original.model_copy(
        update={"id": "other-valid", "issuer": "other", "arguments": {"value": 5}}
    )
    replies = {"producer": [valid[0][1]], "other": [identities["other"].sign(other)]}
    if mode in {"mixed", "reverse"}:
        replies["producer"] = [identities["producer"].sign(bad), bad_signature, valid[0][1]]
        if mode == "reverse":
            replies["producer"].reverse()
    if mode == "malformed":
        replies["other"] = "not-a-container"
    if mode == "oversized":
        replies["other"] *= 9
    if mode == "allbad":
        replies["producer"] = [identities["producer"].sign(bad), bad_signature]
        wrong_reference = other.model_copy(
            update={
                "opportunity": other.opportunity.model_copy(update={"payload_digest": "f" * 64})
            }
        )
        replies["other"] = [identities["other"].sign(wrong_reference)]
    servers, serving = [], []
    try:
        for name in goal.peers:

            async def handler(caller, data, peer=name):
                assert caller == "receiver" and data["operation"] == "propose"
                observed = verify(data["envelope"], overlay.store.principals)
                assert observed.id == opportunity.id and observed.issuer == caller
                if mode == "unavailable":
                    raise ValueError("remote peer temporarily unavailable")
                return {"proposals": replies[peer]}

            app = application(config[name], handler)

            async def hostile_wire(scope, receive, send, peer=name, standard=app):
                if peer == "other" and scope["type"] == "http":
                    if mode == "card_structure" and scope["method"] == "GET":
                        await JSONResponse({"skills": [0]})(scope, receive, send)
                        return
                    if scope["method"] == "POST":
                        if mode == "rpc_structure":
                            await JSONResponse({"jsonrpc": "2.0", "result": [0]})(
                                scope, receive, send
                            )
                            return
                        if mode == "rpc_json":
                            await Response(b"not JSON", media_type="application/json")(
                                scope, receive, send
                            )
                            return
                await standard(scope, receive, send)

            server = uvicorn.Server(
                uvicorn.Config(
                    hostile_wire,
                    host="127.0.0.1",
                    port=urlsplit(config[name].url).port,
                    log_level="critical",
                    access_log=False,
                )
            )
            servers.append(server)
            serving.append(asyncio.create_task(server.serve()))
        for _ in range(100):
            if all(server.started for server in servers):
                break
            await asyncio.sleep(0.05)
        assert all(server.started for server in servers)
        collected = await collect(
            config["receiver"], overlay.store, identities["receiver"], goal, opportunity.id
        )
        result = await steps.step(opportunity.id, collected)
        if mode == "allbad":
            assert result.reason == "no_valid_alternatives" and result.invocation is None
            assert {r.category for r in result.rejections} == {
                "authentication",
                "authorization",
                "reference",
            }
        elif mode == "unavailable":
            assert result.reason == "peers_unavailable" and result.invocation is None
            assert result.unavailable == goal.peers and not result.rejections
        else:
            assert result.invocation["state"] == "completed"
            expected = (
                3
                if mode in {"malformed", "oversized", "rpc_structure", "rpc_json", "card_structure"}
                else 5
            )
            assert result.invocation["result"] == {"value": expected}
            assert result.selection.proposal.issuer == ("producer" if expected == 3 else "other")
            assert not collected.unavailable
            if mode in {"mixed", "reverse"}:
                assert {r.category for r in result.rejections} == {
                    "authentication",
                    "authorization",
                }
            if expected == 3:
                assert [r.category for r in result.rejections] == ["format"]
        stored = overlay.store.record_page(RecordQuery(kinds=("proposal",))).items
        assert {p.id for p in stored} <= {original.id, other.id}
        observed = overlay.store.record_page(
            RecordQuery(kinds=("event",), issuer="receiver", task_id=opportunity.id)
        ).items
        assert all(isinstance(e, Event) for e in observed)
        assert "remote peer temporarily unavailable" not in " ".join(
            e.model_dump_json() for e in observed
        )
    finally:
        for server in servers:
            server.should_exit = True
        if serving:
            await asyncio.wait_for(asyncio.gather(*serving), 10)


async def test_cio_030_02_collect_internal_fault_is_not_peer_unavailability(
    overlay, identities, records, tmp_path, monkeypatch
):
    from collective_intelligence_overlay.adapters import a2a

    steps, opportunity, _ = await configured_steps(overlay, identities, records)
    config = configured_http_peers(tmp_path, identities)

    async def internal_error(*args, **kwargs):
        raise ValueError("internal SDK wrapper invariant")

    monkeypatch.setattr(a2a, "send", internal_error)
    with pytest.raises(ValueError, match="internal SDK wrapper"):
        await collect(
            config["receiver"],
            overlay.store,
            identities["receiver"],
            steps.opportunities.goal(opportunity.goal_id),
            opportunity.id,
        )

    def broken_database(*args, **kwargs):
        raise ValueError("local event storage invariant")

    monkeypatch.setattr(overlay.store, "put", broken_database)
    with pytest.raises(ValueError, match="local event storage"):
        await collect(
            config["receiver"],
            overlay.store,
            identities["receiver"],
            steps.opportunities.goal(opportunity.goal_id),
            opportunity.id,
        )


async def test_cio_030_02_collect_cancels_and_joins_requests_before_store_close(
    overlay, identities, records, tmp_path, monkeypatch
):
    from collective_intelligence_overlay.adapters import a2a

    steps, opportunity, _ = await configured_steps(overlay, identities, records)
    config = configured_http_peers(tmp_path, identities)
    started, finished = set(), set()
    both_started = asyncio.Event()

    async def blocked(config, identity, peer, data):
        started.add(peer)
        if len(started) == 2:
            both_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.add(peer)

    monkeypatch.setattr(a2a, "send", blocked)
    collecting = asyncio.create_task(
        collect(
            config["receiver"],
            overlay.store,
            identities["receiver"],
            steps.opportunities.goal(opportunity.goal_id),
            opportunity.id,
        )
    )
    await asyncio.wait_for(both_started.wait(), 5)
    collecting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await collecting
    assert started == finished == {"producer", "other"}
    costs = overlay.store.record_page(
        RecordQuery(kinds=("event",), issuer="receiver", task_id=opportunity.id)
    ).items
    assert sum(e.action == "proposal" for e in costs) == 2
