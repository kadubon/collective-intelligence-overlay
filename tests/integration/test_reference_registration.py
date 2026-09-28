import importlib.util
from datetime import timedelta
from pathlib import Path

import pytest

from collective_intelligence_overlay.bindings import ExecutionContext, Registry
from collective_intelligence_overlay.models import Evidence, Revocation, now
from collective_intelligence_overlay.overlay import AdmissionDenied
from collective_intelligence_overlay.reference import verify_csv
from collective_intelligence_overlay.security import digest


def test_registered_checker_binds_evidence_to_exact_contract(overlay):
    from collective_intelligence_overlay.reference_bindings import (
        check_registered,
        register_reference,
    )

    binding, cap = register_reference(Registry(overlay), "verifier")[0]
    source = "category,amount\na,3.50\n"
    observed = check_registered(
        "verifier", cap, binding, source, {"rows": 1, "total": "3.50"}, "receiver"
    )
    assert observed.verdict == "PASS"
    assert observed.binding_digest == binding.digest
    assert observed.subject == cap.subject
    incorrect = check_registered(
        "verifier", cap, binding, source, {"rows": 1, "total": "99.00"}, "receiver"
    )
    assert incorrect.verdict == "FAIL"
    for update in ({"claim": "different claim"}, {"binding_digest": "0" * 64}):
        with pytest.raises(ValueError, match="contract mismatch"):
            check_registered(
                "verifier", cap.model_copy(update=update), binding, source, {}, "receiver"
            )


async def test_reference_functions_register_and_check_each_child(overlay, identities):
    path = Path(__file__).parents[2] / "examples/reference_registration.py"
    spec = importlib.util.spec_from_file_location("registered_reference_example", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    registry = Registry(overlay)
    installed = module.register_reference(registry, "verifier")
    probe = ExecutionContext(
        caller="verifier", environment={"reference": "1"}, purpose="verification"
    )
    use = ExecutionContext(caller="receiver", environment={"reference": "1"})
    source = "category,amount\nA,1.25\nB,2.75\n"
    inputs = ({"source": source}, {"summary": {"rows": 2, "total": "4.00"}}, {"source": source})
    for (binding, cap), arguments in zip(installed, inputs, strict=True):
        overlay.store.put(identities["receiver"].sign(cap))
        with pytest.raises(AdmissionDenied):
            await registry.execute(binding.id, binding.digest, arguments, use)
        result = await registry.execute(binding.id, binding.digest, arguments, probe)
        if binding.id == "csv-sum":
            assert verify_csv(source, result)
        else:
            assert result == "<p>Rows: 2; total: 4.00</p>"
        evidence = Evidence(
            schema_version="2",
            binding_digest=binding.digest,
            issuer="verifier",
            subject=cap.subject,
            claim=cap.claim,
            scope=cap.scope,
            receivers=("receiver",),
            verdict="PASS",
            method="csv-check",
            verifier_version="1",
            artifact_digest=digest(str(result).encode()),
            expires_at=now() + timedelta(hours=1),
        )
        overlay.store.put(identities["verifier"].sign(evidence))
    binding, _ = installed[-1]
    result = await registry.execute(
        binding.id, binding.digest, {"source": "category,amount\nC,9.10\n"}, use
    )
    assert result == "<p>Rows: 1; total: 9.10</p>"
    withdrawal = Revocation(issuer="receiver", subject=installed[0][1].subject, reason="retired")
    overlay.store.put(identities["receiver"].sign(withdrawal))
    with pytest.raises(AdmissionDenied):
        await registry.execute(binding.id, binding.digest, {"source": source}, use)


async def test_reference_peer_publishes_registered_candidates_and_durable_probes(
    overlay, identities, records, tmp_path
):
    from decimal import Decimal
    from types import SimpleNamespace

    from collective_intelligence_overlay.reference_peer import ReferencePeerService

    config = SimpleNamespace(
        owner="receiver",
        artifact_directory=tmp_path / "artifacts",
        max_seconds=30,
        execution_environment={"reference": "1"},
        policy=overlay.policy.settings,
        runtime=lambda: (identities["receiver"], overlay),
    )
    service = ReferencePeerService(config)
    with pytest.raises(ValueError, match="owner-only"):
        await service.handle("other", {"operation": "reference-register"})
    registrations = await service.handle("receiver", {"operation": "reference-register"})
    assert len(registrations["registrations"]) == 3
    assert await service.handle("receiver", {"operation": "reference-register"}) == registrations
    binding, cap = service.registered[0]
    overlay.store.set_budget("work", Decimal(10))
    request = {
        "operation": "invoke",
        "binding_id": binding.id,
        "binding_digest": binding.digest,
        "invocation_id": "before-pass",
        "arguments": {"source": "category,amount\na,3.50\n"},
    }
    assert (await service.handle("receiver", request))["state"] == "unknown"
    probe = await service.handle(
        "verifier", {**request, "invocation_id": "probe", "purpose": "verification"}
    )
    assert probe["state"] == "completed"
    assert verify_csv(request["arguments"]["source"], probe["result"])
    _, evidence = records
    evidence = evidence.model_copy(
        update={
            "id": "registered-reference-check",
            "schema_version": "2",
            "binding_digest": binding.digest,
            "subject": cap.subject,
            "scope": cap.scope,
            "claim": cap.claim,
        }
    )
    overlay.store.put(identities["verifier"].sign(evidence))
    result = await service.handle("receiver", {**request, "invocation_id": "ordinary"})
    assert result["state"] == "completed"
    restarted = ReferencePeerService(config)
    assert await restarted.handle("receiver", {"operation": "reference-register"}) == registrations
    lookup = await restarted.handle(
        "receiver", {"operation": "invocation", "invocation_id": "ordinary"}
    )
    assert lookup["invocation"] == result
