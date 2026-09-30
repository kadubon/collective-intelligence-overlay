import asyncio
import os
import sys
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from a2a.client import AgentCardResolutionError
from sqlalchemy import select

from collective_intelligence_overlay.adapters.a2a import send
from collective_intelligence_overlay.config import Config
from collective_intelligence_overlay.demo import initialize
from collective_intelligence_overlay.storage import budgets


@pytest.mark.parametrize(
    "training_text,work_allowance,mode,connection_mismatch,host_mode",
    [
        ("calibration vocabulary", 50, "adaptive-run", False, False),
        ("a longer calibration document", 50, "adaptive-run", False, False),
        ("bounded checker calibration", 5, "adaptive-run", False, False),
        ("calibration vocabulary", 50, "static-run", False, False),
        ("calibration vocabulary", 50, "adaptive-run", True, False),
        ("calibration vocabulary", 50, "static-run", True, False),
        pytest.param("shared 文書 calibration", 50, "adaptive-run", False, True, id="host-normal"),
        pytest.param(
            "bounded checker calibration", 5, "adaptive-run", False, True, id="host-bottleneck"
        ),
    ],
)
async def test_peer_selected_document_formation_restart_and_withdrawal(
    tmp_path,
    policy,
    monkeypatch,
    training_text,
    work_allowance,
    mode,
    connection_mismatch,
    host_mode,
):
    url = os.environ.get("CIO_TEST_DATABASE_URL")
    if not url:
        pytest.skip("real PostgreSQL required")
    examples = Path(__file__).parents[2] / "examples"
    monkeypatch.syspath_prepend(str(examples))
    from adaptive_documents import ENVIRONMENT, configure_application, write_json

    from collective_intelligence_overlay.starter.documents import (
        APPLICATION_FACTORY,
        APPLICATION_OPERATIONS,
    )

    opa = await asyncio.to_thread(os.path.abspath, policy.binary)
    configs = await asyncio.to_thread(
        initialize, tmp_path / "application", url, opa, work_allowance=Decimal(work_allowance)
    )
    for name, original in configs.items():
        config = original.model_copy(
            update={
                "execution_environment": ENVIRONMENT,
                "max_seconds": 120 if host_mode else 300,
                "application": APPLICATION_FACTORY if host_mode else None,
                "application_settings": original.private_key.parent / "application.json"
                if host_mode
                else None,
            }
        )
        configs[name] = config
        data = config.model_dump(mode="json")
        data["database_url"] = config.database_url.get_secret_value()
        write_json(config.private_key.parent / "config.json", data)
    configure_application(configs, training_text, connection_mismatch=connection_mismatch)
    identities = {}
    for name, config in configs.items():
        identity, overlay = config.runtime()
        identities[name] = identity
        overlay.store.close()
    processes = {}
    logs = []

    async def call(owner, **data):
        if host_mode:
            if data["operation"] in {"adaptive-run", "static-run"}:
                data = {**data, "operation": "run"}
            elif data["operation"] in APPLICATION_OPERATIONS:
                data = {**data, "operation": "app." + data["operation"]}
        return await send(configs[owner], identities[owner], owner, data)

    async def start(name):
        config: Config = configs[name]
        log_path = config.private_key.parent / "adaptive.log"
        log = log_path.open("ab")
        logs.append(log)
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            *(
                ["-m", "collective_intelligence_overlay.cli", "peer"]
                if host_mode
                else [str(examples / "adaptive_documents.py")]
            ),
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
                    observed = await call(name, operation="status" if host_mode else "metrics")
                    if host_mode and observed["state"] != "ready":
                        await asyncio.sleep(0.1)
                        continue
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

    def balance(owner):
        _, overlay = configs[owner].runtime()
        try:
            with overlay.store.engine.connect() as conn:
                return conn.execute(
                    select(budgets.c.remaining).where(budgets.c.unit == "work")
                ).scalar_one()
        finally:
            overlay.store.close()

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
            checker_description = await call("verifier", operation="describe-checker")
            from adaptive_documents import checker_binding

            source = (await call("receiver", operation="describe", name="remote-words"))["binding"]
            from collective_intelligence_overlay.bindings import Binding

            before_checker_test = await send(
                configs["receiver"],
                identities["receiver"],
                "verifier",
                {
                    "operation": "invoke",
                    "invocation_id": "unverified-checker",
                    "binding_id": checker_description["binding"]["id"],
                    "binding_digest": checker_binding().digest,
                    "arguments": {
                        "name": "remote-words",
                        "attempt": "unverified-checker",
                        "binding_digest": Binding.model_validate(source).digest,
                    },
                },
            )
            assert before_checker_test["state"] == "unknown"
            checker_test = await call("producer", operation="certify-checker", target="verifier")
            if work_allowance == 5:
                assert checker_test["evidence"]["verdict"] == "UNKNOWN", checker_test
                assert checker_test["checks"][0]["state"] == "completed"
                assert checker_test["checks"][1]["state"] == "conflict"
                assert await asyncio.to_thread(balance, "verifier") == 0
                repeated_test = await call(
                    "producer", operation="certify-checker", target="verifier"
                )
                assert repeated_test == checker_test
                assert await asyncio.to_thread(balance, "verifier") == 0
                await sync("verifier", "producer")
                decision = await call(
                    "verifier",
                    operation="qualify",
                    request={
                        "receiver": "verifier",
                        "subject": checker_binding().subject.model_dump(mode="json"),
                        "capability_issuer": "verifier",
                        "binding_digest": checker_binding().digest,
                        "scope": checker_binding().scope.model_dump(mode="json"),
                        "semantic_fit": "confirmed",
                    },
                )
                assert decision["decision"]["outcome"] != "ACCEPT"
                return
            assert checker_test["evidence"]["verdict"] == "PASS", checker_test
            await sync("verifier", "producer")
            await sync("receiver", "verifier")
            await sync("receiver", "producer")
            imported_checker_test = await call(
                "producer", operation="certify-checker", target="receiver"
            )
            assert imported_checker_test["evidence"]["verdict"] == "PASS", imported_checker_test
            await sync("receiver", "producer")
            if connection_mismatch:
                import json

                application = json.loads(
                    (configs["receiver"].private_key.parent / "application.json").read_text()
                )
                mismatch = await call(
                    "receiver", operation="qualify", request=application["goals"][0]["request"]
                )
                assert mismatch["decision"]["outcome"] != "ACCEPT"
                assert "scope_mismatch" in mismatch["decision"]["reasons"]
            first = await call("receiver", operation=mode, max_steps=1)
            assert first["reason"] == "step_limit" and len(first["history"]) == 1
            c3 = (await call("receiver", operation="describe", name="report"))["binding"]
            before_check = await call(
                "receiver",
                operation="invoke",
                invocation_id="unverified-c3",
                binding_id=c3["id"],
                binding_digest=first["history"][0]["formation"]["formation"]["binding_digest"],
                arguments={
                    "document"
                    if connection_mismatch
                    else "text": "ordinary use must wait for independent checking"
                },
            )
            assert before_check["state"] == "unknown"
            # Resume with a formed but still unverified C3. The harness supplies
            # no next-task instruction after restarting the owner process.
            await stop("receiver")
            if host_mode:
                # Restore explicit pins even when unrelated retained candidates
                # exceed both the old 16-record and the transport byte window.
                from collective_intelligence_overlay.models import Capability, Subject
                from collective_intelligence_overlay.queries import RecordQuery

                local_identity, retained = configs["receiver"].runtime()
                try:
                    original = retained.store.record_page(
                        RecordQuery(
                            kinds=("capability",),
                            issuer="receiver",
                            subject=Subject.model_validate(c3["subject"]),
                        )
                    ).items[0]
                    assert isinstance(original, Capability)
                    unrelated = []
                    for index in range(24):
                        candidate = original.model_copy(
                            update={
                                "subject": original.subject.model_copy(
                                    update={"id": f"retained.unrelated-{index}"}
                                ),
                                "entrypoint": f"unrelated-{index}",
                            }
                        )
                        envelope = local_identity.sign(candidate)
                        retained.store.put(envelope)
                        reference = retained.store.reference(
                            "capability", "receiver", candidate.subject.key
                        )
                        unrelated.append((reference, envelope))
                finally:
                    retained.store.close()
            await start("receiver")
            if host_mode:
                _, retained = configs["receiver"].runtime()
                try:
                    assert all(
                        retained.store.signed_record(ref) == envelope for ref, envelope in unrelated
                    )
                finally:
                    retained.store.close()
            result = await call("receiver", operation=mode, max_steps=8)
            assert result["reason"] == "goals_satisfied", result
            history = first["history"] + result["history"]
            assert [item["kind"] for item in history] == [
                "connection" if connection_mismatch else "formation",
                "verification",
                "formation",
                "verification",
            ]
            assert [
                item["target"] for item in history if item["kind"] in {"formation", "connection"}
            ] == [
                "report",
                "triage",
            ]
            for item in (history[0], history[2]):
                if mode == "adaptive-run":
                    assert set(item["proposers"]) == {"producer", "verifier"}
                assert item["formation"]["outcome"] == "UNKNOWN"
                if mode == "adaptive-run":
                    assert item["step"]["invocation"]["state"] == "completed"
                    assert item["step"]["selection"]["skipped"]
                else:
                    assert item["invocation"]["state"] == "completed"
            assert len(history[0]["formation"]["formation"]["receipts"]) == 2
            assert len(history[2]["formation"]["formation"]["receipts"]) == 3
            assert history[1]["evidence"]["verdict"] == history[3]["evidence"]["verdict"] == "PASS"
            if mode == "adaptive-run":
                if connection_mismatch:
                    assert history[0]["allocation"]["ordered"][0] == history[0]["opportunity"]
                    assert "connection_backlog" in history[0]["allocation"]["reasons"]
                    assert c3["scope"]["input_contract"] == "report.in.v2"
                    assert c3["input_schema"]["required"] == ["document"]
                assert history[1]["allocation"]["qualified_checkers"]
                assert (
                    "verification_backlog_with_qualified_checker"
                    in history[1]["allocation"]["reasons"]
                )
                assert history[1]["step"]["invocation"]["state"] == "completed"
                assert history[3]["step"]["selection"]["skipped"]
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
            # Replay a completed checker result after checker restart while the
            # target process is stopped. No fresh probe or reservation can hide
            # behind a successful response.
            checker_before = await asyncio.to_thread(balance, "verifier")
            repeated_certificate = await call(
                "producer", operation="certify-checker", target="receiver"
            )
            assert repeated_certificate == imported_checker_test
            await stop("verifier")
            await start("verifier")
            check_request = {
                "operation": "app.request-document-check"
                if host_mode
                else "request-document-check",
                "name": "report",
                "attempt": ("check-" + history[1]["opportunity"])
                if mode == "adaptive-run"
                else history[1]["check_attempt"],
                "binding_digest": history[1]["evidence"]["binding_digest"],
                "checker_digest": checker_binding().digest,
            }
            replayed_check = await send(
                configs["receiver"], identities["receiver"], "verifier", check_request
            )
            assert replayed_check["evidence"] == history[1]["evidence"]
            assert replayed_check["observed"]["state"] == "completed"
            changed_request = await send(
                configs["receiver"],
                identities["receiver"],
                "verifier",
                {**check_request, "binding_digest": "0" * 64},
            )
            assert changed_request["state"] == "conflict"
            assert await asyncio.to_thread(balance, "verifier") == checker_before
            await start("receiver")
            assert processes["receiver"].pid != old_pid
            assert await call("receiver", **request) == outcome
            restarted = await call("receiver", operation=mode, max_steps=8)
            assert restarted["reason"] == "goals_satisfied" and not restarted["history"]
            if mode == "static-run":
                from collective_intelligence_overlay.queries import RecordQuery

                _, inspected = configs["receiver"].runtime()
                try:
                    assert not inspected.store.record_page(
                        RecordQuery(kinds=("opportunity", "proposal"))
                    ).items
                finally:
                    inspected.store.close()
            await call(
                "producer",
                operation="revoke",
                subject=words["binding"]["subject"],
                reason="withdrawn primitive",
            )
            await sync("receiver", "producer")
            stopped = await call("receiver", operation=mode, max_steps=8)
            assert stopped["reason"] == "requires_repair" and not stopped["history"]
            denied = await call("receiver", **{**request, "invocation_id": "after-withdrawal"})
            assert denied["state"] == "unknown"
    finally:
        for name in processes:
            await stop(name)
        for log in logs:
            log.close()
