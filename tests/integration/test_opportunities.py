import asyncio
import base64
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from collective_intelligence_overlay.allocation import AllocationPolicy, allocate
from collective_intelligence_overlay.bindings import (
    Binding,
    ExecutionContext,
    Registry,
    Target,
    callable_digest,
)
from collective_intelligence_overlay.invocations import Executor, Reservation
from collective_intelligence_overlay.models import (
    BindingRef,
    Capability,
    Event,
    Proposal,
    RecordRef,
    Revocation,
    Subject,
    UseRequest,
    now,
)
from collective_intelligence_overlay.opportunities import (
    Goal,
    Opportunities,
    ProposalDraft,
    ProposalDrafts,
    propose,
)
from collective_intelligence_overlay.queries import RecordQuery
from collective_intelligence_overlay.security import digest
from collective_intelligence_overlay.steps import Steps
from collective_intelligence_overlay.storage import Conflict
from collective_intelligence_overlay.storage import records as record_table


async def installed_builder(arguments):
    return {"value": arguments["value"]}


def setup(overlay, identities, records):
    cap = records[0]
    subject = Subject(id="new-transform", version="1", digest=callable_digest(installed_builder))
    binding = Binding(
        id="installed",
        revision="1",
        issuer="receiver",
        subject=subject,
        registrar="receiver",
        target=Target(
            kind="local",
            name="installed",
            interface_digest=callable_digest(installed_builder),
            implementation_identity="installed",
        ),
        scope=cap.scope,
        input_schema={
            "type": "object",
            "required": ["value"],
            "additionalProperties": False,
            "properties": {"value": {"type": "integer"}},
        },
        output_schema={"type": "object"},
        callers=("receiver",),
        effects="read-only",
    )
    registry = Registry(overlay)
    registry.register_local(binding, installed_builder, lambda args: True)
    ref = BindingRef(issuer=binding.issuer, id=binding.id, digest=binding.digest)
    request = UseRequest(
        receiver="receiver",
        capability_issuer="receiver",
        subject=subject,
        scope=cap.scope,
        binding_digest=binding.digest,
        semantic_fit="confirmed",
    )
    goal = Goal(
        id="transformation",
        revision="1",
        request=request,
        checker=ref,
        builders=(ref,),
        peers=("producer", "other"),
    )
    return Opportunities(registry, identities["receiver"], (goal,)), goal, binding


async def test_real_deficit_stable_ids_concurrency_and_evidence_change(
    overlay, identities, records
):
    opportunities, goal, binding = setup(overlay, identities, records)
    first = await opportunities.discover()
    assert first.discovered == 1
    initial = first.opportunities[0]
    assert initial.work_kind == "formation"
    assert overlay.store.resolve_reference(initial.basis[0]).outcome != "ACCEPT"
    event = Event(
        issuer="receiver",
        subject=goal.request.subject,
        action="admission",
        task_id="unrelated",
        attempt_id="unrelated",
        correlation_id="unrelated",
    )
    overlay.store.put(identities["receiver"].sign(event))
    repeated = await asyncio.gather(*(opportunities.discover() for _ in range(3)))
    assert all(r.deduplicated == 1 and r.opportunities[0] == initial for r in repeated)
    assert len(overlay.store.record_page(RecordQuery(kinds=("opportunity",))).items) == 1
    candidate = Capability.model_validate(
        {
            **records[0].model_dump(),
            "schema_version": "2",
            "issuer": "receiver",
            "subject": goal.request.subject,
            "binding_digest": binding.digest,
        }
    )
    overlay.store.put(identities["receiver"].sign(candidate))
    next_step = await opportunities.discover()
    assert next_step.discovered == 1
    assert next_step.opportunities[0].work_kind == "verification"
    assert next_step.opportunities[0].id != initial.id
    withdrawal = Revocation(issuer="receiver", subject=candidate.subject, reason="withdrawn")
    overlay.store.put(identities["receiver"].sign(withdrawal))
    repair = await opportunities.discover()
    assert repair.opportunities[0].work_kind == "repair"


async def test_parallel_first_discovery_retains_one_signed_observation(
    overlay, identities, records
):
    opportunities, _, _ = setup(overlay, identities, records)
    results = await asyncio.gather(*(opportunities.discover() for _ in range(4)))
    assert sum(r.discovered for r in results) == 1
    assert sum(r.deduplicated for r in results) == 3
    assert all(r.opportunities == results[0].opportunities for r in results)


