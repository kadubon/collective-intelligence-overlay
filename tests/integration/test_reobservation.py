"""CIO-030-03: real database, controlled clocks, and the unchanged execution ledger."""

import asyncio
import json
import os
import subprocess
import sys
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, update
from test_opportunities import configured_steps, setup

from collective_intelligence_overlay import invocations as invocation_module
from collective_intelligence_overlay import opportunities as observation_module
from collective_intelligence_overlay import reobservation as renewal_module
from collective_intelligence_overlay import steps as selection_module
from collective_intelligence_overlay import storage as storage_module
from collective_intelligence_overlay.allocation import AllocationPolicy, allocate
from collective_intelligence_overlay.bindings import Registry
from collective_intelligence_overlay.config import Config, TrustedIdentity
from collective_intelligence_overlay.invocations import invocation_request, invocations
from collective_intelligence_overlay.models import Capability, Revocation, Verdict, now
from collective_intelligence_overlay.opportunities import (
    Opportunities,
    ProposalDraft,
    ProposalDrafts,
    propose,
)
from collective_intelligence_overlay.queries import RecordQuery
from collective_intelligence_overlay.reobservation import ReobservationPolicy, instances, requests
from collective_intelligence_overlay.security import verify
from collective_intelligence_overlay.steps import Selection, Steps
from collective_intelligence_overlay.storage import (
    Conflict,
    budgets,
    leases,
)
from collective_intelligence_overlay.storage import (
    records as record_table,
)


@pytest.fixture
def clock(monkeypatch):
    value = [now()]
    for module in (
        observation_module,
        renewal_module,
        selection_module,
        invocation_module,
        storage_module,
    ):
        monkeypatch.setattr(module, "now", lambda: value[0])
    return value


def proposals(host, opportunity, identities, value=3):
    goal = host.goal(opportunity.goal_id)
    reference = host.registry.overlay.store.reference("opportunity", "receiver", opportunity.id)
    proposal = propose(
        opportunity,
        reference,
        identities["producer"],
        ProposalDrafts(
            alternatives=(
                ProposalDraft(
                    builder=goal.builders[0], arguments={"value": value}, alternative="installed"
                ),
            )
        ),
    )[0]
    return (("producer", identities["producer"].sign(proposal)),)


def budget(store):
    with store.engine.connect() as conn:
        return conn.execute(
            select(budgets.c.remaining).where(budgets.c.unit == "work")
        ).scalar_one()


def envelope(store, opportunity_id):
    with store.engine.connect() as conn:
        return conn.execute(
            select(record_table.c.envelope).where(
                (record_table.c.kind == "opportunity")
                & (record_table.c.issuer == "receiver")
                & (record_table.c.record_id == opportunity_id)
            )
        ).scalar_one()


def old_choice(steps, opportunity, envelopes):
    caller, envelope = envelopes[0]
    proposal = steps.opportunities.validate_proposal(envelope, caller, steps.context)
    steps.store.put(envelope)
    choice = Selection(
        owner="receiver",
        opportunity=steps.store.reference("opportunity", "receiver", opportunity.id),
        proposal=steps.store.reference("proposal", caller, proposal.id),
        invocation_id="original",
        reasons=("installed",),
        skipped=(),
        estimates=(),
    )
    assert steps._choice(opportunity.id, choice) == choice
    request = invocation_request(
        "receiver", proposal.builder.id, proposal.builder.digest, proposal.arguments, steps.context
    )
    return choice, proposal, request


