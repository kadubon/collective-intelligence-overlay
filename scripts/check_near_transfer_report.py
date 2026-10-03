"""Hosted, no-model check of bounded scientific results and declared denominators."""

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(root=ROOT):
    directory = root / "docs/studies/near-transfer-043/pilot-v1"
    manifest = json.loads((directory.parent / "scientific-manifest-v1.json").read_bytes())
    for section in ("final_source_hashes", "derivatives"):
        for name, expected in manifest[section].items():
            path = (root / name).resolve()
            assert path.is_relative_to(root.resolve()) and path.is_file()
            # Git stores LF text; Windows checkout may materialize CRLF. This
            # applies only to repository sources/derivatives, never signed/raw data.
            data = path.read_bytes().replace(b"\r\n", b"\n")
            assert hashlib.sha256(data).hexdigest() == expected, name
    for path in directory.iterdir():
        if path.is_symlink() or path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("scientific derivative exceeds finite file bound")
    result = json.loads((directory / "results.json").read_bytes())
    verified = json.loads((directory / "verification.json").read_bytes())
    with (directory / "paired.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 54 and len({(r["world"], r["arm"], r["offer"]) for r in rows}) == 54
    assert result["confirmation_worlds"] == 0 and verified["gate"]["status"] == "assay_not_ready"
    assert verified["generation_attempts"] == result["generation_requests"] == 54
    assert sum(int(r["actual_measured_tokens"]) for r in rows) == verified["measured_tokens"]
    assert sum(int(r["actual_charged_tokens"]) for r in rows) == verified["charged_tokens"]
    assert sum(int(r["missing_usage_requests"]) for r in rows) == 0
    for row in rows:
        q = int(row["Q"])
        assert q in (0, 1)
        assert int(row["prefix_Q_half_time"]) <= q and int(row["prefix_Q_half_tokens"]) <= q
        if not q:
            assert float(row["restricted_time_seconds"]) == 600
            assert float(row["restricted_charged_tokens"]) == 10240
    for family in ("sql", "calibration", "composition"):
        group = [r for r in rows if r["stage"] == "locked-validation" and r["family"] == family]
        assert len(group) == 6
        assert sum(int(r["Q"]) for r in group) == verified["gate"]["families"][family]["passed"]
    assert all(result[name] == "not_estimated" for name in ("H_ACC", "H_CIO", "H_FORM"))
    assert result["break_even"] is None and result["future_maintenance"] is None
    return {"offered_rows": len(rows), "status": result["status"], "model_generation": False}


if __name__ == "__main__":
    print(json.dumps(check()))
