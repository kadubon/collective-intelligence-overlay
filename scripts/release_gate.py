"""Retain hash-bound native CI evidence and authenticate its later reuse.

GitHub's trusted main workflow is the authority. JSON and checksums alone are
not an attestation; reuse also requires the successful original run and jobs.
"""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "kadubon/collective-intelligence-overlay"
WORKFLOW = ".github/workflows/workflow.yml"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def report_files(directory):
    # The ready job's fresh local proxy-build diagnostics are distinct from
    # the twelve retained native reports. The native source review is retained.
    return {
        p.relative_to(directory).as_posix(): sha(p)
        for p in directory.rglob("*")
        if p.is_file() and p.relative_to(directory).parts[0] != "proxy"
    }


def provenance():
    names = [
        WORKFLOW,
        "uv.lock",
        "scripts/runtime-matrix.json",
        "docs/profiles/production-040.json",
        "docs/profiles/native-fault-041.json",
        "docs/profiles/native-fault-042.json",
        "docs/profiles/native-fault-043.json",
        "docs/profiles/native-fault-044.json",
        "docs/profiles/native-fault-050.json",
    ]
    names.extend(
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "scripts").rglob("*")
        if p.is_file() and p.suffix in {".py", ".json", ".mod", ".sum"}
    )
    names.extend(
        p.relative_to(ROOT).as_posix()
        for directory in ("tests", "examples")
        for p in (ROOT / directory).rglob("*.py")
    )
    return {
        "repository": REPOSITORY,
        "workflow": WORKFLOW,
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_tree": subprocess.check_output(
            ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
        ).strip(),
        "validation_scope": os.environ.get("CIO_VALIDATION_SCOPE", "local"),
        "toolchain": {"uv": "0.12.19", "go": "1.27.1"},
        "gates": {name: sha(ROOT / name) for name in sorted(set(names))},
    }


def api(suffix):
    assert os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
    request = Request(
        "https://api.github.com/repos/" + REPOSITORY + suffix,
        headers={
            "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
            "Accept": "application/vnd.github+json",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def trusted_run(run_id, source_commit, *, full=True):
    assert isinstance(run_id, str) and run_id.isdigit()
    run = api("/actions/runs/" + run_id)
    assert run["event"] in {"push", "workflow_dispatch"} and run["head_branch"] == "main"
    assert run["head_repository"]["full_name"] == REPOSITORY
    assert run["path"] == WORKFLOW and run["head_sha"] == source_commit
    assert run["status"] == "completed" and run["conclusion"] == "success"
    jobs = []
    for page in range(1, 5):
        found = api(f"/actions/runs/{run_id}/jobs?per_page=100&page={page}")["jobs"]
        jobs.extend(found)
        if len(found) < 100:
            break
    assert any(j["name"] == "ready" and j["conclusion"] == "success" for j in jobs)
    if full:
        native = [j for j in jobs if j["name"].startswith(("linux (", "windows (", "macos ("))]
        assert len(native) == 12 and all(j["conclusion"] == "success" for j in native)
        assert any(j["name"] == "mixed" and j["conclusion"] == "success" for j in jobs)
        assert (
            sum(j["name"].startswith("cross (") and j["conclusion"] == "success" for j in jobs) == 4
        )
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", source_commit, "HEAD"], cwd=ROOT, check=True
    )
    return run


def check_reuse(candidate, gate, manifest, reports=None):
    assert sha(gate) == manifest["gate_sha256"]
    record = json.loads(gate.read_bytes())
    original = json.loads((candidate / "provenance.json").read_bytes())
    assert record["status"] == "passed" and record["candidate_provenance"] == original
    assert original["validation_scope"] == "full"
    assert original["source_commit"] == manifest["source_commit"]
    assert original["source_tree"] == manifest["source_tree"]
    assert original["gates"] == provenance()["gates"], "gate or dependency pins changed"
    hashes = json.loads((candidate / "artifacts.json").read_bytes())
    assert record["artifacts"] == manifest["artifacts"] == hashes
    assert record["run_id"] == manifest["candidate_run_id"]
    if reports is not None:
        actual = report_files(reports)
        assert actual == record["report_files"], "original native evidence changed or missing"
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("provenance", "attest", "reuse"))
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--reports", type=Path)
    parser.add_argument("--gate", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if args.mode == "provenance":
        path, value = args.candidate / "provenance.json", provenance()
    elif args.mode == "attest":
        assert os.environ["CIO_VALIDATION_SCOPE"] == "full"
        subprocess.run(
            [
                "uv",
                "run",
                "--frozen",
                "python",
                str(ROOT / "scripts/check_matrix.py"),
                "--candidate",
                str(args.candidate),
                "--reports",
                str(args.reports),
            ],
            cwd=ROOT,
            check=True,
        )
        path = args.gate
        value = {
            "status": "passed",
            "run_id": os.environ["GITHUB_RUN_ID"],
            "artifacts": json.loads((args.candidate / "artifacts.json").read_bytes()),
            "candidate_provenance": json.loads((args.candidate / "provenance.json").read_bytes()),
            "report_files": report_files(args.reports),
        }
    else:
        manifest = json.loads(args.manifest.read_bytes())
        trusted_run(manifest["candidate_run_id"], manifest["source_commit"])
        check_reuse(args.candidate, args.gate, manifest, args.reports)
        print("original trusted full-matrix evidence verified")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()
