"""Offline bounded verification and all-offered endpoints; no network or inference."""

import argparse
import asyncio
import csv
import json
from pathlib import Path

from accumulation_primitives import Problem, Solution, factory
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


def check_transcript(value, world, artifacts, expected_problems=None):
    checked = value["check"]
    original = json.loads(artifacts["verifier", checked["artifact_digest"]])
    transcripts = original["transcripts"]
    if expected_problems is not None and [t["case"]["problem"] for t in transcripts] != [
        p.model_dump(mode="json") for p in expected_problems
    ]:
        raise ValueError("independent checker inputs differ from planned forms")
    failures = set()
    for item in transcripts:
        problem = Problem.model_validate(item["case"]["problem"])
        if item["case"]["expected"] != world.expected(problem):
            raise ValueError("checker expected output differs from independent generator")
        observed = item["observed"]
        passed = observed.get("state") == "completed" and compare(
            observed.get("result"), world.expected(problem)
        )
        if item["passed"] != passed:
            raise ValueError("checker transcript quality changed")
        if not passed:
            if observed.get("state") != "completed":
                failures.add("execution_incomplete_or_unknown")
            elif isinstance(observed.get("result"), dict) and observed["result"].get(
                "program_error"
            ):
                failures.add("program_" + observed["result"]["program_error"])
            else:
                failures.add("semantic_mismatch")
    return failures


async def verify_run(directory):
    protocol = read(directory / "protocol.json")
    for name, digest in protocol["sources"].items():
        if sha(directory / "source-snapshot" / name) != digest:
            raise ValueError("frozen source digest mismatch")
    offers, attempts, sent, normal, measured, charged, missing = [], 0, 0, 0, 0, 0, 0
    reference = []
    for session in sorted(directory.glob("world-043-*")):
        signed, states, artifacts = records(session, new_receiver=True)
        world_info = read(session / "initial-stock.json")
        # The stage/seed are recovered from the fixed protocol, not inferred from output.
        candidates = [
            World(seed, stage) for stage, seeds in protocol["stage_seeds"].items() for seed in seeds
        ]
        world = next(w for w in candidates if w.id == world_info["world"])
        for path in sorted(session.glob("offers/*/result.json")):
            offer = read(path)
            event = signed["event", offer["peer"], "offer-observation-" + offer["id"]]
            if artifacts[offer["peer"], event.subject.digest] != path.read_bytes():
                raise ValueError("offer file differs from original signed/CAS observation")
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
            failure_classes = set()
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
                    event = signed["event", offer["peer"], "model-" + attempt["id"]]
                    if json.loads(artifacts[offer["peer"], event.subject.digest]) != parsed:
                        raise ValueError(
                            "parsed file differs from original signed model observation"
                        )
                    candidate_error = (attempt.get("response", {}).get("result") or {}).get(
                        "error_type"
                    )
                    if candidate_error:
                        failure_classes.add(candidate_error)
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
                    failure_classes.update(
                        check_transcript(attempt, world, artifacts, (problem, hidden))
                    )
                    solution = Solution.model_validate(attempt["solution"])
                    outcomes = [
                        compare(
                            await factory(solution.model_dump(mode="json"))(
                                {"problem": p.model_dump(mode="json")}
                            ),
                            world.expected(p),
                        )
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
                "failure_classes": "|".join(sorted(failure_classes)),
                **restricted_endpoint(offer, protocol),
                "prefix_Q_half_time": int(
                    any(
                        a.get("succeeded")
                        and a["endpoint_wall_seconds"] <= protocol["endpoint_time_seconds"] / 2
                        and a["endpoint_charged_tokens"] <= protocol["endpoint_token_horizon"]
                        for a in offer["attempts"]
                    )
                ),
                "prefix_Q_half_tokens": int(
                    any(
                        a.get("succeeded")
                        and a["endpoint_charged_tokens"] <= protocol["endpoint_token_horizon"] / 2
                        and a["endpoint_wall_seconds"] <= protocol["endpoint_time_seconds"]
                        for a in offer["attempts"]
                    )
                ),
            }
            offers.append(row)
        for path in session.glob("*-reference.json"):
            value = read(path)
            check_transcript(value, world, artifacts)
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
    natural = [read(path) for path in directory.glob("*/natural-stock-validation.json")]
    stock_ready = len(natural) == 2 and all(
        len(n["transfer"]) == 2
        and all(
            t["succeeded"] and t["copied_executable"] and t["generation_calls"] == 0
            for t in n["transfer"]
        )
        for n in natural
    )
    if any(any(p["returncode"] is None for p in n["providers_absent"].values()) for n in natural):
        raise ValueError("providers absent claim lacks physical stop observation")
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
        "reader_sha256": sha(Path(__file__)),
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
