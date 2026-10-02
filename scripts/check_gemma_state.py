"""Reconstruct cognitive states from the ordered original offered trajectory.

The caller verifies every selected execution/check first. This reader then checks
exact state membership and origin; a self-consistent arbitrary snapshot cannot
substitute for the actual allowed learning history.
"""

from accumulation_primitives import Solution
from accumulation_protocol import matched_placebo, schedule
from accumulation_stock import Skill, Snapshot
from accumulation_tasks import World

from collective_intelligence_overlay.bindings import Binding


def learned_skill(offer, selected, episode, *, world=None, producer=None, problem=None):
    binding = Binding.model_validate(selected["construction"]["binding"])
    evidence = selected["check"].get("evidence")
    from accumulation_primitives import Problem

    original = Problem.model_validate(problem or offer["problem"])
    return Skill(
        id=binding.id,
        producer=producer or offer["peer"],
        family=original.family,
        contract=original.contract,
        revision=original.revision,
        schema_digest=original.schema_digest,
        solution=Solution.model_validate(selected["solution"]),
        basic_passed=True,
        independent_verdict="PASS",
        evidence_id=evidence["id"] if evidence else None,
        binding_digest=binding.digest,
        artifact_digest=binding.artifact_digest,
        source_world=world or offer["world"],
        source_binding=binding,
        source_problem=original,
        episode=episode,
    )


def reconstruct_states(summary, protocol):
    world, arm = World(summary["seed"]), summary["arm"]
    if summary["world"] != world.id:
        raise ValueError("world identity differs from declared independent seed")
    plan = schedule(world, arm, protocol)
    ordinary = [o for o in plan if o.phase != "qualification"]
    if [o["id"] for o in summary["offers"]] != [o.id for o in ordinary]:
        raise ValueError("original offer order differs from the fixed trajectory")
    stock = Snapshot(world=world.id, arm=arm, checkpoint=0, skills=())
    expected, checkpoints = {}, {"0": stock}
    pool, final, irrelevant, matching = [], None, None, None
    receiver = Snapshot(world=world.id, arm=arm, checkpoint=6, skills=())
    qualifications = summary.get("qualification", [])
    if len({q["id"] for q in qualifications}) != len(qualifications):
        raise ValueError("duplicate receiver qualification")
    qualified = {q["id"]: q for q in qualifications}
    expected_qualification_ids = set()
    receiver_ready = False
    for item, offered in zip(ordinary, summary["offers"], strict=True):
        if (
            offered["problem"] != item.problem.model_dump(mode="json")
            or offered["world"] != world.id
            or offered["arm"] != arm
            or offered["peer"] != item.peer
            or offered["phase"] != item.phase
            or offered["view"] != item.view
            or offered["task_world"] != item.world.id
        ):
            raise ValueError("original offered contract differs from the fixed trajectory")
        if item.phase == "placebo" and final is None:
            final = stock
            checkpoints["6"] = final
        if item.phase == "anchor" and item.checkpoint == 3:
            checkpoints["3"] = stock
        if item.phase == "anchor" and item.checkpoint == 6 and irrelevant is None:
            irrelevant, matching = matched_placebo(final, pool)
        if item.phase == "transfer" and not receiver_ready:
            for qualification in (o for o in plan if o.phase == "qualification"):
                source = next(
                    (
                        s
                        for s in final.skills
                        if s.family == qualification.problem.family
                        and s.contract == qualification.problem.contract
                    ),
                    None,
                )
                if source is None:
                    continue
                expected_qualification_ids.add(qualification.id)
                q = qualified.get(qualification.id)
                if (
                    q is None
                    or q["source_skill"] != source.id
                    or q["problem"] != qualification.problem.model_dump(mode="json")
                ):
                    raise ValueError("missing or changed planned receiver qualification")
                if q["succeeded"]:
                    local = learned_skill(
                        offered,
                        {**q, "solution": source.solution.model_dump(mode="json")},
                        6,
                        producer="newreceiver",
                        problem=q["problem"],
                    )
                    receiver = receiver.model_copy(update={"skills": (*receiver.skills, local)})
            receiver_ready = True
        snapshot = stock
        if item.phase == "placebo":
            snapshot = Snapshot(world=world.id, arm=arm, checkpoint=6, skills=())
        elif item.view == "irrelevant":
            snapshot = irrelevant
        elif item.phase == "transfer":
            snapshot = receiver
        elif final is not None:
            snapshot = final
        if (
            offered["snapshot_digest"] != snapshot.digest
            or offered["checkpoint"] != snapshot.checkpoint
            or offered["episode"] != item.episode
            or offered["learn"] != (item.phase == "training")
        ):
            raise ValueError("offered cognitive state differs from the actual learning history")
        expected[item.id] = snapshot
        selected = next((a for a in offered["attempts"] if a["succeeded"]), None)
        if item.phase == "training":
            skills = stock.skills
            if selected is not None and arm != "E":
                skills = (*skills, learned_skill(offered, selected, item.episode))
            stock = Snapshot(world=world.id, arm=arm, checkpoint=item.episode, skills=skills)
        elif item.phase == "placebo" and selected is not None:
            pool.append(learned_skill(offered, selected, 6, world=item.world.id))
        if offered["stock_digest_after"] != stock.digest:
            raise ValueError("readonly evaluation or training stock transition changed")
    if set(qualified) != expected_qualification_ids:
        raise ValueError("extra or missing planned receiver qualification")
    if summary["snapshots"] != {k: v.digest for k, v in checkpoints.items()}:
        raise ValueError("missing or changed predeclared immutable checkpoint")
    if summary["placebo_matching"] != matching:
        raise ValueError("foreign procedure matching differs from original state and pool")
    return {
        "initial": checkpoints["0"],
        "offers": expected,
        "checkpoints": checkpoints,
        "final": final,
        "irrelevant": irrelevant,
        "receiver": receiver if protocol.get("new_receiver") else None,
    }


def check_state_files(directory, states, read):
    paths = {
        "initial-stock.json": states["initial"],
        "final-stock.json": states["final"],
        "irrelevant-stock.json": states["irrelevant"],
        "new-receiver-stock.json": states["receiver"],
        **{f"snapshot-{k}.json": v for k, v in states["checkpoints"].items()},
    }
    for name, expected in paths.items():
        if expected is not None and Snapshot.model_validate(read(directory / name)) != expected:
            raise ValueError("original immutable stock differs from reconstructed learning history")
