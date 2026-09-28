"""Operator-owned execution bindings; no received code or dynamic plugin loading.

The registry holds real callables, while manifests are inspectable JSON data.
Neither a manifest nor a matching JSON schema supplies semantic evidence.
"""

from __future__ import annotations

import copy
import inspect
import json
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import Digest, Identifier, Scope, Subject, UseRequest, uid
from .overlay import Overlay
from .security import Identity, allowed_url, digest

if TYPE_CHECKING:
    from .config import Config

active_invocation: ContextVar[str | None] = ContextVar("active_overlay_invocation", default=None)


def fingerprint(value: Any) -> str:
    """Local request/change identifier, never a replacement DSSE canonicalization."""
    return digest(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    )


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["local", "mcp", "a2a"]
    name: Identifier
    endpoint: str | None = None
    peer: Identifier | None = None
    interface_digest: Digest
    # An observed remote interface is not a digest of remote executable code.
    implementation_identity: Literal["installed", "remote-unknown"]

    @model_validator(mode="after")
    def validate_target(self) -> Target:
        if self.kind == "local":
            if self.endpoint is not None or self.peer is not None:
                raise ValueError("local binding cannot carry a remote destination")
            if self.implementation_identity != "installed":
                raise ValueError("local target must identify installed code")
        else:
            if self.endpoint is None or self.implementation_identity != "remote-unknown":
                raise ValueError(
                    "remote binding requires endpoint and explicit unknown code identity"
                )
            if self.kind == "a2a" and self.peer is None:
                raise ValueError("A2A peer identity required")
        return self


class Binding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    binding_schema: Literal["1"] = "1"
    id: Identifier
    revision: Identifier
    issuer: Identifier
    subject: Subject
    registrar: Identifier
    target: Target
    scope: Scope
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    callers: tuple[Identifier, ...] = Field(min_length=1, max_length=128)
    permissions: tuple[Identifier, ...] = Field(default=(), max_length=64)
    effects: Literal["read-only", "idempotent", "reconcile-required"]
    # JSON pointers to security-relevant argument values and exact allowed values.
    # Paths/URLs/tenants that change authority must be declared by the operator.
    resources: dict[str, tuple[str, ...]] = Field(default_factory=dict, max_length=64)

    @model_validator(mode="after")
    def schemas(self) -> Binding:
        if set(self.permissions) != set(self.scope.permissions):
            raise ValueError("binding and capability scope permissions differ")
        for schema in (self.input_schema, self.output_schema):
            if len(json.dumps(schema).encode()) > 32768:
                raise ValueError("schema too large")
            Draft202012Validator.check_schema(schema)

            # Never fetch remote references during an argument check.
            def check_refs(node: Any) -> None:
                if isinstance(node, dict):
                    for key, value in node.items():
                        if key in {"$ref", "$dynamicRef"} and (
                            not isinstance(value, str) or not value.startswith("#")
                        ):
                            raise ValueError("only local JSON schema references are supported")
                        check_refs(value)
                elif isinstance(node, list):
                    for value in node:
                        check_refs(value)

            check_refs(schema)
        for pointer, values in self.resources.items():
            if not pointer.startswith("/") or not values or len(values) > 256:
                raise ValueError("resource rule requires a JSON pointer and bounded allowlist")
        return self

    @property
    def digest(self) -> str:
        return fingerprint(self.model_dump(mode="json"))


