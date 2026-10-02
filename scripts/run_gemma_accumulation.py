"""Finite longitudinal Gemma study over the source-only registered application.

Smoke, sensitivity calibration and confirmation have separate immutable outputs.
Confirmation refuses unpushed preregistration or changed source/options/seeds.
"""

import argparse
import asyncio
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from accumulation_application import DIGEST, MODEL, wire_schema
from accumulation_host import OwnedOllama, ProcessObserver, runtime_contract
from accumulation_protocol import checker_settings, matched_placebo, schedule
from accumulation_session import ROOT, StudySession
from accumulation_stock import Snapshot
from accumulation_tasks import World
from check_gemma_candidate import installed_candidate

from collective_intelligence_overlay.adapters.inference_observer import write_new


def sources():
    paths = list((ROOT / "src").rglob("*.py"))
    paths += list((ROOT / "src").rglob("*.rego"))
    paths += list((ROOT / "scripts").glob("accumulation_*.py"))
    paths += [
        ROOT / p
        for p in (
            "scripts/run_gemma_accumulation.py",
            "scripts/verify_gemma_accumulation.py",
            "scripts/analyze_gemma_accumulation.py",
            "scripts/prepare_accumulation_protocol.py",
            "scripts/prepare_gemma_public.py",
            "scripts/check_gemma_candidate.py",
            "scripts/check_gemma_state.py",
            "scripts/check_gemma_transport.py",
            "scripts/report_gemma_accumulation.py",
            "scripts/release_gate.py",
            "scripts/release_candidate.py",
            "scripts/production_session.py",
            "scripts/run_production_experiment.py",
            "tests/e2e/production_mesh.py",
            "examples/evaluate_documents.py",
            "pyproject.toml",
            "uv.lock",
        )
    ]
    return {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(paths)
    }


def preregistration(args, protocol):
    if args.classification != "confirmation":
        return None
    if args.prereg_commit is None:
        raise ValueError("confirmation requires a committed and pushed preregistration")
    relative = args.protocol.resolve().relative_to(ROOT).as_posix()
    committed = subprocess.check_output(
        ["git", "show", args.prereg_commit + ":" + relative], cwd=ROOT
    )
    if committed != args.protocol.read_bytes():
        raise ValueError("preregistered original differs from current protocol")
    for tip in ("HEAD", "origin/main"):
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", args.prereg_commit, tip], cwd=ROOT, check=True
        )
    remote = subprocess.check_output(
        ["git", "ls-remote", "origin", "refs/heads/main"], cwd=ROOT, text=True
    ).split()[0]
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", args.prereg_commit, remote], cwd=ROOT, check=True
    )
    if protocol["classification"] != "confirmation" or protocol["model_digest"] != DIGEST:
        raise ValueError("explicit independent confirmation protocol required")
    schema_catalog = {
        family + "/" + level: wire_schema(family, level).model_json_schema()
        for family in ("sql", "calibration", "composition")
        for level in ("low", "middle", "high")
    }
    if (
        protocol.get("schedule_schema") != "2"
        or protocol.get("retrieval_revision") != "2"
        or protocol.get("observation_binding_schema") != "2"
        or protocol.get("wire_schemas") != schema_catalog
    ):
        raise ValueError("confirmation requires the complete current schema and state contracts")
    if datetime.fromisoformat(protocol["registered_at"]) >= datetime.now(UTC):
        raise ValueError("preregistration must precede the first confirmation request")
    if protocol["sources"] != sources():
        raise ValueError("confirmation source/lock/factory/checker changed")
    artifact = protocol["installed_wheel"]
    inspected = installed_candidate(ROOT, artifact)
    if inspected["original_package_file_sha256"] != artifact["package_file_sha256"]:
        raise ValueError("installed candidate package manifest differs from preregistration")
    from release_gate import check_reuse, trusted_run

    gate = protocol["native_gate"]
    paths = {}
    for key in ("candidate_directory", "gate", "release_manifest", "reports_directory"):
        path = (ROOT / gate[key]).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError("native gate evidence must belong to this repository")
        paths[key] = path
    manifest_raw = paths["release_manifest"].read_bytes()
    if hashlib.sha256(manifest_raw).hexdigest() != gate["release_manifest_sha256"]:
        raise ValueError("original candidate release manifest changed")
    native_manifest = json.loads(manifest_raw)
    check_reuse(
        paths["candidate_directory"],
        paths["gate"],
        native_manifest,
        reports=paths["reports_directory"],
    )
    trusted_run(native_manifest["candidate_run_id"], native_manifest["source_commit"])
    if native_manifest["artifacts"][Path(artifact["path"]).name] != artifact["sha256"]:
        raise ValueError("confirmation wheel is not the original full-native-tested candidate")
    sdist = protocol["installed_sdist"]
    if (
        native_manifest["artifacts"][Path(sdist["path"]).name] != sdist["sha256"]
        or hashlib.sha256((ROOT / sdist["path"]).read_bytes()).hexdigest() != sdist["sha256"]
    ):
        raise ValueError("confirmation sdist is not the original full-native-tested pair")
    return {
        "commit": args.prereg_commit,
        "protocol_sha256": hashlib.sha256(committed).hexdigest(),
        "remote_head_before_inference": remote,
        "installed_wheel_sha256": artifact["sha256"],
        "installed_candidate_inspection": inspected,
        "native_gate_sha256": native_manifest["gate_sha256"],
        "native_gate_run_id": native_manifest["candidate_run_id"],
        "native_gate_source_commit": native_manifest["source_commit"],
    }


