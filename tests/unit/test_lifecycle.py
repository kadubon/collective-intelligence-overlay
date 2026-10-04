import json
import socket
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from collective_intelligence_overlay.lifecycle import (
    CapabilityIdentity,
    ContributionRelation,
    HandoffObservation,
    HandoffRole,
    ObservationContext,
    ResidualKind,
    StockCoordinates,
    StockEntry,
    StockObservation,
    build_handoff,
    inspect_lifecycle,
    observe_contributions,
    observe_growth,
    snapshot_from_material,
)
from collective_intelligence_overlay.models import (
    Capability,
    Cost,
    Decision,
    Event,
    ExecutionReceipt,
    FormationInput,
    FormationReceipt,
    ReceiptRef,
    Revocation,
    Scope,
    Subject,
    UseRequest,
    Verdict,
)
from collective_intelligence_overlay.security import Principal, digest
from collective_intelligence_overlay.storage import Conflict, projection_digest

START = datetime(2026, 10, 4, tzinfo=UTC)
SCOPE = Scope(
    task="sum", input_contract="rows.v1", output_contract="sum.v1", environment={"tool": "1"}
)
POLICY = digest(b"policy")


def capability(name="sum", issuer="producer"):
    return Capability(
        schema_version="2",
        issuer=issuer,
        subject=Subject(id=name, version="1", digest=digest(name.encode())),
        binding_digest=digest(("binding-" + name).encode()),
        scope=SCOPE,
        entrypoint=name,
        claim="sum-contract",
        provenance="explicit synthetic unit fixture",
        classification="declared-new",
        created_at=START,
        expires_at=START + timedelta(days=1),
    )


def target(cap):
    return CapabilityIdentity(
        issuer=cap.issuer, subject=cap.subject, binding_digest=cap.binding_digest
    )


def context(cutoff=START + timedelta(minutes=1), coverage="complete", **kwargs):
    return ObservationContext(
        owner="receiver",
        receiver="receiver",
        scope=SCOPE,
        policy_digest=POLICY,
        cutoff=cutoff,
        observed_at=cutoff,
        feed_generation="test-generation",
        prefix=100,
        coverage=coverage,
        coverage_basis="Explicit finite synthetic test material only.",
        **kwargs,
    )


def snapshot(*records, ctx=None, principals=None, signed=False):
    ctx = ctx or context()
    material = {"view_schema_version": "1", "context": ctx.model_dump(mode="json"), "records": []}
    for index, record in enumerate(records):
        material["records"].append(
            {
                "format": "dsse" if signed else "unsigned",
                "document": record if signed else record.model_dump(mode="json"),
                "received_at": START.isoformat(),
                "sequence": index + 1,
            }
        )
    return snapshot_from_material(
        material, owner="receiver", caller="receiver", principals=principals
    )


def use(cap, name="use-1", invocation=None, result=b"result", transport="local", **kwargs):
    return Event(
        schema_version="2",
        id=name,
        issuer="receiver",
        subject=cap.subject,
        action="reuse",
        task_id=name,
        attempt_id=name,
        correlation_id="fixture",
        occurred_at=START,
        execution=ExecutionReceipt(
            invocation_id=invocation or name,
            caller="receiver",
            resource_owner="receiver",
            capability_issuer=cap.issuer,
            binding_digest=cap.binding_digest,
            arguments_digest=digest(b"input"),
            result_digest=digest(result),
            scope=SCOPE,
            policy_digest=POLICY,
            state="completed",
            transport=transport,
        ),
        **kwargs,
    )


