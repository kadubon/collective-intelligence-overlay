"""Run the same service and artifact gates on every stable Python/OS pair."""

import argparse
import json
import os
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from sqlalchemy import create_engine, text
from validate_short_protocol import validate as validate_short_protocol

from collective_intelligence_overlay.opa_install import architecture, verify_opa

parser = argparse.ArgumentParser()
parser.add_argument("--python-version", required=True)
parser.add_argument("--architecture", required=True)
parser.add_argument("--candidate", type=Path, required=True)
parser.add_argument("--report-dir", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
output = args.report_dir.resolve()
output.mkdir(parents=True, exist_ok=True)
os.environ["CIO_GOLDEN_REPORT_DIR"] = str(output / "golden")
os.environ["CIO_PRODUCTION_FAULT_REPORT_DIR"] = str(output / "source-production-faults")
assert platform.python_version() == args.python_version, "matrix interpreter mismatch"
assert architecture() == args.architecture, "matrix CPU mismatch"
assert os.environ.get("CIO_TEST_DATABASE_URL") and os.environ.get("CIO_OPA"), (
    "mandatory matrix requires real PostgreSQL and OPA"
)


def run(*command):
    subprocess.run(command, cwd=root, check=True)


runtime = {
    "version": sys.version,
    "patch": platform.python_version(),
    "executable": sys.executable,
    "os": platform.system(),
    "architecture": architecture(),
    "machine": platform.machine(),
    "scope": "full",
    "platform": platform.platform(),
    "frozen_dependencies": json.loads(
        subprocess.check_output(
            ["uv", "pip", "list", "--python", sys.executable, "--format=json"], text=True
        )
    ),
}
database = create_engine(os.environ["CIO_TEST_DATABASE_URL"])
try:
    with database.connect() as connection:
        runtime["postgresql"] = connection.execute(text("SELECT version()")).scalar_one()
finally:
    database.dispose()
runtime["opa"] = verify_opa(Path(os.environ["CIO_OPA"]))
(output / "source-runtime.json").write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in runtime.items() if k != "frozen_dependencies"}))
run(sys.executable, "-m", "ruff", "check", ".")
run(sys.executable, "-m", "ruff", "format", "--check", ".")
run(sys.executable, "-m", "mypy")
run(sys.executable, "scripts/check_docs.py")
run(sys.executable, "scripts/runtime_matrix.py", "--check-docs")
print(runtime["opa"])
run(
    sys.executable,
    "-m",
    "pytest",
    "--cov=collective_intelligence_overlay",
    "--cov-report=term-missing",
    "--cov-report=xml:" + str(output / "coverage.xml"),
    "--junitxml=" + str(output / "source-tests.xml"),
    "-W",
    "error::pytest.PytestUnraisableExceptionWarning",
)
totals = {
    key: sum(int(s.get(key, "0")) for s in ET.parse(output / "source-tests.xml").iter("testsuite"))
    for key in ("tests", "failures", "errors", "skipped")
}
assert totals["tests"] > 0 and not any(totals[k] for k in ("failures", "errors", "skipped")), totals
validate_short_protocol(output / "source-production-faults", root)
runtime["source_tests"] = totals
(output / "source-runtime.json").write_text(json.dumps(runtime, indent=2) + "\n", encoding="utf-8")
# The unpublished editable root is checked by artifact metadata/license gates;
# pip-audit audits the installed third-party environment. Audit the actual PyPI
# root separately after publishing, without ignoring vulnerability IDs.
run(sys.executable, "-m", "pip_audit", "--progress-spinner", "off")
run(
    sys.executable,
    "-m",
    "piplicenses",
    "--format=json",
    "--with-urls",
    "--output-file=" + str(output / "source-licenses.json"),
)
run(sys.executable, "scripts/check_licenses.py", str(output / "source-licenses.json"))
run(
    sys.executable,
    "-m",
    "cyclonedx_py",
    "environment",
    sys.executable,
    "--output-file=" + str(output / "source-sbom.json"),
)
run(
    sys.executable,
    "scripts/check_package.py",
    "--python",
    sys.executable,
    "--dist-dir",
    str(args.candidate / "dist"),
    "--hash-file",
    str(args.candidate / "artifacts.json"),
    "--test-scope",
    "full",
    "--report",
    str(output / "package.json"),
    "--supply-chain-dir",
    str(output / "installed-supply-chain"),
    *(["--from-pypi"] if os.environ.get("CIO_FROM_PYPI") == "true" else []),
)
