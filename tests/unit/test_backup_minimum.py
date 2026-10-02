"""Checksum consistency alone does not establish a complete backup structure."""

import hashlib
import json

import pytest

from collective_intelligence_overlay.recovery import verify_backup


def test_one_arbitrary_file_is_not_a_complete_backup(tmp_path):
    payload = b"arbitrary bytes"
    (tmp_path / "arbitrary").write_bytes(payload)
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "backup_schema": "1",
                "complete": True,
                "files": {"arbitrary": hashlib.sha256(payload).hexdigest()},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        verify_backup(tmp_path)