async def test_expiry_reobservation_retry_concurrency_restart_and_finite_limit(
    overlay, identities, records, clock
):
    host, goal, _ = setup(overlay, identities, records)
    goal = goal.model_copy(update={"lifetime_seconds": 10})
    policy = ReobservationPolicy(cooldown_seconds=60, max_reissues=2)
    host = Opportunities(
        host.registry, identities["receiver"], (goal,), reobservation_policy=policy
    )
    overlay.store.set_budget("work", Decimal(4))
    original = (await host.discover()).opportunities[0]
    original_envelope = envelope(overlay.store, original.id)
    clock[0] += timedelta(seconds=11)
    expired = await host.discover()
    assert expired.opportunities == () and expired.expired == (original,)
    assert expired.next_action == "reobserve"
    with pytest.raises(ValueError, match="local owner"):
        await host.reobserve(original.id, "other", "expired", caller="producer")
    refused = await host.reobserve(original.id, "early", "expired", caller="receiver")
    assert refused.state == "cooldown" and refused.reissue_count == 0
    clock[0] += timedelta(seconds=50)
    first, retry = await asyncio.gather(
        *(host.reobserve(original.id, "first", "expired", caller="receiver") for _ in range(2))
    )
    assert first.opportunity == retry.opportunity and {first.replayed, retry.replayed} == {
        False,
        True,
    }
    current = first.opportunity
    assert first.state == "issued" and first.reissue_count == 1
    assert current.id != original.id and current.supersedes == original.id
    assert current.observation_digest == original.observation_digest
    assert current.basis != original.basis and current.expires_at > clock[0]
    assert envelope(overlay.store, original.id) == original_envelope
    assert (await host.discover()).opportunities == (current,)
    with pytest.raises(Conflict, match="different arguments"):
        await host.reobserve(original.id, "first", "different", caller="receiver")
    # Independent requests converge on the same still-valid instance.
    parallel = await asyncio.gather(
        *(
            host.reobserve(original.id, f"parallel-{index}", "expired", caller="receiver")
            for index in range(4)
        )
    )
    assert all(r.state == "existing_instance" and r.opportunity == current for r in parallel)
    clock[0] += timedelta(seconds=61)
    restarted = Opportunities(
        host.registry, identities["receiver"], (goal,), reobservation_policy=policy
    )
    second = await restarted.reobserve(current.id, "second", "expired", caller="receiver")
    assert second.state == "issued" and second.reissue_count == 2
    assert second.opportunity.supersedes == current.id
    clock[0] += timedelta(seconds=61)
    limit = await restarted.reobserve(second.opportunity.id, "third", "expired", caller="receiver")
    assert limit.state == "reissue_limit" and limit.reissue_count == 2
    assert len(overlay.store.record_page(RecordQuery(kinds=("opportunity",))).items) == 3
    assert budget(overlay.store) == 4
    with overlay.store.engine.connect() as conn:
        assert set(conn.execute(select(instances.c.cause_id)).scalars()) == {first.cause_id}
        assert len(conn.execute(select(requests)).all()) == 8


@pytest.mark.parametrize("phase", ["selected", "reserved", "dispatched", "unknown"])
async def test_renewed_instance_cannot_bypass_pending_or_uncertain_execution(
    overlay, identities, records, clock, phase
):
    steps, original, envelopes = await configured_steps(overlay, identities, records)
    choice, proposal, request = old_choice(steps, original, envelopes)
    if phase != "selected":
        claim, fresh = steps.executor.store.claim(
            "receiver",
            choice.invocation_id,
            proposal.builder.id,
            proposal.builder.digest,
            request,
            steps.executor.allowance,
        )
        assert fresh
        if phase in {"dispatched", "unknown"}:
            steps.executor.store.dispatched(claim)
        if phase == "unknown":
            steps.executor.store.cancel("receiver", choice.invocation_id)
    clock[0] = original.expires_at + timedelta(seconds=1)
    renewed = await steps.opportunities.reobserve(
        original.id, "renew", "expired", caller="receiver", new_attempt=True
    )
    assert renewed.state == "issued"
    current = renewed.opportunity
    before = budget(overlay.store)
    result = await steps.step(current.id, proposals(steps.opportunities, current, identities))
    assert result.reason == "reconciliation_required" and result.invocation is None
    assert steps._choice(current.id) is None
    assert steps._choice(original.id) == choice
    assert budget(overlay.store) == before
    with overlay.store.engine.connect() as conn:
        assert len(conn.execute(select(invocations)).all()) == (0 if phase == "selected" else 1)


async def test_updated_host_contract_cannot_hide_an_old_unknown(
    overlay, identities, records, clock
):
    steps, original, envelopes = await configured_steps(overlay, identities, records)
    choice, proposal, request = old_choice(steps, original, envelopes)
    claim, _ = steps.executor.store.claim(
        "receiver",
        choice.invocation_id,
        proposal.builder.id,
        proposal.builder.digest,
        request,
        steps.executor.allowance,
    )
    steps.executor.store.dispatched(claim)
    steps.executor.store.cancel("receiver", choice.invocation_id)
    goal = steps.opportunities.goal(original.goal_id)
    changed = goal.model_copy(update={"revision": "2", "checker_arguments": {"value": 0}})
    assert changed.contract_digest != goal.contract_digest
    host = Opportunities(steps.opportunities.registry, identities["receiver"], (changed,))
    current = (await host.discover()).opportunities[0]
    assert current.supersedes == original.id
    worker = Steps(host, steps.executor, steps.context)
    result = await worker.step(current.id, proposals(host, current, identities))
    assert result.reason == "reconciliation_required" and worker._choice(current.id) is None
    assert budget(overlay.store) == 3
    with overlay.store.engine.connect() as conn:
        assert len(set(conn.execute(select(instances.c.cause_id)).scalars())) == 1


