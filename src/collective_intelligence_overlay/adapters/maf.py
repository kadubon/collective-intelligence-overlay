"""Public Microsoft Agent Framework middleware and workflow integration."""

from collections.abc import Awaitable, Callable

from agent_framework import FunctionInvocationContext, FunctionMiddleware, MiddlewareFailure

from ..models import UseRequest
from ..overlay import AdmissionDenied, Overlay


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
