"""Typed accounting: unavailable, estimated and measured quantities stay distinct."""

from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any

from .models import Event
from .storage import Conflict


def metrics(events: list[Event]) -> dict[str, Any]:
    unique: dict[tuple[str, str], Event] = {}
    for event in events:
        key = (event.issuer, event.id)
        if key in unique and unique[key] != event:
            raise Conflict("event content conflict")
        unique[key] = event
    totals: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    missing: Counter[tuple[str, str]] = Counter()
    elapsed_observations: list[dict[str, Any]] = []
    for event in unique.values():
        for cost in event.costs:
            if cost.unit == "wall_seconds":
                elapsed_observations.append(
                    {
                        "issuer": event.issuer,
                        "event": event.id,
                        "category": cost.category,
                        "quantity": str(cost.quantity) if cost.quantity is not None else None,
                        "status": cost.status,
                        "parent_invocation": event.execution.parent_invocation
                        if event.execution
                        else None,
                    }
                )
                continue  # inclusive parent/child or remote wall time is not an additive resource
            if cost.quantity is None:
                missing[cost.category, cost.unit] += 1
            else:
                totals[cost.category, cost.unit, cost.status] += cost.quantity
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
