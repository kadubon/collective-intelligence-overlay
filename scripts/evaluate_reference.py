"""Run a bounded matched comparison using the installed public overlay API."""

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from collective_intelligence_overlay.demo import FORMATION_CSV, initialize
from collective_intelligence_overlay.evaluation import compare
from collective_intelligence_overlay.models import UseRequest
from collective_intelligence_overlay.peer import PeerService


async def run(args):
    start = time.perf_counter_ns()
    configs = initialize(args.directory, args.database_url, args.opa)
    peers = {name: PeerService(config) for name, config in configs.items()}
    try:
        formed = await peers["producer"].work(
            {"mode": "form", "attempt": "formation", "name": "csv-sum", "source": FORMATION_CSV}
        )
        checked = await peers["verifier"].work(
            {
                "mode": "verify",
                "attempt": "verification",
                "capability": formed["capability"],
                "result": formed["result"],
                "source": FORMATION_CSV,
                "receiver": "receiver",
            }
        )
        receiver = peers["receiver"]
        for record in (formed["envelope"], checked["envelope"]):
            receiver.overlay.store.put(record)
        receiver.overlay.observed("producer")
        receiver.overlay.observed("verifier")
        cap = formed["capability"]
        request = UseRequest(
            receiver="receiver",
            subject=cap["subject"],
            scope=cap["scope"],
            semantic_fit="confirmed",
        )
        setup = (time.perf_counter_ns() - start) / 1e9
        result = await compare(receiver.overlay, request)
        result["shared_setup_seconds"] = setup
        result["setup_includes"] = (
            "database/identity provisioning, formation, checking, local transfer"
        )
        maintenance = time.perf_counter_ns()
        for peer in peers.values():
            peer.overlay.store.events()
        result["maintenance_read_seconds"] = (time.perf_counter_ns() - maintenance) / 1e9
        result["unmeasured"] = [
            "long-term maintenance",
            "currency charges",
            "network transfer in baseline arms",
        ]
        (args.directory / "evaluation.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        print(json.dumps(result))
    finally:
        for peer in peers.values():
            peer.overlay.store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument(
        "--database-url", default=os.environ.get("CIO_TEST_DATABASE_URL"), required=False
    )
    parser.add_argument("--opa", default=os.environ.get("CIO_OPA", "opa"))
    asyncio.run(run(parser.parse_args()))
