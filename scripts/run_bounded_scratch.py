"""Finite 0.4.4 assay over existing installed owner/session/builder/observer APIs."""

import argparse
import asyncio
import json
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from accumulation_host import OwnedOllama, ProcessObserver, runtime_contract
from accumulation_primitives import Solution, bounded_execute
from accumulation_session import ROOT, StudySession
from accumulation_stock import Snapshot
from accumulation_tasks import compare
from bounded_scratch_application import slot_candidates, wire_schema
from bounded_scratch_protocol import FAMILIES, boundary, controls, locked_gate, screen_decision
from bounded_scratch_tasks import World
from check_gemma_candidate import installed_candidate
from near_transfer_protocol import CohortCap, sha
from run_near_transfer import checks
from run_near_transfer import prepare as old_prepare
from run_near_transfer import sources as old_sources

from collective_intelligence_overlay.adapters.inference_observer import write_new


def sources():
    return {
        **old_sources(),
        **{
            p.relative_to(ROOT).as_posix(): sha(p)
            for pattern in (
                "scripts/bounded_scratch_*.py",
                "scripts/run_bounded_scratch.py",
                "scripts/analyze_bounded_scratch.py",
                "scripts/diagnose_near_transfer.py",
                "tests/unit/test_bounded_scratch*.py",
            )
            for p in ROOT.glob(pattern)
        },
    }


def prepare(path, wheel=None):
    with tempfile.TemporaryDirectory() as tmp:
        protocol = old_prepare(Path(tmp) / "base.json", wheel)
    protocol.update(
        id="cio-044-bounded-scratch-v1",
        sources=sources(),
        application_factory="bounded_scratch_application:configure",
        phase_recording="explicit-v1",
        max_waves=3,
        pilot_max_requests=84,
        candidates={f: ["L0", "L1", "L2"] for f in FAMILIES},
        model_options={**protocol["model_options"], "num_predict": 256},
        endpoint_time_seconds=300,
        endpoint_token_horizon=4352,
        stage_seeds={
            "smoke": [944001, 944002],
            "screen-L0": list(range(944100, 944108)),
            "screen-L1": list(range(944110, 944118)),
            "screen-L2": list(range(944120, 944128)),
            "locked-validation": list(range(944200, 944212)),
            "independent-control": list(range(944500, 944596)),
            "confirmation": list(range(944400, 944406)),
        },
        selection="start L1; 8 scratch/family; 0-1 narrow, 6-8 expand; 2-5 select; no revisits",
        validation_examples_per_family=12,
        wire_schemas={
            f + "/" + d: wire_schema(
                World(0, "schema").problem(f, level, "schema")
            ).model_json_schema()
            for f in FAMILIES
            for level, d in (("L0", "low"), ("L1", "middle"), ("L2", "high"))
        },
        checker_sources=[
            "scripts/bounded_scratch_tasks.py",
            "scripts/accumulation_tasks.py",
            "scripts/accumulation_primitives.py",
        ],
        runtime_scope=(
            "published noneditable 0.4.2 runtime; 0.4.4 research sources separately fixed"
        ),
        confirmation_plan={
            "worlds": 6,
            "training_episodes": 4,
            "probe_attempts": 1,
            "maximum_requests": 96,
            "separate_pushed_protocol_required": True,
        },
        stock_diagnosis={
            "maximum_new_generations": 8,
            "sources": "G1/G2 native PASS only",
            "initial_confirmation_stock": "empty, never diagnostic stock",
        },
        controls={
            "worlds": 96,
            "seeds": list(range(944500, 944596)),
            "primary_minimum_functional_classes": 4,
            "gate": "observed quality exceeds independent uniform and best constant rates",
            "pvalues": "descriptive only; no significant intelligence assertion",
        },
    )
    protocol["warmup"] = "4 charged smoke requests; no uncharged generation, serial CPU"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_new(path, protocol)
    return protocol


def registration(path, protocol, commit):
    relative = path.resolve().relative_to(ROOT).as_posix()
    if (
        subprocess.check_output(["git", "show", commit + ":" + relative], cwd=ROOT)
        != path.read_bytes()
    ):
        raise ValueError("exact committed protocol required")
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
        raise ValueError("source changed or registration is not prospective")
    return {
        "commit": commit,
        "remote_tip": remote,
        "checked_at": datetime.now(UTC).isoformat(),
        "installed_candidate": installed_candidate(ROOT, protocol["installed_wheel"]),
    }


def make_plan(world, family, level, name):
    return (
        name,
        family,
        level,
        world.problem(family, level, name + "/public"),
        world.problem(family, level, name + "/independent"),
    )


