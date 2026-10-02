"""World-level bounded contrasts and finite-cohort precision planning.

Task/checkpoint/peer rows never become independent observations. Bootstrap is
descriptive; the distribution-free independent-world bound remains alongside it,
including degenerate samples. No non-significant result establishes equivalence.
"""

import math

import numpy as np
from scipy import stats


def paired_worlds(left, right, *, alpha=0.05, seed=729101, draws=20000):
    left, right = np.asarray(left, dtype=float), np.asarray(right, dtype=float)
    if left.ndim != 1 or right.shape != left.shape or left.size < 2:
        raise ValueError("one equally sized final score per independent world is required")
    if not (0 < alpha < 1) or not (1000 <= draws <= 100000):
        raise ValueError("finite interval settings required")
    if not np.all(np.isfinite(left)) or not np.all(np.isfinite(right)):
        raise ValueError("missing worlds cannot silently disappear")
    if np.any((left < 0) | (left > 1) | (right < 0) | (right > 1)):
        raise ValueError("quality score must lie in [0,1]")
    d = left - right
    estimate = float(d.mean())
    radius = math.sqrt(2 * math.log(2 / alpha) / d.size)
    bound = [max(-1.0, estimate - radius), min(1.0, estimate + radius)]
    degenerate = bool(np.ptp(d) == 0)
    if degenerate:
        bootstrap = None
    else:
        rng = np.random.default_rng(seed)
        sampled = d[rng.integers(d.size, size=(draws, d.size))].mean(axis=1)
        bootstrap = [float(x) for x in np.quantile(sampled, [alpha / 2, 1 - alpha / 2])]
    return {
        "independent_worlds": int(d.size),
        "mean_difference": estimate,
        "world_differences": d.tolist(),
        "bootstrap_percentile_interval": bootstrap,
        "independent_world_hoeffding_interval": bound,
        "alpha": alpha,
        "degenerate_bootstrap": degenerate,
        "interpretation": "finite-task-law contrast; no equivalence or extrapolated acceleration",
    }


def evidence_for_margin(contrast, margin):
    if not 0 <= margin <= 1:
        raise ValueError("bounded declared margin required")
    lower, upper = contrast["independent_world_hoeffding_interval"]
    if lower > margin:
        return "supports_declared_margin_under_independent_world_assumption"
    if upper < -margin:
        return "supports_harm_under_independent_world_assumption"
    return "unjudged_precision_insufficient"


def bounded_margin_p(contrast, margin):
    """Conservative one-sided Hoeffding bound; no symmetry/label-swap assumption."""
    gap = max(0, contrast["mean_difference"] - margin)
    return math.exp(-contrast["independent_worlds"] * gap * gap / 2)


def holm(pvalues):
    """Adjust only performed, preregistered contrasts; missing is not p=0."""
    if not pvalues or any(
        not isinstance(p, int | float)
        or isinstance(p, bool)
        or not math.isfinite(p)
        or not 0 <= p <= 1
        for p in pvalues.values()
    ):
        raise ValueError("explicit finite performed-test p-values required")
    ordered = sorted(pvalues, key=pvalues.get)
    adjusted, previous = {}, 0.0
    for rank, name in enumerate(ordered):
        previous = max(previous, min(1.0, (len(ordered) - rank) * pvalues[name]))
        adjusted[name] = previous
    return adjusted


def restricted_formation_time(succeeded, observed_seconds, maximum):
    """Finite-policy success time is infinite on failure, then restricted to a horizon.

    This is not Kaplan-Meier censoring or measured wall/CPU consumption.
    """
    if not isinstance(succeeded, bool) or not math.isfinite(observed_seconds):
        raise ValueError("success status and actual observation time required")
    if observed_seconds < 0 or not math.isfinite(maximum) or maximum <= 0:
        raise ValueError("observation outside the preregistered horizon")
    return min(observed_seconds, maximum) if succeeded else maximum


