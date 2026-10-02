"""Recompute finite world-level endpoints only after original offline verification."""

import argparse
import csv
import hashlib
from pathlib import Path

import numpy as np
from accumulation_statistics import (
    bounded_margin_p,
    evidence_for_margin,
    holm,
    paired_worlds,
    restricted_formation_time,
)
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
    formation = []
    for (world, name), _arm in sorted(arms.items()):
        original = read(directory / (world + "-" + name) / "arm-result.json")
        training = [o for o in original["offers"] if o["phase"] == "training"]
        investment = sum(
            o["budget_after"]["charged_tokens"] - o["budget_before"]["charged_tokens"]
            for o in training
        )
        for o in original["offers"]:
            if o["phase"] == "formation":
                marginal = (
                    o["budget_after"]["charged_tokens"] - o["budget_before"]["charged_tokens"]
                )
                formation.append(
                    {
                        "world": world,
                        "arm": name,
                        "view": o["view"],
                        "succeeded": o["succeeded"],
                        "actual_observed_wall_seconds": o["inclusive_wall_seconds"],
                        "restricted_time_endpoint": restricted_formation_time(
                            o["succeeded"],
                            o["inclusive_wall_seconds"],
                            protocol["formation_horizon_seconds"],
                        ),
                        "initial_training_tokens_charged": investment,
                        "marginal_tokens_charged": marginal,
                        "investment_inclusive_tokens_charged": investment + marginal,
                        "endpoint_censor_charge_is_not_measured_consumption": True,
                    }
                )
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
    controls = verified["positive_controls"]
    control_fraction = (
        sum(a["passed"] for a in controls) / sum(a["offered"] for a in controls)
        if controls
        else None
    )
    real = [m for a in verified["arms"] for m in a["model"].values()]
    complete = sum(m["complete"] and m["measured"] for m in real) / len(real) if real else 0
    band = protocol.get("sensitivity_gate", {}).get("E_M_quality_band", [0.3, 0.8])
    candidates = []
    for level in ("low", "middle", "high"):
        scores = [
            s["mean_Q"] for s in strata if s["difficulty"] == level and s["arm"] in {"E", "M"}
        ]
        if len(scores) == 2 and all(band[0] <= q <= band[1] for q in scores):
            candidates.append(level)
    return {
        "verified_originals": True,
        "classification": protocol["classification"],
        "protocol_sha256": hashlib.sha256((directory / "protocol.json").read_bytes()).hexdigest(),
        "independent_worlds": len(worlds),
        "arm_world_rows": rows,
        "strata": strata,
        "contrasts": contrasts,
        "formation": formation,
        "sensitivity": {
            "positive_control_fraction": control_fraction,
            "completed_measured_response_fraction": complete,
            "E_M_candidate_strata_without_C_minus_M": candidates,
            "passed": bool(candidates)
            and control_fraction is not None
            and control_fraction >= 0.9
            and complete >= 0.9,
        },
        "H_SHARE": "unjudged_I_not_performed",
        "H_ADAPT": "unjudged_A_not_performed",
        "twenty_percent_cost_benefit": "unjudged_without_quality_precision_and_complete_compute",
        "extrapolation": "finite synthetic law on one host/model; no universal intelligence claim",
        "all_worlds_and_failures_retained": True,
        "bootstrap_unit": "world",
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
