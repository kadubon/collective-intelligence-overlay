"""Scientific contracts, endpoints and conservative accounting before real inference."""

import json
import sys
from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from accumulation_primitives import Solution, bounded_execute  # noqa: E402
from accumulation_tasks import compare  # noqa: E402
from check_gemma_transport import validate_wire  # noqa: E402
from near_transfer_application import model_prompt, wire_schema  # noqa: E402
from near_transfer_protocol import (  # noqa: E402
    CohortCap,
    choose_levels,
    entrance_gate,
    restricted_endpoint,
)
from near_transfer_tasks import LEVELS, World  # noqa: E402


@pytest.mark.parametrize("seed", [943100, 943203, 943405])
async def test_every_level_positive_and_negative_control(seed):
    world = World(seed, "unit")
    for family, levels in LEVELS.items():
        for level in levels:
            problem = world.problem(family, level, "public")
            hidden = world.problem(family, level, "hidden")
            oracle = world.oracle(problem)
            assert compare(await bounded_execute(oracle, problem), world.expected(problem))
            assert compare(await bounded_execute(oracle, hidden), world.expected(hidden))
            negative = (
                oracle.model_copy(update={"coefficients": (0, 0, 0)})
                if family != "sql"
                else oracle.model_copy(
                    update={
                        "sql": 'SELECT bucket AS "group", 0 AS value FROM readings GROUP BY bucket'
                    }
                )
            )
            assert not compare(await bounded_execute(negative, hidden), world.expected(hidden))
            if family == "composition":
                wrong = oracle.model_copy(
                    update={
                        "calibration_order": "calibrate-then-reduce"
                        if oracle.calibration_order == "reduce-then-calibrate"
                        else "reduce-then-calibrate"
                    }
                )
                assert not compare(await bounded_execute(wrong, hidden), world.expected(hidden))