async def test_host_candidate_transition_preserves_contract_and_invalidates_old_proposals(
    overlay, identities, records
):
    host, goal, binding = setup(overlay, identities, records)
    initial = (await host.discover()).opportunities[0]
    reference = overlay.store.reference("opportunity", "receiver", initial.id)
    proposal = propose(
        initial,
        reference,
        identities["producer"],
        ProposalDrafts(
            alternatives=(
                ProposalDraft(
                    builder=goal.builders[0], arguments={"value": 3}, alternative="first"
                ),
            )
        ),
    )[0]
    context = ExecutionContext(caller="receiver", environment=binding.scope.environment)
    host.validate_proposal(identities["producer"].sign(proposal), "producer", context)
    changed = binding.model_copy(
        update={
            "id": "formed",
            "revision": "2",
            "subject": binding.subject.model_copy(
                update={"version": "2", "digest": digest(b"formed")}
            ),
        }
    )
    host.registry.register_local(changed, installed_builder, lambda args: True)
    candidate = Capability.model_validate(
        {
            **records[0].model_dump(),
            "schema_version": "2",
            "issuer": "receiver",
            "subject": changed.subject,
            "binding_digest": changed.digest,
        }
    )
    overlay.store.put(identities["receiver"].sign(candidate))
    candidate_ref = overlay.store.reference("capability", "receiver", candidate.subject.key)
    with pytest.raises(ValueError, match="contract"):
        host.select_target(goal.id, goal.digest, binding.id, candidate_ref)
    with pytest.raises(ValueError, match="capability reference"):
        host.select_target(goal.id, goal.digest, changed.id, reference)
    for label, changes in (
        ("other-family", {"subject": changed.subject.model_copy(update={"id": "other-family"})}),
        ("other-scope", {"scope": changed.scope.model_copy(update={"permissions": ("extra",)})}),
        ("other-issuer", {"issuer": "producer"}),
    ):
        outside = changed.model_copy(update={"id": label, **changes})
        # Distinct versions retain rejected observations without overwriting any candidate.
        outside = outside.model_copy(
            update={"subject": outside.subject.model_copy(update={"version": "3"})}
        )
        host.registry.register_local(outside, installed_builder, lambda args: True)
        outside_cap = candidate.model_copy(
            update={
                "issuer": outside.issuer,
                "subject": outside.subject,
                "scope": outside.scope,
                "binding_digest": outside.digest,
            }
        )
        overlay.store.put(identities[outside.issuer].sign(outside_cap))
        outside_ref = overlay.store.reference("capability", outside.issuer, outside.subject.key)
        with pytest.raises(ValueError, match="contract"):
            host.select_target(goal.id, goal.digest, outside.id, outside_ref)
        assert host.goal(goal.id) == goal
    updated = host.select_target(goal.id, goal.digest, changed.id, candidate_ref)
    assert updated.request.subject == candidate.subject
    assert updated.request.binding_digest == changed.digest
    assert updated.digest != goal.digest
    assert updated.model_dump(exclude={"request", "revision"}) == goal.model_dump(
        exclude={"request", "revision"}
    )
    assert updated.request.model_dump(exclude={"subject", "binding_digest"}) == (
        goal.request.model_dump(exclude={"subject", "binding_digest"})
    )
    assert host.select_target(goal.id, updated.digest, changed.id, candidate_ref) == updated
    with pytest.raises(Conflict, match="goal changed"):
        host.select_target(goal.id, goal.digest, changed.id, candidate_ref)
    with pytest.raises(ValueError, match="registered goal"):
        host.validate_proposal(identities["producer"].sign(proposal), "producer", context)
    discovered = await host.discover()
    assert discovered.satisfied == 0
    assert discovered.opportunities[0].work_kind == "verification"
    assert discovered.opportunities[0].id != initial.id
    # The application persists its returned configuration; restoring it does not
    # turn candidate registration into verification or duplicate discovery.
    restored = Opportunities(
        host.registry,
        identities["receiver"],
        (Goal.model_validate_json(updated.model_dump_json()),),
    )
    again = await restored.discover()
    assert again.deduplicated == 1 and again.opportunities == discovered.opportunities


async def test_proposal_validates_real_reference_goal_and_installed_authority(
    overlay, identities, records
):
    opportunities, goal, binding = setup(overlay, identities, records)
    opportunity = (await opportunities.discover()).opportunities[0]
    with overlay.store.engine.connect() as conn:
        envelope = conn.execute(
            select(record_table.c.envelope).where(
                (record_table.c.kind == "opportunity")
                & (record_table.c.record_id == opportunity.id)
            )
        ).scalar_one()
    ref = RecordRef(
        kind="opportunity",
        issuer="receiver",
        id=opportunity.id,
        payload_digest=digest(base64.b64decode(envelope["payload"])),
    )
    proposal = Proposal(
        id="alternative-a",
        issuer="producer",
        subject=opportunity.subject,
        scope=opportunity.scope,
        receivers=("receiver",),
        goal_id=goal.id,
        goal_digest=goal.digest,
        opportunity=ref,
        builder=goal.builders[0],
        arguments={"value": 3},
        alternative="first",
        expires_at=opportunity.expires_at,
    )
    context = ExecutionContext(caller="receiver", environment=binding.scope.environment)
    assert (
        opportunities.validate_proposal(identities["producer"].sign(proposal), "producer", context)
        == proposal
    )
    # Alternative peers remain separate observations, not votes or verified outcomes.
    other = proposal.model_copy(
        update={"issuer": "other", "id": "alternative-b", "alternative": "second"}
    )
    assert (
        opportunities.validate_proposal(identities["other"].sign(other), "other", context) == other
    )
    for change in (
        {"goal_digest": digest(b"different")},
        {"opportunity": ref.model_copy(update={"payload_digest": digest(b"fiction")})},
        {"builder": goal.builders[0].model_copy(update={"digest": digest(b"other")})},
        {"expires_at": opportunity.expires_at + timedelta(seconds=1)},
        {"expires_at": now() - timedelta(seconds=1)},
    ):
        bad = proposal.model_copy(update=change)
        with pytest.raises(ValueError):
            opportunities.validate_proposal(identities["producer"].sign(bad), "producer", context)
    with pytest.raises(ValueError):
        opportunities.validate_proposal(identities["producer"].sign(proposal), "other", context)
    with pytest.raises(ValueError):
        opportunities.validate_proposal(
            identities["producer"].sign(proposal),
            "producer",
            context.model_copy(update={"permissions": frozenset(), "caller": "other"}),
        )
    # A genuine changed observation invalidates previously proposed work even
    # while its declared deadline has not expired.
    withdrawal = Revocation(issuer="receiver", subject=goal.request.subject, reason="withdrawn")
    overlay.store.put(identities["receiver"].sign(withdrawal))
    with pytest.raises(ValueError, match="observation changed"):
        opportunities.validate_proposal(identities["producer"].sign(proposal), "producer", context)


