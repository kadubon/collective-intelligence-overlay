import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from securesystemslib.signer import Key
from sqlalchemy import (
    DateTime,
    MetaData,
    Numeric,
    create_engine,
    event,
    insert,
    inspect,
    select,
    text,
    update,
)

from collective_intelligence_overlay.security import Principal, verify
from collective_intelligence_overlay.storage import Store, budgets, leases, migrate, records


def seed_release(store, version):
    revision, commit = {
        "020": ("0008", "394ba59aa6ec9e95b4f725862747f5198826cf9b"),
        "021": ("0009", "3026c39b7cb3a4808e4b1eaf45332b1b81f4df8a"),
        "030": ("0012", "a2fc32b5511b3c3cec4f2e15fcd6375eb9540c67"),
        "031": ("0014", "e7e245920be3687eebb4b0a0817d60a82ed2c1b9"),
    }[version]
    fixture = json.loads(
        (Path(__file__).parents[1] / f"fixtures/v{version}_database.json").read_text()
    )
    assert fixture["created_by"] == "collective-intelligence-overlay==" + ".".join(version)
    assert fixture["release_commit"] == commit
    store.principals = {
        name: Principal(
            Key.from_dict(item["keyid"], item["key"]),
            item["trust_group"],
            frozenset(item["methods"]),
        )
        for name, item in fixture["principals"].items()
    }
    migrate(store.engine, revision)
    old = MetaData()
    old.reflect(store.engine)
    with store.engine.begin() as conn:
        for name, rows in fixture["tables"].items():
            table = old.tables[name]
            for original in rows:
                values = dict(original)
                for column in table.columns:
                    if values[column.name] is not None:
                        if isinstance(column.type, DateTime):
                            values[column.name] = datetime.fromisoformat(values[column.name])
                        elif isinstance(column.type, Numeric):
                            values[column.name] = Decimal(values[column.name])
                if name == "feed_state":
                    conn.execute(update(table).where(table.c.id == 1).values(**values))
                else:
                    conn.execute(insert(table).values(**values))
    return fixture


@pytest.mark.parametrize("interrupted", [False, True])
def test_actual_031_cleanup_index_upgrade_and_restore_preserve_all_rows(
    unmigrated_store, interrupted
):
    from collective_intelligence_overlay.calls import remote_calls
    from collective_intelligence_overlay.invocations import InvocationStore, invocations

    store = unmigrated_store
    fixture = seed_release(store, "031")
    assert fixture["wheel_sha256"] == (
        "caa5acb140e5e2a09067ee4fa4e074e019fb02a68dd8a59a70ff9e973a6f9a41"
    )
    old = MetaData()
    old.reflect(store.engine)

    def snapshot(target):
        with target.engine.connect() as conn:
            return {
                name: [
                    dict(r)
                    for r in conn.execute(
                        select(table).order_by(*table.primary_key.columns)
                    ).mappings()
                ]
                for name, table in old.tables.items()
                if name != "alembic_version"
            }

    original = snapshot(store)
    assert original["budgets"][0]["remaining"] == 6
    assert len(original["remote_calls"]) == 1
    if interrupted:

        def interrupt(conn, cursor, statement, parameters, context, executemany):
            if "CREATE INDEX ix_invocations_owner_running_order" in statement:
                raise RuntimeError("interrupted cleanup index migration")

        event.listen(store.engine, "after_cursor_execute", interrupt)
        try:
            with pytest.raises(RuntimeError, match="cleanup index migration"):
                migrate(store.engine)
        finally:
            event.remove(store.engine, "after_cursor_execute", interrupt)
        assert snapshot(store) == original
        with store.engine.connect() as conn:
            assert (
                conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0014"
            )
    migrate(store.engine)
    migrate(store.engine)
    assert snapshot(store) == original
    assert "ix_invocations_owner_running_order" in {
        i["name"] for i in inspect(store.engine).get_indexes("invocations")
    }
    with database_copy(store) as restored:
        migrate(restored.engine)
        assert snapshot(restored) == original
        for row in original["records"]:
            verify(row["envelope"], restored.principals)
        with restored.engine.connect() as conn:
            mapped = list(conn.execute(select(remote_calls)).mappings())
            assert all(row["arguments_digest"] is None for row in mapped)
            assert [
                {k: v for k, v in row.items() if k != "arguments_digest"} for row in mapped
            ] == original["remote_calls"]
        with restored.engine.begin() as conn:
            conn.execute(
                update(leases)
                .where(leases.c.state == "active")
                .values(expires_at=datetime.fromisoformat("2020-01-01T00:00:00+00:00"))
            )
        cleaned = InvocationStore(restored).cleanup_expired(owner="receiver")
        assert len(cleaned["items"]) == 2
        with restored.engine.connect() as conn:
            saved = {r["id"]: r for r in conn.execute(select(invocations)).mappings()}
            assert saved["reserved"]["reservation_state"] == "released"
            assert saved["dispatched"]["state"] == "unknown"
            assert saved["dispatched"]["reservation_state"] == "held"
            assert saved["uncertain"]["state"] == "unknown"
            assert saved["completed"]["result"] == {"value": 7}
            assert conn.execute(select(budgets.c.remaining)).scalar_one() == 7
            mapped = list(conn.execute(select(remote_calls)).mappings())
            assert all(row["arguments_digest"] is None for row in mapped)
            assert [
                {k: v for k, v in row.items() if k != "arguments_digest"} for row in mapped
            ] == original["remote_calls"]


