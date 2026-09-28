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


def checked(store, identities, b, observed):
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
        expires_at=now() + timedelta(hours=1),
    )
    store.put(identities["verifier"].sign(evidence))


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
