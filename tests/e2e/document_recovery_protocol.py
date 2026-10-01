"""Actual TLS/A2A recovery of three owned peers, using standard PostgreSQL tools."""

import asyncio
import json
import os
import re
import shutil
import sys
from contextlib import ExitStack
from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url

from collective_intelligence_overlay.adapters.a2a import send
from collective_intelligence_overlay.bindings import Binding
from collective_intelligence_overlay.config import load_config
from collective_intelligence_overlay.recovery import backup, verify_backup
from collective_intelligence_overlay.storage import budgets, records


def restore_home(original, archive, home, stack):
    helpers = str(Path(__file__).parents[1] / "integration")
    if helpers not in sys.path:
        sys.path.insert(0, helpers)
    from test_production_recovery_review import restored_database

    restored = stack.enter_context(restored_database(original, archive / "database.dump"))
    admin_url = make_url(restored.database_url.get_secret_value())
    runtime_url = make_url(original.database_url.get_secret_value()).set(
        database=admin_url.database
    )
    role, database = runtime_url.username, runtime_url.database
    assert re.fullmatch(r"[a-z][a-z0-9_]{0,62}", role)
    assert re.fullmatch(r"cio_recovery_[0-9a-f]{32}", database)
    # pg_restore's --no-owner/--no-acl keeps DDL with the operator. Restore
    # the original role's narrow DML grant; never run a peer with the admin URL.
    admin = create_engine(admin_url, hide_parameters=True)
    try:
        with admin.begin() as conn:
            conn.execute(text(f'REVOKE CONNECT ON DATABASE "{database}" FROM PUBLIC'))
            conn.execute(text(f'GRANT CONNECT ON DATABASE "{database}" TO "{role}"'))
            conn.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
            conn.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))
            conn.execute(
                text(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
                    f'TO "{role}"'
                )
            )
            conn.execute(text(f'REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM "{role}"'))
            conn.execute(text(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}"'))
    finally:
        admin.dispose()
    shutil.copytree(archive, home)
    (home / "database-url").write_text(
        runtime_url.render_as_string(hide_password=False), encoding="utf-8"
    )
    (home / "database-url").chmod(0o600)
    shutil.copy2(
        original.application_settings.parent / "preserved-reference.json",
        home / "preserved-reference.json",
    )
    config = load_config(home / "config.json")
    assert config.database_url == SecretStr(runtime_url.render_as_string(hide_password=False))
    _, overlay = config.runtime()
    try:
        with overlay.store.engine.connect() as conn:
            assert not conn.execute(
                text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
            ).scalar_one()
            assert not conn.execute(
                text("SELECT has_table_privilege(current_user, 'alembic_version', 'UPDATE')")
            ).scalar_one()
    finally:
        overlay.store.close()
    return config


def originals(config):
    _, overlay = config.runtime()
    try:
        with overlay.store.engine.connect() as conn:
            return (
                dict(conn.execute(select(records.c.record_id, records.c.envelope)).all()),
                dict(conn.execute(select(budgets.c.unit, budgets.c.remaining)).all()),
            )
    finally:
        overlay.store.close()


def close_restored_intake(config):
    # Run the real installed CLI outside checkout. This is operator recovery,
    # before boot, not a fabricated flag or an unauthenticated HTTP operation.
    import subprocess

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "collective_intelligence_overlay.cli",
            "restore-state",
            "--config",
            str(config.private_key.parent / "config.json"),
        ],
        cwd=config.private_key.parent,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert json.loads(result.stdout)


