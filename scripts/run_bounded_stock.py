"""Prospective G3-only repair; preserve G1, restore global cap, never repeat calibration."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from accumulation_host import OwnedOllama, ProcessObserver, runtime_contract
from accumulation_session import ROOT
from near_transfer_protocol import CohortCap, sha
from run_bounded_scratch import registration, sources, stock_diagnosis

from collective_intelligence_overlay.adapters.inference_observer import write_new


def prepare(args):
    protocol = json.loads((args.source_run / "protocol.json").read_bytes())
    summary = json.loads((args.source_run / "pilot-summary.json").read_bytes())
    budget = json.loads((args.source_run / "resources.json").read_bytes())
    selected = {}
    for family in ("sql", "composition"):
        source = next(
            r
            for r in (*summary["screen"], *summary["locked"])
            if r["family"] == family and r["succeeded"]
        )
        selected[family] = {**source, "offer_sha256": sha(args.source_run / source["file"])}
    protocol.update(
        id="cio-044-bounded-scratch-G3-v2",
        registered_at=datetime.now(UTC).isoformat(),
        sources=sources(),
        source_run=args.source_run.resolve().relative_to(ROOT).as_posix(),
        source_protocol_sha256=sha(args.source_run / "protocol.json"),
        source_resources_sha256=sha(args.source_run / "resources.json"),
        source_offers=selected,
        previous_resources=budget,
        previous_finished_at=datetime.now(UTC).isoformat(),
        pilot_max_requests=budget["model_calls"] + 8,
        revision_scope=(
            "G3 home namespace isolation and real receiver restart; "
            "task/compiler/options and original G1 scores unchanged"
        ),
        confirmation_authorized=False,
    )
    args.protocol.parent.mkdir(parents=True, exist_ok=True)
    write_new(args.protocol, protocol)


async def run(args):
    protocol = json.loads(args.protocol.read_bytes())
    proof = registration(args.protocol, protocol, args.prereg_commit)
    if sha(args.source_run / "protocol.json") != protocol["source_protocol_sha256"] or (
        sha(args.source_run / "resources.json") != protocol["source_resources_sha256"]
    ):
        raise ValueError("original calibration or global accounting changed")
    args.output.mkdir(parents=True, exist_ok=False)
    args.home.mkdir(parents=True, exist_ok=False)
    cap = CohortCap(protocol, args.output, ROOT)
    previous = protocol["previous_resources"]
    for attr, key in (
        ("calls", "model_calls"),
        ("charged_tokens", "charged_tokens"),
        ("measured_tokens", "measured_tokens"),
        ("missing_usage", "missing_usage_requests"),
        ("actions", "application_actions"),
        ("execution_invocations", "execution_invocations_reserved"),
        ("checker_cases", "checker_cases_reserved"),
        ("retrievals", "retrieval_calls"),
        ("identity_observations_reserved", "model_identity_observations_reserved"),
        ("model_retrievals_reserved", "model_retrieval_calls_reserved"),
        ("not_sent", "proven_not_sent_requests"),
    ):
        setattr(cap, attr, previous[key])
    # Preserve the intervening time conservatively; never reset the all-stage wall.
    first = json.loads((args.source_run / "registration.json").read_bytes())["checked_at"]
    previous_wall = (datetime.now(UTC) - datetime.fromisoformat(first)).total_seconds() + 300
    cap.started -= previous_wall
    server = OwnedOllama(args.home / "ollama", args.output, port=11444, context=4096)
    observer = ProcessObserver(
        args.output / "process-resources.jsonl", max(1, int(14700 - previous_wall))
    )
    write_new(args.output / "protocol.json", protocol)
    write_new(args.output / "registration.json", proof)
    for name in protocol["sources"]:
        target = args.output / "source-snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    results, error = [], None
    try:
        manifest = await server.start()
        write_new(args.output / "runtime-contract.json", runtime_contract(manifest))
        observer.start()
        for family, source in protocol["source_offers"].items():
            if sha(args.source_run / source["file"]) != source["offer_sha256"]:
                raise ValueError("diagnostic source offer changed")
            results += await stock_diagnosis(
                args, protocol, cap, server, source, source_root=args.source_run
            )
            print(
                json.dumps(
                    {
                        "family": family,
                        "results": [
                            {
                                k: r[k]
                                for k in (
                                    "arm",
                                    "family",
                                    "ready",
                                    "full",
                                    "empty",
                                    "new_generations",
                                )
                            }
                            for r in results
                            if r["family"] == family
                        ],
                    }
                ),
                flush=True,
            )
    except Exception as exc:
        error = type(exc).__name__
        write_new(
            args.output / "driver-failure.json", {"error_type": error, "automatic_retry": False}
        )
        raise
    finally:
        await server.close()
        observer.close()
        cap.close()
        write_new(args.output / "resources.json", cap.report())
        write_new(
            args.output / "cleanup.json",
            {
                "owned_server_stopped": server.process is None or server.process.poll() is not None,
                "observer_stopped": observer.thread is None or not observer.thread.is_alive(),
            },
        )
        write_new(
            args.output / "G3-summary.json",
            {
                "results": results,
                "driver_error": error,
                "ready": len(results) == 4 and all(r["ready"] for r in results),
                "confirmation_authorized": False,
                "source_scores_unchanged": True,
                "global_resources": cap.report(),
            },
        )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("operation", choices=("prepare", "run"))
    p.add_argument("--protocol", type=Path, required=True)
    p.add_argument("--source-run", type=Path, required=True)
    p.add_argument("--output", type=Path)
    p.add_argument("--home", type=Path)
    p.add_argument("--prereg-commit")
    args = p.parse_args()
    if args.operation == "prepare":
        prepare(args)
    else:
        if not all((args.output, args.home, args.prereg_commit)):
            p.error("run requires output, private home and pushed preregistration")
        asyncio.run(run(args))


if __name__ == "__main__":
    main()
