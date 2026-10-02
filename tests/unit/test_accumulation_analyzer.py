"""Offered denominators and explicit invalid-study exclusion."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from accumulation_application import wire_schema  # noqa: E402
from analyze_gemma_accumulation import (  # noqa: E402
    analyze,
    family_sensitivity,
    quality,
    sampled_resources,
)


def test_every_failed_censored_offering_remains_in_quality_denominator():
    rows = [
        {"phase": "anchor", "checkpoint": 6, "view": "full", "difficulty": "low", "succeeded": x}
        for x in (True, False, False)
    ]
    assert quality(rows) == 1 / 3
    with pytest.raises(ValueError):
        quality(rows, view="empty")


def test_declared_invalid_calibration_cannot_be_analyzed_as_performance(tmp_path):
    (tmp_path / "operator-invalidation-v1.json").write_text(
        json.dumps({"classification": "invalid_calibration", "reason": "source freshness confound"})
    )
    with pytest.raises(ValueError, match="invalid calibration"):
        analyze(tmp_path)


def test_low_affine_constraint_is_public_contract_not_unknown_parameter_oracle():
    schema = wire_schema("calibration", "low").model_json_schema()
    assert schema["properties"]["coefficients"]["prefixItems"][2]["const"] == 0
    assert all("const" not in f for f in schema["properties"]["coefficients"]["prefixItems"][:2])
    middle = wire_schema("calibration", "middle").model_json_schema()
    assert all("const" not in f for f in middle["properties"]["coefficients"]["prefixItems"])


def test_one_ceiling_and_one_floor_family_cannot_pass_by_pooled_average():
    families = [
        {"arm": arm, "family": family, "difficulty": "low", "mean_Q": q}
        for arm in ("E", "M")
        for family, q in (("sql", 0), ("calibration", 1))
    ]
    pooled = [{"arm": arm, "difficulty": "low", "mean_Q": 0.5} for arm in ("E", "M")]
    assert family_sensitivity(families, pooled, [0.3, 0.8]) == ([], ["low"])
    for row in families:
        row["mean_Q"] = 0.5
    assert family_sensitivity(families, pooled, [0.3, 0.8]) == (["low"], ["low"])


def test_missing_initial_cpu_does_not_impute_preexperiment_process_lifetime(tmp_path):
    samples = [
        {"status": "unavailable", "roots": [1]},
        {
            "status": "measured",
            "processes": [{"pid": 1, "started_at": "old", "cpu_seconds": 100, "rss_bytes": 10}],
        },
        {
            "status": "measured",
            "processes": [{"pid": 1, "started_at": "old", "cpu_seconds": 103, "rss_bytes": 12}],
        },
    ]
    (tmp_path / "os-processes.jsonl").write_text(
        "\n".join(json.dumps(s) for s in samples), encoding="utf-8"
    )
    value = sampled_resources(tmp_path, lambda _: {"hardware": {}})
    assert value["sampled_owned_process_CPU_lower_bound_seconds"] == 3
    assert value["unavailable_samples"] == 1 and not value["first_cohort_sample_available"]
    assert value["energy_joules"] is None and value["shared_WSL_PostgreSQL_CPU"] is None
