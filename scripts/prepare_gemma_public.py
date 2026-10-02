"""Create a separate shareable copy; preserve every source byte and failure locally."""

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def public_bytes(path, raw):
    # Signed envelopes, CAS, model input/output and frozen source are retained
    # verbatim. Reject accidental private material instead of mutating proofs.
    protected = (
        "source-snapshot" in path.parts
        or "source" in path.parts
        or "model" in path.parts
        or "offers" in path.parts
        or path.name.endswith(("-observations.json", "-artifacts.json"))
        or path.name.endswith("-decisions.json")
        or path.name.startswith("snapshot-")
        or path.name
        in {
            "protocol.json",
            "source-manifest.json",
            "offer-plan.json",
            "arm-result.json",
            "cohort.json",
            "final-stock.json",
            "irrelevant-stock.json",
            "new-receiver-stock.json",
            "resources.json",
            "transfers.json",
            "calls.jsonl",
            "export.json",
        }
    )
    secrets = (b"BEGIN PRIVATE KEY", b"BEGIN RSA PRIVATE KEY", b"BEGIN OPENSSH PRIVATE KEY")
    if any(marker in raw for marker in secrets):
        # Source code and tests may contain the marker as a scanner constant;
        # complete PEM headers with a newline denote actual key material.
        if b"-----BEGIN " in raw and b"PRIVATE KEY-----\n" in raw:
            raise ValueError("private key material in " + path.as_posix())
    changes = []
    if protected:
        if re.search(rb"postgresql(?:\+pg8000)?://[^\s\"']+", raw):
            # Frozen source may contain example URIs, never an operator secret.
            if not {"source-snapshot", "source"} & set(path.parts):
                raise ValueError("private DSN in protected observation " + path.as_posix())
        return raw, changes
    if path.name == "before-tags.raw":
        value = json.loads(raw)
        models = value.get("models", [])
        selected = [m for m in models if m.get("name") == "gemma4:e4b"]
        if len(selected) != len(models):
            value["models"] = selected
            raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
            changes.append(
                {"kind": "unrelated_installed_model_metadata", "count": len(models) - len(selected)}
            )
    if path.name == "model-manifest.json":
        value = json.loads(raw)
        models = value.get("tags", {}).get("models", [])
        selected = [m for m in models if m.get("name") == "gemma4:e4b"]
        if len(selected) != len(models):
            value["tags"]["models"] = selected
            raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
            changes.append(
                {"kind": "unrelated_installed_model_metadata", "count": len(models) - len(selected)}
            )
    patterns = (
        (
            rb"postgresql(?:\+pg8000)?://[^\s\"'<>]+",
            b"[REDACTED_DATABASE_DSN]",
            "operator_database_dsn",
        ),
        (
            rb"C:(?:\\\\|\\|/)Users(?:\\\\|\\|/)[^/\\\s\"']+",
            b"[LOCAL_HOME]",
            "operator_home_path",
        ),
        (rb"/mnt/[a-z]/Users/[^/\\\s\"']+", b"[LOCAL_HOME]", "operator_wsl_home_path"),
        (rb"/home/[^/\\\s\"']+", b"[LOCAL_HOME]", "operator_linux_home_path"),
        (rb"/Users/[^/\\\s\"']+", b"[UPSTREAM_HOME]", "upstream_calibration_home_path"),
    )
    for pattern, replacement, reason in patterns:
        raw, count = re.subn(pattern, replacement, raw)
        if count:
            changes.append({"kind": reason, "count": count})
    return raw, changes


def prepare(source, destination):
    from check_production_reports import file_manifest

    source, destination = source.resolve(), destination.resolve()
    if destination == source or destination.is_relative_to(source):
        raise ValueError("public copy must be outside originals")
    destination.mkdir(parents=True, exist_ok=False)
    original_manifest = file_manifest(source)
    mappings = []
    for name, original_hash in original_manifest.items():
        path = Path(name)
        original = source / path
        if original.is_symlink():
            raise ValueError("symlink in original data")
        raw = original.read_bytes()
        public, changes = public_bytes(path, raw)
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(public)
        mappings.append(
            {
                "file": name,
                "original_sha256": original_hash,
                "public_sha256": sha(public),
                "transformations": changes,
            }
        )
    assert file_manifest(source) == original_manifest, "originals changed while copying"
    manifest = {
        "classification": "separate_shareable_copy",
        "originals_unchanged": True,
        "inference_performed": False,
        "omitted_failure_records": 0,
        "mappings": mappings,
        "integrity_scope": (
            "Original raw model bytes, CAS, signed envelopes and source snapshot are unchanged; "
            "metadata path redactions are separate unsigned transformations. Hashes are identity "
            "checks, not truth or malicious-operator resistance."
        ),
    }
    with (destination / "redaction-manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    with (destination / "file-manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(file_manifest(destination), stream, indent=2)
        stream.write("\n")
    print(
        json.dumps(
            {
                "files": len(mappings),
                "transformed_files": sum(bool(m["transformations"]) for m in mappings),
                "inference_performed": False,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.source, args.output)
