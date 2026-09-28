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
    for event in unique.values():
        for cost in event.costs:
            if cost.quantity is None:
                missing[cost.category, cost.unit] += 1
            else:
                totals[cost.category, cost.unit, cost.status] += cost.quantity
    return {
        "events": len(unique),
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
