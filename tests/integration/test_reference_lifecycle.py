from decimal import Decimal

import pytest
from sqlalchemy import select

from collective_intelligence_overlay.operations import OwnerAlreadyRunning
from collective_intelligence_overlay.reference_peer import load_reference
from collective_intelligence_overlay.storage import budgets, records


def preserved_state(host):
    with host.overlay.store.engine.connect() as conn:
        return (
            conn.execute(select(records.c.envelope).order_by(records.c.sequence)).all(),
            conn.execute(select(budgets).order_by(budgets.c.unit)).all(),
        )


async def test_reference_keeps_original_bindings_and_uses_owner_drain(app_config):
    config = app_config.model_copy(
        update={
            "application": None,
            "local_development": True,
            "execution_environment": {"reference": "1"},
        }
    )
    host = load_reference(config)
    control = host.operations
    assert control is not None
    try:
        await control.start()
        assert control.state == "ready"
        with pytest.raises(OwnerAlreadyRunning):
            load_reference(config)
        assert host.overlay.store.capabilities() == []
        registrations = await control.handle("receiver", {"operation": "reference-register"})
        binding = host.registry.inspect("csv-sum")
        assert binding.scope.environment == {"reference": "1"}
        host.overlay.store.set_budget("work", Decimal(10))
        request = {
            "operation": "invoke",
            "invocation_id": "legacy-reference-probe",
            "binding_id": binding.id,
            "binding_digest": binding.digest,
            "arguments": {"source": "category,amount\na,3.50\n"},
            "purpose": "verification",
        }
        result = await control.handle("receiver", request)
        assert result["state"] == "completed"
        original = preserved_state(host)
        await control.handle("receiver", {"operation": "drain"})
        assert (await control.handle("receiver", {**request, "invocation_id": "after-drain"}))[
            "error"
        ] == "SERVICE_INTAKE_CLOSED"
        assert (await control.handle("receiver", {"operation": "reference-register"}))[
            "error"
        ] == "SERVICE_INTAKE_CLOSED"
        assert preserved_state(host) == original
        assert host.executor.store.get("receiver", "after-drain") is None
    finally:
        await control.stop()
        host.close()
    restarted = load_reference(config)
    control = restarted.operations
    assert control is not None
    try:
        await control.start()
        assert (
            await control.handle("receiver", {"operation": "reference-register"}) == registrations
        )
        assert restarted.executor.store.get("receiver", "legacy-reference-probe") == result
    finally:
        await control.stop()
        restarted.close()


@pytest.mark.parametrize(
    "content,reason",
    [
        (" " * 262145, "settings exceed bound"),
        ('{"recovery_reference_config":true}', "config path exceeds bound"),
        ("[]", "settings must be an object"),
    ],
    ids=("oversized", "nontext-path", "nonobject"),
)
def test_invalid_private_reference_settings_release_owner_lock(
    app_config, tmp_path, content, reason
):
    path = tmp_path / "private-reference-settings.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=reason):
        load_reference(app_config.model_copy(update={"application_settings": path}))
    good = load_reference(app_config)
    try:
        assert good.overlay.store.capabilities() == []
        assert good.operations is not None and good.operations.lock.check()
    finally:
        good.close()
