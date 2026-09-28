from datetime import timedelta
from decimal import Decimal

import pytest
from agent_framework import WorkflowBuilder, WorkflowContext
from agent_framework import executor as maf_executor

from collective_intelligence_overlay.accounting import metrics
from collective_intelligence_overlay.bindings import (
    Binding,
    ExecutionContext,
    Registry,
    Target,
    active_invocation,
    callable_digest,
    fingerprint,
)
from collective_intelligence_overlay.invocations import Executor, Reservation
from collective_intelligence_overlay.lineage import FormationSession
from collective_intelligence_overlay.models import (
    Capability,
    Evidence,
    FormationInput,
    ReceiptRef,
    Revocation,
    Scope,
    Subject,
    UseRequest,
    now,
    uid,
)


async def words(arguments):
    return {"words": len(arguments["text"].split())}


async def render(arguments):
    return {"report": f"Words: {arguments['words']}"}


def binding(name, operation, issuer="receiver", components=()):
    return Binding(
        id=name,
        revision="1",
        issuer=issuer,
        registrar="receiver",
        subject=Subject(id=name, version="1", digest=callable_digest(operation)),
        scope=Scope(
            task=name,
            input_contract=name + ".in",
            output_contract=name + ".out",
            environment={"reference": "1"},
        ),
        target=Target(
            kind="local",
            name=name,
            interface_digest=callable_digest(operation),
            implementation_identity="installed",
        ),
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        callers=("receiver",),
        effects="read-only",
        components=components,
    )


def candidate(b, dependencies=()):
    return Capability(
        schema_version="2",
        binding_digest=b.digest,
        subject=b.subject,
        issuer=b.issuer,
        scope=b.scope,
        entrypoint=b.id,
        claim="document-contract",
        dependencies=tuple(d.subject for d in dependencies),
        dependency_issuers=tuple(d.issuer for d in dependencies),
        license="Apache-2.0",
        provenance="installed document application",
        classification="declared-new",
        expires_at=now() + timedelta(hours=1),
    )


def checked(store, identities, b, observed, *, seconds=3600):
    evidence = Evidence(
        schema_version="2",
        binding_digest=b.digest,
        issuer="verifier",
        subject=b.subject,
        claim="document-contract",
        scope=b.scope,
        receivers=("receiver",),
        verdict="PASS",
        method="report-check",
        verifier_version="1",
        artifact_digest=fingerprint(observed),
        expires_at=now() + timedelta(seconds=seconds),
    )
    store.put(identities["verifier"].sign(evidence))
    return evidence


