import concurrent.futures
import subprocess
import sys
import time
from pathlib import Path

import pytest

from collective_intelligence_overlay.artifacts import Artifacts
from collective_intelligence_overlay.security import digest


@pytest.mark.parametrize(
    "phase", ["before-write", "during-write", "after-fsync", "before-rename", "after-rename"]
)
def test_killed_writer_restart_preserves_only_complete_public_artifact(tmp_path, phase):
    directory = tmp_path / "published"
    ready = tmp_path / "ready"
    process = subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).with_name("artifact_crash_writer.py")),
            str(directory),
            phase,
            str(ready),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 15
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), process.poll()
        process.kill()  # No finally/unlink, real native process termination.
        process.communicate(timeout=10)
        assert process.returncode != 0
        artifacts = Artifacts(directory)
        payload = b"finite original artifact" * 1000
        name = digest(payload)
        if phase == "after-rename":
            assert list(directory.iterdir()) == [directory / name]
            assert artifacts.get(name) == payload
        else:
            assert list(directory.iterdir()) == []
        usage = artifacts.usage()
        assert usage["staging_files"] == 0 and usage["staging_bytes"] == 0
        assert artifacts.put(payload) == name
        assert artifacts.get(name) == payload
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)


def test_legacy_write_quarantine_never_deletes_or_promotes_bytes(tmp_path):
    directory = tmp_path / "published"
    artifacts = Artifacts(directory)
    name = artifacts.put(b"canonical signed attachment")
    legacy = directory / ".write-oldwrite"
    legacy.write_bytes(b"partial historical write")
    restarted = Artifacts(directory)
    assert not legacy.exists() and restarted.get(name) == b"canonical signed attachment"
    quarantined = [p for p in restarted.staging_directory.iterdir() if p.name.startswith("legacy-")]
    assert len(quarantined) == 1 and quarantined[0].read_bytes() == b"partial historical write"
    usage = restarted.usage()
    assert usage["files"] == 1 and usage["bytes"] == len(b"canonical signed attachment")
    assert usage["legacy_quarantined_files"] == 1
    assert usage["staging_bytes"] == len(b"partial historical write")
    assert restarted.recover_staging()["abandoned_writes_removed"] == 0
    assert quarantined[0].exists()


def test_active_writer_lock_blocks_reclamation_and_concurrent_publication(tmp_path):
    directory = tmp_path / "published"
    artifacts = Artifacts(directory)
    ready = tmp_path / "ready"
    process = subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).with_name("artifact_crash_writer.py")),
            str(directory),
            "during-write",
            str(ready),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 15
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists()
        before = [p for p in artifacts.staging_directory.iterdir() if p.name.startswith(".write-")]
        assert len(before) == 1
        with pytest.raises(TimeoutError, match="lock time bound"):
            artifacts.recover_staging()
        assert before[0].exists()
    finally:
        process.kill()
        process.communicate(timeout=10)
    artifacts.recover_staging()
    assert not before[0].exists()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        values = list(
            pool.map(lambda _: Artifacts(directory).put(b"same complete content"), range(8))
        )
    assert len(set(values)) == 1 and artifacts.usage()["files"] == 1


def test_unknown_staging_is_rejected_without_cleanup(tmp_path):
    artifacts = Artifacts(tmp_path / "published")
    unknown = artifacts.staging_directory / "unowned"
    unknown.write_bytes(b"retain")
    with pytest.raises(ValueError, match="unsafe"):
        artifacts.recover_staging()
    assert unknown.read_bytes() == b"retain"


def test_staging_symlink_is_rejected_without_following_or_deleting_target(tmp_path):
    artifacts = Artifacts(tmp_path / "published")
    outside = tmp_path / "retained-original"
    outside.write_bytes(b"retain original")
    link = artifacts.staging_directory / ".write-testlink"
    link.symlink_to(outside)
    with pytest.raises(ValueError, match="unsafe"):
        artifacts.recover_staging()
    assert link.is_symlink() and outside.read_bytes() == b"retain original"


def test_quarantine_capacity_cannot_be_silently_ignored(tmp_path):
    artifacts = Artifacts(tmp_path / "published", max_bytes=10, capacity_bytes=10, max_files=2)
    (artifacts.directory / ".write-legacy0").write_bytes(b"12345678")
    artifacts.recover_staging()
    with pytest.raises(ValueError, match="STAGING_CAPACITY"):
        artifacts.put(b"four")
    assert artifacts.usage()["files"] == 0 and artifacts.usage()["staging_bytes"] == 8