class ExecutionContext(BaseModel):
    """Actual host/caller authority; the host constructs this, never model metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    caller: Identifier
    environment: dict[str, str]
    permissions: frozenset[str] = frozenset()


Operation = Callable[[dict[str, Any]], Awaitable[Any]]
Assessment = Callable[[dict[str, Any]], bool]


@dataclass(frozen=True)
class _Registration:
    binding: Binding
    digest: str
    operation: Operation
    assess: Assessment


@dataclass(frozen=True)
class PreparedCall:
    binding: Binding
    binding_digest: str
    arguments: dict[str, Any]
    arguments_digest: str
    request: UseRequest


def callable_digest(operation: Operation) -> str:
    """Installed source identity, not an attestation of its dependencies or correctness."""
    return digest(inspect.getsource(operation).encode())


def _pointer(arguments: dict[str, Any], pointer: str) -> Any:
    value: Any = arguments
    try:
        for key in pointer[1:].split("/"):
            key = key.replace("~1", "/").replace("~0", "~")
            value = value[int(key)] if isinstance(value, list) else value[key]
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise ValueError("required resource argument missing") from exc
    return value


class Registry:
    """A host registers bindings before exposing an agent or authenticated peer.

    Registration is a trusted Python API, never a wire operation. Updating a binding
    requires a new revision and digest. A prepared call cannot change its operation.
    """

    def __init__(self, overlay: Overlay) -> None:
        self.overlay = overlay
        self._entries: dict[str, _Registration] = {}

    def register_local(self, binding: Binding, operation: Operation, assess: Assessment) -> None:
        if binding.target.kind != "local":
            raise ValueError("local registration requires local binding")
        if callable_digest(operation) != binding.target.interface_digest:
            raise ValueError("installed callable does not match binding")
        self._register(binding, operation, assess)

    def _register(self, binding: Binding, operation: Operation, assess: Assessment) -> None:
        if binding.registrar != self.overlay.store.owner:
            raise ValueError("registration belongs to the local operator")
        if binding.issuer not in self.overlay.store.principals:
            raise ValueError("unknown capability issuer")
        previous = self._entries.get(binding.id)
        if previous and previous.binding.revision == binding.revision:
            raise ValueError("binding revision already registered")
        # Pydantic frozen models can contain mutable dicts: own an isolated copy and
        # compare its original fingerprint again at the actuator boundary.
        owned = binding.model_copy(deep=True)
        self._entries[binding.id] = _Registration(owned, owned.digest, operation, assess)

    def inspect(self, binding_id: str) -> Binding:
        return self._entry(binding_id).binding.model_copy(deep=True)

    def _entry(self, binding_id: str) -> _Registration:
        entry = self._entries.get(binding_id)
        if entry is None:
            raise ValueError("unregistered binding")
        if entry.binding.digest != entry.digest:
            raise ValueError("binding mutated without registration")
        return entry

    def prepare(
        self,
        binding_id: str,
        expected_digest: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> PreparedCall:
        entry = self._entry(binding_id)
        binding = entry.binding
        if entry.digest != expected_digest:
            raise ValueError("binding changed; requalification required")
        if context.caller not in binding.callers:
            raise ValueError("caller not authorized for binding")
        if not set(binding.permissions) <= context.permissions:
            raise ValueError("insufficient execution permissions")
        if context.environment != binding.scope.environment:
            raise ValueError("execution environment changed; requalification required")
        encoded = json.dumps(arguments, allow_nan=False)
        if len(encoded.encode()) > 65536:
            raise ValueError("arguments exceed execution bound")
        actual: dict[str, Any] = json.loads(encoded)
        Draft202012Validator(binding.input_schema).validate(actual)
        for pointer, values in binding.resources.items():
            value = _pointer(actual, pointer)
            if not isinstance(value, str) or value not in values:
                raise ValueError("resource argument not authorized")
        # Assessment is operator-installed domain logic, not inferred schema equality.
        fits = entry.assess(copy.deepcopy(actual)) is True
        request = UseRequest(
            receiver=self.overlay.store.owner,
            subject=binding.subject,
            capability_issuer=binding.issuer,
            scope=binding.scope.model_copy(deep=True),
            semantic_fit="confirmed" if fits else "unknown",
            binding_digest=entry.digest,
            arguments_digest=fingerprint(actual),
        )
        return PreparedCall(
            binding.model_copy(deep=True), entry.digest, actual, fingerprint(actual), request
        )

    async def execute(
        self,
        binding_id: str,
        expected_digest: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
        *,
        before_call: Callable[[], Awaitable[None]] | None = None,
    ) -> Any:
        prepared = self.prepare(binding_id, expected_digest, arguments, context)
        entry = self._entry(binding_id)

        async def actuator() -> Any:
            current = self._entry(binding_id)
            if current is not entry or current.digest != prepared.binding_digest:
                raise ValueError("binding changed before execution")
            checked = self.prepare(binding_id, expected_digest, prepared.arguments, context)
            if (
                checked.arguments_digest != prepared.arguments_digest
                or checked.request != prepared.request
            ):
                raise ValueError("invocation changed before execution")
            result = await entry.operation(copy.deepcopy(prepared.arguments))
            if len(json.dumps(result, allow_nan=False).encode()) > 65536:
                raise ValueError("result exceeds execution bound")
            Draft202012Validator(entry.binding.output_schema).validate(result)
            return result

        async def operation() -> Any:
            if before_call is not None:
                await before_call()
                # Durable dispatch can yield to another task: recheck admission
                # and the exact registration after that await, before the actuator.
                return await self.overlay.execute(prepared.request, actuator)
            return await actuator()

        return await self.overlay.execute(prepared.request, operation)

    def register_mcp(self, binding: Binding, assess: Assessment, *, local: bool = False) -> None:
        if binding.target.kind != "mcp" or binding.target.endpoint is None:
            raise ValueError("MCP registration requires an MCP target")
        endpoint = allowed_url(
            binding.target.endpoint, frozenset({binding.target.endpoint}), local=local
        )
        target = binding.target.model_copy(deep=True)

        async def operation(arguments: dict[str, Any]) -> Any:
            from .adapters.mcp import invoke_registered

            return await invoke_registered(
                endpoint, target.name, target.interface_digest, arguments
            )

        self._register(binding, operation, assess)

    def register_a2a(
        self, binding: Binding, assess: Assessment, config: Config, identity: Identity
    ) -> None:
        """Invoke an explicitly registered provider binding through official A2A.

        interface_digest identifies the provider's binding manifest, not remote code.
        The provider applies its own authority/admission/allowance and returns a
        durable business result inside an immediate protocol Message.
        """
        target = binding.target.model_copy(deep=True)
        if target.kind != "a2a" or target.peer is None or target.endpoint is None:
            raise ValueError("A2A registration requires an exact peer destination")
        peer = next((peer for peer in config.peers if peer.identity == target.peer), None)
        if peer is None or peer.url != target.endpoint or identity.name != self.overlay.store.owner:
            raise ValueError("A2A binding does not match operator-owned peer configuration")
        peer_name = target.peer
        local_binding_id, local_binding_digest = binding.id, binding.digest

        async def operation(arguments: dict[str, Any]) -> Any:
            from .adapters.a2a import send

            invocation = fingerprint(
                [
                    active_invocation.get() or uid(),
                    local_binding_id,
                    local_binding_digest,
                    arguments,
                ]
            )
            response = await send(
                config,
                identity,
                peer_name,
                {
                    "operation": "invoke",
                    "invocation_id": invocation,
                    "binding_id": target.name,
                    "binding_digest": target.interface_digest,
                    "arguments": arguments,
                },
            )
            if response.get("state") != "completed":
                raise ValueError(
                    "remote invocation is incomplete or unknown; reconcile by invocation ID"
                )
            return response["result"]

        self._register(binding, operation, assess)
