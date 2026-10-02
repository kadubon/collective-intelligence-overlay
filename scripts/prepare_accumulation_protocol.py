"""Write finite calibration, precision planning or independent confirmation declarations."""

import argparse
import hashlib
import importlib.metadata
import json
import platform
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from accumulation_application import DIGEST, MODEL, wire_schema
from accumulation_statistics import simulation
from run_gemma_accumulation import ROOT, sources

from collective_intelligence_overlay.adapters.inference_observer import write_new


def calibration(identifier):
    seeds = [307191, 872131]
    return {
        "id": identifier,
        "classification": "calibration",
        "schedule_schema": "1",
        "registered_at": datetime.now(UTC).isoformat(),
        "world_seeds": seeds,
        "arms": ["E", "M"],
        "arm_orders": {str(seeds[0]): ["E", "M"], str(seeds[1]): ["M", "E"]},
        "order_seed": 813971,
        "analysis_seed": 729101,
        "model": MODEL,
        "model_digest": DIGEST,
        "prompt_revision": "2",
        "new_receiver": True,
        "positive_control_seeds": [3439169],
        "training_attempts": 1,
        "placebo_attempts": 2,
        "formation_attempts": 2,
        "model_options": {
            "num_ctx": 8192,
            "num_predict": 2048,
            "temperature": 0.2,
            "top_p": 0.95,
            "top_k": 64,
            "draft_num_predict": 0,
        },
        "request_seconds": 240,
        "caps": {
            "model_calls": 64,
            "model_tokens": 655360,
            "application_actions": 4096,
            "execution_invocations": 4096,
            "checker_cases": 1024,
            "retrieval_calls": 80,
            "owner_CAS_bytes": 16777216,
            "stock_bytes": 131072,
            "retrieval_bytes": 10000,
            "prompt_bytes": 20000,
            "concurrent_model_requests": 1,
            "wall_seconds": 10000,
        },
        "cohort_wall_seconds": 43200,
        "formation_horizon_seconds": 900,
        "sensitivity_gate": {
            "E_M_quality_band": [0.3, 0.8],
            "positive_control_minimum": 0.9,
            "completed_measured_response_minimum": 0.9,
            "maximum_calibration_cohorts": 2,
            "selection": "E/M sensitivity, complete outputs and measured costs; never C-M sign",
            "no_passing_band": "retain assay_insensitive; confirmation needs a new declaration",
        },
        "primary_endpoint": "final_checkpoint_full_stock_quality_C_minus_M",
        "sources": sources(),
    }


def precision_planning(identifier):
    results = [simulation(shift=effect) for effect in (0.05, 0.10)]
    rows = [r for result in results for r in result["scenarios"]]
    return {
        "id": identifier,
        "classification": "prospective_precision_planning_not_model_results",
        "registered_at": datetime.now(UTC).isoformat(),
        "source_sha256": hashlib.sha256(
            Path(__file__).with_name("accumulation_statistics.py").read_bytes()
        ).hexdigest(),
        "python": platform.python_version(),
        "numpy": importlib.metadata.version("numpy"),
        "scipy": importlib.metadata.version("scipy"),
        "simulation_seed": results[0]["simulation_seed"],
        "repetitions_per_scenario": results[0]["repetitions"],
        "scenarios": rows,
        "scenario_count": len(rows),
        "selected_independent_worlds": 3,
        "quality_MCID": 0.05,
        "per_contrast_interval_alpha": 0.005,
        "distribution_free_worlds_for_95_halfwidth005": results[0][
            "distribution_free_worlds_for_95_halfwidth005"
        ],
        "distribution_free_worlds_for_simultaneous_halfwidth005": results[0][
            "distribution_free_worlds_for_simultaneous_halfwidth005"
        ],
        "pilot_zero_SD_is_not_future_zero_variance": True,
        "limited_power": True,
        "parametric_power_is_not_power_of_distribution_free_analysis": True,
        "independent_unit": "world",
    }


