"""Close the reviewed pg8000 transport buffer even when protocol close fails.

pg8000 1.31.5 drops its buffered file without closing it after a failed flush.
Keep that resource alive until explicit close, preventing a later unraisable
Windows socket error. This isolated compatibility access is not a driver fork.
"""

from pg8000.dbapi import Connection  # type: ignore[import-untyped]


class ManagedConnection(Connection):  # type: ignore[misc]
    def close(self) -> None:
        stream = getattr(self, "_sock", None)
        failed = False
        try:
            super().close()
        except BaseException:
            failed = True
            raise
        finally:
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    # The original close failure still propagates. Explicit
                    # file close releases its resource even when flush fails.
                    if not failed:
                        raise
