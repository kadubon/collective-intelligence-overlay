"""Assess retained matched resources without converting allowances or nested costs."""

import argparse
import base64
import itertools
import json
import math
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from validate_production_experiment import validate

from collective_intelligence_overlay.bindings import fingerprint


def distribution(values):
    values = sorted(values)
    return {
        "count": len(values),
        **{
            f"p{percent}": values[max(0, math.ceil(len(values) * percent / 100) - 1)]
            if values
            else None
            for percent in (50, 95, 99)
        },
        "maximum": max(values, default=None),
    }


def sampled_resources(samples, field):
    rows = [row[field] for row in samples]
    rss = [sum(process["rss_bytes"] for process in row.values()) for row in rows]
    # Process lifetime identity is PID plus start_ticks: reused PIDs are distinct.
    identities = {(pid, process["start_ticks"]) for row in rows for pid, process in row.items()}
    return {
        "samples": len(rows),
        "observed_process_lifetimes": len(identities),
        "rss_peak_bytes": max(rss, default=None),
        "rss_first_bytes": rss[0] if rss else None,
        "rss_last_bytes": rss[-1] if rss else None,
        "cpu_sum": None,
        "cpu_reason": "live/reaped counters overlap; retained originals are not summed",
    }


def assess(directory):
    original = validate(directory)
    protocol = json.loads((directory / "protocol.json").read_text(encoding="utf-8"))
    summary = json.loads((directory / "results.json").read_text(encoding="utf-8"))
    arms = []
    seconds_allowance = protocol.get("owner_time_allowance", {})
    time_allowance_verified = (
        seconds_allowance.get("unit") == "wall_seconds"
        and seconds_allowance.get("quantity") == 500
        and seconds_allowance.get("work_credits_are_separate") is True
    )
    for assignment in summary["arms"]:
        home = directory / assignment["directory"]
        report = json.loads((home / "result.json").read_text(encoding="utf-8"))
        lifetime = report.get("owner_time_allowance", {})
        owners = lifetime.get("owners", {})
        time_allowance_verified = time_allowance_verified and (
            lifetime.get("unit") == "wall_seconds"
            and lifetime.get("quantity") == 500
            and set(owners) == {"producer", "verifier", "receiver"}
            and all(
                row.get("physical_stop_confirmed") is True
                and 0 <= row["started_seconds"] <= row["stopped_seconds"] <= 500
                for row in owners.values()
            )
        )
        samples = json.loads((home / "process-samples.json").read_text(encoding="utf-8"))
        signed_costs, unknown, obligations = defaultdict(list), Counter(), Counter()
        owner_resources = {}
        for owner in ("producer", "verifier", "receiver"):
            exported = json.loads((home / f"{owner}-observations.json").read_text(encoding="utf-8"))
            owned = {}
            for envelope in exported["signed_records"]:
                record = json.loads(base64.b64decode(envelope["payload"], validate=True))
                if record["issuer"] != owner:
                    continue  # Received replicas are not additional consumption.
                key = (
                    record["kind"],
                    record.get("id") or fingerprint(record["subject"]),
                )
                prior = owned.setdefault(key, record)
                if prior != record:
                    raise ValueError("different original content under one owned record ID")
            for record in owned.values():
                for obligation in record.get("obligations", []):
                    obligations[str(obligation)] += 1
                if record["kind"] != "event":
                    continue
                for cost in record.get("costs", []):
                    key = (owner, cost["category"], cost["unit"], cost["status"])
                    quantity = cost.get("quantity")
                    if quantity is None:
                        unknown[key] += 1
                    else:
                        signed_costs[key].append(Decimal(quantity))
            operational = report["operational_end"][owner]
            process = operational["process"]
            # One final root snapshot covers its own CPU and already reaped
            # children. Living children and shared DB CPU stay separately missing.
            cpu = {
                key: process[key]
                for key in (
                    "self_user_seconds",
                    "self_system_seconds",
                    "reaped_children_user_seconds",
                    "reaped_children_system_seconds",
                )
            }
            owner_samples = [{"processes": sample["owners"][owner]} for sample in samples]
            owner_resources[owner] = {
                **sampled_resources(owner_samples, "processes"),
                "final_root_cpu_seconds": cpu,
                "database_end_bytes": operational["database"]["database_bytes"],
                "artifact_end_bytes": operational["artifacts"]["bytes"],
                "remaining_allowance": exported["remaining"],
                "reservation_states": dict(Counter(r["state"] for r in exported["reservations"])),
                "unresolved_effects": operational["database"]["unresolved_effects"],
                "allowance_is_consumption": False,
            }
        resources = []
        for key in sorted(signed_costs.keys() | unknown.keys()):
            values = signed_costs[key]
            resources.append(
                {
                    "owner": key[0],
                    "category": key[1],
                    "unit": key[2],
                    "status": key[3],
                    "quantities": [str(value) for value in values],
                    "unavailable_observations": unknown[key],
                    "sum": None,
                    "sum_reason": "preserve typed observations; no inclusive parent/child addition",
                }
            )
        arms.append(
            {
                "seed": report["seed"],
                "mode": report["mode"],
                "condition": report["condition"],
                "denominator": report["denominator"],
                "independent_pass": report["passed_business_tasks"],
                "elapsed_including_export_seconds": report["elapsed_including_export_seconds"],
                "time_to_first_checked_task_seconds": report["time_to_first_checked_task_seconds"],
                "owners": owner_resources,
                "owner_time_allowance": lifetime,
                "other_processes": {
                    field: sampled_resources(samples, field)
                    for field in ("proxy", "mcp", "postgresql_shared_cluster")
                },
                "sample_spacing_seconds": distribution(
                    [b["seconds"] - a["seconds"] for a, b in itertools.pairwise(samples)]
                ),
                "client_wall_seconds": distribution([r["wall_seconds"] for r in report["calls"]]),
                "monitoring_seconds": {
                    owner: {
                        reason: distribution(value["durations_seconds"])
                        for reason, value in series.items()
                    }
                    for owner, series in report["monitoring_durations"].items()
                },
                "signed_costs": resources,
                "retained_obligations": dict(obligations),
                "missing_resources": sorted(
                    set(report["missing_resources"])
                    | {
                        "complete_wire_bytes",
                        "exact_per_owner_shared_PostgreSQL_CPU",
                        "between_sample_short_lived_child_RSS_peaks",
                        "live_child_CPU_after_final_root_snapshot",
                    }
                ),
            }
        )
    paired = summary["paired_fraction_differences"]
    means = sorted(
        sum(sample) / len(paired) for sample in itertools.product(paired, repeat=len(paired))
    )
    elapsed = all(arm["elapsed_including_export_seconds"] <= 900 for arm in arms)
    return {
        "assessment": "production-matched-resource-assessment.v1",
        "original_validation": original,
        "protocol_sha256": fingerprint(protocol),
        "artifacts": protocol["artifacts"],
        "arms": arms,
        "paired_differences": paired,
        "exact_descriptive_bootstrap": distribution(means),
        "descriptive_paired_bootstrap_95_interval": [
            means[max(0, math.ceil(len(means) * fraction) - 1)] for fraction in (0.025, 0.975)
        ],
        "all_ten_inclusive_elapsed_within_900_seconds": elapsed,
        "all_ten_observed_inclusive_elapsed_within_500_seconds": all(
            arm["elapsed_including_export_seconds"] <= 500 for arm in arms
        ),
        "profile_allowance_unit_verified": time_allowance_verified,
        "allowance_deviation": None
        if time_allowance_verified
        else (
            "profile declares 500 seconds per owner; executed ledger reserves 500 work credits. "
            "Observed wall time under 500 seconds is not proof of a seconds-unit allowance."
        ),
        "general_adaptive_advantage_established": False,
        "passed": elapsed and time_allowance_verified and not protocol["development_only"],
        "release_approval": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(assess(args.directory.resolve()), indent=2))
