"""Verify native-produced shared artifacts; no cross-runner network/port claims."""

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

from runtime_matrix import combinations
from securesystemslib.signer import Key

import collective_intelligence_overlay as package
from collective_intelligence_overlay.opa_install import architecture
from collective_intelligence_overlay.security import Principal, verify

parser = argparse.ArgumentParser()
parser.add_argument("--candidate", type=Path, required=True)
parser.add_argument("--reports", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
assert Path(package.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()), (
    "cross-platform reader must import the installed candidate"
)
hashes = json.loads((args.candidate / "artifacts.json").read_text(encoding="utf-8"))
assert hashes == {
    p.name: hashlib.sha256(p.read_bytes()).hexdigest()
    for p in (args.candidate / "dist").iterdir()
    if p.name.endswith((".whl", ".tar.gz"))
}
required = {(r["os"], r["architecture"], r["python"], r["scope"]) for r in combinations()}
observed = set()
baseline = None
verified = 0
for path in args.reports.rglob("installed-golden.json"):
    report = json.loads(path.read_text(encoding="utf-8"))
    identity = tuple(report["identity"])
    assert identity in required and identity not in observed
    assert report["profile"] == "installed"
    observed.add(identity)
    basis = (report["fixed"], report["legacy_payloads"])
    if baseline is None:
        baseline = basis
    assert basis == baseline, "native OS/CPU changed golden serialization/digests"
    principals = {
        name: Principal(
            Key.from_dict(p["keyid"], p["key"]), p["trust_group"], frozenset(p["methods"])
        )
        for name, p in report["principals"].items()
    }
    assert len(report["signed"]) == len(report["legacy_payloads"]) > 0
    for envelope in report["signed"]:
        verify(envelope, principals)
        verified += 1
assert observed == required, "native installed producers missing"
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(
    json.dumps(
        {
            "artifacts": hashes,
            "origins": sorted(observed),
            "receiver": [platform.system(), architecture(), platform.python_version(), "full"],
            "verified_new_signatures": verified,
            "passed": True,
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
