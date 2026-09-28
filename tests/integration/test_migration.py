import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from securesystemslib.signer import Key
from sqlalchemy import DateTime, MetaData, Numeric, event, insert, inspect, select, text

from collective_intelligence_overlay.security import Principal, verify
from collective_intelligence_overlay.storage import budgets, leases, migrate, records


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
