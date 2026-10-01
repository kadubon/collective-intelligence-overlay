"""Offer the predeclared soak workload to normally installed HTTPS production peers."""

import argparse
import asyncio
import importlib.metadata
import json
import os
import platform
import random
import subprocess
import sys
import time
from pathlib import Path

from production_session import ProductionSession
from production_soak_faults import inject, invocation, request
from run_production_experiment import ROOT, digest_file, installed_wheel_provenance

from collective_intelligence_overlay.bindings import fingerprint
from collective_intelligence_overlay.starter.adaptive_documents import write_json


def workload(seed, count):
    rng = random.Random(f"production-040-soak/{seed}")
    # Each block has exactly the declared 15/20/20/25/15/5 percentages.
    block = [
        name
        for name, number in (
            ("state", 3),
            ("discovery", 4),
            ("qualification", 4),
            ("invoke", 5),
            ("formation_check", 3),
            ("original_query", 1),
        )
        for _ in range(number)
    ]
    result = []
    for index in range(count):
        if index % len(block) == 0:
            rng.shuffle(block)
        document = rng.choice((" ", "\n", "\t", "\u3000")).join(
            [f"soak-{seed}-{index}"]
            + [
                rng.choice(("文書", "Δ", "résumé", "data", "42"))
                for _ in range(rng.randrange(1, 160))
            ]
        )
        result.append(
            {
                "index": index,
                "kind": block[index % len(block)],
                "text": document,
                # This value actually reaches the registered render component
                # through words -> report -> triage, rather than an unused draw.
                "render_parameter": len(document.split()),
            }
        )
    return result


