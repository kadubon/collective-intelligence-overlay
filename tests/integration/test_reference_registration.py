import importlib.util
from datetime import timedelta
from pathlib import Path

import pytest

from collective_intelligence_overlay.bindings import ExecutionContext, Registry
from collective_intelligence_overlay.models import Evidence, Revocation, now
from collective_intelligence_overlay.overlay import AdmissionDenied
from collective_intelligence_overlay.reference import verify_csv
from collective_intelligence_overlay.security import digest


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
