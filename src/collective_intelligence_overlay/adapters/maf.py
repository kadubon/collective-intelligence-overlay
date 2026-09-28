"""Public Microsoft Agent Framework middleware and workflow integration."""

from collections.abc import Awaitable, Callable
from typing import Any

from agent_framework import (
    FunctionInvocationContext,
    FunctionMiddleware,
    FunctionTool,
    MiddlewareFailure,
    tool,
)

from ..bindings import ExecutionContext, Registry
from ..models import UseRequest
from ..overlay import AdmissionDenied, Overlay


def bound_tool(registry: Registry, binding_id: str, context: ExecutionContext) -> FunctionTool:
    """Create an ordinary MAF tool with a pinned operator registration.

    The model controls arguments only. Binding updates require the host to create
    a new tool; an old tool cannot silently start invoking the changed operation.
    """
    binding = registry.inspect(binding_id)
    execution_context = context.model_copy(deep=True)

    @tool(
        name=binding_id,
        description="Invoke the operator-registered capability with checked inputs.",
    )
    async def invoke(arguments: dict[str, Any]) -> Any:
        return await registry.execute(binding_id, binding.digest, arguments, execution_context)

    return invoke


class AdmissionMiddleware(FunctionMiddleware):
    """Operator-provided mappings, never inferred from model/tool descriptions."""

    def __init__(self, overlay: Overlay, requests: dict[str, UseRequest]) -> None:
        self.overlay = overlay
        self.requests = dict(requests)

    async def process(
        self, context: FunctionInvocationContext, call_next: Callable[[], Awaitable[None]]
    ) -> None:
        request = self.requests.get(context.function.name)
        if request is None:
            raise MiddlewareFailure("unregistered function")
        try:
            await self.overlay.execute(request, call_next)
        except AdmissionDenied as exc:
            raise MiddlewareFailure(str(exc)) from exc