async def test_completed_matching_result_is_queried_without_new_choice_or_charge(
    overlay, identities, records, clock
):
    steps, original, envelopes = await configured_steps(overlay, identities, records)
    completed = await steps.step(original.id, envelopes[:1])
    clock[0] = original.expires_at + timedelta(seconds=1)
    renewed = await steps.opportunities.reobserve(
        original.id, "renew", "expired", caller="receiver", new_attempt=True
    )
    result = await steps.step(
        renewed.opportunity.id, proposals(steps.opportunities, renewed.opportunity, identities)
    )
    assert result.reason == "existing_invocation"
    assert result.selection == completed.selection and result.invocation == completed.invocation
    assert steps._choice(renewed.opportunity.id) is None and budget(overlay.store) == 3
    with overlay.store.engine.connect() as conn:
        assert len(conn.execute(select(invocations)).all()) == 1


async def test_changed_observation_does_not_reuse_a_result_from_old_evidence(
    overlay, identities, records, clock
):
    steps, old, envelopes = await configured_steps(overlay, identities, records)
    completed = await steps.step(old.id, envelopes[:1])
    goal = steps.opportunities.goal(old.goal_id)
    cap = Capability.model_validate(
        {
            **records[0].model_dump(),
            "schema_version": "2",
            "issuer": "receiver",
            "subject": goal.request.subject,
            "binding_digest": goal.request.binding_digest,
        }
    )
    overlay.store.put(identities["receiver"].sign(cap))
    current = (await steps.opportunities.discover()).opportunities[0]
    assert current.observation_digest != old.observation_digest
    signed = proposals(steps.opportunities, current, identities)
    refused = await steps.step(current.id, signed)
    assert refused.reason == "new_attempt_required" and refused.invocation is None
    permission = await steps.opportunities.reobserve(
        current.id, "explicit", "changed-evidence", caller="receiver", new_attempt=True
    )
    assert permission.state == "existing_instance"
    result = await steps.step(current.id, signed)
    assert result.invocation["state"] == "completed"
    assert result.selection.invocation_id != completed.selection.invocation_id
    assert budget(overlay.store) == 2


@pytest.mark.parametrize("released", [True, False])
async def test_explicit_new_attempt_requires_positive_undispatched_release_proof(
    overlay, identities, records, clock, released
):
    steps, original, envelopes = await configured_steps(overlay, identities, records)
    choice, proposal, request = old_choice(steps, original, envelopes)
    claim, _ = steps.executor.store.claim(
        "receiver",
        choice.invocation_id,
        proposal.builder.id,
        proposal.builder.digest,
        request,
        steps.executor.allowance,
    )
    if not released:
        steps.executor.store.dispatched(claim)
    cancelled = steps.executor.store.cancel("receiver", choice.invocation_id)
    assert cancelled["reservation_state"] == ("released" if released else "held")
    clock[0] = original.expires_at + timedelta(seconds=1)
    renewed = await steps.opportunities.reobserve(
        original.id, "observe", "expired", caller="receiver"
    )
    current = renewed.opportunity
    signed = proposals(steps.opportunities, current, identities)
    blocked = await steps.step(current.id, signed)
    assert blocked.reason == ("new_attempt_required" if released else "reconciliation_required")
    permission = await steps.opportunities.reobserve(
        current.id, "owner-attempt", "retry-released", caller="receiver", new_attempt=True
    )
    assert permission.state == "existing_instance" and permission.opportunity == current
    result = await steps.step(current.id, signed)
    if released:
        assert result.invocation["state"] == "completed" and result.invocation["result"] == {
            "value": 3
        }
        assert result.selection.invocation_id != choice.invocation_id and budget(overlay.store) == 3
        with pytest.raises(Conflict, match="ownership"):
            steps.executor.store.dispatched(claim)
    else:
        assert result.reason == "reconciliation_required" and budget(overlay.store) == 3
    with overlay.store.engine.connect() as conn:
        row = (
            conn.execute(select(leases).where(leases.c.task_id == claim["lease_id"]))
            .mappings()
            .one()
        )
        assert row["fence"] > claim["fence"] and row["actual"] is None


