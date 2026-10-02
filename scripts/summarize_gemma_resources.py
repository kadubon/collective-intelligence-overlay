"""Descriptive resource groups from retained raw data; no inference or primary test."""

import argparse
import hashlib
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from analyze_gemma_tabular import read, signed_records
from ollama_observer import write_new


def summarize(directory):
    groups, counts, originals = defaultdict(Counter), Counter(), {}
    for episode in sorted(directory.glob("block-*")):
        arm = episode.name.rsplit("-", 1)[1]
        for path in sorted((episode / "model").glob("attempt-*/observation.json")):
            value = read(path)
            key = arm + ":" + value["identity"]["goal"]
            assert value["token_status"] == "measured" and value["stream_complete"]
            native = value["usage_native"]
            counts[key] += 1
            for name in ("prompt_eval_count", "eval_count", "prompt_eval_cached_count"):
                groups[key][name] += native.get(name, 0)
            for name, seconds in value["durations_seconds"].items():
                groups[key]["model_" + name + "_seconds"] += Decimal(str(seconds))
            groups[key]["client_wall_seconds"] += Decimal(str(value["client_elapsed_seconds"]))
            originals[path.relative_to(directory).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
        events, _, _, _ = signed_records(episode)
        for event in events.values():
            if event.formation is not None:
                key = arm + ":" + event.formation.scope.task
                groups[key]["signed_candidate_formation_receipts"] += 1
                for cost in event.costs:
                    name = "candidate_formation:" + ":".join(
                        (cost.category, cost.unit, cost.status)
                    )
                    if cost.quantity is None:
                        groups[key][name + ":observations"] += 1
                    else:
                        groups[key][name] += cost.quantity
        for owner in ("producer", "verifier", "receiver"):
            path = episode / (owner + "-observations.json")
            originals[path.relative_to(directory).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return {
        "classification": "posthoc_descriptive_resources_only",
        "inference_performed": False,
        "primary_analysis_changed": False,
        "groups": {
            key: {
                "actual_model_requests": counts[key],
                **{
                    name: str(value) if isinstance(value, Decimal) else value
                    for name, value in row.items()
                },
            }
            for key, row in sorted(groups.items())
        },
        "original_input_sha256": originals,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scope": (
            "aggregate is C3. Model and candidate-formation durations are separate nested "
            "observations, not additive total elapsed. Candidate formation is not itself "
            "independent PASS or functional novelty. Missing monetary observations remain "
            "unavailable. Cached prompt counters describe the shared server, not a reset cache."
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_new(args.output, summarize(args.run))
    print("descriptive raw resource groups retained; no inference performed")
