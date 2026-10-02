"""No favorable effect is a test condition; retain bounds and censored failures."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from accumulation_statistics import (  # noqa: E402
    bounded_margin_p,
    evidence_for_margin,
    holm,
    paired_worlds,
    restricted_formation_time,
    simulation,
)


def test_all_ceiling_is_not_zero_width_population_interval_or_equivalence():
    result = paired_worlds([1] * 8, [1] * 8)
    assert result["mean_difference"] == 0 and result["degenerate_bootstrap"] is True
    assert result["bootstrap_percentile_interval"] is None
    lower, upper = result["independent_world_hoeffding_interval"]
    assert lower < 0 < upper
    assert evidence_for_margin(result, 0.05) == "unjudged_precision_insufficient"
    assert bounded_margin_p(result, 0.05) == 1


def test_world_pairs_and_rare_failures_remain_in_the_denominator():
    result = paired_worlds([1, 0, 1, 0], [1, 1, 0, 1])
    assert result["independent_worlds"] == 4 and result["mean_difference"] == -0.25
    assert len(result["world_differences"]) == 4
    assert result["bootstrap_percentile_interval"] is not None
    with pytest.raises(ValueError, match="per independent world"):
        paired_worlds([[1, 1], [0, 1]], [[1, 0], [1, 1]])
    with pytest.raises(ValueError, match="missing"):
        paired_worlds([1, float("nan")], [1, 1])


def test_multiplicity_does_not_turn_unperformed_panels_into_significance():
    assert holm({"acc-c": 0.01, "acc-m": 0.02, "form": 0.8}) == {
        "acc-c": 0.03,
        "acc-m": 0.04,
        "form": 0.8,
    }
    with pytest.raises(ValueError):
        holm({"share": None})


def test_failure_endpoint_time_is_censored_and_not_measured_consumption():
    assert restricted_formation_time(False, 3, 600) == 600
    assert restricted_formation_time(True, 3, 600) == 3
    assert restricted_formation_time(True, 601, 600) == 600
    with pytest.raises(ValueError, match="outside"):
        restricted_formation_time(True, -1, 600)


def test_planning_uses_multiple_cluster_and_censoring_scenarios():
    result = simulation(repetitions=100)
    rows = result["scenarios"]
    assert len(rows) == 216
    assert {r["within_world_correlation"] for r in rows} == {0.1, 0.4, 0.7}
    assert {r["censor_probability"] for r in rows} == {0, 0.1, 0.2}
    assert {r["baseline"] for r in rows} == {0.3, 0.5, 0.8}
    assert result["zero_variance_pilot_used"] is False
    assert result["distribution_free_worlds_for_simultaneous_halfwidth005"] == 4794
    assert result["distribution_free_worlds_for_95_halfwidth005"] == 2952
    assert result["simultaneous_planning_compares_zero_and_MCID_separately"]
    assert all(r["simultaneous_one_sided_alpha"] == 0.0025 for r in rows)
    for row in rows:
        assert 0 <= row["paired_t_probability_exceeding_MCID_simultaneous"] <= 1
        assert (
            row["paired_t_probability_exceeding_MCID_simultaneous"]
            <= row["paired_t_power_against_zero_simultaneous"]
        )