def stock(caps, accepted, *, cutoff, coverage="complete", policy=POLICY, unknown=()):
    ctx = context(cutoff, coverage).model_copy(update={"policy_digest": policy})
    coordinates = StockCoordinates(
        receiver="receiver",
        scope=SCOPE,
        policy_digest=policy,
        target_universe=tuple(target(cap) for cap in caps),
    )
    entries, sources = [], []
    for index, cap in enumerate(caps):
        state = (
            "unknown" if index in unknown else "accepted" if index in accepted else "nonaccepted"
        )
        decision = Decision(
            id=f"decision-{index}-{int(cutoff.timestamp())}",
            request=UseRequest(
                receiver="receiver",
                subject=cap.subject,
                scope=SCOPE,
                capability_issuer=cap.issuer,
                binding_digest=cap.binding_digest,
            ),
            outcome="ACCEPT"
            if state == "accepted"
            else "UNKNOWN"
            if state == "unknown"
            else "REJECT",
            reasons=(),
            policy_digest=policy,
            evaluated_at=cutoff - timedelta(seconds=1),
            valid_until=cutoff + timedelta(minutes=5),
        )
        observed = snapshot(decision, ctx=ctx).records[0].source
        sources.append(observed)
        entries.append(
            StockEntry(
                target=target(cap),
                availability=state,
                decision=decision,
                reference=observed.reference,
            )
        )
    return StockObservation(
        context=ctx,
        sources=tuple(sources),
        residuals=(),
        coordinates=coordinates,
        entries=tuple(entries),
        assessment_started_at=cutoff - timedelta(seconds=1),
        assessment_completed_at=cutoff,
    )


def test_candidate_only_does_not_create_generation_evidence_decision_or_use():
    cap = capability()
    view = inspect_lifecycle(snapshot(cap), target(cap))
    assert view.candidate_observed is True and view.generation_observed is None
    assert view.evidence == view.decisions == view.withdrawals == view.costs == ()
    assert view.current_admission == "unassessed" and view.execution_authority == "not_granted"
    assert {r.kind for r in view.residuals} >= {
        ResidualKind.MISSING_EVIDENCE,
        ResidualKind.UNKNOWN_COST,
    }
    assert len(view.contributions) == 1
    assert view.contributions[0].relations == (ContributionRelation.NEW_CANDIDATE,)


def test_receiver_decisions_and_unknown_reason_are_retained(records):
    cap = records[0]
    decisions = tuple(
        Decision(
            id=f"decision-{receiver}",
            request=UseRequest(
                receiver=receiver,
                subject=cap.subject,
                scope=cap.scope,
                capability_issuer=cap.issuer,
                binding_digest=None,
            ),
            outcome=outcome,
            reasons=("future_unknown_reason",),
            policy_digest=POLICY,
            evaluated_at=START,
            valid_until=START + timedelta(days=1),
        )
        for receiver, outcome in (("receiver", "ACCEPT"), ("other", "REJECT"))
    )
    view = inspect_lifecycle(snapshot(cap, *decisions), target(cap))
    assert [(d.request.receiver, d.outcome) for d in view.decisions] == [
        ("receiver", "ACCEPT"),
        ("other", "REJECT"),
    ]
    assert any(r.explanation == "future_unknown_reason" for r in view.residuals)
    assert view.current_admission == "unassessed"


def test_pass_fail_withdrawal_expiry_and_obligations_remain(records):
    cap, evidence = records
    evidence = evidence.model_copy(
        update={
            "created_at": START,
            "expires_at": START + timedelta(seconds=5),
            "obligations": ("operator-check-original",),
        }
    )
    failed = evidence.model_copy(update={"id": "later-fail", "verdict": Verdict.FAIL})
    revoked = Revocation(
        id="withdraw",
        issuer=evidence.issuer,
        subject=cap.subject,
        evidence_id=evidence.id,
        reason="withdrawn",
        created_at=START,
    )
    view = inspect_lifecycle(snapshot(cap, evidence, failed, revoked), target(cap))
    assert [e["verdict"] for e in view.evidence] == ["PASS", "FAIL"]
    assert all(e["expired_at_cutoff"] for e in view.evidence)
    assert len(view.withdrawals) == 1
    assert any(r.kind == ResidualKind.STALE_SOURCE for r in view.residuals)
    assert any(r.explanation == "operator-check-original" for r in view.residuals)