def smoke_protocol():
    return {
        "id": "cio-042-accumulation-smoke-v5",
        "classification": "smoke",
        "world_seeds": [982317],
        "arms": ["E"],
        "model": MODEL,
        "model_digest": DIGEST,
        "model_options": {
            "num_ctx": 8192,
            "num_predict": 1536,
            "temperature": 0.2,
            "top_p": 0.95,
            "top_k": 64,
            "draft_num_predict": 0,
        },
        "request_seconds": 240,
        "caps": {
            "model_calls": 2,
            "model_tokens": 19456,
            "application_actions": 1024,
            "wall_seconds": 900,
        },
        "cohort_wall_seconds": 1200,
        "schedule": "two-connection-and-usage-probes-not-performance",
        "sources": sources(),
    }


def forms(world, prefix):
    return [
        ("producer", world.sales(prefix + "-sql-low", "low")),
        ("receiver", world.calibration(prefix + "-calibration-middle", "middle")),
    ]


async def run(args):
    args.home, args.output = args.home.resolve(), args.output.resolve()
    if args.classification != "smoke" and args.protocol is None:
        raise ValueError("explicit finite calibration/confirmation protocol required")
    protocol = json.loads(args.protocol.read_bytes()) if args.protocol else smoke_protocol()
    if protocol["classification"] != args.classification or protocol["model_digest"] != DIGEST:
        raise ValueError("protocol/cohort/model mismatch")
    if set(protocol["arms"]) - {"E", "I", "M", "C"}:
        raise ValueError(
            "adaptive A is an unperformed panel, not this fixed allocation implementation"
        )
    registration = preregistration(args, protocol)
    if protocol["sources"] != sources():
        raise ValueError("declared source changed before model/server startup")
    args.output.mkdir()
    args.created = True
    args.home.mkdir()
    write_new(args.output / "protocol.json", protocol)
    write_new(args.output / "source-manifest.json", protocol["sources"])
    for name in protocol["sources"]:
        destination = args.output / "source" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / name).read_bytes())
    observer = ProcessObserver(
        args.output / "os-processes.jsonl",
        protocol["cohort_wall_seconds"],
        interval=protocol.get("OS_observation_interval_seconds", 5),
    )
    server = OwnedOllama(
        args.home / "ollama",
        args.output,
        port=args.port,
        context=protocol["model_options"]["num_ctx"],
        metadata_cap=protocol.get("owned_server_metadata_calls", 160),
    )
    start = time.monotonic()
    cohorts = []
    observer.start()
    try:
        observed_runtime = await server.start()
        if args.classification == "confirmation" and (
            runtime_contract(observed_runtime) != protocol["runtime_contract"]
        ):
            raise ValueError(
                "actual host/model/dependency/backend settings changed before inference"
            )
        remaining = protocol["cohort_wall_seconds"] - (time.monotonic() - start)
        if remaining <= 0:
            raise TimeoutError("cohort wall budget exhausted during owned server startup")
        async with asyncio.timeout(remaining):
            controls = []
            for seed in protocol.get("positive_control_seeds", ()):
                controls.append(await positive_control(args, World(seed), protocol, server))
            for seed in protocol["world_seeds"]:
                world = World(seed)
                order = protocol.get("arm_orders", {}).get(str(seed), protocol["arms"])
                if sorted(order) != sorted(protocol["arms"]):
                    raise ValueError("arm order must contain every declared arm once")
                for arm in order:
                    smoke_offers = forms(world, args.classification)
                    offers = (
                        schedule(world, arm, protocol) if args.classification != "smoke" else ()
                    )
                    checks = (
                        checker_settings(offers)
                        if offers
                        else {
                            f"smoke-{i}": [
                                {
                                    "problem": p.model_dump(mode="json"),
                                    "expected": world.expected(p),
                                }
                            ]
                            for i, (_, p) in enumerate(smoke_offers)
                        }
                    )
                    model = {
                        "host": server.host,
                        "seconds": protocol["request_seconds"],
                        "options": protocol["model_options"],
                        "prompt_revision": protocol.get("prompt_revision", "1"),
                    }
                    output = args.output / (world.id + "-" + arm)
                    s = StudySession(
                        args.home / (world.id + "-" + arm),
                        output,
                        world,
                        arm,
                        protocol,
                        model,
                        checks,
                    )
                    result = {"world": world.id, "seed": seed, "arm": arm, "offers": []}
                    if offers:
                        write_new(
                            output / "offer-plan.json",
                            [
                                {
                                    "id": o.id,
                                    "peer": o.peer,
                                    "task_world": o.world.id,
                                    "phase": o.phase,
                                    "checkpoint": o.checkpoint,
                                    "view": o.view,
                                    "episode": o.episode,
                                    "attempts": o.attempts,
                                    "problem": o.problem.model_dump(mode="json"),
                                }
                                for o in offers
                            ],
                        )
                    try:
                        await s.initialize()
                        if offers:
                            await trajectory(s, offers, result)
                        else:
                            for i, (peer, p) in enumerate(smoke_offers):
                                result["offers"].append(
                                    await s.offer(peer, f"smoke-{i}", p, s.stock, attempts=1)
                                )
                    except Exception as error:
                        result["error_type"] = type(error).__name__
                    finally:
                        result["export"] = await s.finish()
                        write_new(output / "arm-result.json", result)
                        cohorts.append(result)
                    if sources() != protocol["sources"]:
                        raise ValueError("source changed during frozen inference")
        model_observations = [
            read_observation(p) for p in args.output.glob("world-*/model/*/observation.json")
        ]
        connected = len(model_observations) == 2 and all(
            o["status"] == 200 and o["stream_complete"] and o["tokens_measured"] is not None
            for o in model_observations
        )
        write_new(
            args.output / "cohort.json",
            {
                "classification": args.classification,
                "preregistration": registration,
                "arms": cohorts,
                "positive_controls": controls,
                "inclusive_wall_seconds": time.monotonic() - start,
                "smoke_excluded_from_performance": args.classification == "smoke",
                "smoke_connection_and_usage_passed": connected,
            },
        )
    finally:
        cleanup_started = time.monotonic()
        errors = {}
        try:
            await server.close()
        except BaseException as error:
            errors["owned_server"] = type(error).__name__
        finally:
            try:
                observer.close()
            except BaseException as error:
                errors["process_observer"] = type(error).__name__
        cleanup_seconds = time.monotonic() - cleanup_started
        write_new(
            args.output / "cleanup.json",
            {
                "cleanup_wall_seconds": cleanup_seconds,
                "cleanup_grace_seconds": protocol.get("cleanup_grace_seconds", 300),
                "inclusive_cohort_wall_including_cleanup_seconds": time.monotonic() - start,
                "owned_server_physically_stopped": server.process is None
                or server.process.poll() is not None,
                "process_observer_physically_stopped": observer.thread is None
                or not observer.thread.is_alive(),
                "errors": errors,
                "no_past_OS_reobservation_claim": True,
            },
        )
        if errors or cleanup_seconds > protocol.get("cleanup_grace_seconds", 300):
            raise RuntimeError("owned cleanup incomplete or outside declared finite grace")
    clean = all(not c.get("error_type") for c in cohorts)
    return 0 if clean and (connected or args.classification != "smoke") else 1