def simulation(*, seed=820317, repetitions=4000, shift=0.05, interval_alpha=0.005):
    """Beta-binomial worlds: multiple heterogeneity/dependence/censoring scenarios.

    Parametric paired-t planning power is sensitivity information, not the power
    of the more conservative bound or a guarantee from a zero-variance pilot.
    """
    if not 0 < shift <= 0.5 or not 0 < interval_alpha < 0.05:
        raise ValueError("explicit finite positive shift and simultaneous interval alpha required")
    rng = np.random.default_rng(seed)
    rows = []
    for n in (2, 3, 6, 8, 12, 24, 64, 128):
        for baseline in (0.3, 0.5, 0.8):
            for correlation in (0.1, 0.4, 0.7):
                for censor in (0, 0.1, 0.2):
                    concentration = 1 / correlation - 1
                    common = rng.beta(
                        baseline * concentration,
                        (1 - baseline) * concentration,
                        size=(repetitions, n),
                    )
                    candidate = rng.binomial(6, np.clip(common + shift, 0, 1)) / 6
                    baseline_scores = rng.binomial(6, common) / 6
                    candidate[rng.random(candidate.shape) < censor] = 0
                    baseline_scores[rng.random(baseline_scores.shape) < censor] = 0
                    d = candidate - baseline_scores
                    means, sd = d.mean(axis=1), d.std(axis=1, ddof=1)
                    error = sd / math.sqrt(n)
                    nonzero = error > 0
                    t = np.divide(means, error, out=np.zeros_like(means), where=nonzero)
                    p = stats.t.sf(t, n - 1)
                    # A constant sample supplies no variance-based precision proof.
                    p[~nonzero] = 1
                    halfwidth = stats.t.ppf(0.975, n - 1) * error
                    halfwidth[~nonzero] = math.sqrt(2 * math.log(40) / n)
                    simultaneous_width = stats.t.ppf(1 - interval_alpha / 2, n - 1) * error
                    simultaneous_width[~nonzero] = math.sqrt(2 * math.log(2 / interval_alpha) / n)
                    margin_t = np.divide(
                        means - 0.05, error, out=np.zeros_like(means), where=nonzero
                    )
                    margin_p = stats.t.sf(margin_t, n - 1)
                    margin_p[~nonzero] = 1
                    rows.append(
                        {
                            "worlds": n,
                            "tasks_per_world_endpoint": 6,
                            "baseline": baseline,
                            "within_world_correlation": correlation,
                            "censor_probability": censor,
                            "true_shift_before_censoring": shift,
                            "paired_t_one_sided_power_alpha025": float(np.mean(p < 0.025)),
                            "median_approximate_95_halfwidth": float(np.median(halfwidth)),
                            "distribution_free_95_halfwidth": math.sqrt(2 * math.log(40) / n),
                            "planning_world_variance": float(np.mean(sd * sd)),
                            "observed_shift_after_clipping_censoring": float(means.mean()),
                            "normal_approximation_worlds_for_power80_against_zero": math.ceil(
                                (stats.norm.ppf(0.975) + stats.norm.ppf(0.8)) ** 2
                                * float(np.mean(sd * sd))
                                / max(float(means.mean()) ** 2, 1e-12)
                            ),
                            "normal_approximation_worlds_for_95_halfwidth005": math.ceil(
                                stats.norm.ppf(0.975) ** 2 * float(np.mean(sd * sd)) / 0.05**2
                            ),
                            "simultaneous_interval_alpha": interval_alpha,
                            "median_simultaneous_approximate_halfwidth": float(
                                np.median(simultaneous_width)
                            ),
                            "simultaneous_distribution_free_halfwidth": math.sqrt(
                                2 * math.log(2 / interval_alpha) / n
                            ),
                            "simultaneous_one_sided_alpha": interval_alpha / 2,
                            "paired_t_power_against_zero_simultaneous": float(
                                np.mean(p < interval_alpha / 2)
                            ),
                            "paired_t_probability_exceeding_MCID_simultaneous": float(
                                np.mean(margin_p < interval_alpha / 2)
                            ),
                        }
                    )
    return {
        "simulation_seed": seed,
        "repetitions": repetitions,
        "scenarios": rows,
        "independent_unit": "world, never task/peer/checkpoint",
        "zero_variance_pilot_used": False,
        "mcid": 0.05,
        "distribution_free_worlds_for_95_halfwidth005": math.ceil(2 * math.log(40) / 0.05**2),
        "simultaneous_interval_alpha": interval_alpha,
        "distribution_free_worlds_for_simultaneous_halfwidth005": math.ceil(
            2 * math.log(2 / interval_alpha) / 0.05**2
        ),
        "simultaneous_planning_compares_zero_and_MCID_separately": True,
        "planning_power_tests_zero_not_exceeding_mcid": True,
        "limited_cohort_cannot_guarantee_five_percentage_point_precision": True,
    }
