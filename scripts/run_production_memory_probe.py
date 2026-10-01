"""Diagnose a retained RSS failure; this is neither a formal soak nor acceptance."""

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from production_session import ProductionSession
from production_soak_faults import request
from run_production_experiment import ROOT, digest_file

from collective_intelligence_overlay.adapters import a2a


async def run(args):
    if sys.platform != "linux":
        raise ValueError("owned Linux diagnostic signals required")
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    source_files = [
        Path(__file__),
        ROOT / "tests/integration/memory_diagnostic_peer.py",
        Path(a2a.__file__),
    ]
    (args.output / "sources").mkdir(mode=0o700)
    for source in source_files:
        (args.output / "sources" / source.name).write_bytes(source.read_bytes())
    (args.output / "protocol.json").write_text(
        json.dumps(
            {
                "development_only": True,
                "formal_acceptance": False,
                "interpreter": sys.executable,
                "sources": {source.name: digest_file(source) for source in source_files},
                "offers": "600 qualification calls, four groups of 150",
                "diagnostic_gc": "explicit final snapshot only; no formal performance claim",
            },
            indent=2,
        )
    )
    session = ProductionSession(
        args.private.resolve(),
        args.output.resolve(),
        args.database_url,
        str(args.opa.resolve()),
        str(args.caddy.resolve()),
        5000,
        "calibration 文書 alpha Δ data 42",
    )
    snapshots = args.private.resolve() / "receiver" / "memory-snapshots"

    async def snapshot(signum):
        before = len(list(snapshots.glob("*.json")))
        os.kill(session.processes["receiver"].pid, signum)
        async with asyncio.timeout(20):
            while True:
                if len(list(snapshots.glob("*.json"))) > before:
                    break
                await asyncio.sleep(0.1)
        report = await session.sample(operational=False)
        print(json.dumps({"stage": "snapshot", "number": before, "seconds": report["seconds"]}))

    try:
        await session.initialize()
        await session.stop("receiver")
        log = (args.private.resolve() / "receiver" / "memory-process.log").open("ab")
        session.logs.append(log)
        session.processes["receiver"] = await asyncio.to_thread(
            subprocess.Popen,
            [
                sys.executable,
                str(ROOT / "tests/integration/memory_diagnostic_peer.py"),
                "--config",
                str(args.private.resolve() / "receiver" / "config.json"),
                "--snapshots",
                str(snapshots),
            ],
            cwd=args.private,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        async with asyncio.timeout(30):
            while True:
                if (await session.call("receiver", operation="status")).get("state") == "ready":
                    break
                await asyncio.sleep(0.1)
        await snapshot(signal.SIGUSR1)
        for _group in range(4):
            for _ in range(150):
                result = await session.call(
                    "receiver", operation="qualify", request=request(session)
                )
                if "decision" not in result:
                    raise ValueError("diagnostic qualification did not return")
            await snapshot(signal.SIGUSR1)
        await snapshot(signal.SIGUSR2)
    finally:
        exported = await session.finish()
        (args.output / "diagnostic.json").write_text(
            json.dumps(
                {
                    "development_only": True,
                    "formal_acceptance": False,
                    "explicit_final_gc": True,
                    "samples": session.samples,
                    "exports": exported,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("CIO_TEST_DATABASE_URL"))
    parser.add_argument("--opa", type=Path, required=True)
    parser.add_argument("--caddy", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(run(parser.parse_args()))