def test_new_application_inputs_do_not_contain_checker_or_arm_labels(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    w = World(943100, "screen")
    for family, levels in LEVELS.items():
        p = w.problem(family, levels[0], "public")
        text = model_prompt(p, ())
        public = json.loads(text.split("\n", 1)[1])
        assert set(public) == {"problem", "skills"}
        assert not {"expected", "seed", "stage", "arm", "checker"} & set(public["problem"])
        assert public["skills"] == []
        assert text == model_prompt(p, ())
        if family == "sql":
            assert w.oracle(p).sql not in text
        source = Path(__file__).resolve().parents[2] / "scripts/near_transfer_application.py"
        assert "near_transfer_tasks" not in source.read_text()


@pytest.mark.parametrize(
    "family,value",
    [
        ("sql", {"family": "sql", "uses": []}),
        ("calibration", {"family": "calibration", "uses": []}),
        ("composition", {"family": "composition", "uses": []}),
    ],
)
def test_short_schema_cannot_invent_missing_executable_fields(family, value):
    with pytest.raises(ValidationError):
        validate_wire(json.dumps(value), wire_schema(family).model_json_schema(), Solution)


def test_family_gate_never_pools_floor_and_ceiling():
    rows = [
        {"family": family, "succeeded": i < k}
        for family, k in (("sql", 0), ("calibration", 6), ("composition", 3))
        for i in range(6)
    ]
    gate = entrance_gate(rows, [{"succeeded": True}] * 18, 18, 18, True)
    assert gate["status"] == "assay_not_ready"
    assert not gate["confirmation_authorized"]
    assert gate["families"]["composition"]["ready"]


def test_selection_uses_only_scratch_quality_with_declared_tie():
    candidates = {"sql": ["S1", "S2"]}
    rows = [
        {
            "family": "sql",
            "level": level,
            "succeeded": i < 2,
            "C_minus_M": 99 if level == "S2" else -99,
        }
        for level in candidates["sql"]
        for i in range(4)
    ]
    assert choose_levels(rows, candidates)["selected"] == {"sql": "S1"}
    assert {
        World(1, stage).id for stage in ("screen", "locked-validation", "confirmation")
    }.__len__() == 3


def test_all_offered_failure_endpoint_is_separate_from_actual_consumption():
    record = {
        "attempts": [{"kind": "model", "succeeded": False}],
        "inclusive_wall_seconds": 2,
        "budget_before": {"measured_tokens": 0, "charged_tokens": 0, "missing_usage_requests": 0},
        "budget_after": {"measured_tokens": 0, "charged_tokens": 5120, "missing_usage_requests": 1},
    }
    endpoint = restricted_endpoint(
        record, {"endpoint_time_seconds": 600, "endpoint_token_horizon": 10240}
    )
    assert endpoint["Q"] == 0
    assert endpoint["restricted_time_seconds"] == 600
    assert endpoint["actual_wall_seconds"] == 2
    assert endpoint["restricted_charged_tokens"] == 10240
    assert endpoint["measured_token_interval"] == [0, 5120]


def test_serial_global_cap_preserves_missing_reservation_and_refuses_resume(tmp_path):
    protocol = {
        "caps": {
            "model_calls": 256,
            "model_tokens": 400000,
            "wall_seconds": 14400,
            "application_actions": 100,
        },
        "model_options": {"num_ctx": 4096, "num_predict": 1024},
        "sources": {},
        "pilot_max_requests": 60,
        "request_seconds": 120,
        "endpoint_time_seconds": 600,
        "endpoint_token_horizon": 10240,
    }
    cap = CohortCap(protocol, tmp_path, tmp_path)
    cap.begin_offer("w", "M", "a", "pilot")
    assert cap.reserve_model("a-draft-0")
    with pytest.raises(ValueError):
        cap.reserve_model("a-draft-0")
    cap.end_offer()
    assert cap.charged_tokens == 5120 and cap.missing_usage == 1
    cap.close()
    with pytest.raises(FileExistsError):
        CohortCap(protocol, tmp_path, tmp_path)


def test_source_change_prevents_another_generation(tmp_path):
    from near_transfer_protocol import sha

    source = tmp_path / "source.py"
    source.write_text("original")
    protocol = {
        "caps": {
            "model_calls": 256,
            "model_tokens": 400000,
            "wall_seconds": 14400,
            "application_actions": 100,
        },
        "model_options": {"num_ctx": 4096, "num_predict": 1024},
        "sources": {"source.py": sha(source)},
        "pilot_max_requests": 60,
        "request_seconds": 120,
        "endpoint_time_seconds": 600,
        "endpoint_token_horizon": 10240,
    }
    cap = CohortCap(protocol, tmp_path, tmp_path)
    cap.begin_offer("w", "C", "a", "pilot")
    source.write_text("changed")
    with pytest.raises(ValueError, match="source changed"):
        cap.reserve_model("a-draft-0")
    assert cap.calls == 0
    cap.end_offer()
    cap.close()


def test_offline_invalid_program_stays_a_failed_offer_and_hidden_forms_cannot_change():
    from analyze_near_transfer import check_transcript

    world = World(943203, "locked-validation")
    public = world.problem("sql", "S1", "public")
    hidden = world.problem("sql", "S1", "independent")
    transcript = {
        "transcripts": [
            {
                "case": {"problem": p.model_dump(mode="json"), "expected": world.expected(p)},
                "observed": {"state": "completed", "result": {"program_error": "ValueError"}},
                "passed": False,
            }
            for p in (public, hidden)
        ]
    }
    artifacts = {("verifier", "a" * 64): json.dumps(transcript).encode()}
    value = {"check": {"artifact_digest": "a" * 64}}
    assert check_transcript(value, world, artifacts, (public, hidden)) == {"program_ValueError"}
    with pytest.raises(ValueError, match="planned forms"):
        check_transcript(value, world, artifacts, (public, public))


def test_empty_views_preserve_model_input_for_each_new_family():
    from accumulation_stock import Snapshot, retrieve

    world = World(943400, "confirmation")
    for family, level in (("sql", "S1"), ("calibration", "K1"), ("composition", "F0")):
        problem = world.problem(family, level, "near/public")
        prompts = []
        for arm in ("M", "C"):
            snapshot = Snapshot(world=world.id, arm=arm, checkpoint=4, skills=())
            for view in ("full", "empty"):
                visible = retrieve(snapshot, problem, "newreceiver", view=view, revision="2")
                prompts.append(model_prompt(problem, visible))
        assert len(set(prompts)) == 1
