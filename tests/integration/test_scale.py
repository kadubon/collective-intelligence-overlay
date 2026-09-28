"""Real-service mixed-history profile; select 100000 with CIO_SCALE_COUNTS.

Reports contain observations, not latency SLOs or whole-process memory claims.
Setup uses bounded transactions and verifies every signed record before insertion.
"""

import asyncio
import json
import os
import platform
import subprocess
import time
import tracemalloc
from collections import Counter
from pathlib import Path

import pytest
from sqlalchemy import event, func, select, text

from collective_intelligence_overlay.models import (
    Cost,
    Event,
    Revocation,
    Subject,
    UseRequest,
    Verdict,
)
from collective_intelligence_overlay.security import verify
from collective_intelligence_overlay.storage import records as record_table

COUNTS = tuple(int(value) for value in os.environ.get("CIO_SCALE_COUNTS", "1000,10000").split(","))
if not COUNTS or any(value not in (1000, 10000, 100000) for value in COUNTS):
    raise ValueError("CIO_SCALE_COUNTS must select 1000,10000,100000")


@pytest.mark.parametrize("total", COUNTS)
async def test_mixed_history_scale(total, overlay, identities, records, monkeypatch):
    import collective_intelligence_overlay.storage as storage

    cap, evidence = records
    store = overlay.store
    # Existing root capability + PASS, plus one independently checked dependency.
    child = cap.model_copy(
        update={"subject": Subject(id="scale-child", version="1", digest="c" * 64)}
    )
    root = cap.model_copy(
        update={
            "subject": Subject(id="scale-root", version="1", digest="d" * 64),
            "dependencies": (child.subject,),
        }
    )
    for index, candidate in enumerate((child, root)):
        store.put(identities[candidate.issuer].sign(candidate))
        checked = evidence.model_copy(
            update={"id": f"target-{index}", "subject": candidate.subject}
        )
        store.put(identities[checked.issuer].sign(checked))

    setup_start = time.perf_counter()
    pending = []
    inserted = 6
    outcomes = Counter()
    for index in range((total - 6 + 3) // 4):
        subject = Subject(id=f"history-{index}", version="1", digest=f"{index:064x}")
        candidate = cap.model_copy(update={"subject": subject})
        verdict = (Verdict.PASS, Verdict.FAIL, Verdict.UNKNOWN)[index % 3]
        checked = evidence.model_copy(
            update={"id": f"evidence-{index}", "subject": subject, "verdict": verdict}
        )
        withdrawal = Revocation(
            issuer="verifier", subject=subject, evidence_id=checked.id, reason="checker superseded"
        )
        observation = Event(
            issuer="receiver",
            subject=subject,
            action="verification",
            task_id=f"history-{index}",
            attempt_id="1",
            correlation_id=f"history-{index}",
            outcome=verdict,
            costs=(Cost(category="verification", status="unavailable", quantity=None, unit="USD"),),
        )
        for record in (candidate, checked, withdrawal, observation):
            if inserted >= total:
                break
            envelope = identities[record.issuer].sign(record)
            pending.append((verify(envelope, store.principals), envelope))
            inserted += 1
            if record.kind == "evidence":
                outcomes[record.verdict] += 1
        if len(pending) >= 100 or index == (total - 6 + 3) // 4 - 1:
            with store.engine.begin() as conn:
                for record, envelope in pending:
                    store._insert(conn, record, envelope)
            pending.clear()
    setup_seconds = time.perf_counter() - setup_start
    with store.engine.begin() as conn:
        conn.execute(text("ANALYZE records"))
        conn.execute(text("ANALYZE subject_revisions"))
        counts = dict(
            conn.execute(
                select(record_table.c.kind, func.count()).group_by(record_table.c.kind)
            ).all()
        )
        database_version = conn.execute(text("SELECT version()")).scalar_one()
    assert sum(counts.values()) == total
    assert set(counts) == {"capability", "evidence", "revocation", "event"}
    assert set(outcomes) == {"PASS", "FAIL", "UNKNOWN"}
    # This direct local-Store fixture has no network synchronization. Establish
    # its trusted-host observations after bulk setup, not before a long stress
    # load. Production persistent_sources peers still require completed sync.
    for issuer in ("producer", "verifier"):
        overlay.observed(issuer)

    statements = []
    query_rows = []
    signature_bytes = []
    opa_seconds = []
    original_verify = storage.verify
    original_decide = overlay.policy.decide

    def measured_verify(envelope, principals):
        signature_bytes.append(len(json.dumps(envelope, separators=(",", ":")).encode()))
        return original_verify(envelope, principals)

    async def measured_decide(facts):
        started = time.perf_counter()
        result = await original_decide(facts)
        opa_seconds.append(time.perf_counter() - started)
        return result

    def after_query(conn, cursor, statement, parameters, context, executemany):
        statements.append((statement, parameters))
        if statement.lstrip().upper().startswith("SELECT"):
            query_rows.append(max(0, cursor.rowcount))

    monkeypatch.setattr(storage, "verify", measured_verify)
    monkeypatch.setattr(overlay.policy, "decide", measured_decide)
    event.listen(store.engine, "after_cursor_execute", after_query)
    measurements = []
    request = UseRequest(
        receiver="receiver",
        subject=root.subject,
        capability_issuer="producer",
        scope=root.scope,
        semantic_fit="confirmed",
    )
    try:
        for _ in range(5):
            statements.clear()
            query_rows.clear()
            signature_bytes.clear()
            opa_seconds.clear()
            tracemalloc.start()
            started = time.perf_counter()
            decision = await overlay.qualify(request)
            elapsed = time.perf_counter() - started
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            assert decision.outcome == "ACCEPT", decision.model_dump(mode="json")
            assert len(signature_bytes) == 4
            assert len(statements) <= 16
            assert sum(query_rows) <= 20
            measurements.append(
                {
                    "latency_seconds": elapsed,
                    "opa_calls_seconds": list(opa_seconds),
                    "db_statements": len(statements),
                    "select_returned_rows": sum(query_rows),
                    "verified_signatures": len(signature_bytes),
                    "envelope_json_bytes": sum(signature_bytes),
                    "python_traced_peak_bytes": peak,
                }
            )
    finally:
        event.remove(store.engine, "after_cursor_execute", after_query)
        if tracemalloc.is_tracing():
            tracemalloc.stop()
    plans = []
    with store.engine.connect() as conn:
        for statement, parameters in statements:
            if statement.startswith("SELECT records.envelope"):
                plan = conn.exec_driver_sql(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, parameters
                ).scalar_one()
                plans.append(plan)
    assert plans
    report = {
        "profile_records": total,
        "counts": counts,
        "unrelated_evidence_verdicts": outcomes,
        "target_dependency_edges": 1,
        "target_capabilities": 2,
        "setup_seconds": setup_seconds,
        "measurements": measurements,
        "query_plans": plans,
        "conditions": {
            "python": platform.python_version(),
            "os": platform.platform(),
            "cpu": platform.processor(),
            "logical_cpu_count": os.cpu_count(),
            "postgresql": database_version,
            "opa": await asyncio.to_thread(
                subprocess.check_output, [overlay.policy.binary, "version"], text=True
            ),
            "memory": "tracemalloc during qualification only; excludes PostgreSQL/OPA/native heaps",
            "bytes": "verified envelope JSON bytes, excludes DB wire framing and A2A transport",
            "timing": "five sequential warmed-process calls, tracing enabled; no latency SLO",
        },
    }
    directory = os.environ.get("CIO_SCALE_REPORT_DIR")
    if directory:
        output = Path(directory)
        await asyncio.to_thread(output.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(
            (output / f"scale-{total}.json").write_text,
            json.dumps(report, indent=2),
            encoding="utf-8",
        )