async def test_bounded_goal_paging_and_host_configuration_isolation(overlay, identities, records):
    opportunities, goal, _ = setup(overlay, identities, records)
    second = goal.model_copy(update={"id": "second", "revision": "2"}, deep=True)
    bounded = Opportunities(opportunities.registry, identities["receiver"], (goal, second))
    first = await bounded.discover(max_candidates=1)
    assert first.next_goal == 1 and len(first.opportunities) == 1
    last = await bounded.discover(max_candidates=1, start=first.next_goal)
    assert last.next_goal is None and last.opportunities[0].goal_id == "second"
    assert first.opportunities[0].id != last.opportunities[0].id
    returned = bounded.goal(goal.id)
    returned.request.scope.environment["untrusted"] = "injected"
    assert bounded.goal(goal.id).digest == goal.digest
    with pytest.raises(ValueError, match="bound"):
        await bounded.discover(max_candidates=33)
    with pytest.raises(ValueError, match="bound"):
        await bounded.discover(start=2)


async def test_deterministic_proposer_preserves_alternatives_and_replay(
    overlay, identities, records
):
    opportunities, goal, binding = setup(overlay, identities, records)
    opportunity = (await opportunities.discover()).opportunities[0]
    reference = overlay.store.reference("opportunity", "receiver", opportunity.id)
    drafts = ProposalDrafts(
        alternatives=(
            ProposalDraft(builder=goal.builders[0], arguments={"value": 3}, alternative="three"),
            ProposalDraft(builder=goal.builders[0], arguments={"value": 5}, alternative="five"),
        )
    )
    proposed = propose(opportunity, reference, identities["producer"], drafts)
    assert proposed == propose(opportunity, reference, identities["producer"], drafts)
    assert proposed[0].id != proposed[1].id
    context = ExecutionContext(caller="receiver", environment=binding.scope.environment)
    for item in proposed:
        assert (
            opportunities.validate_proposal(identities["producer"].sign(item), "producer", context)
            == item
        )
    with pytest.raises(ValueError, match="duplicate"):
        propose(
            opportunity,
            reference,
            identities["producer"],
            ProposalDrafts(alternatives=(drafts.alternatives[0],) * 2),
        )
    with pytest.raises(ValueError, match="not shared"):
        propose(opportunity, reference, identities["verifier"], drafts)


async def configured_steps(overlay, identities, records, amount=4):
    original, goal, binding = setup(overlay, identities, records)
    target = goal.request.subject.model_copy(update={"id": "missing-output"})
    goal = goal.model_copy(update={"request": goal.request.model_copy(update={"subject": target})})
    opportunities = Opportunities(original.registry, identities["receiver"], (goal,))
    candidate = Capability.model_validate(
        {
            **records[0].model_dump(),
            "schema_version": "2",
            "issuer": "receiver",
            "subject": binding.subject,
            "binding_digest": binding.digest,
        }
    )
    evidence = records[1].model_copy(
        update={
            "schema_version": "2",
            "subject": binding.subject,
            "binding_digest": binding.digest,
            "id": "builder-check",
        }
    )
    for record in (candidate, evidence):
        overlay.store.put(identities[record.issuer].sign(record))
    overlay.store.set_budget("work", Decimal(amount))
    opportunity = (await opportunities.discover()).opportunities[0]
    ref = overlay.store.reference("opportunity", "receiver", opportunity.id)
    proposals = propose(
        opportunity,
        ref,
        identities["producer"],
        ProposalDrafts(
            alternatives=(
                ProposalDraft(
                    builder=goal.builders[0], arguments={"value": 3}, alternative="three"
                ),
                ProposalDraft(builder=goal.builders[0], arguments={"value": 5}, alternative="five"),
            )
        ),
    )
    envelopes = tuple((p.issuer, identities[p.issuer].sign(p)) for p in proposals)
    executor = Executor(opportunities.registry, identities["receiver"], Reservation())
    context = ExecutionContext(caller="receiver", environment=binding.scope.environment)
    return Steps(opportunities, executor, context), opportunity, envelopes


@pytest.mark.parametrize("bad_first", [False, True])
async def test_cio_030_02_signed_unapproved_alternative_does_not_veto_valid_work(
    overlay, identities, records, bad_first
):
    steps, opportunity, valid = await configured_steps(overlay, identities, records)
    original = steps.opportunities.validate_proposal(valid[0][1], "producer", steps.context)
    bad = original.model_copy(
        update={
            "id": "signed-unapproved-builder",
            "builder": original.builder.model_copy(update={"id": "not-registered"}),
        }
    )
    rejected = ("producer", identities["producer"].sign(bad))
    batch = (rejected, valid[0]) if bad_first else (valid[0], rejected)
    result = await steps.step(opportunity.id, batch)
    assert result.invocation is not None and result.invocation["state"] == "completed"
    assert result.invocation["result"] == {"value": 3}
    assert result.selection.proposal.id == original.id
    assert [(r.category, r.count) for r in result.rejections] == [("authorization", 1)]
    assert not overlay.store.record_page(RecordQuery(kinds=("proposal",), record_id=bad.id)).items


