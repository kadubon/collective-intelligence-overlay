"""Offline bounded verification and all-offered endpoints; no network or inference."""

import argparse
import asyncio
import csv
import json
from pathlib import Path

from accumulation_primitives import Problem, Solution, bounded_execute
from accumulation_tasks import compare
from check_gemma_transport import (
    check_model_attempt,
    check_native_observation,
    check_originals,
    check_requested_payload,
    check_selected_identity,
)
from near_transfer_application import model_prompt, wire_schema
from near_transfer_protocol import choose_levels, entrance_gate, restricted_endpoint, sha
from near_transfer_tasks import World
from verify_gemma_accumulation import read, records

from collective_intelligence_overlay.adapters.inference_observer import write_new


async def verify_run(directory):
    protocol = read(directory / "protocol.json")
    for name, digest in protocol["sources"].items():
        if sha(directory / "source-snapshot" / name) != digest:
            raise ValueError("frozen source digest mismatch")
    offers, attempts, sent, normal, measured, charged, missing = [], 0, 0, 0, 0, 0, 0
    reference = []
    for session in sorted(directory.glob("world-043-*")):
        signed, _, states, artifacts = records(session, new_receiver=True)
        world_info = read(session / "initial-stock.json")
        # The stage/seed are recovered from the fixed protocol, not inferred from output.
        candidates = [
            World(seed, stage) for stage, seeds in protocol["stage_seeds"].items() for seed in seeds
        ]
        world = next(w for w in candidates if w.id == world_info["world"])
        for path in sorted(session.glob("offers/*/result.json")):
            offer = read(path)
            problem = Problem.model_validate(offer["problem"])
            if offer["world"] != world.id or world_info["arm"] != offer["arm"]:
                raise ValueError("offer world/arm identity mismatch")
            hidden = world.problem(
                problem.family,
                problem.contract.split("-")[2],
                ("screen" if world.stage == "screen" else "locked") + "/independent",
            )
            if world.stage == "natural-stock":
                split = (
                    "learn/" + offer["id"].split("-")[-1] + "/independent"
                    if offer["learn"]
                    else "transfer/hidden"
                )
                hidden = world.problem(problem.family, problem.contract.split("-")[2], split)
            for attempt in offer["attempts"]:
                if attempt["kind"] == "model" and "model_seed" in attempt:
                    attempts += 1
                    rawdir = session / "model" / attempt["id"]
                    observation, intent = (
                        read(rawdir / "observation.json"),
                        read(rawdir / "intent.json"),
                    )
                    check_model_attempt(offer, attempt, protocol, world.seed, 1)
                    dispatched = observation.get("transport_dispatch_started") is True
                    check_selected_identity(
                        read(rawdir / "model-identity.json"), protocol, dispatched=dispatched
                    )
                    parsed = read(rawdir / "parsed.json")
                    check_originals(rawdir, observation, parsed, offer["peer"], artifacts)
                    if dispatched:
                        sent += 1
                        request = read(rawdir / "request.json")
                        text = model_prompt(
                            problem,
                            [
                                __import__("accumulation_stock").ViewSkill.model_validate(s)
                                for s in parsed["visible_snapshot"]["skills"]
                            ],
                        )
                        check_requested_payload(
                            request,
                            (rawdir / "request.raw").read_bytes(),
                            intent,
                            protocol,
                            attempt["model_seed"],
                            wire_schema(problem.family).model_json_schema(),
                            text,
                        )
                        response_name = "response.raw"
                        check_native_observation(
                            (rawdir / response_name).read_bytes(), observation, intent
                        )
                        normal += int(
                            observation.get("error_type") is None
                            and observation.get("done") is True
                        )
                    usage = observation.get("tokens_measured")
                    reservation = (
                        protocol["model_options"]["num_ctx"]
                        + protocol["model_options"]["num_predict"]
                    )
                    if observation.get("transport_dispatch_started") is False:
                        pass
                    elif isinstance(usage, int):
                        measured += usage
                        charged += usage
                    else:
                        missing += 1
                        charged += reservation
                if attempt.get("solution"):
                    solution = Solution.model_validate(attempt["solution"])
                    outcomes = [
                        compare(await bounded_execute(solution, p), world.expected(p))
                        for p in (problem, hidden)
                    ]
                    passed = all(outcomes)
                    if passed != bool(attempt.get("check", {}).get("verdict") == "PASS"):
                        raise ValueError(
                            "offline independent task quality disagrees with original check"
                        )
            if offer["succeeded"] != any(a.get("succeeded", False) for a in offer["attempts"]):
                raise ValueError("first-pass/offer summary differs")
            row = {
                "world": world.id,
                "stage": world.stage,
                "arm": offer["arm"],
                "view": offer["view"],
                "family": problem.family,
                "level": problem.contract.split("-")[2],
                "offer": offer["id"],
                "succeeded": offer["succeeded"],
                **restricted_endpoint(offer, protocol),
            }
            offers.append(row)
        for path in session.glob("*-reference.json"):
            value = read(path)
            reference.append({"succeeded": value["succeeded"]})
    resource = read(directory / "resources.json")
    if (attempts, measured, charged, missing) != (
        resource["model_calls"],
        resource["measured_tokens"],
        resource["charged_tokens"],
        resource["missing_usage_requests"],
    ):
        raise ValueError("complete model accounting disagrees with cohort resources")
    selection = choose_levels([r for r in offers if r["stage"] == "screen"], protocol["candidates"])
    if selection != read(directory / "selection.json"):
        raise ValueError("difficulty selection changed")
    raw_summary = read(directory / "pilot-summary.json")
    stock_ready = raw_summary["gate"]["natural_stock_reaches_retrieval_and_execution"]
    gate = entrance_gate(
        [r for r in offers if r["stage"] == "locked-validation"],
        reference,
        normal,
        sent,
        stock_ready,
    )
    if gate != raw_summary["gate"]:
        raise ValueError("family-specific entrance gate changed")
    return {
        "classification": "offline_raw_verification",
        "source_files": len(protocol["sources"]),
        "generation_attempts": attempts,
        "sent": sent,
        "normal": normal,
        "measured_tokens": measured,
        "charged_tokens": charged,
        "missing_usage_requests": missing,
        "gate": gate,
        "offers": offers,
        "checks": [
            "source identity",
            "DSSE signatures/CAS hashes",
            "exact requests/native responses",
            "independent sandbox/Decimal task quality",
            "all-offered endpoints",
            "family denominators",
        ],
        "scope": "byte/contract consistency, not proof against a malicious experiment operator",
    }


async def analyze(directory, output):
    output.mkdir(parents=True, exist_ok=False)
    result = await verify_run(directory)
    rows = result.pop("offers")
    write_new(output / "verification.json", result)
    with (output / "paired.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    write_new(
        output / "analysis.json",
        {
            "gate": result["gate"],
            "confirmation": "not_performed",
            "H_ACC": "not_estimated",
            "H_CIO": "not_estimated",
            "H_FORM": "not_estimated",
            "reason": (
                "confirmation requires a locked family-specific sensitivity gate "
                "and a separate preregistration"
            ),
            "maintenance_future": None,
            "break_even": None,
        },
    )
    print(json.dumps(result), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    asyncio.run(analyze(args.run, args.output))


if __name__ == "__main__":
    main()