def create_session(args, protocol, cap, server, world, arm, plan):
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
            "schema_policy": "bounded-slots-v1",
            "provenance": {
                "protocol_sha256": sha(args.protocol),
                "source_manifest": protocol["sources"],
            },
        },
        checks(world, plan),
    )
    s.cap = cap
    write_new(
        output / "planned-tasks.json",
        {
            "world": world.id,
            "seed": world.seed,
            "stage": world.stage,
            "arm": arm,
            "plan": [
                {
                    "offer": i,
                    "family": f,
                    "level": level,
                    "public": p.model_dump(mode="json"),
                    "hidden": h.model_dump(mode="json"),
                }
                for i, f, level, p, h in plan
            ],
        },
    )
    return s


def observed_row(s, record, family, level, block=None):
    model = next((a for a in record["attempts"] if a["kind"] == "model"), {})
    path = s.output / "model" / model.get("id", "missing") / "observation.json"
    observation = json.loads(path.read_bytes()) if path.is_file() else None
    checked = model.get("check", {})
    transcript = (
        json.loads(s.session.configs["verifier"].artifacts().get(checked["artifact_digest"]))[
            "transcripts"
        ]
        if checked
        else []
    )
    return {
        "world": s.world.id,
        "family": family,
        "level": level,
        "block": block,
        "offer": record["id"],
        "succeeded": record["succeeded"],
        "file": (s.output / "offers" / record["id"] / "result.json")
        .relative_to(s.output.parent)
        .as_posix(),
        **boundary(record, observation, transcript),
    }


async def calibration(
    args, protocol, cap, server, world, levels, references, *, block=None, g0=False
):
    families = list(levels)
    if world.seed % 2:
        families.reverse()
    plan = [make_plan(world, f, levels[f], world.stage + "-" + f) for f in families]
    s = create_session(args, protocol, cap, server, world, "M", plan)
    rows = []
    try:
        with s.observe_phase("setup"):
            await s.initialize()
        for identifier, family, level, problem, hidden in plan:
            with s.observe_phase("qualification", offer=identifier, cost_scope="fixed"):
                solution = world.oracle(problem)
                result = await s.check_constructed(
                    "producer",
                    identifier,
                    problem,
                    solution,
                    identifier + "-reference",
                    copied=False,
                )
                references.append(
                    {
                        "world": world.id,
                        "family": family,
                        "level": level,
                        "succeeded": result["succeeded"],
                    }
                )
                write_new(s.output / (identifier + "-reference.json"), result)
                if not result["succeeded"]:
                    raise ValueError(
                        "nonmodel positive control failed; stop before further generation"
                    )
                if g0:
                    # Every candidate traverses the actual builder/checker; exactly one is correct.
                    for i, candidate in enumerate(slot_candidates(family, problem.difficulty)):
                        from bounded_scratch_application import compile_slots

                        value = compile_slots(problem, candidate)
                        actual = await s.check_constructed(
                            "producer",
                            identifier,
                            problem,
                            value,
                            f"{identifier}-candidate-{i}",
                            copied=False,
                        )
                        wanted = compare(
                            await bounded_execute(value, hidden), world.expected(hidden)
                        )
                        if actual["succeeded"] != wanted:
                            raise ValueError(
                                "actual builder candidate control disagrees with oracle"
                            )
                        write_new(s.output / f"{identifier}-candidate-{i}.json", actual)
            record = await s.offer(
                "producer",
                identifier,
                problem,
                s.stock,
                view="empty",
                attempts=1,
                phase="formation" if family == "composition" else "probe",
            )
            row = observed_row(s, record, family, level, block)
            rows.append(row)
            print(
                json.dumps(
                    {
                        "stage": world.stage,
                        "family": family,
                        "level": level,
                        "Q": int(record["succeeded"]),
                        "boundary": row["stage"],
                        "calls": cap.calls,
                        "charged_tokens": cap.charged_tokens,
                    }
                ),
                flush=True,
            )
            if not all(row[k] for k in ("normal", "schema", "executable")):
                break
    finally:
        exported = await s.finish()
        write_new(s.output / "session-summary.json", {"rows": rows, "export": exported})
    return rows