def test_replay_cost_position_and_distinct_invocations():
    cap = capability()
    cost = Cost(category="use", status="measured", quantity=Decimal("2"), unit="tokens")
    first, second = use(cap, costs=(cost,)), use(cap, "use-2", costs=(cost,))
    view = inspect_lifecycle(snapshot(cap, first, first, second), target(cap))
    assert sum(ContributionRelation.REUSE in c.relations for c in view.contributions) == 2
    assert len(view.costs) == 2 and view.cost_subtotals[0].quantity == 4
    duplicate_receipt = use(cap, "second-report", invocation=first.execution.invocation_id)
    assert (
        len(
            [
                c
                for c in observe_contributions(snapshot(first, duplicate_receipt))
                if c.invocation_id
            ]
        )
        == 1
    )
    with pytest.raises(Conflict):
        observe_contributions(
            snapshot(first, use(cap, "conflict", invocation=first.id, result=b"other"))
        )
    with pytest.raises(ValueError, match="source identity content conflict"):
        snapshot(first, first.model_copy(update={"costs": ()}))


def test_four_copies_never_become_four_functionally_new_capabilities():
    original = capability()
    copies = tuple(
        capability(issuer=f"peer-{i}").model_copy(update={"classification": "replicated"})
        for i in range(4)
    )
    contributions = observe_contributions(snapshot(original, *copies))
    assert sum(ContributionRelation.COPY in c.relations for c in contributions) == 4
    assert all(
        c.functional_novelty == "unknown" and c.source_capability is None for c in contributions
    )
    assert all(c.residuals for c in contributions)


def test_remote_receipt_is_not_installation_or_quality():
    cap = capability()
    c = observe_contributions(snapshot(use(cap, transport="a2a")))[0]
    assert c.transport == "a2a" and c.observed_outcome == "completed"
    assert c.local_installation == "unobserved" and c.functional_novelty == "unknown"
    assert "quality" in c.basis


def test_declared_formation_inputs_are_not_runtime_dependencies(records):
    original = capability()
    built = capability("built").model_copy(
        update={
            "schema_version": "3",
            "formation_inputs": (
                FormationInput(
                    issuer=original.issuer,
                    subject=original.subject,
                    binding_digest=original.binding_digest,
                ),
            ),
        }
    )
    view = inspect_lifecycle(snapshot(original, built), target(built))
    assert view.runtime_dependencies == () and view.formation_inputs == (target(original),)
    assert any(
        c.source_capability == target(original) and c.strength == "declared"
        for c in view.contributions
    )


def test_visible_dependency_and_receipt_cycles_are_rejected():
    a, b = capability("a"), capability("b")
    a = a.model_copy(update={"dependencies": (b.subject,), "dependency_issuers": (b.issuer,)})
    b = b.model_copy(update={"dependencies": (a.subject,), "dependency_issuers": (a.issuer,)})
    with pytest.raises(ValueError, match="cyclic"):
        snapshot(a, b)

    def formation(cap, name, child):
        return Event(
            schema_version="2",
            id=name,
            issuer="producer",
            subject=cap.subject,
            action="formation",
            task_id=name,
            attempt_id=name,
            correlation_id="cycle",
            occurred_at=START,
            formation=FormationReceipt(
                receipts=(ReceiptRef(issuer="producer", id=child),),
                scope=SCOPE,
                binding_digest=cap.binding_digest,
                policy_digest=POLICY,
                relationship="declared",
            ),
        )

    with pytest.raises(ValueError, match="cyclic"):
        snapshot(formation(a, "f-a", "f-b"), formation(b, "f-b", "f-a"))


