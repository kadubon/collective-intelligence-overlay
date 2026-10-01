"""Review retained native assembly/header source hashes and literal includes.

This supplements go-licenses' warning; it does not prove semantic absence of
hidden dependencies or replace upstream notices and native binary audits.
"""

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

from runtime_matrix import combinations


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def review(reports, candidate, cache, goroot, output):
    expected = json.loads((candidate / "artifacts.json").read_text(encoding="utf-8"))
    assert expected == {
        p.name: digest(p) for p in (candidate / "dist").iterdir() if p.suffix in {".whl", ".gz"}
    }
    assert (goroot / "VERSION").read_text(encoding="utf-8").splitlines()[0] == "go1.27.1"
    output.mkdir(parents=True, exist_ok=False)
    source_bytes = {}
    summaries = []
    for runtime in combinations():
        name = "reports-{os}-{architecture}-{python}-full".format(**runtime)
        directory = reports / name
        package = json.loads((directory / "package.json").read_text(encoding="utf-8"))
        assert package["artifacts"] == expected
        proxy = directory / "proxy"
        metadata = json.loads((proxy / "proxy.json").read_text(encoding="utf-8"))
        assert metadata["audits_passed"] is True
        assert (metadata["os"], metadata["architecture"]) == (
            runtime["os"],
            runtime["architecture"],
        )
        assert "CGO_ENABLED=0" in (proxy / "buildinfo.stdout").read_text(encoding="utf-8")
        sbom = json.loads((proxy / "sbom.json").read_text(encoding="utf-8"))
        files = []
        visited = set()

        def retain(
            path,
            owner,
            base,
            *,
            expected_hash=None,
            assembly_input=True,
            files=files,
            visited=visited,
        ):
            path = path.resolve()
            assert path.is_relative_to(base.resolve())
            key = owner + "/" + path.relative_to(base.resolve()).as_posix()
            content = path.read_bytes()
            sha = hashlib.sha256(content).hexdigest()
            if expected_hash is not None:
                assert sha == expected_hash, key
            source_bytes.setdefault(key, content)
            assert source_bytes[key] == content
            visit = (key, assembly_input)
            if visit in visited:
                return key
            visited.add(visit)
            assert len(visited) <= 10000
            includes = []
            for token in re.findall(rb"(?m)^\s*#\s*include\s+([^\r\n]+)", content):
                if not assembly_input:
                    includes.append({"directive": token.decode("utf-8"), "assembly_input": False})
                    continue
                match = re.fullmatch(rb'"([^"\r\n]+)"\s*(?://[^\r\n]*)?', token)
                assert match is not None, (key, token)
                header = match[1].decode("ascii")
                if header == "go_asm.h":
                    includes.append(
                        {"name": header, "origin": "Go compiler generated ABI constants"}
                    )
                    continue
                local = path.parent / header
                global_header = goroot / "pkg/include" / header
                if local.is_file():
                    target = retain(local, owner, base)
                else:
                    assert global_header.is_file(), (key, header)
                    target = retain(global_header, "std@go1.27.1", goroot)
                includes.append({"name": header, "source": target})
            files.append(
                {
                    "source": key,
                    "sha256": sha,
                    "includes": includes,
                    "assembly_input": assembly_input,
                }
            )
            return key

        for module in sbom["components"]:
            owner = module["name"] + "@" + module["version"]
            assert not Path(owner).is_absolute() and ".." not in Path(owner).parts
            standard = module["name"] == "std"
            base = goroot if standard else cache / owner
            assert standard or base.resolve().is_relative_to(cache.resolve())
            for component in module.get("components", []):
                package_name = component["name"]
                assert (
                    standard
                    or package_name == module["name"]
                    or package_name.startswith(module["name"] + "/")
                )
                relative = (
                    "src/" + package_name
                    if standard
                    else package_name.removeprefix(module["name"]).lstrip("/")
                )
                for file in component.get("components", []):
                    if file.get("type") != "file":
                        continue
                    assert not file["name"].endswith((".syso", ".o", ".a")), file["name"]
                    if not file["name"].endswith((".s", ".S", ".h")):
                        continue
                    hashes = [h["content"] for h in file["hashes"] if h["alg"] == "SHA-256"]
                    assert len(hashes) == 1
                    retain(
                        base / relative / file["name"],
                        owner,
                        base,
                        expected_hash=hashes[0],
                        assembly_input=file["name"].endswith((".s", ".S")),
                    )
        assert files
        # Full original module notices, including OFL/MPL, stay with each native
        # report; add the exact toolchain LICENSE and per-file source notices.
        retain(goroot / "LICENSE", "std@go1.27.1", goroot, assembly_input=False)
        notices = proxy / metadata["saved_notices"]
        assert notices.resolve().is_relative_to(proxy.resolve()) and notices.is_dir()
        notice_hashes = {}
        for notice in notices.rglob("*"):
            if notice.is_file():
                relative = notice.relative_to(notices).as_posix()
                content = notice.read_bytes()
                notice_hashes[relative] = hashlib.sha256(content).hexdigest()
                key = "native-module-notices/" + name + "/" + relative
                source_bytes[key] = content
        assert notice_hashes
        summaries.append(
            {
                "runtime": runtime,
                "proxy": metadata,
                "sbom_sha256": digest(proxy / "sbom.json"),
                "license_warnings_sha256": digest(proxy / "license-check.stderr"),
                "native_module_notice_sha256": notice_hashes,
                "assembly_headers_and_includes": sorted(files, key=lambda item: item["source"]),
            }
        )
    with zipfile.ZipFile(
        output / "original-assembly-header-notices.zip", "w", zipfile.ZIP_DEFLATED
    ) as archive:
        for name, content in sorted(source_bytes.items()):
            archive.writestr(name, content)
    result = {
        "artifacts": expected,
        "runtimes": summaries,
        "unique_original_files": len(source_bytes),
        "source_notice_archive_sha256": digest(output / "original-assembly-header-notices.zip"),
        "unresolved_assembly_literal_includes": 0,
        "scope": (
            "Exact native SBOM source hashes, original file notices and literal includes. "
            "compiler-generated go_asm.h is identified separately. No semantic hidden-dependency "
            "or independent legal/security audit claim. All SBOM headers are retained; standalone "
            "header directives are separate from the actual assembly include closure under CGO=0."
        ),
        "review_passed": True,
    }
    (output / "review.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("reports", "candidate", "cache", "goroot", "output"):
        parser.add_argument("--" + option, type=Path, required=True)
    args = parser.parse_args()
    result = review(**vars(args))
    print(
        json.dumps(
            {"runtimes": len(result["runtimes"]), "original_files": result["unique_original_files"]}
        )
    )
