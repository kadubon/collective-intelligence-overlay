"""Native killed writer followed by real PostgreSQL backup/restore."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from test_production_recovery_review import restored_database

from collective_intelligence_overlay.artifacts import Artifacts
from collective_intelligence_overlay.recovery import backup, verify_backup
from collective_intelligence_overlay.security import digest


@pytest.mark.parametrize(
    "phase", ["before-write", "during-write", "after-fsync", "before-rename", "after-rename"]
)
def test_crash_restart_backup_and_actual_restore(app_config, tmp_path, phase):
    marker = tmp_path / "writer-ready"
    helper = Path(__file__).parents[1] / "unit" / "artifact_crash_writer.py"
    process = subprocess.Popen(
        [sys.executable, str(helper), str(app_config.artifact_directory), phase, str(marker)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 15
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists()
        process.kill()
        process.communicate(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)
    restarted = app_config.artifacts()
    assert restarted.usage()["staging_files"] == 0
    target = tmp_path / "backup"
    result = backup(app_config, target, operator_url=os.environ["CIO_TEST_DATABASE_URL"])
    assert verify_backup(target)["manifest_sha256"] == result["manifest_sha256"]
    with restored_database(app_config, target / "database.dump") as restored:
        _, overlay = restored.runtime()
        try:
            assert overlay.store.owner == app_config.owner
            active = tmp_path / "restored-cas"
            shutil.copytree(target / "artifacts", active)
            assets = Artifacts(active)
            payload = b"finite original artifact" * 1000
            assert assets.usage()["files"] == int(phase == "after-rename")
            if phase == "after-rename":
                assert assets.get(digest(payload)) == payload
        finally:
            overlay.store.close()
