"""Register the installed CSV/report functions using the public binding API.

This creates new v2 candidates; it does not upgrade or re-sign old evidence.
The host must publish the candidates and obtain independent checks before reuse.
"""

from typing import Any

from collective_intelligence_overlay.bindings import (
    Assessment,
    Binding,
    ExecutionContext,
    Operation,
    Registry,
    Target,
    callable_digest,
    fingerprint,
)
from collective_intelligence_overlay.models import Capability, Scope, Subject
from collective_intelligence_overlay.reference import capability, csv_sum, render_report


async def aggregate(arguments: dict[str, Any]) -> dict[str, Any]:
    return csv_sum(arguments["source"])


async def render(arguments: dict[str, Any]) -> str:
    return render_report(arguments["summary"])


def csv_scope(arguments: dict[str, Any]) -> bool:
    # Explicit application assessment: these capabilities are for the documented
    # CSV domain, not arbitrary tables merely having a compatible string schema.
    source = arguments.get("source")
    return isinstance(source, str) and source.splitlines()[:1] == ["category,amount"]


def register_reference(
    registry: Registry,
    checker: str,
    *,
    callers: tuple[str, ...] | None = None,
    owner_probes: bool = False,
) -> tuple[tuple[Binding, Capability], ...]:
    from agent_framework import WorkflowBuilder, WorkflowContext, executor

    owner = registry.overlay.store.owner
    allowed = callers or tuple(dict.fromkeys((owner, checker)))
    probes = tuple(dict.fromkeys((owner, checker))) if owner_probes else (checker,)
    context = ExecutionContext(caller=owner, environment={"reference": "1"})
    source_schema = {
        "type": "object",
        "required": ["source"],
        "additionalProperties": False,
        "properties": {"source": {"type": "string", "maxLength": 32768}},
    }
    summary_schema = {
        "type": "object",
        "required": ["rows", "total"],
        "additionalProperties": False,
        "properties": {
            "rows": {"type": "integer", "minimum": 0, "maximum": 5000},
            "total": {"type": "string", "maxLength": 80},
        },
    }
    installed: list[tuple[Binding, Capability]] = []

    def install(
        name: str,
        operation: Operation,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        assess: Assessment,
        dependencies: tuple[tuple[Binding, Capability], ...] = (),
    ) -> tuple[Binding, Capability]:
        original = (
            capability(owner, name, tuple(cap.subject for _, cap in dependencies))
            if name != "csv-report"
            else None
        )
        scope = (
            original.scope
            if original
            else Scope(
                task=name,
                input_contract="csv.category-amount.v1",
                output_contract="html-report.v1",
                environment={"reference": "1"},
            )
        )
        subject = Subject(
            id=f"{owner}/registered-{name}",
            version="1",
            digest=fingerprint(
                {
                    "operation": callable_digest(operation),
                    "components": [binding.digest for binding, _ in dependencies],
                    "installed_primitive": original.subject.digest if original else None,
                }
            ),
        )
        binding = Binding(
            id=name,
            revision="1",
            issuer=owner,
            registrar=owner,
            subject=subject,
            scope=scope,
            target=Target(
                kind="local",
                name=name,
                interface_digest=callable_digest(operation),
                implementation_identity="installed",
            ),
            input_schema=inputs,
            output_schema=outputs,
            callers=allowed,
            verification_callers=probes,
            effects="read-only",
            components=tuple(binding.digest for binding, _ in dependencies),
        )
        registry.register_local(binding, operation, assess)
        candidate = Capability(
            schema_version="2",
            binding_digest=binding.digest,
            subject=subject,
            issuer=owner,
            scope=scope,
            entrypoint=name,
            claim="reference-contract",
            dependencies=tuple(cap.subject for _, cap in dependencies),
            dependency_issuers=tuple(cap.issuer for _, cap in dependencies),
            license="Apache-2.0",
            provenance="operator-installed public reference functions",
            classification="declared-new",
            expires_at=capability(owner, "csv-sum").expires_at,
        )
        installed.append((binding, candidate))
        return binding, candidate

    sum_pair = install("csv-sum", aggregate, source_schema, summary_schema, csv_scope)
    render_pair = install(
        "render-report",
        render,
        {
            "type": "object",
            "required": ["summary"],
            "additionalProperties": False,
            "properties": {"summary": summary_schema},
        },
        {"type": "string", "maxLength": 1024},
        lambda args: True,
    )

    async def compose(arguments: dict[str, Any]) -> str:
        @executor(id="aggregate")
        async def aggregate_step(source: str, ctx: WorkflowContext[dict[str, Any]]) -> None:
            binding, _ = sum_pair
            result = await registry.execute(binding.id, binding.digest, {"source": source}, context)
            await ctx.send_message(result)

        @executor(id="render")
        async def render_step(summary: dict[str, Any], ctx: WorkflowContext[str, str]) -> None:
            binding, _ = render_pair
            result = await registry.execute(
                binding.id, binding.digest, {"summary": summary}, context
            )
            await ctx.yield_output(result)

        result = (
            await WorkflowBuilder(start_executor=aggregate_step, max_iterations=3)
            .add_edge(aggregate_step, render_step)
            .build()
            .run(arguments["source"])
        )
        outputs = result.get_outputs()
        if len(outputs) != 1 or not isinstance(outputs[0], str):
            raise ValueError("reference workflow produced no unique report")
        return outputs[0]

    install(
        "csv-report",
        compose,
        source_schema,
        {"type": "string", "maxLength": 1024},
        csv_scope,
        (sum_pair, render_pair),
    )
    return tuple(installed)
