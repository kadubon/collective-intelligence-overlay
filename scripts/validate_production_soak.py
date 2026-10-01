"""Recompute quantitative soak observations; no inferred safety or release approval."""

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

from collective_intelligence_overlay.bindings import fingerprint

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples"))
from evaluate_documents import validate_owner_observations  # noqa: E402


def rank(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def validate(directory):
    protocol = json.loads((directory / "protocol.json").read_text())
    result = json.loads((directory / "result.json").read_text())
    profile = json.loads((ROOT / "docs/profiles/production-040.json").read_text())
    if protocol["profile_sha256"] != fingerprint(profile):
        raise ValueError("profile differs from its original declared digest")
    for name, expected in protocol["sources"].items():
        if hashlib.sha256((directory / "sources" / name).read_bytes()).hexdigest() != expected:
            raise ValueError("saved source differs from its original digest")
    calls = [json.loads(line) for line in (directory / "calls.jsonl").read_text().splitlines()]
    offers = [json.loads(line) for line in (directory / "offers.jsonl").read_text().splitlines()]
    if len({call["call_index"] for call in calls}) != len(calls):
        raise ValueError("duplicate observation call index")
    if Counter(map(fingerprint, offers)) != Counter(map(fingerprint, result["offers"])):
        raise ValueError("raw offered outcomes differ from the retained result")
    inputs = json.loads((directory / "inputs.json").read_text())
    regular = [row for row in offers if row["phase"] == "measurement" and not row["burst"]]
    if [
        (row["index"], row["kind"], row["text"])
        for row in sorted(regular, key=lambda x: x["index"])
    ] != [(row["index"], row["kind"], row["text"]) for row in inputs]:
        raise ValueError("regular offered inputs were lost, added or changed")
    if len(regular) != protocol["regular_offers"]:
        raise ValueError("regular offered denominator changed")
    databases, signed_count = set(), 0
    for owner in ("producer", "verifier", "receiver"):
        observed = json.loads((directory / f"{owner}-observations.json").read_text())
        checked = validate_owner_observations(
            observed, owner, Decimal(protocol["work_allowance_per_owner"])
        )
        databases.add(checked["database_identity"])
        signed_count += checked["verified_signed_records"]
    if len(databases) != 3:
        raise ValueError("three distinct owner databases are required")
    samples = [json.loads(line) for line in (directory / "samples.jsonl").read_text().splitlines()]
    operations = [
        json.loads(line)
        for line in (directory / "operational-samples.jsonl").read_text().splitlines()
    ]
    start = result["measurement_started_seconds"]
    measured = [row for row in offers if row["phase"] == "measurement"]
    gates, observations = {}, {}
    limits = profile["release_soak"]["gates"]

    def upper(name, value, maximum):
        observations[name] = value
        gates[name] = value is not None and value <= maximum

    def lower(name, value, minimum):
        observations[name] = value
        gates[name] = value is not None and value >= minimum

    def normal(row):
        seconds = row["offered_seconds"] - start
        return not any(
            fault["at_seconds"] <= seconds < fault["normal_exclusion_end_seconds"]
            for fault in protocol["faults"]
        )

    censored = [row for row in measured if row["status"] in {"censored", "failed"}]
    observations["censored_or_failed_count"] = len(censored)
    observations["latency_basis"] = "all offered outcomes; incomplete waits are lower bounds"
    groups = {
        "readonly": [
            row["wall_seconds"]
            for row in measured
            if row["kind"] in {"state", "discovery", "qualification", "original_query"}
        ],
        "invoke_all_outcomes": [row["wall_seconds"] for row in measured if row["kind"] == "invoke"],
        "finite_loop_all_outcomes": [
            row["wall_seconds"] for row in measured if row["kind"] == "formation_check"
        ],
    }
    for name, values in groups.items():
        observations[name] = {
            f"p{percent}": rank(values, percent / 100) for percent in (50, 95, 99)
        }
        observations[name]["denominator"] = len(values)
    for name, group, percent in (
        ("readonly_p95_seconds_max", "readonly", 95),
        ("readonly_p99_seconds_max", "readonly", 99),
        ("invoke_all_outcomes_p99_seconds_max", "invoke_all_outcomes", 99),
        ("finite_loop_all_outcomes_p95_seconds_max", "finite_loop_all_outcomes", 95),
        ("finite_loop_all_outcomes_p99_seconds_max", "finite_loop_all_outcomes", 99),
    ):
        upper(name, observations[group][f"p{percent}"], limits[name])
    upper(
        "operation_absolute_seconds_max",
        max((row["wall_seconds"] for row in measured), default=None),
        limits["operation_absolute_seconds_max"],
    )
    normal_offers = [row for row in measured if normal(row)]
    lower(
        "normal_window_classified_response_fraction_min",
        sum(row["status"] == "returned" for row in normal_offers) / len(normal_offers)
        if normal_offers
        else None,
        limits["normal_window_classified_response_fraction_min"],
    )
    # Completion throughput excludes the UNION of fixed fault windows; overlapping
    # development windows must not be counted twice.
    windows = sorted(
        (fault["at_seconds"], fault["normal_exclusion_end_seconds"]) for fault in protocol["faults"]
    )
    union = []
    for begin, end in windows:
        if union and begin <= union[-1][1]:
            union[-1][1] = max(end, union[-1][1])
        else:
            union.append([begin, end])
    normal_seconds = protocol["measurement_seconds"] - sum(end - begin for begin, end in union)
    completed_normal = sum(
        row["status"] == "returned"
        and 0 <= row["completed_seconds"] - start <= protocol["measurement_seconds"]
        for row in normal_offers
    )
    lower(
        "normal_window_completion_throughput_requests_per_second_min",
        completed_normal / normal_seconds if normal_seconds > 0 else None,
        limits["normal_window_completion_throughput_requests_per_second_min"],
    )
    measured_samples = [row for row in samples if row["seconds"] >= start]
    owner_rss = {}
    for owner in ("producer", "verifier", "receiver"):
        values = [
            sum(process["rss_bytes"] for process in row.get("owners", {}).get(owner, {}).values())
            for row in measured_samples
            if row.get("owners", {}).get(owner)
        ]
        owner_rss[owner] = {
            "start": values[0] if values else None,
            "peak": max(values) if values else None,
            "end": values[-1] if values else None,
        }
    observations["owner_rss"] = owner_rss
    peaks = [row["peak"] for row in owner_rss.values() if row["peak"] is not None]
    growth = [row["end"] - row["start"] for row in owner_rss.values() if row["end"] is not None]
    upper("owner_rss_peak_bytes_max", max(peaks, default=None), limits["owner_rss_peak_bytes_max"])
    upper(
        "owner_rss_growth_after_warmup_bytes_max",
        max(growth, default=None),
        limits["owner_rss_growth_after_warmup_bytes_max"],
    )
    db_growth, artifacts, unresolved = [], [], []
    for owner in ("producer", "verifier", "receiver"):
        values = [
            row["observation"]
            for row in operations
            if row["owner"] == owner and "database" in row["observation"]
        ]
        if values:
            db_growth.append(
                values[-1]["database"]["database_bytes"] - values[0]["database"]["database_bytes"]
            )
            artifacts.extend(value["artifacts"]["bytes"] for value in values)
            unresolved.extend(value["database"]["unresolved_effects"] for value in values)
    upper(
        "database_disk_growth_bytes_max",
        max(db_growth, default=None),
        limits["database_disk_growth_bytes_max"],
    )
    upper(
        "artifact_disk_bytes_max", max(artifacts, default=None), limits["artifact_disk_bytes_max"]
    )
    upper(
        "unresolved_effects_count_max",
        max(unresolved, default=None),
        limits["unresolved_effects_count_max"],
    )
    faults = result["faults"]
    upper(
        "resolved_fault_recovery_seconds_max",
        max((row.get("elapsed_seconds", 10**9) for row in faults), default=None),
        limits["resolved_fault_recovery_seconds_max"],
    )
    gates["all_predeclared_faults_executed"] = len(faults) == 11 and all(
        row["status"] == "executed" for row in faults
    )
    gates["full_duration_and_warmup"] = (
        not protocol["development_only"]
        and protocol["measurement_seconds"] >= 3600
        and protocol["warmup_seconds"] >= 300
    )
    gates["minimum_offers"] = len(regular) >= 900
    # Do not imply these facts from a clean driver exit or aggregate row counts.
    pending = [
        "rotated_log_total_bytes",
        "unverified_candidate_count_and_age",
        "unexplained_backlog_growth",
        "all_original_effect_and_signature_safety_invariants",
        "complete_original_check_artifact_and_execution_receipt_validation",
        "uninterrupted_five_second_sample_coverage",
    ]
    return {
        "validator": "production-soak-observation.v1",
        "profile_id": protocol["profile_id"],
        "profile_sha256": protocol["profile_sha256"],
        "artifacts": protocol["artifacts"],
        "development_only": protocol["development_only"],
        "gates": gates,
        "observations": observations,
        "pending_validation": pending,
        "original_signed_records": signed_count,
        "allowance_conserved": True,
        "passed": False,
        "release_approval": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.directory.resolve()), indent=2))
