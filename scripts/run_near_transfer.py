"""Prepare/run the bounded v0.4.3 sensitivity study using existing owner sessions."""

import argparse
import asyncio
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from accumulation_application import DIGEST, MODEL
from accumulation_host import OwnedOllama, ProcessObserver, runtime_contract
from accumulation_primitives import bounded_execute
from accumulation_session import ROOT, StudySession
from accumulation_stock import Snapshot
from accumulation_tasks import compare
from check_gemma_candidate import installed_candidate
from near_transfer_application import wire_schema
from near_transfer_protocol import CohortCap, choose_levels, entrance_gate, sha
from near_transfer_tasks import World
from run_gemma_accumulation import sources as old_sources

from collective_intelligence_overlay.adapters.inference_observer import write_new

FAMILIES = ("sql", "calibration", "composition")
CANDIDATES = {"sql": ["S1", "S2"], "calibration": ["K1", "K2"], "composition": ["F0", "F1"]}


def sources():
    return {
        **old_sources(),
        **{
            p.relative_to(ROOT).as_posix(): sha(p)
            for pattern in (
                "scripts/near_transfer_*.py",
                "scripts/run_near_transfer.py",
                "scripts/analyze_near_transfer.py",
                "tests/unit/test_near_transfer*.py",
            )
            for p in ROOT.glob(pattern)
        },
    }


