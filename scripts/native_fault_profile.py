"""Select the declared short fault profile for the actual candidate version."""

import json
from pathlib import Path

PROFILES = {
    "0.4.0": ("production-040.json", "production-short-040-v1"),
    "0.4.1": ("native-fault-041.json", "production-short-041-v1"),
}


def load(root: Path, version: str):
    assert version in PROFILES, f"no declared native fault profile for {version}"
    filename, protocol = PROFILES[version]
    profile = json.loads((root / "docs/profiles" / filename).read_text(encoding="utf-8"))
    assert profile["target_version"] == version
    assert profile.get("protocol", protocol) == protocol
    return profile, protocol
