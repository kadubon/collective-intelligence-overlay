import copy

import pytest
from remote_call_application import admit, capability, parent_binding, provider_binding
from sqlalchemy import select, update
from test_call_identity import count
from test_call_identity import peers as peers
from test_call_identity import serving as serving

from collective_intelligence_overlay.bindings import callable_digest, fingerprint
from collective_intelligence_overlay.calls import RemoteCall, remote_calls
from collective_intelligence_overlay.invocations import Executor, Reservation
from collective_intelligence_overlay.reconciliation import EffectObservation, Reconciliations
from collective_intelligence_overlay.security import verify
from collective_intelligence_overlay.storage import Conflict, budgets, records


async def unknown_parent(p):
    async def operation(arguments):
        await p.registry.execute(
            p.proxy.id, p.proxy.digest, arguments, p.context, call_id="original-child"
        )
        raise TimeoutError("response lost after real provider completion")

    parent = parent_binding(p.proxy, operation)
    p.registry.register_local(parent, operation, lambda _: True)
    admit(p.registry.overlay, p.identity, parent, p.configs["verifier"], dependency=p.proxy)
    executor = Executor(p.registry, p.identity, Reservation())
    result = await executor.invoke(
        "unknown-parent", parent.id, parent.digest, {"value": 7}, p.context
    )
    assert result["state"] == "unknown"
    return executor, result, p.registry.remote_calls(p.context, invocation_id="unknown-parent")[0]


def remaining(p):
    with p.registry.overlay.store.engine.connect() as conn:
        return conn.execute(
            select(budgets.c.remaining).where(budgets.c.unit == "work")
        ).scalar_one()


def envelopes(p):
    with p.registry.overlay.store.engine.connect() as conn:
        return dict(conn.execute(select(records.c.record_id, records.c.envelope)).all())


async def test_reconcile_original_unknown_actual_a2a_no_resend_refund_or_pass(serving):
    p = serving
    executor, original, ref = await unknown_parent(p)
    old_envelopes, allowance = envelopes(p), remaining(p)
    observer = Reconciliations(p.registry, p.configs["receiver"], p.identity)
    event = await observer.observe(
        "receiver", ref.call_key, "observe-1", invocation_id="unknown-parent"
    )
    r = event.reconciliation
    assert r.reported_state == "completed"
    assert r.effect == "unknown" and r.independent_verification == "UNKNOWN"
    assert (
        r.provider_invocation_id == ref.remote_invocation_id
        and r.arguments_digest == fingerprint({"value": 7})
    )
    assert r.original_receipt.id == original["receipt_id"]
    assert verify(p.identity.sign(event), p.registry.overlay.store.principals) == event
    assert (
        await observer.observe(
            "receiver", ref.call_key, "observe-1", invocation_id="unknown-parent"
        )
        == event
    )
    assert executor.store.get("receiver", "unknown-parent") == original
    assert remaining(p) == allowance and count(p) == 1
    assert all(envelopes(p)[key] == value for key, value in old_envelopes.items())
    with pytest.raises(ValueError, match="owner-only"):
        await observer.observe("verifier", ref.call_key, "unauthorized")
    with pytest.raises(Conflict, match="changed"):
        await observer.observe(
            "receiver", ref.call_key, "observe-1", invocation_id="changed-parent"
        )
    with pytest.raises(ValueError, match="original parent"):
        await observer.observe("receiver", ref.call_key, "missing-parent")
    # Reloading the installed host preserves the observation and original map.
    restarted = Reconciliations(p.registry, p.configs["receiver"], p.identity)
    assert (
        await restarted.observe(
            "receiver", ref.call_key, "observe-1", invocation_id="unknown-parent"
        )
        == event
    )


async def test_explicit_effect_query_and_mismatched_unknown_hold_allowance(serving, monkeypatch):
    p = serving
    executor, original, ref = await unknown_parent(p)
    observer = Reconciliations(p.registry, p.configs["receiver"], p.identity)
    query_binding = provider_binding().model_copy(
        update={
            "id": "effect-query",
            "issuer": "receiver",
            "registrar": "receiver",
            "callers": ("receiver",),
            "verification_callers": ("receiver",),
        }
    )

    query_calls = []

    async def confirm(arguments):
        saved = RemoteCall.model_validate(arguments["call"])
        query_calls.append(saved.remote_invocation_id)
        assert count(p) == 1
        return EffectObservation(
            provider_invocation_id=saved.remote_invocation_id,
            provider_binding_digest=saved.provider_binding_digest,
            arguments_digest=saved.arguments_digest,
            effect="confirmed",
            observation_digest=fingerprint(
                {"witness_count": count(p), "original_id": saved.remote_invocation_id}
            ),
            reason="APPLICATION_WITNESS_CONFIRMED",
        ).model_dump(mode="json")

    query_binding = query_binding.model_copy(
        update={
            "target": query_binding.target.model_copy(
                update={"interface_digest": callable_digest(confirm)}
            ),
            "subject": query_binding.subject.model_copy(
                update={"digest": callable_digest(confirm)}
            ),
            "input_schema": {"type": "object", "required": ["call", "provider_report"]},
            "output_schema": {"type": "object"},
        }
    )
    p.registry.register_local(query_binding, confirm, lambda _: True)
    p.registry.overlay.store.put(p.identity.sign(capability(query_binding)))
    observer.register("effect-query")
    allowance = remaining(p)
    event = await observer.observe(
        "receiver",
        ref.call_key,
        "confirm-1",
        invocation_id="unknown-parent",
        reconciler="effect-query",
    )
    assert event.reconciliation.effect == "confirmed"
    assert event.reconciliation.independent_verification == "UNKNOWN"
    assert (
        executor.store.get("receiver", "unknown-parent") == original and remaining(p) == allowance
    )
    await observer.observe(
        "receiver",
        ref.call_key,
        "confirm-1",
        invocation_id="unknown-parent",
        reconciler="effect-query",
    )
    assert query_calls == [ref.remote_invocation_id]
    actual = await p.registry.query_remote_call(
        ref.call_key, p.context, p.configs["receiver"], p.identity
    )
    for index, (field, value) in enumerate(
        [
            ("id", "different-operation"),
            ("binding_digest", "a" * 64),
            ("arguments_digest", "b" * 64),
            ("caller", "verifier"),
            ("result_digest", "c" * 64),
            ("fingerprint", "malformed-provider-digest"),
        ]
    ):
        changed = copy.deepcopy(actual)
        changed[field] = value

        async def bad_query(*_, result=changed):
            return result

        monkeypatch.setattr(p.registry, "query_remote_call", bad_query)
        invalid = await observer.observe(
            "receiver",
            ref.call_key,
            f"mismatch-{index}",
            invocation_id="unknown-parent",
            reconciler="effect-query",
        )
        assert invalid.reconciliation.reported_state == "unknown"
        assert invalid.reconciliation.effect == "unknown"
        assert len(query_calls) == 1 and remaining(p) == allowance and count(p) == 1
    # An actual saved legacy map has no positive argument identity proof.
    with p.registry.overlay.store.engine.begin() as conn:
        conn.execute(
            update(remote_calls)
            .where(remote_calls.c.call_key == ref.call_key)
            .values(arguments_digest=None)
        )
    legacy = await observer.observe(
        "receiver",
        ref.call_key,
        "legacy",
        invocation_id="unknown-parent",
        reconciler="effect-query",
    )
    assert legacy.reconciliation.reason == "LEGACY_REMOTE_ARGUMENTS_UNKNOWN"
    assert executor.store.get("receiver", "unknown-parent") == original
