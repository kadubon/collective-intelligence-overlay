import subprocess
import sys
import time

import pytest

from collective_intelligence_overlay.artifacts import Artifacts


def test_capacity_preserves_original_and_same_content_replay(tmp_path):
    artifacts = Artifacts(tmp_path / "cas", max_bytes=4, capacity_bytes=8, max_files=2)
    original = artifacts.put(b"abcd")
    second = artifacts.put(b"efgh")
    assert artifacts.usage()["capacity_warning"]
    assert artifacts.put(b"abcd") == original
    with pytest.raises(ValueError, match="CAPACITY_EXCEEDED"):
        artifacts.put(b"i")
    assert artifacts.get(original) == b"abcd" and artifacts.get(second) == b"efgh"
    assert set(p.name for p in artifacts.directory.iterdir()) == {original, second}


def test_actual_processes_cannot_race_quota_or_partial_publication(tmp_path):
    directory = tmp_path / "shared-cas"
    artifacts = Artifacts(directory, max_bytes=4096, capacity_bytes=6144)
    script = """
import sys
from pathlib import Path
from collective_intelligence_overlay.artifacts import Artifacts
a = Artifacts(Path(sys.argv[1]), max_bytes=4096, capacity_bytes=6144)
try:
    a.put(sys.argv[2].encode() * 4096)
except ValueError as exc:
    assert str(exc) == 'ARTIFACT_CAPACITY_EXCEEDED'
    raise SystemExit(2)
"""
    children = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(directory), value],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for value in ("a", "b", "c", "d")
    ]
    try:
        for child in children:
            output, errors = child.communicate(timeout=15)
            assert not output and not errors
        assert sorted(child.returncode for child in children) == [0, 2, 2, 2]
        assert artifacts.usage()["bytes"] == 4096
        files = list(directory.iterdir())
        assert len(files) == 1 and len(artifacts.get(files[0].name)) == 4096
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)


def test_empty_native_lock_is_initialized_only_by_its_holder(tmp_path):
    # Hold the first byte of a genuinely empty file, as a creator can do before
    # initialization. The other process must wait instead of writing that byte.
    artifacts = Artifacts(tmp_path / "held-cas", max_bytes=16, capacity_bytes=32)
    lock_path = tmp_path / "held-cas.lock"
    ready = tmp_path / "ready"
    script = """
import sys
from pathlib import Path
from collective_intelligence_overlay.artifacts import Artifacts
a = Artifacts(Path(sys.argv[1]), max_bytes=16, capacity_bytes=32)
Path(sys.argv[2]).touch()
a.put(b'original')
"""
    child = None
    with lock_path.open("a+b") as lock:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            child = subprocess.Popen(
                [sys.executable, "-c", script, str(artifacts.directory), str(ready)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            deadline = time.monotonic() + 5
            while not ready.exists():
                assert child.poll() is None and time.monotonic() < deadline
                time.sleep(0.01)
            time.sleep(0.1)
            assert child.poll() is None
            assert lock_path.stat().st_size == 0
        finally:
            if sys.platform == "win32":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            if child is not None:
                try:
                    output, errors = child.communicate(timeout=10)
                    assert child.returncode == 0 and not output and not errors
                finally:
                    if child.poll() is None:
                        child.kill()
                        child.wait(timeout=5)
    assert artifacts.usage()["files"] == 1
