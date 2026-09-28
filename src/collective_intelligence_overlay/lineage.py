"""Observed formation links from actual completed invocations, not causal proofs."""

from __future__ import annotations

import asyncio
import contextlib
from decimal import Decimal
from types import TracebackType
from typing import Any

from sqlalchemy import select

from .bindings import Registry, formation_receipts, formation_steps
from .invocations import invocations
from .models import Capability, Event, FormationReceipt, ReceiptRef, Verdict, uid
from .security import Identity, verify
from .storage import Conflict, records


class FormationSession:
    """Bounded operator construction using installed code and ordinary SDK calls.

    The host builds/registers the real executable; this context only witnesses
    returned invocation receipts and publishes their scoped relationship. It does
    not synthesize or execute code and makes no functional-novelty or causal claim.
    """

    def __init__(
        self, registry: Registry, identity: Identity, *, max_steps: int = 16, max_seconds: int = 120
    ) -> None:
        if identity.name != registry.overlay.store.owner:
            raise ValueError("formation belongs to the local resource owner")
        if not 1 <= max_steps <= 64 or not 1 <= max_seconds <= 300:
            raise ValueError("invalid formation bounds")
        self.registry, self.identity = registry, identity
        self.store = registry.overlay.store
        self.max_steps, self.max_seconds = max_steps, max_seconds
        self.id = "formation-" + uid()
        self.receipts: list[ReceiptRef] = []
        self.published = False
        self.active = False

    async def __aenter__(self) -> FormationSession:
        if self.active or self.published or formation_receipts.get() is not None:
            raise ValueError("nested formation sessions are not supported")
        self.fence = await asyncio.to_thread(
            self.store.acquire, self.id, self.identity.name, "work", Decimal(1), self.max_seconds
        )
        self.receipt_token = formation_receipts.set(self.receipts)
        self.step_token = formation_steps.set([0, self.max_steps])
        self.timeout = asyncio.timeout(self.max_seconds)
        await self.timeout.__aenter__()
        self.active = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        formation_receipts.reset(self.receipt_token)
        formation_steps.reset(self.step_token)
        self.active = False
        if not self.published:
            with contextlib.suppress(Conflict):
                await asyncio.shield(
                    asyncio.to_thread(
                        self.store.finish, self.id, self.identity.name, self.fence, cancelled=True
                    )
                )
        await self.timeout.__aexit__(exc_type, exc, tb)
        return None

    async def publish(self, binding_id: str, candidate: Capability) -> Event:
        if not self.active or self.published or not self.receipts:
            raise ValueError("formation requires an active session with observed completed use")
        binding = self.registry.inspect(binding_id)
        if (
            binding.subject != candidate.subject
            or binding.issuer != candidate.issuer
            or binding.digest != candidate.binding_digest
            or candidate.issuer != self.identity.name
            or candidate.scope != binding.scope
            or binding.target.kind != "local"
        ):
            raise ValueError("candidate must identify the actual locally installed binding")
        event = await asyncio.to_thread(self._validate, candidate)
        await asyncio.to_thread(
            self.store.commit_work,
            self.id,
            self.identity.name,
            self.fence,
            [self.identity.sign(candidate), self.identity.sign(event)],
        )
        self.published = True
        return event

    def _validate(self, candidate: Capability) -> Event:
        if candidate.binding_digest is None:
            raise ValueError("formation requires a v2 binding identity")
        if any(ref.issuer != self.identity.name for ref in self.receipts):
            raise ValueError("observed formation requires local execution observations")
        ids = {ref.id for ref in self.receipts}
        with self.store.engine.connect() as conn:
            signed: Any = (
                conn.execute(
                    select(records.c.envelope).where(
                        (records.c.kind == "event")
                        & (records.c.issuer == self.identity.name)
                        & records.c.record_id.in_(ids)
                    )
                )
                .scalars()
                .all()
            )
            outcomes = {
                row["receipt_id"]: row
                for row in conn.execute(
                    select(invocations).where(invocations.c.receipt_id.in_(ids))
                ).mappings()
            }
        if len(signed) != len(ids) or len(outcomes) != len(ids):
            raise ValueError("formation receipt is missing or has no local execution")
        dependencies = set(zip(candidate.dependencies, candidate.dependency_issuers, strict=True))
        for envelope in signed:
            event = verify(envelope, self.store.principals)
            if not isinstance(event, Event) or event.execution is None:
                raise ValueError("legacy/unknown-scope events cannot prove observed formation")
            receipt = event.execution
            outcome = outcomes[event.id]
            if (
                receipt.state != "completed"
                or outcome["state"] != "completed"
                or receipt.result_digest != outcome["result_digest"]
                or receipt.binding_digest != outcome["binding_digest"]
                or event.subject == candidate.subject
                or (event.subject, receipt.capability_issuer) not in dependencies
            ):
                raise ValueError("formation lineage is cyclic, incomplete or inconsistent")
        return Event(
            schema_version="2",
            id=self.id,
            issuer=self.identity.name,
            subject=candidate.subject,
            action="composition" if len(ids) > 1 else "formation",
            task_id=self.id,
            attempt_id=self.id,
            correlation_id=self.id,
            outcome=Verdict.UNKNOWN,
            formation=FormationReceipt(
                receipts=tuple(self.receipts),
                scope=candidate.scope,
                binding_digest=candidate.binding_digest,
                policy_digest=self.registry.overlay.policy.digest,
                relationship="observed-use",
            ),
        )
