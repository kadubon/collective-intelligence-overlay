"""Peer service binds configured runtime resources to the public overlay API."""

import contextlib
import json
import time
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import select

from .accounting import metrics
from .artifacts import Artifacts
from .config import Config
from .models import Capability, Cost, Event, Revocation, Subject, UseRequest, Verdict, uid
from .reference import capability, check, compose_report, csv_sum, render_report
from .security import verify
from .storage import Conflict, records


class PeerService:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.identity, self.overlay = config.runtime()
        self.artifacts = Artifacts(config.artifact_directory)

    async def handle(self, caller: str, data: dict[str, Any]) -> dict[str, Any]:
        operation = data.get("operation")
        started = time.perf_counter()
        if operation == "discover":
            # Explicitly configured peers may read this peer's shared record set.
            if not self.config.share_records or caller not in {
                p.identity for p in self.config.peers
            }:
                raise ValueError("peer not authorized for evidence exchange")
            with self.overlay.store.engine.connect() as conn:
                result: list[dict[str, Any]] = list(
                    conn.execute(
                        select(records.c.envelope)
                        .where(records.c.issuer == self.config.owner)
                        .limit(257)
                    ).scalars()
                )
            if len(result) > 256:
                raise ValueError("discovery limit exceeded")
            return {"envelopes": result}
        if operation == "submit":
            record = verify(data["envelope"], self.overlay.store.principals)
            if record.issuer != caller:
                raise ValueError("issuer must match authenticated submitting peer")
            return {"inserted": self.overlay.store.put(data["envelope"])}
        if caller != self.config.owner:
            raise ValueError("owner operation; delegation is not configured")
        if operation == "sync":
            from .adapters.a2a import send

            peer = str(data["peer"])
            response = await send(self.config, self.identity, peer, {"operation": "discover"})
            envelopes = response.get("envelopes")
            if not isinstance(envelopes, list) or len(envelopes) > 256:
                raise ValueError("invalid discovery result")
            for envelope in envelopes:
                self.overlay.store.put(envelope)
            self.overlay.observed(peer)
            if envelopes:
                subject = verify(envelopes[0], self.overlay.store.principals).subject
                self.record_event(subject, "import", "transfer", started)
            return {"received": len(envelopes)}
        if operation == "qualify":
            decision = await self.overlay.qualify(UseRequest.model_validate(data["request"]))
            self.record_event(
                decision.request.subject, "admission", "overhead", started, decision.outcome
            )
            return {
                "decision": decision.model_dump(mode="json"),
                "next_work": self.overlay.recommend(decision),
            }
        if operation == "metrics":
            return metrics(self.overlay.store.events())
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
        if operation == "work":
            return await self.work(data)
        raise ValueError("unknown operation")

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
                        unit="seconds",
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
                                unit="seconds",
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
                        "unit": "seconds",
                    }
                ],
            }
        )
        self.overlay.store.put(self.identity.sign(event))

    @staticmethod
    async def _run(name: str, source: str) -> Any:
        if name == "csv-sum":
            return csv_sum(source)
        if name == "render-report":
            return render_report(json.loads(source))
        if name == "csv-report":
            return await compose_report(source)
        raise ValueError("unregistered reference capability")
