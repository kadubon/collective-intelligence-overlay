"""Typed accounting: unavailable, estimated and measured quantities stay distinct."""

import asyncio
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Context, Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select

from .models import Capability, Event, Evidence, UseRequest, now
from .overlay import Overlay
from .queries import RecordCursor, RecordQuery
from .storage import Conflict, Store, projection_digest, records, subject_key


def metrics(events: list[Event]) -> dict[str, Any]:
    unique: dict[tuple[str, str], Event] = {}
    for event in events:
        key = (event.issuer, event.id)
        if key in unique and unique[key] != event:
            raise Conflict("event content conflict")
        unique[key] = event
    totals: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    arithmetic = Context(prec=max(28, 25 + len(str(max(1, len(unique) * 64)))))
    missing: Counter[tuple[str, str]] = Counter()
    elapsed_observations: list[dict[str, Any]] = []
    for event in unique.values():
        for cost in event.costs:
            if cost.unit in {"wall_seconds", "seconds"}:
                elapsed_observations.append(
                    {
                        "issuer": event.issuer,
                        "event": event.id,
                        "category": cost.category,
                        "unit": cost.unit,
                        "quantity": str(cost.quantity) if cost.quantity is not None else None,
                        "status": cost.status,
                        "parent_invocation": event.execution.parent_invocation
                        if event.execution
                        else None,
                    }
                )
                if cost.quantity is None:
                    missing[cost.category, cost.unit] += 1
                continue  # inclusive parent/child or remote wall time is not an additive resource
            if cost.quantity is None:
                missing[cost.category, cost.unit] += 1
            else:
                cost_key = (cost.category, cost.unit, cost.status)
                totals[cost_key] = arithmetic.add(totals[cost_key], cost.quantity)
    return {
        "events": len(unique),
        "elapsed_observations": elapsed_observations,
        "actions": dict(Counter(e.action for e in unique.values())),
        "outcomes": dict(Counter(str(e.outcome) for e in unique.values() if e.outcome)),
        "costs": [
            {"category": c, "unit": u, "status": s, "quantity": str(q)}
            for (c, u, s), q in sorted(totals.items())
        ],
        "unavailable": [
            {"category": c, "unit": u, "count": n} for (c, u), n in sorted(missing.items())
        ],
    }


def metrics_page(
    store: Store,
    query: RecordQuery | None = None,
    *,
    cursor: RecordCursor | None = None,
    limit: int = 128,
    byte_limit: int = 196608,
) -> dict[str, Any]:
    """Page-local history metrics; never label a partial page as a global total.

    Scope/policy filters exclude legacy events without these observations. A
    completion cursor closes the fixed prefix, not a claim about future events.
    """
    query = query or RecordQuery(kinds=("event",))
    if query.kinds != ("event",):
        raise ValueError("event metrics require exactly the event kind")
    page = store.record_page(query, cursor=cursor, limit=limit, byte_limit=byte_limit)
    events = [event for event in page.items if isinstance(event, Event)]
    owners = sorted({event.issuer for event in events})
    timeline = Counter((event.occurred_at.date().isoformat(), event.action) for event in events)
    return {
        **metrics(events),
        "costs": metrics([event for event in events if event.issuer == store.owner])["costs"],
        "unavailable": metrics([event for event in events if event.issuer == store.owner])[
            "unavailable"
        ],
        "cost_owner": store.owner,
        "aggregation": "this_page_only",
        "receiver": store.owner,
        "query": query.model_dump(mode="json"),
        "snapshot": page.snapshot.model_dump(mode="json"),
        "complete": page.next_cursor is None,
        "next_cursor": page.next_cursor.model_dump(mode="json") if page.next_cursor else None,
        "attribution": [
            {"issuer": owner, **metrics([event for event in events if event.issuer == owner])}
            for owner in owners
        ],
        "timeline": [
            {"date": date, "action": action, "count": count}
            for (date, action), count in sorted(timeline.items())
        ],
        "execution_states": dict(
            Counter(event.execution.state for event in events if event.execution)
        ),
        "execution_purposes": dict(
            Counter(event.execution.purpose for event in events if event.execution)
        ),
        "transport_observations": dict(
            Counter(event.execution.transport for event in events if event.execution)
        ),
        "scope_unobserved": sum(event.schema_version == "1" for event in events),
        "lineage": [
            {
                "issuer": event.issuer,
                "event": event.id,
                "subject": event.subject.model_dump(mode="json"),
                "formation": event.formation.model_dump(mode="json"),
                "verification_status": "signature verified; references not checked by this page",
            }
            for event in events
            if event.formation
        ],
    }


