import asyncio
import base64
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

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
