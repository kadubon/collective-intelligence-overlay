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