async def main(args):
    if platform.system() != "Linux":
        raise ValueError("the release soak needs native Linux OS /proc observations")
    profile = json.loads((ROOT / "docs/profiles/production-040.json").read_text())
    spec = profile["release_soak"]
    development = args.development_seconds is not None
    if development and (args.development_seed is None or args.development_seed == 401):
        raise ValueError("development needs a separate seed")
    if not development and args.development_seed is not None:
        raise ValueError("formal seed cannot be overridden")
    duration = args.development_seconds if development else spec["duration_seconds_min"]
    warmup = 5 if development else spec["warmup_seconds"]
    if duration < 120:
        raise ValueError("development must still retain at least 120 seconds")
    seed = args.development_seed if development else 401
    interval = duration / 12 if development else spec["fault_interval_seconds"]
    faults = [
        {
            "index": index,
            "name": name,
            "at_seconds": (index + 1) * interval,
            "normal_exclusion_end_seconds": min(duration, (index + 1) * interval + 60),
        }
        for index, name in enumerate(spec["fault_schedule"])
    ]
    candidate = json.loads((args.candidate / "artifacts.json").read_text())
    if candidate != {
        path.name: digest_file(path)
        for path in (args.candidate / "dist").iterdir()
        if path.name.endswith((".whl", ".tar.gz"))
    }:
        raise ValueError("candidate changed")
    provenance = installed_wheel_provenance(args.candidate, candidate)
    if importlib.metadata.version("collective-intelligence-overlay") != profile["target_version"]:
        raise ValueError("installed version differs")
    meminfo = await asyncio.to_thread(Path("/proc/meminfo").read_text)
    if os.cpu_count() < 2 or int(meminfo.splitlines()[0].split()[1]) < 4 * 1024**2:
        raise ValueError("minimum hardware envelope is unavailable")
    output, private = args.output.resolve(), args.private.resolve()
    if output.is_relative_to(private) or private.is_relative_to(output):
        raise ValueError("private homes and shareable reports must be disjoint")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    private.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    count = int(duration * spec["offered_requests_per_second"])
    inputs = workload(seed, count)
    source_paths = [
        Path(__file__),
        Path(__file__).with_name("production_session.py"),
        Path(__file__).with_name("production_soak_faults.py"),
        Path(__file__).with_name("quiesced_evidence_withdrawal.py"),
        Path(__file__).with_name("run_production_experiment.py"),
        Path(__file__).with_name("validate_production_soak.py"),
        ROOT / "tests/e2e/production_mesh.py",
        ROOT / "examples/evaluate_documents.py",
        ROOT / "tests/integration/authenticated_mcp_application.py",
    ]
    protocol = {
        "protocol": "production-soak-040-v1",
        "development_only": development,
        "profile_id": profile["profile_id"],
        "profile_sha256": fingerprint(profile),
        "artifacts": candidate,
        "installed_wheel_provenance": provenance,
        "seed": seed,
        "measurement_seconds": duration,
        "warmup_seconds": warmup,
        "work_allowance_per_owner": "5000",
        "allowance_is_consumption": False,
        "rate": spec["offered_requests_per_second"],
        "regular_offers": count,
        "faults": faults,
        "fault_exclusions": "fixed 60-second windows by offer time; all retained",
        "bursts": {
            "at_seconds": [i * interval for i in range(1, 12)],
            "requests": 16,
            "kind": "qualification",
            "excluded_from_regular_mix": True,
        },
        "sample_seconds": 5,
        "verification_backlog_basis": (
            "the two exact operator-selected report/triage requests; not all history"
        ),
        "discovery_maintenance": (
            "producer/verifier reciprocal sync plus receiver source sync; "
            "old expiry is never renewed"
        ),
        "maximum_operation_seconds": 180,
        "initialization": "actual primitive checks, checker calibration and finite formation",
        "operator_training_text": "calibration 文書 alpha Δ data 42",
        "operator_threshold": 6,
        "composition_parameter": "render.words is the generated document word count",
        "source_commit": (
            await asyncio.to_thread(
                subprocess.check_output, ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            )
        ).strip(),
        "warmup": "same mix and rate; excluded from measured latency/throughput only",
        "costs": "OS process CPU/RSS, inclusive client wall, DB/OPA/A2A monitoring are separate",
        "missing_resources": [
            "model_tokens",
            "currency",
            "exact_per_owner_shared_PostgreSQL_CPU",
            "complete_wire_bytes",
            "between_sample_short_lived_child_RSS_peaks",
        ],
        "contention_notes": args.contention_notes,
        "paid_inference": False,
        "runtime": {
            "python": sys.version,
            "executable": sys.executable,
            "platform": platform.platform(),
            "logical_cpus": os.cpu_count(),
            "meminfo": meminfo,
        },
        "sources": {path.name: digest_file(path) for path in source_paths},
    }
    (output / "sources").mkdir(mode=0o700)
    for path in source_paths:
        (output / "sources" / path.name).write_bytes(path.read_bytes())
    write_json(output / "protocol.json", protocol)
    write_json(output / "inputs.json", inputs)
    session = ProductionSession(
        private,
        output,
        args.database_url,
        str(args.opa.resolve()),
        str(args.caddy.resolve()),
        5000,
        "calibration 文書 alpha Δ data 42",
    )
    offered, completed, fault_results, tasks = [], [], [], []
    sampling_stop = asyncio.Event()
    sampler = None
    measurement_started = None
    status = "initializing"
    with (output / "offers.jsonl").open("x", encoding="utf-8") as stream:

        async def offer(item, phase, *, burst=False):
            before = time.monotonic()
            row = {
                **item,
                "phase": phase,
                "burst": burst,
                "offered_seconds": session.seconds(),
                "status": "censored",
            }
            offered.append(row)
            key = f"{phase}-{'burst' if burst else 'regular'}-{item['index']}"
            try:
                async with asyncio.timeout(180):
                    kind = item["kind"]
                    if kind == "state":
                        result = await session.call("receiver", operation="status", category=kind)
                    elif kind == "discovery":
                        values = await asyncio.gather(
                            session.sync("producer", "verifier"),
                            session.sync("verifier", "producer"),
                            session.sync(
                                "receiver", "verifier" if item["index"] % 2 else "producer"
                            ),
                        )
                        result = {"owner_syncs": values}
                    elif kind == "qualification":
                        result = await session.call(
                            "receiver", operation="qualify", request=request(session), category=kind
                        )
                    elif kind == "invoke":
                        data = invocation(session, key, item["text"])
                        result = await session.call("receiver", category=kind, **data)
                        if result.get("state") == "completed":
                            completed.append({"request": data, "result": result})
                        row["expected_result"] = {
                            "long": len(item["text"].split()) > 6,
                            "threshold": 6,
                        }
                        row["application_output_matches"] = (
                            result.get("result") == row["expected_result"]
                        )
                    elif kind == "formation_check":
                        loop = await session.call(
                            "receiver", operation="run", max_steps=8, category=kind
                        )
                        check = await session.verify(
                            "receiver", "triage", {"text": item["text"]}, key + "-check"
                        )
                        result = {"run": loop, "check": check}
                    elif kind == "original_query":
                        if completed:
                            original = completed[item["index"] % len(completed)]
                            result = await session.call(
                                "receiver",
                                operation="invocation",
                                category=kind,
                                invocation_id=original["request"]["invocation_id"],
                            )
                        else:
                            result = {
                                "not_offered_to_provider": True,
                                "reason": "no_original_completed_invocation_yet",
                            }
                    row.update(status="returned", result=result)
                    if "error_type" in result:
                        row["status"] = "transport_failed"
            except Exception as error:
                row.update(status="failed", error_type=type(error).__name__)
            finally:
                row["wall_seconds"] = time.monotonic() - before
                row["completed_seconds"] = session.seconds()
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                stream.flush()

        async def sample():
            next_sample = time.monotonic()
            slot = 0
            pending = {}
            while not sampling_stop.is_set():
                # Slow or unavailable HTTP/DB observations cannot delay OS RSS
                # sampling or generate an unbounded stack of monitoring requests.
                await session.sample(
                    operational=False,
                    schedule={
                        "slot": slot,
                        "due_session_seconds": next_sample - session.started,
                        "interval_seconds": 5,
                    },
                )
                for owner in session.configs:
                    previous = pending.get(owner)
                    if previous is None or previous.done():
                        if previous is not None:
                            value = previous.result()
                            with (output / "operational-samples.jsonl").open(
                                "a", encoding="utf-8"
                            ) as observations:
                                observations.write(
                                    json.dumps(
                                        {
                                            "owner": owner,
                                            "received_seconds": session.seconds(),
                                            "observation": value,
                                        }
                                    )
                                    + "\n"
                                )
                        pending[owner] = asyncio.create_task(
                            session.call(
                                owner, operation="operational_metrics", category="monitoring"
                            )
                        )
                goal_key = "receiver-current-targets"
                previous = pending.get(goal_key)
                if previous is None or previous.done():
                    if previous is not None:
                        with (output / "operational-samples.jsonl").open(
                            "a", encoding="utf-8"
                        ) as observations:
                            observations.write(
                                json.dumps(
                                    {
                                        "owner": goal_key,
                                        "received_seconds": session.seconds(),
                                        "observation": previous.result(),
                                    }
                                )
                                + "\n"
                            )
                    pending[goal_key] = asyncio.create_task(
                        session.call(
                            "receiver",
                            operation="capability_metrics",
                            requests=session.target_requests,
                            category="monitoring",
                        )
                    )
                if sampling_stop.is_set():
                    break
                next_sample += 5
                slot += 1
                try:
                    await asyncio.wait_for(
                        sampling_stop.wait(), max(0, next_sample - time.monotonic())
                    )
                except TimeoutError:
                    pass
            # The stop event can wake a deadline wait early. Join the existing
            # observations without creating a fictitious sample in a future slot.
            await asyncio.gather(*pending.values())
            with (output / "operational-samples.jsonl").open("a", encoding="utf-8") as observations:
                for owner, task in pending.items():
                    observations.write(
                        json.dumps(
                            {
                                "owner": owner,
                                "received_seconds": session.seconds(),
                                "observation": task.result(),
                            }
                        )
                        + "\n"
                    )

        async def schedule_faults(start):
            for fault in faults:
                await asyncio.sleep(max(0, start + fault["at_seconds"] - time.monotonic()))
                print(json.dumps({"stage": "fault-start", **fault}), flush=True)
                try:
                    async with asyncio.timeout(180):
                        value = await inject(session, fault["index"], completed)
                    row = {**fault, "status": "executed", **value}
                except Exception as error:
                    row = {
                        **fault,
                        "status": "failed",
                        "error_type": type(error).__name__,
                        "elapsed_seconds": session.seconds()
                        - measurement_session_seconds
                        - fault["at_seconds"],
                    }
                fault_results.append(row)
                write_json(output / f"fault-{fault['index']:02}.json", row)
                print(
                    json.dumps(
                        {
                            "stage": "fault-finished",
                            "index": fault["index"],
                            "status": row["status"],
                        }
                    ),
                    flush=True,
                )

        async def schedule_bursts(start):
            for number, offset in enumerate(protocol["bursts"]["at_seconds"]):
                await asyncio.sleep(max(0, start + offset - time.monotonic()))
                for child in range(16):
                    item = {
                        "index": number * 16 + child,
                        "kind": "qualification",
                        "text": "burst 文書",
                    }
                    tasks.append(asyncio.create_task(offer(item, "measurement", burst=True)))

        try:
            await session.initialize()
            sampler = asyncio.create_task(sample())
            session.phase = "warmup"
            print(json.dumps({"stage": "warmup", "seconds": warmup}), flush=True)
            start = time.monotonic()
            for item in workload(seed + 1, int(warmup / 4)):
                await asyncio.sleep(max(0, start + item["index"] * 4 - time.monotonic()))
                tasks.append(asyncio.create_task(offer(item, "warmup")))
            await asyncio.sleep(max(0, start + warmup - time.monotonic()))
            await asyncio.gather(*tasks)
            tasks.clear()
            session.phase = "measurement"
            measurement_started = time.monotonic()
            measurement_session_seconds = session.seconds()
            print(
                json.dumps({"stage": "measurement", "seconds": duration, "regular_offers": count}),
                flush=True,
            )
            fault_task = asyncio.create_task(schedule_faults(measurement_started))
            burst_task = asyncio.create_task(schedule_bursts(measurement_started))
            for item in inputs:
                await asyncio.sleep(
                    max(0, measurement_started + item["index"] * 4 - time.monotonic())
                )
                tasks.append(asyncio.create_task(offer(item, "measurement")))
            await asyncio.sleep(max(0, measurement_started + duration - time.monotonic()))
            await asyncio.gather(fault_task, burst_task, *tasks)
            status = "executed"
        except Exception as error:
            status = "failed"
            write_json(
                output / "failure.json",
                {"error_type": type(error).__name__, "phase": session.phase},
            )
        finally:
            sampling_stop.set()
            if sampler is not None:
                await sampler
            exported = await session.finish()
            write_json(
                output / "result.json",
                {
                    "status": status,
                    "development_only": development,
                    "measurement_started_seconds": measurement_session_seconds
                    if measurement_started
                    else None,
                    "elapsed_seconds": session.seconds(),
                    "offers": offered,
                    "faults": fault_results,
                    **exported,
                    "passed": False,
                    "acceptance": (
                        "not asserted by the driver; independent complete validation required"
                    ),
                },
            )
    if status != "executed":
        raise ValueError("soak execution incomplete; preserved reports and private runtime")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.environ.get("CIO_TEST_DATABASE_URL"))
    parser.add_argument("--opa", type=Path, required=True)
    parser.add_argument("--caddy", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--development-seconds", type=int)
    parser.add_argument("--development-seed", type=int)
    parser.add_argument(
        "--contention-notes", default="host not CPU isolated; external activity unmeasured"
    )
    asyncio.run(main(parser.parse_args()))
