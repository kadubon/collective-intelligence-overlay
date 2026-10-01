"""A physical independent-checker outage creates no PASS or implicit retry."""

import asyncio
import json

from document_recovery_protocol import originals

from collective_intelligence_overlay.adapters.a2a import send
from collective_intelligence_overlay.bindings import Binding, fingerprint
from collective_intelligence_overlay.invocations import InvocationStore
from collective_intelligence_overlay.queries import RecordQuery


async def run(configs, identities, processes, mesh, start, stop, call, target, checker, root):
    target = Binding.model_validate(target)
    attempt = "checker-physical-outage-original"
    request = {
        "operation": "app.request-document-check",
        "name": "triage",
        "attempt": attempt,
        "binding_digest": target.digest,
        "checker_digest": checker.digest,
    }
    evidence_id = "checked-" + fingerprint(["verifier", attempt])

    def absent():
        _, verifier = configs["verifier"].runtime()
        _, receiver = configs["receiver"].runtime()
        try:
            assert not verifier.store.record_page(
                RecordQuery(
                    kinds=("evidence",),
                    issuer="verifier",
                    record_id=evidence_id,
                ),
                limit=1,
            ).items
            assert InvocationStore(receiver.store).get("verifier", attempt) is None
        finally:
            verifier.store.close()
            receiver.store.close()

    await asyncio.to_thread(absent)
    before = {
        owner: await asyncio.to_thread(originals, config) for owner, config in configs.items()
    }
    effects = mesh.mcp_audit.read_bytes()
    old = processes["verifier"]
    await stop("verifier", crash=True)
    assert old.poll() is not None
    try:
        await send(configs["receiver"], identities["receiver"], "verifier", request)
    except Exception as error:
        assert type(error).__name__ in {"InternalError", "AgentCardResolutionError"}
        failure = type(error).__name__
    else:
        raise AssertionError("stopped checker returned evidence")
    await asyncio.to_thread(absent)
    assert mesh.mcp_audit.read_bytes() == effects
    for owner in ("producer", "receiver"):
        assert (await call(owner, operation="status"))["state"] == "ready"
    for owner, config in configs.items():
        assert await asyncio.to_thread(originals, config) == before[owner]
    (root / "checker-outage-observations.json").write_text(
        json.dumps(
            {
                "injection": "checker unavailability",
                "attempt": attempt,
                "pid": old.pid,
                "physical_exit": old.returncode,
                "transport_error": failure,
                "request_outcome": "UNKNOWN",
                "independent_pass_created": False,
                "original_probe_and_evidence_absent": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    await start("verifier")
    await asyncio.to_thread(absent)
    # The operator explicitly performs the same read-only check after proving
    # no earlier checker/probe receipt exists. This is not an effect retry.
    checked = await send(configs["receiver"], identities["receiver"], "verifier", request)
    assert checked["evidence"]["id"] == evidence_id
    assert checked["evidence"]["verdict"] == "PASS"
    retained = await asyncio.to_thread(originals, configs["verifier"])
    effects_after = mesh.mcp_audit.read_bytes()
    assert await send(configs["receiver"], identities["receiver"], "verifier", request) == checked
    assert await asyncio.to_thread(originals, configs["verifier"]) == retained
    assert mesh.mcp_audit.read_bytes() == effects_after
