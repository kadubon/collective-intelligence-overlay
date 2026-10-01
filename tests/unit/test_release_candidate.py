import hashlib
import importlib.util
import io
import json
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest


@pytest.fixture
def candidate_repository(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts/release_candidate.py"
    spec = importlib.util.spec_from_file_location("release_candidate", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "repository"
    root.mkdir()
    files = {
        "src/collective_intelligence_overlay/__init__.py": b"VERSION = '0.4.0'\n",
        "src/collective_intelligence_overlay/policy.rego": b"package cio\n",
        "README.md": b"Measured scope is recorded separately.\n",
        "LICENSE": b"test license\n",
        "NOTICE": b"test notice\n",
        "pyproject.toml": b"[project]\nversion = '0.4.0'\n",
    }
    for name, value in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)

    def commit():
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.test",
                "commit",
                "-m",
                "fixture",
            ],
            cwd=root,
            check=True,
            capture_output=True,
        )

    commit()
    module.ROOT = root
    candidate = tmp_path / "candidate"
    dist = candidate / "dist"
    dist.mkdir(parents=True)
    wheel, sdist = dist / "candidate.whl", dist / "candidate.tar.gz"
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, value in files.items():
            if name.startswith("src/"):
                archive.writestr(name[4:], value)
    with tarfile.open(sdist, "w:gz") as archive:
        for name, value in files.items():
            member = tarfile.TarInfo(
                "candidate/" + name + (".orig" if name == "pyproject.toml" else "")
            )
            member.size = len(value)
            archive.addfile(member, io.BytesIO(value))
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (wheel, sdist)}
    (candidate / "artifacts.json").write_text(json.dumps(hashes))
    return module, root, candidate, hashes, commit


@pytest.mark.parametrize("change", [None, "source", "added-file", "readme", "artifact", "manifest"])
def test_pretested_pair_requires_original_packaged_content(candidate_repository, change):
    module, root, candidate, hashes, commit = candidate_repository
    if change in {"source", "added-file", "readme"}:
        name = {
            "source": "src/collective_intelligence_overlay/__init__.py",
            "added-file": "src/collective_intelligence_overlay/new.py",
            "readme": "README.md",
        }[change]
        (root / name).write_bytes(b"changed tagged content\n")
        commit()
    elif change == "artifact":
        with (candidate / "dist/candidate.whl").open("ab") as stream:
            stream.write(b"unreviewed bytes")
    elif change == "manifest":
        hashes = {**hashes, "candidate.whl": "0" * 64}
    if change is None:
        assert module.check(candidate, hashes) == hashes
    else:
        with pytest.raises(AssertionError):
            module.check(candidate, hashes)