async def capability_metrics(overlay: Overlay, requests: tuple[UseRequest, ...]) -> dict[str, Any]:
    """Evaluate an explicit bounded target set, never invent applicability from schemas.

    Historical independent PASS and current admission are different observations.
    Each current decision has its own evaluation time; this is not a historical
    replay or a globally atomic assessment. No execution authority is granted.
    """
    if not 1 <= len(requests) <= 32:
        raise ValueError("capability metrics require 1 to 32 explicit use requests")
    if any(request.receiver != overlay.store.owner for request in requests):
        raise ValueError("capability metrics belong to the local receiver")
    keys = [projection_digest(request.model_dump(mode="json")) for request in requests]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate metric target")
    started = now()
    policy = overlay.policy.digest
    items = []
    async with asyncio.timeout(60):
        for request in requests:
            decision = await overlay.qualify(request)
            snapshot = await asyncio.to_thread(
                overlay.store.admission_snapshot, request, overlay.max_graph_nodes
            )
            caps = [
                cap
                for cap in snapshot.capabilities
                if cap.subject == request.subject
                and (request.capability_issuer is None or cap.issuer == request.capability_issuer)
            ]
            detail: dict[str, Any] = {
                "request": request.model_dump(mode="json"),
                "decision": decision.model_dump(mode="json"),
                "historical_independent_pass": None,
                "unresolved_obligations": [],
                "first_verification_seconds": None,
                "first_reuse_seconds": None,
                "capability_identity": None,
            }
            if len(caps) == 1:
                cap = caps[0]
                applicable = [
                    e
                    for e in snapshot.evidence
                    if e.subject == cap.subject
                    and e.scope == request.scope
                    and e.claim == cap.claim
                    and e.binding_digest == request.binding_digest
                    and request.receiver in e.receivers
                ]
                passed = [
                    e
                    for e in applicable
                    if e.verdict == "PASS"
                    and e.method in overlay.store.principals[e.issuer].methods
                    and e.issuer != cap.issuer
                    and overlay.store.principals[e.issuer].trust_group
                    != overlay.store.principals[cap.issuer].trust_group
                ]
                withdrawn = {
                    (r.issuer, r.evidence_id) for r in snapshot.revocations if r.evidence_id
                }
                obligations = [
                    {"issuer": cap.issuer, "record": cap.subject.key, "obligation": item}
                    for item in cap.obligations
                ]
                obligations.extend(
                    {"issuer": e.issuer, "record": e.id, "obligation": item}
                    for e in applicable
                    if e.created_at <= started < e.expires_at and (e.issuer, e.id) not in withdrawn
                    for item in e.obligations
                )
                detail.update(
                    {
                        "historical_independent_pass": bool(passed),
                        "capability_identity": projection_digest(
                            [cap.issuer, cap.subject.model_dump(mode="json"), cap.binding_digest]
                        ),
                        "classification": cap.classification,
                        "functional_novelty": "unknown",
                        "unresolved_obligations": obligations,
                        **await asyncio.to_thread(
                            _first_observations, overlay.store, cap, passed, request
                        ),
                    }
                )
            if snapshot.revisions != decision.revisions or policy != overlay.policy.digest:
                # Never combine a previous ACCEPT with a later history snapshot as a current total.
                detail["consistent"] = False
            else:
                detail["consistent"] = (
                    await asyncio.to_thread(overlay.store.revisions, set(snapshot.revisions))
                    == snapshot.revisions
                )
            items.append(detail)
    return {
        "receiver": overlay.store.owner,
        "policy_digest": policy,
        "started_at": started.isoformat(),
        "completed_at": now().isoformat(),
        "evaluation": "per_target_current_decisions; not an atomic historical replay",
        "latency_basis": "first locally received record minus local candidate receipt",
        "targets": items,
        "historically_checked_targets": sum(
            item["historical_independent_pass"] is True for item in items
        ),
        "historically_checked_capabilities": len(
            {
                item["capability_identity"]
                for item in items
                if item["historical_independent_pass"] is True and item["capability_identity"]
            }
        ),
        "currently_accepted_capabilities": len(
            {
                item["capability_identity"]
                for item in items
                if item["consistent"]
                and item["decision"]["outcome"] == "ACCEPT"
                and item["capability_identity"]
            }
        ),
        "currently_accepted_targets": sum(
            item["consistent"] and item["decision"]["outcome"] == "ACCEPT" for item in items
        ),
        "verification_backlog": sum(
            "independent_evidence_required" in item["decision"]["reasons"] for item in items
        ),
        "unresolved_obligations": sum(len(item["unresolved_obligations"]) for item in items),
        "inconsistent_targets": sum(not item["consistent"] for item in items),
    }


