"""Compatibility reference application; generic peers have no CSV dispatch logic."""

import contextlib
import json
import time
from decimal import Decimal
from typing import Any, Literal

from .artifacts import Artifacts
from .config import Config
from .models import Capability, Cost, Event, Subject, UseRequest, Verdict
from .peer import PeerService
from .reference import capability, check, compose_report, csv_sum, render_report
from .storage import Conflict


class ReferencePeerService(PeerService):
    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self.artifacts = Artifacts(config.artifact_directory)
        self.reference_cache: dict[str, Any] = {}

    async def handle(self, caller: str, data: dict[str, Any]) -> dict[str, Any]:
        if data.get("operation") == "work":
            if caller != self.config.owner:
                raise ValueError("reference work is owner-only")
            return await self.work(data)
        return await super().handle(caller, data)

    async def work(self, data: dict[str, Any]) -> dict[str, Any]:
        """Finite single-attempt reference work with local budget and persistent fencing."""
        attempt = str(data["attempt"])
        fence = self.overlay.store.acquire(
            attempt, self.config.owner, "work", Decimal(1), seconds=60
        )
        started = time.perf_counter()
        cap: Capability | None = None
        pending: list[dict[str, Any]] = []
        action: Literal["formation", "verification", "reuse", "composition"]
        try:
            mode = data["mode"]
            source = str(data.get("source", ""))
            if mode == "form":
                deps = tuple(Subject.model_validate(d) for d in data.get("dependencies", []))
                cap = capability(self.config.owner, str(data["name"]), deps)
                artifact = self.identity.sign(cap)
                pending.append(artifact)
                result = await self._run(cap.entrypoint, source)
                response = {
                    "capability": cap.model_dump(mode="json"),
                    "result": result,
                    "envelope": artifact,
                }
                action = "formation"
            elif mode in {"scratch", "scratch_checked"}:
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
            elif mode == "verify":
                cap = Capability.model_validate(data["capability"])
                self.artifacts.put(json.dumps(data["result"]).encode())
                evidence = check(
                    self.config.owner, cap, source, data["result"], str(data["receiver"])
                )
                envelope = self.identity.sign(evidence)
                pending.append(envelope)
                response = {"evidence": evidence.model_dump(mode="json"), "envelope": envelope}
                action = "verification"
            elif mode == "reuse":
                req = UseRequest.model_validate(data["request"])
                matches = [c for c in self.overlay.store.capabilities() if c.subject == req.subject]
                if len(matches) != 1:
                    raise ValueError("missing or ambiguous capability")
                cap = matches[0]

                async def operation() -> Any:
                    # Only preinstalled code is executable, and its digest must match.
                    expected = capability(cap.issuer, cap.entrypoint, cap.dependencies)
                    if expected.subject != cap.subject:
                        raise ValueError("unrecognized installed artifact")
                    return await self._run(cap.entrypoint, source)

                result = await self.overlay.execute(req, operation)
                response = {"result": result}
                action = "composition" if cap.dependencies else "reuse"
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
                        if mode == "verify"
                        else "formation"
                        if mode == "form"
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

    @staticmethod
    async def _run(name: str, source: str) -> Any:
        if name == "csv-sum":
            return csv_sum(source)
        if name == "render-report":
            return render_report(json.loads(source))
        if name == "csv-report":
            return await compose_report(source)
        raise ValueError("unregistered reference capability")
