"""Write a new finite calibration declaration; confirmation is frozen after pilot review."""

import argparse
from datetime import UTC, datetime
from pathlib import Path

from accumulation_application import DIGEST, MODEL
from run_gemma_accumulation import sources

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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_new(args.output, calibration(args.id))


if __name__ == "__main__":
    main()