def _first_observations(
    store: Store, cap: Capability, passed: list[Evidence], request: UseRequest
) -> dict[str, float | None]:
    with store.engine.connect() as conn:
        created: datetime = conn.execute(
            select(records.c.received_at).where(
                (records.c.kind == "capability")
                & (records.c.issuer == cap.issuer)
                & (records.c.subject_key == subject_key(cap.subject))
            )
        ).scalar_one()
        checked: datetime | None = None
        if passed:
            checked = conn.execute(
                select(func.min(records.c.received_at)).where(
                    (records.c.kind == "evidence")
                    & or_(
                        *[
                            and_(records.c.issuer == e.issuer, records.c.record_id == e.id)
                            for e in passed
                        ]
                    )
                )
            ).scalar_one()
        # v1 use does not identify a binding or actual outcome. Do not fill the gap.
        reused: datetime | None = conn.execute(
            select(func.min(records.c.received_at)).where(
                (records.c.kind == "event")
                & (records.c.issuer == store.owner)
                & (records.c.subject_key == subject_key(cap.subject))
                & (
                    records.c.scope_digest
                    == projection_digest(request.scope.model_dump(mode="json"))
                )
                & (records.c.body["execution"]["state"].as_string() == "completed")
                & or_(
                    records.c.body["execution"]["purpose"].as_string() == "reuse",
                    records.c.body["execution"]["purpose"].as_string().is_(None),
                )
                & (
                    records.c.body["execution"]["binding_digest"].as_string()
                    == request.binding_digest
                )
                & (records.c.body["execution"]["capability_issuer"].as_string() == cap.issuer)
            )
        ).scalar_one()
    return {
        "first_verification_seconds": (checked - created).total_seconds()
        if checked and checked >= created
        else None,
        "first_reuse_seconds": (reused - created).total_seconds()
        if reused and reused >= created
        else None,
    }


