"""Real PostgreSQL capacity recovery without looking up the orphaned IDs first."""

import json
import os
import platform
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from threading import Event as ThreadEvent

import pytest
from process_control import stop_owned_process
from sqlalchemy import create_engine, event, insert, select, text, update
from sqlalchemy.exc import DBAPIError

from collective_intelligence_overlay.invocations import InvocationStore, Reservation, invocations
from collective_intelligence_overlay.models import Event, now
from collective_intelligence_overlay.storage import Conflict, budgets, leases


@pytest.mark.parametrize("dispatched", [False, True])
def test_cio_031_01_capacity_recovers_without_individual_old_id_query(store, dispatched):
    store.set_budget("work", Decimal(10))
    ledger = InvocationStore(store)
    allowance = Reservation(max_concurrent=2)
    old = [
        ledger.claim("receiver", f"orphan-{i}", "binding", "a" * 64, {}, allowance)[0]
        for i in range(2)
    ]
    if dispatched:
        for claim in old:
            ledger.dispatched(claim)
    with store.engine.begin() as conn:
        conn.execute(
            update(leases)
            .where(leases.c.task_id.in_([claim["lease_id"] for claim in old]))
            .values(expires_at=now() - timedelta(seconds=1))
        )
    # No get(old_id), manual cancellation or cleanup precedes the new independent claim.
    fresh, created = ledger.claim("receiver", "independent", "binding", "a" * 64, {}, allowance)
    assert created and fresh["state"] == "running"
    for claim in old:
        result = ledger.get("receiver", claim["id"])
        assert result["state"] == ("unknown" if dispatched else "cancelled")
        assert result["reservation_state"] == ("held" if dispatched else "released")
        with pytest.raises(Conflict, match="ownership"):
            ledger.dispatched(claim)
    with store.engine.connect() as conn:
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == (7 if dispatched else 9)


def expire(store):
    with store.engine.begin() as conn:
        conn.execute(update(leases).values(expires_at=now() - timedelta(seconds=1)))


def remaining(store, unit="work"):
    with store.engine.connect() as conn:
        return conn.execute(select(budgets.c.remaining).where(budgets.c.unit == unit)).scalar_one()


def test_dry_run_bounds_then_idempotent_cleanup_retains_live_and_other_owner(store):
    store.set_budget("work", Decimal(10))
    ledger = InvocationStore(store)
    claims = [
        ledger.claim("receiver", f"old-{i}", "b", "a" * 64, {}, Reservation())[0] for i in range(3)
    ]
    expire(store)
    live, _ = ledger.claim("receiver", "live", "b", "a" * 64, {}, Reservation())
    with store.engine.begin() as conn:
        conn.execute(update(invocations).where(invocations.c.id == "old-2").values(owner="other"))
    with pytest.raises(ValueError, match="owner"):
        ledger.cleanup_expired(owner="other")
    preview = ledger.cleanup_expired(owner="receiver", limit=1, dry_run=True)
    assert preview["has_more"] and len(preview["items"]) == 1
    assert preview["items"][0]["state"] == "running"
    assert preview["items"][0]["action"] == "release_undispatched"
    assert not preview["items"][0]["logical_slot_recovered"]
    assert remaining(store) == 6
    first = ledger.cleanup_expired(owner="receiver", limit=1)
    assert first["has_more"] and len(first["items"]) == 1
    assert first["items"][0]["lease_state"] == "cancelled"
    assert first["items"][0]["logical_slot_recovered"]
    second = ledger.cleanup_expired(owner="receiver", limit=1)
    assert not second["has_more"] and len(second["items"]) == 1
    assert ledger.cleanup_expired(owner="receiver")["items"] == []
    assert remaining(store) == 8
    # Do not query the foreign old ID through get: inspect immutable owner/state directly.
    with store.engine.connect() as conn:
        assert (
            conn.execute(
                select(invocations.c.state).where(invocations.c.id == "old-2")
            ).scalar_one()
            == "running"
        )
    assert ledger.get("receiver", live["id"])["state"] == "running"
    ledger.dispatched(live)
    assert len(claims) == 3