def test_typed_cost_units_status_wall_and_unknown_are_separate():
    cap = capability()
    costs = tuple(
        Cost(category="use", status=status, quantity=amount, unit=unit)
        for unit, status, amount in (
            ("tokens", "measured", Decimal("3")),
            ("tokens", "estimated", Decimal("4")),
            ("USD", "measured", Decimal("1.50")),
            ("wall_seconds", "measured", Decimal("10")),
            ("tokens", "unavailable", None),
        )
    )
    view = inspect_lifecycle(snapshot(cap, use(cap, costs=costs)), target(cap))
    assert {(c.unit, c.status, c.quantity) for c in view.cost_subtotals} == {
        ("tokens", "measured", Decimal("3")),
        ("tokens", "estimated", Decimal("4")),
        ("USD", "measured", Decimal("1.50")),
    }
    assert len(view.costs) == 5
    assert {r.kind for r in view.residuals} >= {
        ResidualKind.UNKNOWN_COST,
        ResidualKind.INCOMPATIBLE_UNIT,
    }


def test_read_only_missing_partial_and_handoff_preserve_residuals(monkeypatch):
    def prohibited(*args, **kwargs):
        raise AssertionError("network must not run")

    monkeypatch.setattr(socket.socket, "connect", prohibited)
    cap = capability()
    view = inspect_lifecycle(snapshot(cap, ctx=context(coverage="partial")), target(cap))
    handoff = build_handoff(
        view,
        source_role=HandoffRole.GENERATE,
        target_role=HandoffRole.VERIFY,
        producer="producer",
        receiver="receiver",
        contract_identity="view.v1",
    )
    assert handoff.residuals == view.residuals and handoff.sources == view.sources
    assert handoff.state == "proposed" and handoff.authority == "not_granted"
    assert handoff.disposition == "review"
    restored = HandoffObservation.model_validate_json(handoff.model_dump_json())
    assert restored.residuals == handoff.residuals
    with pytest.raises(ValidationError):
        HandoffObservation.model_validate_json(
            handoff.model_dump_json().replace(
                '"view_schema_version":"1"', '"view_schema_version":"future"'
            )
        )


def test_handoff_receipt_state_needs_matching_actual_observation():
    cap = capability()
    view = inspect_lifecycle(snapshot(cap), target(cap))
    kwargs = dict(
        source_role=HandoffRole.GENERATE,
        target_role=HandoffRole.VERIFY,
        producer="producer",
        receiver="receiver",
        contract_identity="view.v1",
    )
    with pytest.raises(ValueError, match="basis"):
        build_handoff(view, **kwargs, state="received")
    received = build_handoff(
        view, **kwargs, state="received", state_basis=view.sources[0].reference
    )
    assert received.authority == "not_granted"
    with pytest.raises(ValueError, match="Decision"):
        build_handoff(view, **kwargs, state="assessed", state_basis=view.sources[0].reference)
    with pytest.raises(ValueError, match="actual reuse"):
        build_handoff(
            view,
            source_role=HandoffRole.REUSE,
            target_role=HandoffRole.ACCOUNT,
            producer="producer",
            receiver="receiver",
            contract_identity="view.v1",
        )


def test_material_authorization_tampering_original_hash_and_historical_key(
    identities, principals, records
):
    cap = records[0]
    envelope = identities[cap.issuer].sign(cap)
    observed = snapshot(envelope, signed=True, principals=principals)
    assert observed.records[0].source.reference.payload_digest != projection_digest(
        cap.model_dump(mode="json")
    )
    view = inspect_lifecycle(observed, target(cap))
    assert view.sources[0].payload_basis == "original_dsse_payload"
    assert view.sources[0].reference.payload_digest != view.projection_digest
    damaged = json.loads(json.dumps(envelope))
    damaged["payload"] = damaged["payload"][:-4] + "AAAA"
    with pytest.raises(ValueError):
        snapshot(damaged, signed=True, principals=principals)
    principal = principals[cap.issuer]
    pins = {
        **principals,
        cap.issuer: Principal(
            principal.key,
            principal.trust_group,
            principal.methods,
            compromised_keyids=frozenset({principal.key.keyid}),
        ),
    }
    compromised = inspect_lifecycle(snapshot(envelope, signed=True, principals=pins), target(cap))
    assert compromised.sources[0].current_key_authority == "compromised_key_observed"
    assert any(r.kind == ResidualKind.AUTHORITY_MISSING for r in compromised.residuals)
    with pytest.raises(PermissionError):
        snapshot_from_material({}, owner="receiver", caller="other")