async def positive_control(args, world, protocol, server):
    offers = [
        o
        for o in schedule(world, "E", protocol)
        if (o.phase == "anchor" and o.checkpoint == 0) or o.phase in {"challenge", "formation"}
    ]
    output = args.output / (world.id + "-positive")
    s = StudySession(
        args.home / output.name,
        output,
        world,
        "E",
        protocol,
        {
            "host": server.host,
            "seconds": protocol["request_seconds"],
            "options": protocol["model_options"],
        },
        checker_settings(offers),
    )
    result = {
        "world": world.id,
        "seed": world.seed,
        "arm": "E",
        "offers": [],
        "classification": "positive-calibration-only",
    }
    try:
        await s.initialize()
        for o in offers:
            solution = world.oracle(o.problem)
            checked = await s.check_constructed(
                "producer", o.id, o.problem, solution, o.id, copied=False
            )
            record = {
                "id": o.id,
                "peer": "producer",
                "world": world.id,
                "task_world": world.id,
                "arm": "E",
                "problem": o.problem.model_dump(mode="json"),
                "view": "empty",
                "snapshot_digest": s.stock.digest,
                "checkpoint": 0,
                "phase": "positive-control",
                "episode": 0,
                "learn": False,
                "attempts": [
                    {
                        "id": o.id,
                        "kind": "oracle-calibration-only",
                        "solution": solution.model_dump(mode="json"),
                        **checked,
                    }
                ],
                "succeeded": checked["succeeded"],
            }
            directory = output / "offers" / o.id
            directory.mkdir(parents=True)
            write_new(
                directory / "intent.json", {k: v for k, v in record.items() if k != "attempts"}
            )
            s.persist_offer(directory, record)
            result["offers"].append(record)
    except Exception as error:
        result["error_type"] = type(error).__name__
    finally:
        result["export"] = await s.finish()
        write_new(output / "arm-result.json", result)
    return result


