"""Execute the installed README/tutorial blocks in a new native directory."""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def blocks(path, language):
    return re.findall(
        r"```" + language + r"\n(.*?)\n```", path.read_text(encoding="utf-8"), flags=re.S
    )


def run(wheel, output):
    windows = os.name == "nt"
    language = "powershell" if windows else "sh"
    readme = blocks(ROOT / "README.md", language)
    assert readme == blocks(ROOT / "README.ja.md", language), "bilingual commands differ"
    quickstart = blocks(ROOT / "docs/quickstart.md", language)[0]
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    suffix = ".exe" if windows else ""
    pg_config = shutil.which("pg_config" + suffix)
    assert pg_config, "native PostgreSQL tools required for the installed tutorial"
    pg_bin = Path(subprocess.check_output([pg_config, "--bindir"], text=True).strip())
    assert all((pg_bin / (name + suffix)).is_file() for name in ("initdb", "pg_ctl", "pg_isready"))
    shell = shutil.which("pwsh" if windows else "bash")
    assert shell, "documented native shell unavailable"
    with tempfile.TemporaryDirectory(prefix="cio-installed-tutorial-") as temporary:
        directory = Path(temporary)
        venv = directory / ".venv"
        python = venv / ("Scripts/python.exe" if windows else "bin/python")
        environment = os.environ.copy()
        environment["PATH"] = str(pg_bin) + os.pathsep + environment["PATH"]
        # Venv creation is infrastructure; CLI/demo startup retains the package guard.
        creation_env = {k: v for k, v in environment.items() if not k.startswith("CIO_PACKAGE_")}
        subprocess.run(
            ["uv", "venv", "--python", sys.executable, str(venv)],
            cwd=directory,
            env=creation_env,
            check=True,
            timeout=60,
        )
        environment["CIO_PACKAGE_RUNTIME_EXE"] = str(python.absolute())
        installation = readme[0].splitlines()[1:]
        requirement = "collective-intelligence-overlay[agents]==0.4.0"
        local_requirement = str(wheel.absolute())
        assert not any(char in local_requirement for char in "'\r\n"), "unsafe tutorial wheel path"
        installation = [
            line.replace(requirement, local_requirement + "[agents]") for line in installation
        ]
        tutorial = quickstart.replace("55439", str(port))
        lines = installation + tutorial.splitlines()
        for index, line in enumerate(lines):
            if line.startswith("collective-intelligence-overlay demo "):
                lines[index] = line + " > demo.json"
            elif line.startswith("collective-intelligence-overlay doctor "):
                lines[index] = line + " > doctor.json"
        # The starter block follows the first-run instructions in both READMEs.
        starter = blocks(ROOT / "README.md", "sh")[2]
        assert starter == blocks(ROOT / "README.ja.md", "sh")[2]
        lines.extend(starter.splitlines())
        text = "\n".join(lines) + "\n"
        if windows:
            text = "$ErrorActionPreference = 'Stop'\n" + text
            text += "if ($LASTEXITCODE -ne 0) { throw 'Installed tutorial failed' }\n"
        else:
            text = "set -eu\n" + text
        script = directory / ("tutorial.ps1" if windows else "tutorial.sh")
        script.write_text(text, encoding="utf-8")
        try:
            command = (
                [shell, "-NoProfile", "-File", str(script)] if windows else [shell, str(script)]
            )
            with (directory / "commands.log").open("wb") as log:
                subprocess.run(
                    command,
                    cwd=directory,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=True,
                    timeout=360,
                )
            demo = json.loads((directory / "demo.json").read_text(encoding="utf-8-sig"))
            doctor = json.loads((directory / "doctor.json").read_text(encoding="utf-8-sig"))
            assert demo["processes"] == 3 and demo["admission"] == "ACCEPT"
            assert demo["changed_environment"] == "REQUALIFY"
            assert demo["after_dependency_revocation"] == "REJECT"
            assert "117.00" in demo["held_out_result"]
            assert (directory / "my-application/application.py").is_file()
            result = {
                "passed": True,
                "wheel": wheel.name,
                "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                "runtime": platform.python_version(),
                "os": platform.system(),
                "native_postgresql_bin": str(pg_bin),
                "tutorial_port": port,
                "substitutions": [
                    "candidate wheel installation",
                    "selected interpreter",
                    "unused dedicated port",
                ],
                "docs_sha256": {
                    name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                    for name in ("README.md", "README.ja.md", "docs/quickstart.md")
                },
                "demo": demo,
                "doctor": doctor,
            }
        finally:
            output.parent.mkdir(parents=True, exist_ok=True)
            if (directory / "commands.log").is_file():
                shutil.copyfile(directory / "commands.log", output.with_suffix(".log"))
            data = directory / "tutorial-pg"
            if (data / "postmaster.pid").exists():
                # This unique directory was created by this invocation; no shared cluster.
                subprocess.run(
                    [
                        str(pg_bin / ("pg_ctl" + suffix)),
                        "-D",
                        str(data),
                        "-m",
                        "fast",
                        "-w",
                        "stop",
                    ],
                    check=True,
                    timeout=40,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        output.write_text(json.dumps(result, indent=2) + "\n")
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.wheel, args.output)))
