"""Own one disposable native CI cluster; never operate on an existing service."""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("operation", choices=["start", "stop"])
parser.add_argument("--bin", type=Path, required=True)
parser.add_argument("--data", type=Path, required=True)
parser.add_argument("--port", type=int, default=55439)
args = parser.parse_args()
base = Path(os.environ["RUNNER_TEMP"]).resolve()
data = args.data.absolute()
binary = args.bin.resolve()
assert not data.is_symlink() and data.resolve().is_relative_to(base) and data.resolve() != base, (
    "CI data must be a dedicated child of RUNNER_TEMP"
)
data = data.resolve()
suffix = ".exe" if os.name == "nt" else ""
assert all(
    (binary / (name + suffix)).is_file()
    for name in ("initdb", "pg_ctl", "pg_isready", "psql", "pg_dump", "pg_restore")
), "PG tools missing"
marker = data / ".cio-ci-owner.json"
owned = {"data": str(data), "bin": str(binary)}


def run(name, *arguments, check=True):
    result = subprocess.run(
        [str(binary / (name + suffix)), *map(str, arguments)],
        check=False,
        timeout=70,
        capture_output=True,
        text=True,
    )
    if check and result.returncode:
        print(result.stdout[-4096:], file=sys.stderr)
        print(result.stderr[-4096:], file=sys.stderr)
        if name == "pg_ctl" and "start" in arguments and (data / "server.log").is_file():
            # Startup precedes test/application queries; retain this bounded diagnosis.
            log = (data / "server.log").read_text(encoding="utf-8", errors="replace")[-4096:]
            print(log, file=sys.stderr)
        result.check_returncode()
    return result


if args.operation == "start":
    assert not data.exists(), "refusing to reinitialize an existing directory"
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", args.port)) != 0, "private CI port already occupied"
    run("initdb", "-D", data, "-U", "postgres", "-A", "trust", "--encoding=UTF8")
    marker.write_text(json.dumps(owned), encoding="utf-8")
    # Windows has no shared Unix socket. POSIX explicitly disables its default
    # /tmp socket; shell single quotes must not be passed through Windows pg_ctl.
    options = f"-h 127.0.0.1 -p {args.port}"
    if os.name != "nt":
        options += " -c unix_socket_directories=''"
    run(
        "pg_ctl",
        "-D",
        data,
        "-l",
        data / "server.log",
        "-o",
        options,
        "-w",
        "-t",
        "60",
        "start",
    )
    run("pg_isready", "-h", "127.0.0.1", "-p", args.port, "-U", "postgres")
    print(
        run(
            "psql",
            "-h",
            "127.0.0.1",
            "-p",
            args.port,
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-c",
            "SELECT version()",
        ).stdout
    )
else:
    if not data.exists():
        raise SystemExit(0)
    assert marker.is_file() and not marker.is_symlink(), "cluster ownership marker missing"
    assert json.loads(marker.read_text(encoding="utf-8")) == owned, "cluster ownership mismatch"
    status = run("pg_ctl", "-D", data, "status", check=False)
    if status.returncode == 0:
        run("pg_ctl", "-D", data, "-m", "fast", "-w", "-t", "30", "stop")
    else:
        assert status.returncode == 3, "cannot determine cluster state; data retained"
    assert data.resolve().is_relative_to(base) and data.resolve() != base and not data.is_symlink()
    shutil.rmtree(data)
