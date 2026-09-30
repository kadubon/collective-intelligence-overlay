"""Track bounded standard thread-pool work through cancellation and shutdown."""

from __future__ import annotations

import asyncio
import contextvars
import functools
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any


class BlockingCapacity(ValueError):
    """No additional physical blocking work may be submitted in this owner scope."""


class BlockingWork:
    """A standard executor, with no unbounded submission queue or custom scheduler.

    Await cancellation does not cancel a running database transaction. Its future
    remains tracked until the physical function returns. Callers inspect pending
    work and cannot claim completion from a cancelled coroutine.
    """

    def __init__(self, workers: int = 8) -> None:
        if not 1 <= workers <= 32:
            raise ValueError("invalid blocking worker bound")
        self.workers = workers
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="cio-owner")
        self._pending: set[asyncio.Future[Any]] = set()
        self._closed = False
        self.completed = self.failed = 0
        self.elapsed_seconds = 0.0

    @property
    def pending(self) -> int:
        return len(self._pending)

    @contextmanager
    def scope(self) -> Iterator[None]:
        token = _current.set(self)
        try:
            yield
        finally:
            _current.reset(token)

    async def run[**P, T](self, function: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
        if self._closed or self.pending >= self.workers:
            raise BlockingCapacity("OWNER_BLOCKING_WORK_LIMIT")
        context = contextvars.copy_context()
        started = time.perf_counter()
        future = asyncio.get_running_loop().run_in_executor(
            self._executor, context.run, functools.partial(function, *args, **kwargs)
        )
        self._pending.add(future)

        def finished(done: asyncio.Future[T]) -> None:
            self._pending.discard(done)
            self.completed += 1
            self.elapsed_seconds += time.perf_counter() - started
            if done.cancelled() or done.exception() is not None:
                self.failed += 1

        future.add_done_callback(finished)
        return await asyncio.shield(future)

    async def wait(self, seconds: float) -> bool:
        if not 0 <= seconds <= 30:
            raise ValueError("invalid physical work wait bound")
        if self._pending:
            await asyncio.wait(tuple(self._pending), timeout=seconds)
        return self.pending == 0

    def close(self) -> None:
        if self.pending:
            raise ValueError("physical blocking work still running")
        self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=False)


_current: contextvars.ContextVar[BlockingWork | None] = contextvars.ContextVar(
    "owner_blocking_work", default=None
)


async def run_blocking[**P, T](function: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """Existing SDK use retains asyncio behavior; a host supplies its bounded scope."""
    scope = _current.get()
    if scope is None:
        return await asyncio.to_thread(function, *args, **kwargs)
    return await scope.run(function, *args, **kwargs)
