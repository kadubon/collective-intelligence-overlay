"""Real DB/OPA/A2A: owner closes a reviewed slot without refund or rewriting history."""

import asyncio
import copy
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from remote_call_application import admit, capability, parent_binding, provider_binding
from securesystemslib.exceptions import VerificationError
from sqlalchemy import select, update
from test_call_identity import count
from test_call_identity import peers as peers
from test_call_identity import serving as serving
from test_production_reconciliation import envelopes, remaining

from collective_intelligence_overlay.bindings import active_invocation, callable_digest, fingerprint
from collective_intelligence_overlay.calls import RemoteCall
from collective_intelligence_overlay.invocations import (
    Executor,
    InvocationStore,
    Reservation,
    UnresolvedEffectsLimit,
)
from collective_intelligence_overlay.models import Event, Evidence, ReceiptRef, Revocation, now
from collective_intelligence_overlay.reconciliation import EffectObservation, Reconciliations
from collective_intelligence_overlay.resolutions import ResolutionObservation, Resolutions
from collective_intelligence_overlay.security import verify
from collective_intelligence_overlay.storage import Conflict, budgets, records


def query_binding(operation, name):
    original = provider_binding()
    return original.model_copy(
        update={
            "id": name,
            "issuer": "receiver",
            "registrar": "receiver",
            "subject": original.subject.model_copy(
                update={"id": name, "digest": callable_digest(operation)}
            ),
            "target": original.target.model_copy(
                update={"name": name, "interface_digest": callable_digest(operation)}
            ),
            "callers": ("receiver",),
            "verification_callers": ("receiver",),
            "input_schema": {"type": "object"},
            "output_schema": {"type": "object"},
        }
    )


@pytest.fixture
def resolution_host(serving):
    p = serving
    witness = {
        "effect": "confirmed",
        "all_effects_checked": True,
        "all_results_checked": True,
        "worker_quiescent": True,
    }
    review_calls = []
    effect_queries = []

    async def operation(arguments):
        await p.registry.execute(p.proxy.id, p.proxy.digest, arguments, p.context, call_id="first")
        await p.registry.execute(p.proxy.id, p.proxy.digest, arguments, p.context, call_id="second")
        raise TimeoutError("terminal original outcome remains unknown")

    parent = parent_binding(p.proxy, operation)
    p.registry.register_local(parent, operation, lambda _: True)
    admit(p.registry.overlay, p.identity, parent, p.configs["verifier"], dependency=p.proxy)
    executor = Executor(p.registry, p.identity, Reservation())
    observer = Reconciliations(p.registry, p.configs["receiver"], p.identity)

    async def effect_query(arguments):
        saved = RemoteCall.model_validate(arguments["call"])
        effect_queries.append(saved.remote_invocation_id)
        actual = InvocationStore(p.provider.store).get("receiver", saved.remote_invocation_id)
        assert actual is not None and actual["state"] == "completed"
        assert actual["result_digest"] == fingerprint(actual["result"])
        return EffectObservation(
            provider_invocation_id=saved.remote_invocation_id,
            provider_binding_digest=saved.provider_binding_digest,
            arguments_digest=saved.arguments_digest,
            effect=witness["effect"],
            observation_digest=fingerprint(actual),
            reason="ACTUAL_PROVIDER_WITNESS",
        ).model_dump(mode="json")

    effect = query_binding(effect_query, "effect-query")
    p.registry.register_local(effect, effect_query, lambda _: True)
    p.registry.overlay.store.put(p.identity.sign(capability(effect)))
    observer.register(effect.id)

    async def whole_query(arguments):
        state = arguments["state"]
        review_calls.append(state["invocation"]["id"])
        original_id = state["invocation"]["id"]
        # This installed test application has exactly two known remote samples,
        # no other actuator and a completed/cancelled worker coroutine. Query the
        # owner DB's full map and every independently retained provider row.
        saved = p.registry.remote_calls(p.context, invocation_id=original_id, limit=65)
        assert len(saved) == 2 and [c.call_key for c in saved] == state["remote_call_keys"]
        for call in saved:
            actual = InvocationStore(p.provider.store).get("receiver", call.remote_invocation_id)
            assert actual["result_digest"] == fingerprint(actual["result"])
        return ResolutionObservation(
            caller="receiver",
            invocation_id=original_id,
            state_digest=state["state_digest"],
            effect=witness["effect"],
            all_effects_checked=witness["all_effects_checked"],
            all_results_checked=witness["all_results_checked"],
            worker_quiescent=witness["worker_quiescent"],
            observation_digest=fingerprint(
                {
                    "original": original_id,
                    "provider_results": [c.remote_invocation_id for c in saved],
                    "witness": witness,
                }
            ),
            reason="WHOLE_APPLICATION_QUERY",
        ).model_dump(mode="json")

    whole = query_binding(whole_query, "whole-query")
    p.registry.register_local(whole, whole_query, lambda _: True)
    p.registry.overlay.store.put(p.identity.sign(capability(whole)))
    resolutions = Resolutions(p.registry, p.configs["receiver"], p.identity, observer)
    resolutions.register(whole.id)
    return SimpleNamespace(
        p=p,
        executor=executor,
        observer=observer,
        resolutions=resolutions,
        parent=parent,
        effect=effect,
        whole=whole,
        witness=witness,
        review_calls=review_calls,
        effect_queries=effect_queries,
    )


