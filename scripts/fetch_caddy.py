"""Explicit native Caddy build with frozen security updates and standard audits.

Requires operator-installed Go 1.27.1 and Git. Never runs on import or pip install.
"""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from collective_intelligence_overlay.opa_install import architecture

VERSION = "v2.11.4+cio.1"
COMMIT = "e2eee6a7fce366321294c9c2a79f3146891dcbdf"
TOOLS = {
    "go-licenses": "github.com/google/go-licenses/v2@v2.0.1",
    "govulncheck": "golang.org/x/vuln/cmd/govulncheck@v1.8.0",
    "cyclonedx-gomod": "github.com/CycloneDX/cyclonedx-gomod/cmd/cyclonedx-gomod@v1.12.0",
}


def sha(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def build(go_bin: Path) -> dict:
    system, cpu = platform.system(), architecture()
    if (system, cpu) not in {
        ("Windows", "amd64"),
        ("Linux", "amd64"),
        ("Darwin", "amd64"),
        ("Darwin", "arm64"),
    }:
        raise ValueError("undeclared native proxy target")
    root = Path(".local/proxy-build").resolve()
    root.mkdir(parents=True, exist_ok=True)
    report = Path(".local/reports/proxy").resolve()
    report.mkdir(parents=True, exist_ok=True)
    pins = Path(__file__).resolve().parent / "proxy"
    go_bin = go_bin.resolve()
    environment = os.environ.copy()
    environment.update(
        PATH=str(go_bin.parent) + os.pathsep + environment.get("PATH", ""),
        GOTOOLCHAIN="local",
        GOMODCACHE=environment.get("GOMODCACHE", str(root / "go-modules")),
        GOCACHE=environment.get("GOCACHE", str(root / "go-cache")),
        GOBIN=str(root / "tools/bin"),
        CGO_ENABLED="0",
        GOFLAGS="-mod=readonly",
    )

    def run(argv: list[str], name: str, *, cwd: Path = root, seconds: int = 600) -> str:
        result = subprocess.run(
            argv, cwd=cwd, env=environment, capture_output=True, timeout=seconds
        )
        (report / (name + ".stdout")).write_bytes(result.stdout)
        (report / (name + ".stderr")).write_bytes(result.stderr)
        if result.returncode:
            raise ValueError(f"proxy {name} failed ({result.returncode}); see retained report")
        return result.stdout.decode("utf-8")

    version = run([str(go_bin), "version"], "go-version", seconds=10).strip()
    native_os = "darwin" if system == "Darwin" else system.lower()
    if version != f"go version go1.27.1 {native_os}/{cpu}":
        raise ValueError("proxy requires the exact native Go 1.27.1 toolchain")
    # POSIX binaries have no .exe suffix. Keep the checkout separate from
    # root/caddy so Go never treats the executable output as a directory.
    source = root / "caddy-source"
    if not source.exists():
        run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                "v2.11.4",
                "https://github.com/caddyserver/caddy.git",
                str(source),
            ],
            "clone",
        )
    if run(["git", "rev-parse", "HEAD"], "commit", cwd=source, seconds=10).strip() != COMMIT:
        raise ValueError("Caddy source commit differs")
    changes = run(
        ["git", "diff", "--name-only"], "source-changes", cwd=source, seconds=10
    ).splitlines()
    if set(changes) - {"go.mod", "go.sum", "modules/caddyhttp/celmatcher.go"}:
        raise ValueError("unexpected Caddy source modifications")
    original = subprocess.run(
        ["git", "show", "HEAD:modules/caddyhttp/celmatcher.go"],
        cwd=source,
        capture_output=True,
        check=True,
        timeout=10,
    ).stdout
    if original.count(b"[]interpreter.Interpretable{reqAttr}") != 2:
        raise ValueError("unexpected upstream CEL callsites")
    (source / "modules/caddyhttp/celmatcher.go").write_bytes(
        original.replace(
            b"[]interpreter.Interpretable{reqAttr}", b"[]interpreter.InterpretableV2{reqAttr}"
        )
    )
    for name in ("go.mod", "go.sum"):
        shutil.copyfile(pins / name, source / name)
    binary = root / ("caddy.exe" if system == "Windows" else "caddy")
    run(
        [
            str(go_bin),
            "build",
            "-trimpath",
            "-buildvcs=false",
            "-ldflags",
            "-X github.com/caddyserver/caddy/v2.CustomVersion=" + VERSION,
            "-o",
            str(binary),
            "./cmd/caddy",
        ],
        "build",
        cwd=source,
    )
    run([str(go_bin), "mod", "verify"], "modules-verify", cwd=source)
    if run([str(binary), "version"], "version", seconds=10).strip() != VERSION:
        raise ValueError("unexpected custom Caddy version")
    run([str(go_bin), "version", "-m", str(binary)], "buildinfo", seconds=10)
    run(
        [str(go_bin), "test", "./modules/caddyhttp/...", "./modules/caddytls/..."],
        "upstream-tests",
        cwd=source,
    )
    packages = run(
        [str(go_bin), "list", "-deps", "./cmd/caddy"], "packages", cwd=source
    ).splitlines()
    if any(p.startswith("golang.org/x/crypto/openpgp") for p in packages):
        raise ValueError("unsafe unmaintained OpenPGP package is linked")
    tools_bin = root / "tools/bin"
    tools_bin.mkdir(parents=True, exist_ok=True)
    for name, pin in TOOLS.items():
        run([str(go_bin), "install", pin], "install-" + name, cwd=source)
    extension = ".exe" if system == "Windows" else ""
    licenses, vuln, sbom = (str(tools_bin / (name + extension)) for name in TOOLS)
    run([licenses, "report", "./cmd/caddy"], "licenses", cwd=source)
    run(
        [
            licenses,
            "check",
            "--allowed_licenses=Apache-2.0,BSD-2-Clause,BSD-3-Clause,MIT,CC0-1.0,MPL-2.0,OFL-1.1",
            "./cmd/caddy",
        ],
        "license-check",
        cwd=source,
    )
    # Save cannot handle OFL even though report/check identify it. Review Chroma's
    # combined MIT/OFL COPYING explicitly; check still includes the whole graph.
    notices = Path(tempfile.mkdtemp(prefix="licenses-", dir=report)) / "notices"
    run(
        [
            licenses,
            "save",
            "--ignore=github.com/alecthomas/chroma/v2",
            "--save_path=" + str(notices),
            "./cmd/caddy",
        ],
        "license-save-reviewed",
        cwd=source,
    )
    chroma = json.loads(
        run(
            [str(go_bin), "mod", "download", "-json", "github.com/alecthomas/chroma/v2@v2.24.1"],
            "chroma-source",
            cwd=source,
        )
    )
    combined = notices / "github.com/alecthomas/chroma/v2"
    combined.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(chroma["Dir"]) / "COPYING", combined / "COPYING")
    run([vuln, "-mode=binary", "-show", "verbose", str(binary)], "vulnerabilities", cwd=source)
    messages = run([vuln, "-mode=binary", "-json", str(binary)], "vulnerabilities-json", cwd=source)
    # Read the scanner's public JSON stream; this is not a vulnerability detector.
    decoder = json.JSONDecoder()
    findings = []
    while messages.strip():
        message, end = decoder.raw_decode(messages.lstrip())
        messages = messages.lstrip()[end:]
        if "finding" in message:
            findings.append(message["finding"])
    if any(
        f["osv"] != "GO-2026-5932" or any(t.get("package") or t.get("function") for t in f["trace"])
        for f in findings
    ):
        raise ValueError("unreviewed proxy vulnerability finding")
    run(
        [
            sbom,
            "app",
            "-json",
            "-licenses",
            "-std",
            "-packages",
            "-files",
            "-main",
            "cmd/caddy",
            "-output",
            str(report / "sbom.json"),
            str(source),
        ],
        "sbom",
        cwd=source,
    )
    result = {
        "version": VERSION,
        "official_binary": False,
        "os": system,
        "architecture": cpu,
        "source_commit": COMMIT,
        "go": version,
        "go_binary_sha256": sha(go_bin),
        "binary_sha256": sha(binary),
        "go_mod_sha256": sha(pins / "go.mod"),
        "go_sum_sha256": sha(pins / "go.sum"),
        "cel_patch_sha256": sha(pins / "cel-v2.patch"),
        "linked_packages": len(packages),
        "vulnerability_module_findings": findings,
        "module_review": "scripts/proxy/README.md#security-review",
        "license_review": "scripts/proxy/README.md#license-review",
        "saved_notices": str(notices.relative_to(report)),
        "audits_passed": True,
    }
    (report / "proxy.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if environment_file := os.environ.get("GITHUB_ENV"):
        with Path(environment_file).open("a", encoding="utf-8") as output:
            output.write(f"CIO_CADDY={binary}\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go-bin", type=Path, default=shutil.which("go"))
    args = parser.parse_args()
    if args.go_bin is None:
        parser.error("install native Go 1.27.1 explicitly, then supply --go-bin or PATH")
    print(json.dumps(build(args.go_bin)))
