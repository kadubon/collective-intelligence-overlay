"""Download a reviewed OPA release, verifying a pinned upstream SHA-256."""

import hashlib
import os
import platform
import urllib.request
from pathlib import Path

ASSETS = {
    "Windows": (
        "opa_windows_amd64.exe",
        "1e0e9639673615fa3a6d4974b07e335e44827e377ce7c7bffbb1a6605a26479b",
    ),
    "Linux": (
        "opa_linux_amd64_static",
        "5eef70644868bb04d0556bcc795ee42f2ab379e73f51d1bfa30f83e1305bc9b9",
    ),
}


def main() -> None:
    if platform.machine().lower() not in {"amd64", "x86_64"}:
        raise SystemExit("install OPA 1.21.0 for your architecture and set CIO_OPA")
    asset, checksum = ASSETS[platform.system()]
    target = Path(".local/bin") / ("opa.exe" if os.name == "nt" else "opa")
    target.parent.mkdir(parents=True, exist_ok=True)
    data = urllib.request.urlopen(
        f"https://github.com/open-policy-agent/opa/releases/download/v1.21.0/{asset}", timeout=60
    ).read()
    if hashlib.sha256(data).hexdigest() != checksum:
        raise SystemExit("OPA checksum mismatch")
    target.write_bytes(data)
    target.chmod(0o755)
    print(target.resolve())


if __name__ == "__main__":
    main()