def test_late_record_and_overlimit_material_fail_before_projection():
    cap = capability()
    ctx = context(cutoff=START - timedelta(seconds=1))
    with pytest.raises(ValueError, match="cutoff"):
        snapshot(cap, ctx=ctx)
    with pytest.raises(ValueError, match="bound"):
        snapshot(*([cap] * 257))


@given(st.sets(st.integers(0, 4)), st.sets(st.integers(0, 4)))
def test_independent_endpoint_sets_reconcile_with_fixed_identity_universe(before, after):
    caps = tuple(capability(str(i)) for i in range(5))
    opening = stock(caps, before, cutoff=START + timedelta(seconds=10))
    closing = stock(caps, after, cutoff=START + timedelta(seconds=20))
    growth = observe_growth(opening, closing)
    assert growth.reconciled is True
    assert growth.closing_admitted_entry_count == growth.opening_admitted_entry_count + len(
        growth.entries_added_net
    ) - len(growth.entries_lost_net)
    assert growth.gross_additions is None and growth.re_admissions is None
    assert growth.service_use_count is None and growth.functional_growth == "not_estimated"


@pytest.mark.parametrize("change", ["policy", "universe", "partial"])
def test_incomparable_growth_has_no_exact_delta(change):
    cap = capability()
    opening = stock((cap,), {0}, cutoff=START + timedelta(seconds=10))
    caps = (capability("other"),) if change == "universe" else (cap,)
    closing = stock(
        caps,
        {0},
        cutoff=START + timedelta(seconds=20),
        coverage="partial" if change == "partial" else "complete",
        policy=digest(b"other") if change == "policy" else POLICY,
    )
    growth = observe_growth(opening, closing)
    assert growth.reconciled is None and growth.entries_added_net is None
    assert growth.entries_lost_net is None and growth.residuals


def test_unknown_transition_is_not_confirmed_loss():
    cap = capability()
    opening = stock((cap,), {0}, cutoff=START + timedelta(seconds=10))
    closing = stock((cap,), set(), cutoff=START + timedelta(seconds=20), unknown={0})
    growth = observe_growth(opening, closing)
    assert growth.became_unassessed == (target(cap),) and growth.lost_confirmed_availability == ()
    assert growth.functional_growth == "not_estimated"


def period(opening, closing, *records, coverage="complete"):
    return snapshot(
        *records,
        ctx=context(
            closing.context.cutoff,
            coverage,
            period_start=opening.context.cutoff,
            period_end=closing.context.cutoff,
        ),
    )


def period_decision(base, outcome, seconds, name):
    return Decision.model_validate(
        {
            **base.model_dump(mode="python"),
            "id": name,
            "outcome": outcome,
            "evaluated_at": START + timedelta(seconds=seconds),
        }
    )


def test_gross_loss_and_readmission_are_distinct_from_zero_endpoint_delta():
    cap = capability()
    opening = stock((cap,), {0}, cutoff=START + timedelta(seconds=10))
    closing = stock((cap,), {0}, cutoff=START + timedelta(seconds=20))
    reject = period_decision(closing.entries[0].decision, "REJECT", 14, "lost")
    readmit = period_decision(closing.entries[0].decision, "ACCEPT", 18, "readmit")
    history = period(opening, closing, reject, readmit, closing.entries[0].decision)
    growth = observe_growth(opening, closing, history=history)
    assert growth.entries_added_net == growth.entries_lost_net == ()
    assert (growth.gross_additions, growth.gross_losses, growth.re_admissions) == (1, 1, 1)
    incomplete = observe_growth(
        opening,
        closing,
        history=period(
            opening,
            closing,
            reject,
            coverage="partial",
        ),
    )
    assert incomplete.gross_additions is None and incomplete.re_admissions is None