async def unknown(h, name):
    result = await h.executor.invoke(name, h.parent.id, h.parent.digest, {"value": 7}, h.p.context)
    assert result["state"] == "unknown" and result["reservation_state"] == "held"
    return result


async def observations(h, name, *, effect=True):
    refs = []
    for index, call in enumerate(h.p.registry.remote_calls(h.p.context, invocation_id=name)):
        event = await h.observer.observe(
            "receiver",
            call.call_key,
            name + f"-observe-{index}",
            invocation_id=name,
            reconciler=h.effect.id if effect else None,
        )
        refs.append(ReceiptRef(issuer="receiver", id=event.id))
    return tuple(refs)


async def test_default_32_limit_restores_only_one_explicitly_reviewed_slot(resolution_host):
    h, p = resolution_host, resolution_host.p
    # Configure this newly allocated fixture before work, never refund a live
    # invocation. The regular set_budget API intentionally forbids replacement.
    for store in (p.registry.overlay.store, p.provider.store):
        with store.engine.begin() as conn:
            conn.execute(
                update(budgets).where(budgets.c.unit == "work").values(remaining=Decimal(100))
            )
    originals = [await unknown(h, f"original-{index}") for index in range(32)]
    assert count(p) == 64
    with pytest.raises(UnresolvedEffectsLimit):
        await unknown(h, "blocked-before-review")
    assert h.executor.store.get("receiver", "blocked-before-review") is None
    old_bytes, allowance = envelopes(p), remaining(p)
    refs = await observations(h, "original-0")
    # Merely confirming both children still leaves the original row/32-slot gate.
    with pytest.raises(UnresolvedEffectsLimit):
        await unknown(h, "blocked-after-child-observation")
    assert remaining(p) == allowance and count(p) == 64
    with pytest.raises(ValueError, match="every"):
        await h.resolutions.review("receiver", "original-0", "partial", h.whole.id, refs[:1])
    event = await h.resolutions.review(
        "receiver", "original-0", "close-original-0", h.whole.id, refs
    )
    assert verify(p.identity.sign(event), p.registry.overlay.store.principals) == event
    assert event.resolution.independent_verification == "UNKNOWN"
    assert event.resolution.allowance_changed is False
    assert remaining(p) == allowance and count(p) == 64
    assert h.executor.store.get("receiver", "original-0") == originals[0]
    from collective_intelligence_overlay.observability import database_observations

    measured = database_observations(p.registry.overlay.store, p.configs["receiver"])
    assert measured["unresolved_effects"] == 31
    assert measured["historical_uncertain_effects"] == 32
    assert measured["resolved_historical_effects"] == 1
    assert measured["invocation_states"]["unknown"] == 32
    assert all(envelopes(p)[key] == value for key, value in old_bytes.items())
    restarted = Resolutions(p.registry, p.configs["receiver"], p.identity, h.observer)
    restarted.register(h.whole.id)
    assert restarted.active("receiver", "original-0")
    assert (
        await restarted.review("receiver", "original-0", "close-original-0", h.whole.id, refs)
        == event
    )
    assert h.review_calls == ["original-0"]
    with pytest.raises(Conflict, match="already resolved"):
        await restarted.review("receiver", "original-0", "double-close", h.whole.id, refs)
    with pytest.raises(Conflict, match="changed"):
        await restarted.review(
            "receiver",
            "original-0",
            "close-original-0",
            h.whole.id,
            refs,
            arguments={"changed": True},
        )
    # A stale task cannot dispatch an extra child from this historical parent,
    # even after later support invalidation reopens the capacity projection.
    token = active_invocation.set(fingerprint(["receiver", "receiver", "original-0"]))
    try:
        with pytest.raises(ValueError, match="cannot dispatch"):
            await p.registry.execute(
                p.proxy.id, p.proxy.digest, {"value": 7}, p.context, call_id="late-child"
            )
    finally:
        active_invocation.reset(token)
    assert count(p) == 64
    await unknown(h, "one-slot-recovered")
    assert count(p) == 66 and remaining(p) == allowance - 1
    with pytest.raises(UnresolvedEffectsLimit):
        await unknown(h, "blocked-again")
    # Exact review support withdrawal reopens admission, preserving its receipt.
    p.registry.overlay.store.put(
        p.identity.sign(
            Revocation(
                issuer="receiver", subject=h.whole.subject, reason="review implementation withdrawn"
            )
        )
    )
    assert not restarted.active("receiver", "original-0")
    assert h.executor.store.get("receiver", "original-0") == originals[0]
    assert (
        await restarted.review("receiver", "original-0", "close-original-0", h.whole.id, refs)
        == event
    )


