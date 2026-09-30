import asyncio
import contextvars
import threading

import pytest

from collective_intelligence_overlay.blocking import BlockingCapacity, BlockingWork, run_blocking


async def test_cancelled_await_preserves_physical_work_and_capacity():
    entered = threading.Event()
    release = threading.Event()
    work = BlockingWork(1)

    def delayed_commit():
        entered.set()
        assert release.wait(5)
        return "committed"

    try:
        with work.scope():
            caller = asyncio.create_task(run_blocking(delayed_commit))
            assert await asyncio.to_thread(entered.wait, 5)
            caller.cancel()
            with pytest.raises(asyncio.CancelledError):
                await caller
            assert work.pending == 1
            assert await work.wait(0) is False
            with pytest.raises(BlockingCapacity):
                await run_blocking(lambda: "not submitted")
            with pytest.raises(ValueError, match="still running"):
                work.close()
            release.set()
            assert await work.wait(5)
            assert work.completed == 1 and work.failed == 0
            assert await run_blocking(lambda: "next") == "next"
    finally:
        release.set()
        await work.wait(5)
        work.close()


async def test_blocking_context_and_exceptions_remain_owner_scoped():
    value = contextvars.ContextVar("host-test-value", default="absent")
    work = BlockingWork(1)
    try:
        value.set("registered-host")
        with work.scope():
            assert await run_blocking(value.get) == "registered-host"

            def failure():
                raise RuntimeError("controlled failure")

            with pytest.raises(RuntimeError, match="controlled failure"):
                await run_blocking(failure)
        assert work.pending == 0 and work.failed == 1
        work.close()
        # Closing this host does not close another SDK caller's default executor.
        assert await run_blocking(lambda: 42) == 42
    finally:
        if not work.pending:
            work.close()


async def test_already_finished_future_releases_capacity_before_callback(monkeypatch):
    loop = asyncio.get_running_loop()
    work = BlockingWork(1)

    def immediate(executor, function, *arguments):
        future = loop.create_future()
        try:
            future.set_result(function(*arguments))
        except RuntimeError as error:
            future.set_exception(error)
        return future

    monkeypatch.setattr(loop, "run_in_executor", immediate)
    try:
        with work.scope():
            assert await run_blocking(lambda: "physical return") == "physical return"
            assert work.pending == 0 and work.completed == 1

            def failure():
                raise RuntimeError("physical failure")

            with pytest.raises(RuntimeError, match="physical failure"):
                await run_blocking(failure)
            assert work.pending == 0 and work.completed == 2 and work.failed == 1
        # Deferred callbacks must not count either completion twice.
        await asyncio.sleep(0)
        assert work.completed == 2 and work.failed == 1
    finally:
        work.close()
