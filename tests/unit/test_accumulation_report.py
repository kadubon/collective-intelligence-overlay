"""The downstream renderer must not label smoke or unverified rows as study data."""

import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def renderer():
    path = Path(__file__).parents[2] / "scripts/report_gemma_accumulation.py"
    spec = importlib.util.spec_from_file_location("tested_accumulation_report", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("verified", "classification", "worlds"),
    [
        (False, "confirmation", 3),
        (True, "smoke", 2),
        (True, "incomplete", 2),
        (True, "calibration", 1),
    ],
)
def test_unverified_smoke_or_incomplete_analysis_cannot_render_as_study(
    renderer, tmp_path, verified, classification, worlds
):
    path = tmp_path / "analysis.json"
    path.write_text(
        json.dumps(
            {
                "verified_originals": verified,
                "classification": classification,
                "independent_worlds": worlds,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        renderer.render(path, tmp_path / "report")
    assert not (tmp_path / "report").exists()