def test_actual_020_invocation_upgrade_keeps_unknown_allowances_and_signed_history(
    unmigrated_store,
):
    from collective_intelligence_overlay.invocations import (
        InvocationStore,
        Reservation,
        invocations,
    )

    store = unmigrated_store
    fixture = seed_release(store, "020")
    # Explicit patch-release checkpoint before adding the 0.3.0 tables/indexes.
    migrate(store.engine, "0009")
    with store.engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0009"
        assert set(conn.execute(select(invocations.c.reservation_state)).scalars()) == {
            "legacy_unknown"
        }
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == 7
        assert {
            (row.kind, row.issuer, row.record_id): row.envelope
            for row in conn.execute(select(records))
        } == {
            (row["kind"], row["issuer"], row["record_id"]): row["envelope"]
            for row in fixture["tables"]["records"]
        }
    migrate(store.engine)
    migrate(store.engine)
    with store.engine.connect() as conn:
        current = list(conn.execute(select(records)).mappings())
        originals = {
            (r["kind"], r["issuer"], r["record_id"]): r for r in fixture["tables"]["records"]
        }
        assert len(current) == len(originals)
        for row in current:
            source = originals[row["kind"], row["issuer"], row["record_id"]]
            assert row["body"] == source["body"] and row["envelope"] == source["envelope"]
            verify(row["envelope"], store.principals)
        assert set(conn.execute(select(invocations.c.reservation_state)).scalars()) == {
            "legacy_unknown"
        }
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == 7
    ledger = InvocationStore(store)
    assert ledger.cancel("receiver", "reserved")["reservation_state"] == "legacy_unknown"
    assert ledger.cancel("receiver", "dispatched")["reservation_state"] == "legacy_unknown"
    assert ledger.get("receiver", "completed")["result"] == {"value": 7}
    assert {e.verdict for e in store.evidence()} == {"PASS", "FAIL", "UNKNOWN"}
    assert len(store.revocations()) == 1
    claim, fresh = ledger.claim("receiver", "new", "b", "c" * 64, {}, Reservation())
    assert fresh and claim["reservation_state"] == "held"
    assert ledger.cancel("receiver", "new")["reservation_state"] == "released"
    with store.engine.connect() as conn:
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == 7


