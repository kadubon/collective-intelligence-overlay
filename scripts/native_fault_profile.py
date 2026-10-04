"""Select the declared short fault profile for the actual candidate version."""

import json
from pathlib import Path

PROFILES = {
    "0.4.0": ("production-040.json", "production-short-040-v1"),
    "0.4.1": ("native-fault-041.json", "production-short-041-v1"),
    "0.4.2": ("native-fault-042.json", "production-short-042-v1"),
    "0.4.3": ("native-fault-043.json", "production-short-043-v1"),
    "0.4.4": ("native-fault-044.json", "production-short-044-v1"),
    "0.5.0": ("native-fault-050.json", "production-short-050-v1"),
    "0.5.1": ("native-fault-051.json", "production-short-051-v1"),
}


def load(root: Path, version: str):
    assert version in PROFILES, f"no declared native fault profile for {version}"
    filename, protocol = PROFILES[version]
    profile = json.loads((root / "docs/profiles" / filename).read_text(encoding="utf-8"))
    assert profile["target_version"] == version
    assert profile.get("protocol", protocol) == protocol
    return profile, protocol
