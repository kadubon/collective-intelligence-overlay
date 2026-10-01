"""Require all mandatory reports to reference the single immutable candidate."""

import argparse
import hashlib
import json
from pathlib import Path

from packaging.utils import parse_wheel_filename
from packaging.version import Version
from production_acceptance import require_prepublication
from runtime_matrix import combinations, manifest
from validate_short_protocol import validate as validate_short_protocol

parser = argparse.ArgumentParser()
parser.add_argument("--candidate", type=Path, required=True)
parser.add_argument("--reports", type=Path, required=True)
args = parser.parse_args()
expected = json.loads((args.candidate / "artifacts.json").read_text(encoding="utf-8"))
assert expected == {
    p.name: hashlib.sha256(p.read_bytes()).hexdigest()
    for p in (args.candidate / "dist").iterdir()
    if p.name.endswith((".whl", ".tar.gz"))
}, "candidate changed"
wheel_names = [name for name in expected if name.endswith(".whl")]
assert len(wheel_names) == 1
version = parse_wheel_filename(wheel_names[0])[1]
if version >= Version("0.4.0"):
    root = Path(__file__).resolve().parents[1]
    profile = json.loads((root / "docs/profiles/production-040.json").read_text(encoding="utf-8"))
    profile_digest = hashlib.sha256(
        json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    acceptance = json.loads(
        (root / "docs/production-040-acceptance.json").read_text(encoding="utf-8")
    )
    require_prepublication(acceptance)
    for name in ("production-acceptance.json", "production-soak.json", "matched-experiment.json"):
        evidence = list(args.reports.rglob(name))
        assert len(evidence) == 1, f"mandatory 0.4.0 evidence absent or duplicate: {name}"
        report = json.loads(evidence[0].read_text(encoding="utf-8"))
        assert report["artifacts"] == expected and report["passed"] is True
        assert report["profile_id"] == profile["profile_id"]
        assert report["profile_sha256"] == profile_digest
required = {(r["os"], r["architecture"], r["python"], r["scope"]) for r in combinations()}
observed = set()
packages = list(args.reports.rglob("package.json"))
assert len(packages) == len(required), "missing or duplicate matrix artifact reports"
for filename in packages:
    report = json.loads(filename.read_text(encoding="utf-8"))
    source = json.loads((filename.parent / "source-runtime.json").read_text(encoding="utf-8"))
    pair = (source["os"], source["architecture"], source["patch"], source["scope"])
    assert pair in required and pair not in observed, pair
    observed.add(pair)
    assert report["artifacts"] == expected and report["test_scope"] == "full"
    if version >= Version("0.4.0"):
        for directory in (
            filename.parent / "source-production-faults",
            filename.parent / "installed-production-faults" / "agents",
        ):
            short = validate_short_protocol(directory, root)
            assert short["runtime"]["python"] == source["patch"]
            assert short["runtime"]["os"] == source["os"]
            assert short["runtime"]["machine"].lower() == source["machine"].lower()
    assert report["selected"]["version"].split()[0] == source["patch"]
    assert report["selected"]["architecture"].lower() == source["machine"].lower()
    for tests in (
        source["source_tests"],
        report["environments"]["agents"]["tests"],
        report["environments"]["agents-model"]["tests"],
        report["environments"]["agents-model"]["sdist_tests"],
    ):
        assert tests["tests"] > 0 and not any(tests[k] for k in ("failures", "errors", "skipped"))
    for environment in report["environments"].values():
        assert environment["runtime"]["version"].split()[0] == source["patch"]
        assert environment["runtime"]["architecture"].lower() == source["machine"].lower()
        assert environment["child_runtimes"] and environment["supply_chain"]
        assert all(
            r["architecture"].lower() == source["machine"].lower()
            for r in environment["child_runtimes"]
        )
    assert report["environments"]["agents-model"]["build_runtimes"]
assert observed == required
if version >= Version("0.4.0"):
    upgrades = list(args.reports.rglob("installed-upgrade-032/report.json"))
    assert len(upgrades) == 1, "mandatory installed legacy live upgrade proof absent or duplicate"
    upgraded = json.loads(upgrades[0].read_text(encoding="utf-8"))
    assert upgraded["status"] == "passed"
    assert upgraded["candidate_wheel_sha256"] == expected[wheel_names[0]]
    assert upgraded["legacy_wheel_sha256"] == (
        "cc4086d5e27cbdc1d13d2d79b7438e4c787cea208b9e321b8fc0fcbc4e279ae9"
    )
    calls = upgrades[0].parent / "calls.json"
    assert hashlib.sha256(calls.read_bytes()).hexdigest() == upgraded["calls_sha256"]
    assert upgraded["offline_old_columns_and_signed_envelopes_preserved"] is True
    assert upgraded["closed_restore_external_match_explicit_resume"]["business_state"] == "matched"
    assert upgraded["new_business_reuse_after_recovery"] == "completed"
mixed = list(args.reports.rglob("mixed-python.json"))
assert len(mixed) == 1, "mandatory mixed-Python report absent"
interop = json.loads(mixed[0].read_text(encoding="utf-8"))
assert interop["artifacts"] == expected and interop["passed"] is True
assert set(interop["patches"]) == {manifest()["python"][0], manifest()["python"][-1]}
cross = list(args.reports.rglob("cross-platform.json"))
receivers = {
    (r["os"], r["architecture"], manifest()["python"][0], "full") for r in manifest()["runtimes"]
}
assert len(cross) == len(receivers), "cross-platform signature/artifact verification absent"
observed_receivers = set()
for filename in cross:
    cross_report = json.loads(filename.read_text(encoding="utf-8"))
    assert cross_report["artifacts"] == expected and cross_report["passed"] is True
    assert {tuple(r) for r in cross_report["origins"]} == required
    receiver = tuple(cross_report["receiver"])
    assert receiver in receivers and receiver not in observed_receivers
    observed_receivers.add(receiver)
assert observed_receivers == receivers
print(json.dumps({"artifacts": expected, "matrix": sorted(observed), "mixed_python": "passed"}))
