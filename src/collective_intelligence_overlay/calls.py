"""Stable host call context and remote-ID references; no execution state or retry engine."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy import Column, DateTime, String, Table, select
from sqlalchemy.dialects.postgresql import insert

from .bindings import Binding, Target, fingerprint
from .models import Digest, Identifier, now
from .storage import Conflict, Store, metadata

remote_calls = Table(
    "remote_calls",
    metadata,
    Column("owner", String(160), primary_key=True),
    Column("caller", String(160), primary_key=True),
    Column("call_key", String(64), primary_key=True),
    Column("call_id", String(160), nullable=False),
    Column("call_scope", String(160), nullable=False),
    Column("parent_context", String(64)),
    Column("invocation_context", String(64)),
    Column("request_fingerprint", String(64), nullable=False),
    Column("arguments_digest", String(64)),
    Column("lineage_fingerprint", String(64), nullable=False),
    Column("provider", String(160), nullable=False),
    Column("endpoint", String(2048), nullable=False),
    Column("binding_id", String(160), nullable=False),
    Column("binding_digest", String(64), nullable=False),
    Column("provider_binding_id", String(160), nullable=False),
    Column("provider_binding_digest", String(64), nullable=False),
    Column("remote_invocation_id", String(160), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


class MissingCallIdentity(ValueError):
    """A remote operation lacks a stable host-assigned logical identity."""


class CallInstance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    owner: Identifier
    caller: Identifier
    call_scope: Identifier
    call_id: Identifier
    parent_context: Digest | None
    invocation_context: Digest | None
    request_fingerprint: Digest
    lineage_fingerprint: Digest
    depth: int = Field(ge=1, le=16)

    @property
    def key(self) -> str:
        # Content, provider/binding and arrival order never choose the identity.
        return fingerprint(
            {
                "owner": self.owner,
                "caller": self.caller,
                "session": self.call_scope,
                "parent": self.parent_context,
                "call": self.call_id,
            }
        )


active_call: ContextVar[CallInstance | None] = ContextVar("active_overlay_call", default=None)


def call_instance(
    owner: str,
    call_id: str,
    call_scope: str | None,
    invocation_context: str | None,
    request: dict[str, Any],
) -> CallInstance:
    parent = active_call.get()
    if call_scope is not None:
        TypeAdapter(Identifier).validate_python(call_scope)
    scope = call_scope or (parent.call_scope if parent else invocation_context)
    if scope is None:
        raise MissingCallIdentity(
            "provide a persisted call_scope or execute inside a stable Executor invocation"
        )
    TypeAdapter(Identifier).validate_python(call_id)
    TypeAdapter(Identifier).validate_python(scope)
    content = fingerprint(request)
    return CallInstance(
        owner=owner,
        caller=request["caller"],
        call_scope=scope,
        call_id=call_id,
        parent_context=parent.key if parent else invocation_context,
        invocation_context=invocation_context,
        request_fingerprint=content,
        lineage_fingerprint=fingerprint([parent.lineage_fingerprint if parent else None, content]),
        depth=parent.depth + 1 if parent else 1,
    )


class RemoteCall(BaseModel):
    """An owner-scoped saved reference, never a cached business result or authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    owner: Identifier
    caller: Identifier
    call_key: Digest
    call_id: Identifier
    call_scope: Identifier
    parent_context: Digest | None
    invocation_context: Digest | None
    request_fingerprint: Digest
    lineage_fingerprint: Digest
    provider: Identifier
    arguments_digest: Digest | None = None
    endpoint: str
    binding_id: Identifier
    binding_digest: Digest
    provider_binding_id: Identifier
    provider_binding_digest: Digest
    remote_invocation_id: Identifier


