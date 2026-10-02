"""Offered denominators and explicit invalid-study exclusion."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from accumulation_application import wire_schema  # noqa: E402
from analyze_gemma_accumulation import analyze, quality  # noqa: E402


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
