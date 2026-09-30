"""Require all mandatory reports to reference the single immutable candidate."""

import argparse
import hashlib
import json
from pathlib import Path

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
required = {(os, py) for os in ("Linux", "Windows") for py in ("3.12.14", "3.13.15", "3.14.7")}
observed = set()
packages = list(args.reports.rglob("package.json"))
assert len(packages) == len(required), "missing or duplicate matrix artifact reports"
for filename in packages:
    report = json.loads(filename.read_text(encoding="utf-8"))
    source = json.loads((filename.parent / "source-runtime.json").read_text(encoding="utf-8"))
    pair = (source["os"], source["patch"])
    assert pair in required and pair not in observed, pair
    observed.add(pair)
    assert report["artifacts"] == expected and report["test_scope"] == "full"
    assert report["selected"]["version"].split()[0] == source["patch"]
    for tests in (
        source["source_tests"],
        report["environments"]["agents"]["tests"],
        report["environments"]["agents-model"]["tests"],
        report["environments"]["agents-model"]["sdist_tests"],
    ):
        assert tests["tests"] > 0 and not any(tests[k] for k in ("failures", "errors", "skipped"))
    for environment in report["environments"].values():
        assert environment["runtime"]["version"].split()[0] == source["patch"]
        assert environment["child_runtimes"] and environment["supply_chain"]
    assert report["environments"]["agents-model"]["build_runtimes"]
assert observed == required
mixed = list(args.reports.rglob("mixed-python.json"))
assert len(mixed) == 1, "mandatory mixed-Python report absent"
interop = json.loads(mixed[0].read_text(encoding="utf-8"))
assert interop["artifacts"] == expected and interop["passed"] is True
assert set(interop["patches"]) == {"3.12.14", "3.14.7"}
print(json.dumps({"artifacts": expected, "matrix": sorted(observed), "mixed_python": "passed"}))
