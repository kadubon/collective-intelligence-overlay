import json
import os
from decimal import Decimal

import pytest
from sqlalchemy import select

from collective_intelligence_overlay.application import load_application
from collective_intelligence_overlay.artifacts import Artifacts
from collective_intelligence_overlay.operations import OwnerAlreadyRunning
from collective_intelligence_overlay.recovery import backup, verify_backup
from collective_intelligence_overlay.storage import budgets


async def test_actual_offline_pg_backup_private_assets_and_restored_intake(app_config, tmp_path):
    prefix = tuple(json.loads(os.environ.get("CIO_PG_TOOL_PREFIX", "[]")))
    config = app_config.model_copy(update={"local_development": True})
    host = load_application(config)
    original_candidate = host.overlay.store.capabilities()[0]
    host.overlay.store.set_budget("work", Decimal(25))
    artifact = Artifacts(config.artifact_directory).put(b"private original application data")
    target = tmp_path / "coherent-backup"
    try:
        with pytest.raises(OwnerAlreadyRunning):
            backup(
                config, target, operator_url=os.environ["CIO_TEST_DATABASE_URL"], pg_prefix=prefix
            )
        assert not target.exists()
    finally:
        host.close()
    result = backup(
        config, target, operator_url=os.environ["CIO_TEST_DATABASE_URL"], pg_prefix=prefix
    )
    assert result["complete"] and result["business_restore_verified"] is False
    assert verify_backup(target)["manifest_sha256"] == result["manifest_sha256"]
    manifest = json.loads((target / "manifest.json").read_bytes())
    assert config.database_url.get_secret_value() not in json.dumps(manifest)
    assert (target / "artifacts" / artifact).read_bytes() == b"private original application data"
    assert (target / "identity.pem").read_bytes() == config.private_key.read_bytes()
    assert (target / "database.dump").read_bytes().startswith(b"PGDMP")
    with pytest.raises(FileExistsError):
        backup(config, target, operator_url=os.environ["CIO_TEST_DATABASE_URL"], pg_prefix=prefix)
    # Restore-state persists closure and does not alter budget, signed history or IDs.
    identity, overlay = config.runtime()
    overlay.store.reset_sync_after_restore()
    overlay.store.close()
    restarted = load_application(config)
    control = restarted.operations
    try:
        await control.start()
        assert control.state == "degraded" and control.reason == "RESTORE_RECONCILIATION_REQUIRED"
        assert (await control.handle("receiver", {"operation": "resume"}))["state"] == "degraded"
        assert (
            await control.handle(
                "receiver", {"operation": "invoke", "invocation_id": "unreviewed-restored-call"}
            )
        )["error"] == "SERVICE_INTAKE_CLOSED"
        assert restarted.executor.store.get("receiver", "unreviewed-restored-call") is None
        assert restarted.overlay.store.capabilities() == [original_candidate]
        with restarted.overlay.store.engine.connect() as conn:
            assert conn.execute(select(budgets.c.remaining)).scalar_one() == 25
    finally:
        await control.stop()
        restarted.close()
    (target / "artifacts" / artifact).write_bytes(b"changed")
    with pytest.raises(ValueError, match="digest mismatch"):
        verify_backup(target)


def test_interrupted_backup_has_no_accepted_manifest(app_config, tmp_path, monkeypatch):
    import collective_intelligence_overlay.recovery as recovery

    config = app_config.model_copy(update={"local_development": True})
    target = tmp_path / "interrupted-backup"

    def interrupted(*_, **__):
        raise TimeoutError("injected pg_dump interruption")

    monkeypatch.setattr(recovery.subprocess, "run", interrupted)
    with pytest.raises(TimeoutError):
        backup(
            config,
            target,
            operator_url=os.environ["CIO_TEST_DATABASE_URL"],
            pg_prefix=("explicit-wrapper",),
        )
    assert target.exists() and not (target / "manifest.json").exists()
    with pytest.raises(FileNotFoundError):
        verify_backup(target)