async def trajectory(s, offers, result):
    pool, final, irrelevant, receiver_stock = [], None, None, None
    result["snapshots"] = {}
    result["qualification"] = []
    for item in offers:
        if item.phase == "qualification":
            if receiver_stock is None:
                result["new_receiver"] = await s.activate_receiver()
                receiver_stock = Snapshot(world=s.world.id, arm=s.arm, checkpoint=6, skills=())
            for source in (
                skill
                for skill in final.skills
                if skill.family == item.problem.family and skill.contract == item.problem.contract
            ):
                await s.import_to(source, "newreceiver")
                checked = await s.check_constructed(
                    "newreceiver",
                    item.id,
                    item.problem,
                    source.solution,
                    item.id,
                    copied=True,
                    source_skill=source,
                )
                result["qualification"].append(
                    {
                        "id": item.id,
                        "source_skill": source.id,
                        "problem": item.problem.model_dump(mode="json"),
                        **checked,
                    }
                )
                if checked["succeeded"]:
                    qualified = s.skill(
                        {**checked, "solution": source.solution.model_dump(mode="json")},
                        "newreceiver",
                        item.problem,
                        6,
                    )
                    receiver_stock = receiver_stock.model_copy(
                        update={"skills": (*receiver_stock.skills, qualified)}
                    )
                break
            continue
        if item.phase == "transfer" and "providers_absent" not in result:
            for owner in ("producer", "receiver"):
                await s.session.stop(owner)
            result["providers_absent"] = {
                owner: {
                    "pid": s.session.processes[owner].pid,
                    "returncode": s.session.processes[owner].poll(),
                }
                for owner in ("producer", "receiver")
            }
            if any(v["returncode"] is None for v in result["providers_absent"].values()):
                raise ValueError("original providers are physically present")
            write_new(s.output / "new-receiver-stock.json", receiver_stock.model_dump(mode="json"))
        if item.phase == "placebo" and final is None:
            final = s.stock
            write_new(s.output / "snapshot-6.json", final.model_dump(mode="json"))
            result["snapshots"]["6"] = final.digest
        if item.phase == "anchor" and item.checkpoint in {0, 3}:
            if str(item.checkpoint) not in result["snapshots"]:
                write_new(
                    s.output / f"snapshot-{item.checkpoint}.json", s.stock.model_dump(mode="json")
                )
                result["snapshots"][str(item.checkpoint)] = s.stock.digest
        if item.phase in {"anchor", "frontier"} and item.checkpoint == 6 and irrelevant is None:
            irrelevant, match = matched_placebo(final, pool)
            result["placebo_matching"] = match
            write_new(s.output / "irrelevant-stock.json", irrelevant.model_dump(mode="json"))
        snapshot = s.stock
        if item.phase == "placebo":
            snapshot = Snapshot(world=s.world.id, arm=s.arm, checkpoint=6, skills=())
        elif item.view == "irrelevant":
            snapshot = irrelevant
        elif item.phase == "transfer":
            snapshot = receiver_stock
        elif final is not None:
            snapshot = final
        # readonly excludes feedback to training; fresh Message is built on every
        # model call. A retry receives only its own public independent failure.
        observed = await s.offer(
            item.peer,
            item.id,
            item.problem,
            snapshot,
            view=item.view,
            attempts=item.attempts,
            episode=item.episode,
            learn=item.phase == "training",
            phase=item.phase,
            task_world=item.world.id,
        )
        result["offers"].append(observed)
        if item.phase == "placebo" and observed["succeeded"]:
            selected = next(a for a in observed["attempts"] if a["succeeded"])
            foreign = s.skill(selected, item.peer, item.problem, 6, source_world=item.world.id)
            pool.append(foreign)
            await s.transfer(foreign)
    if final is not None and s.stock.digest != final.digest:
        raise ValueError("readonly final evaluation changed immutable training state")


def read_observation(path):
    return json.loads(path.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--classification", choices=("smoke", "calibration", "confirmation"), required=True
    )
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--prereg-commit")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--port", type=int, default=11443)
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args))
    except BaseException as error:
        if getattr(args, "created", False):
            write_new(
                args.output / "termination.json",
                {
                    "error_type": type(error).__name__,
                    "classification": args.classification,
                    "completed": False,
                    "at": datetime.now(UTC).isoformat(),
                },
            )
        raise
    raise SystemExit(result)


if __name__ == "__main__":
    main()
