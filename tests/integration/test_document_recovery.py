"""Actual unrewound PostgreSQL originals versus pg_dump/pg_restore rollback."""

import json
import os
import shutil
from datetime import timedelta
from decimal import Decimal

import pytest
from test_production_recovery_review import restored_database

from collective_intelligence_overlay.application import ApplicationHost, load_application
from collective_intelligence_overlay.bindings import ExecutionContext, Target, fingerprint
from collective_intelligence_overlay.calls import RemoteCalls, call_instance
from collective_intelligence_overlay.models import Event, Subject, now
from collective_intelligence_overlay.recovery import backup
from collective_intelligence_overlay.starter.application import configure
from collective_intelligence_overlay.starter.document_recovery import register


def reference_file(config, path):
    data = config.model_dump(mode="json")
    data["database_url"] = config.database_url.get_secret_value()
    path.write_text(json.dumps(data), encoding="utf-8")
    path.chmod(0o600)
    return path


@pytest.mark.parametrize("post_backup_work,clock_offset", [(False, -60), (True, 60)])
async def test_preserved_database_detects_actual_missing_work_and_maps_before_resume(
    app_config, tmp_path, post_backup_work, clock_offset
):
    config = app_config.model_copy(update={"local_development": True})
    reference = reference_file(config, tmp_path / "operator-preserved-config.json")
    source = load_application(config)
    register(source, reference)
    source.overlay.store.set_budget("work", Decimal(10))
    binding = source.registry.inspect("word-count")
    context = ExecutionContext(caller="receiver", purpose="verification", environment={})
    original = await source.executor.invoke(
        "before-backup", binding.id, binding.digest, {"text": "preserved 文書"}, context
    )
    assert original["state"] == "completed"
    source.close()
    directory = tmp_path / "coherent-backup"
    backup(
        config,
        directory,
        operator_url=os.environ["CIO_TEST_DATABASE_URL"],
        pg_prefix=tuple(json.loads(os.environ.get("CIO_PG_TOOL_PREFIX", "[]"))),
    )
    source = load_application(config)
    register(source, reference)
    try:
        with restored_database(config, directory / "database.dump") as restored:
            restored_artifacts = tmp_path / "restored-artifacts"
            shutil.copytree(directory / "artifacts", restored_artifacts)
            restored = restored.model_copy(update={"artifact_directory": restored_artifacts})
            host = load_application(restored)
            query = register(host, reference)
            host.overlay.store.reset_sync_after_restore()
            control = host.operations
            await control.start()
            try:
                assert control.state == "degraded"
                busy = await host.recovery.review("receiver", "source-active", query.id, {})
                assert busy["business_state"] == "unknown"
                proof = json.loads(host.config.artifacts().get(busy["observation_digest"]))
                assert proof["observation"]["reason"] == "REFERENCE_OWNER_ACTIVE"
                # Preserve a new, genuinely signed fixture observation carrying
                # skewed record time. It references the actual private query
                # proof; no existing envelope or admission clock is rewritten.
                generation = proof["state"]["generation"]
                shifted = Event(
                    issuer="receiver",
                    subject=Subject(
                        id="recovery-review",
                        version=generation,
                        digest=busy["observation_digest"],
                    ),
                    action="recommendation",
                    task_id=generation,
                    attempt_id="clock-observation",
                    correlation_id=generation,
                    occurred_at=now() + timedelta(seconds=clock_offset),
                )
                host.overlay.store.put(host.identity.sign(shifted))
                source.close()
                matched = await host.recovery.review("receiver", "current-original", query.id, {})
                assert matched["business_state"] == "matched"
                assert host.overlay.store.restore_pending()
                assert (
                    await host.recovery.review("receiver", "current-original", query.id, {})
                    == matched
                )
                if post_backup_work:
                    # An original CAS addition is also external state; equal
                    # balances and invocation projections alone cannot confirm it.
                    artifacts = config.artifacts()
                    added = artifacts.put(b"post-backup staged document candidate")
                    missing_artifact = await host.recovery.review(
                        "receiver", "missing-artifact", query.id, {}
                    )
                    assert missing_artifact["business_state"] == "unknown"
                    proof = json.loads(
                        host.config.artifacts().get(missing_artifact["observation_digest"])
                    )
                    assert proof["observation"]["reason"] == "REFERENCE_POST_BACKUP_MISMATCH"
                    assert (
                        proof["observation"]["allowance_remaining"]
                        == proof["state"]["allowance_remaining"]
                    )
                    # Explicitly copy the exact original bytes, then reobserve.
                    # No original record, balance or UNKNOWN receipt is rewritten.
                    assert host.config.artifacts().put(artifacts.get(added)) == added
                    repaired = await host.recovery.review(
                        "receiver", "artifact-transferred", query.id, {}
                    )
                    assert repaired["business_state"] == "matched"
                    assert host.overlay.store.restore_pending()
                    source = load_application(config)
                    register(source, reference)
                    target = Target(
                        kind="a2a",
                        name="words",
                        peer="producer",
                        endpoint="https://producer.example.test/",
                        interface_digest="a" * 64,
                        implementation_identity="remote-unknown",
                    )
                    # This persisted mapping control is not a network execution.
                    # It proves that equal restored/source allowances are insufficient.
                    args = {"text": "preserved 文書"}
                    call = RemoteCalls(source.overlay.store).bind(
                        call_instance(
                            "receiver",
                            "post-backup-child",
                            None,
                            fingerprint(["receiver", "receiver", "before-backup"]),
                            {"caller": "receiver", "arguments": args},
                        ),
                        binding,
                        target,
                        args,
                    )
                    source.close()
                    missing_map = await host.recovery.review(
                        "receiver", "missing-map", query.id, {}
                    )
                    assert missing_map["business_state"] == "unknown"
                    proof = json.loads(
                        host.config.artifacts().get(missing_map["observation_digest"])
                    )
                    assert proof["observation"]["reason"] == "REFERENCE_POST_BACKUP_MISMATCH"
                    assert (
                        proof["observation"]["allowance_remaining"]
                        == proof["state"]["allowance_remaining"]
                    )
                    assert RemoteCalls(host.overlay.store).get("receiver", call.call_key) is None
                    source = load_application(config)
                    register(source, reference)
                    actual = await source.executor.invoke(
                        "after-backup",
                        binding.id,
                        binding.digest,
                        {"text": "actual post backup consumption"},
                        context,
                    )
                    assert actual["state"] == "completed"
                    source.close()
                    missing_work = await host.recovery.review(
                        "receiver", "missing-work", query.id, {}
                    )
                    assert missing_work["business_state"] == "unknown"
                    proof = json.loads(
                        host.config.artifacts().get(missing_work["observation_digest"])
                    )
                    assert proof["observation"]["allowance_remaining"]["work"] == "8.000000000"
                    assert proof["state"]["allowance_remaining"]["work"] == "9.000000000"
                    assert host.executor.store.get("receiver", "after-backup") is None
                    assert (await control.handle("receiver", {"operation": "resume"}))[
                        "state"
                    ] == "degraded"
                    assert host.overlay.store.restore_pending()
                else:
                    assert (await control.handle("receiver", {"operation": "resume"}))[
                        "state"
                    ] == "ready"
                    assert not host.overlay.store.restore_pending()
                assert host.executor.store.get("receiver", "before-backup") == original
                assert host.overlay.store.evidence() == []
            finally:
                await control.stop()
                host.close()
    finally:
        source.close()


async def test_restored_database_cannot_serve_as_its_own_external_reference(app_config, tmp_path):
    host = ApplicationHost(app_config)
    configure(host)
    try:
        host.overlay.store.set_budget("work", Decimal(10))
        reference = reference_file(app_config, tmp_path / "self-config.json")
        query = register(host, reference)
        host.overlay.store.reset_sync_after_restore()
        observed = await host.recovery.review("receiver", "self-reference", query.id, {})
        assert observed["business_state"] == "unknown"
        proof = json.loads(host.config.artifacts().get(observed["observation_digest"]))
        assert proof["observation"]["reason"] == "REFERENCE_NOT_UNRESTORED"
        assert host.overlay.store.restore_pending()
    finally:
        host.close()
