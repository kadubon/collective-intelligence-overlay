"""Require all mandatory reports to reference the single immutable candidate."""

import argparse
import hashlib
import json
from pathlib import Path

from runtime_matrix import combinations, manifest

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