@pytest.mark.parametrize(
    "category", ["authentication", "expired", "scope", "reference", "arguments"]
)
@pytest.mark.parametrize("bad_first", [False, True])
async def test_cio_030_02_expected_rejections_are_isolated_and_observed(
    overlay, identities, records, category, bad_first
):
    steps, opportunity, valid = await configured_steps(overlay, identities, records)
    original = steps.opportunities.validate_proposal(valid[0][1], "producer", steps.context)
    changes = {
        "expired": {
            "created_at": now() - timedelta(hours=2),
            "expires_at": now() - timedelta(hours=1),
        },
        "scope": {"scope": original.scope.model_copy(update={"task": "another-task"})},
        "reference": {
            "opportunity": original.opportunity.model_copy(update={"payload_digest": "f" * 64})
        },
        "arguments": {"arguments": {"value": "invalid"}},
    }
    bad = original.model_copy(update={"id": "bad-alternative", **changes.get(category, {})})
    envelope = identities["producer"].sign(bad)
    if category == "authentication":
        envelope["signatures"][0]["sig"] = base64.b64encode(b"x" * 64).decode()
    rejected = ("producer", envelope)
    result = await steps.step(
        opportunity.id, (rejected, valid[0]) if bad_first else (valid[0], rejected)
    )
    assert result.invocation["state"] == "completed" and result.invocation["result"] == {"value": 3}
    assert [(r.category, r.count) for r in result.rejections] == [(category, 1)]
    assert not overlay.store.record_page(RecordQuery(kinds=("proposal",), record_id=bad.id)).items
    observations = [
        e.work
        for e in overlay.store.record_page(
            RecordQuery(kinds=("event",), issuer="receiver", task_id=opportunity.id)
        ).items
        if isinstance(e, Event) and e.work is not None
    ]
    assert any(work.result == "rejected_" + category for work in observations)
    assert sum(work.proposals_received or 0 for work in observations) == 2
    assert "invalid" not in " ".join(work.model_dump_json() for work in observations)


async def test_cio_030_02_all_bad_unavailable_and_budget_are_distinct(overlay, identities, records):
    from collective_intelligence_overlay.proposal_exchange import CollectedProposals

    steps, opportunity, valid = await configured_steps(overlay, identities, records, amount=0)
    rejected = ("producer", {"secret": "must-not-be-recorded"})
    result = await steps.step(opportunity.id, (rejected,))
    assert result.reason == "no_valid_alternatives" and result.invocation is None
    assert result.rejections[0].category == "format"
    stopped = await steps.step(
        opportunity.id, CollectedProposals(replies=(), unavailable=("producer", "other"))
    )
    assert stopped.reason == "peers_unavailable" and not stopped.rejections
    budget = await steps.step(opportunity.id, valid)
    assert budget.reason == "insufficient_allowance" and budget.selection is None


@pytest.mark.parametrize("reverse", [False, True])
async def test_cio_030_02_ambiguous_id_batch_has_no_arrival_order_winner(
    overlay, identities, records, reverse
):
    steps, opportunity, valid = await configured_steps(overlay, identities, records)
    original = steps.opportunities.validate_proposal(valid[0][1], "producer", steps.context)
    changed = original.model_copy(update={"arguments": {"value": 99}})
    collision = (("producer", identities["producer"].sign(changed)), valid[0])
    result = await steps.step(opportunity.id, tuple(reversed(collision)) if reverse else collision)
    assert result.reason == "no_valid_alternatives" and result.rejections[0].category == "conflict"
    assert result.rejections[0].count == 2
    assert not overlay.store.record_page(RecordQuery(kinds=("proposal",))).items
    assert steps._choice(opportunity.id) is None


async def test_cio_030_02_stored_id_conflict_does_not_mask_database_failure(
    overlay, identities, records, monkeypatch
):
    steps, opportunity, valid = await configured_steps(overlay, identities, records)
    overlay.store.put(valid[0][1])
    original = steps.opportunities.validate_proposal(valid[0][1], "producer", steps.context)
    changed = original.model_copy(update={"arguments": {"value": 99}})
    result = await steps.step(opportunity.id, (("producer", identities["producer"].sign(changed)),))
    assert result.reason == "no_valid_alternatives" and result.rejections[0].category == "conflict"

    def internal_failure(*args, **kwargs):
        raise ValueError("installed assessment or database invariant failed")

    monkeypatch.setattr(steps.opportunities.registry, "prepare", internal_failure)
    with pytest.raises(ValueError, match="database invariant"):
        await steps.step(opportunity.id, valid)
    assert steps._choice(opportunity.id) is None


