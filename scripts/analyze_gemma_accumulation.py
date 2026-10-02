"""Recompute finite world-level endpoints only after original offline verification."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from accumulation_statistics import (
    bounded_margin_p,
    evidence_for_margin,
    holm,
    paired_worlds,
)
from check_gemma_state import matched_retrieval_dose
from verify_gemma_accumulation import read, verify_run

from collective_intelligence_overlay.adapters.inference_observer import write_new


def quality(outcomes, *, phase="anchor", checkpoint=6, view="full", difficulty=None):
    rows = [
        r
        for r in outcomes
        if r["phase"] == phase
        and r["view"] == view
        and (phase != "anchor" or r["checkpoint"] == checkpoint)
        and (difficulty is None or r["difficulty"] == difficulty)
    ]
    if not rows:
        raise ValueError("declared quality endpoint has no offered denominator")
    return sum(r["succeeded"] for r in rows) / len(rows)


def family_sensitivity(family_strata, pooled, band):
    """A pooled middle score cannot hide a ceiling family and a floor family."""
    candidates, pooled_candidates = [], []
    for level in ("low", "middle", "high"):
        family = [
            r["mean_Q"]
            for r in family_strata
            if r["arm"] in {"E", "M"} and r["difficulty"] == level
        ]
        combined = [
            r["mean_Q"] for r in pooled if r["arm"] in {"E", "M"} and r["difficulty"] == level
        ]
        if len(family) == 4 and all(band[0] <= q <= band[1] for q in family):
            candidates.append(level)
        if len(combined) == 2 and all(band[0] <= q <= band[1] for q in combined):
            pooled_candidates.append(level)
    return candidates, pooled_candidates


FIELDS = (
    "model_calls",
    "charged_tokens",
    "measured_tokens",
    "missing_usage_requests",
    "application_actions",
    "execution_invocations_reserved",
    "checker_cases_reserved",
    "retrieval_calls",
    "proven_not_sent_requests",
)


def resource_delta(before, after):
    result = {}
    for name in FIELDS:
        a, b = before[name], after[name]
        if type(a) is not int or type(b) is not int or not 0 <= a <= b:
            raise ValueError("nonmonotone original resource counter: " + name)
        result[name] = b - a
    return result


def original_cost_groups(summary, resources):
    initial = summary["offers"][0]["budget_before"]
    groups = {"initial_setup": {k: initial[k] for k in FIELDS}}
    groups["initial_setup"]["observed_serial_wall_seconds"] = initial["inclusive_wall_seconds"]
    for offer in summary["offers"]:
        phase = offer["phase"]
        group = groups.setdefault(
            phase, {**{k: 0 for k in FIELDS}, "observed_serial_wall_seconds": 0}
        )
        for name, value in resource_delta(offer["budget_before"], offer["budget_after"]).items():
            group[name] += value
        group["observed_serial_wall_seconds"] += offer["inclusive_wall_seconds"]
    other = {name: resources[name] - sum(g[name] for g in groups.values()) for name in FIELDS}
    if any(value < 0 for value in other.values()):
        raise ValueError("resource segments exceed their original inclusive total")
    other["observed_serial_wall_seconds"] = resources["inclusive_wall_seconds"] - sum(
        g["observed_serial_wall_seconds"] for g in groups.values()
    )
    if other["observed_serial_wall_seconds"] < -0.01:
        raise ValueError("serial interval observations exceed the inclusive arm wall")
    groups["qualification_and_other_between_offer_export_overhead"] = other
    return groups


def sampled_resources(directory, read):
    maximum, baseline, peaks, missing, missing_identity = {}, {}, [], 0, 0
    samples = [
        json.loads(line) for line in (directory / "os-processes.jsonl").read_text().splitlines()
    ]
    for sample in samples:
        if sample["status"] != "measured":
            missing += 1
            continue
        processes = sample["processes"]
        if isinstance(processes, dict):
            processes = (
                [processes]
                if "pid" in processes
                else [{"pid": int(pid), **p} for pid, p in processes.items()]
            )
        rss = []
        for process in processes:
            start = process.get("started_at", process.get("start_ticks"))
            key = process["pid"], start
            cpu = process.get("cpu_seconds")
            if cpu is None and all(k in process for k in ("user_seconds", "system_seconds")):
                cpu = process["user_seconds"] + process["system_seconds"]
            if (
                isinstance(cpu, int | float)
                and not isinstance(cpu, bool)
                and math.isfinite(cpu)
                and cpu >= 0
            ):
                if start is None:
                    missing_identity += 1
                else:
                    baseline.setdefault(key, cpu)
                    maximum[key] = max(cpu, maximum.get(key, cpu))
            value = process.get("rss_bytes")
            if type(value) is int and value >= 0:
                rss.append(value)
        if rss:
            peaks.append(sum(rss))
    manifest = read(directory / "model-manifest.json")
    return {
        "sample_count": len(samples),
        "unavailable_samples": missing,
        "CPU_observations_missing_process_start_identity": missing_identity,
        "sampled_process_identities": len(maximum),
        "sampled_owned_process_CPU_lower_bound_seconds": sum(
            v - baseline[k] for k, v in maximum.items()
        )
        if maximum
        else None,
        "peak_sum_of_sampled_working_sets_bytes": max(peaks) if peaks else None,
        "process_identity": "pid/native start; first observed CPU subtracted for each process",
        "CPU_scope": "increments between first and last available samples per process",
        "first_cohort_sample_available": samples[0]["status"] == "measured" if samples else False,
        "CPU_before_first_process_sample_not_inferred": True,
        "RSS_is_process_working_set_sum_not_complete_physical_RAM": True,
        "polling_can_miss_short_lived_processes_and_peaks": True,
        "shared_WSL_PostgreSQL_CPU": None,
        "energy_joules": None,
        "GPU_energy_or_compute": None,
        "compute_complete": False,
        "hardware": manifest["hardware"],
    }


def additional_endpoints(directory, protocol, arms, read, quality):
    curves, strata, interventions, frontier, costs, formation = [], [], [], [], [], []
    placebo_doses = []
    conditions = []
    worlds = sorted({w for w, _ in arms})
    horizon_tokens = protocol.get(
        "formation_horizon_tokens",
        protocol["formation_attempts"]
        * (protocol["model_options"]["num_ctx"] + protocol["model_options"]["num_predict"]),
    )
    for (world, name), verified in sorted(arms.items()):
        folder = directory / (world + "-" + name)
        summary, resources = read(folder / "arm-result.json"), read(folder / "resources.json")
        grouped = original_cost_groups(summary, resources)
        for phase, values in grouped.items():
            costs.append(
                {
                    "world": world,
                    "arm": name,
                    "segment": phase,
                    **values,
                    "execution_counters_are_reservations": True,
                    "experimental_control_overhead": phase
                    in {"anchor", "frontier", "placebo", "challenge"},
                }
            )
        setup, training = grouped["initial_setup"], grouped["training"]
        for outcome in verified["outcomes"]:
            if outcome["phase"] in {"challenge", "transfer", "formation"}:
                conditions.append({"world": world, "arm": name, **outcome})
        if name != "E":
            anchors = [
                o for o in verified["outcomes"] if o["phase"] == "anchor" and o["checkpoint"] == 6
            ]
            for full in (o for o in anchors if o["view"] == "full"):
                foreign = next(
                    o
                    for o in anchors
                    if o["view"] == "irrelevant" and o["problem_id"] == full["problem_id"]
                )
                left, right = full["retrieved_dose"], foreign["retrieved_dose"]
                placebo_doses.append(
                    {
                        "world": world,
                        "arm": name,
                        "problem_id": full["problem_id"],
                        "family": full["family"],
                        "difficulty": full["difficulty"],
                        "full_retrieved_dose": left,
                        "irrelevant_retrieved_dose": right,
                        "retrieved_type_count_bytes_matched": matched_retrieval_dose(left, right)
                        if left is not None and right is not None
                        else None,
                        "full_direct_admitted_dose": full["direct_admitted_dose"],
                        "irrelevant_direct_admitted_dose": foreign["direct_admitted_dose"],
                        "full_model_context_doses": full["model_context_doses"],
                        "irrelevant_model_context_doses": foreign["model_context_doses"],
                        "matching_is_not_semantic_equivalence": True,
                    }
                )
        for checkpoint in (0, 3, 6):
            prior = [
                o
                for o in summary["offers"]
                if o["phase"] == "training" and o["episode"] <= checkpoint
            ]
            curves.append(
                {
                    "world": world,
                    "arm": name,
                    "checkpoint": checkpoint,
                    "declared_training_fraction": checkpoint / 6,
                    "Q": quality(verified["outcomes"], checkpoint=checkpoint),
                    "training_tokens_charged": sum(
                        resource_delta(o["budget_before"], o["budget_after"])["charged_tokens"]
                        for o in prior
                    ),
                    "offered_anchor_tasks": 6,
                }
            )
        for view in ("full", "empty", "irrelevant") if name != "E" else ("full",):
            selected = [
                o
                for o in summary["offers"]
                if o["phase"] == "anchor" and o["checkpoint"] == 6 and o["view"] == view
            ]
            tokens = sum(
                resource_delta(o["budget_before"], o["budget_after"])["charged_tokens"]
                for o in selected
            )
            interventions.append(
                {
                    "world": world,
                    "arm": name,
                    "view": view,
                    "Q": quality(verified["outcomes"], view=view),
                    "offered": len(selected),
                    "tokens_charged_per_offered_task": tokens / len(selected),
                    "trained_state_nonempty": summary["placebo_matching"]["nonempty"],
                    "pool_matched": summary["placebo_matching"]["matched"],
                    "causal_placebo_judgment_requires_actual_retrieval_dose_match": True,
                }
            )
        if protocol.get("budget_frontier"):
            for view in ("full", "empty") if name != "E" else ("full",):
                for budget in (1, 2):
                    selected = [
                        o
                        for o in summary["offers"]
                        if o["view"] == view
                        and (
                            (budget == 1 and o["phase"] == "anchor" and o["checkpoint"] == 6)
                            or (budget == 2 and o["phase"] == "frontier")
                        )
                    ]
                    if len(selected) != 6:
                        raise ValueError("missing prospective six-form frontier budget")
                    frontier.append(
                        {
                            "world": world,
                            "arm": name,
                            "view": view,
                            "allowed_model_drafts": budget,
                            "offered": len(selected),
                            "Q": sum(o["succeeded"] for o in selected) / len(selected),
                            "tokens_charged_per_offered_task": sum(
                                resource_delta(o["budget_before"], o["budget_after"])[
                                    "charged_tokens"
                                ]
                                for o in selected
                            )
                            / len(selected),
                        }
                    )
        for offer in summary["offers"]:
            if offer["phase"] != "formation":
                continue
            delta = resource_delta(offer["budget_before"], offer["budget_after"])
            if delta["charged_tokens"] > horizon_tokens:
                raise ValueError("formation charged tokens exceed the prospective endpoint horizon")
            actual = offer["inclusive_wall_seconds"]
            if not math.isfinite(actual) or actual < 0:
                raise ValueError("formation observed time is missing or invalid")
            formation.append(
                {
                    "world": world,
                    "arm": name,
                    "view": offer["view"],
                    "succeeded": offer["succeeded"],
                    "actual_observed_wall_seconds": actual,
                    "restricted_time_endpoint": min(actual, protocol["formation_horizon_seconds"])
                    if offer["succeeded"]
                    else protocol["formation_horizon_seconds"],
                    "restricted_tokens_endpoint": delta["charged_tokens"]
                    if offer["succeeded"]
                    else horizon_tokens,
                    "initial_training_tokens_charged": training["charged_tokens"],
                    "initial_setup_actions": setup["application_actions"],
                    "initial_setup_wall_seconds": setup["observed_serial_wall_seconds"],
                    "training_sharing_maintenance_actions": training["application_actions"],
                    "training_sharing_maintenance_wall_seconds": training[
                        "observed_serial_wall_seconds"
                    ],
                    "marginal_tokens_charged": delta["charged_tokens"],
                    "marginal_application_actions": delta["application_actions"],
                    "investment_inclusive_tokens_charged": setup["charged_tokens"]
                    + training["charged_tokens"]
                    + delta["charged_tokens"],
                    "investment_inclusive_restricted_tokens_endpoint": setup["charged_tokens"]
                    + training["charged_tokens"]
                    + (delta["charged_tokens"] if offer["succeeded"] else horizon_tokens),
                    "endpoint_penalty_is_not_measured_consumption": True,
                    "initial_investment_charged_in_both_full_and_empty_interventions": True,
                }
            )
    for name in sorted({a for _, a in arms}):
        for family in ("sql", "calibration"):
            for level in ("low", "middle", "high"):
                scores = []
                for world in worlds:
                    rows = [
                        o
                        for o in arms[world, name]["outcomes"]
                        if o["phase"] == "anchor"
                        and o["checkpoint"] == 6
                        and o["view"] == "full"
                        and o["family"] == family
                        and o["difficulty"] == level
                    ]
                    if len(rows) != 1:
                        raise ValueError("missing fixed family/stratum form in a world")
                    scores.append(float(rows[0]["succeeded"]))
                strata.append(
                    {
                        "arm": name,
                        "family": family,
                        "difficulty": level,
                        "world_scores": scores,
                        "mean_Q": float(np.mean(scores)),
                        "all_floor": not any(scores),
                        "all_ceiling": all(q == 1 for q in scores),
                    }
                )
    means = []
    for name, view in sorted({(r["arm"], r["view"]) for r in formation}):
        rows = [r for r in formation if (r["arm"], r["view"]) == (name, view)]
        if len(rows) != len(worlds):
            raise ValueError("formation rows cannot inflate independent world count")
        means.append(
            {
                "arm": name,
                "view": view,
                "independent_worlds": len(rows),
                "success_fraction": sum(r["succeeded"] for r in rows) / len(rows),
                **{
                    k: float(np.mean([r[k] for r in rows]))
                    for k in (
                        "actual_observed_wall_seconds",
                        "restricted_time_endpoint",
                        "restricted_tokens_endpoint",
                        "marginal_tokens_charged",
                        "investment_inclusive_tokens_charged",
                        "investment_inclusive_restricted_tokens_endpoint",
                    )
                },
                "restricted_mean_is_finite_policy_not_Kaplan_Meier": True,
            }
        )
    return {
        "protocol_id": protocol["id"],
        "learning_curves": curves,
        "family_strata": strata,
        "state_interventions": interventions,
        "placebo_retrieval_doses": placebo_doses,
        "condition_outcomes": conditions,
        "budget_frontier": frontier,
        "cost_accounting": costs,
        "formation": formation,
        "formation_means": means,
        "formation_horizon_seconds": protocol["formation_horizon_seconds"],
        "formation_horizon_tokens": horizon_tokens,
        "OS_resource_observation": sampled_resources(directory, read),
        "twenty_percent_complete_cost_benefit": (
            "unjudged_without_quality_precision_and_complete_compute"
        ),
        "conditional_break_even": (
            "not_estimated_without_matched_quality_and_positive_repeated_marginal_savings"
        ),
    }


def analyze(directory):
    verified = verify_run(directory)
    protocol = read(directory / "protocol.json")
    if protocol["classification"] == "smoke":
        raise ValueError("smoke cannot be mixed into performance analysis")
    arms = {(a["world"], a["arm"]): a for a in verified["arms"]}
    worlds = sorted({w for w, _ in arms})
    rows = []
    for (world, name), arm in sorted(arms.items()):
        resources = read(directory / (world + "-" + name) / "resources.json")
        summary = read(directory / (world + "-" + name) / "arm-result.json")
        q = quality(arm["outcomes"])
        rows.append(
            {
                "world": world,
                "arm": name,
                "independent_unit": "world",
                "Q_final_full": q,
                "model_calls": len(arm["model"]),
                "model_tokens_measured": sum(
                    v["charge"] for v in arm["model"].values() if v["measured"]
                ),
                "model_tokens_charged": resources["charged_tokens"],
                "missing_usage": sum(not v["measured"] for v in arm["model"].values()),
                "inclusive_arm_wall_seconds": resources["inclusive_wall_seconds"],
                "placebo_matched": summary["placebo_matching"]["matched"],
                "trained_state_nonempty": summary["placebo_matching"]["nonempty"],
                "original_providers_absent": all(
                    v["returncode"] is not None for v in summary["providers_absent"].values()
                ),
                "process_CPU_complete": None,
                "energy_joules": None,
            }
        )
    names = set(protocol["arms"])
    contrasts = {}

    def contrast(key, left, right):
        result = paired_worlds(
            left, right, alpha=protocol.get("interval_alpha", 0.005), seed=protocol["analysis_seed"]
        )
        result["MCID"] = protocol.get("quality_MCID", 0.05)
        result["judgment"] = evidence_for_margin(result, result["MCID"])
        result["one_sided_margin_p_bound"] = bounded_margin_p(result, result["MCID"])
        contrasts[key] = result

    if {"C", "M"} <= names:
        contrast(
            "H_CIO_primary_final_Q_C_minus_M",
            [quality(arms[w, "C"]["outcomes"]) for w in worlds],
            [quality(arms[w, "M"]["outcomes"]) for w in worlds],
        )
    for name in sorted(names & {"C", "M"}):
        contrast(
            "H_ACC_" + name + "_full_minus_empty",
            [quality(arms[w, name]["outcomes"]) for w in worlds],
            [quality(arms[w, name]["outcomes"], view="empty") for w in worlds],
        )
        contrast(
            "H_ACC_" + name + "_full_minus_irrelevant",
            [quality(arms[w, name]["outcomes"]) for w in worlds],
            [quality(arms[w, name]["outcomes"], view="irrelevant") for w in worlds],
        )
        contrast(
            "H_FORM_" + name + "_full_minus_empty_success",
            [quality(arms[w, name]["outcomes"], phase="formation") for w in worlds],
            [quality(arms[w, name]["outcomes"], phase="formation", view="empty") for w in worlds],
        )
    if {"C", "M"} <= names:
        contrast(
            "H_FORM_C_minus_M_success",
            [quality(arms[w, "C"]["outcomes"], phase="formation") for w in worlds],
            [quality(arms[w, "M"]["outcomes"], phase="formation") for w in worlds],
        )
    adjusted = holm({k: v["one_sided_margin_p_bound"] for k, v in contrasts.items()})
    for key, value in adjusted.items():
        contrasts[key]["holm_adjusted_p_bound"] = value
    if len(contrasts) > protocol.get("maximum_preregistered_quality_contrasts", 10):
        raise ValueError("performed contrasts exceed the prospective multiplicity budget")
    strata = []
    for name in sorted(names):
        for level in ("low", "middle", "high"):
            values = [quality(arms[w, name]["outcomes"], difficulty=level) for w in worlds]
            strata.append(
                {
                    "arm": name,
                    "difficulty": level,
                    "world_scores": values,
                    "mean_Q": float(np.mean(values)),
                }
            )
    extras = additional_endpoints(directory, protocol, arms, read, quality)
    controls = verified["positive_controls"]
    control_fraction = (
        sum(a["passed"] for a in controls) / sum(a["offered"] for a in controls)
        if controls
        else None
    )
    real = [m for a in verified["arms"] for m in a["model"].values()]
    complete = sum(m["complete"] and m["measured"] for m in real) / len(real) if real else 0
    band = protocol.get("sensitivity_gate", {}).get("E_M_quality_band", [0.3, 0.8])
    candidates, pooled_candidates = family_sensitivity(extras["family_strata"], strata, band)
    gate = protocol.get("sensitivity_gate", {})
    control_threshold = gate.get("positive_control_minimum", 0.9)
    complete_threshold = gate.get("completed_measured_response_minimum", 0.9)
    passed = (
        bool(candidates)
        and control_fraction is not None
        and control_fraction >= control_threshold
        and complete >= complete_threshold
    )
    for name in names & {"C", "M"}:
        states = [r for r in rows if r["arm"] == name]
        nonempty = sum(r["trained_state_nonempty"] for r in states)
        for key, value in contrasts.items():
            if key.startswith("H_ACC_" + name) or key.startswith(
                "H_FORM_" + name + "_full_minus_empty"
            ):
                value["worlds_with_nonempty_retained_state"] = nonempty
                if nonempty == 0:
                    value["judgment"] = "unjudged_empty_retained_state"
            if key == "H_ACC_" + name + "_full_minus_irrelevant" and any(
                not r["placebo_matched"] for r in states
            ):
                value["judgment"] = "unjudged_unmatched_placebo"
            if key == "H_ACC_" + name + "_full_minus_irrelevant" and nonempty:
                doses = [r for r in extras["placebo_retrieval_doses"] if r["arm"] == name]
                if any(r["retrieved_type_count_bytes_matched"] is not True for r in doses):
                    value["judgment"] = "unjudged_unmatched_or_unobserved_retrieval_dose"
    review_files = [
        "analyze_gemma_accumulation.py",
        "verify_gemma_accumulation.py",
        "accumulation_statistics.py",
        "check_gemma_state.py",
        "check_gemma_transport.py",
        "check_gemma_candidate.py",
        "accumulation_host.py",
        "accumulation_stock.py",
        "accumulation_protocol.py",
    ]
    hypotheses = {
        key: {
            "performed_contrasts": {
                name: value["judgment"]
                for name, value in contrasts.items()
                if name.startswith(key + "_")
            }
        }
        for key in ("H_ACC", "H_CIO", "H_FORM")
    }
    hypotheses["H_SHARE"] = {"judgment": "unjudged_I_not_performed"}
    hypotheses["H_ADAPT"] = {"judgment": "unjudged_A_not_performed"}
    for key in ("H_ACC", "H_CIO", "H_FORM"):
        results = list(hypotheses[key]["performed_contrasts"].values())
        hypotheses[key]["judgment"] = (
            "unjudged_contrast_not_performed"
            if not results
            else results[0]
            if len(set(results)) == 1
            else "condition_specific_judgments"
        )
    hypotheses["H_CIO"]["full_additional_value_requires_complete_cost_and_safety_constraints"] = (
        True
    )
    hypotheses["H_FORM"]["scope"] = (
        "finite-budget new composition, independently checked alternate form; "
        "new composition at a new receiver is not measured"
    )
    return {
        "verified_originals": True,
        "classification": protocol["classification"],
        "protocol_sha256": hashlib.sha256((directory / "protocol.json").read_bytes()).hexdigest(),
        "analysis_review_source_sha256": {
            name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in review_files
        },
        "independent_worlds": len(worlds),
        "arm_world_rows": rows,
        "strata": strata,
        "contrasts": contrasts,
        "hypothesis_judgments": hypotheses,
        **extras,
        "sensitivity": {
            "positive_control_fraction": control_fraction,
            "completed_measured_response_fraction": complete,
            "E_M_candidate_strata_without_C_minus_M": candidates,
            "legacy_pooled_candidate_strata": pooled_candidates,
            "legacy_preregistered_pooled_gate_passed": bool(pooled_candidates)
            and control_fraction is not None
            and control_fraction >= control_threshold
            and complete >= complete_threshold,
            "family_review_was_pilot_preregistered": gate.get("unit") == "family_by_difficulty",
            "passed": passed,
            "assay_insensitive": not passed,
        },
        "H_SHARE": "unjudged_I_not_performed",
        "H_ADAPT": "unjudged_A_not_performed",
        "twenty_percent_cost_benefit": "unjudged_without_quality_precision_and_complete_compute",
        "extrapolation": "finite synthetic law on one host/model; no universal intelligence claim",
        "all_worlds_and_failures_retained": True,
        "bootstrap_unit": "world",
        "cohort_inclusive_wall_seconds": read(directory / "cohort.json")["inclusive_wall_seconds"],
        "cohort_wall_including_physical_cleanup_seconds": read(directory / "cleanup.json")[
            "inclusive_cohort_wall_including_cleanup_seconds"
        ]
        if (directory / "cleanup.json").exists()
        else None,
        "owned_server_metadata_accounting": verified["owned_server_metadata_accounting"],
        "model_identity_observations_dispatched": sum(
            m["model_identity_observation_dispatched"] for m in real
        )
        if protocol.get("observation_binding_schema") == "2"
        else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.run)
    write_new(args.output, result)
    csv_path = args.output.with_suffix(".csv")
    with csv_path.open("x", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(result["arm_world_rows"][0]))
        writer.writeheader()
        writer.writerows(result["arm_world_rows"])


if __name__ == "__main__":
    main()
