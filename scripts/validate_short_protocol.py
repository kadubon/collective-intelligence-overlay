"""Check retained same-run fault proof completeness against the fixed profile."""

import hashlib
import json
from pathlib import Path

from native_fault_profile import load as load_profile


def validate(directory: Path, root: Path, *, expected_version: str):
    profile, protocol = load_profile(root, expected_version)
    report = json.loads((directory / "production-fault-protocol.json").read_text(encoding="utf-8"))
    assert report["profile_id"] == profile["profile_id"]
    assert report["protocol"] == protocol
    assert report["required_injections"] == profile["fault_protocol"]["required_injections"]
    assert set(report["required_injections"]) <= set(report["observed_injections"])
    bounds = profile["fault_protocol"]["short_ci"]
    assert (
        bounds["duration_seconds_min"]
        <= report["elapsed_seconds"]
        < bounds["maximum_total_seconds"]
    )
    assert report["owners"] == bounds["owners"]
    assert report["assertions_passed"] is True
    assert report["formal_soak_or_release_approval"] is False
    assert report["runtime"]["distribution_version"] == profile["target_version"]
    assert len(report["proof_sha256"]) == 10
    for name, digest in report["proof_sha256"].items():
        assert Path(name).name == name and name.endswith(".json")
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest
    return report