class RemoteCalls:
    def __init__(self, store: Store) -> None:
        self.store = store

    def get(self, caller: str, call_key: str) -> RemoteCall | None:
        TypeAdapter(Identifier).validate_python(caller)
        TypeAdapter(Digest).validate_python(call_key)
        with self.store.engine.connect() as conn:
            row = (
                conn.execute(
                    select(remote_calls).where(
                        (remote_calls.c.owner == self.store.owner)
                        & (remote_calls.c.caller == caller)
                        & (remote_calls.c.call_key == call_key)
                    )
                )
                .mappings()
                .first()
            )
        return None if row is None else self._reference(row)

    @staticmethod
    def _reference(row: Any) -> RemoteCall:
        return RemoteCall.model_validate({name: row[name] for name in RemoteCall.model_fields})

    @staticmethod
    def _check(saved: RemoteCall, instance: CallInstance) -> None:
        if (
            saved.request_fingerprint != instance.request_fingerprint
            or saved.lineage_fingerprint != instance.lineage_fingerprint
        ):
            raise Conflict("logical call ID reused with different request or parent content")

    def check(self, instance: CallInstance) -> None:
        saved = self.get(instance.caller, instance.key)
        if saved is not None:
            self._check(saved, instance)

    def bind(
        self,
        instance: CallInstance,
        binding: Binding,
        target: Target,
        arguments: dict[str, Any] | None = None,
    ) -> RemoteCall:
        if instance.owner != self.store.owner or target.peer is None or target.endpoint is None:
            raise ValueError("remote mapping requires the local owner and a pinned provider")
        selector = (
            (remote_calls.c.owner == self.store.owner)
            & (remote_calls.c.caller == instance.caller)
            & (remote_calls.c.call_key == instance.key)
        )
        with self.store.engine.begin() as conn:
            conn.execute(
                insert(remote_calls)
                .values(
                    owner=self.store.owner,
                    caller=instance.caller,
                    call_key=instance.key,
                    call_id=instance.call_id,
                    call_scope=instance.call_scope,
                    parent_context=instance.parent_context,
                    invocation_context=instance.invocation_context,
                    request_fingerprint=instance.request_fingerprint,
                    arguments_digest=fingerprint(arguments) if arguments is not None else None,
                    lineage_fingerprint=instance.lineage_fingerprint,
                    provider=target.peer,
                    endpoint=target.endpoint,
                    binding_id=binding.id,
                    binding_digest=binding.digest,
                    provider_binding_id=target.name,
                    provider_binding_digest=target.interface_digest,
                    remote_invocation_id="call-" + instance.key,
                    created_at=now(),
                )
                .on_conflict_do_nothing()
            )
            row = conn.execute(select(remote_calls).where(selector)).mappings().one()
            saved = self._reference(row)
            self._check(saved, instance)
            if (
                saved.provider != target.peer
                or saved.endpoint != target.endpoint
                or saved.binding_id != binding.id
                or saved.binding_digest != binding.digest
                or saved.provider_binding_id != target.name
                or saved.provider_binding_digest != target.interface_digest
                or saved.arguments_digest
                != (fingerprint(arguments) if arguments is not None else None)
            ):
                raise Conflict("logical call ID reused with a different provider or binding")
            return saved

    def page(
        self,
        caller: str,
        *,
        invocation_id: str | None = None,
        call_scope: str | None = None,
        limit: int = 32,
        after: str | None = None,
    ) -> tuple[RemoteCall, ...]:
        if (invocation_id is None) == (call_scope is None) or not 1 <= limit <= 128:
            raise ValueError("choose one bounded invocation or call-scope lookup")
        TypeAdapter(Identifier).validate_python(caller)
        TypeAdapter(Identifier).validate_python(invocation_id or call_scope)
        selector = (remote_calls.c.owner == self.store.owner) & (remote_calls.c.caller == caller)
        if after is not None:
            TypeAdapter(Digest).validate_python(after)
            selector &= remote_calls.c.call_key > after
        selector &= (
            remote_calls.c.invocation_context
            == fingerprint([self.store.owner, caller, invocation_id])
            if invocation_id is not None
            else remote_calls.c.call_scope == call_scope
        )
        with self.store.engine.connect() as conn:
            rows = (
                conn.execute(
                    select(remote_calls)
                    .where(selector)
                    .order_by(remote_calls.c.call_key)
                    .limit(limit)
                )
                .mappings()
                .all()
            )
        return tuple(self._reference(row) for row in rows)