def test_actual_021_upgrade_and_backup_preserve_all_reservation_states(unmigrated_store):
    from collective_intelligence_overlay.invocations import InvocationStore, invocations

    store = unmigrated_store
    fixture = seed_release(store, "021")

    def snapshot(target):
        with target.engine.connect() as conn:
            return {
                table.name: [
                    dict(row)
                    for row in conn.execute(
                        select(table).order_by(*table.primary_key.columns)
                    ).mappings()
                ]
                for table in (records, budgets, leases, invocations)
            }

    original = snapshot(store)
    assert {row["reservation_state"] for row in original["invocations"]} == {
        "held",
        "released",
        "consumed",
    }
    assert original["budgets"][0]["remaining"] == 6
    migrate(store.engine)
    migrate(store.engine)
    assert snapshot(store) == original
    assert "work_selections" in inspect(store.engine).get_table_names()
    with database_copy(store) as restored:
        migrate(restored.engine)
        assert snapshot(restored) == original
        restored.reset_sync_after_restore()
        assert snapshot(restored) == original
        for row in original["records"]:
            verify(row["envelope"], restored.principals)
        assert len(original["records"]) == len(fixture["tables"]["records"])
        ledger = InvocationStore(restored)
        assert ledger.get("receiver", "completed")["result"] == {"value": 7}
        assert ledger.get("receiver", "uncertain")["state"] == "unknown"
        assert ledger.cancel("receiver", "released")["reservation_state"] == "released"
        assert ledger.cancel("receiver", "dispatched")["reservation_state"] == "held"
        assert ledger.cancel("receiver", "reserved")["reservation_state"] == "released"
        assert ledger.cancel("receiver", "reserved")["reservation_state"] == "released"
        with restored.engine.connect() as conn:
            assert conn.execute(select(budgets.c.remaining)).scalar_one() == 7


@pytest.mark.parametrize("interrupted", [False, True])
def test_actual_030_upgrade_preserves_execution_and_unknown_history(unmigrated_store, interrupted):
    from collective_intelligence_overlay.calls import RemoteCalls, remote_calls
    from collective_intelligence_overlay.invocations import InvocationStore, invocations
    from collective_intelligence_overlay.opportunities import Goal
    from collective_intelligence_overlay.reobservation import cause_id, instances, requests
    from collective_intelligence_overlay.steps import selections

    store = unmigrated_store
    fixture = seed_release(store, "030")
    old = MetaData()
    old.reflect(store.engine)
    preserved = tuple(
        old.tables[name]
        for name in ("records", "decisions", "budgets", "leases", "invocations", "work_selections")
    )

    def snapshot(target):
        with target.engine.connect() as conn:
            return {
                table.name: [
                    dict(row)
                    for row in conn.execute(
                        select(table).order_by(*table.primary_key.columns)
                    ).mappings()
                ]
                for table in preserved
            }

    original = snapshot(store)
    assert original["budgets"][0]["remaining"] == 5
    assert {row["schema_version"] for row in (r["body"] for r in original["records"])} == {
        "1",
        "2",
        "3",
    }
    if interrupted:

        def interrupt(conn, cursor, statement, parameters, context, executemany):
            if "INSERT INTO work_opportunity_instances" in statement:
                raise RuntimeError("interrupted observation projection")

        event.listen(store.engine, "after_cursor_execute", interrupt)
        try:
            with pytest.raises(RuntimeError, match="observation projection"):
                migrate(store.engine)
        finally:
            event.remove(store.engine, "after_cursor_execute", interrupt)
        assert snapshot(store) == original
        assert "work_opportunity_instances" not in inspect(store.engine).get_table_names()
        with store.engine.connect() as conn:
            assert (
                conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0012"
            )
    migrate(store.engine)
    migrate(store.engine)
    assert snapshot(store) == original
    goal = Goal.model_validate(fixture["goal"])
    with store.engine.connect() as conn:
        projection = conn.execute(select(instances)).mappings().one()
        assert projection["cause_id"] == cause_id("receiver", goal.id)
        assert projection["reissue_count"] is None and projection["last_reissued_at"] is None
        assert projection["reissue_reason"] is None and projection["new_attempt_requested"] is False
        selection = conn.execute(select(selections)).mappings().one()
        assert selection["invocation_id"] == selection["body"]["invocation_id"]
        assert selection["cause_id"] == projection["cause_id"]
        assert conn.execute(select(requests)).first() is None
        assert conn.execute(select(remote_calls)).first() is None
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0019"
        assert conn.execute(
            select(invocations.c.id).where(invocations.c.id == fixture["legacy_remote_id"])
        ).scalar_one()
    with database_copy(store) as restored:
        migrate(restored.engine)
        assert snapshot(restored) == original
        for row in original["records"]:
            verify(row["envelope"], restored.principals)
        ledger = InvocationStore(restored)
        assert RemoteCalls(restored).page("receiver", invocation_id="old-parent") == ()
        legacy = ledger.get("producer", fixture["legacy_remote_id"])
        assert legacy["state"] == "unknown" and legacy["phase"] == "dispatched"
        assert legacy["reservation_state"] == "held"
        assert ledger.get("receiver", "completed")["result"] == {"value": 7}
        assert ledger.get("receiver", "uncertain")["state"] == "unknown"
        assert ledger.cancel("receiver", "dispatched")["reservation_state"] == "held"
        assert ledger.cancel("receiver", "reserved")["reservation_state"] == "released"
        with restored.engine.connect() as conn:
            assert conn.execute(select(budgets.c.remaining)).scalar_one() == 6


