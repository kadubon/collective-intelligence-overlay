"""Compatibility reference application; generic peers have no CSV dispatch logic."""

import contextlib
import json
import time
from decimal import Decimal
from typing import Any, Literal

from .artifacts import Artifacts
from .bindings import Binding, ExecutionContext, Target, fingerprint
from .config import Config
from .models import Capability, Cost, Event, Subject, UseRequest, Verdict
from .peer import PeerService
from .queries import RecordQuery
from .reference import capability, check, csv_sum
from .reference_bindings import check_registered, csv_scope, register_reference
from .storage import Conflict


class ReferencePeerService(PeerService):
    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self.artifacts = Artifacts(config.artifact_directory)
        self.reference_cache: dict[str, Any] = {}
        self.registered = register_reference(
            self.registry,
            "verifier",
            callers=tuple(dict.fromkeys((config.owner, "verifier", "receiver"))),
            owner_probes=True,
        )
        self.imported: dict[str, tuple[Binding, Capability]] = {}

    async def handle(self, caller: str, data: dict[str, Any]) -> dict[str, Any]:
        if data.get("operation") == "reference-import":
            if caller != self.config.owner:
                raise ValueError("reference import is owner-only")
            source = Binding.model_validate(data["binding"])
            page = self.overlay.store.record_page(
                RecordQuery(
                    kinds=("capability",),
                    issuer=source.issuer,
                    subject=source.subject,
                )
            )
            if len(page.items) != 1 or not isinstance(page.items[0], Capability):
                raise ValueError("synchronize the source capability before importing")
            original = page.items[0]
            if original.binding_digest != source.digest:
                raise ValueError("source binding mismatch")
            peer = next(p for p in self.config.peers if p.identity == source.issuer)
            subject = Subject(
                id=f"{self.config.owner}/remote-{source.id}",
                version="1",
                digest=fingerprint([peer.identity, source.digest]),
            )
            binding = Binding.model_validate(
                {
                    **source.model_dump(),
                    "id": "remote-" + source.id,
                    "issuer": self.config.owner,
                    "registrar": self.config.owner,
                    "subject": subject,
                    "components": (),
                    "callers": (self.config.owner, "verifier"),
                    "verification_callers": ("verifier",),
                    "target": Target(
                        kind="a2a",
                        name=source.id,
                        peer=peer.identity,
                        endpoint=peer.url,
                        interface_digest=source.digest,
                        implementation_identity="remote-unknown",
                    ),
                }
            )
            candidate = Capability.model_validate(
                {
                    **original.model_dump(),
                    "issuer": self.config.owner,
                    "subject": subject,
                    "binding_digest": binding.digest,
                    "dependencies": (original.subject,),
                    "dependency_issuers": (original.issuer,),
                    "classification": "imported",
                    "provenance": "configured reference A2A service; no code transfer",
                }
            )
            if binding.id not in self.imported:
                self.registry.register_a2a(
                    binding,
                    csv_scope if original.entrypoint != "render-report" else lambda _: True,
                    self.config,
                    self.identity,
                )
                self.overlay.store.put(self.identity.sign(candidate))
                self.imported[binding.id] = binding, candidate
            elif self.imported[binding.id][0].digest != binding.digest:
                raise ValueError("import binding changed; explicit operator revision required")
            return {
                "binding": binding.model_dump(mode="json"),
                "capability": candidate.model_dump(mode="json"),
            }
        if data.get("operation") == "reference-register":
            if caller != self.config.owner:
                raise ValueError("reference registration is owner-only")
            candidates = []
            for binding, proposed in self.registered:
                page = self.overlay.store.record_page(
                    RecordQuery(
                        kinds=("capability",),
                        issuer=proposed.issuer,
                        subject=proposed.subject,
                    )
                )
                if page.items:
                    candidate = Capability.model_validate(page.items[0].model_dump())
                    if candidate.binding_digest != binding.digest:
                        raise ValueError("persisted reference binding differs from installed code")
                else:
                    candidate = proposed
                    self.overlay.store.put(self.identity.sign(candidate))
                candidates.append(
                    {
                        "binding": binding.model_dump(mode="json"),
                        "capability": candidate.model_dump(mode="json"),
                    }
                )
            return {"registrations": candidates}
        if data.get("operation") == "work":
            if caller != self.config.owner:
                raise ValueError("reference work is owner-only")
            return await self.work(data)
        return await super().handle(caller, data)

    async def work(self, data: dict[str, Any]) -> dict[str, Any]:
        """Finite single-attempt reference work with local budget and persistent fencing."""
        if data["mode"] == "reuse" and data["request"].get("binding_digest"):
            request = UseRequest.model_validate(data["request"])
            pairs = (*self.registered, *self.imported.values())
            registered_matches = [
                (b, c)
                for b, c in pairs
                if c.subject == request.subject
                and c.issuer == request.capability_issuer
                and b.digest == request.binding_digest
                and b.scope == request.scope
            ]
            if len(registered_matches) != 1:
                raise ValueError("missing or ambiguous installed reference binding")
            binding, selected_cap = registered_matches[0]
            arguments = (
                {"summary": json.loads(data["source"])}
                if selected_cap.entrypoint == "render-report"
                else {"source": data["source"]}
            )
            result = await self.executor.invoke(
                str(data["attempt"]),
                binding.id,
                binding.digest,
                arguments,
                ExecutionContext(
                    caller=self.config.owner,
                    environment=self.config.execution_environment,
                    permissions=frozenset(self.config.policy.permissions),
                ),
            )
            if result["state"] != "completed":
                raise ValueError("reference invocation incomplete; inspect its saved state")
            return {"result": result["result"], "invocation": result}
        attempt = str(data["attempt"])
        fence = self.overlay.store.acquire(
            attempt, self.config.owner, "work", Decimal(1), seconds=60
        )
        started = time.perf_counter()
        cap: Capability | None = None
        pending: list[dict[str, Any]] = []
        action: Literal["verification", "reuse"]
        try:
            mode = data["mode"]
            source = str(data.get("source", ""))
            if mode in {"scratch", "scratch_checked"}:
                # Explicit benchmark baseline: no overlay admission or shared evidence.
                from .reference import verify_csv

                cap = capability(self.config.owner, "csv-sum")
                if mode == "scratch_checked" and source in self.reference_cache:
                    result = self.reference_cache[source]
                else:
                    result = csv_sum(source)
                if mode == "scratch_checked":
                    if not verify_csv(source, result):
                        raise ValueError("baseline quality check failed")
                    if len(self.reference_cache) < 64:
                        self.reference_cache[source] = result
                response = {
                    "result": result,
                    "capability": cap.model_dump(mode="json"),
                    "quality_checked": mode == "scratch_checked",
                }
                action = "reuse"
            elif mode in {"verify", "verify-registered"}:
                cap = Capability.model_validate(data["capability"])
                self.artifacts.put(json.dumps(data["result"]).encode())
                evidence = (
                    check_registered(
                        self.config.owner,
                        cap,
                        Binding.model_validate(data["binding"]),
                        source,
                        data["result"],
                        str(data["receiver"]),
                    )
                    if mode == "verify-registered"
                    else check(
                        self.config.owner, cap, source, data["result"], str(data["receiver"])
                    )
                )
                envelope = self.identity.sign(evidence)
                pending.append(envelope)
                response = {"evidence": evidence.model_dump(mode="json"), "envelope": envelope}
                action = "verification"
            else:
                raise ValueError("unknown reference work mode")
            elapsed = Decimal(str(round(time.perf_counter() - started, 9)))
            artifact_digest = self.artifacts.put(json.dumps(response, ensure_ascii=False).encode())
            event = Event(
                issuer=self.config.owner,
                subject=cap.subject,
                action=action,
                task_id=attempt,
                attempt_id=attempt,
                correlation_id=str(data.get("correlation", attempt)),
                costs=(
                    Cost(
                        category="verification"
                        if mode in {"verify", "verify-registered"}
                        else "use",
                        status="measured",
                        quantity=elapsed,
                        unit="wall_seconds",
                    ),
                    Cost(category="overhead", status="unavailable", quantity=None, unit="USD"),
                ),
                duration_seconds=float(elapsed),
            )
            pending.append(self.identity.sign(event))
            self.overlay.store.commit_work(attempt, self.config.owner, fence, pending)
            return {**response, "artifact_digest": artifact_digest}
        except BaseException:
            # Preserve uncertain costs. Stale workers cannot add accepted results.
            with contextlib.suppress(Conflict):
                if cap is not None:
                    failure = Event(
                        issuer=self.config.owner,
                        subject=cap.subject,
                        action="failure",
                        task_id=attempt,
                        attempt_id=attempt,
                        correlation_id=attempt,
                        outcome=Verdict.UNKNOWN,
                        costs=(
                            Cost(
                                category="failure",
                                status="measured",
                                quantity=Decimal(str(round(time.perf_counter() - started, 9))),
                                unit="wall_seconds",
                            ),
                        ),
                    )
                    self.overlay.store.commit_work(
                        attempt,
                        self.config.owner,
                        fence,
                        [self.identity.sign(failure)],
                        cancelled=True,
                    )
                else:
                    self.overlay.store.finish(attempt, self.config.owner, fence, cancelled=True)
            raise
