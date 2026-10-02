"""Physical worker loss after real PG/OPA dispatch and authenticated A2A."""

import asyncio
import base64
import copy
import json
import os
import platform
import sys
import time
from decimal import Decimal
from pathlib import Path
from threading import Event as ThreadEvent
from urllib.parse import urlsplit

import pytest
import uvicorn
from pydantic import SecretStr
from remote_call_application import (
    LoseResponse,
    admit,
    capability,
    parent_binding,
    register_consumer,
    register_parent,
    register_provider,
)
from securesystemslib.exceptions import VerificationError
from sqlalchemy import select, update
from test_call_identity import count, ready
from test_call_identity import peers as peers
from test_call_identity import serving as serving
from test_invocation_resolution import query_binding
from test_migration import database_copy
from test_production_reconciliation import envelopes, remaining

from collective_intelligence_overlay.adapters.a2a import application
from collective_intelligence_overlay.bindings import fingerprint
from collective_intelligence_overlay.calls import RemoteCall
from collective_intelligence_overlay.invocations import (
    Executor,
    InvocationStore,
    Reservation,
    UnresolvedEffectsLimit,
    invocation_basis_id,
    invocations,
)
from collective_intelligence_overlay.models import ReceiptRef, Revocation
from collective_intelligence_overlay.peer import PeerService
from collective_intelligence_overlay.reconciliation import EffectObservation, Reconciliations
from collective_intelligence_overlay.resolutions import ResolutionObservation, Resolutions
from collective_intelligence_overlay.security import verify
from collective_intelligence_overlay.storage import Conflict, budgets, records