async def stock_diagnosis(args, protocol, cap, server, source):
    """Same natural pilot output, separately constructed in M/C; zero oracle stock."""
    source_offer = json.loads((args.output / source["file"]).read_bytes())
    solution = Solution.model_validate(
        next(a for a in source_offer["attempts"] if a["succeeded"])["solution"]
    )
    original_session = args.output / source["file"].split("/")[0]
    original_plan = json.loads((original_session / "planned-tasks.json").read_bytes())
    world = World(original_plan["seed"], original_plan["stage"])
    family, level = source["family"], source["level"]
    outputs = []
    for arm in ("M", "C"):
        # Same world law, distinct owner histories and output directory.
        plan = [
            make_plan(world, family, level, name)
            for name in ("diagnostic-bind", "qualify", "transfer", "empty")
        ]
        local_args = argparse.Namespace(
            **{**vars(args), "output": args.output / ("G3-" + arm + "-" + family)}
        )
        local_args.output.mkdir()
        s = create_session(local_args, protocol, cap, server, world, arm, plan)
        result = {
            "source_offer_file": source["file"],
            "source_response_not_regenerated": True,
            "arm": arm,
            "family": family,
            "new_generations": 0,
        }
        try:
            with s.observe_phase("setup"):
                await s.initialize()
            _, _, _, problem, _ = plan[0]
            with s.observe_phase("qualification", offer="diagnostic-bind"):
                checked = await s.check_constructed(
                    "producer",
                    "diagnostic-bind",
                    problem,
                    solution,
                    "diagnostic-bind",
                    copied=False,
                )
            if not checked["succeeded"]:
                raise ValueError("natural pilot candidate cannot be reconstructed")
            skill = s.skill(
                {**checked, "solution": solution.model_dump(mode="json")},
                "producer",
                problem,
                0,
                source_world=world.id,
            )
            result["initialization"] = await s.activate_receiver()
            await s.import_to(skill, "newreceiver")
            _, _, _, problem, _ = plan[1]
            with s.observe_phase("qualification", offer="qualify"):
                checked = await s.check_constructed(
                    "newreceiver",
                    "qualify",
                    problem,
                    solution,
                    "qualify",
                    copied=True,
                    source_skill=skill,
                )
            result["qualification"] = checked
            qualified_skill = s.skill(
                {**checked, "solution": solution.model_dump(mode="json")}, "newreceiver", problem, 0
            )
            qualified = Snapshot(world=world.id, arm=arm, checkpoint=0, skills=(qualified_skill,))
            write_new(s.output / "new-receiver-stock.json", qualified.model_dump(mode="json"))
            for owner in ("producer", "receiver"):
                await s.session.stop(owner)
            result["providers_absent"] = {
                o: {"pid": s.session.processes[o].pid, "returncode": s.session.processes[o].poll()}
                for o in ("producer", "receiver")
            }
            if any(r["returncode"] is None for r in result["providers_absent"].values()):
                raise ValueError("original provider still running")
            before = cap.calls
            full = await s.offer(
                "newreceiver", "transfer", plan[2][3], qualified, attempts=1, phase="probe"
            )
            if cap.calls != before:
                raise ValueError(
                    "Full diagnostic should execute imported skill without new inference"
                )
            result["full"] = {
                "succeeded": full["succeeded"],
                "calls": cap.calls - before,
                "copied_executable": any(
                    a["kind"] == "copied-executable" and a["succeeded"] for a in full["attempts"]
                ),
            }
            before = cap.calls
            empty = await s.offer(
                "newreceiver",
                "empty",
                plan[3][3],
                qualified,
                view="empty",
                attempts=1,
                phase="probe",
            )
            result["empty"] = {
                "succeeded": empty["succeeded"],
                "calls": cap.calls - before,
                "retrieval_count": len(empty.get("retrieval_candidates", [])),
            }
            result["new_generations"] = cap.calls - before
            result["ready"] = (
                full["succeeded"]
                and result["full"]["copied_executable"]
                and (result["empty"]["calls"] == 1 and result["empty"]["retrieval_count"] == 0)
            )
        finally:
            result["export"] = await s.finish()
            write_new(s.output / "stock-diagnosis.json", result)
        outputs.append(result)
    return outputs


