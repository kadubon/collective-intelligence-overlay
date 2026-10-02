"""Finite duplicate/aging/disconnection probe over the existing HTTPS mesh.

This source-only diagnostic does not repeat the long soak or resolve its unknown
historical cause. Its protocol is saved before the first service request.
"""

import argparse
import asyncio
import hashlib
import json
import os
import platform
import time
from pathlib import Path

from production_session import ProductionSession
from production_soak_faults import stop_process


def write_new(path, value):
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.flush()
        os.fsync(output.fileno())


async def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = await asyncio.to_thread(Path(__file__).read_bytes)
    (output / "probe-source.py").write_bytes(source)
    protocol = {
        "id": "cio-041-duplicate-local-v3",
        "classification": "bounded diagnostic, not original-cause confirmation",
        "duplicate_trials": 12,
        "order": ["immediate", "aged-2-seconds", "disconnected-proxy"] * 4,
        "recovery_queries": 4,
        "maximum_total_seconds": 300,
        "original": "the session's completed original direct registered A2A call",
        "success": "returned result exactly matches the saved original; actuator count unchanged",
        "failure": "retain transport errors separately from any changed returned receipt",
        "injection": "stop only this mesh's receiver proxy before the duplicate; restart once",
        "historical_limit": "does not reproduce the historical 1200-second elapsed soak state",
        "platform": platform.system(),
        "script_sha256": hashlib.sha256(source).hexdigest(),
        "caddy_sha256": hashlib.sha256(await asyncio.to_thread(args.caddy.read_bytes)).hexdigest(),
    }
    write_new(output / "protocol.json", protocol)
    session = ProductionSession(
        args.home.resolve(),
        output,
        os.environ["CIO_TEST_DATABASE_URL"],
        str(args.opa.resolve()),
        str(args.caddy.resolve()),
        100,
        "calibration 文書 alpha Δ data 42",
    )
    trials, failure, initial_count = [], None, None
    started = time.monotonic()
    try:
        async with asyncio.timeout(300):
            await session.initialize()
            session.phase = "duplicate-diagnostic"
            original = session.original_direct
            initial_count = len(session.mesh.mcp_audit.read_bytes().splitlines())
            write_new(output / "original.json", original)
            for index, mode in enumerate(protocol["order"]):
                proxy = None
                if mode == "aged-2-seconds":
                    await asyncio.sleep(2)
                elif mode == "disconnected-proxy":
                    proxy = next(
                        p
                        for p in reversed(session.mesh.proxies)
                        if p.poll() is None and Path(p.args[-1]).parent.name == "receiver"
                    )
                    await asyncio.to_thread(stop_process, proxy)
                    assert proxy.poll() is not None
                result = await session.call("receiver", **original["request"])
                trial = {
                    "index": index,
                    "mode": mode,
                    "result": result,
                    "returned_receipt_unchanged": result == original["result"],
                    "transport_error": "error_type" in result,
                    "call_index": session.calls[-1]["call_index"],
                    "actuator_count": len(session.mesh.mcp_audit.read_bytes().splitlines()),
                    "receiver_proxy_exit_confirmed": proxy is not None and proxy.poll() is not None,
                }
                trials.append(trial)
                if proxy is not None:
                    config = session.configs["receiver"]
                    await asyncio.to_thread(
                        session.mesh.start_proxy,
                        "receiver",
                        config.url,
                        config.listen_port,
                    )
                    await asyncio.sleep(0.5)
                    recovery = await session.call("receiver", **original["request"])
                    trial["recovery"] = {
                        "result": recovery,
                        "returned_receipt_unchanged": recovery == original["result"],
                        "call_index": session.calls[-1]["call_index"],
                    }
                write_new(output / f"trial-{index:02}.json", trial)
    except Exception as error:
        failure = type(error).__name__
        if hasattr(error, "errors"):
            write_new(output / "validation-errors.json", error.errors(include_input=False))
    finally:
        final_count = (
            len(session.mesh.mcp_audit.read_bytes().splitlines())
            if session.mesh and session.mesh.mcp_audit.exists()
            else None
        )
        exported = await session.finish()
        write_new(
            output / "result.json",
            {
                "status": "executed" if failure is None and len(trials) == 12 else "incomplete",
                "failure": failure,
                "trials": trials,
                "offered_trials": 12,
                "observed_trials": len(trials),
                "all_calls": len(session.calls),
                "elapsed_seconds": time.monotonic() - started,
                "initial_actuator_count": initial_count,
                "final_actuator_count": final_count,
                "actuator_count_unchanged": initial_count is not None
                and initial_count == final_count,
                "historical_duplicate_soak_cause": "unresolved",
                "exports": exported,
            },
        )
    print(json.dumps({"observed_trials": len(trials), "failure": failure}))
    return int(failure is not None or len(trials) != 12)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "home", "opa", "caddy"):
        parser.add_argument("--" + name, type=Path, required=True)
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()
