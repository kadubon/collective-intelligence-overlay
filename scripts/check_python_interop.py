"""Verify fixed hashes, original DSSE and real mixed-version installed peers."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from collective_intelligence_overlay.demo import initialize

parser = argparse.ArgumentParser()
parser.add_argument("--candidate", type=Path, required=True)
parser.add_argument("--minimum", required=True)
parser.add_argument("--latest", required=True)
parser.add_argument("--report", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
helper = root / "tests/integration/python_interop_application.py"
hashes = json.loads((args.candidate / "artifacts.json").read_text(encoding="utf-8"))
assert hashes == {
    path.name: hashlib.sha256(path.read_bytes()).hexdigest()
    for path in (args.candidate / "dist").iterdir()
    if path.name.endswith((".whl", ".tar.gz"))
}
wheel = next((args.candidate / "dist").glob("*.whl")).resolve()
admin_url, opa = os.environ["CIO_TEST_DATABASE_URL"], os.environ["CIO_OPA"]
report = {"artifacts": hashes, "patches": [args.minimum, args.latest], "directions": []}
report["resolved_dependencies"] = {}


def child(python, patch, mode, home, output, *options):
    command = [str(python), str(helper), mode, str(home), "--output", str(output), *options]
    environment = {**os.environ, "CIO_INTEROP_PATCH": patch}
    # The test application directory contains host fixtures, never CIO source.
    environment.pop("PYTHONPATH", None)
    return command, environment


def run(python, patch, mode, home, output, *options):
    command, environment = child(python, patch, mode, home, output, *options)
    subprocess.run(command, cwd=home.parent, env=environment, check=True, timeout=180)
    value = json.loads(output.read_text(encoding="utf-8"))
    assert value["runtime"]["patch"] == patch
    assert os.path.normcase(value["runtime"]["executable"]) == os.path.normcase(str(python))
    return value


with tempfile.TemporaryDirectory(prefix="cio-python-interop-") as temporary:
    directory = Path(temporary)
    interpreters = {}
    for patch in (args.minimum, args.latest):
        venv = directory / ("python-" + patch)
        subprocess.run(["uv", "venv", "--python", patch, str(venv)], check=True)
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
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
            ],
            check=True,
        )
        subprocess.run(["uv", "pip", "check", "--python", str(python)], check=True)
        report["resolved_dependencies"][patch] = json.loads(
            subprocess.check_output(
                ["uv", "pip", "list", "--python", str(python), "--format=json"], text=True
            )
        )
        interpreters[patch] = python
    for writer, reader in ((args.minimum, args.latest), (args.latest, args.minimum)):
        home = directory / ("writer-" + writer)
        configs = initialize(home, admin_url, opa)
        for name, config in configs.items():
            saved = config.model_dump(mode="json")
            saved["execution_environment"] = {"application": "1"}
            saved["database_url"] = config.database_url.get_secret_value()
            (home / name / "config.json").write_text(json.dumps(saved), encoding="utf-8")
        processes, logs = [], []
        try:
            seeded = run(interpreters[writer], writer, "seed", home, home / "seed.json")
            snapshots = {}
            for patch in (writer, reader):
                snapshots[patch] = run(
                    interpreters[patch], patch, "snapshot", home, home / (patch + "-snapshot.json")
                )
            assert snapshots[writer]["fixed"] == snapshots[reader]["fixed"]
            assert snapshots[writer]["legacy_payloads"] == snapshots[reader]["legacy_payloads"]
            peers = {}
            for owner, patch in (("producer", writer), ("verifier", reader), ("receiver", reader)):
                output = home / (owner + "-runtime.json")
                command, environment = child(
                    interpreters[patch], patch, "peer", home, output, "--owner", owner
                )
                log = (home / (owner + ".log")).open("wb")
                logs.append(log)
                process = subprocess.Popen(
                    command,
                    cwd=directory,
                    env=environment,
                    stdout=log,
                    stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                processes.append(process)
                peers[owner] = (patch, output)
            exchanged = run(interpreters[reader], reader, "exercise", home, home / "exchange.json")
            runtime_peers = {}
            for owner, (patch, output) in peers.items():
                actual = json.loads(output.read_text(encoding="utf-8"))
                assert actual["patch"] == patch
                assert os.path.normcase(actual["executable"]) == os.path.normcase(
                    str(interpreters[patch])
                )
                runtime_peers[owner] = actual
            verified = []
            for patch, other in ((reader, writer), (writer, reader)):
                verified.append(
                    run(
                        interpreters[patch],
                        patch,
                        "verify",
                        home,
                        home / (patch + "-verified.json"),
                        "--other",
                        str(home / (other + "-snapshot.json")),
                    )
                )
            report["directions"].append(
                {
                    "writer": writer,
                    "reader": reader,
                    "seed": seeded,
                    "peers": runtime_peers,
                    "exchange": exchanged,
                    "verification": verified,
                }
            )
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate(timeout=10)
            for log in logs:
                log.close()
            # Only these freshly allocated UUID roles/databases belong to this run.
            admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
            try:
                with admin.connect() as conn:
                    for config in configs.values():
                        url = make_url(config.database_url.get_secret_value())
                        role = url.database
                        assert role == url.username and re.fullmatch(r"cio_[0-9a-f]{32}", role)
                        conn.execute(text(f'DROP DATABASE "{role}" WITH (FORCE)'))
                        conn.execute(text(f'DROP ROLE "{role}"'))
            finally:
                admin.dispose()
report["passed"] = True
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"patches": report["patches"], "passed": True, "report": str(args.report)}))
