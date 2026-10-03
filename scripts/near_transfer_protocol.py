"""Finite preregistration, family gates and all-stage operator accounting."""

import hashlib
import json
import time
from pathlib import Path

from accumulation_session import SharedCap
from scipy.stats import binomtest


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def proportion(rows):
    n, k = len(rows), sum(bool(r["succeeded"]) for r in rows)
    interval = binomtest(k, n).proportion_ci(confidence_level=0.95) if n else None
    return {
        "passed": k,
        "offered": n,
        "rate": k / n if n else None,
        "exact_binomial_95_interval": [interval.low, interval.high] if interval else None,
        "uncertainty_scope": (
            "finite calibration observations; dependence may invalidate binomial interpretation"
        ),
    }


def choose_levels(rows, candidates):
    selected, summaries = {}, {}
    for family, levels in candidates.items():
        summaries[family] = {
            level: proportion([r for r in rows if r["family"] == family and r["level"] == level])
            for level in levels
        }
        if any(not summaries[family][level]["offered"] for level in levels):
            raise ValueError("incomplete screening cannot choose a difficulty")
        selected[family] = min(
            levels,
            key=lambda level: (abs(summaries[family][level]["rate"] - 0.5), levels.index(level)),
        )
    return {
        "selected": selected,
        "screen": summaries,
        "selection_inputs": (
            "ordinary-M scratch quality only; closest to 0.5, declared ascending tie order"
        ),
    }


def entrance_gate(rows, reference, normal, sent, stock_ready):
    families = {}
    for family in ("sql", "calibration", "composition"):
        summary = proportion([r for r in rows if r["family"] == family])
        low, high = (0.2, 0.8) if family == "composition" else (0.3, 0.7)
        summary.update(
            target=[low, high],
            ready=summary["offered"] == 6 and low <= summary["rate"] <= high,
        )
        families[family] = summary
    reference_summary = proportion(reference)
    completion = normal / sent if sent else 0
    ready = (
        all(r["ready"] for r in families.values())
        and (reference_summary["rate"] or 0) >= 0.9
        and completion >= 0.9
        and stock_ready
    )
    return {
        "status": "assay_ready" if ready else "assay_not_ready",
        "families": families,
        "reference": reference_summary,
        "completion": {"normal": normal, "sent": sent, "rate": completion},
        "natural_stock_reaches_retrieval_and_execution": stock_ready,
        "confirmation_authorized": ready,
        "confirmation_started": False,
    }


class CohortCap(SharedCap):
    """One serial cap across all sessions/stages; append intent before dispatch.

    Existing Executor reservations remain authoritative within each owner. This
    finite experiment counter does not replace them. No automatic resume exists.
    """

    def __init__(self, protocol, output, root, *, check_sources=True):
        super().__init__(
            protocol["caps"],
            context=protocol["model_options"]["num_ctx"],
            predict=protocol["model_options"]["num_predict"],
        )
        self.protocol, self.output, self.root = protocol, Path(output), Path(root)
        self.pending, self.active = None, None
        self.check_sources = check_sources
        self.offer_started = self.started
        self.offer_tokens = 0
        self.journal = (self.output / "generation-accounting.jsonl").open("x", encoding="utf-8")

    def begin_offer(self, world, arm, offer, phase):
        if self.pending or self.active:
            raise ValueError("serial offer or unsettled generation already active")
        self.active = {"world": world, "arm": arm, "offer": offer, "phase": phase}
        self.offer_started, self.offer_tokens = time.monotonic(), self.charged_tokens

    def end_offer(self):
        if self.pending:
            # Lost reply/driver exception retains reservation, never replays.
            self.settle_model(None)
        self.active = None

    def append(self, value):
        self.journal.write(json.dumps(value, allow_nan=False) + "\n")
        self.journal.flush()

    def reserve_model(self, identifier=None):
        if self.pending or not self.active or not identifier:
            raise ValueError("stable offer identity and no pending request required")
        if self.check_sources and any(
            sha(self.root / p) != digest for p, digest in self.protocol["sources"].items()
        ):
            raise ValueError("source changed; no resume or inference")
        if (
            self.calls >= self.protocol["pilot_max_requests"]
            or time.monotonic() - self.started + self.protocol["request_seconds"] + 300
            >= self.limits["wall_seconds"]
            or time.monotonic() - self.offer_started + self.protocol["request_seconds"]
            >= self.protocol["endpoint_time_seconds"]
            or self.charged_tokens - self.offer_tokens + self.reservation
            > self.protocol["endpoint_token_horizon"]
        ):
            return False
        if not super().reserve_model(identifier):
            return False
        self.pending = {
            **self.active,
            "attempt": identifier,
            "call": self.calls,
            "reservation": self.reservation,
        }
        self.append(
            {
                "kind": "reserved",
                **self.pending,
                "cohort_elapsed_seconds": time.monotonic() - self.started,
            }
        )
        return True

    def settle_model(self, observation):
        if not self.pending:
            raise ValueError("settlement without original pending reservation")
        super().settle_model(observation)
        self.append(
            {
                "kind": "settled",
                **self.pending,
                "observation": observation,
                "charged_total": self.charged_tokens,
                "measured_total": self.measured_tokens,
                "missing_total": self.missing_usage,
            }
        )
        self.pending = None

    def close(self):
        if self.pending:
            self.settle_model(None)
        self.journal.close()


def restricted_endpoint(record, protocol):
    attempts = record.get("attempts", [])
    first = next((a for a in attempts if a.get("succeeded")), None)
    if first and (
        first["endpoint_wall_seconds"] > protocol["endpoint_time_seconds"]
        or first["endpoint_charged_tokens"] > protocol["endpoint_token_horizon"]
    ):
        first = None
    actual_tokens = (
        record["budget_after"]["measured_tokens"] - record["budget_before"]["measured_tokens"]
    )
    charge = record["budget_after"]["charged_tokens"] - record["budget_before"]["charged_tokens"]
    missing = (
        record["budget_after"]["missing_usage_requests"]
        - record["budget_before"]["missing_usage_requests"]
    )
    return {
        "Q": int(first is not None),
        "restricted_time_seconds": min(
            first["endpoint_wall_seconds"], protocol["endpoint_time_seconds"]
        )
        if first
        else protocol["endpoint_time_seconds"],
        "restricted_charged_tokens": min(
            first["endpoint_charged_tokens"], protocol["endpoint_token_horizon"]
        )
        if first
        else protocol["endpoint_token_horizon"],
        "actual_wall_seconds": record["inclusive_wall_seconds"],
        "actual_measured_tokens": actual_tokens,
        "actual_charged_tokens": charge,
        "missing_usage_requests": missing,
        "measured_token_interval": [actual_tokens, charge],
        "failure_horizons_are_endpoints_not_consumption": True,
        "direct_reuse": bool(first and first["kind"] == "copied-executable"),
        "stop_reason": "first_pass"
        if first
        else record.get("error_type", "draft_budget_or_resource_cap"),
    }
