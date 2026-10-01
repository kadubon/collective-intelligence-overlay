"""Check identical candidates with normal resolution and observed child interpreters."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import xml.etree.ElementTree as ET
import zipfile
from email.parser import BytesParser
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--dist-dir", type=Path, default=root / "dist")
parser.add_argument(
    "--python", default=sys.executable, help="Exact interpreter or uv Python request"
)
parser.add_argument("--report", type=Path)
parser.add_argument("--hash-file", type=Path, help="Expected candidate filename/SHA-256 object")
parser.add_argument("--test-scope", choices=("auto", "unit", "full"), default="auto")
parser.add_argument("--supply-chain-dir", type=Path, help="Audit each actual installed profile")
parser.add_argument(
    "--from-pypi",
    action="store_true",
    help="Post-publication: cache-disabled PyPI install, including root vulnerability audit",
)
args = parser.parse_args()
project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
version = project["project"]["version"]
distribution = args.dist_dir.resolve()
wheels, sdists = list(distribution.glob("*.whl")), list(distribution.glob("*.tar.gz"))
assert len(wheels) == len(sdists) == 1, "dist must contain one candidate version"
wheel, sdist = wheels[0], sdists[0]
hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (wheel, sdist)}
if args.hash_file:
    assert json.loads(args.hash_file.read_text(encoding="utf-8")) == hashes, (
        "candidate hash mismatch"
    )


def check_metadata(data):
    metadata = BytesParser().parsebytes(data)
    assert metadata["Name"] == "collective-intelligence-overlay"
    assert metadata["Version"] == version
    assert metadata["Requires-Python"] == ">=3.12", metadata["Requires-Python"]


with zipfile.ZipFile(wheel) as archive:
    members = archive.namelist()
    check_metadata(archive.read(next(n for n in members if n.endswith(".dist-info/METADATA"))))
    for ending in (
        "policy.rego",
        "schemas/capability.json",
        "py.typed",
        "licenses/LICENSE",
        "licenses/NOTICE",
        "migrations/versions/0008_dependency_refs.py",
        "migrations/versions/0009_invocation_allowance.py",
        "migrations/versions/0010_work_selections.py",
        "migrations/versions/0011_invocation_capacity.py",
        "migrations/versions/0012_selection_window.py",
        "migrations/versions/0013_reobservation.py",
        "migrations/versions/0014_remote_calls.py",
        "migrations/versions/0015_invocation_cleanup.py",
        "migrations/versions/0016_reconciliation.py",
        "migrations/versions/0017_recovery_gate.py",
        "migrations/versions/0018_recovery_review.py",
        "migrations/versions/0019_sync_completion.py",
        "migrations/versions/0020_restore_sequence.py",
        "schemas/config.json",
        "starter/application.py",
        "starter/Caddyfile",
        "starter/README.txt",
        "starter/documents.py",
        "starter/adaptive_documents.py",
        "calls.py",
        "reobservation.py",
        "schemas/event.json",
        "schemas/evidence.json",
        "schemas/opportunity.json",
        "schemas/proposal.json",
        "schemas/binding.json",
        "schemas/artifactspec.json",
    ):
        assert any(n.endswith(ending) for n in members), ending
with tarfile.open(sdist) as archive:
    metadata_file = next(m for m in archive.getmembers() if m.name.endswith("/PKG-INFO"))
    check_metadata(archive.extractfile(metadata_file).read())

runtime_code = (
    "import sys,json,platform; "
    "print(json.dumps({'version':sys.version,'minor':list(sys.version_info[:2]),"
    "'executable':sys.executable,'prefix':sys.prefix,'os':platform.platform(),"
    "'architecture':platform.machine()}))"
)
selected = subprocess.check_output(["uv", "python", "find", args.python], text=True).strip()
requested = json.loads(subprocess.check_output([selected, "-c", runtime_code], text=True))
assert tuple(requested["minor"]) >= (3, 12), "Python >=3.12 required"
minor_request = re.match(r"^(?:cpython-)?(\d+)\.(\d+)(?:\.|$)", args.python)
if minor_request:
    assert requested["minor"] == [int(n) for n in minor_request.groups()], "Python request mismatch"
if re.fullmatch(r"\d+\.\d+\.\d+", args.python):
    assert requested["version"].split()[0] == args.python, "Python patch request mismatch"
full = args.test_scope == "full" or (
    args.test_scope == "auto" and bool(os.environ.get("CIO_TEST_DATABASE_URL"))
)
if full:
    assert os.environ.get("CIO_TEST_DATABASE_URL") and os.environ.get("CIO_OPA"), (
        "full artifact tests require real PostgreSQL and OPA"
    )
report = {
    "verified_version": version,
    "artifacts": hashes,
    "selected": requested,
    "test_scope": "full" if full else "unit",
    "installation_source": "cache-disabled-pypi-index" if args.from_pypi else "candidate-wheel",
    "environments": {},
}

# Test-only instrumentation, with no package/application source in PYTHONPATH.
# Record actual CLI, pytest, PEP-517 and demo child startup; fail a wrong runtime.
startup_guard = """import importlib.util, json, os, platform, sys
from pathlib import Path
if os.environ.get("CIO_PACKAGE_RUNTIME_DIR"):
    expected = json.loads(os.environ["CIO_PACKAGE_RUNTIME_MINOR"])
    executable = os.path.normcase(os.path.realpath(sys.executable))
    wanted = os.path.normcase(os.path.realpath(os.environ["CIO_PACKAGE_RUNTIME_EXE"]))
    if list(sys.version_info[:2]) != expected or executable != wanted:
        raise SystemExit("artifact child interpreter mismatch")
    spec = importlib.util.find_spec("collective_intelligence_overlay")
    origin = None if spec is None else spec.origin
    if origin is not None and not Path(origin).resolve().is_relative_to(Path(sys.prefix).resolve()):
        raise SystemExit("artifact import escaped site-packages")
    phase = os.environ.get("CIO_PACKAGE_RUNTIME_PHASE", "check")
    filename = phase + "-" + str(os.getpid()) + ".json"
    runtime_file = Path(os.environ["CIO_PACKAGE_RUNTIME_DIR"]) / filename
    runtime_file.write_text(
        json.dumps({"version":sys.version,"minor":list(sys.version_info[:2]),
                    "executable":sys.executable,"prefix":sys.prefix,"import":origin,
                    "argv":sys.argv,"phase":phase,"architecture":platform.machine()}),
        encoding="utf-8")
