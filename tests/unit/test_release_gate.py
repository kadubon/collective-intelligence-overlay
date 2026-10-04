"""Reject altered/missing native proof and untrusted successful-run lookalikes."""

import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def gate_module():
    path = Path(__file__).parents[2] / "scripts/release_gate.py"
    spec = importlib.util.spec_from_file_location("tested_release_gate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_declared_native_fault_profiles_are_bound_into_reuse(gate_module):
    record = gate_module.provenance()
    for name in (
        "docs/profiles/production-040.json",
        "docs/profiles/native-fault-041.json",
        "docs/profiles/native-fault-042.json",
        "docs/profiles/native-fault-043.json",
        "docs/profiles/native-fault-044.json",
        "docs/profiles/native-fault-050.json",
        "tests/e2e/document_fault_report.py",
        "tests/e2e/production_mesh.py",
        "examples/adaptive_documents.py",
    ):
        assert record["gates"][name] == gate_module.sha(gate_module.ROOT / name)


@pytest.mark.parametrize("change", [None, "missing", "bytes", "pins", "hash", "scope"])
def test_original_proof_and_pins_are_required(gate_module, tmp_path, monkeypatch, change):
    module = gate_module
    candidate, reports = tmp_path / "candidate", tmp_path / "reports"
    candidate.mkdir()
    reports.mkdir()
    report = reports / "original.json"
    report.write_text('{"passed":true}')
    original = {
        "validation_scope": "full",
        "source_commit": "a" * 40,
        "source_tree": "b" * 40,
        "gates": {"uv.lock": "c" * 64},
    }
    hashes = {"candidate.whl": "d" * 64}
    (candidate / "provenance.json").write_text(json.dumps(original))
    (candidate / "artifacts.json").write_text(json.dumps(hashes))
    gate = tmp_path / "gate.json"
    gate.write_text(
        json.dumps(
            {
                "status": "passed",
                "candidate_provenance": original,
                "artifacts": hashes,
                "run_id": "123",
                "report_files": {"original.json": module.sha(report)},
            }
        )
    )
    manifest = {
        "gate_sha256": module.sha(gate),
        "candidate_run_id": "123",
        "source_commit": original["source_commit"],
        "source_tree": original["source_tree"],
        "artifacts": hashes,
    }
    current = {"gates": dict(original["gates"])}
    monkeypatch.setattr(module, "provenance", lambda: current)
    if change == "missing":
        report.unlink()
    elif change == "bytes":
        report.write_text('{"passed":false}')
    elif change == "pins":
        current["gates"]["uv.lock"] = "e" * 64
    elif change == "hash":
        manifest["artifacts"] = {"candidate.whl": "e" * 64}
    elif change == "scope":
        original["validation_scope"] = "representative"
        (candidate / "provenance.json").write_text(json.dumps(original))
    if change is None:
        module.check_reuse(candidate, gate, manifest, reports)
    else:
        with pytest.raises(AssertionError):
            module.check_reuse(candidate, gate, manifest, reports)


@pytest.mark.parametrize("change", ["fork", "branch", "workflow", "failure", "missing-native"])
def test_success_without_trusted_complete_native_workflow_is_rejected(
    gate_module, monkeypatch, change
):
    module = gate_module
    run = {
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": "a" * 40,
        "head_repository": {"full_name": module.REPOSITORY},
        "path": module.WORKFLOW,
        "status": "completed",
        "conclusion": "success",
    }
    jobs = [{"name": "ready", "conclusion": "success"}, {"name": "mixed", "conclusion": "success"}]
    jobs += [{"name": f"linux ({i})", "conclusion": "success"} for i in range(12)]
    jobs += [{"name": f"cross ({i})", "conclusion": "success"} for i in range(4)]
    if change == "fork":
        run["head_repository"]["full_name"] = "other/fork"
    elif change == "branch":
        run["head_branch"] = "unreviewed"
    elif change == "workflow":
        run["path"] = "untrusted.yml"
    elif change == "failure":
        run["conclusion"] = "failure"
    else:
        jobs[3]["conclusion"] = "skipped"
    monkeypatch.setattr(module, "api", lambda suffix: {"jobs": jobs} if "/jobs?" in suffix else run)
    with pytest.raises(AssertionError):
        module.trusted_run("123", "a" * 40)
