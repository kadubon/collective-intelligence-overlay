"""Native producers of shared signed artifacts, using installed public APIs in wheel CI."""

import base64
import json
import os
import platform
import sys
from pathlib import Path
from types import SimpleNamespace

from python_interop_application import fixed, legacy

import collective_intelligence_overlay as package
from collective_intelligence_overlay.opa_install import architecture
from collective_intelligence_overlay.security import record_adapter, verify


def test_platform_golden_payloads_artifacts_and_new_signatures(identities, principals):
    envelopes, hashes = legacy()
    values = fixed(SimpleNamespace(owner="receiver", execution_environment={"application": "1"}))
    signed = []
    for envelope in envelopes:
        record = record_adapter.validate_json(base64.b64decode(envelope["payload"]))
        signed.append(identities[record.issuer].sign(record))
        assert verify(signed[-1], principals) == record
    output = os.environ.get("CIO_GOLDEN_REPORT_DIR")
    if output:
        profile = (
            "installed"
            if Path(package.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
            else "source"
        )
        root = Path(output)
        root.mkdir(parents=True, exist_ok=True)
        report = {
            "identity": [platform.system(), architecture(), platform.python_version(), "full"],
            "profile": profile,
            "import": package.__file__,
            "executable": sys.executable,
            "fixed": values,
            "legacy_payloads": hashes,
            "signed": signed,
            "principals": {
                name: {
                    "keyid": p.key.keyid,
                    "key": p.key.to_dict(),
                    "trust_group": p.trust_group,
                    "methods": sorted(p.methods),
                }
                for name, p in principals.items()
            },
        }
        (root / (profile + "-golden.json")).write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
