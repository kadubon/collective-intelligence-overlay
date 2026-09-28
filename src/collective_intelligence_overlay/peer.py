"""Peer service binds configured runtime resources to the public overlay API."""

import asyncio
import time
from collections.abc import Callable
from typing import Any

from jsonschema import ValidationError as SchemaError  # type: ignore[import-untyped]

from .accounting import capability_metrics, metrics_page
from .bindings import ExecutionContext, Registry
from .config import Config
from .invocations import Executor, Reservation
from .models import Event, Revocation, Subject, UseRequest, uid
from .proposal_exchange import ProposalExchange
from .queries import RecordCursor, RecordQuery
from .security import verify
from .storage import Conflict
from .synchronization import Feed, FeedFilter, ResnapshotRequired


class PeerService:
    def __init__(self, config: Config, configure: Callable[[Registry], None] | None = None) -> None:
        self.config = config
        self.identity, self.overlay = config.runtime()
        self.registry = Registry(self.overlay)
        self.proposal_exchange: ProposalExchange | None = None
        if configure is not None:
            configure(self.registry)
        self.executor = Executor(
            self.registry, self.identity, Reservation(seconds=min(config.max_seconds, 30))
        )

    async def handle(self, caller: str, data: dict[str, Any]) -> dict[str, Any]:
        operation = data.get("operation")
        started = time.perf_counter()
        if operation == "propose":
            if self.proposal_exchange is None or caller not in {
                p.identity for p in self.config.peers
            }:
                raise ValueError("peer not authorized for proposal exchange")
            return await self.proposal_exchange.respond(caller, data["envelope"])
        if operation == "discover":
            # Explicitly configured peers may read this peer's shared record set.
            if not self.config.share_records or caller not in {
                p.identity for p in self.config.peers
            }:
                raise ValueError("peer not authorized for evidence exchange")
            try:
                page = await asyncio.to_thread(
                    Feed(self.overlay.store, self.identity).page,
                    caller,
                    FeedFilter.model_validate(data.get("filter", {})),
                    cursor=data.get("cursor"),
                    since=int(data.get("since", 0)),
                    generation=data.get("generation"),
                    limit=int(data.get("limit", 32)),
                )
            except ResnapshotRequired:
                return {"error": "RESNAPSHOT_REQUIRED"}
            return page.model_dump(mode="json")
        if operation == "submit":
            record = verify(data["envelope"], self.overlay.store.principals)
            if record.issuer != caller:
                raise ValueError("issuer must match authenticated submitting peer")
            if record.kind in {"opportunity", "proposal"}:
                raise ValueError("work proposals require a registered goal exchange")
            return {"inserted": self.overlay.store.put(data["envelope"])}
        if operation == "invoke":
            context = ExecutionContext(
                caller=caller,
                purpose=data.get("purpose", "reuse"),
                environment=self.config.execution_environment,
                permissions=frozenset(self.config.policy.permissions),
            )
            try:
                return await self.executor.invoke(
                    str(data["invocation_id"]),
                    str(data["binding_id"]),
                    str(data["binding_digest"]),
                    data["arguments"],
                    context,
                )
            except Conflict:
                return {"state": "conflict", "error": "INVOCATION_OR_ALLOWANCE_CONFLICT"}
            except (ValueError, SchemaError):
                return {"state": "rejected", "error": "INVALID_OR_UNAUTHORIZED_BINDING"}
        if operation in {"invocation", "cancel_invocation"}:
            lookup = (
                self.executor.store.cancel
                if operation == "cancel_invocation"
                else self.executor.store.get
            )
            return {
                "invocation": await asyncio.to_thread(lookup, caller, str(data["invocation_id"]))
            }
        if caller != self.config.owner:
            raise ValueError("owner operation; delegation is not configured")
        if operation == "sync":
            from .adapters.a2a import synchronize

            return await synchronize(
                self.config,
                self.identity,
                self.overlay.store,
                str(data["peer"]),
                filter_data=data.get("filter"),
                max_pages=int(data.get("max_pages", 16)),
                page_size=int(data.get("page_size", 32)),
                restart=data.get("restart") is True,
            )
        if operation == "qualify":
            decision = await self.overlay.qualify(UseRequest.model_validate(data["request"]))
            self.record_event(
                decision.request.subject, "admission", "overhead", started, decision.outcome
            )
            return {
                "decision": decision.model_dump(mode="json"),
                "next_work": self.overlay.recommend(decision),
            }
        if operation == "capability_metrics":
            requests = data.get("requests")
            if not isinstance(requests, list) or not 1 <= len(requests) <= 32:
                raise ValueError("expected 1 to 32 explicit use requests")
            return await capability_metrics(
                self.overlay, tuple(UseRequest.model_validate(request) for request in requests)
            )
        if operation == "metrics":
            return await asyncio.to_thread(
                metrics_page,
                self.overlay.store,
                RecordQuery.model_validate(data.get("query", {"kinds": ["event"]})),
                cursor=RecordCursor.model_validate(data["cursor"]) if data.get("cursor") else None,
                limit=int(data.get("limit", 128)),
                byte_limit=32768,
            )
        if operation == "revoke":
            subject = Subject.model_validate(data["subject"])
            if not any(
                c.subject == subject and c.issuer == self.config.owner
                for c in self.overlay.store.capabilities()
            ):
                raise ValueError("can only revoke own capability")
            record = Revocation(
                issuer=self.config.owner, subject=subject, reason=str(data["reason"])
            )
            envelope = self.identity.sign(record)
            self.overlay.store.put(envelope)
            self.record_event(subject, "revocation", "revocation", started)
            return {"envelope": envelope}
        raise ValueError("unknown operation")

    def record_event(
        self, subject: Subject, action: str, category: str, started: float, outcome: Any = None
    ) -> None:
        event_id = uid()
        event = Event.model_validate(
            {
                "issuer": self.config.owner,
                "subject": subject,
                "action": action,
                "task_id": event_id,
                "attempt_id": event_id,
                "correlation_id": event_id,
                "outcome": outcome,
                "costs": [
                    {
                        "category": category,
                        "status": "measured",
                        "quantity": str(round(time.perf_counter() - started, 9)),
                        "unit": "wall_seconds",
                    }
                ],
            }
        )
        self.overlay.store.put(self.identity.sign(event))
