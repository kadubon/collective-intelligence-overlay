"""Reject historical/version-mismatched proof without relaxing fault bounds."""

import hashlib
import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def validator(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return importlib.import_module("validate_short_protocol")


@pytest.mark.parametrize("version", ["0.4.0", "0.4.1", "0.4.2"])
def test_version_profiles_retain_identical_short_fault_requirements(validator, version):
    profile, protocol = validator.load_profile(ROOT, version)
    original, _ = validator.load_profile(ROOT, "0.4.0")
    assert profile["target_version"] == version
    assert protocol == "production-short-" + version.replace(".", "") + "-v1"
    assert (
        profile["fault_protocol"]["required_injections"]
        == (original["fault_protocol"]["required_injections"])
    )
    assert profile["fault_protocol"]["short_ci"] == original["fault_protocol"]["short_ci"]


@pytest.mark.parametrize(
    "change",
    [
        None,
        "historical-identity",
        "historical-protocol",
        "historical-runtime",
        "wrong-candidate",
        "unknown-version",
        "missing-injection",
        "too-short",
        "too-long",
        "wrong-owners",
        "assertion-failed",
        "formal-approval",
        "missing-proof",
        "changed-proof",
    ],
)
def test_candidate_version_and_complete_original_proof_required(validator, tmp_path, change):
    profile, protocol = validator.load_profile(ROOT, "0.4.1")
    hashes = {}
    for index in range(10):
        name = f"proof-{index}.json"
        content = b'{"test_fixture":true}'
        (tmp_path / name).write_bytes(content)
        hashes[name] = hashlib.sha256(content).hexdigest()
    report = {
        "profile_id": profile["profile_id"],
        "protocol": protocol,
        "required_injections": profile["fault_protocol"]["required_injections"],
        "observed_injections": list(profile["fault_protocol"]["required_injections"]),
        "elapsed_seconds": 120,
        "owners": 3,
        "assertions_passed": True,
        "formal_soak_or_release_approval": False,
        "runtime": {"distribution_version": "0.4.1"},
        "proof_sha256": hashes,
    }
    expected = "0.4.1"
    if change == "historical-identity":
        report["profile_id"] = "permissioned-single-owner-040-v1"
    elif change == "historical-protocol":
        report["protocol"] = "production-short-040-v1"
    elif change == "historical-runtime":
        report["runtime"]["distribution_version"] = "0.4.0"
    elif change == "wrong-candidate":
        expected = "0.4.0"
    elif change == "unknown-version":
        expected = "9.9.9"
    elif change == "missing-injection":
        report["observed_injections"].pop()
    elif change == "too-short":
        report["elapsed_seconds"] = 119.9
    elif change == "too-long":
        report["elapsed_seconds"] = 600
    elif change == "wrong-owners":
        report["owners"] = 2
    elif change == "assertion-failed":
        report["assertions_passed"] = False
    elif change == "formal-approval":
        report["formal_soak_or_release_approval"] = True
    elif change == "missing-proof":
        hashes.pop("proof-0.json")
    elif change == "changed-proof":
        (tmp_path / "proof-0.json").write_bytes(b"{}")
    (tmp_path / "production-fault-protocol.json").write_text(json.dumps(report))
    if change is None:
        assert validator.validate(tmp_path, ROOT, expected_version=expected) == report
    else:
        with pytest.raises(AssertionError):
            validator.validate(tmp_path, ROOT, expected_version=expected)