def test_legacy_missing_contract_is_not_backfilled_as_a_known_cause(
    unmigrated_store, identities, opportunity
):
    from collective_intelligence_overlay.reobservation import instances

    store = unmigrated_store
    migrate(store.engine, "0012")
    assert opportunity.goal_contract_digest is None
    original = identities["receiver"].sign(opportunity)
    store.put(original)
    migrate(store.engine)
    with store.engine.connect() as conn:
        state = conn.execute(select(instances)).mappings().one()
        assert state["cause_id"] is None and state["reissue_count"] is None
        assert state["last_reissued_at"] is None and state["reissue_reason"] is None
        retained = conn.execute(select(records.c.envelope)).scalar_one()
        assert retained == original
    assert verify(retained, store.principals) == opportunity


def seed_actual_v010(store):
    fixture = json.loads((Path(__file__).parents[1] / "fixtures/v010_database.json").read_text())
    assert fixture["created_by"] == "collective-intelligence-overlay==0.1.0"
    store.principals = {
        name: Principal(
            Key.from_dict(item["keyid"], item["key"]),
            item["trust_group"],
            frozenset(item["methods"]),
        )
        for name, item in fixture["principals"].items()
    }
    migrate(store.engine, "0001")
    old_schema = MetaData()
    old_schema.reflect(store.engine)
    with store.engine.begin() as conn:
        for table_name, rows in fixture["tables"].items():
            table = old_schema.tables[table_name]
            for row in rows:
                values = dict(row)
                for column in table.columns:
                    if values[column.name] is not None:
                        if isinstance(column.type, DateTime):
                            values[column.name] = datetime.fromisoformat(values[column.name])
                        elif isinstance(column.type, Numeric):
                            values[column.name] = Decimal(values[column.name])
                conn.execute(insert(table).values(**values))
    return fixture


def test_actual_010_upgrade_preserves_signed_payloads_revocations_and_budget(unmigrated_store):
    store = unmigrated_store
    fixture = seed_actual_v010(store)
    migrate(store.engine)
    migrate(store.engine)  # already applied, no duplicate projection/feed changes
    with store.engine.connect() as conn:
        upgraded = list(conn.execute(select(records)).mappings())
        assert len(upgraded) == len(fixture["tables"]["records"])
        by_key = {(r["kind"], r["issuer"], r["record_id"]): r for r in upgraded}
        for original in fixture["tables"]["records"]:
            row = by_key[original["kind"], original["issuer"], original["record_id"]]
            assert row["envelope"] == original["envelope"]
            assert row["body"] == original["body"]
            parsed = verify(row["envelope"], store.principals)
            assert parsed.schema_version == "1"
            assert row["subject_digest"] == parsed.subject.digest
            assert not store.put(original["envelope"])
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == Decimal(7)
        upgraded_leases = {row["task_id"]: row for row in conn.execute(select(leases)).mappings()}
        assert upgraded_leases["in-flight"]["reservation"] == Decimal(2)
        assert upgraded_leases["in-flight"]["state"] == "active"
        assert upgraded_leases["finished"]["state"] == "complete"
        assert upgraded_leases["finished"]["actual"] == Decimal(1)
        assert {r.verdict for r in store.evidence()} == {"PASS", "FAIL", "UNKNOWN"}
        assert len(store.revocations()) == 1
        assert len(store.capabilities()) == 2  # colliding old subject; issuers remain distinct