async def run(configs, identities, start, stop, call, sync, root, mesh):
    original = configs["receiver"]
    audit = mesh.mcp_audit
    operator = os.environ["CIO_TEST_DATABASE_URL"]
    prefix = tuple(json.loads(os.environ.get("CIO_PG_TOOL_PREFIX", "[]")))
    trace = []

    async def drained():
        value = await call("receiver", operation="drain")
        assert value["state"] == "draining"
        refused = await call("receiver", operation="invoke", invocation_id="during-recovery-drain")
        assert refused["error"] == "SERVICE_INTAKE_CLOSED"
        trace.extend([value, refused])
        await stop("receiver")

    await drained()
    old = root / "recovery-old-backup"
    await asyncio.to_thread(backup, original, old, operator_url=operator, pg_prefix=prefix)
    assert await asyncio.to_thread(verify_backup, old)
    await start("receiver")
    remote = Binding.model_validate(
        (await call("receiver", operation="describe", name="remote-words"))["binding"]
    )
    request = {
        "operation": "invoke",
        "invocation_id": "post-backup-network-original",
        "binding_id": remote.id,
        "binding_digest": remote.digest,
        "arguments": {"text": "post backup actual 文書"},
    }
    completed = await call("receiver", **request)
    assert completed["state"] == "completed" and completed["result"] == {"words": 4}
    mapping = (
        await call("receiver", operation="remote_calls", invocation_id=request["invocation_id"])
    )["calls"]
    assert len(mapping) == 1
    observation_request = {
        "operation": "reconcile",
        "call_key": mapping[0]["call_key"],
        "command_id": "post-backup-network-observation",
        "invocation_id": request["invocation_id"],
        "reconciler": "document-original-result",
    }
    observation = await call("receiver", **observation_request)
    assert observation["event"]["reconciliation"]["effect"] == "confirmed"
    assert observation["event"]["reconciliation"]["independent_verification"] == "UNKNOWN"
    await drained()
    latest = root / "recovery-current-backup"
    await asyncio.to_thread(backup, original, latest, operator_url=operator, pg_prefix=prefix)
    before, allowance = await asyncio.to_thread(originals, original)
    effects = audit.read_bytes()

    with ExitStack() as stack:
        try:
            for label, archive, expected in (
                ("old", old, "unknown"),
                ("current", latest, "matched"),
            ):
                restored = await asyncio.to_thread(
                    restore_home, original, archive, root / ("restored-" + label), stack
                )
                configs["receiver"] = restored
                await asyncio.to_thread(close_restored_intake, restored)
                await start("receiver", expected_state="degraded")
                assert (await call("receiver", operation="resume"))["state"] == "degraded"
                for peer in ("producer", "verifier"):
                    await sync("receiver", peer)
                review_request = {
                    "operation": "recovery_review",
                    "command_id": "network-recovery-" + label,
                    "checker": "document-recovery-state",
                    "arguments": {},
                }
                review = await call("receiver", **review_request)
                trace.append({"case": label, "review": review, "original_mapping": mapping})
                (root / "network-recovery-observations.json").write_text(
                    json.dumps(trace, indent=2), encoding="utf-8"
                )
                assert review["business_state"] == expected, review
                assert review["independent_verification"] == "UNKNOWN"
                assert await call("receiver", **review_request) == review
                proof = json.loads(restored.artifacts().get(review["observation_digest"]))
                if expected == "unknown":
                    assert proof["observation"]["reason"] == "REFERENCE_POST_BACKUP_MISMATCH"
                    assert (
                        proof["state"]["allowance_remaining"]
                        != proof["observation"]["allowance_remaining"]
                    )
                    assert (
                        await call(
                            "receiver",
                            operation="remote_calls",
                            invocation_id=request["invocation_id"],
                        )
                    )["calls"] == []
                    provider = await send(
                        restored,
                        identities["receiver"],
                        "producer",
                        {
                            "operation": "invocation",
                            "invocation_id": mapping[0]["remote_invocation_id"],
                        },
                    )
                    assert provider["invocation"]["state"] == "completed"
                    assert provider["invocation"]["result"] == {"words": 4}
                    assert (await call("receiver", operation="resume"))["state"] == "degraded"
                else:
                    # Recover the original signed reconciliation, preserving its
                    # effect/independent-verification distinction and old bytes.
                    assert await call("receiver", **observation_request) == observation
                    assert (
                        await call(
                            "receiver",
                            operation="remote_calls",
                            invocation_id=request["invocation_id"],
                        )
                    )["calls"] == mapping
                    assert (
                        await call(
                            "receiver",
                            operation="invocation",
                            invocation_id=request["invocation_id"],
                        )
                    )["invocation"] == completed
                    assert (await call("receiver", operation="resume"))["state"] == "ready"
                    after, restored_allowance = await asyncio.to_thread(originals, restored)
                    assert all(after[key] == value for key, value in before.items())
                    assert restored_allowance == allowance
                    assert await call("receiver", **request) == completed
                assert audit.read_bytes() == effects
                await stop("receiver")
        finally:
            await stop("receiver")
            configs["receiver"] = original
    await start("receiver")
    assert await call("receiver", **request) == completed
    assert audit.read_bytes() == effects
    (root / "network-recovery-observations.json").write_text(
        json.dumps(trace, indent=2), encoding="utf-8"
    )
