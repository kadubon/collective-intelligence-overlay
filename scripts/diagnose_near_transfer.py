"""Cause ledger from preserved 0.4.3 responses; never change the old score/raw.

Reuse the hash-verified delivered archive and existing verified derivatives.
Replay only the bounded installed read-only primitives for diagnostic exceptions.
No model, service, hidden feedback or parser rescue is used to change old results.
"""

import argparse
import asyncio
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from accumulation_primitives import Problem, Solution, execute_solution, readonly_sql
from accumulation_tasks import compare
from near_transfer_tasks import World
from verify_gemma_accumulation import records


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def native_text(path):
    value = json.loads(path.read_bytes())
    return value["message"]["content"]


async def diagnose(run, output, verification):
    run, output = Path(run), Path(output)
    proof = json.loads(await asyncio.to_thread(Path(verification).read_bytes))
    if not (proof.get("verification_equals_published") and proof.get("analysis_equals_published")):
        raise ValueError("existing delivered-archive verification is required")
    root = run.parent
    manifest = json.loads((root / "file-manifest.json").read_bytes())
    protocol = json.loads((run / "protocol.json").read_bytes())
    # Verify the exact reused inputs, not a claim in the old results JSON alone.
    for name in ("accumulation_primitives.py", "near_transfer_tasks.py"):
        expected = protocol["sources"]["scripts/" + name]
        if sha((Path(__file__).parent / name).read_bytes()) != expected:
            raise ValueError("diagnostic primitive/generator differs from old frozen source")
    ledger, counts = [], Counter()
    for session in sorted(run.glob("world-043-*")):
        signed, _, artifacts = records(session, new_receiver=True)
        for path in sorted(session.glob("offers/*/result.json")):
            relative = path.relative_to(root).as_posix()
            if sha(path.read_bytes()) != manifest[relative]:
                raise ValueError("reused original offer changed")
            offer = json.loads(path.read_bytes())
            problem = Problem.model_validate(offer["problem"])
            world = next(
                World(seed, stage)
                for stage, seeds in protocol["stage_seeds"].items()
                for seed in seeds
                if World(seed, stage).id == offer["world"]
            )
            hidden_split = (
                (
                    "learn/" + offer["id"].split("-")[-1] + "/independent"
                    if offer["learn"]
                    else "transfer/hidden"
                )
                if world.stage == "natural-stock"
                else ("screen/independent" if world.stage == "screen" else "locked/independent")
            )
            hidden = world.problem(problem.family, problem.contract.split("-")[2], hidden_split)
            attempt = offer["attempts"][0]
            rawdir = session / "model" / attempt["id"]
            observed = json.loads((rawdir / "observation.json").read_bytes())
            parsed = json.loads((rawdir / "parsed.json").read_bytes())
            event = signed["event", offer["peer"], "model-" + attempt["id"]]
            if json.loads(artifacts[offer["peer"], event.subject.digest]) != parsed:
                raise ValueError("parsed values differ from signed CAS")
            raw = (rawdir / "response.raw").read_bytes()
            for filename in ("response.raw", "parsed.json", "request.raw"):
                f = rawdir / filename
                if sha(f.read_bytes()) != manifest[f.relative_to(root).as_posix()]:
                    raise ValueError("verified transport input changed")
            response_values = json.loads(native_text(rawdir / "response.raw"))
            solution = Solution.model_validate(parsed["solution"]) if parsed["solution"] else None
            error = (attempt.get("response", {}).get("result") or {}).get("error_type")
            item = {
                "offer": offer["id"],
                "world": offer["world"],
                "arm": offer["arm"],
                "family": problem.family,
                "old_pass": offer["succeeded"],
                "old_error": error,
                "old_offer_file": relative,
                "original_response_file": (rawdir / "response.raw").relative_to(root).as_posix(),
                "original_response_sha256": sha(raw),
                "parsed_sha256": sha((rawdir / "parsed.json").read_bytes()),
                "signed_parsed_subject_digest": event.subject.digest,
                "model_values": response_values,
                "executed_plan": attempt.get("solution"),
                "diagnostic_replay": [],
                "secondary_findings": [],
            }
            if (
                not observed["stream_complete"]
                or observed.get("error_type")
                or observed["tokens_measured"] is None
            ):
                stage, cause = 1, "transport_or_usage_boundary"
            elif error == "InvisibleSkillReference":
                stage, cause = 2, "scratch_schema_allowed_nonvisible_skill_ids"
                item["invisible_ids"] = (
                    list(solution.uses) if solution else response_values.get("uses")
                )
            elif solution is None:
                stage, cause = 2, "json_or_schema_rejection"
            else:
                stage, cause = (
                    (0, "passed") if offer["succeeded"] else (5, "semantic_or_numeric_mismatch")
                )
            if solution:
                for p in (problem, hidden):
                    try:
                        actual = await execute_solution(solution, p)
                        replay = {
                            "case": "public" if p is problem else "hidden",
                            "completed": True,
                            "matches_independent_expected": compare(actual, world.expected(p)),
                            "actual": actual,
                        }
                    except Exception as exc:
                        message = str(exc)[:300]
                        replay = {
                            "case": "public" if p is problem else "hidden",
                            "completed": False,
                            "exception_type": type(exc).__name__,
                            "diagnostic_message": message,
                        }
                        if stage != 2:
                            if (
                                message
                                in {
                                    "query must return exactly group,value in that order",
                                    "bounded text group required",
                                    "finite numeric value required",
                                }
                                or "no such column" in message
                                or "no such table" in message
                            ):
                                stage, cause = 3, "query_output_or_declared_input_contract"
                            else:
                                stage, cause = 4, "sql_syntax_authorizer_or_execution"
                    item["diagnostic_replay"].append(replay)
                if problem.family == "composition" and re.search(
                    r"\b(?:GROUP\s+BY|SUM\s*\(|AVG\s*\()", solution.sql, re.I
                ):
                    try:
                        sql_rows = readonly_sql(solution.sql, problem)
                        item["secondary_findings"].append(
                            {
                                "kind": "sql_preaggregation_before_installed_reduction",
                                "query_rows": len(sql_rows),
                                "scope": (
                                    "Observed query aggregate tokens and actual output; "
                                    "not assumed to explain every mismatch."
                                ),
                            }
                        )
                    except Exception:
                        pass
                if problem.family != "sql":
                    c = solution.coefficients
                    fits = all(
                        abs(c[0] + c[1] * x + c[2] * x * x - y) <= 1e-5 + 1e-5 * abs(y)
                        for x, y in problem.observations
                    )
                    item["secondary_findings"].append(
                        {"kind": "coefficients_fit_public_observations", "matches": fits}
                    )
            item.update(primary_stage=stage, primary_cause=cause)
            counts[str(stage) + ":" + cause] += 1
            ledger.append(item)
    if len(ledger) != 54 or sum(not r["old_pass"] for r in ledger) != 53:
        raise ValueError("old denominator changed")
    output.mkdir(parents=True, exist_ok=False)
    summary = {
        "classification": "diagnostic_replay_not_new_model_observations",
        "old_offered": 54,
        "old_failures": 53,
        "old_scores_unchanged": True,
        "old_verifier_rerun": False,
        "existing_verification_proof_sha256": sha(
            await asyncio.to_thread(Path(verification).read_bytes)
        ),
        "diagnostic_primitives_match_frozen_source": True,
        "counts": dict(sorted(counts.items())),
        "new_inference": False,
        "assay_ambiguity_or_checker_defect_confirmed": False,
        "scope": (
            "Reuse exact verified delivered inputs; signed CAS links rechecked. "
            "Exception messages accompany actual replay and original plans, "
            "not stand-alone causal evidence."
        ),
    }
    for name, value in [("failure-ledger.json", ledger), ("summary.json", summary)]:
        with (output / name).open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verified-delivery", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(diagnose(args.run, args.output, args.verified_delivery))