async def test_actual_predispatch_refusal_can_resume_after_freshness_recovers(
    overlay, identities, records, clock
):
    steps, old, envelopes = await configured_steps(overlay, identities, records)
    overlay.observed_sources["verifier"] = now() - timedelta(seconds=301)
    refused = await steps.step(old.id, envelopes[:1])
    assert refused.invocation["state"] == "unknown"
    assert refused.invocation["phase"] == "reserved"
    assert refused.invocation["reservation_state"] == "released"
    overlay.observed("verifier")
    clock[0] = old.created_at + timedelta(seconds=61)
    renewed = await steps.opportunities.reobserve(
        old.id, "retry-refusal", "freshness-restored", caller="receiver", new_attempt=True
    )
    assert renewed.state == "issued" and renewed.opportunity.supersedes == old.id
    result = await steps.step(
        renewed.opportunity.id, proposals(steps.opportunities, renewed.opportunity, identities)
    )
    assert result.invocation["state"] == "completed" and result.invocation["result"] == {"value": 3}
    assert budget(overlay.store) == 3
    retained = steps.executor.store.get("receiver", refused.selection.invocation_id)
    assert retained["state"] == "unknown" and retained["reservation_state"] == "released"


async def test_proven_release_can_reissue_before_expiry_with_owner_intent(
    overlay, identities, records, clock
):
    steps, original, envelopes = await configured_steps(overlay, identities, records)
    choice, proposal, request = old_choice(steps, original, envelopes)
    steps.executor.store.claim(
        "receiver",
        choice.invocation_id,
        proposal.builder.id,
        proposal.builder.digest,
        request,
        steps.executor.allowance,
    )
    steps.executor.store.cancel("receiver", choice.invocation_id)
    clock[0] = original.created_at + timedelta(seconds=61)
    assert clock[0] < original.expires_at
    first, second = await asyncio.gather(
        *(
            steps.opportunities.reobserve(
                original.id, name, "retry-released", caller="receiver", new_attempt=True
            )
            for name in ("one", "two")
        )
    )
    assert {first.state, second.state} == {"issued", "existing_instance"}
    assert first.opportunity == second.opportunity and first.opportunity.supersedes == original.id
    result = await steps.step(
        first.opportunity.id, proposals(steps.opportunities, first.opportunity, identities)
    )
    assert result.invocation["state"] == "completed" and budget(overlay.store) == 3


async def test_observation_does_not_transfer_proposals_and_budget_can_resume(
    overlay, identities, records, clock
):
    steps, original, old = await configured_steps(overlay, identities, records, amount=0)
    assert (await steps.step(original.id, old)).reason == "insufficient_allowance"
    clock[0] = original.expires_at + timedelta(seconds=1)
    receipt = await steps.opportunities.reobserve(
        original.id, "renew", "budget-restored", caller="receiver"
    )
    current = receipt.opportunity
    assert (await steps.step(current.id, old)).reason == "no_valid_alternatives"
    assert steps._choice(current.id) is None and budget(overlay.store) == 0
    # Operator replenishment is explicit; Store.set_budget initializes a new unit.
    with overlay.store.engine.begin() as conn:
        conn.execute(select(budgets.c.unit).where(budgets.c.unit == "work").with_for_update()).one()
        conn.execute(update(budgets).where(budgets.c.unit == "work").values(remaining=Decimal(2)))
    fresh = proposals(steps.opportunities, current, identities)
    result = await steps.step(current.id, fresh)
    assert result.invocation["state"] == "completed" and budget(overlay.store) == 1
    assert result.selection.proposal.id != verify(old[0][1], overlay.store.principals).id


async def test_fresh_revision_and_withdrawal_are_preserved_in_reobservation(
    overlay, identities, records, clock
):
    host, goal, binding = setup(overlay, identities, records)
    original = (await host.discover()).opportunities[0]
    cap = Capability.model_validate(
        {
            **records[0].model_dump(),
            "schema_version": "2",
            "issuer": "receiver",
            "subject": goal.request.subject,
            "binding_digest": binding.digest,
        }
    )
    overlay.store.put(identities["receiver"].sign(cap))
    withdrawal = Revocation(issuer="receiver", subject=cap.subject, reason="known-negative")
    overlay.store.put(identities["receiver"].sign(withdrawal))
    clock[0] = original.expires_at + timedelta(seconds=1)
    renewed = await host.reobserve(original.id, "recheck", "withdrawn", caller="receiver")
    assert renewed.state == "issued" and renewed.opportunity.work_kind == "repair"
    assert "known_revocation" in renewed.opportunity.reasons
    decision = overlay.store.resolve_reference(renewed.opportunity.basis[0])
    assert decision.revisions != overlay.store.resolve_reference(original.basis[0]).revisions
    assert overlay.store.revocations() == [withdrawal]
    assert {e.verdict for e in overlay.store.evidence()} == {"PASS"}


