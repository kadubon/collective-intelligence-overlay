"""Reassess original formal reports and all native operational proofs."""

import argparse
import hashlib
import json
import os
from pathlib import Path

from assess_production_experiment import assess as assess_experiment
from assess_production_soak import assess as assess_soak
from runtime_matrix import combinations
from validate_short_protocol import validate as validate_short

ROOT = Path(__file__).resolve().parents[1]


def file_manifest(directory):
    return {
        path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.name != "file-manifest.json"
    }


def check(candidate, reports):
    expected = json.loads((candidate / "artifacts.json").read_text())
    profile = json.loads((ROOT / "docs/profiles/production-040.json").read_text())
    profile_hash = hashlib.sha256(
        json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    originals = reports / "reports-production"
    actual = file_manifest(originals)
    assert actual and json.loads((originals / "file-manifest.json").read_text()) == actual
    manifest_hash = hashlib.sha256((originals / "file-manifest.json").read_bytes()).hexdigest()
    if os.environ.get("GITHUB_REF") == "refs/tags/v0.4.0":
        release = json.loads((ROOT / "docs/release-040.json").read_text())
        assert release["production_manifest_sha256"] == manifest_hash
    soak = assess_soak(originals / "soak")
    experiment = assess_experiment(originals / "experiment")
    for result, directory in ((soak, "soak"), (experiment, "experiment")):
        protocol = json.loads((originals / directory / "protocol.json").read_text())
        assert protocol["profile_id"] == profile["profile_id"]
        assert protocol["profile_sha256"] == profile_hash and protocol["artifacts"] == expected
        assert result["passed"] is True and result["artifacts"] == expected
        for name, digest in protocol["sources"].items():
            sources = (
                list(ROOT.glob("scripts/" + name))
                + list(ROOT.glob("examples/" + name))
                + list(ROOT.glob("tests/e2e/" + name))
                + list(ROOT.glob("tests/integration/" + name))
            )
            assert (
                len(sources) == 1 and hashlib.sha256(sources[0].read_bytes()).hexdigest() == digest
            )
    native = []
    for runtime in combinations():
        directory = reports / "reports-{os}-{architecture}-{python}-full".format(**runtime)
        package = json.loads((directory / "package.json").read_text())
        assert package["artifacts"] == expected
        validate_short(directory / "source-production-faults", ROOT)
        validate_short(directory / "installed-production-faults/agents", ROOT)
        tutorial = package["environments"]["agents"]["installed_tutorial"]
        assert (
            tutorial["passed"] is True and tutorial["wheel_sha256"] == expected[tutorial["wheel"]]
        )
        native.append(runtime)
    proxy = json.loads((reports / "proxy-source-review/review.json").read_text())
    assert proxy["artifacts"] == expected and proxy["review_passed"] is True
    assert len(proxy["runtimes"]) == len(native)
    acceptance = {
        "profile_id": profile["profile_id"],
        "profile_sha256": profile_hash,
        "artifacts": expected,
        "formal_original_manifest_sha256": manifest_hash,
        "native_operational_profiles": native,
        "proxy_source_review_sha256": hashlib.sha256(
            (reports / "proxy-source-review/review.json").read_bytes()
        ).hexdigest(),
        "passed": True,
        "release_approval": False,
    }
    experiment.update(profile_id=profile["profile_id"], profile_sha256=profile_hash)
    output = reports / "validated-production"
    output.mkdir(exist_ok=False)
    for name, result in (
        ("production-acceptance", acceptance),
        ("production-soak", soak),
        ("matched-experiment", experiment),
    ):
        (output / (name + ".json")).write_text(json.dumps(result, indent=2) + "\n")
    return acceptance


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--reports", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.candidate, args.reports)))