async def test_cio_030_02_database_unavailability_and_cancellation_propagate(
    overlay, identities, records, monkeypatch
):
    from sqlalchemy import create_engine
    from sqlalchemy.exc import DBAPIError

    from collective_intelligence_overlay.demo import free_port

    steps, opportunity, valid = await configured_steps(overlay, identities, records)
    # A genuine failed PostgreSQL connection, rather than a peer rejection double.
    unavailable = create_engine(
        overlay.store.engine.url.set(port=free_port()), connect_args={"timeout": 1}
    )
    with monkeypatch.context() as patch:
        patch.setattr(overlay.store, "engine", unavailable)
        try:
            with pytest.raises(DBAPIError):
                await steps.step(opportunity.id, valid)
        finally:
            unavailable.dispose()

    def cancelled(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(steps.opportunities, "validate_proposal", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await steps.step(opportunity.id, valid)
    assert steps._choice(opportunity.id) is None


async def test_cio_030_02_run_reaches_valid_work_and_preserves_internal_timeout(
    overlay, identities, records, monkeypatch
):
    steps, opportunity, valid = await configured_steps(overlay, identities, records)

    async def mixed(observation):
        assert observation.id == opportunity.id
        return (("producer", {}), valid[0])

    result = await steps.run(mixed, max_steps=2, seconds=30)
    assert result.steps[0].invocation["state"] == "completed"
    assert result.steps[0].invocation["result"] == {"value": 3}
    assert result.steps[0].rejections[0].category == "format"

    async def internal_timeout(*args, **kwargs):
        raise TimeoutError("internal service failed")

    monkeypatch.setattr(steps.opportunities, "discover", internal_timeout)
    with pytest.raises(TimeoutError, match="internal service"):
        await steps.run(mixed, max_steps=1, seconds=30)


async def test_cio_030_03_discovery_does_not_offer_expired_observation(
    overlay, identities, records, monkeypatch
):
    from collective_intelligence_overlay import opportunities as module

    host, goal, _ = setup(overlay, identities, records)
    observed_at = now()
    monkeypatch.setattr(module, "now", lambda: observed_at)
    first = (await host.discover()).opportunities[0]
    observed_at += timedelta(seconds=goal.lifetime_seconds + 1)
    later = await host.discover()
    assert first.expires_at <= observed_at
    assert not later.opportunities
    assert later.expired == (first,)
    # Discovery alone must not mint a fresh execution attempt on every call.
    assert overlay.store.record_page(RecordQuery(kinds=("opportunity",))).items == (first,)


async def test_cio_030_03_expired_instance_rejects_propose_validation_and_selection(
    overlay, identities, records, monkeypatch
):
    from collective_intelligence_overlay import opportunities as observation_module
    from collective_intelligence_overlay import steps as selection_module

    steps, opportunity, valid = await configured_steps(overlay, identities, records)
    expired_clock = opportunity.expires_at + timedelta(seconds=1)
    monkeypatch.setattr(observation_module, "now", lambda: expired_clock)
    monkeypatch.setattr(selection_module, "now", lambda: expired_clock)
    with pytest.raises(ValueError, match="proposal expired"):
        steps.opportunities.validate_proposal(valid[0][1], "producer", steps.context)
    reference = overlay.store.reference("opportunity", "receiver", opportunity.id)
    goal = steps.opportunities.goal(opportunity.goal_id)
    with pytest.raises(ValueError, match="has expired"):
        propose(
            opportunity,
            reference,
            identities["producer"],
            ProposalDrafts(
                alternatives=(
                    ProposalDraft(
                        builder=goal.builders[0], arguments={"value": 3}, alternative="late"
                    ),
                )
            ),
        )
    result = await steps.step(opportunity.id, valid)
    assert result.reason == "expired_or_changed_goal" and result.selection is None
    assert steps._choice(opportunity.id) is None
    assert not overlay.store.record_page(RecordQuery(kinds=("proposal",))).items


async def test_step_concurrency_replay_and_one_allowance(overlay, identities, records):
    steps, opportunity, envelopes = await configured_steps(overlay, identities, records)
    results = await asyncio.gather(
        steps.step(opportunity.id, envelopes),
        steps.step(opportunity.id, tuple(reversed(envelopes))),
    )
    assert results[0].selection == results[1].selection
    restarted = Steps(steps.opportunities, steps.executor, steps.context)
    replay = await restarted.step(opportunity.id)
    assert replay.reason == "existing_invocation"
    assert replay.invocation["state"] == "completed"
    assert replay.invocation["result"]["value"] in (3, 5)
    from collective_intelligence_overlay.storage import budgets

    with overlay.store.engine.connect() as conn:
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == Decimal(3)
    assert len(overlay.store.record_page(RecordQuery(kinds=("proposal",))).items) == 2


async def test_step_insufficient_allowance_does_not_choose_or_dispatch(
    overlay, identities, records
):
    steps, opportunity, envelopes = await configured_steps(overlay, identities, records, amount=0)
    result = await steps.step(opportunity.id, envelopes)
    assert result.reason == "insufficient_allowance" and result.selection is None
    assert steps._choice(opportunity.id) is None


async def test_restart_after_choice_uses_original_alternative(
    overlay, identities, records, monkeypatch
):
    steps, opportunity, envelopes = await configured_steps(overlay, identities, records)
    original = steps.executor.invoke

    async def interrupted(*args, **kwargs):
        raise RuntimeError("process stopped before invocation claim")

    monkeypatch.setattr(steps.executor, "invoke", interrupted)
    with pytest.raises(RuntimeError):
        await steps.step(opportunity.id, envelopes)
    chosen = steps._choice(opportunity.id)
    assert chosen is not None
    monkeypatch.setattr(steps.executor, "invoke", original)
    restarted = Steps(steps.opportunities, steps.executor, steps.context)
    result = await restarted.step(opportunity.id, tuple(reversed(envelopes)))
    assert result.selection == chosen and result.invocation["state"] == "completed"


async def test_step_unknown_is_not_reexecuted(overlay, identities, records, monkeypatch):
    steps, opportunity, envelopes = await configured_steps(overlay, identities, records)
    original = steps.executor.registry.execute
    calls = []

    async def lost_response(*args, **kwargs):
        output = await original(*args, **kwargs)
        calls.append(output)
        raise RuntimeError("response lost after the actual installed operation")

    monkeypatch.setattr(steps.executor.registry, "execute", lost_response)
    result = await steps.step(opportunity.id, envelopes)
    assert result.invocation["state"] == "unknown"
    assert result.invocation["reservation_state"] == "held"
    restarted = Steps(steps.opportunities, steps.executor, steps.context)
    again = await restarted.step(opportunity.id)
    assert again.invocation == result.invocation and len(calls) == 1


async def test_finite_loop_stops_without_reproposing_completed_work(overlay, identities, records):
    steps, opportunity, envelopes = await configured_steps(overlay, identities, records)
    calls = []

    async def alternatives(observation):
        calls.append(observation.id)
        return envelopes

    result = await steps.run(alternatives, max_steps=8)
    assert result.reason == "no_progress" and result.rounds == 2
    assert len(result.steps) == 1 and result.steps[0].invocation["state"] == "completed"
    assert calls == [opportunity.id]
    resumed = await Steps(steps.opportunities, steps.executor, steps.context).run(alternatives)
    assert resumed.reason == "no_progress"
    assert resumed.steps[0].reason == "existing_invocation"
    assert calls == [opportunity.id]


async def test_finite_loop_deadline_and_allowance_stop(overlay, identities, records):
    steps, _, envelopes = await configured_steps(overlay, identities, records, amount=0)

    async def alternatives(observation):
        return envelopes

    result = await steps.run(alternatives)
    assert result.reason == "insufficient_allowance" and result.rounds == 1

    async def unavailable(observation):
        await asyncio.sleep(30)
        return envelopes

    expired = await steps.run(unavailable, seconds=1)
    assert expired.reason == "deadline" and not expired.steps
    with pytest.raises(ValueError, match="bounds"):
        await steps.run(alternatives, max_steps=0)


async def test_allocation_reacts_to_backlog_but_does_not_trust_unqualified_checker(
    overlay, identities, records
):
    steps, _, _ = await configured_steps(overlay, identities, records)
    formation = steps.opportunities.goal("transformation")
    binding = steps.executor.registry.inspect("installed")
    verification_target = binding.subject.model_copy(update={"id": "unchecked-candidate"})
    checking = formation.model_copy(
        update={
            "id": "check-goal",
            "checker_arguments": {"value": 3},
            "request": formation.request.model_copy(update={"subject": verification_target}),
        }
    )
    candidate = Capability.model_validate(
        {
            **records[0].model_dump(),
            "schema_version": "2",
            "issuer": "receiver",
            "subject": verification_target,
            "binding_digest": binding.digest,
        }
    )
    overlay.store.put(identities["receiver"].sign(candidate))
    host = Opportunities(steps.executor.registry, identities["receiver"], (formation, checking))
    page = await host.discover()
    assert [o.work_kind for o in page.opportunities] == ["formation", "verification"]
    static = await allocate(
        host, steps.context, page.opportunities, AllocationPolicy(mode="static")
    )
    assert static.ordered[0] == page.opportunities[0].id
    adaptive = await allocate(
        host,
        steps.context,
        page.opportunities,
        AllocationPolicy(verification_threshold=1, unverified_limit=1),
    )
    assert adaptive.ordered == (page.opportunities[1].id,)
    assert adaptive.qualified_checkers == (checking.checker,)
    assert adaptive.deferred[page.opportunities[0].id] == "unverified_queue_limit"
    assert adaptive.sample_count == 2 and adaptive.checker_decisions
    requested = []

    async def alternatives(observation):
        requested.append(observation.work_kind)
        ref = overlay.store.reference("opportunity", "receiver", observation.id)
        generated = propose(
            observation,
            ref,
            identities["producer"],
            ProposalDrafts(
                alternatives=(
                    ProposalDraft(
                        builder=checking.builders[0], arguments={"value": 3}, alternative="bounded"
                    ),
                )
            ),
        )
        return tuple((p.issuer, identities[p.issuer].sign(p)) for p in generated)

    worker = Steps(host, steps.executor, steps.context)
    # Page size one still accounts for the verification backlog on the next page.
    run = await worker.run(
        alternatives,
        max_steps=1,
        max_candidates=1,
        allocation_policy=AllocationPolicy(verification_threshold=1, unverified_limit=1),
    )
    assert requested == ["verification"] and run.allocations[0].sample_count == 2
    assert run.steps[0].selection.allocation == run.allocations[0]
    requested.clear()
    retained = await worker.run(
        alternatives,
        max_steps=1,
        max_candidates=1,
        allocation_policy=AllocationPolicy(verification_threshold=2, reserve_operations=4),
    )
    assert requested == ["formation"]
    assert retained.steps[0].reason == "allowance_or_capacity_deferred"
    assert retained.steps[0].invocation is None
    # A checker withdrawal is not overridden by the existence of a backlog.
    withdrawal = Revocation(issuer="receiver", subject=binding.subject, reason="checker withdrawn")
    overlay.store.put(identities["receiver"].sign(withdrawal))
    unavailable = await allocate(
        host,
        steps.context,
        page.opportunities,
        AllocationPolicy(verification_threshold=1, unverified_limit=1),
    )
    assert not unavailable.qualified_checkers and not unavailable.ordered
    assert unavailable.deferred[page.opportunities[1].id] == "checker_unavailable"

    from collective_intelligence_overlay.accounting import metrics_page
    from collective_intelligence_overlay.queries import RecordQuery

    query = RecordQuery(
        kinds=("event",),
        issuer="receiver",
        scope=formation.request.scope,
        policy_digest=overlay.policy.digest,
    )
    report = metrics_page(overlay.store, query)
    allocations = [item for item in report["work_observations"] if item["stage"] == "allocation"]
    assert len(allocations) == 10  # five bounded batches, two observed opportunities each
    assert any(
        item["result"] == "deferred"
        and item["reasons"] == ["checker_unavailable"]
        and item["work_kind"] == "verification"
        for item in allocations
    )
    assert any(
        item["result"] == "deferred"
        and item["reasons"] == ["unverified_queue_limit"]
        and item["work_kind"] == "formation"
        for item in allocations
    )
    assert all(item["rank"] is None for item in allocations if item["result"] == "deferred")
    cost_ids = {item["shared_cost_event"] for item in allocations}
    assert len(cost_ids) == 5 and None not in cost_ids
    for identifier in cost_ids:
        batch_cost = overlay.store.record_page(
            RecordQuery(kinds=("event",), issuer="receiver", record_id=identifier)
        ).items[0]
        assert batch_cost.work is None and len(batch_cost.costs) == 2
    # Scoped per-opportunity observations do not duplicate the shared batch cost.
    for item in overlay.store.record_page(query).items:
        if item.work and item.work.stage == "allocation":
            assert item.costs == ()


async def test_cooldown_uses_persisted_choice_and_does_not_renew_forever(
    overlay, identities, records
):
    steps, _, _ = await configured_steps(overlay, identities, records)
    base = steps.opportunities.goal("transformation")
    binding = steps.executor.registry.inspect("installed")
    connection = base.model_copy(
        update={
            "id": "connect",
            "request": base.request.model_copy(
                update={
                    "subject": binding.subject,
                    "scope": base.request.scope.model_copy(
                        update={"environment": {"reference": "2"}}
                    ),
                }
            ),
        }
    )
    checks = []
    for index in range(2):
        subject = binding.subject.model_copy(update={"id": f"unchecked-{index}"})
        overlay.store.put(
            identities["receiver"].sign(
                Capability.model_validate(
                    {
                        **records[0].model_dump(),
                        "schema_version": "2",
                        "issuer": "receiver",
                        "subject": subject,
                        "binding_digest": binding.digest,
                    }
                )
            )
        )
        checks.append(
            base.model_copy(
                update={
                    "id": f"check-{index}",
                    "checker_arguments": {"value": 3},
                    "request": base.request.model_copy(update={"subject": subject}),
                }
            )
        )
    policy = AllocationPolicy(connection_threshold=1, verification_threshold=2, cooldown_seconds=60)
    host = Opportunities(steps.executor.registry, identities["receiver"], (connection, checks[0]))
    worker = Steps(host, steps.executor, steps.context)

    async def alternatives(observation):
        ref = overlay.store.reference("opportunity", "receiver", observation.id)
        generated = propose(
            observation,
            ref,
            identities["producer"],
            ProposalDrafts(
                alternatives=(
                    ProposalDraft(
                        builder=base.builders[0], arguments={"value": 3}, alternative="calibrated"
                    ),
                )
            ),
        )
        return tuple((p.issuer, identities[p.issuer].sign(p)) for p in generated)

    first = await worker.run(alternatives, max_steps=1, allocation_policy=policy)
    assert first.allocations[0].preferred_kind == "connection"
    restarted = Steps(host, steps.executor, steps.context)
    previous = restarted.last_allocation()
    assert previous == first.allocations[0]
    expanded = Opportunities(steps.executor.registry, identities["receiver"], (connection, *checks))
    page = await expanded.discover()
    held = await allocate(expanded, steps.context, page.opportunities, policy, previous)
    assert held.preferred_kind == "connection" and held.priority_since == previous.priority_since
    assert "retain_qualified_priority_during_cooldown" in held.reasons
    expired = previous.model_copy(update={"priority_since": now() - timedelta(seconds=61)})
    changed = await allocate(expanded, steps.context, page.opportunities, policy, expired)
    assert changed.preferred_kind == "verification"
    overlay.store.put(
        identities["receiver"].sign(
            Revocation(
                issuer="receiver", subject=binding.subject, reason="withdrawn during cooldown"
            )
        )
    )
    changed_page = await expanded.discover()
    urgent = await allocate(expanded, steps.context, changed_page.opportunities, policy, previous)
    assert urgent.preferred_kind == "repair"
    assert not urgent.qualified_checkers


@pytest.mark.parametrize("lose_response", [False, True])
async def test_work_metrics_page_tracks_durable_selection_without_inventing_pass(
    overlay, identities, records, monkeypatch, lose_response, tmp_path, capsys
):
    from collective_intelligence_overlay.accounting import work_metrics_page
    from collective_intelligence_overlay.queries import RecordCursor, RecordQuery

    steps, opportunity, envelopes = await configured_steps(overlay, identities, records)
    query = RecordQuery(
        kinds=("opportunity",),
        issuer="receiver",
        scope=opportunity.scope,
        policy_digest=opportunity.policy_digest,
        since=opportunity.created_at - timedelta(seconds=1),
        until=now() + timedelta(hours=1),
    )
    before = work_metrics_page(overlay.store, query, limit=1)
    assert before["unique_opportunities"] == 1 and before["selected"] == 0
    assert before["execution_states"] == {"unselected": 1}
    assert before["items"][0]["checked_outcome"] is None
    original = steps.executor.registry.execute

    async def lost_response(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError("actual operation completed but reply lost")

    if lose_response:
        monkeypatch.setattr(steps.executor.registry, "execute", lost_response)
    executed = await steps.step(opportunity.id, envelopes)
    expected = "unknown" if lose_response else "completed"
    assert executed.invocation["state"] == expected
    # A later record cannot enter the report's original committed prefix.
    later = opportunity.model_copy(update={"id": "later-work-observation"})
    overlay.store.put(identities["receiver"].sign(later))
    after = work_metrics_page(
        overlay.store,
        query,
        cursor=RecordCursor.model_validate(before["snapshot"]).model_copy(update={"after": 0}),
        limit=1,
    )
    assert after["unique_opportunities"] == after["selected"] == 1
    assert after["execution_states"] == {expected: 1}
    detail = after["items"][0]
    assert detail["alternatives_at_selection"] == len(envelopes)
    assert detail["checked_outcome"] is None
    assert detail["execution_receipt"]["issuer"] == "receiver"
    resource = detail["resource_observation"]
    assert resource["execution"]["state"] == expected
    assert resource["resources"]["elapsed_observations"]
    assert resource["resources"]["costs"] == []  # inclusive wall time is not additive
    assert resource["resources"]["unavailable"][0]["unit"] == "USD"
    assert after["resource_observations"][0]["work_kind"] == opportunity.work_kind
    assert (
        detail["selection"]["estimates"] == executed.selection.model_dump(mode="json")["estimates"]
    )
    assert (detail["unknown_since_last_update_seconds"] is not None) == lose_response
    assert after["allowance_observations"] == [
        {
            "work_kind": opportunity.work_kind,
            "unit": "work",
            "reservation_state": "held" if lose_response else "consumed",
            "quantity": "1.000000000",
        }
    ]
    assert "independently_checked_work_outcomes" in after["unavailable"]
    for invalid in (
        query.model_copy(update={"issuer": "producer"}),
        query.model_copy(update={"scope": None}),
        query.model_copy(update={"since": None}),
    ):
        with pytest.raises(ValueError, match="filters"):
            work_metrics_page(overlay.store, invalid)

    import json
    from types import SimpleNamespace

    from collective_intelligence_overlay import cli

    query_path = tmp_path / "work-query.json"
    query_path.write_text(query.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda _: SimpleNamespace(runtime=lambda: (identities["receiver"], overlay)),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "collective-intelligence-overlay",
            "metrics",
            "--config",
            "unused.json",
            "--work",
            "--query-file",
            str(query_path),
            "--page-size",
            "1",
        ],
    )
    assert cli.main() == 3  # The later cohort member requires another bounded page.
    output = json.loads(capsys.readouterr().out)
    assert output["unique_opportunities"] == 1 and output["next_cursor"] is not None
    assert output["execution_states"] == {expected: 1}


async def test_scoped_attempt_events_retain_discovery_deduplication_and_deferral(
    overlay, identities, records
):
    from collective_intelligence_overlay.accounting import metrics_page
    from collective_intelligence_overlay.queries import RecordQuery

    steps, opportunity, envelopes = await configured_steps(overlay, identities, records)
    repeated = await steps.opportunities.discover()
    assert repeated.deduplicated == 1 and repeated.discovered == 0
    deferred = await steps.step(opportunity.id, ())
    assert deferred.reason == "no_valid_alternatives"
    executed = await steps.step(opportunity.id, envelopes)
    assert executed.invocation["state"] == "completed"
    query = RecordQuery(
        kinds=("event",),
        issuer="receiver",
        scope=opportunity.scope,
        policy_digest=overlay.policy.digest,
    )
    report = metrics_page(overlay.store, query)
    counts = {(row["stage"], row["result"]): row["count"] for row in report["work_attempt_counts"]}
    assert counts == {
        ("discovery", "discovered"): 1,
        ("discovery", "deduplicated"): 1,
        ("selection", "no_valid_alternatives"): 1,
        ("selection", "selected"): 1,
    }
    assert report["proposal_deliveries_at_selection"] == len(envelopes)
    assert len(report["work_observations"]) == 4
    assert report["scope_unobserved"] == 0
    before = report["work_attempt_counts"]
    await steps.step(opportunity.id, envelopes)  # Exact invocation replay makes no new choice.
    assert metrics_page(overlay.store, query)["work_attempt_counts"] == before

    from types import SimpleNamespace

    from collective_intelligence_overlay.peer import PeerService
    from collective_intelligence_overlay.security import verify
    from collective_intelligence_overlay.synchronization import Feed, FeedFilter

    shared = Feed(overlay.store, identities["receiver"]).page("producer", FeedFilter())
    assert all(verify(item, overlay.store.principals).kind != "event" for item in shared.records)
    local_events = overlay.store.record_page(query).items
    work_event = next(item for item in local_events if item.work)
    with pytest.raises(ValueError, match="local owner"):
        await PeerService.handle(
            SimpleNamespace(overlay=overlay),
            "receiver",
            {"operation": "submit", "envelope": identities["receiver"].sign(work_event)},
        )


async def test_allocation_observation_and_shared_cost_commit_atomically(
    overlay, identities, records, monkeypatch
):
    steps, opportunity, _ = await configured_steps(overlay, identities, records)
    store = overlay.store
    before = store.record_count()
    original = store._insert

    def interrupted(conn, record, envelope):
        if getattr(record, "work", None) and record.work.stage == "allocation":
            raise RuntimeError("observation write interrupted after shared cost insert")
        return original(conn, record, envelope)

    with monkeypatch.context() as patch:
        patch.setattr(store, "_insert", interrupted)
        with pytest.raises(RuntimeError, match="write interrupted"):
            await allocate(
                steps.opportunities, steps.context, (opportunity,), AllocationPolicy(mode="static")
            )
    assert store.record_count() == before
    result = await allocate(
        steps.opportunities, steps.context, (opportunity,), AllocationPolicy(mode="static")
    )
    assert result.ordered == (opportunity.id,)
    assert store.record_count() == before + 2
