"""Owner-local content-addressed artifacts; remote references are never opened."""

import os
import re
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from .security import digest


class Artifacts:
    def __init__(
        self,
        directory: Path,
        max_bytes: int = 1048576,
        capacity_bytes: int = 256 * 1048576,
        max_files: int = 65536,
    ) -> None:
        if not 1 <= max_bytes <= capacity_bytes or not 1 <= max_files <= 65536:
            raise ValueError("invalid artifact capacity")
        self.directory = directory.resolve()
        self.max_bytes = max_bytes
        self.capacity_bytes, self.max_files = capacity_bytes, max_files
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.staging_directory = self.directory.with_name(self.directory.name + ".staging")
        self.recover_staging()

    def _staging(self) -> None:
        """Separate, same-volume private staging, identified before any reclamation."""
        if self.staging_directory.is_symlink():
            raise ValueError("unsafe artifact staging")
        self.staging_directory.mkdir(exist_ok=True, mode=0o700)
        if self.staging_directory.stat().st_dev != self.directory.stat().st_dev:
            raise ValueError("artifact staging must share the published filesystem")
        marker = self.staging_directory / ".cio-staging"
        expected = b"cio-cas-staging-v1\n"
        if not marker.exists():
            if next(self.staging_directory.iterdir(), None) is not None:
                raise ValueError("unowned nonempty artifact staging")
            with marker.open("xb") as output:
                os.chmod(marker, 0o600)
                output.write(expected)
                output.flush()
                os.fsync(output.fileno())
            self._sync_directory(self.staging_directory)
        if marker.is_symlink() or not marker.is_file() or marker.stat().st_size != len(expected):
            raise ValueError("unsafe artifact staging marker")
        if marker.read_bytes() != expected:
            raise ValueError("unowned artifact staging")

    def recover_staging(self) -> dict[str, int]:
        """Under the writer lock, discard abandoned new writes and quarantine legacy writes.

        Cooperating old and new writers hold this same lock through publication.
        Canonical digest files are never reclaimed. Legacy bytes remain outside CAS
        for operator inspection; no incomplete file is promoted to an artifact.
        """
        with self._lock():
            self._staging()
            self._staging_usage()
            recovered = quarantined = 0
            for source in self.staging_directory.iterdir():
                if re.fullmatch(r"\.write-[a-z0-9_-]{6,64}", source.name):
                    # The marked directory, finite regular-file check and exclusive
                    # writer lock establish ownership; this is not recursive cleanup.
                    source.unlink()
                    recovered += 1
            started = time.monotonic()
            for count, source in enumerate(self.directory.iterdir(), 1):
                if count > self.max_files or time.monotonic() - started > 5:
                    raise ValueError("artifact recovery capacity/time exceeded")
                if not re.fullmatch(r"\.write-[a-z0-9_-]{6,64}", source.name):
                    continue
                if (
                    source.is_symlink()
                    or not source.is_file()
                    or source.stat().st_size > self.max_bytes
                ):
                    raise ValueError("unsafe legacy artifact staging")
                usage = self._staging_usage()
                if (
                    usage["files"] >= self.max_files
                    or usage["bytes"] + source.stat().st_size > self.capacity_bytes
                ):
                    raise ValueError("ARTIFACT_STAGING_CAPACITY_EXCEEDED")
                target = self.staging_directory / ("legacy-" + source.name + "-" + uuid4().hex)
                os.replace(source, target)
                quarantined += 1
            if recovered or quarantined:
                self._sync_directory(self.staging_directory)
                self._sync_directory(self.directory)
            return {"abandoned_writes_removed": recovered, "legacy_writes_quarantined": quarantined}

    def _staging_usage(self) -> dict[str, int]:
        total = count = legacy = 0
        started = time.monotonic()
        for source in self.staging_directory.iterdir():
            if source.name == ".cio-staging":
                continue
            count += 1
            if count > self.max_files or time.monotonic() - started > 5:
                raise ValueError("artifact staging capacity/time exceeded")
            if (
                source.is_symlink()
                or not source.is_file()
                or source.stat().st_size > self.max_bytes
                or not re.fullmatch(
                    r"(?:\.write-[a-z0-9_-]{6,64}|legacy-\.write-[a-z0-9_-]{6,64}-[a-f0-9]{32})",
                    source.name,
                )
            ):
                raise ValueError("unsafe artifact staging inventory")
            total += source.stat().st_size
            legacy += int(source.name.startswith("legacy-"))
            if total > self.capacity_bytes:
                raise ValueError("ARTIFACT_STAGING_CAPACITY_EXCEEDED")
        return {"bytes": total, "files": count, "legacy_files": legacy}

    @contextmanager
    def _lock(self) -> Iterator[None]:
        # Native OS advisory locks serialize quota checks and atomic publication.
        # The empty lock is outside the CAS; it is not a business/result ledger.
        lock_path = self.directory.with_name(self.directory.name + ".lock")
        if lock_path.is_symlink():
            raise ValueError("unsafe artifact lock")
        with lock_path.open("a+b") as lock:
            os.chmod(lock_path, 0o600)
            deadline = time.monotonic() + 5
            while True:
                try:
                    if sys.platform == "win32":
                        import msvcrt

                        lock.seek(0)
                        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("artifact lock time bound exceeded") from None
                    time.sleep(0.01)
            try:
                # Windows permits locking beyond EOF. Initialize only while
                # holding that range: another creator can observe an empty file
                # before the first process flushes its initial byte.
                if lock.seek(0, 2) == 0:
                    lock.write(b"0")
                    lock.flush()
                yield
            finally:
                if sys.platform == "win32":
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def usage(self) -> dict[str, int | bool]:
        with self._lock():
            published = self._usage()
            staged = self._staging_usage()
            return published | {
                "staging_bytes": staged["bytes"],
                "staging_files": staged["files"],
                "legacy_quarantined_files": staged["legacy_files"],
                "staging_capacity_warning": staged["bytes"] >= self.capacity_bytes * 9 // 10,
            }

    def _usage(self) -> dict[str, int | bool]:
        total = count = 0
        started = time.monotonic()
        for source in self.directory.iterdir():
            count += 1
            if count > self.max_files or time.monotonic() - started > 5:
                raise ValueError("artifact inventory capacity/time exceeded")
            if (
                source.is_symlink()
                or not source.is_file()
                or not re.fullmatch(r"[a-f0-9]{64}", source.name)
            ):
                raise ValueError("unsafe artifact inventory")
            total += source.stat().st_size
        return {
            "bytes": total,
            "files": count,
            "capacity_bytes": self.capacity_bytes,
            "capacity_warning": total >= self.capacity_bytes * 9 // 10,
            "automatic_signed_history_purge": False,
        }

    def put(self, value: bytes) -> str:
        if len(value) > self.max_bytes:
            raise ValueError("artifact too large")
        name = digest(value)
        target = self.directory / name
        if target.is_symlink():
            raise ValueError("symlink artifact")
        with self._lock():
            if target.exists():
                if self.get(name) != value:
                    raise ValueError("artifact collision")
                return name
            usage = self._usage()
            staged = self._staging_usage()
            if (
                int(usage["bytes"]) + len(value) > self.capacity_bytes
                or int(usage["files"]) >= self.max_files
            ):
                raise ValueError("ARTIFACT_CAPACITY_EXCEEDED")
            if (
                staged["bytes"] + len(value) > self.capacity_bytes
                or staged["files"] >= self.max_files
            ):
                raise ValueError("ARTIFACT_STAGING_CAPACITY_EXCEEDED")
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=self.staging_directory, prefix=".write-", delete=False
                ) as file:
                    temporary = Path(file.name)
                    os.chmod(temporary, 0o600)
                    file.write(value)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temporary, target)
                self._sync_directory(self.directory)
                self._sync_directory(self.staging_directory)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        return name

    @staticmethod
    def _sync_directory(directory: Path) -> None:
        # Windows has no portable Python directory fsync. File fsync + atomic
        # rename is supported there, but power-loss durability is not asserted.
        if sys.platform != "win32":
            descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    def get(self, name: str) -> bytes:
        if len(name) != 64 or any(c not in "0123456789abcdef" for c in name):
            raise ValueError("invalid artifact digest")
        target = self.directory / name
        if target.is_symlink() or target.stat().st_size > self.max_bytes:
            raise ValueError("unsafe artifact")
        value = target.read_bytes()
        if digest(value) != name:
            raise ValueError("artifact digest mismatch")
        return value
