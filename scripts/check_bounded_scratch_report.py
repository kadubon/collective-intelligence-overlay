"""Hosted no-inference integrity and all-offered denominator check for 0.4.4."""

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(root=ROOT):
    study = root / "docs/studies/bounded-scratch-044"
    manifest = json.loads((study / "scientific-manifest-v1.json").read_bytes())
    for section in ("final_source_hashes", "derivatives"):
        for name, expected in manifest[section].items():
            path = (root / name).resolve()
            assert path.is_relative_to(root.resolve()) and path.is_file() and not path.is_symlink()
            assert path.stat().st_size <= 4 * 1024 * 1024
            raw = path.read_bytes()
            if section == "final_source_hashes":
                raw = raw.replace(b"\r\n", b"\n")
            assert hashlib.sha256(raw).hexdigest() == expected, name
    result_dir = study / "results-v1"
    result = json.loads((result_dir / "results.json").read_bytes())
    with (result_dir / "paired.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 44
    assert len({(r["run_revision"], r["world"], r["arm"], r["offer"]) for r in rows}) == 44
    verified = [json.loads((result_dir / f"verification-{i}.json").read_bytes()) for i in (1, 2, 3)]
    assert all(v["verification"] == "passed" and not v["pending"] for v in verified)
    assert [v["generation_calls"] for v in verified] == [36, 0, 4]
    assert result["generation_requests"] == sum(v["generation_calls"] for v in verified) == 40
    assert sum(int(r["actual_measured_tokens"]) for r in rows) == result["measured_tokens"] == 28178
    assert sum(int(r["actual_charged_tokens"]) for r in rows) == result["charged_tokens"] == 28178
    assert (
        sum(int(r["missing_usage_requests"]) for r in rows) == result["missing_usage_requests"] == 0
    )
    for row in rows:
        assert int(row["Q"]) in (0, 1)
        if not int(row["Q"]):
            assert float(row["restricted_time_seconds"]) == 300
            assert int(row["restricted_charged_tokens"]) == 4352
    for setting, stats in result["G1"].items():
        family, level = setting.split("/")
        group = [
            r
            for r in rows
            if r["run_revision"] == "1"
            and r["family"] == family
            and r["level"] == level
            and r["study_stage"].startswith("screen-")
        ]
        assert len(group) == stats["offered"] == 8
        assert sum(int(r["Q"]) for r in group) == stats["passed"]
    assert result["status"] == "assay_not_ready" and result["G2"]["offered"] == 0
    assert result["confirmation_worlds"] == 0 and not result["confirmation_started"]
    assert all(result[k] == "not_estimated" for k in ("H_ACC", "H_CIO", "H_FORM"))
    assert len(result["G3"]) == 4 and all(d["ready"] for d in result["G3"])
    assert all(
        d["full"]["calls"] == 0 and d["empty"]["calls"] == 1 and d["empty"]["retrieval_count"] == 0
        for d in result["G3"]
    )
    assert result["break_even"] is None and result["energy_joules"] is None
    assert result["full_compute"] is None and result["future_maintenance"] is None
    assert result["normal_cleanup_inclusive_charge_seconds"] <= 14400
    return {"status": result["status"], "offered": len(rows), "generation_performed": False}


if __name__ == "__main__":
    print(json.dumps(check()))