@pytest.mark.parametrize(
    "condition",
    [
        "normal-provider-only",
        "unknown-effect",
        "unknown-local",
        "unchecked-results",
        "active-physical-worker",
        "foreign-owner",
        "unauthorized-actor",
        "missing-receipt",
        "changed-parent",
        "stale",
        "forged",
        "withdrawn-effect-query",
    ],
)
async def test_incomplete_forged_stale_and_unauthorized_reviews_never_close(
    resolution_host, condition
):
    h, p = resolution_host, resolution_host.p
    original = await unknown(h, "uncertain")
    if condition == "unknown-effect":
        h.witness["effect"] = "unknown"
    refs = await observations(h, "uncertain", effect=condition != "normal-provider-only")
    if condition == "unknown-local":
        h.witness["all_effects_checked"] = False
    elif condition == "unchecked-results":
        h.witness["all_results_checked"] = False
    elif condition == "active-physical-worker":
        h.witness["worker_quiescent"] = False
    elif condition == "foreign-owner":
        refs = (refs[0].model_copy(update={"issuer": "verifier"}), refs[1])
    elif condition == "missing-receipt":
        refs = (refs[0].model_copy(update={"id": "missing"}), refs[1])
    elif condition in {"changed-parent", "stale", "forged"}:
        # A genuine signature over mismatched/stale content is still unusable;
        # a changed payload retaining the old signature fails verification.
        ref = p.registry.overlay.store.reference("event", "receiver", refs[0].id)
        envelope = p.registry.overlay.store.signed_record(ref)
        event = verify(envelope, p.registry.overlay.store.principals)
        if condition == "changed-parent":
            event = event.model_copy(
                update={
                    "reconciliation": event.reconciliation.model_copy(
                        update={"original_invocation_id": "other-parent"}
                    )
                }
            )
        elif condition == "stale":
            event = event.model_copy(update={"occurred_at": now() - timedelta(seconds=301)})
        if condition != "forged":
            envelope = p.identity.sign(event)
        else:
            envelope = copy.deepcopy(envelope)
            envelope["signatures"][0]["sig"] = "A" * len(envelope["signatures"][0]["sig"])
        with p.registry.overlay.store.engine.begin() as conn:
            conn.execute(
                update(records).where(records.c.record_id == refs[0].id).values(envelope=envelope)
            )
    elif condition == "withdrawn-effect-query":
        p.registry.overlay.store.put(
            p.identity.sign(
                Revocation(
                    issuer="receiver", subject=h.effect.subject, reason="effect query withdrawn"
                )
            )
        )
    allowance = remaining(p)
    with pytest.raises((ValueError, VerificationError)):
        await h.resolutions.review(
            "verifier" if condition == "unauthorized-actor" else "receiver",
            "uncertain",
            "reject-close",
            h.whole.id,
            refs,
        )
    assert not h.resolutions.active("receiver", "uncertain")
    assert h.executor.store.get("receiver", "uncertain") == original
    assert remaining(p) == allowance and count(p) == 2
    with p.registry.overlay.store.engine.connect() as conn:
        failed = (
            conn.execute(
                select(records.c.body).where(
                    (records.c.kind == "event") & records.c.record_id.like("resolve-failed-%")
                )
            )
            .scalars()
            .all()
        )
    if condition == "unauthorized-actor":
        assert failed == []
    else:
        assert len(failed) == 1 and failed[0]["outcome"] == "UNKNOWN"
        assert failed[0]["costs"][0]["unit"] == "wall_seconds"
        assert failed[0]["costs"][0]["status"] == "measured"


