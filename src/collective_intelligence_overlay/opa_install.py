"""Explicit, atomic installation of a reviewed official OPA binary (no import I/O)."""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

VERSION = "1.21.0"
# Official release checksums, reviewed 2026-09-30. Apache-2.0 upstream binary.
ASSETS = {
    ("Windows", "amd64"): (
        "opa_windows_amd64.exe",
        "1e0e9639673615fa3a6d4974b07e335e44827e377ce7c7bffbb1a6605a26479b",
    ),
    ("Linux", "amd64"): (
        "opa_linux_amd64_static",
        "5eef70644868bb04d0556bcc795ee42f2ab379e73f51d1bfa30f83e1305bc9b9",
    ),
    ("Darwin", "amd64"): (
        "opa_darwin_amd64",
        "0ceb96979d259b3ee31711a6b316a592b8ffcfdd4209cc37600ed85a6cd4a55c",
    ),
    ("Darwin", "arm64"): (
        "opa_darwin_arm64",
        "f1e4da6467a2adb2846bb23eec6ea00d8c3a04786f9270bb11003d22dfd827a5",
    ),
}
MAX_BYTES = 128 * 1024 * 1024


def architecture(machine: str | None = None) -> str:
    """Normalize CPU spellings; unsupported CPUs remain explicit errors."""
    value = (platform.machine() if machine is None else machine).lower()
    aliases = {"amd64": "amd64", "x86_64": "amd64", "aarch64": "arm64", "arm64": "arm64"}
    if value not in aliases:
        raise ValueError(f"unsupported CPU {value!r}; install a reviewed OPA manually")
    return aliases[value]


class _HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> urllib.request.Request | None:
        url = urlsplit(newurl)
        if url.scheme != "https" or url.hostname not in {
            "github.com",
            "release-assets.githubusercontent.com",
            "objects.githubusercontent.com",
        }:
            raise ValueError("OPA download redirected outside official HTTPS assets")
        return super().redirect_request(req, fp, code, msg, headers, newurl)  # type: ignore[arg-type]


def verify_opa(path: Path) -> str:
    """Execute the pinned binary and check its reported native OS/CPU and version."""
    system, cpu = platform.system(), architecture()
    if system == "Darwin":
        translated = subprocess.run(
            ["sysctl", "-in", "sysctl.proc_translated"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if translated.stdout.strip() == "1":
            raise ValueError("native macOS setup requires native Python; Rosetta is not supported")
    result = subprocess.run(
        [str(path.resolve()), "version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    ).stdout
    fields = dict(line.split(": ", 1) for line in result.splitlines() if ": " in line)
    if fields.get("Version") != VERSION or fields.get("Platform") != f"{system.lower()}/{cpu}":
        raise ValueError("OPA version/native platform does not match the reviewed asset")
    return result


def install_opa(target: Path) -> Path:
    """Download on explicit operator request, verify, then replace in the same directory.

    A failed download, hash, execution or native-platform check retains the old
    target. No privilege changes, quarantine manipulation or service restart.
    """
    key = (platform.system(), architecture())
    if key not in ASSETS:
        raise ValueError(f"unsupported OPA platform {key}; install a reviewed OPA manually")
    target = target.expanduser().absolute()
    if target.is_symlink():
        raise ValueError("OPA target must not be a symlink")
    target.parent.mkdir(parents=True, exist_ok=True)
    asset, checksum = ASSETS[key]
    url = f"https://github.com/open-policy-agent/opa/releases/download/v{VERSION}/{asset}"
    deadline = time.monotonic() + 60
    opener = urllib.request.build_opener(_HTTPSRedirect())
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent, prefix=".opa-", suffix=target.suffix, delete=False
        ) as output:
            temporary = Path(output.name)
            digest = hashlib.sha256()
            size = 0
            with opener.open(url, timeout=10) as response:
                if int(response.headers.get("Content-Length", "0")) > MAX_BYTES:
                    raise ValueError("OPA download exceeds size limit")
                while True:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("OPA download time budget exceeded")
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    size += len(block)
                    if size > MAX_BYTES:
                        raise ValueError("OPA download exceeds size limit")
                    digest.update(block)
                    output.write(block)
            if digest.hexdigest() != checksum:
                raise ValueError("OPA checksum mismatch; existing target retained")
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o755)
        verify_opa(temporary)
        os.replace(temporary, target)
        return target.resolve()
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
