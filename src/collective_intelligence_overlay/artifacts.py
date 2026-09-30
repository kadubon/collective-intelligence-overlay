"""Owner-local content-addressed artifacts; remote references are never opened."""

import os
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

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

    @contextmanager
    def _lock(self) -> Iterator[None]:
        # Native OS advisory locks serialize quota checks and atomic publication.
        # The empty lock is outside the CAS; it is not a business/result ledger.
        lock_path = self.directory.with_name(self.directory.name + ".lock")
        if lock_path.is_symlink():
            raise ValueError("unsafe artifact lock")
        with lock_path.open("a+b") as lock:
            os.chmod(lock_path, 0o600)
            if lock.seek(0, 2) == 0:
                lock.write(b"0")
                lock.flush()
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
                yield
            finally:
                if sys.platform == "win32":
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def usage(self) -> dict[str, int | bool]:
        with self._lock():
            return self._usage()

    def _usage(self) -> dict[str, int | bool]:
        total = count = 0
        started = time.monotonic()
        for source in self.directory.iterdir():
            count += 1
            if count > self.max_files or time.monotonic() - started > 5:
                raise ValueError("artifact inventory capacity/time exceeded")
            if source.is_symlink() or not source.is_file():
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
            if (
                int(usage["bytes"]) + len(value) > self.capacity_bytes
                or int(usage["files"]) >= self.max_files
            ):
                raise ValueError("ARTIFACT_CAPACITY_EXCEEDED")
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=self.directory, prefix=".write-", delete=False
                ) as file:
                    temporary = Path(file.name)
                    os.chmod(temporary, 0o600)
                    file.write(value)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(temporary, target)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        return name

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