async def test_actual_maf_composition_then_calibrated_formation_and_withdrawal(overlay, identities):
    store = overlay.store
    store.set_budget("work", Decimal(100))
    registry = Registry(overlay)
    runner = Executor(registry, identities["receiver"], Reservation())
    context = ExecutionContext(caller="receiver", environment={"reference": "1"})
    c1, c2 = binding("document-words", words, "producer"), binding("document-render", render)
    for b, function in ((c1, words), (c2, render)):
        registry.register_local(
            b, function, lambda args: bool(args.get("text", "nonempty").strip())
        )
        store.put(identities[b.issuer].sign(candidate(b)))
    assert await words({"text": "a short document"}) == {"words": 3}
    assert await render({"words": 3}) == {"report": "Words: 3"}
    checked(store, identities, c1, {"words": 3})
    checked(store, identities, c2, {"report": "Words: 3"})

    async def call(b, arguments):
        attempt = fingerprint([active_invocation.get() or uid(), b.digest, arguments])
        result = await runner.invoke(attempt, b.id, b.digest, arguments, context)
        if result["state"] != "completed":
            raise ValueError("child was not admitted/completed")
        return result["result"]

    async def report(arguments):
        @maf_executor(id="analyze")
        async def analyze(data: dict, ctx: WorkflowContext[dict]) -> None:
            await ctx.send_message(await call(c1, data))

        @maf_executor(id="format")
        async def format_result(data: dict, ctx: WorkflowContext[dict, dict]) -> None:
            await ctx.yield_output(await call(c2, data))

        workflow = (
            WorkflowBuilder(start_executor=analyze, max_iterations=3)
            .add_edge(analyze, format_result)
            .build()
        )
        outputs = (await workflow.run(arguments)).get_outputs()
        assert len(outputs) == 1
        return outputs[0]

    async with FormationSession(registry, identities["receiver"]) as formation:
        summary = await call(c1, {"text": "formation document"})
        assert (await call(c2, summary))["report"] == "Words: 2"
        c3 = binding("document-report", report, components=(c1.digest, c2.digest))
        registry.register_local(c3, report, lambda _: True)
        formed3 = await formation.publish(c3.id, candidate(c3, (c1, c2)))
    assert formed3.formation.relationship == "observed-use"
    assert len(formed3.formation.receipts) == 2
    assert formed3.outcome == "UNKNOWN"
    observed = await report({"text": "verification is separate"})
    assert observed == {"report": "Words: 3"}
    checked(store, identities, c3, observed)

    async with FormationSession(registry, identities["receiver"], max_steps=8) as formation:
        calibration = await call(c3, {"text": "calibration sample"})
        threshold = int(calibration["report"].split(": ")[1])

        async def triage(arguments):
            result = await call(c3, arguments)
            length = int(result["report"].split(": ")[1])
            return {"long": length > threshold, "threshold": threshold}

        c4 = binding("document-triage", triage, components=(c3.digest,))
        registry.register_local(c4, triage, lambda _: True)
        formed4 = await formation.publish(c4.id, candidate(c4, (c1, c2, c3)))
    assert len(formed4.formation.receipts) == 3
    assert formed4.formation.functional_novelty == "unknown"
    observed = await triage({"text": "new independent verification document"})
    assert observed == {"long": True, "threshold": 2}
    checked(store, identities, c4, observed)
    assert await call(c4, {"text": "held out work differs"}) == {"long": True, "threshold": 2}
    # Parent scope fits, but the actual empty child input fails its own assessment.
    with pytest.raises(ValueError, match="child"):
        await call(c3, {"text": ""})
    aggregate = metrics(store.events())
    assert aggregate["elapsed_observations"]
    assert not any(cost["unit"] == "wall_seconds" for cost in aggregate["costs"])
    store.put(
        identities["producer"].sign(
            Revocation(issuer="producer", subject=c1.subject, reason="withdrawn")
        )
    )
    for b in (c3, c4):
        req = UseRequest(
            receiver="receiver",
            subject=b.subject,
            capability_issuer=b.issuer,
            binding_digest=b.digest,
            scope=b.scope,
            semantic_fit="confirmed",
        )
        assert (await overlay.qualify(req)).outcome == "REJECT"


async def test_missing_receipts_and_binding_change_are_not_observed_formation(overlay, identities):
    overlay.store.set_budget("work", Decimal(10))
    registry = Registry(overlay)
    original = binding("primitive", words)
    registry.register_local(original, words, lambda _: True)
    composite = binding("composite", render, components=(original.digest,))
    registry.register_local(composite, render, lambda _: True)
    async with FormationSession(registry, identities["receiver"]) as session:
        with pytest.raises(ValueError, match="observed completed"):
            await session.publish(composite.id, candidate(composite, (original,)))
        session.receipts.append(ReceiptRef(issuer="receiver", id="invented"))
        with pytest.raises(ValueError, match="missing"):
            await session.publish(composite.id, candidate(composite, (original,)))
    replacement = original.model_copy(update={"revision": "2"})
    registry.register_local(replacement, words, lambda _: True)
    with pytest.raises(ValueError, match="component binding changed"):
        registry.prepare(
            composite.id,
            composite.digest,
            {"words": 1},
            ExecutionContext(caller="receiver", environment={"reference": "1"}),
        )


