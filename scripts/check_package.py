"""Check exact publish artifacts and install their wheel outside the repository."""

import argparse
import hashlib
import json
import os
import subprocess
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--dist-dir", type=Path, default=root / "dist")
args = parser.parse_args()
distribution = args.dist_dir.resolve()
expected_version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
wheels = list(distribution.glob("*.whl"))
sdists = list(distribution.glob("*.tar.gz"))
assert len(wheels) == len(sdists) == 1, "dist must contain one release version"
wheel, sdist = wheels[0], sdists[0]
with zipfile.ZipFile(wheel) as archive:
    members = archive.namelist()
    for ending in (
        "policy.rego",
        "schemas/capability.json",
        "py.typed",
        "licenses/LICENSE",
        "licenses/NOTICE",
        "migrations/versions/0008_dependency_refs.py",
        "migrations/versions/0009_invocation_allowance.py",
        "schemas/event.json",
        "schemas/evidence.json",
    ):
        assert any(n.endswith(ending) for n in members), ending
with tempfile.TemporaryDirectory(prefix="cio-package-") as directory:
    temp = Path(directory)
    env = temp / "venv"
    subprocess.run(["uv", "venv", "--python", "3.12", str(env)], check=True)
    python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run(["uv", "pip", "install", "--python", str(python), str(wheel)], check=True)
    subprocess.run(
        [str(python), "-m", "collective_intelligence_overlay.cli", "--version"],
        cwd=temp,
        check=True,
    )
    subprocess.run(
        [
            str(python),
            "-c",
            "from collective_intelligence_overlay.models import Scope; "
            "s=Scope(task='test',input_contract='in',output_contract='out',environment={}); "
            "assert Scope.model_validate_json(s.model_dump_json()) == s; "
            "import sys; assert 'agent_framework' not in sys.modules; "
            "assert 'mcp' not in sys.modules",
        ],
        cwd=temp,
        check=True,
    )
    subprocess.run(
        [
            str(python),
            "-c",
            "import importlib.metadata as m,sys; from pathlib import Path; "
            "import collective_intelligence_overlay as c; "
            f"assert m.version('collective-intelligence-overlay') == {expected_version!r}; "
            "assert Path(c.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()); "
            "from collective_intelligence_overlay.queries import RecordQuery; "
            "assert RecordQuery(kinds=('capability',)).depends_on is None",
        ],
        cwd=temp,
        check=True,
    )
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            str(wheel) + "[agents]",
            "pytest>=9,<10",
            "pytest-asyncio>=1,<2",
            "hypothesis>=6,<7",
        ],
        check=True,
    )
    tests = root / "tests" if os.environ.get("CIO_TEST_DATABASE_URL") else root / "tests/unit"
    subprocess.run(
        [
            str(python),
            "-m",
            "pytest",
            str(tests),
            "--rootdir",
            str(temp),
            "-q",
            "--ignore",
            str(root / "tests/integration/test_model_adapter.py"),
        ],
        cwd=temp,
        check=True,
    )
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), str(wheel) + "[model]"], check=True
    )
    subprocess.run(
        [
            str(python),
            "-m",
            "pytest",
            str(root / "tests/integration/test_model_adapter.py"),
            "--rootdir",
            str(temp),
            "-q",
        ],
        cwd=temp,
        check=True,
    )
    with tarfile.open(sdist) as archive:
        archive.extractall(temp / "source", filter="data")
    source = next((temp / "source").iterdir())
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(temp / "rebuilt"), str(source)],
        cwd=temp,
        check=True,
    )
    rebuilt = next((temp / "rebuilt").glob("*.whl"))
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--reinstall-package",
            "collective-intelligence-overlay",
            str(rebuilt),
        ],
        check=True,
    )
    subprocess.run(
        [str(python), "-m", "collective_intelligence_overlay.cli", "--version"],
        cwd=temp,
        check=True,
    )
print(
    json.dumps(
        {
            "verified_version": expected_version,
            "artifacts": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (wheel, sdist)
            },
            "checks": (
                "core + agents wheel outside checkout, model adapter, sdist rebuild/install"
            ),
        },
        indent=2,
    )
)
