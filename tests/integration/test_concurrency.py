from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from collective_intelligence_overlay.models import now
from collective_intelligence_overlay.storage import Conflict, budgets, leases


def test_racing_acquire_and_budget(store):
    store.set_budget("work", Decimal("1.1"))

    def acquire(worker):
        try:
            return store.acquire("task", worker, "work", Decimal("0.6"))
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(acquire, [str(n) for n in range(8)]))
    assert results.count(1) == 1
    with store.engine.connect() as conn:
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == Decimal("0.5")


def test_stale_worker_cannot_commit(store, records, identities):
    store.set_budget("work", Decimal(10))
    old = store.acquire("task", "old", "work", Decimal(1))
    with store.engine.begin() as conn:
        conn.execute(update(leases).values(expires_at=now() - timedelta(seconds=1)))
    new = store.acquire("task", "new", "work", Decimal(1))
    assert new > old
    record = records[0].model_copy(update={"issuer": "receiver"})
    signed = identities["receiver"].sign(record)
    with pytest.raises(Conflict):
        store.commit_work("task", "old", old, [signed])
    assert store.capabilities() == []
    store.commit_work("task", "new", new, [signed])
    assert len(store.capabilities()) == 1
    with pytest.raises(Conflict):
        store.finish("task", "old", old)


def test_nonreclaiming_check_keeps_unknown_attempt_and_allowance(store):
    store.set_budget("work", Decimal(10))
    fence = store.acquire("uncertain-check", "original", "work", Decimal(1), reclaim_expired=False)
    with store.engine.begin() as conn:
        conn.execute(update(leases).values(expires_at=now() - timedelta(seconds=1)))
    store.close()

    def retry(worker):
        with pytest.raises(Conflict):
            store.acquire("uncertain-check", worker, "work", Decimal(1), reclaim_expired=False)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(retry, ["original", "other", "another", "original"]))
    with store.engine.connect() as conn:
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == Decimal(9)
        row = conn.execute(select(leases)).mappings().one()
        assert row["worker"] == "original" and row["fence"] == fence
        assert row["state"] == "active"


def test_cancel_completion_race_and_restart(store, records, identities):
    store.set_budget("work", Decimal(10))
    fence = store.acquire("task", "worker", "work", Decimal(1))
    store.finish("task", "worker", fence, cancelled=True)
    with pytest.raises(Conflict):
        store.commit_work("task", "worker", fence, [])
    with pytest.raises(Conflict):
        store.acquire("task", "worker", "work", Decimal(1))
    store.close()
    assert store.events() == []  # engine reconnects; durable terminal lease remains
