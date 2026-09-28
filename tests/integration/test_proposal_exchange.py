import asyncio
import os
from urllib.parse import urlsplit

import pytest
import uvicorn

from collective_intelligence_overlay.adapters.a2a import application
from collective_intelligence_overlay.bindings import Registry
from collective_intelligence_overlay.demo import initialize
from collective_intelligence_overlay.models import BindingRef, Scope, Subject, UseRequest
from collective_intelligence_overlay.opportunities import (
    Goal,
    Opportunities,
    ProposalDraft,
    ProposalDrafts,
)
from collective_intelligence_overlay.peer import PeerService
from collective_intelligence_overlay.proposal_exchange import ProposalExchange, collect
from collective_intelligence_overlay.security import digest, verify


async def test_authenticated_a2a_alternative_proposers_and_unavailable_peer(tmp_path, policy):
    url = os.environ.get("CIO_TEST_DATABASE_URL")
    if not url:
        pytest.skip("real PostgreSQL required")
    configs = initialize(tmp_path / "exchange", url, policy.binary)
    services = {name: PeerService(config) for name, config in configs.items()}
    receiver = services["receiver"]
    scope = Scope(
        task="transformation",
        input_contract="input.v1",
        output_contract="output.v1",
        environment={"application": "1"},
    )
    builder = BindingRef(issuer="receiver", id="registered-transform", digest=digest(b"builder"))
    goal = Goal(
        id="transform",
        revision="1",
        request=UseRequest(
            receiver="receiver",
            capability_issuer="receiver",
            binding_digest=digest(b"target-binding"),
            subject=Subject(id="target", version="1", digest=digest(b"target")),
            scope=scope,
            semantic_fit="confirmed",
        ),
        checker=builder,
        builders=(builder,),
        peers=("producer", "verifier"),
    )
    opportunities = Opportunities(Registry(receiver.overlay), receiver.identity, (goal,))
    opportunity = (await opportunities.discover()).opportunities[0]
    seen = []

    async def producer(observation):
        seen.append(("producer", observation.id))
        return ProposalDrafts(
            alternatives=(
                ProposalDraft(builder=builder, arguments={"strategy": "a"}, alternative="first"),
            )
        )

    async def verifier(observation):
        seen.append(("verifier", observation.id))
        return ProposalDrafts(
            alternatives=(
                ProposalDraft(builder=builder, arguments={"strategy": "b"}, alternative="second"),
            )
        )

    servers, serving = [], []
    try:
        for name, proposer in (("producer", producer), ("verifier", verifier)):
            service = services[name]
            service.proposal_exchange = ProposalExchange(
                service.overlay.store, service.identity, (goal,), proposer
            )
            server = uvicorn.Server(
                uvicorn.Config(
                    application(configs[name], service.handle),
                    host="127.0.0.1",
                    port=urlsplit(configs[name].url).port,
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
        result = await collect(
            configs["receiver"], receiver.overlay.store, receiver.identity, goal, opportunity.id
        )
        assert not result.unavailable
        assert {caller for caller, _ in result.replies} == {"producer", "verifier"}
        records = [
            verify(envelope, receiver.overlay.store.principals) for _, envelope in result.replies
        ]
        assert {p.arguments["strategy"] for p in records} == {"a", "b"}
        assert len({p.id for p in records}) == 2 and len(seen) == 2
        repeated = await collect(
            configs["receiver"], receiver.overlay.store, receiver.identity, goal, opportunity.id
        )
        assert repeated.replies == result.replies
        # Sharing evidence does not enable proposal exchange by default.
        services["verifier"].proposal_exchange = None
        partial = await collect(
            configs["receiver"], receiver.overlay.store, receiver.identity, goal, opportunity.id
        )
        assert partial.unavailable == ("verifier",)
        assert len(partial.replies) == 1 and partial.replies[0][0] == "producer"
        ref = receiver.overlay.store.reference("opportunity", "receiver", opportunity.id)
        envelope = receiver.overlay.store.signed_record(ref)
        with pytest.raises(ValueError, match="authenticated owner"):
            await services["producer"].proposal_exchange.respond("verifier", envelope)
        changed = opportunity.model_copy(update={"goal_digest": digest(b"unapproved")})
        with pytest.raises(ValueError, match="contract"):
            await services["producer"].proposal_exchange.respond(
                "receiver", receiver.identity.sign(changed)
            )
    finally:
        for server in servers:
            server.should_exit = True
        if serving:
            await asyncio.wait_for(asyncio.gather(*serving), 15)
        for service in services.values():
            service.overlay.store.close()