async def test_concurrent_close_claim_and_restore_never_duplicate_slot_or_credit(resolution_host):
    h, p = resolution_host, resolution_host.p
    original = await unknown(h, "uncertain")
    refs = await observations(h, "uncertain")
    allowance = remaining(p)
    results = await asyncio.gather(
        h.resolutions.review("receiver", "uncertain", "close-a", h.whole.id, refs),
        h.resolutions.review("receiver", "uncertain", "close-b", h.whole.id, refs),
        unknown(h, "concurrent-claim"),
        return_exceptions=True,
    )
    assert sum(isinstance(value, Event) for value in results) == 1
    assert sum(isinstance(value, Conflict) for value in results) == 1
    assert h.resolutions.active("receiver", "uncertain")
    assert remaining(p) == allowance - 1 and count(p) == 4
    assert h.executor.store.get("receiver", "uncertain") == original
    p.registry.overlay.store.reset_sync_after_restore()
    assert not h.resolutions.active("receiver", "uncertain")
    with pytest.raises(ValueError, match="restored"):
        await h.resolutions.review("receiver", "uncertain", "post-restore", h.whole.id, refs)


async def test_explicit_absent_business_effect_requires_all_results_and_queries(resolution_host):
    h, p = resolution_host, resolution_host.p
    original = await unknown(h, "no-business-mutation")
    # These test bindings are read-only. Their sampling witness executed, while
    # the separate business-effect contract asserts that no mutation occurred.
    h.witness["effect"] = "absent"
    refs = await observations(h, "no-business-mutation")
    event = await h.resolutions.review(
        "receiver", "no-business-mutation", "close-absent", h.whole.id, refs
    )
    assert event.resolution.effect == "absent" and event.resolution.all_results_checked
    assert event.resolution.independent_verification == "UNKNOWN"
    assert h.executor.store.get("receiver", "no-business-mutation") == original
    assert count(p) == 2


async def test_unrelated_evidence_and_foreign_withdrawal_do_not_cancel_owner_resolution(
    resolution_host,
):
    h, p = resolution_host, resolution_host.p
    original = await unknown(h, "historical-disposition")
    refs = await observations(h, "historical-disposition")
    event = await h.resolutions.review(
        "receiver", "historical-disposition", "close-history", h.whole.id, refs
    )
    foreign_config = p.configs["verifier"]
    foreign = foreign_config.identity("verifier", foreign_config.private_key)
    unrelated = Evidence(
        schema_version="2",
        issuer="verifier",
        subject=h.whole.subject,
        scope=h.whole.scope,
        binding_digest="b" * 64,
        receivers=("receiver",),
        claim="functional-validity",
        verdict="FAIL",
        method="reference-check",
        verifier_version="unrelated-observation-v1",
        artifact_digest="c" * 64,
        expires_at=now() + timedelta(hours=1),
    )
    p.registry.overlay.store.put(foreign.sign(unrelated))
    p.registry.overlay.store.put(
        foreign.sign(
            Revocation(
                issuer="verifier",
                subject=h.whole.subject,
                reason="not the owner's support withdrawal",
            )
        )
    )
    assert h.resolutions.active("receiver", "historical-disposition")
    assert h.executor.store.get("receiver", "historical-disposition") == original
    assert (
        p.registry.overlay.store.resolve_reference(
            p.registry.overlay.store.reference("event", "receiver", event.id)
        )
        == event
    )
    assert count(p) == 2