def original_file(path):
    path = path.resolve()
    relative = path.relative_to(ROOT).as_posix()
    return {"path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def confirmation(
    identifier, *, candidate, gate, release_manifest, reports, runtime, precision, pilot_analysis
):
    base = calibration(identifier)
    # New worlds are fixed without inspecting generated outcomes or selecting on C-M.
    seeds = [427319, 619843, 953117]
    pair = json.loads((candidate / "artifacts.json").read_bytes())
    wheel = next((candidate / "dist").glob("*.whl"))
    archive = next((candidate / "dist").glob("*.tar.gz"))
    if pair != {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (wheel, archive)}:
        raise ValueError("original candidate pair differs from retained gate artifacts")
    with zipfile.ZipFile(wheel) as contents:
        package = {
            name: hashlib.sha256(contents.read(name)).hexdigest()
            for name in contents.namelist()
            if name.startswith("collective_intelligence_overlay/") and not name.endswith("/")
        }
    planning = json.loads(precision.read_bytes())
    pilot = json.loads(pilot_analysis.read_bytes())
    if not (
        planning["limited_power"]
        and planning["selected_independent_worlds"] == 3
        and pilot["verified_originals"]
        and pilot["classification"] == "calibration"
    ):
        raise ValueError("actual pilot review and prospective N=3 precision plan required")
    base.update(
        {
            "classification": "confirmation",
            "schedule_schema": "2",
            "retrieval_revision": "2",
            "observation_binding_schema": "2",
            "world_seeds": seeds,
            "arms": ["E", "M", "C"],
            "arm_orders": {
                str(s): list(order) for s, order in zip(seeds, ("EMC", "MCE", "CEM"), strict=True)
            },
            "positive_control_seeds": [],
            "positive_control_scope": "separate completed calibration; main stock starts empty",
            "training_attempts": 2,
            "budget_frontier": [1, 2],
            "frontier_order": "randomized within final task packet; budget one shares anchor forms",
            "quality_MCID": 0.05,
            "allowed_quality_harm": 0.05,
            "complete_compute_relative_reduction_MCID": 0.20,
            "MCID_rationale": (
                "5 quality points is material on the finite law; complete cost benefit requires "
                "matched quality and all investment/verification/transfer/maintenance costs"
            ),
            "interval_alpha": 0.005,
            "familywise_alpha_budget": 0.05,
            "maximum_preregistered_quality_contrasts": 8,
            "multiplicity": "Bonferroni 99.5% world bounds plus Holm on performed one-sided bounds",
            "formation_horizon_tokens": 20480,
            "formation_success_budget": "two model drafts and 20480 reserved tokens, "
            "within the finite whole-arm execution/checker/time caps",
            "formation_time_restriction_is_endpoint_not_physical_deadline": True,
            "precision_plan": original_file(precision),
            "pilot_review": original_file(pilot_analysis),
            "limited_power": True,
            "assay_insensitive_carried_from_pilot": pilot["sensitivity"]["assay_insensitive"],
            "no_third_calibration": True,
            "training_two_draft_setting_was_not_pilot_validated": True,
            "difficulty_selection": "all low/middle/high families retained; no passing family band",
            "missing_or_timeout": "keep offered denominator; missing usage charges reservation",
            "infrastructure_invalidity": "retain invalid/incomplete cohort; no replacement worlds",
            "stopping": "fixed three worlds; no optional continuation or efficacy reroll",
            "H_SHARE": "unjudged_I_not_performed",
            "H_ADAPT": "unjudged_A_not_performed",
            "owned_server_metadata_calls": 160,
            "OS_observation_interval_seconds": 5,
            "maximum_OS_observation_samples": 10801,
            "cohort_wall_seconds": 54000,
            "cleanup_grace_seconds": 300,
            "aggregate_main_caps": {
                "model_requests": 864,
                "model_tokens": 8847360,
                "serial_inference_concurrency": 1,
            },
            "maximum_scheduled_main_model_drafts": 723,
            "runtime_contract": json.loads(runtime.read_bytes()),
            "installed_wheel": {**original_file(wheel), "package_file_sha256": package},
            "installed_sdist": original_file(archive),
            "native_gate": {
                "candidate_directory": candidate.resolve().relative_to(ROOT).as_posix(),
                "gate": gate.resolve().relative_to(ROOT).as_posix(),
                "release_manifest": release_manifest.resolve().relative_to(ROOT).as_posix(),
                "release_manifest_sha256": original_file(release_manifest)["sha256"],
                "reports_directory": reports.resolve().relative_to(ROOT).as_posix(),
            },
            "wire_schemas": {
                family + "/" + level: wire_schema(family, level).model_json_schema()
                for family in ("sql", "calibration", "composition")
                for level in ("low", "middle", "high")
            },
        }
    )
    base["caps"].update(
        {
            "model_calls": 96,
            "model_tokens": 983040,
            "model_identity_observations": 96,
            "application_actions": 8192,
            "execution_invocations": 8192,
            "checker_cases": 2048,
            "retrieval_calls": 256,
            "wall_seconds": 12000,
        }
    )
    base["sensitivity_gate"]["unit"] = "family_by_difficulty"
    base["sensitivity_gate"]["selection"] = (
        "retain all calibrated strata; insensitive pilot limits interpretation, and "
        "confirmation cannot establish equivalence from zero differences"
    )
    return base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--classification",
        choices=("calibration", "planning", "confirmation"),
        default="calibration",
    )
    for name in (
        "candidate",
        "gate",
        "release-manifest",
        "reports",
        "runtime",
        "precision",
        "pilot-analysis",
    ):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    if args.classification == "planning":
        value = precision_planning(args.id)
    elif args.classification == "confirmation":
        names = (
            "candidate",
            "gate",
            "release_manifest",
            "reports",
            "runtime",
            "precision",
            "pilot_analysis",
        )
        if any(getattr(args, name) is None for name in names):
            parser.error(
                "confirmation requires exact candidate/native gate/runtime/pilot/planning inputs"
            )
        value = confirmation(args.id, **{name: getattr(args, name) for name in names})
    else:
        value = calibration(args.id)
    write_new(args.output, value)


if __name__ == "__main__":
    main()
