"""Finite task schedule and state interventions, separate from the model application.

All offered tasks are fixed before inference. Outcomes may change a stock, never
the task list, difficulty, evaluation order or number of independent worlds.
"""

import random
from dataclasses import dataclass

from accumulation_stock import Snapshot, ViewSkill
from accumulation_tasks import LEVELS, World


@dataclass(frozen=True)
class Offer:
    id: str
    peer: str
    world: World
    problem: object
    cases: tuple
    phase: str
    checkpoint: int
    view: str = "full"
    attempts: int = 1
    episode: int = 0


def family_problem(world, split, family, level, **options):
    return getattr(world, "sales" if family == "sql" else family)(split, level, **options)


def unrelated_world(world):
    # Choose by latent contract only, before outcomes; no efficacy-dependent search.
    for offset in range(1, 100):
        other = World(world.seed + 70000000 + offset)
        if other.names() != world.names() and all(
            other.coefficients(level) != world.coefficients(level) for level in LEVELS
        ):
            return other
    raise ValueError("no independent placebo contract within declared generator bound")


def schedule(world, arm, protocol):
    result = []

    def add(
        identifier,
        phase,
        checkpoint,
        family,
        level,
        *,
        view="full",
        target=None,
        peer=None,
        attempts=1,
        episode=0,
        split=None,
        **options,
    ):
        w = target or world
        split = split or identifier
        problem = family_problem(w, split, family, level, **options)
        alternate = family_problem(w, split + "/independent-check", family, level, **options)
        if options.get("condition") == "unseen":
            problem = problem.model_copy(update={"component_contracts": ("sales-middle-sum",)})
            alternate = alternate.model_copy(update={"component_contracts": ("sales-middle-sum",)})
        result.append(
            Offer(
                identifier,
                peer or ("producer" if family == "sql" else "receiver"),
                w,
                problem,
                (problem, alternate),
                phase,
                checkpoint,
                view,
                attempts,
                episode,
            )
        )

    def anchors(checkpoint, views=("full",)):
        tasks = [(f, level) for level in LEVELS for f in ("sql", "calibration")]
        for index, (family, level) in enumerate(tasks):
            order = list(views)
            random.Random(f"{protocol['order_seed']}/{world.seed}/{checkpoint}/{index}").shuffle(
                order
            )
            for view in order:
                add(
                    f"anchor-{checkpoint}-{index}-{view}",
                    "anchor",
                    checkpoint,
                    family,
                    level,
                    view=view,
                    split=f"anchor-{checkpoint}-{index}",
                )

    anchors(0)
    for episode, (level, family) in enumerate(
        [(level, family) for level in LEVELS for family in ("sql", "calibration")], 1
    ):
        add(
            f"train-{episode}",
            "training",
            episode,
            family,
            level,
            episode=episode,
            attempts=protocol["training_attempts"],
        )
        if episode == 3:
            anchors(3)
    # Full/empty/irrelevant final evaluation uses exactly the same six public and
    # checker forms and model seed, in the predeclared randomized order.
    other = unrelated_world(world)
    for index, (level, family) in enumerate(
        [(level, family) for level in LEVELS for family in ("sql", "calibration")]
    ):
        add(
            f"placebo-{index}",
            "placebo",
            6,
            family,
            level,
            target=other,
            attempts=protocol["placebo_attempts"],
        )
    anchors(6, ("full", "empty", "irrelevant") if arm != "E" else ("full",))
    add("challenge-unseen", "challenge", 6, "sql", "middle", reduction="mean", condition="unseen")
    add("challenge-drift", "challenge", 6, "sql", "high", revision="2", condition="drift")
    add(
        "challenge-negative",
        "challenge",
        6,
        "calibration",
        "high",
        revision="negative-1",
        condition="negative",
    )
    for view in ("full", "empty") if arm != "E" else ("full",):
        p = world.composition("new-formation")
        q = world.composition("new-formation/independent-check")
        result.append(
            Offer(
                "formation-" + view,
                "receiver",
                world,
                p,
                (p, q),
                "formation",
                6,
                view,
                protocol["formation_attempts"],
            )
        )
    if protocol.get("new_receiver"):
        # Qualification forms are distinct from later transfer probes. Initial
        # import can authorize data copying only; the local output is rechecked.
        for index, (level, family) in enumerate(
            [(level, family) for level in LEVELS for family in ("sql", "calibration")]
        ):
            add(f"qualify-{index}", "qualification", 6, family, level, peer="newreceiver")
        for index, family in enumerate(("sql", "calibration")):
            for view in ("full", "empty"):
                add(
                    f"transfer-{index}-{view}",
                    "transfer",
                    6,
                    family,
                    "low",
                    peer="newreceiver",
                    view=view,
                    split=f"transfer-unseen-{index}",
                )
    return tuple(result)


def matched_placebo(stock, pool):
    chosen, comparisons = [], []
    for skill in stock.skills:
        candidates = [
            s
            for s in pool
            if s.family == skill.family
            and s.source_problem.difficulty == skill.source_problem.difficulty
            and s.revision == skill.revision
            and s.id not in {x.id for x in chosen}
        ]
        size = len(ViewSkill.from_skill(skill).model_dump_json().encode())
        candidate = next(
            (
                s
                for s in sorted(candidates, key=lambda s: s.id)
                if 0.5 <= len(ViewSkill.from_skill(s).model_dump_json().encode()) / size <= 2
            ),
            None,
        )
        comparisons.append(
            {
                "training_skill": skill.id,
                "foreign_skill": candidate.id if candidate else None,
                "training_cognitive_bytes": size,
                "foreign_cognitive_bytes": len(
                    ViewSkill.from_skill(candidate).model_dump_json().encode()
                )
                if candidate
                else None,
            }
        )
        if candidate:
            chosen.append(candidate)
    snapshot = Snapshot(
        world=stock.world,
        arm=stock.arm,
        checkpoint=stock.checkpoint,
        skills=tuple(chosen),
        origin="irrelevant",
        matched_snapshot_digest=stock.digest,
    )
    return snapshot, {
        "matched": len(chosen) == len(stock.skills),
        "nonempty": bool(stock.skills),
        "comparisons": comparisons,
        "interpretation": "empty trained state has no identifying intervention"
        if not stock.skills
        else "real independently generated foreign procedures",
    }


def checker_settings(offers):
    return {
        o.id: [
            {"problem": p.model_dump(mode="json"), "expected": o.world.expected(p)} for p in o.cases
        ]
        for o in offers
    }