"""
smoke = (
    "import importlib.metadata as m,json,sys; from pathlib import Path; "
    "import collective_intelligence_overlay as c; "
    f"assert m.version('collective-intelligence-overlay') == {version!r}; "
    "assert Path(c.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()); "
    "from collective_intelligence_overlay.models import Scope; "
    "s=Scope(task='test',input_contract='in',output_contract='out',environment={}); "
    "assert Scope.model_validate_json(s.model_dump_json()) == s; "
    "from collective_intelligence_overlay.queries import RecordQuery; "
    "assert RecordQuery(kinds=('capability',)).depends_on is None; "
    "print(json.dumps({'import':c.__file__,'version':m.version('collective-intelligence-overlay')}))"
)


def run(command, *, cwd, environment=None):
    subprocess.run(command, cwd=cwd, env=environment, check=True)


def test(python, paths, name, *, temp, environment, ignore_model=False):
    result_path = temp / (name + ".xml")
    command = [
        str(python),
        "-m",
        "pytest",
        *(str(p) for p in paths),
        "--rootdir",
        str(temp),
        "-o",
        "asyncio_mode=auto",
        "-q",
        "-W",
        "error::pytest.PytestUnraisableExceptionWarning",
        "--junitxml",
        str(result_path),
    ]
    if ignore_model:
        command.extend(["--ignore", str(root / "tests/integration/test_model_adapter.py")])
    run(command, cwd=temp, environment=environment)
    totals = {
        key: sum(int(s.get(key, "0")) for s in ET.parse(result_path).iter("testsuite"))
        for key in ("tests", "failures", "errors", "skipped")
    }
    assert totals["tests"] > 0 and not any(totals[k] for k in ("failures", "errors", "skipped")), (
        totals
    )
    return totals


def supply_chain(python, name, packages, *, temp):
    output = args.supply_chain_dir.resolve() / name
    output.mkdir(parents=True, exist_ok=True)
    requirements = output / "resolved-dependencies.txt"
    # Before publication only the first-party root is absent from the index.
    # Post-publication also audit that root; always use actual observed versions.
    # These pip-audit flags do not alter or bypass any package installation.
    dependencies = [
        p for p in packages if args.from_pypi or p["name"] != "collective-intelligence-overlay"
    ]
    requirements.write_text(
        "".join(f"{p['name']}=={p['version']}\n" for p in dependencies), encoding="utf-8"
    )
    run(
        [
            sys.executable,
            "-m",
            "pip_audit",
            "--no-deps",
            "--disable-pip",
            "-r",
            str(requirements),
            "--progress-spinner",
            "off",
            "--format=json",
            "--output",
            str(output / "audit.json"),
        ],
        cwd=temp,
    )
    run(
        [
            sys.executable,
            "-m",
            "piplicenses",
            "--python",
            str(python),
            "--format=json",
            "--with-urls",
            "--output-file",
            str(output / "licenses.json"),
        ],
        cwd=temp,
    )
    run(
        [sys.executable, str(root / "scripts/check_licenses.py"), str(output / "licenses.json")],
        cwd=temp,
    )
    run(
        [
            sys.executable,
            "-m",
            "cyclonedx_py",
            "environment",
            str(python),
            "--output-file",
            str(output / "sbom.json"),
        ],
        cwd=temp,
    )
    return {
        "dependencies": len(dependencies),
        "directory": str(output),
        "candidate_root": (
            "audited published PyPI root"
            if args.from_pypi
            else "candidate root excluded; audit the published root with --from-pypi"
        ),
    }


with tempfile.TemporaryDirectory(prefix="cio-package-") as directory:
    temp = Path(directory)
    guard = temp / "runtime-guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(startup_guard, encoding="utf-8")
    for name, extras in (("core", ""), ("agents", "[agents]"), ("agents-model", "[agents,model]")):
        venv = temp / name
        run(["uv", "venv", "--python", selected, str(venv)], cwd=temp)
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        actual = json.loads(
            subprocess.check_output([str(python), "-c", runtime_code], text=True, cwd=temp)
        )
        assert actual["minor"] == requested["minor"], "venv interpreter fallback"
        records = temp / (name + "-runtimes")
        records.mkdir()
        environment = {
            **os.environ,
            "PYTHONPATH": str(guard),
            "CIO_PACKAGE_RUNTIME_DIR": str(records),
            "CIO_PACKAGE_RUNTIME_MINOR": json.dumps(requested["minor"]),
            "CIO_PACKAGE_RUNTIME_EXE": str(python),
        }
        if full and args.report:
            environment["CIO_PRODUCTION_FAULT_REPORT_DIR"] = str(
                args.report.resolve().parent / "installed-production-faults" / name
            )
        if args.from_pypi:
            index_environment = {
                key: value
                for key, value in os.environ.items()
                if key
                not in {
                    "UV_DEFAULT_INDEX",
                    "UV_INDEX",
                    "UV_INDEX_URL",
                    "UV_EXTRA_INDEX_URL",
                    "UV_FIND_LINKS",
                    "UV_OFFLINE",
                }
            }
            run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    "--no-cache",
                    "--no-config",
                    "--default-index",
                    "https://pypi.org/simple",
                    f"collective-intelligence-overlay{extras}=={version}",
                ],
                cwd=temp,
                environment=index_environment,
            )
        else:
            run(["uv", "pip", "install", "--python", str(python), str(wheel) + extras], cwd=temp)
        run(["uv", "pip", "check", "--python", str(python)], cwd=temp)
        installed = json.loads(
            subprocess.check_output(
                [str(python), "-c", smoke], cwd=temp, env=environment, text=True
            )
        )
        cli = venv / (
            "Scripts/collective-intelligence-overlay.exe"
            if os.name == "nt"
            else "bin/collective-intelligence-overlay"
        )
        output = subprocess.check_output(
            [str(cli), "--version"], cwd=temp, env=environment, text=True
        )
        assert version in output
        result = {"runtime": actual, "installed": installed, "cli": output.strip()}
        result["distribution_resolved"] = json.loads(
            subprocess.check_output(
                ["uv", "pip", "list", "--python", str(python), "--format=json"], cwd=temp, text=True
            )
        )
        if args.supply_chain_dir:
            result["supply_chain"] = supply_chain(
                python, name, result["distribution_resolved"], temp=temp
            )
        if name == "core":
            run(
                [
                    str(python),
                    "-c",
                    "import collective_intelligence_overlay,sys; "
                    "assert 'agent_framework' not in sys.modules; assert 'mcp' not in sys.modules",
                ],
                cwd=temp,
                environment=environment,
            )
        else:
            run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    "pytest>=9,<10",
                    "pytest-asyncio>=1,<2",
                    "hypothesis>=6,<7",
                ],
                cwd=temp,
            )
            paths = (
                [root / "tests" if full else root / "tests/unit"]
                if name == "agents"
                else [root / "tests/integration/test_model_adapter.py"]
            )
            result["tests"] = test(
                python,
                paths,
                name,
                temp=temp,
                environment=environment,
                ignore_model=name == "agents",
            )
        result["resolved"] = json.loads(
            subprocess.check_output(
                ["uv", "pip", "list", "--python", str(python), "--format=json"], cwd=temp, text=True
            )
        )
        if name == "agents-model":
            with tarfile.open(sdist) as archive:
                archive.extractall(temp / "source", filter="data")
            source = next((temp / "source").iterdir())
            run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    *project["build-system"]["requires"],
                ],
                cwd=temp,
            )
            # PEP 517 uses this checked interpreter and already-installed backend.
            # Disable uv's native-backend fast path and build-isolation fallback.
            run(
                [
                    "uv",
                    "build",
                    "--wheel",
                    "--force-pep517",
                    "--no-build-isolation",
                    "--python",
                    str(python),
                    "--out-dir",
                    str(temp / "rebuilt"),
                    str(source),
                ],
                cwd=temp,
                environment={**environment, "CIO_PACKAGE_RUNTIME_PHASE": "sdist-build"},
            )
            rebuilt = next((temp / "rebuilt").glob("*.whl"))
            result["build_runtimes"] = [
                json.loads(p.read_text(encoding="utf-8"))
                for p in sorted(records.glob("sdist-build-*.json"))
            ]
            assert result["build_runtimes"], "PEP-517 backend interpreter was not observed"
            run(
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
                cwd=temp,
            )
            run([str(cli), "--version"], cwd=temp, environment=environment)
            run([str(python), "-c", smoke], cwd=temp, environment=environment)
            result["sdist_tests"] = test(
                python,
                [root / "tests/unit", root / "tests/integration/test_model_adapter.py"],
                "rebuilt",
                temp=temp,
                environment=environment,
            )
            result["rebuilt_sha256"] = hashlib.sha256(rebuilt.read_bytes()).hexdigest()
        result["child_runtimes"] = [
            json.loads(p.read_text(encoding="utf-8")) for p in sorted(records.glob("*.json"))
        ]
        assert result["child_runtimes"], "no child runtime observations"
        report["environments"][name] = result
assert hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (wheel, sdist)}, (
    "candidate distributions changed during validation"
)
if args.report:
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(
    json.dumps(
        {
            "verified_version": version,
            "artifacts": hashes,
            "selected": requested,
            "tests": {name: value.get("tests") for name, value in report["environments"].items()},
            "report": str(args.report),
        },
        indent=2,
    )
)
