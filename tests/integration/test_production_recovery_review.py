import copy
import json
import os
import subprocess
from contextlib import contextmanager
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.engine import make_url

from collective_intelligence_overlay.application import load_application
from collective_intelligence_overlay.bindings import ExecutionContext, callable_digest, fingerprint
from collective_intelligence_overlay.config import Peer
from collective_intelligence_overlay.recovery import RecoveryObservation, backup, verify_backup
from collective_intelligence_overlay.storage import Conflict, Store, budgets, feed_state, records
from collective_intelligence_overlay.synchronization import Feed, FeedFilter, Receiver


@contextmanager
def restored_database(config, dump):
    url = make_url(os.environ["CIO_TEST_DATABASE_URL"])
    name = "cio_recovery_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
        prefix = json.loads(os.environ.get("CIO_PG_TOOL_PREFIX", "[]"))
        environment = os.environ.copy()
        if url.password:
            environment["PGPASSWORD"] = url.password
        with dump.open("rb") as source:
            subprocess.run(
                [
                    *prefix,
                    "pg_restore",
                    "--exit-on-error",
                    "--no-owner",
                    "--no-acl",
                    "-h",
                    url.host,
                    "-p",
                    str(url.port),
                    "-U",
                    url.username,
                    "--dbname",
                    name,
                ],
                stdin=source,
                capture_output=True,
                check=True,
                timeout=60,
                env=environment,
            )
        yield config.model_copy(
            update={
                "database_url": SecretStr(
                    url.set(database=name).render_as_string(hide_password=False)
                )
            }
        )
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def register_query(host, witness, calls):
    async def query(arguments):
        state = arguments["state"]
        calls.append(state["generation"])
        # The external witness is independent of restored balances/receipts. If
        # unavailable or different, the application cannot assert current match.
        return RecoveryObservation(
            owner=host.config.owner,
            generation=state["generation"],
            state_digest=state["state_digest"],
            post_backup_state=witness["state"],
            observation_digest=fingerprint(witness),
            allowance_remaining=witness["allowance"],
            uncertain_original_calls=tuple(tuple(v) for v in witness["originals"]),
            reason="EXTERNAL_APPLICATION_QUERY",
        ).model_dump(mode="json")

    original = host.registry.inspect("word-count")
    binding = original.model_copy(
        update={
            "id": "business-recovery-query",
            "subject": original.subject.model_copy(
                update={"id": "business-recovery-query", "digest": callable_digest(query)}
            ),
            "target": original.target.model_copy(
                update={
                    "name": "business-recovery-query",
                    "interface_digest": callable_digest(query),
                }
            ),
            "input_schema": {"type": "object", "required": ["state", "arguments"]},
            "output_schema": {"type": "object"},
        }
    )
    host.registry.register_local(binding, query, lambda _: True)
    candidate = host.overlay.store.capabilities()[0].model_copy(
        update={
            "subject": binding.subject,
            "binding_digest": binding.digest,
            "entrypoint": binding.id,
        }
    )
    host.publish_candidate(binding, candidate)
    host.recovery.register(binding.id)
    return binding.id


