"""Real PG/OPA/TLS/A2A/Registry transfers; deterministic controls, no LLM claims."""

import json
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import update

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from datetime import timedelta

from accumulation_primitives import Solution  # noqa: E402
from accumulation_session import StudySession  # noqa: E402
from accumulation_stock import Skill, Snapshot, retrieve  # noqa: E402
from accumulation_tasks import World  # noqa: E402

from collective_intelligence_overlay.bindings import Binding  # noqa: E402
from collective_intelligence_overlay.models import now  # noqa: E402
from collective_intelligence_overlay.synchronization import checkpoints  # noqa: E402


@pytest.mark.parametrize("arm", ["E", "M", "C"])
@pytest.mark.parametrize("family", ["calibration", "sql"])
@pytest.mark.parametrize("receiver", ["receiver", "newreceiver"])
async def test_scratch_and_checked_local_reconstruction_survive_original_provider_absence(
    tmp_path, arm, family, receiver
):
    if not all(os.environ.get(k) for k in ("CIO_TEST_DATABASE_URL", "CIO_OPA", "CIO_CADDY")):
        pytest.skip("actual PG/OPA/native Caddy required")
    world = World(938125)
    p = (
        world.calibration("transfer-public-training", "middle")
        if family == "calibration"
        else (world.sales("transfer-public-training", "low"))
    )
    q = (
        world.calibration("transfer-unseen-receiver", "middle")
        if family == "calibration"
        else (world.sales("transfer-unseen-receiver", "low"))
    )
    solution = world.oracle(p)  # Only this deterministic positive control uses an oracle.
    checks = {
        "training": [{"problem": p.model_dump(mode="json"), "expected": world.expected(p)}],
        "new-receiver": [{"problem": q.model_dump(mode="json"), "expected": world.expected(q)}],
    }
    protocol = {
        "id": "test-only-not-real-inference",
        "sources": {},
        "new_receiver": receiver == "newreceiver",
        "caps": {
            "application_actions": 512,
            "model_calls": 2,
            "model_tokens": 20000,
            "wall_seconds": 300,
        },
    }
    model = {
        "host": "http://127.0.0.1:1",
        "seconds": 180,
        "options": {"num_ctx": 8192, "num_predict": 1536, "draft_num_predict": 0},
    }
    s = StudySession(tmp_path / "private", tmp_path / "raw", world, arm, protocol, model, checks)
    try:
        await s.initialize()
        if receiver == "newreceiver":
            await s.activate_receiver()
            _, overlay = s.session.configs["producer"].runtime()
            try:
                # Deliberate local freshness-projection fault; original signed
                # evidence is untouched. This is not a historical observation.
                with overlay.store.engine.begin() as connection:
                    connection.execute(
                        update(checkpoints)
                        .where(checkpoints.c.source == "verifier")
                        .values(anchor=now() - timedelta(seconds=601))
                    )
            finally:
                overlay.store.close()
            denied = await s.call(
                "producer",
                operation="app.construct",
                id="stale-source-control",
                problem=p.model_dump(mode="json"),
                solution=solution.model_dump(mode="json"),
                copied=False,
            )
            assert denied["state"] == "unformed", denied
            assert denied["construction"]["reason"] == "admission_denied"
            s.source_sync_seconds["producer", "verifier"] = 0
        result = await s.check_constructed(
            "producer", "training", p, solution, "test-source", copied=False
        )
        assert result["succeeded"], result
        if family == "sql":
            invalid = await s.check_constructed(
                "producer",
                "training",
                p,
                Solution(family="sql", sql="SELECT missing FROM orders"),
                "test-program-rejection",
                copied=False,
            )
            assert not invalid["succeeded"] and invalid["check"]["verdict"] == "FAIL"
        binding = Binding.model_validate(result["construction"]["binding"])
        evidence = result["check"].get("evidence")
        skill = Skill(
            id=binding.id,
            producer="producer",
            family=p.family,
            contract=p.contract,
            revision=p.revision,
            schema_digest=p.schema_digest,
            solution=solution,
            basic_passed=True,
            independent_verdict="PASS",
            episode=1,
            evidence_id=evidence["id"] if evidence else None,
            binding_digest=binding.digest,
            artifact_digest=binding.artifact_digest,
            source_binding=binding,
            source_problem=p,
            source_world=world.id,
        )
        # E can construct exactly the same executable with no inherited PASS.
        if arm == "E":
            copied = False
        else:
            s.stock = Snapshot(world=world.id, arm=arm, checkpoint=1, skills=(skill,))
            original = s.stock.digest
            await s.transfer(skill)
            if receiver == "newreceiver":
                await s.import_to(skill, receiver)
            assert s.stock.digest == original
            assert len(retrieve(s.stock, q, receiver, view="full")) == 1
            assert retrieve(s.stock, q, receiver, view="empty") == ()
            assert (
                result["construction"]["formation_event"] is not None
                if arm == "C"
                else (result["construction"]["formation_event"] is None)
            )
            # Original CAS bytes, not a cached answer, are authenticated on import.
            exported = await s.call("producer", operation="app.export", name=binding.id)
            tampered = json.loads(json.dumps(skill.model_dump(mode="json")))
            tampered["solution"]["coefficients"][0] += 99
            bad = await s.call(
                receiver,
                operation="app.import",
                skill=tampered,
                artifact_base64=exported["artifact_base64"],
            )
            assert bad.get("source_verified") is not True
            copied = True
        await s.session.stop("producer")
        if receiver == "newreceiver":
            await s.session.stop("receiver")
            assert s.session.processes["receiver"].poll() is not None
        assert s.session.processes["producer"].poll() is not None
        fresh = await s.check_constructed(
            receiver,
            "new-receiver",
            q,
            solution,
            "test-local-reconstruction",
            copied=copied,
            source_skill=skill if copied else None,
        )
        assert fresh["succeeded"], fresh
        assert not (s.output / "model").exists()
        if arm == "C":
            assert fresh["execution"]["purpose"] == "reuse"
        if arm != "E":
            assert s.stock.digest == original
    finally:
        exported = await s.finish()
        assert exported["export_errors"] == {}
