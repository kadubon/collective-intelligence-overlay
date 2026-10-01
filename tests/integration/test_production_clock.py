"""Lease commit authority follows the DB clock in both Python skew directions."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, update

from collective_intelligence_overlay import models
from collective_intelligence_overlay.storage import Conflict, leases


@pytest.mark.parametrize("offset_seconds", [-60, 60])
def test_commit_uses_locked_database_clock(store, records, identities, monkeypatch, offset_seconds):
    store.set_budget("work", Decimal(10))
    fence = store.acquire("clock-original", "receiver", "work", Decimal(1), seconds=30)
    signed = identities["receiver"].sign(records[0].model_copy(update={"issuer": "receiver"}))

    class OffsetDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(seconds=offset_seconds)

    monkeypatch.setattr(models, "datetime", OffsetDateTime)
    with store.engine.connect() as connection:
        valid = connection.execute(
            select(leases.c.expires_at > func.clock_timestamp()).where(
                leases.c.task_id == "clock-original"
            )
        ).scalar_one()
    assert valid
    # Forward Python skew must not revoke this still-valid DB lease.
    store.commit_work("clock-original", "receiver", fence, [signed])
    with store.engine.connect() as connection:
        assert (
            connection.execute(
                select(leases.c.state).where(leases.c.task_id == "clock-original")
            ).scalar_one()
            == "complete"
        )

    expired_fence = store.acquire("clock-expired", "receiver", "work", Decimal(1), seconds=30)
    with store.engine.begin() as connection:
        connection.execute(
            update(leases)
            .where(leases.c.task_id == "clock-expired")
            .values(expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )
    # Backward Python skew must not extend an expired DB lease or its authority.
    with pytest.raises(Conflict, match="stale worker"):
        store.commit_work("clock-expired", "receiver", expired_fence, [signed])