@pytest.mark.parametrize("separate_operator", [False, True])
async def test_actual_backup_restore_review_restart_and_explicit_resume(
    app_config, tmp_path, separate_operator
):
    config = app_config.model_copy(
        update={
            "local_development": True,
            "operator_callers": ("other",) if separate_operator else (),
        }
    )
    resume_caller = "other" if separate_operator else "receiver"
    source = load_application(config)
    source.overlay.store.set_budget("work", Decimal(25))
    witness = {
        "state": "matched",
        "allowance": {"work": "25"},
        "originals": [["receiver", "original-unknown"]],
    }
    queries = []
    checker = register_query(source, witness, queries)
    binding = source.registry.inspect("word-count")
    original = await source.executor.invoke(
        "original-unknown",
        binding.id,
        binding.digest,
        {"text": "unverified original"},
        ExecutionContext(caller="receiver", environment={}),
    )
    assert original["state"] == "unknown"
    with source.overlay.store.engine.connect() as conn:
        original_bytes = list(conn.execute(select(records.c.envelope)).scalars())
    source.close()
    directory = tmp_path / "actual-offline-backup"
    backup(
        config,
        directory,
        operator_url=os.environ["CIO_TEST_DATABASE_URL"],
        pg_prefix=tuple(json.loads(os.environ.get("CIO_PG_TOOL_PREFIX", "[]"))),
    )
    assert verify_backup(directory)["complete"]
    with restored_database(config, directory / "database.dump") as restored:
        host = load_application(restored)
        register_query(host, witness, queries)
        host.overlay.store.reset_sync_after_restore()
        operations = host.operations
        await operations.start()
        try:
            assert (await operations.handle(resume_caller, {"operation": "resume"}))[
                "state"
            ] == "degraded"
            witness["state"] = "unknown"
            request = {
                "operation": "recovery_review",
                "checker": checker,
                "command_id": "unknown-review",
                "arguments": {"incident": "backup-test"},
            }
            unknown = await operations.handle("receiver", request)
            assert unknown["business_state"] == "unknown"
            assert await operations.handle("receiver", request) == unknown
            assert len(queries) == 1
            assert (await operations.handle(resume_caller, {"operation": "resume"}))[
                "state"
            ] == "degraded"
            # A lower external allowance cannot be replaced by the restored balance.
            witness["state"], witness["allowance"] = "matched", {"work": "24"}
            mismatch = await operations.handle(
                "receiver", request | {"command_id": "allowance-mismatch"}
            )
            assert mismatch["business_state"] == "unknown"
            assert host.overlay.store.restore_pending()
            witness["allowance"] = {"work": "25"}
            request["command_id"] = "matched-review"
            accepted = await operations.handle("receiver", request)
            assert accepted["business_state"] == "matched"
            assert host.overlay.store.restore_pending()
            assert (await operations.handle("receiver", {"operation": "status"}))[
                "state"
            ] == "degraded"
            assert (
                await operations.handle(
                    "receiver", {"operation": "invoke", "invocation_id": "before-resume"}
                )
            )["error"] == "SERVICE_INTAKE_CLOSED"
        finally:
            await operations.stop()
            host.close()
        # Review survives restart, but boot remains closed. Explicit resume rechecks
        # the exact state and pinned query before opening; original UNKNOWN survives.
        restarted = load_application(restored)
        register_query(restarted, witness, queries)
        control = restarted.operations
        await control.start()
        try:
            assert control.state == "degraded"
            assert await control.handle("receiver", request) == accepted
            assert len(queries) == 3
            if separate_operator:
                with pytest.raises(ValueError, match="operator control grant"):
                    await control.handle("receiver", {"operation": "resume"})
                assert restarted.overlay.store.restore_pending()
            assert (await control.handle(resume_caller, {"operation": "resume"}))[
                "state"
            ] == "ready"
            assert not restarted.overlay.store.restore_pending()
            assert restarted.executor.store.get("receiver", "original-unknown") == original
            assert restarted.executor.store.get("receiver", "before-resume") is None
            with restarted.overlay.store.engine.connect() as conn:
                after = list(conn.execute(select(records.c.envelope)).scalars())
                assert conn.execute(select(budgets.c.remaining)).scalar_one() == 25
            assert all(value in after for value in original_bytes)
            assert restarted.overlay.store.evidence() == []
        finally:
            await control.stop()
            restarted.close()


async def test_recovery_requires_new_full_sync_and_rechecks_drift(app_config, identities):
    config = app_config.model_copy(
        update={
            "local_development": True,
            "peers": (Peer(identity="producer", url="https://producer.example.test/"),),
        }
    )
    host = load_application(config)
    host.overlay.store.set_budget("work", Decimal(10))
    witness = {"state": "matched", "allowance": {"work": "10"}, "originals": []}
    checker = register_query(host, witness, [])
    host.overlay.store.reset_sync_after_restore()
    try:
        with pytest.raises(ValueError, match="synchronization"):
            host.recovery.inspect()
        provider = Store(
            config.database_url.get_secret_value(), "producer", host.overlay.store.principals
        )
        page = Feed(provider, identities["producer"]).page("receiver", FeedFilter())
        Receiver(host.overlay.store).apply("producer", FeedFilter(), page)
        provider.close()
        state = host.recovery.inspect()
        assert state["signed_records"] == 2
        request = {"incident": "new-feed"}
        await host.recovery.review("receiver", "before-drift", checker, request)
        with host.overlay.store.engine.begin() as conn:
            conn.execute(update(budgets).where(budgets.c.unit == "work").values(remaining=9))
        with pytest.raises(Conflict, match="changed"):
            host.recovery.authorize_resume("receiver")
        assert host.overlay.store.restore_pending()
        with pytest.raises(ValueError, match="owner-only"):
            await host.recovery.review("producer", "foreign", checker, {})
        with host.overlay.store.engine.begin() as conn:
            row = conn.execute(select(records).limit(1)).mappings().one()
            changed = copy.deepcopy(row["body"])
            changed["provenance"] = "changed projection without signature"
            conn.execute(
                update(records).where(records.c.record_id == row["record_id"]).values(body=changed)
            )
        with pytest.raises(ValueError, match="projection mismatch"):
            host.recovery.inspect()
        with host.overlay.store.engine.connect() as conn:
            assert conn.execute(select(feed_state.c.restore_pending)).scalar_one()
    finally:
        host.close()


def test_legacy_restore_without_commit_boundary_stays_closed(app_config):
    host = load_application(app_config)
    try:
        host.overlay.store.reset_sync_after_restore()
        with host.overlay.store.engine.begin() as conn:
            conn.execute(update(feed_state).values(restored_sequence=None))
        with pytest.raises(ValueError, match="offline restore-state"):
            host.recovery.inspect()
        assert host.overlay.store.restore_pending()
        host.overlay.store.reset_sync_after_restore()
        assert host.recovery.inspect()["restored_sequence"] >= 0
        assert host.overlay.store.restore_pending()
    finally:
        host.close()