def test_expiry_and_superseded_expiry_have_owner_clock_semantics():
    cap = capability()
    original = stock((cap,), {0}, cutoff=START + timedelta(seconds=10))
    old = original.entries[0].decision.model_copy(
        update={
            "valid_until": START + timedelta(seconds=15),
        }
    )
    source = snapshot(old, ctx=original.context).records[0].source
    opening = StockObservation.model_validate(
        {
            **original.model_dump(mode="python"),
            "sources": (source,),
            "entries": (
                StockEntry(
                    target=target(cap),
                    availability="accepted",
                    decision=old,
                    reference=source.reference,
                ),
            ),
        }
    )
    closing = stock((cap,), {0}, cutoff=START + timedelta(seconds=20))
    late = period_decision(closing.entries[0].decision, "ACCEPT", 18, "after-expiry")
    expired = observe_growth(opening, closing, history=period(opening, closing, late))
    assert (expired.gross_losses, expired.re_admissions) == (1, 1)
    early = period_decision(closing.entries[0].decision, "ACCEPT", 14, "before-expiry")
    replaced = observe_growth(opening, closing, history=period(opening, closing, early))
    assert (replaced.gross_losses, replaced.re_admissions) == (0, 0)


def test_period_scope_mismatch_cannot_supply_service_or_cost_totals():
    cap = capability()
    opening = stock((cap,), {0}, cutoff=START + timedelta(seconds=10))
    closing = stock((cap,), {0}, cutoff=START + timedelta(seconds=20))
    event = use(cap).model_copy(update={"occurred_at": START + timedelta(seconds=15)})
    matching = period(opening, closing, event)
    observed = observe_growth(opening, closing, history=matching)
    assert observed.service_use_count == 1
    wrong = matching.model_copy(
        update={
            "context": matching.context.model_copy(
                update={"policy_digest": digest(b"other-policy")}
            )
        }
    )
    rejected = observe_growth(opening, closing, history=wrong)
    assert rejected.service_use_count is None and rejected.costs == ()
    assert any(r.kind == ResidualKind.POLICY_MISMATCH for r in rejected.residuals)


def test_stock_rejects_tampered_reference_context_and_old_assessment():
    good = stock((capability(),), {0}, cutoff=START + timedelta(seconds=10))
    for path in ("digest", "policy", "clock"):
        data = good.model_dump(mode="json")
        if path == "digest":
            data["entries"][0]["reference"]["payload_digest"] = "0" * 64
        elif path == "policy":
            data["context"]["policy_digest"] = "0" * 64
        else:
            data["assessment_started_at"] = data["assessment_completed_at"]
        with pytest.raises(ValidationError):
            StockObservation.model_validate(data)


def test_formation_missing_receipts_preserve_unresolved_basis():
    cap, built = capability(), capability("built")
    completed = use(cap)
    formed = Event(
        schema_version="2",
        id="formed",
        issuer=built.issuer,
        subject=built.subject,
        action="formation",
        task_id="formed",
        attempt_id="formed",
        correlation_id="formed",
        occurred_at=START,
        formation=FormationReceipt(
            receipts=(
                ReceiptRef(issuer="receiver", id=completed.id),
                ReceiptRef(issuer="receiver", id="missing"),
            ),
            scope=SCOPE,
            binding_digest=built.binding_digest,
            policy_digest=POLICY,
            relationship="observed-use",
        ),
    )
    view = inspect_lifecycle(snapshot(built, completed, formed), target(built))
    contribution = next(c for c in view.contributions if c.unavailable_receipt_links)
    assert contribution.strength == "unresolved" and len(contribution.receipt_links) == 1
    assert any(r.kind == ResidualKind.MISSING_HISTORY for r in view.residuals)
    assert all(c.functional_novelty == "unknown" for c in view.contributions)


