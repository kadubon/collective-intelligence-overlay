from decimal import Decimal

import pytest

from collective_intelligence_overlay.application import load_application
from collective_intelligence_overlay.bindings import ExecutionContext


async def test_installed_factory_uses_executor_and_preserves_generated_status(app_config):
    host = load_application(app_config)
    try:
        binding = host.registry.inspect("word-count")
        original = host.overlay.store.capabilities()[0]
        host.overlay.store.set_budget("work", Decimal(100))
        args = {"text": "independent 文書\nthree"}
        ordinary = await host.executor.invoke(
            "ordinary-unchecked",
            binding.id,
            binding.digest,
            args,
            ExecutionContext(caller="receiver", environment={}),
        )
        assert ordinary["state"] == "unknown"
        probe = await host.executor.invoke(
            "owner-readonly-probe",
            binding.id,
            binding.digest,
            args,
            ExecutionContext(caller="receiver", purpose="verification", environment={}),
        )
        assert probe["state"] == "completed"
        assert probe["result"] == {"words": 3}
        retry = await host.executor.invoke(
            "owner-readonly-probe",
            binding.id,
            binding.digest,
            args,
            ExecutionContext(caller="receiver", purpose="verification", environment={}),
        )
        assert retry == probe
        assert host.overlay.store.evidence() == []
        with pytest.raises(ValueError, match="owner operation"):
            await host.handle("producer", {"operation": "run"})
    finally:
        host.close()
    restarted = load_application(app_config)
    try:
        assert restarted.overlay.store.capabilities() == [original]
        assert restarted.executor.store.get("receiver", "owner-readonly-probe") == probe
        assert restarted.overlay.store.evidence() == []
    finally:
        restarted.close()


def test_factory_must_be_operator_selected(app_config):
    for name in ("https://peer.example/factory", "app.py", "module:factory.extra"):
        with pytest.raises(ValueError, match="module:factory"):
            load_application(app_config, name)


async def test_installed_operation_namespace_grants_and_drain(app_config):
    host = load_application(app_config.model_copy(update={"local_development": True}))
    calls = []

    async def handle(caller, data):
        calls.append(caller)
        return {"observed": True}

    host.register_operation("app.observe", handle, callers=("receiver",))
    for name, callers in (
        ("invoke", ("receiver",)),
        ("app.observe", ("receiver",)),
        ("app.other", ("unconfigured",)),
    ):
        with pytest.raises(ValueError, match="namespace|pinned callers"):
            host.register_operation(name, handle, callers=callers)
    control = host.operations
    try:
        await control.start()
        assert control.state == "ready"
        with pytest.raises(ValueError, match="operation grant"):
            await control.handle("producer", {"operation": "app.observe"})
        assert not calls
        assert await control.handle("receiver", {"operation": "app.observe"}) == {"observed": True}
        await control.handle("receiver", {"operation": "drain"})
        assert (await control.handle("receiver", {"operation": "app.observe"}))[
            "error"
        ] == "SERVICE_INTAKE_CLOSED"
        assert calls == ["receiver"]
    finally:
        await control.stop()
        host.close()


async def test_original_observation_read_never_resigns_with_current_key(app_config, monkeypatch):
    from collective_intelligence_overlay.models import Event

    host = load_application(app_config)
    try:
        event = Event(
            issuer=host.config.owner,
            subject=host.overlay.store.capabilities()[0].subject,
            action="recommendation",
            task_id="historical-observation",
            attempt_id="original-observation",
            correlation_id="historical-observation",
        )
        original = host.identity.sign(event)
        host.overlay.store.put(original)

        async def historical(*args, **kwargs):
            return event

        def forbid_signing(*args, **kwargs):
            raise AssertionError("a read cannot grant a historical observation a new signature")

        monkeypatch.setattr(host.reconciliations, "observe", historical)
        monkeypatch.setattr(host.identity, "sign", forbid_signing)
        result = await host.handle(
            "receiver",
            {"operation": "reconcile", "call_key": "a" * 64, "command_id": "historical-read"},
        )
        assert result["envelope"] == original
    finally:
        host.close()