@pytest.mark.parametrize("uncertain", ["dispatched", "legacy_unknown", "worker", "actual"])
def test_uncertain_cleanup_fences_without_refund_and_stops_at_owner_limit(store, uncertain):
    store.set_budget("work", Decimal(10))
    ledger = InvocationStore(store)
    allowance = Reservation(max_concurrent=1, max_unresolved=1)
    claim, _ = ledger.claim("receiver", "uncertain", "b", "a" * 64, {}, allowance)
    if uncertain == "dispatched":
        ledger.dispatched(claim)
    with store.engine.begin() as conn:
        if uncertain == "legacy_unknown":
            conn.execute(update(invocations).values(reservation_state="legacy_unknown"))
        elif uncertain == "worker":
            conn.execute(update(leases).values(worker="replacement", fence=leases.c.fence + 1))
        elif uncertain == "actual":
            conn.execute(update(leases).values(actual=Decimal("0.5")))
    expire(store)
    result = ledger.cleanup_expired(owner="receiver")
    assert result["items"][0]["state"] == "unknown"
    assert result["items"][0]["action"] == "retain_unknown_effect"
    assert result["items"][0]["external_effect"] == "unconfirmed"
    assert remaining(store) == 9
    with pytest.raises(Conflict, match="unresolved effects limit"):
        ledger.claim("receiver", "different", "b", "a" * 64, {}, allowance)
    same, fresh = ledger.claim("receiver", "uncertain", "b", "a" * 64, {}, allowance)
    assert not fresh and same["state"] == "unknown"
    assert ledger.cleanup_expired(owner="receiver")["items"] == []
    with store.engine.connect() as conn:
        lease = conn.execute(select(leases)).mappings().one()
    if uncertain == "worker":
        assert lease["worker"] == "replacement" and lease["state"] == "active"
    if uncertain == "actual":
        assert lease["actual"] == Decimal("0.5")


def test_cleanup_claim_get_cancel_finish_race_across_budget_units(store, identities, records):
    ledger = InvocationStore(store)
    for unit in ("work", "USD"):
        store.set_budget(unit, Decimal(10))
    claims = [
        ledger.claim("receiver", f"race-{i}", "b", "a" * 64, {}, Reservation(unit=unit))[0]
        for i, unit in enumerate(("work", "USD"))
    ]
    ledger.dispatched(claims[1])
    expire(store)
    receipt = Event(
        issuer="receiver",
        subject=records[0].subject,
        action="reuse",
        task_id="race-1",
        attempt_id=claims[1]["lease_id"],
        correlation_id="race-1",
    )

    def finish():
        with pytest.raises(Conflict):
            ledger.finish(claims[1], {"late": True}, identities["receiver"], receipt)

    actions = [
        lambda: ledger.cleanup_expired(owner="receiver"),
        lambda: ledger.cleanup_expired(owner="receiver"),
        lambda: ledger.get("receiver", "race-0"),
        lambda: ledger.cancel("receiver", "race-0"),
        finish,
        lambda: ledger.claim(
            "receiver", "new-work", "b", "a" * 64, {}, Reservation(unit="work", max_concurrent=1)
        ),
        lambda: ledger.claim(
            "receiver", "new-usd", "b", "a" * 64, {}, Reservation(unit="USD", max_concurrent=1)
        ),
    ]

    def run(action):
        try:
            return action()
        except Conflict:
            return "finite capacity refusal"

    with ThreadPoolExecutor(max_workers=7) as pool:
        futures = [pool.submit(run, action) for action in actions]
        results = [future.result(timeout=20) for future in futures]
    assert len(results) == 7
    assert ledger.get("receiver", "race-0")["reservation_state"] == "released"
    unknown = ledger.get("receiver", "race-1")
    assert unknown["state"] == "unknown" and unknown["reservation_state"] == "held"
    assert unknown["result"] is None and unknown["receipt_id"] is None
    with store.engine.connect() as conn:
        running = (
            conn.execute(select(invocations.c.id).where(invocations.c.state == "running"))
            .scalars()
            .all()
        )
    assert len(running) <= 1
    assert remaining(store, "work") == (9 if "new-work" in running else 10)
    assert remaining(store, "USD") == (8 if "new-usd" in running else 9)