def test_interrupted_backfill_rolls_back_and_resumes_without_rewriting(unmigrated_store):
    store = unmigrated_store
    fixture = seed_actual_v010(store)
    failed = False

    def interrupt(conn, cursor, statement, parameters, context, executemany):
        nonlocal failed
        if "UPDATE records SET sequence" in statement and not failed:
            failed = True
            raise RuntimeError("injected migration interruption")

    event.listen(store.engine, "after_cursor_execute", interrupt)
    try:
        with pytest.raises(RuntimeError, match="migration interruption"):
            migrate(store.engine)
    finally:
        event.remove(store.engine, "after_cursor_execute", interrupt)
    assert failed
    assert "sequence" not in {c["name"] for c in inspect(store.engine).get_columns("records")}
    with store.engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0001"
    migrate(store.engine)
    with store.engine.connect() as conn:
        assert len(conn.execute(select(records)).all()) == len(fixture["tables"]["records"])


@contextmanager
def database_copy(store):
    prefix = json.loads(os.environ.get("CIO_PG_TOOL_PREFIX", "[]"))
    if not prefix and (not shutil.which("pg_dump") or not shutil.which("pg_restore")):
        pytest.skip("real pg_dump/pg_restore required; set CIO_PG_TOOL_PREFIX for WSL")
    assert isinstance(prefix, list) and all(isinstance(item, str) for item in prefix)
    url = store.engine.url
    environment = os.environ.copy()
    if url.password:
        environment["PGPASSWORD"] = url.password
    connection = ["-h", url.host, "-p", str(url.port or 5432), "-U", url.username]
    dump = subprocess.run(
        [*prefix, "pg_dump", *connection, "--format=custom", "--dbname", url.database],
        check=True,
        capture_output=True,
        env=environment,
        timeout=60,
    ).stdout
    assert dump.startswith(b"PGDMP")
    database = "cio_restore_" + uuid4().hex
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    restored = None
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{database}"'))
        subprocess.run(
            [
                *prefix,
                "pg_restore",
                *connection,
                "--no-owner",
                "--no-acl",
                "--exit-on-error",
                "--dbname",
                database,
            ],
            input=dump,
            check=True,
            capture_output=True,
            env=environment,
            timeout=60,
        )
        restored = Store(
            url.set(database=database).render_as_string(hide_password=False),
            store.owner,
            store.principals,
        )
        yield restored
    finally:
        if restored is not None:
            restored.close()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))
        admin.dispose()


def test_actual_pg_backup_restore_and_upgrade(unmigrated_store):
    store = unmigrated_store
    fixture = seed_actual_v010(store)
    with database_copy(store) as restored:
        migrate(restored.engine)
        restored.reset_sync_after_restore()
        with restored.engine.connect() as conn:
            rows = list(conn.execute(select(records)).mappings())
            originals = {
                (r["kind"], r["issuer"], r["record_id"]): r for r in fixture["tables"]["records"]
            }
            assert len(rows) == len(originals)
            for row in rows:
                original = originals[row["kind"], row["issuer"], row["record_id"]]
                assert row["body"] == original["body"]
                assert row["envelope"] == original["envelope"]
                verify(row["envelope"], restored.principals)
            assert conn.execute(select(budgets.c.remaining)).scalar_one() == Decimal(7)
            saved = {r["task_id"]: r for r in conn.execute(select(leases)).mappings()}
            assert saved["in-flight"]["reservation"] == Decimal(2)
            assert saved["in-flight"]["state"] == "active"
            assert saved["finished"]["actual"] == Decimal(1)
        assert {r.verdict for r in restored.evidence()} == {"PASS", "FAIL", "UNKNOWN"}
        assert len(restored.revocations()) == 1
