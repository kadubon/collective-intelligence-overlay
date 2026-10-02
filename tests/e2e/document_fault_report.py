"""Retain bounded public proof files from the actual nineteen-injection protocol."""

import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import sys
from pathlib import Path

REQUIRED = (
    "owner process kill",
    "database physical disconnect",
    "provider stop",
    "delayed response and timeout",
    "duplicate response/request",
    "owner Python clock offset plus DB clock checks",
    "bad signature",
    "evidence withdrawal",
    "execution and unresolved capacity exhaustion",
    "budget exhaustion",
    "checker failure and checker unavailability",
    "backup interruption",
    "restored intake closed until verification/sync/reconciliation",
    "new effect request during drain",
    "duplicate owner boot",
    "HTTP 429 and 503 with Retry-After",
    "routine key rotation",
    "compromised historical key",
    "protected trial regression",
)
FILES = (
    "core-fault-observations.json",
    "owned-fault-observations.json",
    "network-recovery-observations.json",
    "pressure-observations.json",
    "http-pressure-observations.json",
    "key-observations.json",
    "checker-outage-observations.json",
    "evidence-withdrawal-observations.json",
)


def write_report(root, elapsed):
    # Tests run outside the checkout against the installed wheel. Only the
    # validation helper path is added; package/application source stays absent.
    scripts = str(Path(__file__).resolve().parents[2] / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from native_fault_profile import load as load_profile

    version = importlib.metadata.version("collective-intelligence-overlay")
    profile, protocol = load_profile(Path(__file__).resolve().parents[2], version)
    bounds = profile["fault_protocol"]["short_ci"]
    assert list(REQUIRED) == profile["fault_protocol"]["required_injections"]
    assert bounds["duration_seconds_min"] <= elapsed < bounds["maximum_total_seconds"]
    data = {name: json.loads((root / name).read_text(encoding="utf-8")) for name in FILES}
    observations = [
        item
        for value in data.values()
        for item in (value if isinstance(value, list) else [value])
        if "injection" in item
    ]
    labels = {item["injection"] for item in observations}
    assert {"execution capacity exhaustion", "unresolved capacity exhaustion"} <= labels
    labels.add("execution and unresolved capacity exhaustion")
    assert "checker unavailability" in labels
    assert any(
        item["injection"] == "protected trial regression"
        and item["evidence"]["verdict"] == "FAIL"
        and item["promoted"] is False
        for item in observations
    )
    labels.add("checker failure and checker unavailability")
    recovered = [item for item in data["network-recovery-observations.json"] if "case" in item]
    assert {item["case"] for item in recovered} == {"old", "current"}
    labels.add("restored intake closed until verification/sync/reconciliation")
    assert set(REQUIRED) <= labels, set(REQUIRED) - labels
    hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in FILES}
    # Retain actual recovery-query proof artifacts, never private homes, DSNs,
    # key bundles or backup secret archives.
    for case in recovered:
        digest = case["review"]["observation_digest"]
        source = root / ("restored-" + case["case"]) / "artifacts" / digest
        name = "recovery-proof-" + case["case"] + ".json"
        shutil.copy2(source, root / name)
        hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    report = {
        "profile_id": profile["profile_id"],
        "protocol": protocol,
        "elapsed_seconds": elapsed,
        "owners": bounds["owners"],
        "runtime": {
            "os": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "executable": sys.executable,
            "distribution_version": version,
        },
        "required_injections": list(REQUIRED),
        "observed_injections": sorted(labels),
        "proof_sha256": hashes,
        "assertions_passed": True,
        "formal_soak_or_release_approval": False,
    }
    path = root / "production-fault-protocol.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    destination = os.environ.get("CIO_PRODUCTION_FAULT_REPORT_DIR")
    if destination:
        output = Path(destination)
        output.mkdir(parents=True, exist_ok=True)
        for name in (*hashes, path.name):
            shutil.copy2(root / name, output / name)
