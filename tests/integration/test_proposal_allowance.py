import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update

from collective_intelligence_overlay.application import ApplicationHost
from collective_intelligence_overlay.bindings import fingerprint
from collective_intelligence_overlay.models import Event
from collective_intelligence_overlay.opportunities import ProposalDraft, ProposalDrafts
from collective_intelligence_overlay.proposal_exchange import ProposalContract, ProposalExchange
from collective_intelligence_overlay.queries import RecordQuery
from collective_intelligence_overlay.security import digest, verify
from collective_intelligence_overlay.storage import Conflict, budgets, leases


@pytest.fixture
def proposal_input(opportunity, identities):
    observation = opportunity.model_copy(update={"issuer": "producer", "receivers": ("receiver",)})
    contract = ProposalContract(
        owner=observation.issuer,
        id=observation.goal_id,
        goal_digest=observation.goal_digest,
        contract_digest=digest(b"operator proposal contract"),
        subject=observation.subject,
        scope=observation.scope,
        checker=observation.checker,
        builders=(observation.checker,),
        peers=("receiver",),
        lifetime_seconds=3600,
    )
    drafts = ProposalDrafts(
        alternatives=tuple(
            ProposalDraft(
                builder=observation.checker, arguments={"strategy": name}, alternative=name
            )
            for name in ("first", "second")
        )
    )
    return observation, contract, drafts, identities["producer"].sign(observation)


def balance(store):
    with store.engine.connect() as conn:
        return conn.execute(
            select(budgets.c.remaining).where(budgets.c.unit == "work")
        ).scalar_one()


async def test_installed_proposer_refuses_heavy_work_without_owner_allowance(
    app_config, store, proposal_input
):
    _, contract, drafts, envelope = proposal_input
    called = []

    async def heavy(observation):
        called.append(observation.id)
        return drafts

    store.set_budget("work", Decimal(0))
    host = ApplicationHost(app_config)
    try:
        host.register_proposer((contract,), heavy)
        with pytest.raises(Conflict, match="budget exhausted"):
            await host.proposal_exchange.respond("producer", envelope)
        assert not called and balance(store) == 0
        with store.engine.connect() as conn:
            assert conn.execute(select(func.count()).select_from(leases)).scalar_one() == 0
        assert not store.record_page(RecordQuery(kinds=("proposal", "event"))).items
    finally:
        host.close()


async def test_original_proposal_retry_after_restart_does_not_regenerate_or_debit(
    app_config, store, identities, proposal_input
):
    observation, contract, drafts, envelope = proposal_input
    called, entered, release = [], asyncio.Event(), asyncio.Event()

    async def heavy(observation):
        called.append(observation.id)
        entered.set()
        await release.wait()
        return drafts

    store.set_budget("work", Decimal(2))
    host = ApplicationHost(app_config)
    host.register_proposer((contract,), heavy)
    running = asyncio.create_task(host.proposal_exchange.respond("producer", envelope))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        with pytest.raises(Conflict, match="owned or terminal"):
            await host.proposal_exchange.respond("producer", envelope)
        assert balance(store) == 1
        release.set()
        response = await running
        assert len(response["proposals"]) == 2 and called == [observation.id]
        assert {verify(item, store.principals).alternative for item in response["proposals"]} == {
            "first",
            "second",
        }
        assert await host.proposal_exchange.respond("producer", envelope) == response
        forged = observation.model_copy(update={"reasons": ("different-deficit",)})
        with pytest.raises(Conflict, match="record identity"):
            await host.proposal_exchange.respond("producer", identities["producer"].sign(forged))
        assert balance(store) == 1 and len(called) == 1
        events = store.record_page(RecordQuery(kinds=("event",), issuer="receiver")).items
        assert len(events) == 1 and isinstance(events[0], Event) and events[0].outcome is None
        original_cost = store.signed_record(store.reference("event", "receiver", events[0].id))
        assert not store.evidence()
    finally:
        release.set()
        await running
        host.close()
    restarted = ApplicationHost(app_config)
    try:
        restarted.register_proposer((contract,), heavy)
        assert await restarted.proposal_exchange.respond("producer", envelope) == response
        assert (
            store.signed_record(store.reference("event", "receiver", events[0].id)) == original_cost
        )
        assert balance(store) == 1 and len(called) == 1
    finally:
        restarted.close()


@pytest.mark.parametrize("stop", ["cancel", "timeout", "invalid-builder", "expired-lease"])
async def test_uncertain_proposal_work_stays_held_and_capacity_has_no_wait_queue(
    store, identities, proposal_input, stop
):
    observation, contract, drafts, envelope = proposal_input
    entered, release, called = asyncio.Event(), asyncio.Event(), []

    async def heavy(observation):
        called.append(observation.id)
        entered.set()
        await release.wait()
        if stop == "invalid-builder":
            return drafts.model_copy(
                update={
                    "alternatives": (
                        drafts.alternatives[0].model_copy(
                            update={
                                "builder": contract.builders[0].model_copy(
                                    update={"digest": digest(b"unapproved")}
                                )
                            }
                        ),
                    )
                }
            )
        return drafts

    store.set_budget("work", Decimal(2))

    def exchange():
        return ProposalExchange(
            store,
            identities["receiver"],
            (contract,),
            heavy,
            seconds=1,
            allowance_unit="work",
            max_concurrent=1,
        )

    service = exchange()
    running = asyncio.create_task(service.respond("producer", envelope))
    await asyncio.wait_for(entered.wait(), 5)
    try:
        another = observation.model_copy(update={"id": "another-proposal"})
        with pytest.raises(Conflict, match="capacity"):
            await service.respond("producer", identities["producer"].sign(another))
        assert balance(store) == 1 and called == [observation.id]
        if stop == "cancel":
            running.cancel()
            expected = asyncio.CancelledError
        elif stop == "timeout":
            expected = TimeoutError
        else:
            if stop == "expired-lease":
                with store.engine.begin() as conn:
                    conn.execute(update(leases).values(expires_at=func.clock_timestamp()))
                expected = Conflict
            else:
                expected = ValueError
            release.set()
        with pytest.raises(expected):
            await running
        with pytest.raises(Conflict, match="uncertain|owned or terminal"):
            await exchange().respond("producer", envelope)
        assert balance(store) == 1 and called == [observation.id]
        assert not store.record_page(RecordQuery(kinds=("proposal",))).items
        assert not store.evidence()
        with store.engine.connect() as conn:
            saved = conn.execute(select(leases)).mappings().one()
        assert saved["reservation"] == 1 and saved["actual"] is None
        assert saved["state"] == ("active" if stop == "expired-lease" else "cancelled")
        marker = store.record_page(RecordQuery(kinds=("event",))).items
        assert not marker if stop == "expired-lease" else marker[0].outcome == "UNKNOWN"
        assert saved["task_id"] == "proposal-work-" + fingerprint(["producer", observation.id])
    finally:
        release.set()
        if not running.done():
            running.cancel()
        await asyncio.gather(running, return_exceptions=True)
