"""Deterministic reference applications; never imported by the generic core."""

import csv
import html
import inspect
import io
import json
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any

from .models import Capability, Evidence, Scope, Subject, Verdict, now
from .security import digest


def csv_sum(source: str) -> dict[str, Any]:
    if len(source.encode()) > 32768:
        raise ValueError("CSV too large")
    reader = csv.DictReader(io.StringIO(source))
    if reader.fieldnames != ["category", "amount"]:
        raise ValueError("expected category,amount columns")
    total = Decimal(0)
    count = 0
    for row in reader:
        value = Decimal(row["amount"])
        if not value.is_finite() or abs(value) > Decimal("1e12"):
            raise ValueError("amount outside reference domain")
        total += value
        count += 1
        if count > 5000:
            raise ValueError("too many rows")
    return {"rows": count, "total": str(total)}


def render_report(summary: dict[str, Any]) -> str:
    return f"<p>Rows: {int(summary['rows'])}; total: {html.escape(str(summary['total']))}</p>"


def verify_csv(source: str, result: dict[str, Any]) -> bool:
    """Separate checker using column extraction and sum, not csv_sum()."""
    rows = list(csv.reader(io.StringIO(source)))
    if not rows or rows[0] != ["category", "amount"] or len(rows) > 5001:
        return False
    if any(len(r) != 2 for r in rows[1:]):
        return False
    values = [Decimal(row[1]) for row in rows[1:]]
    if any(not v.is_finite() or abs(v) > Decimal("1e12") for v in values):
        return False
    return result.get("rows") == len(values) and Decimal(str(result.get("total"))) == sum(values)


def capability(owner: str, name: str, dependencies: tuple[Subject, ...] = ()) -> Capability:
    operations: dict[str, Callable[..., Any]] = {
        "csv-sum": csv_sum,
        "render-report": render_report,
        "csv-report": compose_report,
    }
    if name not in operations:
        raise ValueError("unregistered reference operation")
    contract = "csv.category-amount.v1" if name != "render-report" else "summary.v1"
    output = "summary.v1" if name == "csv-sum" else "html-report.v1"
    artifact = inspect.getsource(operations[name]).encode()
    return Capability(
        subject=Subject(id=f"{owner}/{name}", version="1", digest=digest(artifact)),
        issuer=owner,
        scope=Scope(
            task=name,
            input_contract=contract,
            output_contract=output,
            environment={"reference": "1"},
        ),
        entrypoint=name,
        claim="reference-contract",
        dependencies=dependencies,
        license="Apache-2.0",
        provenance="operator-installed collective-intelligence-overlay reference application",
        classification="declared-new",
        expires_at=now() + timedelta(hours=1),
    )


def check(owner: str, cap: Capability, source: str, result: Any, receiver: str) -> Evidence:
    valid = False
    if cap.entrypoint == "csv-sum":
        valid = verify_csv(source, result)
    elif cap.entrypoint == "render-report":
        summary = json.loads(source)
        valid = (
            result
            == f"<p>Rows: {int(summary['rows'])}; total: {html.escape(str(summary['total']))}</p>"
        )
    elif cap.entrypoint == "csv-report":
        # Parse the composite output independently and verify against the source CSV.
        import re

        match = re.fullmatch(r"<p>Rows: (\d+); total: ([0-9.\-]+)</p>", result)
        valid = bool(match and verify_csv(source, {"rows": int(match[1]), "total": match[2]}))
    return Evidence(
        issuer=owner,
        subject=cap.subject,
        claim=cap.claim,
        scope=cap.scope,
        receivers=(receiver,),
        verdict=Verdict.PASS if valid else Verdict.FAIL,
        method="reference-check",
        verifier_version="1",
        artifact_digest=digest(json.dumps(result).encode()),
        declared_origin={"checker": "deterministic reference; shared software authorship"},
        expires_at=now() + timedelta(hours=1),
    )


async def compose_report(source: str) -> str:
    """Composition uses Microsoft Agent Framework's existing workflow executor."""
    from agent_framework import WorkflowBuilder, WorkflowContext, executor

    @executor(id="sum")
    async def aggregate(data: str, ctx: WorkflowContext[dict[str, Any]]) -> None:
        await ctx.send_message(csv_sum(data))

    @executor(id="render")
    async def render(data: dict[str, Any], ctx: WorkflowContext[str, str]) -> None:
        await ctx.yield_output(render_report(data))

    workflow = (
        WorkflowBuilder(start_executor=aggregate, max_iterations=3)
        .add_edge(aggregate, render)
        .build()
    )
    result = await workflow.run(source)
    outputs = result.get_outputs()
    if len(outputs) != 1 or not isinstance(outputs[0], str):
        raise ValueError("composition produced no unique output")
    return outputs[0]