def test_cleanup_database_disconnect_rolls_back_and_can_be_rerun(store):
    store.set_budget("work", Decimal(10))
    ledger = InvocationStore(store)
    ledger.claim("receiver", "disconnect", "b", "a" * 64, {}, Reservation())
    expire(store)
    admin = create_engine(store.engine.url, isolation_level="AUTOCOMMIT")
    disconnected = False

    def disconnect(conn, cursor, statement, parameters, context, executemany):
        nonlocal disconnected
        if statement.startswith("UPDATE budgets") and not disconnected:
            disconnected = True
            pid = conn.execute(text("SELECT pg_backend_pid()")).scalar_one()
            with admin.connect() as killer:
                assert killer.execute(
                    text("SELECT pg_terminate_backend(:pid)"), {"pid": pid}
                ).scalar_one()

    event.listen(store.engine, "after_cursor_execute", disconnect)
    try:
        with pytest.raises(DBAPIError):
            ledger.cleanup_expired(owner="receiver")
    finally:
        event.remove(store.engine, "after_cursor_execute", disconnect)
        admin.dispose()
    assert disconnected and remaining(store) == 9
    with store.engine.connect() as conn:
        assert conn.execute(select(invocations.c.state)).scalar_one() == "running"
        assert conn.execute(select(leases.c.state)).scalar_one() == "active"
    assert ledger.cleanup_expired(owner="receiver")["items"][0]["state"] == "cancelled"
    assert remaining(store) == 10


def wait_for_file(path, process):
    deadline = time.monotonic() + 15
    while not path.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert path.exists(), "child did not reach the controlled database boundary"


@pytest.mark.parametrize("dispatched", [False, True])
def test_killed_worker_restart_accepts_new_id_without_querying_old_ids(store, tmp_path, dispatched):
    store.set_budget("work", Decimal(10))
    marker = tmp_path / "worker-ready"
    script = """
import os, time
from pathlib import Path
from collective_intelligence_overlay.storage import Store
from collective_intelligence_overlay.invocations import InvocationStore, Reservation
store = Store(os.environ['CIO_CRASH_TEST_DB'], 'receiver', {})
ledger = InvocationStore(store)
for i in range(2):
    claim, fresh = ledger.claim('receiver', f'killed-{i}', 'b', 'a'*64, {},
                                Reservation(max_concurrent=2))
    assert fresh
    if os.environ['CIO_CRASH_TEST_DISPATCHED'] == 'yes':
        ledger.dispatched(claim)
Path(os.environ['CIO_CRASH_TEST_MARKER']).write_text('ready')
time.sleep(60)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        env={
            **os.environ,
            "CIO_CRASH_TEST_DB": store.engine.url.render_as_string(hide_password=False),
            "CIO_CRASH_TEST_MARKER": str(marker),
            "CIO_CRASH_TEST_DISPATCHED": "yes" if dispatched else "no",
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_file(marker, process)
    finally:
        stop_owned_process(process, kill=True)
    expire(store)
    ledger = InvocationStore(store)
    fresh, created = ledger.claim(
        "receiver", "restart-new", "b", "a" * 64, {}, Reservation(max_concurrent=2)
    )
    assert created and fresh["state"] == "running"
    assert remaining(store) == (7 if dispatched else 9)
    for i in range(2):
        old = ledger.get("receiver", f"killed-{i}")
        assert old["state"] == ("unknown" if dispatched else "cancelled")


def test_killed_cleanup_preserves_prior_commit_rolls_back_current_row_and_resumes(store, tmp_path):
    store.set_budget("work", Decimal(10))
    ledger = InvocationStore(store)
    for i in range(2):
        ledger.claim("receiver", f"kill-cleanup-{i}", "b", "a" * 64, {}, Reservation())
    expire(store)
    marker = tmp_path / "second-refund-uncommitted"
    script = """