async def pilot(args):
    protocol = json.loads(args.protocol.read_bytes())
    registered = registration(args.protocol, protocol, args.prereg_commit)
    args.output.mkdir(parents=True, exist_ok=False)
    args.home.mkdir(parents=True, exist_ok=False)
    cap = CohortCap(protocol, args.output, ROOT)
    cap.started -= protocol["service_startup_reservation_seconds"]
    server = OwnedOllama(args.home / "ollama", args.output, port=11444, context=4096)
    observer = ProcessObserver(args.output / "process-resources.jsonl", 14700)
    write_new(args.output / "protocol.json", protocol)
    write_new(args.output / "registration.json", registered)
    for name, digest in protocol["sources"].items():
        target = args.output / "source-snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
        if sha(target) != digest:
            raise ValueError("source snapshot mismatch")
    smoke, screen, locked, references, natural, decisions, selected = [], [], [], [], [], [], {}
    error, control_results = None, {}
    try:
        manifest = await server.start()
        write_new(args.output / "runtime-contract.json", runtime_contract(manifest))
        observer.start()
        for i, seed in enumerate(protocol["stage_seeds"]["smoke"]):
            smoke += await calibration(
                args,
                protocol,
                cap,
                server,
                World(seed, "smoke"),
                {f: "L1" if i == 0 else "L2" for f in FAMILIES},
                references,
                g0=True,
            )
            if not all(all(r[k] for k in ("normal", "schema", "executable")) for r in smoke):
                break
        g0 = len(smoke) == 4 and all(
            all(r[k] for k in ("normal", "schema", "executable")) for r in smoke
        )
        if g0:
            for family in FAMILIES:
                current, visited = "L1", []
                while current and len(visited) < 3:
                    visited.append(current)
                    batch = []
                    for seed in protocol["stage_seeds"]["screen-" + current]:
                        batch += await calibration(
                            args,
                            protocol,
                            cap,
                            server,
                            World(seed, "screen-" + current + "-" + family),
                            {family: current},
                            references,
                        )
                        if not all(
                            all(r[k] for k in ("normal", "schema", "executable")) for r in batch
                        ):
                            break
                    screen += batch
                    decision = screen_decision(batch, current, visited)
                    decisions.append({"family": family, "level": current, **decision})
                    write_new(args.output / f"decision-{family}-{current}.json", decisions[-1])
                    if decision["selected"]:
                        selected[family] = current
                    current = decision["next"]
                if decision["reason"] == "boundary_or_incomplete_stop":
                    break
        write_new(args.output / "selection.json", {"selected": selected, "decisions": decisions})
        for family, level in selected.items():
            control_results[family] = await controls(family, level, protocol["controls"]["seeds"])
        write_new(args.output / "controls.json", control_results)
        if len(selected) == 2:
            for i, seed in enumerate(protocol["stage_seeds"]["locked-validation"]):
                locked += await calibration(
                    args,
                    protocol,
                    cap,
                    server,
                    World(seed, "locked-validation"),
                    selected,
                    references,
                    block=i // 6,
                )
                if not all(all(r[k] for k in ("normal", "schema", "executable")) for r in locked):
                    break
        # G3 is a path diagnostic; never a benefit contrast or confirmation stock.
        passed = [r for r in (*screen, *locked) if r["succeeded"]]
        for family in FAMILIES:
            source = next((r for r in passed if r["family"] == family), None)
            if source:
                natural += await stock_diagnosis(args, protocol, cap, server, source)
    except Exception as exc:
        error = type(exc).__name__
        write_new(
            args.output / "driver-failure.json",
            {"error_type": error, "calls": cap.calls, "automatic_retry": False},
        )
        raise
    finally:
        started = time.monotonic()
        await server.close()
        observer.close()
        cap.close()
        write_new(args.output / "resources.json", cap.report())
        write_new(
            args.output / "wall-accounting.json",
            {
                "measured_driver_wall_seconds": time.monotonic() - cap.started - 300,
                "preceding_setup_reserved_seconds": 300,
                "inclusive_total_charge_seconds": cap.report()["inclusive_wall_seconds"],
                "RPC_wall_is_nested_not_added": True,
                "energy_joules": None,
                "full_compute": None,
                "future_maintenance": None,
            },
        )
        write_new(
            args.output / "cleanup.json",
            {
                "seconds": time.monotonic() - started,
                "owned_server_stopped": server.process is None or server.process.poll() is not None,
                "observer_stopped": observer.thread is None or not observer.thread.is_alive(),
            },
        )
        stock_ready = len(natural) == 4 and all(r.get("ready") for r in natural)
        gate = locked_gate(
            locked,
            selected,
            control_results,
            g0=len(smoke) == 4 and error is None,
            stock_ready=stock_ready,
        )
        write_new(
            args.output / "pilot-summary.json",
            {
                "smoke": smoke,
                "screen": screen,
                "locked": locked,
                "reference": references,
                "selected": selected,
                "decisions": decisions,
                "natural_stock": natural,
                "gate": gate,
                "driver_error": error,
            },
        )
    print(json.dumps(gate), flush=True)
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("operation", choices=("prepare", "pilot"))
    p.add_argument("--protocol", type=Path, required=True)
    p.add_argument("--wheel", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--home", type=Path)
    p.add_argument("--prereg-commit")
    args = p.parse_args()
    if args.operation == "prepare":
        prepare(args.protocol, args.wheel)
        return 0
    if not all((args.output, args.home, args.prereg_commit)):
        p.error("pilot requires output, private home and pushed preregistration commit")
    return asyncio.run(pilot(args))


if __name__ == "__main__":
    raise SystemExit(main())