def work_metrics_page(
    store: Store,
    query: RecordQuery,
    *,
    cursor: RecordCursor | None = None,
    limit: int = 128,
    byte_limit: int = 196608,
) -> dict[str, Any]:
    """Bounded opportunity-cohort report with current durable execution observations.

    The signed opportunity prefix is stable. Mutable invocation state is observed
    in a separate repeatable-read transaction, not reconstructed at the cohort date.
    Missing attempts, proposals or checking evidence are never inferred from success.
    """
    from .invocations import invocations
    from .models import Opportunity
    from .steps import Selection, selections
    from .storage import leases

    if (
        query.kinds != ("opportunity",)
        or query.issuer != store.owner
        or query.scope is None
        or query.policy_digest is None
        or query.since is None
        or query.until is None
    ):
        raise ValueError("work metrics require local opportunity, scope, policy and period filters")
    page = store.record_page(query, cursor=cursor, limit=limit, byte_limit=byte_limit)
    opportunities = [item for item in page.items if isinstance(item, Opportunity)]
    ids = [item.id for item in opportunities]
    items = []
    totals: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    arithmetic = Context(prec=40)
    with store.engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin():
            observed_at = now()
            choices = (
                {
                    row["opportunity_id"]: row
                    for row in conn.execute(
                        select(selections).where(
                            (selections.c.owner == store.owner)
                            & selections.c.opportunity_id.in_(ids)
                        )
                    ).mappings()
                }
                if ids
                else {}
            )
            parsed = {key: Selection.model_validate(row["body"]) for key, row in choices.items()}
            executions = (
                {
                    row["id"]: row
                    for row in conn.execute(
                        select(invocations, leases.c.unit, leases.c.reservation)
                        .select_from(
                            invocations.join(leases, invocations.c.lease_id == leases.c.task_id)
                        )
                        .where(
                            (invocations.c.owner == store.owner)
                            & (invocations.c.caller == store.owner)
                            & invocations.c.id.in_(
                                [choice.invocation_id for choice in parsed.values()]
                            )
                        )
                    ).mappings()
                }
                if parsed
                else {}
            )
            for opportunity in opportunities:
                choice = parsed.get(opportunity.id)
                execution = executions.get(choice.invocation_id) if choice else None
                if choice and (
                    choice.owner != store.owner
                    or choice.opportunity.id != opportunity.id
                    or choice.opportunity.issuer != store.owner
                ):
                    raise ValueError("selection does not match local opportunity")
                state = (
                    execution["state"] if execution else "not_invoked" if choice else "unselected"
                )
                if execution:
                    key = (opportunity.work_kind, execution["unit"], execution["reservation_state"])
                    totals[key] = arithmetic.add(totals[key], execution["reservation"])
                items.append(
                    {
                        "opportunity": opportunity.id,
                        "goal": opportunity.goal_id,
                        "goal_digest": opportunity.goal_digest,
                        "work_kind": opportunity.work_kind,
                        "created_at": opportunity.created_at.isoformat(),
                        "age_seconds": max(
                            0, (observed_at - opportunity.created_at).total_seconds()
                        ),
                        "opportunity_expired": opportunity.expires_at <= observed_at,
                        "selection": choice.model_dump(mode="json") if choice else None,
                        "selected_at": choices[opportunity.id]["created_at"].isoformat()
                        if choice
                        else None,
                        "alternatives_at_selection": 1 + len(choice.skipped) if choice else None,
                        "execution_state": state,
                        "execution_reason": execution["reason"] if execution else None,
                        "invocation_id": choice.invocation_id if choice else None,
                        "reservation_state": execution["reservation_state"] if execution else None,
                        "unknown_since_last_update_seconds": max(
                            0, (observed_at - execution["updated_at"]).total_seconds()
                        )
                        if execution and state == "unknown"
                        else None,
                        "checked_outcome": None,
                    }
                )
    return {
        "receiver": store.owner,
        "query": query.model_dump(mode="json"),
        "aggregation": "this_page_only",
        "cohort": "opportunity_creation_period",
        "snapshot": page.snapshot.model_dump(mode="json"),
        "execution_observed_at": observed_at.isoformat(),
        "complete": page.next_cursor is None,
        "next_cursor": page.next_cursor.model_dump(mode="json") if page.next_cursor else None,
        "unique_opportunities": len(items),
        "selected": sum(item["selection"] is not None for item in items),
        "execution_states": dict(Counter(item["execution_state"] for item in items)),
        "work_kinds": dict(Counter(item["work_kind"] for item in items)),
        "allowance_observations": [
            {"work_kind": kind, "unit": unit, "reservation_state": state, "quantity": str(amount)}
            for (kind, unit, state), amount in sorted(totals.items())
        ],
        "allowance_basis": "contractual reservation amounts; not measured resource consumption",
        "unavailable": [
            "discovery_attempts",
            "deduplicated_attempts",
            "all_proposals",
            "deferred_attempts",
            "independently_checked_work_outcomes",
        ],
        "items": items,
    }
