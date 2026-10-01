"""Physical faults in the same restricted-role, three-peer production protocol."""

import asyncio
import base64
import copy
import json
import subprocess
import sys
import time

from document_recovery_protocol import originals
from sqlalchemy import text
from sqlalchemy.engine import make_url

from collective_intelligence_overlay.bindings import Binding


async def run(
    configs,
    identities,
    processes,
    mesh,
    start,
    stop,
    call,
    counter,
    original_request,
    original_result,
    root,
):
    observations = []

    def retain(label, data):
        observations.append({"injection": label, **data})
        (root / "owned-fault-observations.json").write_text(
            json.dumps(observations, indent=2), encoding="utf-8"
        )

    async def states():
        result = {owner: await call(owner, operation="status") for owner in configs}
        assert all(value["state"] == "ready" for value in result.values())
        return result

    # The second installed CLI process must fail before accepting work while
    # the original owner and its exact committed receipt remain available.
    before = await asyncio.to_thread(originals, configs["receiver"])
    effects = mesh.mcp_audit.read_bytes()
    draining = await call("receiver", operation="drain")
    assert draining["state"] == "draining"
    assert (
        await call(
            "receiver", operation="invocation", invocation_id=original_request["invocation_id"]
        )
    )["invocation"] == original_result
    new_request = {**original_request, "invocation_id": "new-effect-during-drain"}
    closed = await call("receiver", **new_request)
    assert closed["error"] == "SERVICE_INTAKE_CLOSED"
    assert (
        await call("receiver", operation="invocation", invocation_id=new_request["invocation_id"])
    )["invocation"] is None
    assert (await call("receiver", operation="resume"))["state"] == "ready"
    assert await asyncio.to_thread(originals, configs["receiver"]) == before
    assert mesh.mcp_audit.read_bytes() == effects
    retain(
        "new effect request during drain",
        {"drain": draining, "refusal": closed, "states": await states()},
    )
    duplicate = await asyncio.to_thread(
        subprocess.run,
        [
            sys.executable,
            "-m",
            "collective_intelligence_overlay.cli",
            "peer",
            "--config",
            str(configs["receiver"].private_key.parent / "config.json"),
        ],
        cwd=root,
        capture_output=True,
        timeout=20,
    )
    assert duplicate.returncode == 2 and b"OwnerAlreadyRunning" in duplicate.stderr
    assert await call("receiver", **original_request) == original_result
    assert await asyncio.to_thread(originals, configs["receiver"]) == before
    assert mesh.mcp_audit.read_bytes() == effects
    retain(
        "duplicate owner boot",
        {"second_process_exit": duplicate.returncode, "states": await states()},
    )

    # Submit an actually corrupted DSSE through authenticated HTTPS/A2A.
    # It must neither insert a record nor reserve/invoke any business work.
    envelope = copy.deepcopy(next(iter(before[0].values())))
    envelope["signatures"][0]["sig"] = base64.b64encode(bytes(64)).decode()
    try:
        await call("receiver", operation="submit", envelope=envelope)
    except Exception as error:
        assert type(error).__name__ == "InternalError"
        refused = type(error).__name__
    else:
        raise AssertionError("corrupted DSSE accepted")
    assert await asyncio.to_thread(originals, configs["receiver"]) == before
    assert mesh.mcp_audit.read_bytes() == effects
    retain("bad signature", {"refusal": refused, "states": await states()})

    previous = processes["receiver"]
    await stop("receiver", crash=True)
    assert previous.poll() is not None
    await start("receiver")
    assert processes["receiver"].pid != previous.pid
    assert await call("receiver", **original_request) == original_result
    assert await asyncio.to_thread(originals, configs["receiver"]) == before
    assert mesh.mcp_audit.read_bytes() == effects
    retain(
        "owner process kill",
        {
            "old_pid": previous.pid,
            "confirmed_exit": previous.returncode,
            "new_pid": processes["receiver"].pid,
            "states": await states(),
        },
    )

    role = make_url(configs["receiver"].database_url.get_secret_value()).username
    with mesh.admin.begin() as conn:
        terminated = (
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE usename=:role AND pid <> pg_backend_pid()"
                ),
                {"role": role},
            )
            .scalars()
            .all()
        )
    assert terminated and all(terminated)
    degraded = await call("receiver", operation="status")
    assert degraded["state"] == "degraded"
    refused_request = {**original_request, "invocation_id": "physical-db-cutoff-new-call"}
    refused = await call("receiver", **refused_request)
    assert refused["error"] == "SERVICE_INTAKE_CLOSED"
    assert (await call("receiver", operation="resume"))["state"] == "degraded"
    assert (await call("producer", operation="status"))["state"] == "ready"
    assert (await call("verifier", operation="status"))["state"] == "ready"
    await stop("receiver")
    await start("receiver")
    assert (
        await call(
            "receiver", operation="invocation", invocation_id=refused_request["invocation_id"]
        )
    )["invocation"] is None
    assert await call("receiver", **original_request) == original_result
    assert await asyncio.to_thread(originals, configs["receiver"]) == before
    assert mesh.mcp_audit.read_bytes() == effects
    retain(
        "database physical disconnect",
        {
            "positively_terminated_sessions": len(terminated),
            "closed": degraded,
            "new_call_refused": refused,
            "states": await states(),
        },
    )

    # Explicit private control delays the actual official MCP server on every OS.
    # The caller retains its original UNKNOWN/held result after the read timeout,
    # even after the owned server confirms completion or cancellation of its task.
    binding = Binding.model_validate(counter)
    delayed_request = {
        "operation": "invoke",
        "invocation_id": "mcp-delayed-original",
        "binding_id": binding.id,
        "binding_digest": binding.digest,
        "arguments": {"text": "delayed original 文書"},
    }
    completed_before = mesh.mcp_results.read_bytes()
    mesh.mcp_delay.write_text("31", encoding="utf-8")
    started = time.monotonic()
    try:
        unknown = await call("producer", **delayed_request)
        assert unknown["state"] == "unknown" and unknown["reservation_state"] == "held"
        assert mesh.mcp_audit.read_bytes() == effects + b"call\n"
        async with asyncio.timeout(20):
            for _ in range(200):
                if mesh.mcp_results.read_bytes() != completed_before:
                    break
                await asyncio.sleep(0.1)
            else:
                raise AssertionError("owned delayed MCP task did not reach a terminal state")
    finally:
        mesh.mcp_delay.write_text("0", encoding="utf-8")
    terminal = mesh.mcp_results.read_bytes()[len(completed_before) :]
    assert terminal in {b"completed\n", b"cancelled\n"}
    held = await asyncio.to_thread(originals, configs["producer"])
    assert await call("producer", **delayed_request) == unknown
    assert (
        await call(
            "producer", operation="invocation", invocation_id=delayed_request["invocation_id"]
        )
    )["invocation"] == unknown
    assert await asyncio.to_thread(originals, configs["producer"]) == held
    assert mesh.mcp_audit.read_bytes() == effects + b"call\n"
    assert mesh.mcp_results.read_bytes() == completed_before + terminal
    retain(
        "delayed response and timeout",
        {
            "delay_seconds": 31,
            "elapsed_seconds": time.monotonic() - started,
            "original": unknown,
            "server_task_terminal": terminal.decode().strip(),
            "actual_calls": 1,
            "same_id_replayed_without_call": True,
            "states": await states(),
        },
    )
    assert await call("receiver", **original_request) == original_result
