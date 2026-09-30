"""Original-ID observation through existing Registry, RemoteCalls and signed events."""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from .bindings import ExecutionContext, Registry, fingerprint
from .blocking import run_blocking
from .calls import RemoteCall, RemoteCalls
from .config import Config
from .invocations import InvocationStore
from .models import Cost, Digest, Event, Identifier, ReceiptRef, ReconciliationReceipt
from .queries import RecordQuery
from .security import Identity
from .storage import Conflict


class EffectObservation(BaseModel):
    """A trusted query's scoped finding, distinct from independent quality checks."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    provider_invocation_id: Identifier
    provider_binding_digest: Digest
    arguments_digest: Digest
    effect: Literal["confirmed", "absent", "unknown"]
    observation_digest: Digest
    reason: Identifier


class Reconciliations:
    """Append observations, never resend, settle, refund, change UNKNOWN or create PASS."""

    def __init__(self, registry: Registry, config: Config, identity: Identity) -> None:
        self.registry, self.config, self.identity = registry, config, identity
        self.store = registry.overlay.store
        self._queries: dict[str, str] = {}

    def register(self, binding_id: str) -> None:
        binding = self.registry.inspect(binding_id)
        if (
            binding.issuer != self.store.owner
            or binding.effects != "read-only"
            or self.store.owner not in binding.verification_callers
            or binding_id in self._queries
        ):
            raise ValueError("reconciler requires one owner-approved read-only query binding")
        self._queries[binding_id] = binding.digest

    def _saved(self, event_id: str) -> Event | None:
        page = self.store.record_page(
            RecordQuery(kinds=("event",), issuer=self.store.owner, record_id=event_id), limit=1
        )
        if not page.items:
            return None
        record = page.items[0]
        if not isinstance(record, Event) or record.reconciliation is None:
            raise Conflict("reconciliation command ID already used for another event")
        return record

    @staticmethod
    def _validate(saved: RemoteCall, owner: str, response: dict[str, Any] | None) -> str:
        if saved.arguments_digest is None:
            return "LEGACY_REMOTE_ARGUMENTS_UNKNOWN"
        if response is None:
            return "PROVIDER_RESULT_ABSENT"
        if (
            response.get("id") != saved.remote_invocation_id
            or response.get("caller") != owner
            or response.get("owner") != saved.provider
            or response.get("binding_id") != saved.provider_binding_id
            or response.get("binding_digest") != saved.provider_binding_digest
            or response.get("arguments_digest") != saved.arguments_digest
            or response.get("purpose") != "reuse"
        ):
            return "PROVIDER_REQUEST_MISMATCH"
        if response.get("state") not in {
            "completed",
            "running",
            "unknown",
            "cancelled",
            "rejected",
        }:
            return "PROVIDER_STATE_INVALID"
        if response["state"] == "completed" and (
            not response.get("result_digest")
            or response["result_digest"] != fingerprint(response.get("result"))
        ):
            return "PROVIDER_RESULT_DIGEST_MISMATCH"
        try:
            TypeAdapter(Digest).validate_python(response.get("fingerprint"))
            if response.get("result_digest") is not None:
                TypeAdapter(Digest).validate_python(response["result_digest"])
        except ValidationError:
            return "PROVIDER_DIGEST_INVALID"
        return "PROVIDER_REPORTED_" + str(response["state"]).upper()

    async def observe(
        self,
        caller: str,
        call_key: str,
        command_id: str,
        *,
        invocation_id: str | None = None,
        reconciler: str | None = None,
    ) -> Event:
        if caller != self.store.owner:
            raise ValueError("reconciliation is owner-only")
        # Stable operator command IDs deduplicate an observation, not future queries.
        TypeAdapter(Identifier).validate_python(command_id)
        event_id = "reconcile-" + fingerprint([caller, command_id])
        previous = await run_blocking(self._saved, event_id)
        if previous is not None:
            assert previous.reconciliation is not None
            r = previous.reconciliation
            if r.call_key != call_key or r.original_invocation_id != invocation_id:
                raise Conflict("reconciliation command changed its original call")
            expected_query = self._queries[reconciler] if reconciler else None
            if r.reconciler_binding_digest != expected_query:
                raise Conflict("reconciliation command changed its query contract")
            return previous
        saved = await run_blocking(RemoteCalls(self.store).get, caller, call_key)
        if saved is None:
            raise ValueError(
                "original remote call mapping is missing; do not reconstruct or invoke"
            )
        if saved.invocation_context is not None and (
            invocation_id is None
            or saved.invocation_context != fingerprint([self.store.owner, caller, invocation_id])
        ):
            raise ValueError("reconciliation must retain the original parent invocation")
        original = (
            await run_blocking(InvocationStore(self.store).get, caller, invocation_id)
            if invocation_id is not None
            else None
        )
        if invocation_id is not None and original is None:
            raise ValueError("original local invocation is missing")
        binding = self.registry.inspect(saved.binding_id)
        if binding.digest != saved.binding_digest:
            raise ValueError("original local binding is not installed; explicit recovery required")
        started = time.perf_counter()
        response: dict[str, Any] | None = None
        try:
            response = await self.registry.query_remote_call(
                call_key,
                ExecutionContext(caller=caller, environment=self.config.execution_environment),
                self.config,
                self.identity,
            )
            reason = self._validate(saved, caller, response)
        except Exception:
            reason = "PROVIDER_QUERY_UNAVAILABLE"
        valid = reason.startswith("PROVIDER_REPORTED_")
        query_digest = None
        effect: Literal["confirmed", "absent", "unknown"] = "unknown"
        observation_digest = None
        if reconciler is not None:
            query_digest = self._queries[reconciler]
            installed = self.registry.inspect(reconciler)
            if installed.digest != query_digest or installed.effects != "read-only":
                raise ValueError("reconciler binding changed")
            # Only a positively matched original request reaches an effect query.
            if valid:
                try:
                    observation = EffectObservation.model_validate(
                        await self.registry.execute(
                            reconciler,
                            query_digest,
                            {"call": saved.model_dump(mode="json"), "provider_report": response},
                            ExecutionContext(
                                caller=caller,
                                purpose="verification",
                                environment=self.config.execution_environment,
                                permissions=frozenset(self.config.policy.permissions),
                            ),
                            call_id=command_id,
                            call_scope="reconciliation/" + call_key,
                        )
                    )
                    if (
                        observation.provider_invocation_id != saved.remote_invocation_id
                        or observation.provider_binding_digest != saved.provider_binding_digest
                        or observation.arguments_digest != saved.arguments_digest
                    ):
                        reason = "EFFECT_OBSERVATION_MISMATCH"
                    else:
                        effect = observation.effect
                        observation_digest = observation.observation_digest
                        reason = observation.reason
                except Exception:
                    reason = "EFFECT_QUERY_UNAVAILABLE"
        receipt = ReconciliationReceipt(
            caller=caller,
            call_key=call_key,
            provider=saved.provider,
            provider_invocation_id=saved.remote_invocation_id,
            local_binding_digest=saved.binding_digest,
            provider_binding_digest=saved.provider_binding_digest,
            request_fingerprint=saved.request_fingerprint,
            arguments_digest=saved.arguments_digest,
            provider_request_fingerprint=response.get("fingerprint")
            if valid and response
            else None,
            provider_result_digest=response.get("result_digest") if valid and response else None,
            original_invocation_id=invocation_id,
            original_receipt=ReceiptRef(issuer=caller, id=original["receipt_id"])
            if original and original["receipt_id"]
            else None,
            reported_state=response["state"]
            if valid and response
            else ("absent" if reason == "PROVIDER_RESULT_ABSENT" else "unknown"),
            effect=effect,
            reason=reason,
            query_response_digest=fingerprint(response) if response is not None else None,
            effect_observation_digest=observation_digest,
            reconciler_binding_digest=query_digest,
        )
        event = Event(
            schema_version="4",
            id=event_id,
            issuer=caller,
            subject=binding.subject,
            action="recommendation",
            task_id=invocation_id or saved.call_id,
            attempt_id=command_id,
            correlation_id=call_key,
            causation_id=original["receipt_id"] if original else None,
            reconciliation=receipt,
            costs=(
                Cost(
                    category="observation",
                    status="measured",
                    quantity=Decimal(str(round(time.perf_counter() - started, 9))),
                    unit="wall_seconds",
                ),
            ),
        )
        await run_blocking(self.store.put, self.identity.sign(event))
        return event
