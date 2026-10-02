"""Real Executor worker; fault injection pauses only after durable boundaries."""

import asyncio
import json
import sys
import time
from pathlib import Path

from remote_call_application import context, parent_binding, register_consumer, register_parent

from collective_intelligence_overlay.config import load_config
from collective_intelligence_overlay.invocations import Executor, Reservation


def register_nested(registry, proxy, execution_context, identity):
    child = register_parent(registry, proxy, execution_context)
    child_executor = Executor(registry, identity, Reservation(seconds=4))

    async def nested(arguments):
        result = await child_executor.invoke(
            "local-child", child.id, child.digest, arguments, execution_context
        )
        if result["state"] != "completed":
            raise TimeoutError("child result remains uncertain")
        return result["result"]

    parent = parent_binding(child, nested, name="nested-parent")
    registry.register_local(parent, nested, lambda _: True)
    return parent, child, child_executor


async def run(config_path, marker, stage, legacy=False, default_limit=False, long_lease=False):
    config = load_config(config_path)
    identity, registry, proxy = register_consumer(config)
    execution_context = context(config)
    if stage.startswith("nested"):
        parent, _, child_executor = register_nested(registry, proxy, execution_context, identity)
    else:
        parent = register_parent(registry, proxy, execution_context)
    executor = Executor(
        registry,
        identity,
        Reservation(seconds=30 if long_lease else 4, max_unresolved=32 if default_limit else 1),
    )
    if legacy:
        executor.store.identity = executor.store.registry = None

    def pause(claim):
        marker.write_text(
            json.dumps(
                {
                    "stage": stage,
                    "caller": claim["caller"],
                    "id": claim["id"],
                    "fence": claim["fence"],
                }
            ),
            encoding="utf-8",
        )
        # The parent test must positively terminate this process. A timeout or
        # cancellation alone is never used as proof of physical quiescence.
        time.sleep(60)

    if stage == "dispatch":
        original = executor.store.dispatched

        def dispatched(claim):
            original(claim)
            pause(claim)

        executor.store.dispatched = dispatched
    else:
        target_executor = child_executor if stage == "nested" else executor
        original_finish = target_executor.store.finish

        def finish(claim, result, identity, event, **kwargs):
            if result is not None or stage == "lost-response":
                pause(claim)
            return original_finish(claim, result, identity, event, **kwargs)

        target_executor.store.finish = finish
    try:
        await executor.invoke(
            "receiptless-" + stage, parent.id, parent.digest, {"value": 7}, execution_context
        )
    finally:
        registry.overlay.store.close()


if __name__ == "__main__":
    asyncio.run(
        run(
            Path(sys.argv[1]),
            Path(sys.argv[2]),
            sys.argv[3],
            "legacy" in sys.argv[4:],
            "default-limit" in sys.argv[4:],
            "long-lease" in sys.argv[4:],
        )
    )