def test_visible_evidence_support_cycles_and_missing_support(records):
    cap, evidence = records
    a = evidence.model_copy(update={"id": "a", "evidence_dependencies": ("b",)})
    b = evidence.model_copy(update={"id": "b", "evidence_dependencies": ("a",)})
    with pytest.raises(ValueError, match="cyclic"):
        snapshot(a, b)
    view = inspect_lifecycle(snapshot(cap, a), target(cap))
    assert view.evidence_support == (("verifier", "b"),)
    assert any(r.kind == ResidualKind.MISSING_EVIDENCE for r in view.residuals)


def test_cli_mode_errors_and_partial_page_exit(monkeypatch, capsys):
    import sys

    from collective_intelligence_overlay import cli, lifecycle_cli

    monkeypatch.setattr(
        sys, "argv", ["collective-intelligence-overlay", "lifecycle", "growth", "--fixture"]
    )
    assert cli.main() == 2
    assert "ValueError" in capsys.readouterr().err
    monkeypatch.setattr(
        lifecycle_cli, "run", lambda args: {"context": {"decision_cursor": {"after": 1}}}
    )
    monkeypatch.setattr(
        sys, "argv", ["collective-intelligence-overlay", "lifecycle", "inspect", "--fixture"]
    )
    assert cli.main() == 3


def test_owner_dispatch_observation_is_neither_reuse_nor_consumption():
    from collective_intelligence_overlay.models import InvocationObservation

    cap = capability()
    retained = Event(
        schema_version="6",
        id="dispatch",
        issuer="receiver",
        subject=cap.subject,
        action="recommendation",
        task_id="work",
        attempt_id="work",
        correlation_id="work",
        occurred_at=START,
        invocation_observation=InvocationObservation(
            caller="receiver",
            invocation_id="held-original",
            resource_owner="receiver",
            binding_id="sum",
            binding_digest=cap.binding_digest,
            request_fingerprint=digest(b"req"),
            arguments_digest=digest(b"input"),
            scope=SCOPE,
            lease_id="lease",
            worker="worker",
            fence=1,
            phase="dispatched",
            origin="execution_transaction",
            accepted_receipt=ReceiptRef(issuer="receiver", id="accepted"),
        ),
    )
    view = inspect_lifecycle(snapshot(cap, retained), target(cap))
    assert view.owner_observations[0]["observation"]["phase"] == "dispatched"
    assert view.costs == view.cost_subtotals == ()
    assert all(ContributionRelation.REUSE not in c.relations for c in view.contributions)
    assert {r.kind for r in view.residuals} >= {
        ResidualKind.UNKNOWN_COST,
        ResidualKind.UNRESOLVED_EFFECT,
    }


def test_residual_identity_is_stable_within_coordinates_and_distinct_across_receivers():
    cap = capability()
    material = snapshot(cap)
    first = inspect_lifecycle(material, target(cap))
    repeated = inspect_lifecycle(material, target(cap))
    assert [r.id for r in first.residuals] == [r.id for r in repeated.residuals]
    changed = material.model_copy(
        update={"context": material.context.model_copy(update={"receiver": "other"})}
    )
    foreign = inspect_lifecycle(changed, target(cap))
    assert not {r.id for r in first.residuals} & {r.id for r in foreign.residuals}


def test_same_clock_unsequenced_decisions_do_not_invent_gross_order():
    cap = capability()
    opening = stock((cap,), {0}, cutoff=START + timedelta(seconds=10))
    closing = stock((cap,), {0}, cutoff=START + timedelta(seconds=20))
    base = closing.entries[0].decision
    history = period(
        opening,
        closing,
        period_decision(base, "REJECT", 15, "same-clock-reject"),
        period_decision(base, "ACCEPT", 15, "same-clock-accept"),
    )
    history = history.model_copy(
        update={
            "records": tuple(
                item.model_copy(
                    update={"source": item.source.model_copy(update={"sequence": None})}
                )
                for item in history.records
            )
        }
    )
    growth = observe_growth(opening, closing, history=history)
    assert growth.reconciled is True and growth.entries_added_net == ()
    assert growth.gross_additions is None and growth.gross_losses is None
    assert any(r.kind == ResidualKind.MISSING_HISTORY for r in growth.residuals)
