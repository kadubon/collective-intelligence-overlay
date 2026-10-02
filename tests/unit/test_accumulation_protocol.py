"""State-independent schedule, fixed forms, finite budgets and sign-blind selection."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
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
