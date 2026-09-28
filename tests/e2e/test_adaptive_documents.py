import asyncio
import os
import sys
from pathlib import Path

import httpx
import pytest
from a2a.client import AgentCardResolutionError

from collective_intelligence_overlay.adapters.a2a import send
from collective_intelligence_overlay.config import Config
from collective_intelligence_overlay.demo import initialize


@pytest.mark.parametrize(
    "training_text", ["calibration vocabulary", "a longer calibration document"]
)
async def test_peer_selected_document_formation_restart_and_withdrawal(
    tmp_path, policy, monkeypatch, training_text
):
    url = os.environ.get("CIO_TEST_DATABASE_URL")
    if not url:
        pytest.skip("real PostgreSQL required")
    examples = Path(__file__).parents[2] / "examples"
    monkeypatch.syspath_prepend(str(examples))
    from adaptive_documents import ENVIRONMENT, configure_application, write_json

    opa = await asyncio.to_thread(os.path.abspath, policy.binary)
    configs = await asyncio.to_thread(initialize, tmp_path / "application", url, opa)
    for name, original in configs.items():
        config = original.model_copy(
            update={"execution_environment": ENVIRONMENT, "max_seconds": 300}
        )
        configs[name] = config
        data = config.model_dump(mode="json")
        data["database_url"] = config.database_url.get_secret_value()
        write_json(config.private_key.parent / "config.json", data)
    configure_application(configs, training_text)
    identities = {}
    for name, config in configs.items():
        identity, overlay = config.runtime()
        identities[name] = identity
        overlay.store.close()
    processes = {}
    logs = []

    async def call(owner, **data):
        return await send(configs[owner], identities[owner], owner, data)

    async def start(name):
        config: Config = configs[name]
        log_path = config.private_key.parent / "adaptive.log"
        log = log_path.open("ab")
        logs.append(log)
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(examples / "adaptive_documents.py"),
            "--config",
            str(config.private_key.parent / "config.json"),
            cwd=tmp_path,
            stdout=log,
            stderr=log,
        )
        processes[name] = process
        async with asyncio.timeout(25):
            while True:
                if process.returncode is not None:
                    raise AssertionError(log_path.read_text(encoding="utf-8"))
                try:
                    await call(name, operation="metrics")
                    return
                except (httpx.HTTPError, ConnectionError, AgentCardResolutionError):
                    await asyncio.sleep(0.1)

    async def stop(name):
        process = processes[name]
        if process.returncode is None:
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 10)
        except TimeoutError:
            process.kill()
            await process.wait()

    async def sync(owner, source):
        assert (await call(owner, operation="sync", peer=source, page_size=4))["complete"]

    try:
        async with asyncio.timeout(180):
            for name in configs:
                await start(name)
            assert len({process.pid for process in processes.values()}) == 3
            # Initial checked primitives are fixtures. No later work, candidate,
            # calibration alternative or verification order is selected here.
            words = await call("producer", operation="describe", name="words")
            checked = await call(
                "verifier",
                operation="verify",
                attempt="initial-words",
                provider="producer",
                name="words",
                arguments={"text": "initial primitive check"},
            )
            assert checked["evidence"]["verdict"] == "PASS"
            await sync("producer", "verifier")
            await sync("receiver", "producer")
            await sync("receiver", "verifier")
            for name, arguments in (
                ("render", {"words": 7}),
                ("remote-words", {"text": "remote primitive check"}),
            ):
                checked = await call(
                    "verifier",
                    operation="verify",
                    attempt="initial-" + name,
                    provider="receiver",
                    name=name,
                    arguments=arguments,
                )
                assert checked["evidence"]["verdict"] == "PASS"
            await sync("receiver", "verifier")
            first = await call("receiver", operation="adaptive-run", max_steps=1)
            assert first["reason"] == "step_limit" and len(first["history"]) == 1
            c3 = (await call("receiver", operation="describe", name="report"))["binding"]
            before_check = await call(
                "receiver",
                operation="invoke",
                invocation_id="unverified-c3",
                binding_id=c3["id"],
                binding_digest=first["history"][0]["formation"]["formation"]["binding_digest"],
                arguments={"text": "ordinary use must wait for independent checking"},
            )
            assert before_check["state"] == "unknown"
            # Resume with a formed but still unverified C3. The harness supplies
            # no next-task instruction after restarting the owner process.
            await stop("receiver")
            await start("receiver")
            result = await call("receiver", operation="adaptive-run", max_steps=8)
            assert result["reason"] == "goals_satisfied", result
            history = first["history"] + result["history"]
            assert [item["kind"] for item in history] == [
                "formation",
                "verification",
                "formation",
                "verification",
            ]
            assert [item["target"] for item in history if item["kind"] == "formation"] == [
                "report",
                "triage",
            ]
            for item in (history[0], history[2]):
                assert set(item["proposers"]) == {"producer", "verifier"}
                assert item["formation"]["outcome"] == "UNKNOWN"
                assert item["step"]["invocation"]["state"] == "completed"
                assert item["step"]["selection"]["skipped"]
            assert len(history[0]["formation"]["formation"]["receipts"]) == 2
            assert len(history[2]["formation"]["formation"]["receipts"]) == 3
            assert history[1]["evidence"]["verdict"] == history[3]["evidence"]["verdict"] == "PASS"
            c4 = (await call("receiver", operation="describe", name="triage"))["binding"]
            request = {
                "operation": "invoke",
                "invocation_id": "held-out-business",
                "binding_id": c4["id"],
                "binding_digest": history[3]["evidence"]["binding_digest"],
                "arguments": {
                    "text": "This evaluation input was unavailable to all proposing agents."
                },
            }
            outcome = await call("receiver", **request)
            assert outcome["state"] == "completed"
            assert outcome["result"] == {"long": True, "threshold": len(training_text.split())}
            old_pid = processes["receiver"].pid
            await stop("receiver")
            await start("receiver")
            assert processes["receiver"].pid != old_pid
            assert await call("receiver", **request) == outcome
            restarted = await call("receiver", operation="adaptive-run", max_steps=8)
            assert restarted["reason"] == "goals_satisfied" and not restarted["history"]
            await call(
                "producer",
                operation="revoke",
                subject=words["binding"]["subject"],
                reason="withdrawn primitive",
            )
            await sync("receiver", "producer")
            stopped = await call("receiver", operation="adaptive-run", max_steps=8)
            assert stopped["reason"] == "requires_repair" and not stopped["history"]
            denied = await call("receiver", **{**request, "invocation_id": "after-withdrawal"})
            assert denied["state"] == "unknown"
    finally:
        for name in processes:
            await stop(name)
        for log in logs:
            log.close()
