"""Recompute committed result tables without a model, network or raw regeneration."""

import json
from pathlib import Path

from analyze_gemma_tabular import analyze

ROOT = Path(__file__).resolve().parents[1]


def check(path):
    saved = json.loads(path.read_bytes())
    assert saved["status"] == "analyzed" and saved["inference_performed"] is False
    episodes = saved["episodes"]
    assert len(episodes) == 2 * saved["paired_episodes"]
    assert {(e["block"], e["arm"]) for e in episodes} == {
        (block, arm) for block in range(saved["paired_episodes"]) for arm in ("static", "adaptive")
    }
    for episode in episodes:
        assert episode["tasks"] == 6 and 0 <= episode["passed"] <= 6
        assert episode["fraction"] == episode["passed"] / 6
        assert 0 <= episode["unknown_tasks"] <= 6
        assert 0 <= episode["false_accepts"] <= 6 - episode["passed"]
        assert 0 <= episode["dispatched_inference_requests"] <= episode["attempts"] <= 4
        assert 0 <= episode["token_budget_charge"] <= 18432
    recomputed = analyze(
        {
            "status": "verified",
            "episodes": episodes,
            "protocol": {"classification": saved["classification"], "mcid": saved["mcid"]},
        }
    )
    # Analysis versions/source hash document the original analysis, while the
    # deterministic tables/statistics must agree under current locked tools.
    for key, value in recomputed.items():
        if key not in {"analysis_versions", "analysis_source_sha256"}:
            assert saved[key] == value, "saved analysis mismatch: " + key
    print(path.relative_to(ROOT).as_posix() + ": offline tables/statistics match")


if __name__ == "__main__":
    reports = sorted((ROOT / "docs/experiments/gemma-041").glob("*/analysis.json"))
    for path in reports:
        check(path)
    if not reports:
        print("real-model result tables are not yet committed; no inference performed")
