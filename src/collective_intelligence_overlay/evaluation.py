"""Matched deterministic microbenchmark, not an intelligence or savings estimator."""

import time
from collections.abc import Awaitable, Callable
from typing import Any

from .models import UseRequest
from .overlay import Overlay
from .reference import csv_sum, verify_csv

EVALUATION_INPUTS = (
    "category,amount\na,10.31\nb,-2.17\nc,0.09\n",
    "category,amount\nx,1001.01\ny,0.99\n",
    "category,amount\nempty,0\n",
)


async def compare(overlay: Overlay, request: UseRequest) -> dict[str, Any]:
    """Same installed function, inputs, checker and one process budget for every arm.

    Multiple agents here means separate deterministic roles, not independent organizations.
    Single and memory baselines may cache results; unique held-out inputs prevent leakage.
    Formation/transfer are supplied separately by the caller's setup ledger.
    """
    rows = []
    for mode in ("single-agent", "multi-agent-no-persistence", "shared-memory", "overlay"):
        started = time.perf_counter_ns()
        cache: dict[str, dict[str, Any]] = {}
        correct = 0
        failed = 0
        for source in EVALUATION_INPUTS:

            async def operation(
                source: str = source, mode: str = mode, cache: dict[str, dict[str, Any]] = cache
            ) -> dict[str, Any]:
                if mode in {"single-agent", "shared-memory"} and source in cache:
                    return cache[source]
                result = csv_sum(source)
                cache[source] = result
                return result

            run: Callable[[], Awaitable[dict[str, Any]]] = operation
            try:
                result = await overlay.execute(request, run) if mode == "overlay" else await run()
                correct += int(verify_csv(source, result))
            except (ValueError, RuntimeError):
                failed += 1
        rows.append(
            {
                "mode": mode,
                "tasks": len(EVALUATION_INPUTS),
                "correct": correct,
                "failed": failed,
                "elapsed_seconds": (time.perf_counter_ns() - started) / 1e9,
                "cost_scope": "execution, checking, failures and overlay overhead",
                "currency_cost": None,
            }
        )
    return {
        "comparison": rows,
        "formation_transfer_maintenance": "see setup event ledger",
        "resource_condition": "same installed code, checker, held-out inputs; concurrency=1",
        "interpretation": "mechanism overhead; no savings or intelligence-growth inference",
    }
