"""Operator-owned execution bindings; no received code or dynamic plugin loading.

The registry holds real callables, while manifests are inspectable JSON data.
Neither a manifest nor a matching JSON schema supplies semantic evidence.
"""

from __future__ import annotations

import asyncio
import copy
import inspect
import json
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from .artifacts import Artifacts
from .blocking import run_blocking
from .models import Digest, Identifier, ReceiptRef, Scope, Subject, UseRequest
from .overlay import Overlay
from .security import Identity, allowed_url, digest

if TYPE_CHECKING:
    import httpx
    import httpx2

    from .calls import RemoteCall
    from .config import Config

active_invocation: ContextVar[str | None] = ContextVar("active_overlay_invocation", default=None)
formation_receipts: ContextVar[list[ReceiptRef] | None] = ContextVar(
    "observed_formation_receipts", default=None
)
formation_steps: ContextVar[list[int] | None] = ContextVar("bounded_formation_steps", default=None)


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
    binding_schema: Literal["1", "2"] = "1"
    artifact_digest: Digest | None = None
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
    verification_callers: tuple[Identifier, ...] = Field(default=(), max_length=128)
    permissions: tuple[Identifier, ...] = Field(default=(), max_length=64)
    effects: Literal["read-only", "idempotent", "reconcile-required"]
    # JSON pointers to security-relevant argument values and exact allowed values.
    # Paths/URLs/tenants that change authority must be declared by the operator.
    resources: dict[str, tuple[str, ...]] = Field(default_factory=dict, max_length=64)
    components: tuple[Digest, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def schemas(self) -> Binding:
        if (self.binding_schema == "2") != (self.artifact_digest is not None):
            raise ValueError("binding v2 requires a persisted artifact; v1 cannot claim one")
        if self.binding_schema == "2" and (
            self.target.kind != "local" or self.subject.digest != self.artifact_digest
        ):
            raise ValueError("artifact binding must identify its local persisted subject")
        if self.verification_callers and (
            self.effects != "read-only" or not set(self.verification_callers) <= set(self.callers)
        ):
            raise ValueError("verification grants require read-only effects and authorized callers")
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
        return fingerprint(
            self.model_dump(
                mode="json", exclude={"artifact_digest"} if self.binding_schema == "1" else set()
            )
        )


class ArtifactSpec(BaseModel):
    """Reconstruction data for installed code, not a workflow or executable format."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    artifact_schema: Literal["1"] = "1"
    builder_id: Identifier
    builder_version: Identifier
    builder_source: Digest
    parameters: dict[str, JsonValue] = Field(max_length=64)
    environment: dict[Identifier, Identifier] = Field(max_length=64)
    components: tuple[Digest, ...] = Field(default=(), max_length=64)
    data_artifacts: tuple[Digest, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def bounded_parameters(self) -> ArtifactSpec:
        if len(json.dumps(self.parameters, allow_nan=False).encode()) > 65536:
            raise ValueError("persisted parameters exceed byte bound")
        return self

    def persist(self, artifacts: Artifacts) -> str:
        return artifacts.put(self.model_dump_json().encode())


class ExecutionContext(BaseModel):
    """Actual host/caller authority; the host constructs this, never model metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    caller: Identifier
    purpose: Literal["reuse", "verification"] = "reuse"
    environment: dict[str, str]
    permissions: frozenset[str] = frozenset()


active_binding: ContextVar[Binding | None] = ContextVar("active_execution_binding", default=None)


Operation = Callable[[dict[str, Any]], Awaitable[Any]]
Assessment = Callable[[dict[str, Any]], bool]


class InvalidArguments(ValueError):
    """An input violates a host-installed argument bound or resource allowlist."""


@dataclass(frozen=True)
class _Registration:
    binding: Binding
    digest: str
    operation: Operation
    assess: Assessment
    remote_identity: bool = False


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
        raise InvalidArguments("required resource argument missing") from exc
    return value


class Registry:
    """A host registers bindings before exposing an agent or authenticated peer.

    Registration is a trusted Python API, never a wire operation. Updating a binding
    requires a new revision and digest. A prepared call cannot change its operation.
    """

    def __init__(self, overlay: Overlay) -> None:
        self.overlay = overlay
        self._entries: dict[str, _Registration] = {}
        self._digests: dict[str, _Registration] = {}

    def register_local(self, binding: Binding, operation: Operation, assess: Assessment) -> None:
        if binding.binding_schema != "1":
            raise ValueError("persisted bindings require register_artifact")
        if binding.target.kind != "local":
            raise ValueError("local registration requires local binding")
        if callable_digest(operation) != binding.target.interface_digest:
            raise ValueError("installed callable does not match binding")
        self._register(binding, operation, assess)

    def register_artifact(
        self,
        binding: Binding,
        artifacts: Artifacts,
        factory: Callable[[dict[str, JsonValue]], Operation],
        assess: Assessment,
        *,
        builder_id: str,
        builder_version: str,
    ) -> None:
        """Reconstruct only through a host-installed factory with pinned configuration.

        Factory registration is operator authority. Data contains no import path,
        code, shell command or package reference to execute. Global dependencies
        of installed code remain a host/environment trust assumption.
        """
        binding = Binding.model_validate(binding.model_dump())
        if binding.binding_schema != "2" or binding.artifact_digest is None:
            raise ValueError("expected a persisted v2 binding")
        manifest_digest = binding.artifact_digest
        raw = artifacts.get(manifest_digest)
        spec = ArtifactSpec.model_validate_json(raw)
        factory_digest = digest(inspect.getsource(factory).encode())
        if (
            spec.builder_id != builder_id
            or spec.builder_version != builder_version
            or spec.builder_source != factory_digest
            or spec.environment != binding.scope.environment
            or spec.components != binding.components
        ):
            raise ValueError("artifact builder, environment or components changed")
        for data_digest in spec.data_artifacts:
            artifacts.get(data_digest)
        operation = factory(copy.deepcopy(spec.parameters))
        if callable_digest(operation) != binding.target.interface_digest:
            raise ValueError("reconstructed operation differs from binding")

        async def reconstructed(arguments: dict[str, Any]) -> Any:
            # Fresh parameters prevent state retained in one closure from silently
            # redefining a persisted procedure on subsequent calls.
            if artifacts.get(manifest_digest) != raw:
                raise ValueError("persisted parameters changed")
            for data_digest in spec.data_artifacts:
                artifacts.get(data_digest)
            if digest(inspect.getsource(factory).encode()) != factory_digest:
                raise ValueError("installed factory changed")
            current = factory(copy.deepcopy(spec.parameters))
            if callable_digest(current) != binding.target.interface_digest:
                raise ValueError("reconstructed operation changed")
            return await current(arguments)

        self._register(binding, reconstructed, assess)

    def _register(
        self,
        binding: Binding,
        operation: Operation,
        assess: Assessment,
        *,
        remote_identity: bool = False,
    ) -> None:
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
        entry = _Registration(owned, owned.digest, operation, assess, remote_identity)
        if previous is not None:
            self._digests.pop(previous.digest, None)
        self._entries[binding.id] = entry
        self._digests[entry.digest] = entry

    def _check_components(
        self, binding: Binding, path: frozenset[str] = frozenset(), checked: set[str] | None = None
    ) -> None:
        checked = set() if checked is None else checked
        if binding.digest in path or len(path) >= 64:
            raise ValueError("cyclic or excessive registered composition")
        if binding.digest in checked:
            return
        if len(checked) >= self.overlay.max_graph_nodes:
            raise ValueError("composition exceeds local dependency bound")
        for component_digest in binding.components:
            component = self._digests.get(component_digest)
            if component is None or component.binding.digest != component_digest:
                raise ValueError("component binding changed; requalification required")
            self._check_components(component.binding, path | {binding.digest}, checked)
        checked.add(binding.digest)

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
        self._check_components(binding)
        parent = active_binding.get()
        if parent is not None and entry.digest not in parent.components:
            raise ValueError("child binding is not an authorized component")
        if entry.digest != expected_digest:
            raise ValueError("binding changed; requalification required")
        if context.caller not in binding.callers:
            raise ValueError("caller not authorized for binding")
        if context.purpose == "verification" and context.caller not in binding.verification_callers:
            raise ValueError("caller has no operator verification grant")
        if not set(binding.permissions) <= context.permissions:
            raise ValueError("insufficient execution permissions")
        if context.environment != binding.scope.environment:
            raise ValueError("execution environment changed; requalification required")
        encoded = json.dumps(arguments, allow_nan=False)
        if len(encoded.encode()) > 65536:
            raise InvalidArguments("arguments exceed execution bound")
        actual: dict[str, Any] = json.loads(encoded)
        Draft202012Validator(binding.input_schema).validate(actual)
        for pointer, values in binding.resources.items():
            value = _pointer(actual, pointer)
            if not isinstance(value, str) or value not in values:
                raise InvalidArguments("resource argument not authorized")
        # Assessment is operator-installed domain logic, not inferred schema equality.
        fits = entry.assess(copy.deepcopy(actual)) is True
        request = UseRequest(
            purpose=context.purpose,
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
        call_id: str | None = None,
        call_scope: str | None = None,
    ) -> Any:
        from .calls import MissingCallIdentity, RemoteCalls, active_call, call_instance
        from .invocations import invocation_request

        arguments = copy.deepcopy(arguments)
        context = context.model_copy(deep=True)
        frame = active_call.get()
        identity_missing = call_id is None
        if call_id is not None:
            try:
                frame = call_instance(
                    self.overlay.store.owner,
                    call_id,
                    call_scope,
                    active_invocation.get(),
                    invocation_request(
                        self.overlay.store.owner, binding_id, expected_digest, arguments, context
                    ),
                )
            except MissingCallIdentity:
                identity_missing = True
                # Unscoped local tools retain their existing non-persistent API.
                # They do not acquire a remote identity or an idempotency claim.
            else:
                assert frame is not None
                await run_blocking(RemoteCalls(self.overlay.store).check, frame)
        entry = self._entry(binding_id)
        if entry.remote_identity and identity_missing:
            raise MissingCallIdentity(
                "A2A calls require call_id and persisted call_scope, or a stable Executor parent"
            )
        prepared = self.prepare(binding_id, expected_digest, arguments, context)

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
            token = active_binding.set(entry.binding)
            call_token = active_call.set(frame)
            try:
                result = await entry.operation(copy.deepcopy(prepared.arguments))
            finally:
                active_call.reset(call_token)
                active_binding.reset(token)
            if len(json.dumps(result, allow_nan=False).encode()) > 65536:
                raise ValueError("result exceeds execution bound")
            Draft202012Validator(entry.binding.output_schema).validate(result)
            return result

        async def operation() -> Any:
            if before_call is not None:
                await before_call()
                # Durable dispatch can yield to another task: recheck admission
                # and the exact registration after that await, before the actuator.
                return await self.overlay.execute(
                    prepared.request,
                    actuator,
                    verification_granted=context.purpose == "verification",
                )
            return await actuator()

        return await self.overlay.execute(
            prepared.request, operation, verification_granted=context.purpose == "verification"
        )

    def register_mcp(
        self,
        binding: Binding,
        assess: Assessment,
        *,
        local: bool = False,
        http_client_factory: Callable[[], httpx2.AsyncClient] | None = None,
    ) -> None:
        if binding.target.kind != "mcp" or binding.target.endpoint is None:
            raise ValueError("MCP registration requires an MCP target")
        endpoint = allowed_url(
            binding.target.endpoint, frozenset({binding.target.endpoint}), local=local
        )
        target = binding.target.model_copy(deep=True)

        async def operation(arguments: dict[str, Any]) -> Any:
            from .adapters.mcp import invoke_registered

            return await invoke_registered(
                endpoint,
                target.name,
                target.interface_digest,
                arguments,
                http_client_factory=http_client_factory,
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
        pinned_binding = binding.model_copy(deep=True)

        async def operation(arguments: dict[str, Any]) -> Any:
            from .adapters.a2a import send
            from .calls import MissingCallIdentity, RemoteCalls, active_call

            instance = active_call.get()
            if instance is None:
                raise MissingCallIdentity(
                    "A2A call has no stable host context; provide call_id and call_scope"
                )
            saving = asyncio.create_task(
                run_blocking(
                    RemoteCalls(self.overlay.store).bind,
                    instance,
                    pinned_binding,
                    target,
                    arguments,
                )
            )
            try:
                saved = await asyncio.shield(saving)
            except asyncio.CancelledError:
                # The DB thread may already have committed. Join it before the
                # host closes its store, and never dispatch a cancelled caller.
                await asyncio.shield(saving)
                raise
            response = await send(
                config,
                identity,
                peer_name,
                {
                    "operation": "invoke",
                    "invocation_id": saved.remote_invocation_id,
                    "binding_id": target.name,
                    "binding_digest": target.interface_digest,
                    "arguments": arguments,
                    # Checking a local proxy still reuses an independently
                    # admitted provider binding. Local verification grants are
                    # not delegated to the authenticated remote resource owner.
                    "purpose": "reuse",
                },
            )
            if response.get("state") != "completed":
                raise ValueError(
                    "remote invocation is incomplete or unknown; reconcile by invocation ID"
                )
            return response["result"]

        self._register(binding, operation, assess, remote_identity=True)

    def remote_calls(
        self,
        context: ExecutionContext,
        *,
        invocation_id: str | None = None,
        call_scope: str | None = None,
        limit: int = 32,
        after: str | None = None,
    ) -> tuple[RemoteCall, ...]:
        """Read one bounded page; continue after its last key when the page is full.

        An empty map never proves that a legacy or uncertain operation had no effect.
        """
        from .calls import RemoteCalls

        return RemoteCalls(self.overlay.store).page(
            context.caller,
            invocation_id=invocation_id,
            call_scope=call_scope,
            limit=limit,
            after=after,
        )

    async def query_remote_call(
        self, call_key: str, context: ExecutionContext, config: Config, identity: Identity
    ) -> dict[str, Any] | None:
        """Query the saved provider ID without issuing an invocation or recomputing IDs."""
        from .adapters.a2a import send
        from .calls import RemoteCalls

        if identity.name != self.overlay.store.owner or config.owner != identity.name:
            raise ValueError("remote lookup requires the local owner")
        saved = await run_blocking(RemoteCalls(self.overlay.store).get, context.caller, call_key)
        if saved is None:
            return None
        peer = next((peer for peer in config.peers if peer.identity == saved.provider), None)
        if peer is None or peer.url != saved.endpoint:
            raise ValueError("saved remote provider destination changed; reconcile explicitly")
        response = await send(
            config,
            identity,
            saved.provider,
            {"operation": "invocation", "invocation_id": saved.remote_invocation_id},
        )
        if set(response) != {"invocation"}:
            raise ValueError("provider query returned no authoritative invocation response")
        result = response.get("invocation")
        if result is not None and not isinstance(result, dict):
            raise ValueError("invalid remote invocation lookup")
        return result

    def register_a2a_service(
        self,
        binding: Binding,
        assess: Assessment,
        *,
        auth: httpx.Auth | None = None,
        local: bool = False,
    ) -> None:
        """Bind a standard A2A service with a pinned card and immediate JSON result.

        Credentials belong to the host's HTTPX auth object, never signed manifests.
        The card pin identifies an interface declaration, not remote executable code.
        """
        target = binding.target.model_copy(deep=True)
        if target.kind != "a2a" or target.endpoint is None or target.peer is None:
            raise ValueError("standard A2A registration requires an exact service destination")
        endpoint = allowed_url(target.endpoint, frozenset({target.endpoint}), local=local)

        async def operation(arguments: dict[str, Any]) -> Any:
            from .adapters.a2a_service import invoke

            return await invoke(target, endpoint, arguments, auth=auth)

        self._register(binding, operation, assess)