import os, time
from pathlib import Path
from sqlalchemy import event
from collective_intelligence_overlay.storage import Store
from collective_intelligence_overlay.invocations import InvocationStore
store = Store(os.environ['CIO_CRASH_TEST_DB'], 'receiver', {})
refunds = 0
def hold(conn, cursor, statement, parameters, context, executemany):
    global refunds
    if statement.startswith('UPDATE budgets'):
        refunds += 1
        if refunds == 2:
            Path(os.environ['CIO_CRASH_TEST_MARKER']).write_text('uncommitted')
            time.sleep(60)
event.listen(store.engine, 'after_cursor_execute', hold)
InvocationStore(store).cleanup_expired(owner='receiver')
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        env={
            **os.environ,
            "CIO_CRASH_TEST_DB": store.engine.url.render_as_string(hide_password=False),
            "CIO_CRASH_TEST_MARKER": str(marker),
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_file(marker, process)
    finally:
        stop_owned_process(process, kill=True)
    assert remaining(store) == 9
    with store.engine.connect() as conn:
        states = (
            conn.execute(select(invocations.c.state).order_by(invocations.c.created_at))
            .scalars()
            .all()
        )
    assert states == ["cancelled", "running"]
    assert len(ledger.cleanup_expired(owner="receiver")["items"]) == 1
    assert remaining(store) == 10
    assert ledger.cleanup_expired(owner="receiver")["items"] == []


def test_cleanup_races_delayed_database_thread_commit_without_inventing_absence(store):
    store.set_budget("work", Decimal(10))
    ledger = InvocationStore(store)
    pending, resume = ThreadEvent(), ThreadEvent()

    def hold(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO invocations"):
            pending.set()
            assert resume.wait(timeout=15)

    event.listen(store.engine, "after_cursor_execute", hold)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                ledger.claim, "receiver", "delayed", "b", "a" * 64, {}, Reservation()
            )
            try:
                assert pending.wait(timeout=10)
                # An uncommitted claim is invisible, not proof of no future commit.
                assert ledger.cleanup_expired(owner="receiver")["items"] == []
            finally:
                resume.set()
            claim, fresh = future.result(timeout=10)
    finally:
        event.remove(store.engine, "after_cursor_execute", hold)
    assert fresh and remaining(store) == 9
    expire(store)
    assert len(ledger.cleanup_expired(owner="receiver")["items"]) == 1
    assert remaining(store) == 10
    with pytest.raises(Conflict, match="ownership"):
        ledger.dispatched(claim)


def test_owner_cli_dry_run_and_apply_with_real_config_database(
    store, identities, tmp_path, monkeypatch, capsys
):
    from collective_intelligence_overlay import cli

    store.set_budget("work", Decimal(10))
    ledger = InvocationStore(store)
    for i in range(2):
        ledger.claim(
            "receiver", f"cli-{i}", "b", "a" * 64, {"private": "not printed"}, Reservation()
        )
    expire(store)
    key = tmp_path / "private.pem"
    key.write_bytes(identities["receiver"].signer.private_bytes)
    key.chmod(0o600)
    config_path = tmp_path / "owner.json"
    config_path.write_text(
        json.dumps(
            {
                "owner": "receiver",
                "database_url": store.engine.url.render_as_string(hide_password=False),
                "private_key": str(key),
                "artifact_directory": str(tmp_path / "artifacts"),
                "opa_binary": os.environ["CIO_OPA"],
                "url": "https://receiver.example/",
                "identities": {
                    name: {
                        "keyid": p.key.keyid,
                        "key": p.key.to_dict(),
                        "trust_group": p.trust_group,
                        "methods": sorted(p.methods),
                    }
                    for name, p in store.principals.items()
                },
            }
        ),
        encoding="utf-8",
    )
    command = ["cio", "invocation-cleanup", "--config", str(config_path)]
    monkeypatch.setattr(sys, "argv", [*command, "--limit", "1", "--dry-run"])
    assert cli.main() == 3
    output = capsys.readouterr()
    preview = json.loads(output.out)
    assert preview["has_more"] and remaining(store) == 8
    assert "not printed" not in output.out and not output.err
    monkeypatch.setattr(sys, "argv", [*command, "--limit", "2"])
    assert cli.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert len(result["items"]) == 2 and remaining(store) == 10


@pytest.mark.parametrize(
    "count", [int(n) for n in os.environ.get("CIO_SCALE_COUNTS", "1000,10000").split(",")]
)
def test_cleanup_batch_queries_and_results_stay_bounded_with_unrelated_history(store, count):
    store.set_budget("work", Decimal(10))
    ledger = InvocationStore(store)
    claim, _ = ledger.claim("receiver", "old-bounded", "b", "a" * 64, {}, Reservation())
    with store.engine.connect() as conn:
        saved_lease = dict(conn.execute(select(leases)).mappings().one())
    # Controlled historical fixtures exercise indexes and preserved terminal state;
    # these inserts are not observed executions or measured historical spending.
    for start in range(0, count, 500):
        rows, lease_rows = [], []
        for i in range(start, min(start + 500, count)):
            key = f"history-{i}"
            rows.append(
                {
                    **claim,
                    "caller": "history",
                    "id": key,
                    "lease_id": key,
                    "owner": "other" if i % 2 else "receiver",
                    "state": "completed",
                    "phase": "dispatched",
                    "reservation_state": "consumed",
                }
            )
            lease_rows.append(
                {**saved_lease, "task_id": key, "state": "complete", "actual": Decimal(1)}
            )
        with store.engine.begin() as conn:
            conn.execute(insert(leases), lease_rows)
            conn.execute(insert(invocations), rows)
    expire(store)
    live, _ = ledger.claim("receiver", "still-live", "b", "a" * 64, {}, Reservation())
    statements = []

    def observe(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(store.engine, "after_cursor_execute", observe)
    started = time.perf_counter()
    try:
        result = ledger.cleanup_expired(owner="receiver", limit=1)
    finally:
        event.remove(store.engine, "after_cursor_execute", observe)
    elapsed = time.perf_counter() - started
    assert len(result["items"]) == 1 and result["items"][0]["id"] == "old-bounded"
    assert not result["has_more"] and len(statements) < 64
    assert any("LIMIT" in s and "LEFT OUTER JOIN leases" in s for s in statements)
    assert remaining(store) == 9
    assert ledger.get("receiver", live["id"])["state"] == "running"
    with store.engine.connect() as conn:
        assert (
            conn.execute(
                select(invocations.c.state).where(invocations.c.id == f"history-{count - 1}")
            ).scalar_one()
            == "completed"
        )
    if directory := os.environ.get("CIO_SCALE_REPORT_DIR"):
        output = Path(directory)
        output.mkdir(parents=True, exist_ok=True)
        (output / f"invocation-cleanup-{count}.json").write_text(
            json.dumps(
                {
                    "historical_rows": count,
                    "returned_rows": len(result["items"]),
                    "cleanup_statements": len(statements),
                    "elapsed_seconds": elapsed,
                    "os": platform.system(),
                    "cpu": platform.machine(),
                    "python": platform.python_version(),
                    "unknown_effect_completion": "not inferred",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
