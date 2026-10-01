"""Recompute quantitative soak observations; no inferred safety or release approval."""

import argparse
import base64
import hashlib
import json
import math
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

from collective_intelligence_overlay.bindings import fingerprint
from collective_intelligence_overlay.models import Evidence

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
    databases, signed_count, evidence, events, original_cas, owner_exports = (
        set(),
        0,
        {},
        {},
        {},
        {},
    )
    for owner in ("producer", "verifier", "receiver"):
        observed = json.loads((directory / f"{owner}-observations.json").read_text())
        checked = validate_owner_observations(
            observed, owner, Decimal(protocol["work_allowance_per_owner"])
        )
        databases.add(checked["database_identity"])
        signed_count += checked["verified_signed_records"]
        owner_exports[owner] = observed
        evidence.update(checked["evidence"])
        events.update(checked["events"])
        artifact_file = directory / f"{owner}-artifacts.json"
        if artifact_file.exists():
            artifact_report = json.loads(artifact_file.read_text())
            for key, encoded in artifact_report["original_bytes_base64"].items():
                raw = base64.b64decode(encoded, validate=True)
                if hashlib.sha256(raw).hexdigest() != key:
                    raise ValueError("original CAS artifact digest mismatch")
                previous = original_cas.setdefault(key, raw)
                if previous != raw:
                    raise ValueError("different bytes under one artifact digest")
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
    checked_artifacts = 0
    for call in calls:
        returned = call.get("result", {})
        if call["operation"] == "invoke" and returned.get("state") == "completed":
            event = events.get((call["owner"], returned.get("receipt_id")))
            receipt = event.execution if event is not None else None
            if (
                receipt is None
                or receipt.invocation_id != call["request"]["invocation_id"]
                or receipt.caller != call["owner"]
                or receipt.binding_digest != call["request"]["binding_digest"]
                or receipt.arguments_digest != fingerprint(call["request"]["arguments"])
                or receipt.result_digest != fingerprint(returned["result"])
            ):
                raise ValueError("completed operation differs from its original signed receipt")
        if call["operation"] != "app.verify" or "evidence" not in returned:
            continue
        claim = Evidence.model_validate(returned["evidence"])
        if claim != evidence.get((claim.issuer, claim.id)) or claim.issuer != "verifier":
            raise ValueError("business check has no matching original independent Evidence")
        if not original_cas:
            continue  # Early development export; reported as pending below.
        proof = json.loads(original_cas[claim.artifact_digest])
        if (
            proof["observed"] != returned["observed"]
            or proof["request"]["arguments"] != call["request"]["arguments"]
            or proof["request"]["provider"] != call["request"]["provider"]
            or proof["request"]["name"] != call["request"]["name"]
            or proof["binding"] != claim.binding_digest
        ):
            raise ValueError("independent proof differs from the original requested operation")
        if claim.verdict == "PASS" and proof["observed"].get("state") != "completed":
            raise ValueError("UNKNOWN/missing observation was promoted to independent PASS")
        if claim.verdict == "PASS" and call["request"]["name"] == "triage":
            text_input = call["request"]["arguments"]["text"]
            expected = {
                "long": len(text_input.split()) > protocol.get("operator_threshold", 6),
                "threshold": protocol.get("operator_threshold", 6),
            }
            if proof["observed"].get("result") != expected:
                raise ValueError("independent PASS differs from the fixed operator triage contract")
        checked_artifacts += 1
    observations["original_check_artifacts_verified"] = checked_artifacts

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

    def classified(row):
        if row["status"] != "returned":
            return False
        value = row.get("result", {})
        if row["kind"] == "formation_check":
            return all("error_type" not in value.get(key, {}) for key in ("run", "check"))
        if row["kind"] == "discovery" and "owner_syncs" in value:
            return all("error_type" not in item for item in value["owner_syncs"])
        return "error_type" not in value

    normal_offers = [row for row in measured if normal(row)]
    lower(
        "normal_window_classified_response_fraction_min",
        sum(classified(row) for row in normal_offers) / len(normal_offers)
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
        classified(row) and 0 <= row["completed_seconds"] - start <= protocol["measurement_seconds"]
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
    if "rotated_owner_log_bytes" in result:
        upper(
            "rotated_log_total_bytes_max",
            max(result["rotated_owner_log_bytes"].values()),
            limits["rotated_log_total_bytes_max"],
        )
        gates["secret_or_raw_input_log_disclosures"] = not result["secret_log_disclosures"]
    current_targets = [
        row["observation"]
        for row in operations
        if row["owner"] == "receiver-current-targets"
        and "verification_backlog" in row["observation"]
    ]
    if current_targets:
        upper(
            "unverified_candidates_count_max",
            max(row["verification_backlog"] for row in current_targets),
            limits["unverified_candidates_count_max"],
        )
        observations["backlog_scope"] = protocol["verification_backlog_basis"]
        observations["current_candidate_ages_seconds"] = [
            [item["candidate_observed_age_seconds"] for item in row["targets"]]
            for row in current_targets
        ]
    gaps = [
        right["seconds"] - left["seconds"]
        for left, right in zip(measured_samples, measured_samples[1:], strict=False)
    ]
    observations["os_sample_interval_seconds"] = {
        "count": len(gaps),
        "maximum": max(gaps, default=None),
        "nominal": 5,
        "late_by_seconds": [max(0, gap - 5) for gap in gaps],
    }
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
        "unexplained_backlog_growth",
        "all_original_effect_and_signature_safety_invariants",
        "uninterrupted_five_second_sample_coverage",
    ]
    if "rotated_owner_log_bytes" not in result:
        pending.append("rotated_log_total_bytes")
    if not current_targets:
        pending.append("unverified_candidate_count_and_age")
    if not original_cas:
        pending.append("complete_original_check_artifact_validation")
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
