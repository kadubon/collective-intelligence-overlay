"""Offline signed/CAS/native-byte verification and all-offered 0.4.4 analysis."""

import argparse
import asyncio
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from accumulation_primitives import Problem, Solution, bounded_execute
from accumulation_stock import ViewSkill
from accumulation_tasks import compare
from analyze_near_transfer import check_transcript
from bounded_scratch_application import compile_slots, model_prompt, wire_schema
from bounded_scratch_protocol import boundary, controls, locked_gate, screen_decision
from bounded_scratch_tasks import World
from check_gemma_transport import (
    check_model_attempt,
    check_native_observation,
    check_originals,
    check_requested_payload,
    check_selected_identity,
    validate_wire,
)
from near_transfer_protocol import proportion, restricted_endpoint, sha
from verify_gemma_accumulation import read, records

from collective_intelligence_overlay.adapters.inference_observer import write_new


async def verify_run(directory):
    protocol = read(directory / "protocol.json")
    if protocol["id"] != "cio-044-bounded-scratch-v1":
        raise ValueError("wrong study schema; old and new assays are not interchangeable")
    for name, digest in protocol["sources"].items():
        if sha(directory / "source-snapshot" / name) != digest:
            raise ValueError("frozen study source changed")
    for name in ("bounded_scratch_tasks.py", "bounded_scratch_application.py"):
        if sha(Path(__file__).parent / name) != protocol["sources"]["scripts/" + name]:
            raise ValueError("current generator/compiler differs from frozen assay")
    summary = read(directory / "pilot-summary.json")
    offered, pending, planned_unoffered, report_rows = [], [], [], []
    model_calls = sent = normal = measured = charged = missing = 0
    rpc_phases, rpc_offer_counts = (
        defaultdict(lambda: {"calls": 0, "nested_wall_seconds": 0}),
        Counter(),
    )
    for plan_path in sorted(directory.rglob("planned-tasks.json")):
        session = plan_path.parent
        planned = read(plan_path)
        world = World(planned["seed"], planned["stage"])
        if world.id != planned["world"]:
            raise ValueError("planned world identity changed")
        signed, _, artifacts = records(session, new_receiver=True)
        initial = read(session / "initial-stock.json")
        if initial["skills"]:
            raise ValueError("initial stock is not empty")
        plans = {p["offer"]: p for p in planned["plan"]}
        for p in plans.values():
            for name in ("public", "hidden"):
                split = p["offer"] + ("/public" if name == "public" else "/independent")
                if world.problem(p["family"], p["level"], split).model_dump(mode="json") != p[name]:
                    raise ValueError("planned task differs from preregistered generator")
        for intent_path in sorted(session.glob("offers/*/intent.json")):
            result_path = intent_path.parent / "result.json"
            if not result_path.is_file():
                pending.append(str(intent_path.relative_to(directory)))
                continue
            offer = read(result_path)
            p = plans[offer["id"]]
            problem, hidden = (Problem.model_validate(p[k]) for k in ("public", "hidden"))
            if offer["problem"] != p["public"]:
                raise ValueError("offered problem differs from planned public contract")
            event = signed["event", offer["peer"], "offer-observation-" + offer["id"]]
            if artifacts[offer["peer"], event.subject.digest] != result_path.read_bytes():
                raise ValueError("offer is not the signed original CAS observation")
            observation, transcripts = None, []
            for attempt in offer["attempts"]:
                if attempt["kind"] == "model" and "model_seed" in attempt:
                    model_calls += 1
                    rawdir = session / "model" / attempt["id"]
                    observation, intent, parsed = (
                        read(rawdir / name)
                        for name in ("observation.json", "intent.json", "parsed.json")
                    )
                    check_model_attempt(offer, attempt, protocol, world.seed, 1)
                    dispatched = observation.get("transport_dispatch_started") is True
                    check_selected_identity(
                        read(rawdir / "model-identity.json"), protocol, dispatched=dispatched
                    )
                    event = signed["event", offer["peer"], "model-" + attempt["id"]]
                    if json.loads(artifacts[offer["peer"], event.subject.digest]) != parsed:
                        raise ValueError("parsed output differs from signed CAS")
                    check_originals(rawdir, observation, parsed, offer["peer"], artifacts)
                    if parsed["slot_schema_revision"] != "bounded-slots-v1":
                        raise ValueError("wrong wire revision")
                    context = {
                        "phase": offer["phase"],
                        "offer_id": offer["id"],
                        "stage": world.stage,
                        "cost_scope": "training_fixed" if offer["learn"] else "online",
                    }
                    if (
                        parsed["study_context"] != context
                        or intent["identity"]["study_context"] != context
                    ):
                        raise ValueError("model phase/offer attribution changed")
                    visible = [
                        ViewSkill.model_validate(s) for s in parsed["visible_snapshot"]["skills"]
                    ]
                    if offer["view"] == "empty" and visible:
                        raise ValueError("Empty model context contains cognitive stock")
                    if dispatched:
                        sent += 1
                        check_requested_payload(
                            read(rawdir / "request.json"),
                            (rawdir / "request.raw").read_bytes(),
                            intent,
                            protocol,
                            attempt["model_seed"],
                            wire_schema(problem, visible).model_json_schema(),
                            model_prompt(problem, visible),
                        )
                        final = check_native_observation(
                            (rawdir / "response.raw").read_bytes(), observation, intent
                        )
                        normal += int(
                            observation.get("error_type") is None
                            and observation.get("done") is True
                        )
                        if parsed["solution"]:
                            fields = validate_wire(
                                final["message"]["content"],
                                wire_schema(problem).model_json_schema(),
                                wire_schema(problem),
                            ).model_dump(mode="json")
                            if (
                                fields != parsed["model_fields"]
                                or compile_slots(problem, fields).model_dump(mode="json")
                                != parsed["solution"]
                            ):
                                raise ValueError("host plan differs from exact native model slots")
                    usage = observation.get("tokens_measured")
                    if observation.get("transport_dispatch_started") is not False:
                        if type(usage) is int:
                            measured += usage
                            charged += usage
                        else:
                            missing += 1
                            charged += protocol["endpoint_token_horizon"]
                if attempt.get("check"):
                    check_transcript(attempt, world, artifacts, (problem, hidden))
                    transcripts = json.loads(
                        artifacts["verifier", attempt["check"]["artifact_digest"]]
                    )["transcripts"]
                if attempt.get("solution"):
                    solution = Solution.model_validate(attempt["solution"])
                    quality = all(
                        [
                            compare(await bounded_execute(solution, x), world.expected(x))
                            for x in (problem, hidden)
                        ]
                    )
                    # Receipt completion is necessary in addition to checker equality.
                    wanted = (
                        quality and (attempt.get("execution") or {}).get("state") == "completed"
                    )
                    if bool(attempt["succeeded"]) != wanted:
                        raise ValueError("quality/receipt result differs from original score")
            if bool(offer["succeeded"]) != any(a["succeeded"] for a in offer["attempts"]):
                raise ValueError("offer success changed")
            classification = boundary(offer, observation, transcripts)
            row = {
                "world": world.id,
                "family": p["family"],
                "level": p["level"],
                "block": protocol["stage_seeds"]["locked-validation"].index(world.seed) // 6
                if world.stage == "locked-validation"
                else None,
                "offer": offer["id"],
                "succeeded": offer["succeeded"],
                "file": result_path.relative_to(directory).as_posix(),
                **classification,
            }
            offered.append(row)
            report_rows.append(
                {
                    **row,
                    **restricted_endpoint(offer, protocol),
                    "arm": offer["arm"],
                    "view": offer["view"],
                    "study_stage": world.stage,
                }
            )
        for p in plans.values():
            if not (session / "offers" / p["offer"] / "intent.json").exists():
                planned_unoffered.append({"world": world.id, "offer": p["offer"]})
        for line in (session / "calls.jsonl").read_text().splitlines():
            call = json.loads(line)
            if (
                call["phase"]
                not in {
                    "setup",
                    "training",
                    "import",
                    "qualification",
                    "probe",
                    "formation",
                    "cleanup",
                }
                or call.get("stage") != world.stage
            ):
                raise ValueError("RPC phase attribution invalid")
            item = rpc_phases[call["phase"] + "/" + call["cost_scope"]]
            item["calls"] += 1
            item["nested_wall_seconds"] += call["wall_seconds"]
            if call.get("offer_id"):
                rpc_offer_counts[call["offer_id"]] += 1
        for control_path in list(session.glob("*-reference.json")) + list(
            session.glob("*-candidate-*.json")
        ):
            value = read(control_path)
            if value.get("check"):
                check_transcript(value, world, artifacts)
    keyed = {r["file"]: r for r in offered}
    for section in ("smoke", "screen", "locked"):
        for original in summary[section]:
            if keyed.get(original["file"]) != original:
                raise ValueError("published summary differs from offline raw recomputation")
    for decision in summary["decisions"]:
        family, level = decision["family"], decision["level"]
        rows = [r for r in summary["screen"] if r["family"] == family and r["level"] == level]
        visited = [d["level"] for d in summary["decisions"] if d["family"] == family]
        actual = screen_decision(rows, level, visited[: visited.index(level) + 1])
        if any(decision[k] != actual[k] for k in actual):
            raise ValueError("directional selection differs from declared rule")
    recomputed_controls = {
        f: await controls(f, level, protocol["controls"]["seeds"])
        for f, level in summary["selected"].items()
    }
    if read(directory / "controls.json") != recomputed_controls:
        raise ValueError("nonlearning controls changed")
    natural = summary["natural_stock"]
    for n in natural:
        if any(p["returncode"] is None for p in n["providers_absent"].values()):
            raise ValueError("provider was not physically absent")
    gate = locked_gate(
        summary["locked"],
        summary["selected"],
        recomputed_controls,
        g0=len(summary["smoke"]) == 4 and summary["driver_error"] is None,
        stock_ready=len(natural) == 4 and all(n.get("ready") for n in natural),
    )
    if gate != summary["gate"]:
        raise ValueError("stage gate changed")
    resources = read(directory / "resources.json")
    if any(
        resources[k] != v
        for k, v in (
            ("model_calls", model_calls),
            ("charged_tokens", charged),
            ("measured_tokens", measured),
            ("missing_usage_requests", missing),
        )
    ):
        raise ValueError("global model accounting differs from original native bytes")
    return {
        "verification": "passed",
        "protocol_sha256": sha(directory / "protocol.json"),
        "reader_sha256": sha(Path(__file__)),
        "offered": len(offered),
        "pending": pending,
        "planned_unoffered": planned_unoffered,
        "all_offered_rows": report_rows,
        "generation_calls": model_calls,
        "sent": sent,
        "normal": normal,
        "measured_tokens": measured,
        "charged_tokens": charged,
        "usage_missing": missing,
        "RPC_phases": dict(rpc_phases),
        "RPC_offer_counts": dict(rpc_offer_counts),
        "RPC_wall_is_nested_and_not_added_to_inclusive_wall": True,
        "screen": {
            f + "/" + level: proportion(
                [r for r in summary["screen"] if r["family"] == f and r["level"] == level]
            )
            for f in ("sql", "composition")
            for level in ("L0", "L1", "L2")
        },
        "controls": recomputed_controls,
        "gate": gate,
        "confirmation_started": False,
        "contrasts": None,
        "break_even": None,
        "energy_joules": None,
        "full_compute": None,
        "future_maintenance": None,
    }


async def analyze(directory, output):
    result = await verify_run(directory)
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / "analysis.json", result)
    with (output / "paired.csv").open("x", encoding="utf-8", newline="") as stream:
        rows = result["all_offered_rows"]
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(
        json.dumps(
            {
                k: result[k]
                for k in ("verification", "offered", "generation_calls", "charged_tokens", "gate")
            }
        )
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    import socket

    def blocked(*a, **kw):
        raise RuntimeError("offline analyzer prohibits network and inference")

    socket.socket.connect = blocked
    socket.create_connection = blocked
    asyncio.run(analyze(args.run, args.output))


if __name__ == "__main__":
    main()
