"""Owner-local content-addressed artifacts; remote references are never opened."""

from pathlib import Path

from .security import digest


class Artifacts:
    def __init__(self, directory: Path, max_bytes: int = 1048576) -> None:
        self.directory = directory.resolve()
        self.max_bytes = max_bytes
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)

    def put(self, value: bytes) -> str:
        if len(value) > self.max_bytes:
            raise ValueError("artifact too large")
        name = digest(value)
        target = self.directory / name
        if target.is_symlink():
            raise ValueError("symlink artifact")
        try:
            with target.open("xb") as file:
                file.write(value)
        except FileExistsError:
            if self.get(name) != value:
                raise ValueError("artifact collision") from None
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