@pytest.mark.parametrize(
    "adverse", ["revocation", "counterexample", "evidence_withdrawal", "missing_source"]
)
async def test_materialized_input_is_not_runtime_dependency_but_adversity_requalifies(
    overlay, identities, monkeypatch, adverse
):
    import collective_intelligence_overlay.overlay as overlay_module
    from collective_intelligence_overlay.opportunities import work_kind

    store = overlay.store
    store.set_budget("work", Decimal(20))
    registry = Registry(overlay)
    runner = Executor(registry, identities["receiver"], Reservation())
    context = ExecutionContext(caller="receiver", environment={"reference": "1"})
    source = binding("calibration-source", words, "producer")
    registry.register_local(source, words, lambda _: True)
    short_lived = candidate(source).model_copy(update={"expires_at": now() + timedelta(seconds=10)})
    store.put(identities["producer"].sign(short_lived))
    source_check = checked(store, identities, source, {"words": 3}, seconds=10)
    async with FormationSession(registry, identities["receiver"]) as session:
        result = await runner.invoke(
            "calibrate-once", source.id, source.digest, {"text": "three calibration words"}, context
        )
        assert result["state"] == "completed"
        value = result["result"]["words"]

        async def constant(arguments):
            return {"threshold": value}

        target = binding("materialized-threshold", constant)
        registry.register_local(target, constant, lambda _: True)
        formed = Capability.model_validate(
            {
                **candidate(target).model_dump(),
                "schema_version": "3",
                "formation_inputs": [
                    FormationInput(
                        subject=source.subject, issuer=source.issuer, binding_digest=source.digest
                    )
                ],
            }
        )
        with pytest.raises(ValueError, match="inconsistent"):
            # v2 cannot reinterpret an omitted runtime dependency as a formation input.
            await session.publish(target.id, candidate(target))
        bad_pin = Capability.model_validate(
            {
                **formed.model_dump(),
                "formation_inputs": [
                    FormationInput(
                        subject=source.subject, issuer=source.issuer, binding_digest="f" * 64
                    )
                ],
            }
        )
        with pytest.raises(ValueError, match="inconsistent"):
            await session.publish(target.id, bad_pin)
        event = await session.publish(target.id, formed)
    assert len(event.formation.receipts) == 1
    assert formed.dependencies == () and target.components == ()
    checked(store, identities, target, {"threshold": 3})
    later = now() + timedelta(seconds=20)
    monkeypatch.setattr(overlay_module, "now", lambda: later)
    # The source's ordinary-use lifetime has ended; the materialized output's has not.
    request = UseRequest(
        receiver="receiver",
        subject=target.subject,
        scope=target.scope,
        capability_issuer=target.issuer,
        binding_digest=target.digest,
        semantic_fit="confirmed",
    )
    assert (await overlay.qualify(request)).outcome == "ACCEPT"
    source_request = request.model_copy(
        update={
            "subject": source.subject,
            "scope": source.scope,
            "capability_issuer": source.issuer,
            "binding_digest": source.digest,
        }
    )
    assert (await overlay.qualify(source_request)).outcome == "REQUALIFY"
    assert (await runner.invoke("materialized-use", target.id, target.digest, {}, context))[
        "result"
    ] == {"threshold": 3}
    if adverse == "revocation":
        store.put(
            identities["producer"].sign(
                Revocation(issuer="producer", subject=source.subject, reason="invalid calibration")
            )
        )
    elif adverse == "counterexample":
        store.put(
            identities["verifier"].sign(
                Evidence(
                    schema_version="2",
                    binding_digest=source.digest,
                    issuer="verifier",
                    subject=source.subject,
                    claim="document-contract",
                    scope=source.scope,
                    receivers=("receiver",),
                    verdict="FAIL",
                    method="report-check",
                    verifier_version="1",
                    artifact_digest=fingerprint({"counterexample": True}),
                    expires_at=now() + timedelta(hours=1),
                )
            )
        )
    elif adverse == "evidence_withdrawal":
        store.put(
            identities["verifier"].sign(
                Revocation(
                    issuer="verifier",
                    subject=source.subject,
                    evidence_id=source_check.id,
                    reason="calibration check withdrawn",
                )
            )
        )
    else:
        overlay.observed_sources.pop("producer")
    decision = await overlay.qualify(request)
    assert decision.outcome == ("UNKNOWN" if adverse == "missing_source" else "REQUALIFY")
    assert work_kind(decision.reasons) == (
        "observation" if adverse == "missing_source" else "repair"
    )
    assert (await runner.invoke("after-origin-change", target.id, target.digest, {}, context))[
        "state"
    ] != "completed"
