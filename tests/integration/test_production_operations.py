import asyncio
import json
import os
import subprocess
import sys
import threading
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from collective_intelligence_overlay.application import load_application
from collective_intelligence_overlay.blocking import run_blocking
from collective_intelligence_overlay.models import now
from collective_intelligence_overlay.operations import OwnerAlreadyRunning, OwnerLock
from collective_intelligence_overlay.storage import Conflict, leases


async def test_duplicate_process_drain_and_dependency_failure(app_config, tmp_path):
    # Superuser/DDL-owner test fixture is explicitly development, never a production role.
    config = app_config.model_copy(update={"local_development": True})
    host = load_application(config)
    control = host.operations
    assert control is not None
    try:
        with pytest.raises(OwnerAlreadyRunning):
            load_application(config)
        config_path = tmp_path / "owner.json"
        data = config.model_dump(mode="json")
        data["database_url"] = config.database_url.get_secret_value()
        config_path.write_text(json.dumps(data))
        process = await asyncio.to_thread(
            subprocess.run,
            [
                sys.executable,
                "-m",
                "collective_intelligence_overlay.cli",
                "peer",
                "--config",
                str(config_path),
            ],
            capture_output=True,
            timeout=20,
            env=os.environ.copy(),
        )
        assert process.returncode == 2
        assert b"OwnerAlreadyRunning" in process.stderr
        await control.start()
        assert control.state == "ready"
        with pytest.raises(ValueError, match="operator control grant"):
            await control.handle("producer", {"operation": "status"})
        drained = await control.handle("receiver", {"operation": "drain"})
        assert drained["state"] == "draining"
        denied = await control.handle(
            "receiver", {"operation": "invoke", "invocation_id": "new-effect"}
        )
        assert denied["error"] == "SERVICE_INTAKE_CLOSED"
        assert host.executor.store.get("receiver", "new-effect") is None
        query = await control.handle(
            "receiver", {"operation": "invocation", "invocation_id": "missing"}
        )
        assert query == {"invocation": None}
        assert (await control.handle("receiver", {"operation": "resume"}))["state"] == "ready"
        # A physical lock-session disconnect cannot silently reacquire authority.
        with host.overlay.store.engine.connect() as conn:
            conn.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": control.lock.backend})
            conn.commit()
        refused = await control.handle(
            "receiver", {"operation": "invoke", "invocation_id": "after-cutoff"}
        )
        assert refused["error"] == "SERVICE_INTAKE_CLOSED"
        assert control.state == "degraded"
        assert (await control.handle("receiver", {"operation": "resume"}))["state"] == "degraded"
    finally:
        await control.stop()
        host.close()
    restarted = load_application(config)
    restarted.close()


async def test_production_readiness_rejects_developer_ddl_role(app_config):
    host = load_application(app_config)
    control = host.operations
    assert control is not None
    try:
        await control.start()
        assert control.state == "degraded"
        assert control.reason == "DATABASE_SCHEMA_OR_ROLE_NOT_READY"
    finally:
        await control.stop()
        host.close()


def test_closing_killed_owner_session_without_an_intervening_check(store):
    lock = OwnerLock(store)
    replacement = OwnerLock(store)
    try:
        lock.acquire()
        with store.engine.begin() as conn:
            assert conn.execute(
                text("SELECT pg_terminate_backend(:pid)"), {"pid": lock.backend}
            ).scalar_one()
        # No readiness query has yet detected the cut-off socket.
        lock.close()
        assert lock.connection is None
        replacement.acquire()
        assert replacement.check()
    finally:
        lock.close()
        replacement.close()


async def test_shutdown_does_not_claim_cancelled_db_thread_finished(app_config):
    host = load_application(app_config.model_copy(update={"local_development": True}))
    control = host.operations
    assert control is not None
    entered, release = threading.Event(), threading.Event()

    def late_commit():
        entered.set()
        assert release.wait(10)
        return "physical return"

    try:
        await control.start()
        with control.blocking.scope():
            task = asyncio.create_task(run_blocking(late_commit))
            assert await asyncio.to_thread(entered.wait, 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        report = await control.stop(0)
        assert report["state"] == "draining"
        assert report["reason"] == "SHUTDOWN_PHYSICAL_WORK_UNKNOWN"
        assert report["physical_blocking_work"] == 1
        assert control.lock.check()
        with pytest.raises(ValueError, match="physical"):
            host.close()
        release.set()
        assert await control.blocking.wait(5)
        assert (await control.stop())["state"] == "stopped"
    finally:
        release.set()
        await control.blocking.wait(5)
        await control.stop()
        host.close()


def test_lease_creation_expiry_and_finish_use_database_clock(store, monkeypatch):
    import collective_intelligence_overlay.storage as storage

    store.set_budget("work", Decimal(100))
    monkeypatch.setattr(storage, "now", lambda: now() + timedelta(days=30))
    store.acquire("db-clock", "worker", "work", Decimal(10), seconds=30)
    with store.engine.connect() as conn:
        row = conn.execute(select(leases).where(leases.c.task_id == "db-clock")).mappings().one()
        observed = conn.execute(text("SELECT clock_timestamp()")).scalar_one()
    assert 0 < (row["expires_at"] - observed).total_seconds() <= 30
    with pytest.raises(Conflict):
        store.acquire("db-clock", "replacement", "work", Decimal(10))
    monkeypatch.setattr(storage, "now", lambda: now() - timedelta(days=30))
    store.finish("db-clock", "worker", 1)
    with store.engine.connect() as conn:
        assert (
            conn.execute(select(leases.c.state).where(leases.c.task_id == "db-clock")).scalar_one()
            == "complete"
        )