def physical_evidence(p, label, process, **observations):
    """Export public original records; no keys, credentials or re-signing."""
    directory = os.environ.get("CIO_RECEIPTLESS_RAW_DIRECTORY")
    if not directory:
        return
    target = Path(directory) / label
    target.mkdir(parents=True, exist_ok=False)
    original_records = {}
    for owner, store in {
        "receiver": p.registry.overlay.store,
        "producer": p.provider.store,
    }.items():
        with store.engine.connect() as conn:
            original_records[owner] = (
                conn.execute(select(records.c.envelope).order_by(records.c.sequence))
                .scalars()
                .all()
            )
    public_keys = {
        owner: {
            "keyid": principal.key.keyid,
            "key": principal.key.to_dict(),
            "trust_group": principal.trust_group,
            "methods": sorted(principal.methods),
        }
        for owner, principal in p.registry.overlay.store.principals.items()
    }
    (target / "observations.json").write_text(
        json.dumps(
            {
                "worker_pid": process.pid,
                "worker_exit_code": process.returncode,
                "keys": public_keys,
                "records": original_records,
                "python": sys.version,
                "os": platform.platform(),
                "model_inference_performed": False,
                "fixture_origin": "synthetic authenticated PG/OPA/A2A physical fault test",
                **observations,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize("stage", ["dispatch", "completed"])
@pytest.mark.parametrize("legacy", [False, True])
async def test_receiptless_worker_loss_requires_whole_owner_review(
    serving, tmp_path, stage, legacy
):
    p = serving
    parent = register_parent(p.registry, p.proxy, p.context)
    admit(p.registry.overlay, p.identity, parent, p.configs["verifier"], dependency=p.proxy)
    default_limit = stage == "completed" and not legacy
    initial_count = 0
    if default_limit:
        for store in (p.registry.overlay.store, p.provider.store):
            with store.engine.begin() as conn:
                conn.execute(
                    update(budgets).where(budgets.c.unit == "work").values(remaining=Decimal(100))
                )

        async def uncertain(arguments):
            await p.registry.execute(
                p.proxy.id, p.proxy.digest, arguments, p.context, call_id="first"
            )
            await p.registry.execute(
                p.proxy.id, p.proxy.digest, arguments, p.context, call_id="second"
            )
            raise TimeoutError("actual terminal unknown; historical allowance remains held")

        previous = parent_binding(p.proxy, uncertain, name="previous-uncertain")
        p.registry.register_local(previous, uncertain, lambda _: True)
        admit(p.registry.overlay, p.identity, previous, p.configs["verifier"], dependency=p.proxy)
        previous_executor = Executor(p.registry, p.identity, Reservation())
        for i in range(31):
            old = await previous_executor.invoke(
                f"previous-{i}", previous.id, previous.digest, {"value": 7}, p.context
            )
            assert old["state"] == "unknown" and old["receipt_id"] is not None
        initial_count = 62
        assert count(p) == initial_count
    marker = tmp_path / (stage + ".json")
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(Path(__file__).with_name("receiptless_worker.py")),
        str(p.root / "receiver" / "config.json"),
        str(marker),
        stage,
        "legacy" if legacy else "anchored",
        "default-limit" if default_limit else "one-limit",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 30
        while not marker.exists() and time.monotonic() < deadline:
            if process.returncode is not None:
                raise AssertionError((await process.communicate())[1].decode())
            await asyncio.sleep(0.05)
        assert marker.exists(), "real worker never reached the durable fault boundary"
        process.kill()
        await asyncio.wait_for(process.communicate(), 10)
        assert process.returncode != 0
        executor = Executor(
            p.registry,
            p.identity,
            Reservation(seconds=4, max_unresolved=32 if default_limit else 1),
        )
        name = "receiptless-" + stage
        assert json.loads(marker.read_text())["id"] == name
        row = executor.store.get("receiver", name)
        assert row["phase"] == "dispatched" and row["receipt_id"] is None
        expected_calls = {"dispatch": 0, "completed": 2, "lost-response": 1}[stage]
        assert count(p) == initial_count + expected_calls
        # Wait for the actual lease clock rather than editing timestamps.
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            executor.store.cleanup_expired(owner="receiver", limit=4)
            row = executor.store.get("receiver", name)
            if row["state"] == "unknown":
                break
            await asyncio.sleep(0.1)
        assert row["state"] == "unknown" and row["reservation_state"] == "held"
        assert row["receipt_id"] is None
        allowance = remaining(p)
        original_envelopes = envelopes(p)
        replay = await executor.invoke(name, parent.id, parent.digest, {"value": 7}, p.context)
        assert replay == row and remaining(p) == allowance
        assert count(p) == initial_count + expected_calls

        observer = Reconciliations(p.registry, p.configs["receiver"], p.identity)
        witness = {"quiescent": False, "request_checked": True, "children_checked": True}

        async def child_query(arguments):
            saved = RemoteCall.model_validate(arguments["call"])
            actual = InvocationStore(p.provider.store).get("receiver", saved.remote_invocation_id)
            assert actual["state"] == "completed" and actual["result_digest"] == fingerprint(
                actual["result"]
            )
            assert actual["arguments_digest"] == fingerprint({"value": 7})
            return EffectObservation(
                provider_invocation_id=saved.remote_invocation_id,
                provider_binding_digest=saved.provider_binding_digest,
                arguments_digest=saved.arguments_digest,
                effect="confirmed",
                observation_digest=fingerprint(actual),
                reason="ACTUAL_ORIGINAL_PROVIDER_ROW",
            ).model_dump(mode="json")

        child_binding = query_binding(child_query, "receiptless-child-query")
        p.registry.register_local(child_binding, child_query, lambda _: True)
        p.registry.overlay.store.put(p.identity.sign(capability(child_binding)))
        observer.register(child_binding.id)
        refs = []
        for i, call in enumerate(p.registry.remote_calls(p.context, invocation_id=name)):
            observed = await observer.observe(
                "receiver",
                call.call_key,
                f"{name}-child-{i}",
                invocation_id=name,
                reconciler=child_binding.id,
            )
            assert observed.reconciliation.original_receipt is None
            refs.append(ReceiptRef(issuer="receiver", id=observed.id))
        refs = tuple(refs)

        async def external_query(arguments):
            state = arguments["state"]
            assert process.returncode is not None and process.returncode != 0
            assert state["request"] == {
                "owner": "receiver",
                "caller": "receiver",
                "purpose": "reuse",
                "binding": parent.id,
                "binding_digest": parent.digest,
                "arguments": {"value": 7},
                "environment": p.context.environment,
                "permissions": sorted(p.context.permissions),
            }
            assert state["local_children"] == []
            saved = p.registry.remote_calls(p.context, invocation_id=name, limit=65)
            assert len(saved) == expected_calls
            assert [c.call_key for c in saved] == state["remote_call_keys"]
            assert count(p) == initial_count + len(saved)
            for call in saved:
                actual = InvocationStore(p.provider.store).get(
                    "receiver", call.remote_invocation_id
                )
                assert actual["state"] == "completed" and actual["result_digest"] == fingerprint(
                    actual["result"]
                )
            return ResolutionObservation(
                caller="receiver",
                invocation_id=name,
                state_digest=state["state_digest"],
                effect="confirmed" if saved else "absent",
                all_effects_checked=True,
                all_results_checked=True,
                worker_quiescent=witness["quiescent"],
                original_request_checked=witness["request_checked"],
                all_children_checked=witness["children_checked"],
                observation_digest=fingerprint(
                    {
                        "pid": process.pid,
                        "returncode": process.returncode,
                        "original_request": state["request"],
                        "provider_calls": [c.model_dump(mode="json") for c in saved],
                        "physical_results": count(p),
                    }
                ),
                reason="PHYSICAL_KILL_AND_ALL_ORIGINAL_PROVIDER_RESULTS",
            ).model_dump(mode="json")

        binding = query_binding(external_query, "receiptless-query")
        p.registry.register_local(binding, external_query, lambda _: True)
        p.registry.overlay.store.put(p.identity.sign(capability(binding)))
        review = Resolutions(
            p.registry,
            p.configs["receiver"],
            p.identity,
            observer,
        )
        review.register(binding.id)
        if refs:
            with pytest.raises(ValueError, match="every"):
                await review.review("receiver", name, name + "-partial", binding.id, refs[:-1])
        with pytest.raises(ValueError, match="physical quiescence"):
            await review.review("receiver", name, name + "-not-quiescent", binding.id, refs)
        with pytest.raises(UnresolvedEffectsLimit):
            await executor.invoke(
                "after-loss-" + stage, parent.id, parent.digest, {"value": 8}, p.context
            )
        assert remaining(p) == allowance
        if not legacy and stage == "dispatch":
            acceptance_id = invocation_basis_id("receiver", "receiver", name, "accepted")
            original_anchor = original_envelopes[acceptance_id]
            forged = copy.deepcopy(original_anchor)
            payload = json.loads(base64.b64decode(forged["payload"]))
            payload["invocation_observation"]["request_fingerprint"] = "a" * 64
            forged["payload"] = base64.b64encode(json.dumps(payload).encode()).decode()
            with p.registry.overlay.store.engine.begin() as conn:
                conn.execute(
                    update(records)
                    .where(records.c.record_id == acceptance_id)
                    .values(envelope=forged)
                )
            with pytest.raises(VerificationError):
                await review.review("receiver", name, name + "-forged-anchor", binding.id, refs)
            with p.registry.overlay.store.engine.begin() as conn:
                conn.execute(
                    update(records)
                    .where(records.c.record_id == acceptance_id)
                    .values(envelope=original_anchor)
                )
                original_request = conn.execute(
                    select(invocations.c.request).where(invocations.c.id == name)
                ).scalar_one()
                changed_request = {**original_request, "arguments": {"value": 8}}
                conn.execute(
                    update(invocations)
                    .where(invocations.c.id == name)
                    .values(request=changed_request, fingerprint=fingerprint(changed_request))
                )
            with pytest.raises(ValueError, match="signed request"):
                await review.review("receiver", name, name + "-changed-request", binding.id, refs)
            with p.registry.overlay.store.engine.begin() as conn:
                conn.execute(
                    update(invocations)
                    .where(invocations.c.id == name)
                    .values(request=original_request, fingerprint=row["fingerprint"])
                )
            assert not review.active("receiver", name) and remaining(p) == allowance
        witness["quiescent"] = True
        for flag in ("request_checked", "children_checked"):
            witness[flag] = False
            with pytest.raises(ValueError, match="physical quiescence"):
                await review.review("receiver", name, name + "-missing-" + flag, binding.id, refs)
            witness[flag] = True
        if not legacy and stage == "completed":
            results = await asyncio.gather(
                *(
                    review.review("receiver", name, name + "-close-" + suffix, binding.id, refs)
                    for suffix in ("a", "b")
                ),
                return_exceptions=True,
            )
            assert sum(isinstance(item, Conflict) for item in results) == 1
            event = next(item for item in results if not isinstance(item, BaseException))
        else:
            event = await review.review("receiver", name, name + "-close", binding.id, refs)
        assert event.schema_version == "6" and event.resolution.original_receipt is None
        assert event.resolution.basis_origin == (
            "legacy_recovery_observation" if legacy else "execution_transaction"
        )
        assert (
            event.resolution.allowance_changed is False
            and event.resolution.independent_verification == "UNKNOWN"
        )
        assert verify(p.identity.sign(event), p.registry.overlay.store.principals) == event
        assert review.active("receiver", name) and remaining(p) == allowance
        assert executor.store.get("receiver", name) == row
        assert all(envelopes(p)[key] == value for key, value in original_envelopes.items())
        restarted = Resolutions(p.registry, p.configs["receiver"], p.identity, observer)
        restarted.register(binding.id)
        assert await restarted.review("receiver", name, event.attempt_id, binding.id, refs) == event
        if not legacy and stage == "dispatch":
            with database_copy(
                p.registry.overlay.store, operator_url=os.environ["CIO_TEST_DATABASE_URL"]
            ) as copied:
                assert InvocationStore(copied).get("receiver", name) == row
                with copied.engine.connect() as conn:
                    restored_bytes = dict(
                        conn.execute(select(records.c.record_id, records.c.envelope)).all()
                    )
                assert restored_bytes == envelopes(p)
                copied.reset_sync_after_restore()
                config = p.configs["receiver"].model_copy(
                    update={
                        "database_url": SecretStr(
                            copied.engine.url.render_as_string(hide_password=False)
                        )
                    }
                )
                identity, registry, proxy = register_consumer(config)
                try:
                    register_parent(registry, proxy, p.context)
                    registry.register_local(child_binding, child_query, lambda _: True)
                    registry.register_local(binding, external_query, lambda _: True)
                    restored_observer = Reconciliations(registry, config, identity)
                    restored_observer.register(child_binding.id)
                    restored_review = Resolutions(registry, config, identity, restored_observer)
                    restored_review.register(binding.id)
                    assert not restored_review.active("receiver", name)
                    with pytest.raises(ValueError, match="restored"):
                        await restored_review.review(
                            "receiver", name, name + "-post-restore", binding.id, refs
                        )
                    assert InvocationStore(copied).get("receiver", name) == row
                finally:
                    registry.overlay.store.close()
        after = await executor.invoke(
            "after-review-" + stage, parent.id, parent.digest, {"value": 8}, p.context
        )
        assert after["state"] == "completed" and remaining(p) == allowance - 1
        # Withdrawing review authority reopens capacity while preserving closure
        # history and the old UNKNOWN/held row. It does not reopen execution.
        p.registry.overlay.store.put(
            p.identity.sign(
                Revocation(
                    issuer="receiver", subject=binding.subject, reason="owner query withdrawn"
                )
            )
        )
        assert not review.active("receiver", name)
        assert executor.store.get("receiver", name) == row
        with pytest.raises(UnresolvedEffectsLimit):
            await executor.invoke(
                "after-reopen-" + stage, parent.id, parent.digest, {"value": 9}, p.context
            )
        if os.environ.get("CIO_RECEIPTLESS_RAW_DIRECTORY"):
            target = Path(os.environ["CIO_RECEIPTLESS_RAW_DIRECTORY"]) / f"{stage}-legacy-{legacy}"
            target.mkdir(parents=True, exist_ok=False)
            stores = {"receiver": p.registry.overlay.store, "producer": p.provider}
            original_records = {}
            for owner, store in stores.items():
                actual_store = store.store if owner == "producer" else store
                with actual_store.engine.connect() as conn:
                    original_records[owner] = (
                        conn.execute(select(records.c.envelope).order_by(records.c.sequence))
                        .scalars()
                        .all()
                    )
            public_keys = {
                owner: {
                    "keyid": principal.key.keyid,
                    "key": principal.key.to_dict(),
                    "trust_group": principal.trust_group,
                    "methods": sorted(principal.methods),
                }
                for owner, principal in p.registry.overlay.store.principals.items()
            }
            observation_record = {
                "stage": stage,
                "legacy": legacy,
                "worker_pid": process.pid,
                "worker_exit_code": process.returncode,
                "marker": json.loads(marker.read_text()),
                "original_invocation": row,
                "original_allowance": str(allowance),
                "after_review_allowance": str(remaining(p)),
                "current_capacity_reopened_after_withdrawal": not review.active("receiver", name),
                "original_envelopes_unchanged": True,
                "keys": public_keys,
                "records": original_records,
                "python": sys.version,
                "os": platform.platform(),
                "model_inference_performed": False,
                "fixture_origin": (
                    "synthetic authenticated PG/OPA/A2A physical fault test; "
                    "no private keys/configuration"
                ),
            }
            (target / "observations.json").write_text(
                json.dumps(observation_record, indent=2) + "\n", encoding="utf-8"
            )
    finally:
        if process.returncode is None:
            process.kill()
            await process.communicate()


@pytest.fixture
async def lost_serving(peers):
    config = peers.configs["producer"]
    service = PeerService(config, register_provider)
    server = uvicorn.Server(
        uvicorn.Config(
            LoseResponse(application(config, service.handle)),
            host="127.0.0.1",
            port=urlsplit(config.url).port,
            log_level="critical",
            access_log=False,
        )
    )
    task = asyncio.create_task(server.serve())
    try:
        await ready(config.url, peers.identity)
        yield peers
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 10)
        service.overlay.store.close()


async def test_lost_actual_a2a_response_then_physical_kill_before_unknown_receipt(
    lost_serving, tmp_path
):
    await test_receiptless_worker_loss_requires_whole_owner_review(
        lost_serving, tmp_path, "lost-response", False
    )


@pytest.mark.parametrize("stage", ["nested", "nested-complete"])
async def test_receiptless_parent_inventories_local_and_remote_descendants(
    serving, tmp_path, stage
):
    from receiptless_worker import register_nested

    p = serving
    parent, child, _ = register_nested(p.registry, p.proxy, p.context, p.identity)
    admit(p.registry.overlay, p.identity, child, p.configs["verifier"], dependency=p.proxy)
    admit(p.registry.overlay, p.identity, parent, p.configs["verifier"], dependency=child)
    marker = tmp_path / (stage + ".json")
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(Path(__file__).with_name("receiptless_worker.py")),
        str(p.root / "receiver" / "config.json"),
        str(marker),
        stage,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 30
        while not marker.exists() and time.monotonic() < deadline:
            if process.returncode is not None:
                raise AssertionError((await process.communicate())[1].decode())
            await asyncio.sleep(0.05)
        assert marker.exists()
        process.kill()
        await asyncio.wait_for(process.communicate(), 10)
        assert process.returncode != 0
        executor = Executor(p.registry, p.identity, Reservation(max_unresolved=1))
        name = "receiptless-" + stage
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            executor.store.cleanup_expired(owner="receiver", limit=4)
            row = executor.store.get("receiver", name)
            child_row = executor.store.get("receiver", "local-child")
            if row["state"] == "unknown" and child_row["state"] != "running":
                break
            await asyncio.sleep(0.1)
        assert row["receipt_id"] is None and row["reservation_state"] == "held"
        assert child_row["state"] == ("unknown" if stage == "nested" else "completed")
        assert count(p) == 2
        original_bytes, allowance = envelopes(p), remaining(p)
        saved = p.registry.remote_calls(p.context, invocation_id="local-child")
        assert len(saved) == 2 and p.registry.remote_calls(p.context, invocation_id=name) == ()
        observer = Reconciliations(p.registry, p.configs["receiver"], p.identity)

        async def effect_query(arguments):
            call = RemoteCall.model_validate(arguments["call"])
            actual = InvocationStore(p.provider.store).get("receiver", call.remote_invocation_id)
            assert actual["state"] == "completed" and actual["result_digest"] == fingerprint(
                actual["result"]
            )
            return EffectObservation(
                provider_invocation_id=call.remote_invocation_id,
                provider_binding_digest=call.provider_binding_digest,
                arguments_digest=call.arguments_digest,
                effect="confirmed",
                observation_digest=fingerprint(actual),
                reason="ACTUAL_DESCENDANT_PROVIDER_RESULT",
            ).model_dump(mode="json")

        effect = query_binding(effect_query, "nested-effect-query")
        p.registry.register_local(effect, effect_query, lambda _: True)
        p.registry.overlay.store.put(p.identity.sign(capability(effect)))
        observer.register(effect.id)
        refs = []
        for i, call in enumerate(saved):
            observed = await observer.observe(
                "receiver",
                call.call_key,
                f"{stage}-observe-{i}",
                invocation_id="local-child",
                reconciler=effect.id,
            )
            refs.append(ReceiptRef(issuer="receiver", id=observed.id))
        refs = tuple(refs)

        async def whole_query(arguments):
            state = arguments["state"]
            assert process.returncode is not None and process.returncode != 0
            assert state["request"]["arguments"] == {"value": 7}
            assert state["remote_call_keys"] == sorted(c.call_key for c in saved)
            if state["invocation"]["id"] == name:
                assert len(state["local_children"]) == 1
                descendant = state["local_children"][0]
                assert descendant["invocation"] == child_row
                assert descendant["dispatch"]["invocation_observation"][
                    "parent_invocation"
                ] == fingerprint(["receiver", "receiver", name])
                if stage == "nested":
                    assert descendant["result_receipt"]["resolution"]["original_receipt"] is None
                    assert (
                        descendant["result_receipt"]["resolution"]["independent_verification"]
                        == "UNKNOWN"
                    )
            else:
                assert state["invocation"]["id"] == "local-child" and state["local_children"] == []
            for call in saved:
                actual = InvocationStore(p.provider.store).get(
                    "receiver", call.remote_invocation_id
                )
                assert actual["state"] == "completed" and actual["result_digest"] == fingerprint(
                    actual["result"]
                )
            assert count(p) == 2
            return ResolutionObservation(
                caller="receiver",
                invocation_id=state["invocation"]["id"],
                state_digest=state["state_digest"],
                effect="confirmed",
                all_effects_checked=True,
                all_results_checked=True,
                worker_quiescent=True,
                original_request_checked=True,
                all_children_checked=True,
                observation_digest=fingerprint(
                    {
                        "process_returncode": process.returncode,
                        "descendants": state["local_children"],
                        "provider_calls": [c.model_dump(mode="json") for c in saved],
                    }
                ),
                reason="PHYSICAL_KILL_AND_COMPLETE_DESCENDANT_REVIEW",
            ).model_dump(mode="json")

        whole = query_binding(whole_query, "nested-whole-query")
        p.registry.register_local(whole, whole_query, lambda _: True)
        p.registry.overlay.store.put(p.identity.sign(capability(whole)))
        resolutions = Resolutions(p.registry, p.configs["receiver"], p.identity, observer)
        resolutions.register(whole.id)
        if stage == "nested":
            with pytest.raises(ValueError, match="local descendant"):
                await resolutions.review(
                    "receiver", name, stage + "-missing-child-review", whole.id, refs
                )
            await resolutions.review(
                "receiver", "local-child", stage + "-close-child", whole.id, refs
            )
            assert resolutions.active("receiver", "local-child")
            with pytest.raises(UnresolvedEffectsLimit):
                await executor.invoke(
                    "before-parent-review", parent.id, parent.digest, {"value": 8}, p.context
                )
        with pytest.raises(ValueError, match="every"):
            await resolutions.review("receiver", name, stage + "-omit-grandchildren", whole.id, ())
        event = await resolutions.review("receiver", name, stage + "-close-parent", whole.id, refs)
        assert event.resolution.original_receipt is None and resolutions.active("receiver", name)
        assert remaining(p) == allowance and count(p) == 2
        assert (
            executor.store.get("receiver", name) == row
            and executor.store.get("receiver", "local-child") == child_row
        )
        assert all(envelopes(p)[key] == value for key, value in original_bytes.items())
        p.registry.overlay.store.put(
            p.identity.sign(
                Revocation(
                    issuer="receiver",
                    subject=effect.subject,
                    reason="descendant query authority withdrawn",
                )
            )
        )
        assert not resolutions.active("receiver", name)
        if stage == "nested":
            assert not resolutions.active("receiver", "local-child")
        physical_evidence(
            p,
            stage,
            process,
            original_invocation=row,
            original_child=child_row,
            original_allowance=str(allowance),
            after_review_allowance=str(remaining(p)),
            original_envelopes_unchanged=True,
            current_capacity_reopened_after_withdrawal=True,
        )
    finally:
        if process.returncode is None:
            process.kill()
            await process.communicate()


async def test_actual_partial_provider_result_and_false_quiescence_stay_unknown(
    serving, tmp_path, monkeypatch
):
    p = serving
    parent = register_parent(p.registry, p.proxy, p.context)
    admit(p.registry.overlay, p.identity, parent, p.configs["verifier"], dependency=p.proxy)
    entered, release, ended = ThreadEvent(), ThreadEvent(), ThreadEvent()
    finish = InvocationStore.finish

    def pending_provider(store, claim, result, identity, event, **kwargs):
        if store.store.owner == "producer" and result == 2:
            entered.set()
            try:
                assert release.wait(20)
                return finish(store, claim, result, identity, event, **kwargs)
            finally:
                ended.set()
        return finish(store, claim, result, identity, event, **kwargs)

    monkeypatch.setattr(InvocationStore, "finish", pending_provider)
    marker = tmp_path / "never-completed-parent.json"
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(Path(__file__).with_name("receiptless_worker.py")),
        str(p.root / "receiver" / "config.json"),
        str(marker),
        "completed",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        assert await asyncio.to_thread(entered.wait, 30), (
            "actual second provider never reached its durable completion boundary"
        )
        assert process.returncode is None
        process.kill()
        await asyncio.wait_for(process.communicate(), 10)
        executor = Executor(p.registry, p.identity, Reservation(max_unresolved=1))
        name = "receiptless-completed"
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            executor.store.cleanup_expired(owner="receiver", limit=4)
            row = executor.store.get("receiver", name)
            if row["state"] == "unknown":
                break
            await asyncio.sleep(0.05)
        assert row["state"] == "unknown" and row["receipt_id"] is None
        allowance = remaining(p)
        saved = p.registry.remote_calls(p.context, invocation_id=name)
        assert len(saved) == 2 and count(p) == 2 and not ended.is_set()
        observer = Reconciliations(p.registry, p.configs["receiver"], p.identity)

        async def child_query(arguments):
            call = RemoteCall.model_validate(arguments["call"])
            actual = InvocationStore(p.provider.store).get("receiver", call.remote_invocation_id)
            return EffectObservation(
                provider_invocation_id=call.remote_invocation_id,
                provider_binding_digest=call.provider_binding_digest,
                arguments_digest=call.arguments_digest,
                effect="confirmed" if actual["state"] == "completed" else "unknown",
                observation_digest=fingerprint(actual),
                reason="ACTUAL_PROVIDER_PENDING_OR_COMPLETED",
            ).model_dump(mode="json")

        effect = query_binding(child_query, "pending-effect-query")
        p.registry.register_local(effect, child_query, lambda _: True)
        p.registry.overlay.store.put(p.identity.sign(capability(effect)))
        observer.register(effect.id)

        async def observe(suffix):
            refs = []
            for i, call in enumerate(saved):
                observed = await observer.observe(
                    "receiver",
                    call.call_key,
                    f"{suffix}-{i}",
                    invocation_id=name,
                    reconciler=effect.id,
                )
                refs.append(ReceiptRef(issuer="receiver", id=observed.id))
            return tuple(refs)

        refs = await observe("pending-original")
        review_calls = []

        async def whole_query(arguments):
            review_calls.append(arguments)
            state = arguments["state"]
            # Ignore untrusted requested quiescence; consult actual physical work.
            quiescent = process.returncode is not None and ended.is_set()
            states = [
                InvocationStore(p.provider.store).get("receiver", call.remote_invocation_id)
                for call in saved
            ]
            complete = all(
                actual["state"] == "completed"
                and actual["result_digest"] == fingerprint(actual["result"])
                for actual in states
            )
            return ResolutionObservation(
                caller="receiver",
                invocation_id=name,
                state_digest=state["state_digest"],
                effect="confirmed" if complete else "unknown",
                all_effects_checked=complete,
                all_results_checked=complete,
                worker_quiescent=quiescent,
                original_request_checked=state["request"]["arguments"] == {"value": 7},
                all_children_checked=len(saved) == 2,
                observation_digest=fingerprint(
                    {
                        "provider_rows": states,
                        "worker_returncode": process.returncode,
                        "provider_thread_ended": ended.is_set(),
                    }
                ),
                reason="ACTUAL_PHYSICAL_PROVIDER_CHECK",
            ).model_dump(mode="json")

        whole = query_binding(whole_query, "pending-whole-query")
        p.registry.register_local(whole, whole_query, lambda _: True)
        p.registry.overlay.store.put(p.identity.sign(capability(whole)))
        resolutions = Resolutions(p.registry, p.configs["receiver"], p.identity, observer)
        resolutions.register(whole.id)
        with pytest.raises(ValueError, match="remote effect/result"):
            await resolutions.review(
                "receiver",
                name,
                "cannot-close-pending",
                whole.id,
                refs,
                arguments={"worker_quiescent": True},
            )
        assert review_calls == [] and not resolutions.active("receiver", name)
        assert remaining(p) == allowance and executor.store.get("receiver", name) == row
        release.set()
        assert await asyncio.to_thread(ended.wait, 5)
        refs = await observe("actually-finished")
        event = await resolutions.review(
            "receiver", name, "close-actually-finished", whole.id, refs
        )
        assert event.resolution.original_receipt is None and resolutions.active("receiver", name)
        assert remaining(p) == allowance and executor.store.get("receiver", name) == row
        assert len(review_calls) == 1 and count(p) == 2
        physical_evidence(
            p,
            "partial-provider",
            process,
            original_invocation=row,
            original_allowance=str(allowance),
            after_review_allowance=str(remaining(p)),
            provider_thread_ended=ended.is_set(),
            partial_review_query_calls=0,
            successful_review_query_calls=len(review_calls),
        )
    finally:
        release.set()
        if process.returncode is None:
            process.kill()
            await process.communicate()


async def test_fenced_still_alive_worker_cannot_be_closed_by_requested_quiescence(
    serving, tmp_path
):
    p = serving
    parent = register_parent(p.registry, p.proxy, p.context)
    admit(p.registry.overlay, p.identity, parent, p.configs["verifier"], dependency=p.proxy)
    marker = tmp_path / "physically-still-alive.json"
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(Path(__file__).with_name("receiptless_worker.py")),
        str(p.root / "receiver" / "config.json"),
        str(marker),
        "dispatch",
        "long-lease",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 30
        while not marker.exists() and time.monotonic() < deadline:
            assert process.returncode is None
            await asyncio.sleep(0.05)
        assert marker.exists()
        executor = Executor(p.registry, p.identity, Reservation(max_unresolved=1))
        name = "receiptless-dispatch"
        row = executor.store.cancel("receiver", name)
        assert row["state"] == "unknown" and row["phase"] == "dispatched"
        assert row["reservation_state"] == "held" and row["receipt_id"] is None
        assert process.returncode is None and count(p) == 0
        allowance = remaining(p)

        async def external_query(arguments):
            state = arguments["state"]
            assert state["request"]["arguments"] == {"value": 7}
            assert (
                state["remote_call_keys"] == [] and state["local_children"] == [] and count(p) == 0
            )
            # The actual process handle is the test application's physical witness.
            # An untrusted argument or cancelled lease cannot replace this check.
            return ResolutionObservation(
                caller="receiver",
                invocation_id=name,
                state_digest=state["state_digest"],
                effect="absent",
                all_effects_checked=True,
                all_results_checked=True,
                worker_quiescent=process.returncode is not None,
                original_request_checked=True,
                all_children_checked=True,
                observation_digest=fingerprint(
                    {"actual_process_returncode": process.returncode, "provider_witness": count(p)}
                ),
                reason="ACTUAL_PROCESS_HANDLE_AND_PROVIDER_INVENTORY",
            ).model_dump(mode="json")

        binding = query_binding(external_query, "physical-quiescence-query")
        p.registry.register_local(binding, external_query, lambda _: True)
        p.registry.overlay.store.put(p.identity.sign(capability(binding)))
        review = Resolutions(
            p.registry,
            p.configs["receiver"],
            p.identity,
            Reconciliations(p.registry, p.configs["receiver"], p.identity),
        )
        review.register(binding.id)
        with pytest.raises(ValueError, match="physical quiescence"):
            await review.review(
                "receiver",
                name,
                "false-requested-quiescence",
                binding.id,
                (),
                arguments={"worker_quiescent": True},
            )
        assert process.returncode is None and not review.active("receiver", name)
        assert remaining(p) == allowance and executor.store.get("receiver", name) == row
        process.kill()
        await asyncio.wait_for(process.communicate(), 10)
        assert process.returncode != 0
        event = await review.review("receiver", name, "actual-physical-quiescence", binding.id, ())
        assert event.resolution.effect == "absent" and event.resolution.original_receipt is None
        assert review.active("receiver", name) and remaining(p) == allowance
        assert executor.store.get("receiver", name) == row and count(p) == 0
        physical_evidence(
            p,
            "fenced-alive-worker",
            process,
            original_invocation=row,
            original_allowance=str(allowance),
            after_review_allowance=str(remaining(p)),
            false_requested_quiescence_rejected=True,
        )
    finally:
        if process.returncode is None:
            process.kill()
            await process.communicate()
