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


async def compare_network(
    call: Callable[..., Awaitable[dict[str, Any]]], candidate: dict[str, Any]
) -> list[dict[str, Any]]:
    """Same three running peers, checker, inputs and fixed work budget in every arm."""
    from .models import uid

    rows = []
    for mode in ("single-agent", "multi-agent-no-persistence", "shared-memory", "overlay"):
        started = time.perf_counter_ns()
        memory: dict[str, dict[str, Any]] = {}
        correct = 0
        for source in EVALUATION_INPUTS:
            if mode == "overlay":
                request = {
                    "receiver": "receiver",
                    "subject": candidate["subject"],
                    "scope": candidate["scope"],
                    "semantic_fit": "confirmed",
                }
                output = await call(
                    "receiver",
                    operation="work",
                    mode="reuse",
                    attempt=uid(),
                    request=request,
                    source=source,
                )
                cap = candidate
            elif mode == "shared-memory" and source in memory:
                output = memory[source]
                cap = output["capability"]
            else:
                output = await call(
                    "producer",
                    operation="work",
                    attempt=uid(),
                    source=source,
                    mode="scratch_checked" if mode == "single-agent" else "scratch",
                )
                cap = output["capability"]
                memory[source] = output
            if mode == "single-agent":
                valid = output.get("quality_checked") is True
            else:
                checked = await call(
                    "verifier",
                    operation="work",
                    mode="verify",
                    attempt=uid(),
                    capability=cap,
                    source=source,
                    result=output["result"],
                    receiver="receiver",
                )
                valid = checked["evidence"]["verdict"] == "PASS"
            correct += int(valid)
        rows.append(
            {
                "mode": mode,
                "tasks": len(EVALUATION_INPUTS),
                "correct": correct,
                "elapsed_seconds": (time.perf_counter_ns() - started) / 1e9,
                "currency_cost": None,
                "cost_scope": "network, execution, checking and overlay overhead",
            }
        )
    return rows
