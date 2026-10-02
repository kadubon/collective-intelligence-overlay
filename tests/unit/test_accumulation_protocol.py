"""State-independent schedule, fixed forms, finite budgets and sign-blind selection."""

import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
import prepare_accumulation_protocol as prepare  # noqa: E402
from accumulation_protocol import schedule, unrelated_world  # noqa: E402
from accumulation_tasks import World  # noqa: E402
from prepare_accumulation_protocol import calibration  # noqa: E402


@pytest.mark.parametrize("seed", [307191, 872131])
def test_task_forms_and_intervention_order_are_fixed_before_outcomes(seed):
    protocol = calibration("unit-not-inference")
    world = World(seed)
    e, m, c = (schedule(world, arm, protocol) for arm in ("E", "M", "C"))
    assert m == c and len({o.id for o in m}) == len(m)
    assert [(o.id, o.problem) for o in e if o.phase == "training"] == [
        (o.id, o.problem) for o in m if o.phase == "training"
    ]
    assert {o.peer for o in m if o.phase == "training"} == {"producer", "receiver"}
    checkpoints = {
        t: [o for o in m if o.phase == "anchor" and o.checkpoint == t and o.view == "full"]
        for t in (0, 3, 6)
    }
    assert all(len(v) == 6 for v in checkpoints.values())
    assert len({o.problem.id for v in checkpoints.values() for o in v}) == 18
    for full in checkpoints[6]:
        siblings = [o for o in m if o.problem.id == full.problem.id and o.phase == "anchor"]
        assert {o.view for o in siblings} == {"full", "empty", "irrelevant"}
        assert all(o.problem == full.problem and o.cases == full.cases for o in siblings)
    assert all(
        o.phase != "training" for o in m[m.index(next(o for o in m if o.phase == "placebo")) :]
    )
    assert unrelated_world(world).names() != world.names()
    assert {o.world.id for o in m if o.phase == "placebo"} == {unrelated_world(world).id}
    assert all(o.world.id == world.id for o in m if o.phase != "placebo")
    formation = [o for o in m if o.phase == "formation"]
    assert {o.view for o in formation} == {"full", "empty"}
    assert all(o.attempts == 2 and o.problem.family == "composition" for o in formation)
    assert not any(
        o.problem.contract == formation[0].problem.contract for o in m if o.phase == "training"
    )
    assert {o.problem.condition for o in m if o.phase == "challenge"} == {
        "unseen",
        "drift",
        "negative",
    }
    assert all(o.peer == "newreceiver" for o in m if o.phase in {"qualification", "transfer"})


def test_confirmation_declaration_has_finite_whole_world_caps_and_no_outcome_selection(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(prepare, "ROOT", tmp_path)
    candidate = tmp_path / "candidate"
    (candidate / "dist").mkdir(parents=True)
    wheel = candidate / "dist/collective_intelligence_overlay-0.4.2-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as package:
        package.writestr("collective_intelligence_overlay/__init__.py", b"unit candidate fixture")
    archive = candidate / "dist/collective_intelligence_overlay-0.4.2.tar.gz"
    archive.write_bytes(b"unit pair declaration only; no native gate claim")
    (candidate / "artifacts.json").write_text(
        json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (wheel, archive)})
    )
    runtime, precision, pilot = [
        tmp_path / name for name in ("runtime.json", "plan.json", "pilot.json")
    ]
    runtime.write_text("{}")
    precision.write_text(json.dumps({"limited_power": True, "selected_independent_worlds": 3}))
    pilot.write_text(
        json.dumps(
            {
                "verified_originals": True,
                "classification": "calibration",
                "sensitivity": {"assay_insensitive": True},
            }
        )
    )
    manifest, gate = tmp_path / "manifest.json", tmp_path / "gate.json"
    manifest.write_text("{}")
    gate.write_text("{}")
    protocol = prepare.confirmation(
        "unit-declaration-not-inference",
        candidate=candidate,
        gate=gate,
        release_manifest=manifest,
        reports=tmp_path,
        runtime=runtime,
        precision=precision,
        pilot_analysis=pilot,
    )
    assert protocol["classification"] == "confirmation"
    assert len(protocol["world_seeds"]) == 3 and protocol["arms"] == ["E", "M", "C"]
    assert protocol["no_third_calibration"] and protocol["limited_power"]
    assert protocol["assay_insensitive_carried_from_pilot"]
    assert protocol["maximum_preregistered_quality_contrasts"] * protocol["interval_alpha"] <= 0.05
    assert protocol["aggregate_main_caps"]["model_requests"] == 9 * protocol["caps"]["model_calls"]
    assert protocol["aggregate_main_caps"]["model_tokens"] == 9 * protocol["caps"]["model_tokens"]
    drafts = sum(
        o.attempts
        for arm in protocol["arms"]
        for o in schedule(World(123), arm, protocol)
        if o.phase != "qualification"
    )
    assert drafts * 3 == protocol["maximum_scheduled_main_model_drafts"]
    assert "equivalence" in protocol["sensitivity_gate"]["selection"]
    assert protocol["installed_wheel"]["sha256"] == hashlib.sha256(wheel.read_bytes()).hexdigest()


def test_pilot_never_selects_on_C_minus_M_or_confirmation_seeds():
    p = calibration("unit-not-inference")
    assert p["arms"] == ["E", "M"] and len(p["world_seeds"]) == 2
    assert not set(p["positive_control_seeds"]) & set(p["world_seeds"])
    assert (
        p["caps"]["model_calls"]
        * (p["model_options"]["num_ctx"] + p["model_options"]["num_predict"])
        == p["caps"]["model_tokens"]
    )
    assert (
        p["model_options"]["draft_num_predict"] == 0 and p["model_options"]["num_predict"] >= 1024
    )
    assert p["sensitivity_gate"]["E_M_quality_band"] == [0.3, 0.8]
    assert p["sensitivity_gate"]["maximum_calibration_cohorts"] == 2
    assert p["caps"]["concurrent_model_requests"] == 1
    assert p["cohort_wall_seconds"] == 43200


def test_prospective_frontier_randomizes_packets_and_reuses_exact_anchor_forms():
    protocol = calibration("prospective-unit-not-inference")
    protocol.update(schedule_schema="2", budget_frontier=[1, 2], training_attempts=2)
    world = World(191307171)
    for name in ("E", "M", "C"):
        offered = schedule(world, name, protocol)
        assert len({o.id for o in offered}) == len(offered)
        ordinary = [o for o in offered if o.phase != "qualification"]
        assert sum(o.attempts for o in ordinary) == (63 if name == "E" else 89)
        for o in [o for o in offered if o.phase == "frontier"]:
            anchor = next(a for a in offered if a.id == o.id.replace("frontier-", "anchor-"))
            assert anchor.problem == o.problem and anchor.cases == o.cases
            assert anchor.attempts == 1 and o.attempts == 2
        final = [o for o in offered if o.phase in {"anchor", "frontier"} and o.checkpoint == 6]
        assert len(final) == (12 if name == "E" else 30)
        assert any(
            o.phase == "anchor"
            for o in final[final.index(next(o for o in final if o.phase == "frontier")) + 1 :]
        )
