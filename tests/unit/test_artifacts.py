import base64
import json

import pytest
from securesystemslib.exceptions import VerificationError

from collective_intelligence_overlay.artifacts import Artifacts
from collective_intelligence_overlay.security import verify


def test_artifact_boundaries(tmp_path):
    artifacts = Artifacts(tmp_path, max_bytes=10)
    name = artifacts.put(b"private")
    assert artifacts.put(b"private") == name
    assert artifacts.get(name) == b"private"
    with pytest.raises(ValueError, match="too large"):
        artifacts.put(b"x" * 11)
    with pytest.raises(ValueError, match="invalid"):
        artifacts.get("../secret")
    (tmp_path / name).write_bytes(b"altered")
    with pytest.raises(ValueError, match="mismatch"):
        artifacts.get(name)


def test_valid_json_with_changed_subject_fails_signature(identities, principals, records):
    signed = identities["producer"].sign(records[0])
    payload = json.loads(base64.b64decode(signed["payload"]))
    payload["subject"]["digest"] = "a" * 64
    signed["payload"] = base64.b64encode(json.dumps(payload).encode()).decode()
    with pytest.raises(VerificationError):
        verify(signed, principals)


def test_another_issuers_signature_is_not_accepted(identities, principals, records):
    signed = identities["producer"].sign(records[0])
    other = records[0].model_copy(update={"issuer": "other"})
    signed["signatures"] = identities["other"].sign(other)["signatures"]
    with pytest.raises(VerificationError):
        verify(signed, principals)
