"""Select a pretested release pair and reject changed packaged sources."""

import argparse
import hashlib
import json
import os
import subprocess
import tarfile
import tomllib
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/release-040.json"


def git_bytes(name):
    return subprocess.check_output(["git", "show", "HEAD:" + name], cwd=ROOT)


def check(candidate, expected=None):
    hashes = json.loads((candidate / "artifacts.json").read_text())
    assert len(hashes) == 2 and hashes == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (candidate / "dist").iterdir()
        if path.name.endswith((".whl", ".tar.gz"))
    }, "candidate pair changed"
    if expected is not None:
        assert hashes == expected, "release manifest differs from tested artifacts"
    wheel = next((candidate / "dist").glob("*.whl"))
    sdist = next((candidate / "dist").glob("*.tar.gz"))
    tracked = set(
        subprocess.check_output(["git", "ls-files", "src"], cwd=ROOT, text=True).splitlines()
    )
    seen = set()
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.startswith("collective_intelligence_overlay/") and not name.endswith("/"):
                source = "src/" + name
                assert archive.read(name) == git_bytes(source), source
                seen.add(source)
    assert seen == tracked, "wheel package file set differs from tagged sources"
    seen = set()
    with tarfile.open(sdist) as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            source = member.name.split("/", 1)[1]
            if source.startswith("src/") or source in {"README.md", "LICENSE", "NOTICE"}:
                assert archive.extractfile(member).read() == git_bytes(source), source
                seen.add(source)
            elif source == "pyproject.toml.orig":
                assert archive.extractfile(member).read() == git_bytes("pyproject.toml")
                seen.add("pyproject.toml")
    assert seen == tracked | {"README.md", "LICENSE", "NOTICE", "pyproject.toml"}
    return hashes


def select():
    ref = os.environ.get("GITHUB_REF", "")
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    selected = {"reuse_run_id": "", "production_run_id": ""}
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    if ref == "refs/tags/v0.4.0":
        assert version == "0.4.0" and MANIFEST.is_file(), "pretested release manifest required"
        manifest = json.loads(MANIFEST.read_text())
        run_id = manifest["candidate_run_id"]
        assert isinstance(run_id, str) and run_id.isdigit()
        repository = os.environ["GITHUB_REPOSITORY"]
        assert repository == "kadubon/collective-intelligence-overlay"
        request = Request(
            f"https://api.github.com/repos/{repository}/actions/runs/{run_id}",
            headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"]},
        )
        with urlopen(request, timeout=30) as response:
            run = json.load(response)
        assert run["event"] in {"push", "workflow_dispatch"} and run["head_branch"] == "main"
        assert run["head_repository"]["full_name"] == repository
        assert run["path"] == ".github/workflows/workflow.yml"
        assert run["head_sha"] == manifest["source_commit"]
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", run["head_sha"], "HEAD"], cwd=ROOT, check=True
        )
        selected.update(reuse_run_id=run_id, production_run_id=run_id)
    elif event == "workflow_dispatch":
        run_id = os.environ.get("CIO_CANDIDATE_RUN_ID", "")
        assert not run_id or run_id.isdigit()
        selected["reuse_run_id"] = run_id
        if run_id and version == "0.4.0" and os.environ.get("CIO_PRODUCTION_PROTOCOLS") != "true":
            selected["production_run_id"] = run_id
    return selected


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path)
    args = parser.parse_args()
    if args.candidate:
        expected = (
            json.loads(MANIFEST.read_text())["artifacts"]
            if os.environ.get("GITHUB_REF") == "refs/tags/v0.4.0"
            else None
        )
        print(
            json.dumps(
                {"packaged_sources_unchanged": True, "artifacts": check(args.candidate, expected)}
            )
        )
    else:
        selected = select()
        if output := os.environ.get("GITHUB_OUTPUT"):
            with Path(output).open("a") as stream:
                for name, value in selected.items():
                    stream.write(f"{name}={value}\n")
        print(json.dumps(selected))