async def test_satisfied_goal_makes_no_instance_and_receipt_remains_historical(
    overlay, identities, records, clock
):
    host, goal, binding = setup(overlay, identities, records)
    original = (await host.discover()).opportunities[0]
    cap = Capability.model_validate(
        {
            **records[0].model_dump(),
            "schema_version": "2",
            "issuer": "receiver",
            "subject": goal.request.subject,
            "binding_digest": binding.digest,
        }
    )
    evidence = records[1].model_copy(
        update={
            "schema_version": "2",
            "id": "satisfied-check",
            "subject": cap.subject,
            "binding_digest": binding.digest,
        }
    )
    for record in (cap, evidence):
        overlay.store.put(identities[record.issuer].sign(record))
    clock[0] = original.expires_at + timedelta(seconds=1)
    result = await host.reobserve(original.id, "satisfied", "new-check", caller="receiver")
    assert result.state == "satisfied" and result.opportunity is None
    assert (await host.discover()).satisfied == 1
    assert len(overlay.store.record_page(RecordQuery(kinds=("opportunity",))).items) == 1
    withdrawal = Revocation(issuer="receiver", subject=cap.subject, reason="later-withdrawal")
    overlay.store.put(identities["receiver"].sign(withdrawal))
    replay = await host.reobserve(original.id, "satisfied", "new-check", caller="receiver")
    assert replay.replayed and replay.state == "satisfied"  # Receipt is not a current grant.
    current = await host.reobserve(original.id, "new-command", "withdrawn", caller="receiver")
    assert current.state == "issued" and "known_revocation" in current.opportunity.reasons


@pytest.mark.parametrize("negative", ["dissent", "obligation"])
async def test_reissue_retains_negative_evidence_and_obligations(
    overlay, identities, records, clock, negative
):
    host, goal, binding = setup(overlay, identities, records)
    original = (await host.discover()).opportunities[0]
    cap = Capability.model_validate(
        {
            **records[0].model_dump(),
            "schema_version": "2",
            "issuer": "receiver",
            "subject": goal.request.subject,
            "binding_digest": binding.digest,
            "obligations": ("operator-review",) if negative == "obligation" else (),
        }
    )
    evidence = records[1].model_copy(
        update={
            "schema_version": "2",
            "id": "dissent",
            "subject": cap.subject,
            "binding_digest": binding.digest,
            "verdict": Verdict.FAIL,
        }
    )
    overlay.store.put(identities["receiver"].sign(cap))
    if negative == "dissent":
        overlay.store.put(identities["verifier"].sign(evidence))
    clock[0] = original.expires_at + timedelta(seconds=1)
    current = await host.reobserve(original.id, "new-check", negative, caller="receiver")
    expected = "in_scope_counterexample" if negative == "dissent" else "unresolved_obligations"
    assert expected in current.opportunity.reasons
    assert (await overlay.qualify(goal.request)).outcome != "ACCEPT"
    if negative == "dissent":
        assert {e.verdict for e in overlay.store.evidence()} == {"PASS", "FAIL"}
    else:
        exact = overlay.store.record_page(
            RecordQuery(kinds=("capability",), issuer="receiver", subject=cap.subject), limit=1
        ).items[0]
        assert exact.obligations == ("operator-review",)


