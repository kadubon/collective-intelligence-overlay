"""Check exact publish artifacts and install their wheel outside the repository."""

import os
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
wheels = list((root / "dist").glob("*.whl"))
sdists = list((root / "dist").glob("*.tar.gz"))
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
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            str(wheel) + "[agents,model]",
            "pytest>=9,<10",
            "pytest-asyncio>=1,<2",
            "hypothesis>=6,<7",
        ],
        check=True,
    )
    tests = root / "tests" if os.environ.get("CIO_TEST_DATABASE_URL") else root / "tests/unit"
    subprocess.run(
        [str(python), "-m", "pytest", str(tests), "--rootdir", str(temp), "-q"],
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
print("exact wheel inspected, clean core install checked, sdist rebuilt")
