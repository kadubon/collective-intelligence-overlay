"""Structure attacks use actual pg_dump archives and deliberately matching hashes."""

import json
import os
from pathlib import Path

import pytest
from test_production_tls import tls_fixture

from collective_intelligence_overlay.artifacts import Artifacts
from collective_intelligence_overlay.recovery import backup, verify_backup
from collective_intelligence_overlay.security import digest


@pytest.fixture
def valid_backup(app_config, tmp_path):
    settings = tmp_path / "application-settings.json"
    settings.write_text("{}", encoding="utf-8")
    config = app_config.model_copy(update={"application_settings": settings})
    target = tmp_path / "backup"
    backup(
        config,
        target,
        operator_url=os.environ["CIO_TEST_DATABASE_URL"],
        pg_prefix=tuple(json.loads(os.environ.get("CIO_PG_TOOL_PREFIX", "[]"))),
    )
    return target


def change_file(target, manifest, name, payload):
    (target / name).write_bytes(payload)
    manifest["files"][name] = digest(payload)


def test_schema_one_empty_cas_remains_valid_without_claiming_restore(valid_backup):
    target = valid_backup
    manifest = json.loads((target / "manifest.json").read_bytes())
    assert manifest["backup_schema"] == "1" and manifest["artifact_bytes"] == 0
    # Old schema-1 manifests have these same fields and distribution 0.4.0.
    manifest["runtime"]["distribution"] = "0.4.0"
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    verified = verify_backup(target)
    assert verified["checksums_verified"] and verified["structure_complete"]
    assert verified["dump_format_verified"]
    assert verified["restoration_tested"] is False
    assert verified["external_reconciliation"] == "not_performed"
    assert verified["manifest_authenticated"] is False


@pytest.mark.parametrize(
    "attack",
    [
        "missing-database.dump",
        "missing-config.json",
        "missing-identity.pem",
        "missing-database-url",
        "missing-application_settings.data",
        "missing-artifact-directory",
        "unknown-entry",
        "unlisted-file",
        "nested-directory",
        "path-traversal",
        "absolute-path",
        "symlink",
        "duplicate-manifest",
        "duplicate-config",
        "unknown-config",
        "external-dsn-reference",
        "external-key-reference",
        "owner-mismatch",
        "application-mismatch",
        "tls-inventory-mismatch",
        "invalid-hash",
        "artifact-size-mismatch",
        "corrupt-dump-magic",
        "corrupt-dump-archive",
        "oversized-identity",
    ],
)
def test_structural_attacks_are_rejected_even_with_matching_hashes(valid_backup, attack):
    target = valid_backup
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    if attack.startswith("missing-"):
        name = attack.removeprefix("missing-")
        if name == "artifact-directory":
            (target / "artifacts").rmdir()
        else:
            (target / name).unlink()
            manifest["files"].pop(name)
    elif attack == "unknown-entry":
        change_file(target, manifest, "arbitrary", b"arbitrary bytes")
    elif attack == "unlisted-file":
        (target / "unlisted").write_bytes(b"not inventoried")
    elif attack == "nested-directory":
        (target / "artifacts" / "nested").mkdir()
    elif attack in {"path-traversal", "absolute-path"}:
        name = "../outside" if attack == "path-traversal" else str(Path(target.anchor) / "outside")
        manifest["files"][name] = "a" * 64
    elif attack == "symlink":
        original = (target / "identity.pem").read_bytes()
        outside = target.parent / "other-identity.pem"
        outside.write_bytes(original)
        (target / "identity.pem").unlink()
        (target / "identity.pem").symlink_to(outside)
    elif attack == "duplicate-manifest":
        original = manifest_path.read_text()
        manifest_path.write_text('{"owner":"receiver",' + original[1:], encoding="utf-8")
        with pytest.raises(ValueError, match="duplicate"):
            verify_backup(target)
        return
    elif attack in {
        "duplicate-config",
        "unknown-config",
        "external-dsn-reference",
        "external-key-reference",
    }:
        config = json.loads((target / "config.json").read_bytes())
        if attack == "duplicate-config":
            payload = ('{"owner":"receiver",' + json.dumps(config)[1:]).encode()
        else:
            key, value = {
                "unknown-config": ("invented_setting", True),
                "external-dsn-reference": ("database_url_file", "../outside"),
                "external-key-reference": ("private_key", "../outside"),
            }[attack]
            config[key] = value
            payload = json.dumps(config).encode()
        change_file(target, manifest, "config.json", payload)
    elif attack == "owner-mismatch":
        manifest["owner"] = "other"
    elif attack == "application-mismatch":
        manifest["application"] = "another.module:configure"
    elif attack == "tls-inventory-mismatch":
        manifest["tls_private_key_included"] = True
    elif attack == "invalid-hash":
        manifest["files"]["database.dump"] = "not-a-digest"
    elif attack == "artifact-size-mismatch":
        manifest["artifact_bytes"] = 1
    elif attack == "corrupt-dump-magic":
        change_file(target, manifest, "database.dump", b"broken archive")
    elif attack == "corrupt-dump-archive":
        change_file(target, manifest, "database.dump", b"PGDMP" + b"\x00" * 100)
    elif attack == "oversized-identity":
        change_file(target, manifest, "identity.pem", b"x" * 8193)
    else:
        raise AssertionError(attack)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        verify_backup(target)


def test_missing_listed_cas_artifact_is_not_complete(app_config, tmp_path):
    name = Artifacts(app_config.artifact_directory).put(b"signed record attachment")
    target = tmp_path / "backup"
    backup(app_config, target, operator_url=os.environ["CIO_TEST_DATABASE_URL"])
    assert verify_backup(target)["structure_complete"]
    (target / "artifacts" / name).unlink()
    with pytest.raises(ValueError):
        verify_backup(target)


@pytest.mark.parametrize("missing", ["tls_ca_certificate.data", "tls-private.pem"])
def test_conditional_tls_inventory_requires_actual_files(app_config, tmp_path, missing):
    certificate, private_key = tls_fixture(tmp_path)
    config = app_config.model_copy(update={"tls_ca_certificate": certificate})
    target = tmp_path / "backup"
    backup(
        config,
        target,
        operator_url=os.environ["CIO_TEST_DATABASE_URL"],
        tls_private_key=private_key,
    )
    assert verify_backup(target)["structure_complete"]
    manifest = json.loads((target / "manifest.json").read_bytes())
    (target / missing).unlink()
    # Matching hashes for the remaining bytes cannot erase conditional references.
    manifest["files"].pop(missing)
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        verify_backup(target)