async def test_checker_recovery_rechecks_installed_grant_before_selection(
    overlay, identities, records, clock
):
    steps, _, _ = await configured_steps(overlay, identities, records)
    goal = steps.opportunities.goal("transformation")
    goal = goal.model_copy(update={"checker_arguments": {"value": 0}})
    cap = Capability.model_validate(
        {
            **records[0].model_dump(),
            "schema_version": "2",
            "issuer": "receiver",
            "subject": goal.request.subject,
            "binding_digest": goal.request.binding_digest,
        }
    )
    overlay.store.put(identities["receiver"].sign(cap))
    unavailable = Opportunities(Registry(overlay), identities["receiver"], (goal,))
    old = (await unavailable.discover()).opportunities[0]
    assert old.work_kind == "verification"
    policy = AllocationPolicy(verification_threshold=1, minimum_samples=1, reserve_operations=0)
    deferred = await allocate(unavailable, steps.context, (old,), policy)
    assert deferred.deferred == {old.id: "checker_unavailable"}
    clock[0] = old.expires_at + timedelta(seconds=1)
    restored = Opportunities(steps.opportunities.registry, identities["receiver"], (goal,))
    current = await restored.reobserve(old.id, "checker-restored", "installed", caller="receiver")
    ready = await allocate(restored, steps.context, (current.opportunity,), policy)
    assert ready.qualified_checkers == (goal.checker,) and ready.ordered == (
        current.opportunity.id,
    )
    worker = Steps(restored, steps.executor, steps.context)
    result = await worker.step(
        current.opportunity.id,
        proposals(restored, current.opportunity, identities),
        allocation=ready,
    )
    assert result.invocation["state"] == "completed"


async def test_revision_change_between_observation_and_commit_does_not_publish(
    overlay, identities, records, clock, monkeypatch
):
    host, goal, binding = setup(overlay, identities, records)
    original = (await host.discover()).opportunities[0]
    clock[0] = original.expires_at + timedelta(seconds=1)
    observe = host._observe

    async def changed(goal):
        candidate = await observe(goal)
        cap = Capability.model_validate(
            {
                **records[0].model_dump(),
                "schema_version": "2",
                "issuer": "receiver",
                "subject": goal.request.subject,
                "binding_digest": binding.digest,
            }
        )
        overlay.store.put(identities["receiver"].sign(cap))
        return candidate

    monkeypatch.setattr(host, "_observe", changed)
    with pytest.raises(Conflict, match="observation changed"):
        await host.reobserve(original.id, "racing", "expired", caller="receiver")
    assert len(overlay.store.record_page(RecordQuery(kinds=("opportunity",))).items) == 1
    with overlay.store.engine.connect() as conn:
        assert conn.execute(select(requests)).first() is None


async def test_cli_reobservation_retries_across_real_processes_without_sleep(
    overlay, identities, records, clock, tmp_path
):
    from pydantic import SecretStr

    clock[0] -= timedelta(seconds=180)
    host, goal, _ = setup(overlay, identities, records)
    goal = goal.model_copy(update={"lifetime_seconds": 60})
    host = Opportunities(host.registry, identities["receiver"], (goal,))
    original = (await host.discover()).opportunities[0]
    key = tmp_path / "identity.pem"
    key.write_bytes(identities["receiver"].signer.private_bytes)
    config = Config(
        owner="receiver",
        database_url=SecretStr(overlay.store.engine.url.render_as_string(hide_password=False)),
        private_key=key,
        artifact_directory=tmp_path,
        opa_binary=os.environ["CIO_OPA"],
        url="http://127.0.0.1:19000/",
        local_development=True,
        identities={
            name: TrustedIdentity(
                keyid=identity.signer.public_key.keyid,
                key=identity.signer.public_key.to_dict(),
                trust_group=name,
                methods=("csv-check",),
            )
            for name, identity in identities.items()
        },
    )
    config_path, goal_path = tmp_path / "config.json", tmp_path / "goal.json"
    config_path.write_text(config.model_dump_json(), encoding="utf-8")
    # SecretStr's JSON serialization is redacted; write the explicit operator configuration.
    data = json.loads(config_path.read_text())
    data["database_url"] = config.database_url.get_secret_value()
    config_path.write_text(json.dumps(data), encoding="utf-8")
    goal_path.write_text(goal.model_dump_json(), encoding="utf-8")
    command = [
        sys.executable,
        "-c",
        "from collective_intelligence_overlay.cli import main; raise SystemExit(main())",
        "reobserve",
        "--config",
        str(config_path),
        "--goal-file",
        str(goal_path),
        "--opportunity-id",
        original.id,
        "--request-id",
        "process-request",
        "--reason",
        "expired",
    ]
    results = [
        await asyncio.to_thread(
            subprocess.run, command, capture_output=True, text=True, check=True, timeout=30
        )
        for _ in range(2)
    ]
    first, replay = (json.loads(result.stdout) for result in results)
    assert first["state"] == "issued" and first["reissue_count"] == 1
    assert replay["replayed"] is True and replay["opportunity"] == first["opportunity"]
    assert len(overlay.store.record_page(RecordQuery(kinds=("opportunity",))).items) == 2
