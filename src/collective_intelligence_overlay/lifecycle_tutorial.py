"""One deterministic actual-service tutorial; no model or comparison experiment.

Creates fresh demonstration owner databases/keys under an explicit directory.
Registry/Executor/FormationSession, PostgreSQL and OPA perform the work. Retains
all records and closes owned Stores; launches no peer/model server.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from .bindings import ExecutionContext, Registry
from .demo import initialize
from .invocations import Executor, Reservation
from .lifecycle import (
    CapabilityIdentity,
    Coverage,
    HandoffRole,
    LifecycleSnapshot,
    assess_stock,
    build_handoff,
    inspect_lifecycle,
    observe_growth,
)
from .lifecycle_store import read_lifecycle_page
from .lineage import FormationSession
from .models import Cost, Event, Revocation, UseRequest
from .overlay import Overlay
from .policy import Policy, PolicySettings
from .reference_bindings import check_registered, register_reference
from .security import Identity
from .synchronization import Feed, FeedFilter, Receiver


def _sync_tutorial_source(identity: Identity, source: Overlay, destination: Overlay) -> None:
    """Commit a finite local signed feed using the existing synchronization API."""
    selection = FeedFilter()
    intake = Receiver(destination.store)
    intake.begin(identity.name, selection)
    feed = Feed(source.store, identity)
    cursor = None
    for _ in range(16):
        page = feed.page(destination.store.owner, selection, cursor=cursor)
        intake.apply(identity.name, selection, page)
        cursor = page.next_cursor
        if cursor is None:
            return
    raise RuntimeError("tutorial signed feed exceeded its finite page bound")


async def run_tutorial(directory: Path, database_url: str, opa: str) -> dict[str, Any]:
    configs = initialize(directory, database_url, opa, work_allowance=Decimal(50))
    runtimes = {name: config.runtime() for name, config in configs.items()}
    try:
        identity, overlay = runtimes["receiver"]
        verifier_identity, verifier = runtimes["verifier"]
        _, receiver_b = runtimes["producer"]
        receiver_b.policy = Policy(opa, PolicySettings(licenses=()))
        registry = Registry(overlay)
        sum_pair, render_pair, report_pair = register_reference(
            registry, "verifier", owner_probes=True
        )
        for _, candidate in (sum_pair, render_pair):
            envelope = identity.sign(candidate)
            overlay.store.put(envelope)
        runner = Executor(registry, identity, Reservation(seconds=30))
        source = "category,amount\na,2.00\nb,3.00\n"
        expected = {"rows": 2, "total": "5.00"}
        probe_context = ExecutionContext(
            caller="verifier", purpose="verification", environment={"reference": "1"}
        )
        for name, (binding, cap), arguments, checker_input in (
            ("sum", sum_pair, {"source": source}, source),
            ("render", render_pair, {"summary": expected}, json.dumps(expected)),
        ):
            observed = await runner.invoke(
                "tutorial-probe-" + name, binding.id, binding.digest, arguments, probe_context
            )
            if observed["state"] != "completed":
                raise RuntimeError("registered verification probe did not complete")
            evidence = check_registered(
                "verifier", cap, binding, checker_input, observed["result"], "receiver"
            )
            if evidence.verdict != "PASS":
                raise RuntimeError("independent deterministic checker failed")
            envelope = verifier_identity.sign(evidence)
            verifier.store.put(envelope)
        _sync_tutorial_source(verifier_identity, verifier, overlay)
        _sync_tutorial_source(identity, overlay, receiver_b)
        _sync_tutorial_source(verifier_identity, verifier, receiver_b)
        binding, cap = sum_pair
        request = UseRequest(
            receiver="receiver",
            subject=cap.subject,
            scope=cap.scope,
            capability_issuer=cap.issuer,
            binding_digest=cap.binding_digest,
            semantic_fit="confirmed",
        )
        opening = await assess_stock(overlay, (request,))
        b_decision = await receiver_b.qualify(request.model_copy(update={"receiver": "producer"}))
        if opening.entries[0].availability != "accepted" or b_decision.outcome == "ACCEPT":
            raise RuntimeError("tutorial receiver policy observations were unexpected")
        context = ExecutionContext(caller="receiver", environment={"reference": "1"})
        reused = await runner.invoke(
            "tutorial-actual-use", binding.id, binding.digest, {"source": source}, context
        )
        if reused["state"] != "completed" or reused["result"] != expected:
            raise RuntimeError("actual deterministic reuse failed")
        async with FormationSession(registry, identity) as formation:
            first = await runner.invoke(
                "tutorial-formation-sum", binding.id, binding.digest, {"source": source}, context
            )
            render_binding, _ = render_pair
            second = await runner.invoke(
                "tutorial-formation-render",
                render_binding.id,
                render_binding.digest,
                {"summary": first["result"]},
                context,
            )
            if first["state"] != "completed" or second["state"] != "completed":
                raise RuntimeError("formation inputs did not complete")
            formed_binding, formed_cap = report_pair
            formed = await formation.publish(formed_binding.id, formed_cap)
        unknown = Event(
            id="tutorial-unmeasured-cost",
            issuer="receiver",
            subject=cap.subject,
            action="recommendation",
            task_id="tutorial-cost",
            attempt_id="tutorial-cost",
            correlation_id="tutorial",
            costs=(
                Cost(category="maintenance", status="unavailable", quantity=None, unit="joules"),
            ),
        )
        overlay.store.put(identity.sign(unknown))
        withdrawal = Revocation(
            id="tutorial-withdrawal",
            issuer=cap.issuer,
            subject=cap.subject,
            reason="explicit tutorial owner withdrawal",
        )
        overlay.store.put(identity.sign(withdrawal))
        closing = await assess_stock(overlay, (request,))
        if closing.entries[0].availability != "nonaccepted":
            raise RuntimeError("withdrawn candidate was not refused")
        a_snapshot = read_lifecycle_page(overlay.store, caller="receiver")
        b_snapshot = read_lifecycle_page(
            receiver_b.store,
            CapabilityIdentity(
                issuer=cap.issuer, subject=cap.subject, binding_digest=cap.binding_digest
            ),
            caller="producer",
        )
        b_records = tuple(
            item for item in b_snapshot.records if item.source.reference.kind == "decision"
        )
        combined_context = a_snapshot.context.model_copy(
            update={
                "coverage": Coverage.PARTIAL,
                "feed_generation": None,
                "prefix": None,
                "coverage_basis": (
                    "Explicit authorized material from two owners; no atomic cross-owner snapshot."
                ),
                "record_cursor": None,
                "decision_cursor": None,
            }
        )
        combined = LifecycleSnapshot(
            context=combined_context, records=a_snapshot.records + b_records
        )
        exact = CapabilityIdentity(
            issuer=cap.issuer, subject=cap.subject, binding_digest=cap.binding_digest
        )
        lifecycle = inspect_lifecycle(combined, exact)
        formed_view = inspect_lifecycle(
            a_snapshot,
            CapabilityIdentity(
                issuer=formed_cap.issuer,
                subject=formed_cap.subject,
                binding_digest=formed_cap.binding_digest,
            ),
        )
        handoff = build_handoff(
            lifecycle,
            source_role=HandoffRole.REUSE,
            target_role=HandoffRole.ACCOUNT,
            producer="receiver",
            receiver="receiver",
            contract_identity="cio.lifecycle.view.v1",
        )
        growth = observe_growth(opening, closing)
        results = {
            "scenario": "deterministic actual-service tutorial; not a growth experiment",
            "new_model_generation_requests": 0,
            "receiver_A": opening.entries[0].decision.outcome,
            "receiver_B": b_decision.outcome,
            "actual_result": reused["result"],
            "formation_receipt": formed.id,
            "formation_functional_novelty": formed.formation.functional_novelty
            if formed.formation
            else None,
            "after_withdrawal": closing.entries[0].decision.outcome,
            "lifecycle": lifecycle.model_dump(mode="json"),
            "formed_lifecycle": formed_view.model_dump(mode="json"),
            "opening": opening.model_dump(mode="json"),
            "closing": closing.model_dump(mode="json"),
            "growth": growth.model_dump(mode="json"),
            "handoff": handoff.model_dump(mode="json"),
            "operational_note": (
                "Isolated owner roles/databases and originals retained; "
                "no peer/model process launched."
            ),
        }
        (directory / "lifecycle-results.json").write_text(
            json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return results
    finally:
        for _, host in runtimes.values():
            host.store.close()