def prepare(path):
    wheel = (
        ROOT
        / ".local/full-042-37126141569-original-v1/candidate/dist"
        / "collective_intelligence_overlay-0.4.2-py3-none-any.whl"
    )
    if not wheel.exists():
        wheel = wheel.parent.parent / wheel.name
    import zipfile

    with zipfile.ZipFile(wheel) as z:
        package = {
            n: __import__("hashlib").sha256(z.read(n)).hexdigest()
            for n in z.namelist()
            if n.startswith("collective_intelligence_overlay/") and not n.endswith("/")
        }
    protocol = {
        "id": "cio-043-near-transfer-cost-pilot-v1",
        "classification": "pilot",
        "registered_at": datetime.now(UTC).isoformat(),
        "sources": sources(),
        "model": MODEL,
        "model_digest": DIGEST,
        "application_factory": "near_transfer_application:configure",
        "model_options": {
            "num_ctx": 4096,
            "num_predict": 1024,
            "temperature": 0.2,
            "top_p": 0.95,
            "top_k": 64,
            "draft_num_predict": 0,
            "num_gpu": 0,
        },
        "request_seconds": 120,
        "pilot_max_requests": 60,
        "smoke_max_requests": 4,
        "caps": {
            "model_calls": 256,
            "model_tokens": 400000,
            "wall_seconds": 14400,
            "application_actions": 12000,
            "execution_invocations": 16000,
            "checker_cases": 12000,
            "retrieval_calls": 1024,
            "model_identity_observations": 256,
            "owner_CAS_bytes": 16777216,
        },
        "cleanup_grace_seconds": 300,
        "service_startup_reservation_seconds": 300,
        "max_waves": 2,
        "candidates": CANDIDATES,
        "screen_examples_per_level": 4,
        "validation_examples_per_family": 6,
        "stage_seeds": {
            "screen": list(range(943100, 943108)),
            "locked-validation": list(range(943200, 943206)),
            "natural-stock": [943300],
            "confirmation": list(range(943400, 943406)),
        },
        "selection": "scratch ordinary-M; closest proportion to .5; ascending candidate tie order",
        "retrieval_revision": "2",
        "observation_binding_schema": "2",
        "new_receiver": True,
        "require_installed_candidate": True,
        "checker_sources": [
            "scripts/near_transfer_tasks.py",
            "scripts/accumulation_tasks.py",
            "scripts/accumulation_primitives.py",
        ],
        "feedback_policy": "none",
        "restricted_endpoints": True,
        "endpoint_time_seconds": 600,
        "endpoint_token_horizon": 10240,
        "wire_schemas": {
            f + "/" + level: wire_schema(f).model_json_schema()
            for f in FAMILIES
            for level in ("low", "middle", "high")
        },
        "installed_wheel": {
            "path": wheel.relative_to(ROOT).as_posix(),
            "sha256": sha(wheel),
            "package_file_sha256": package,
        },
        "runtime_scope": (
            "exact published 0.4.2 noneditable runtime; new scientific sources separately fixed; "
            "final 0.4.3 native gate is distinct"
        ),
        "warmup": (
            "no uncharged warmup generation; first screen inference bears cold load, "
            "fixed serial CPU backend"
        ),
        "confirmation_plan": {
            "worlds": 6,
            "arms": ["M", "C"],
            "training_episodes": 4,
            "training_attempts": 1,
            "probe_attempts": 2,
            "maximum_requests": 192,
        },
        "statistics": {
            "unit": "world",
            "contrasts": ["M:Full-Empty", "C:Full-Empty", "C:Full-M:Full"],
            "directions": "higher Q; lower restricted resources",
            "quality_interest_difference": 0.15,
            "quality_harm_margin": 0.10,
            "resource_interest_fraction": 0.20,
            "interval": "descriptive paired-world bootstrap 95%; small N unstable",
            "multiplicity": (
                "no confirmatory p-value claims; all declared contrasts and families shown"
            ),
            "censoring": (
                "all offered worlds retained; "
                "failure charged endpoint T/B separately from actual usage"
            ),
            "break_even": (
                "same observed quality and unit only; positive savings required; "
                "future maintenance unknown"
            ),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    write_new(path, protocol)
    return protocol


def registration(path, protocol, commit):
    relative = path.resolve().relative_to(ROOT).as_posix()
    if (
        subprocess.check_output(["git", "show", commit + ":" + relative], cwd=ROOT)
        != path.read_bytes()
    ):
        raise ValueError("pushed preregistration bytes required")
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True
    ).strip()
    remote = subprocess.check_output(
        ["git", "ls-remote", "origin", "refs/heads/" + branch], cwd=ROOT, text=True
    ).split()[0]
    subprocess.run(["git", "merge-base", "--is-ancestor", commit, remote], cwd=ROOT, check=True)
    if sources() != protocol["sources"] or datetime.fromisoformat(
        protocol["registered_at"]
    ) >= datetime.now(UTC):
        raise ValueError("changed source or invalid registration time")
    return {
        "commit": commit,
        "branch": branch,
        "remote_tip": remote,
        "checked_before_start_at": datetime.now(UTC).isoformat(),
        "installed_candidate_inspection": installed_candidate(ROOT, protocol["installed_wheel"]),
    }


def plans(world, levels, prefix):
    return [
        (
            prefix + "-" + family,
            family,
            levels[family],
            world.problem(family, levels[family], prefix + "/public"),
            world.problem(family, levels[family], prefix + "/independent"),
        )
        for family in FAMILIES
    ]


def checks(world, plan):
    return {
        identifier: [
            {"problem": p.model_dump(mode="json"), "expected": world.expected(p)}
            for p in (problem, hidden)
        ]
        for identifier, _, _, problem, hidden in plan
    }


def summary(record, family, level, directory):
    return {
        "family": family,
        "level": level,
        "succeeded": record["succeeded"],
        "world": record["world"],
        "offer": record["id"],
        "file": directory.relative_to(directory.parents[3]).as_posix(),
        "error_type": record.get("error_type"),
    }


async def calibration_session(args, protocol, cap, server, world, levels, prefix, reference):
    plan = plans(world, levels, prefix)
    output = args.output / (world.id + "-M")
    s = StudySession(
        args.home / output.name,
        output,
        world,
        "M",
        protocol,
        {
            "host": server.host,
            "seconds": protocol["request_seconds"],
            "options": protocol["model_options"],
            "provenance": {
                "protocol_sha256": sha(args.protocol),
                "source_manifest": protocol["sources"],
            },
        },
        checks(world, plan),
    )
    s.cap = cap
    rows = []
    try:
        await s.initialize()
        for identifier, family, level, problem, hidden in plan:
            if cap.expired():
                break
            solution = world.oracle(problem)
            # Independent reference control through the same installed builder/checker.
            result = await s.check_constructed(
                "producer", identifier, problem, solution, identifier + "-reference", copied=False
            )
            reference.append(
                {
                    "world": world.id,
                    "family": family,
                    "level": level,
                    "succeeded": result["succeeded"],
                }
            )
            write_new(output / (identifier + "-reference.json"), result)
            negative = (
                solution.model_copy(update={"coefficients": (0, 0, 0)})
                if family != "sql"
                else solution.model_copy(
                    update={
                        "sql": (
                            'SELECT "bucket" AS "group", 0 AS value FROM readings GROUP BY bucket'
                        )
                    }
                )
            )
            if compare(await bounded_execute(negative, hidden), world.expected(hidden)):
                raise ValueError("negative control unexpectedly passes")
            record = await s.offer(
                "producer",
                identifier,
                problem,
                s.stock,
                view="empty",
                attempts=1,
                phase=world.stage,
            )
            rows.append(
                summary(record, family, level, output / "offers" / identifier / "result.json")
            )
            print(
                json.dumps(
                    {
                        "stage": world.stage,
                        "family": family,
                        "level": level,
                        "Q": int(record["succeeded"]),
                        "calls": cap.calls,
                        "charged_tokens": cap.charged_tokens,
                    }
                ),
                flush=True,
            )
    finally:
        export = await s.finish()
        write_new(
            output / "session-summary.json",
            {"rows": rows, "export_errors": export["export_errors"]},
        )
    return rows


async def natural_stock_session(args, protocol, cap, server, world, arm, levels):
    plan = []
    for i, family in enumerate(("sql", "calibration", "sql", "calibration"), 1):
        level = levels[family]
        plan.append(
            (
                f"learn-{i}",
                family,
                level,
                world.problem(family, level, f"learn/{i}"),
                world.problem(family, level, f"learn/{i}/independent"),
            )
        )
    for phase in ("qualify", "transfer"):
        for family in ("sql", "calibration"):
            level = levels[family]
            plan.append(
                (
                    phase + "-" + family,
                    family,
                    level,
                    world.problem(family, level, phase + "/public"),
                    world.problem(family, level, phase + "/hidden"),
                )
            )
    output = args.output / (world.id + "-" + arm)
    s = StudySession(
        args.home / output.name,
        output,
        world,
        arm,
        protocol,
        {
            "host": server.host,
            "seconds": protocol["request_seconds"],
            "options": protocol["model_options"],
            "provenance": {
                "protocol_sha256": sha(args.protocol),
                "source_manifest": protocol["sources"],
            },
        },
        checks(world, plan),
    )
    s.cap = cap
    result = {"arm": arm, "world": world.id, "qualification": [], "transfer": []}
    try:
        await s.initialize()
        for i, (identifier, _, _, problem, _) in enumerate(plan[:4], 1):
            await s.offer(
                "producer",
                identifier,
                problem,
                s.stock,
                attempts=1,
                episode=i,
                learn=True,
                phase="training",
            )
        result["initialization"] = await s.activate_receiver()
        qualified = Snapshot(world=world.id, arm=arm, checkpoint=4, skills=())
        for identifier, family, _, problem, _ in plan[4:6]:
            source = next((skill for skill in s.stock.skills if skill.family == family), None)
            if source is None:
                result["qualification"].append(
                    {"family": family, "succeeded": False, "reason": "empty_trained_family"}
                )
                continue
            await s.import_to(source, "newreceiver")
            checked = await s.check_constructed(
                "newreceiver",
                identifier,
                problem,
                source.solution,
                identifier,
                copied=True,
                source_skill=source,
            )
            result["qualification"].append({"family": family, **checked})
            if checked["succeeded"]:
                skill = s.skill(
                    {**checked, "solution": source.solution.model_dump(mode="json")},
                    "newreceiver",
                    problem,
                    4,
                )
                qualified = qualified.model_copy(update={"skills": (*qualified.skills, skill)})
        for owner in ("producer", "receiver"):
            await s.session.stop(owner)
        result["providers_absent"] = {
            owner: {
                "pid": s.session.processes[owner].pid,
                "returncode": s.session.processes[owner].poll(),
            }
            for owner in ("producer", "receiver")
        }
        if any(row["returncode"] is None for row in result["providers_absent"].values()):
            raise ValueError("providers physically present")
        write_new(output / "new-receiver-stock.json", qualified.model_dump(mode="json"))
        for identifier, family, _level, problem, _ in plan[6:]:
            before = cap.calls
            record = await s.offer(
                "newreceiver",
                identifier,
                problem,
                qualified,
                attempts=1,
                phase="stock-path-validation",
            )
            result["transfer"].append(
                {
                    "family": family,
                    "succeeded": record["succeeded"],
                    "generation_calls": cap.calls - before,
                    "retrieval_count": len(record.get("retrieval_candidates", [])),
                    "copied_executable": any(
                        a.get("kind") == "copied-executable" and a.get("succeeded")
                        for a in record["attempts"]
                    ),
                }
            )
    finally:
        result["export"] = await s.finish()
        write_new(output / "natural-stock-validation.json", result)
    return result


async def pilot(args):
    protocol = json.loads(args.protocol.read_bytes())
    registered = registration(args.protocol, protocol, args.prereg_commit)
    args.output.mkdir(parents=True, exist_ok=False)
    args.home.mkdir(parents=True, exist_ok=False)
    cap = CohortCap(protocol, args.output, ROOT)
    # Conservatively reserve preceding operator PG/service startup, rather than
    # treating it as free. Actual launch timing is an additional observation.
    cap.started -= protocol["service_startup_reservation_seconds"]
    server = OwnedOllama(args.home / "ollama", args.output, port=11443, context=4096)
    observer = ProcessObserver(args.output / "process-resources.jsonl", 14700)
    write_new(args.output / "protocol.json", protocol)
    write_new(args.output / "registration.json", registered)
    frozen = args.output / "source-snapshot"
    for name, digest in protocol["sources"].items():
        target = frozen / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
        if sha(target) != digest:
            raise ValueError("source snapshot changed")
    screen, validation, reference, natural = [], [], [], []
    failure = None
    try:
        manifest = await server.start()
        write_new(args.output / "runtime-contract.json", runtime_contract(manifest))
        observer.start()
        for i, seed in enumerate(protocol["stage_seeds"]["screen"]):
            world = World(seed, "screen")
            levels = {family: protocol["candidates"][family][i // 4] for family in FAMILIES}
            screen += await calibration_session(
                args, protocol, cap, server, world, levels, "screen", reference
            )
        selection = choose_levels(screen, protocol["candidates"])
        write_new(args.output / "selection.json", selection)
        # Wave 2 is locked: this choice cannot be updated from these outcomes.
        for seed in protocol["stage_seeds"]["locked-validation"]:
            validation += await calibration_session(
                args,
                protocol,
                cap,
                server,
                World(seed, "locked-validation"),
                selection["selected"],
                "locked",
                reference,
            )
        for arm in ("M", "C"):
            natural.append(
                await natural_stock_session(
                    args,
                    protocol,
                    cap,
                    server,
                    World(protocol["stage_seeds"]["natural-stock"][0], "natural-stock"),
                    arm,
                    selection["selected"],
                )
            )
    except Exception as error:
        failure = type(error).__name__
        write_new(
            args.output / "driver-failure.json",
            {"error_type": failure, "calls": cap.calls, "no_automatic_retry": True},
        )
        raise
    finally:
        cleanup_start = time.monotonic()
        errors = {}
        try:
            await server.close()
        except Exception as error:
            errors["owned_server"] = type(error).__name__
        try:
            observer.close()
        except Exception as error:
            errors["observer"] = type(error).__name__
        cap.close()
        write_new(args.output / "resources.json", cap.report())
        write_new(
            args.output / "wall-accounting.json",
            {
                "measured_driver_wall_seconds": time.monotonic()
                - cap.started
                - protocol["service_startup_reservation_seconds"],
                "preceding_service_startup_reserved_seconds": protocol[
                    "service_startup_reservation_seconds"
                ],
                "cohort_wall_charge_is_conservative_not_fully_measured": True,
                "energy_joules": None,
            },
        )
        write_new(
            args.output / "cleanup.json",
            {
                "wall_seconds": time.monotonic() - cleanup_start,
                "owned_server_stopped": server.process is None or server.process.poll() is not None,
                "observer_stopped": observer.thread is None or not observer.thread.is_alive(),
                "errors": errors,
            },
        )
        observations = [
            json.loads(p.read_bytes()) for p in args.output.glob("*/model/*/observation.json")
        ]
        sent = sum(o.get("transport_dispatch_started") is True for o in observations)
        normal = sum(
            o.get("transport_dispatch_started") is True
            and o.get("error_type") is None
            and o.get("done") is True
            for o in observations
        )
        stock_ready = len(natural) == 2 and all(
            len(n["transfer"]) == 2
            and all(
                t["succeeded"] and t["copied_executable"] and t["generation_calls"] == 0
                for t in n["transfer"]
            )
            for n in natural
        )
        gate = entrance_gate(validation, reference, normal, sent, stock_ready)
        if failure or errors:
            gate.update(
                status="assay_not_ready",
                confirmation_authorized=False,
                driver_error=failure,
                cleanup_errors=errors,
            )
        write_new(
            args.output / "pilot-summary.json",
            {
                "screen": screen,
                "validation": validation,
                "reference": reference,
                "natural_stock": natural,
                "gate": gate,
                "resources": cap.report(),
            },
        )
    print(json.dumps(gate), flush=True)
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("operation", choices=("prepare", "pilot"))
    p.add_argument("--protocol", type=Path, required=True)
    p.add_argument("--output", type=Path)
    p.add_argument("--home", type=Path)
    p.add_argument("--prereg-commit")
    args = p.parse_args()
    if args.operation == "prepare":
        prepare(args.protocol)
        return 0
    if not all((args.output, args.home, args.prereg_commit)):
        p.error("pilot needs --output --home --prereg-commit")
    return asyncio.run(pilot(args))


if __name__ == "__main__":
    raise SystemExit(main())
