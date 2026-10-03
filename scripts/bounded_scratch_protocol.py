"""Prospective directional selection and finite, separately reported gates."""

import random

from accumulation_tasks import compare
from bounded_scratch_application import compile_slots, slot_candidates
from bounded_scratch_tasks import World, semantic_rule_baseline
from near_transfer_protocol import proportion
from scipy.stats import binomtest

FAMILIES = ("sql", "composition")
LEVELS = ("L0", "L1", "L2")


def boundary(record, observation=None, transcripts=()):
    """A semantic miss is distinct from a schema, transport or execution failure."""
    attempts = record.get("attempts", [])
    model = next((a for a in attempts if a.get("kind") == "model"), None)
    if model is None:
        return {"normal": False, "schema": False, "executable": False, "stage": 1}
    result = (model.get("response") or {}).get("result") or {}
    normal = bool(
        observation
        and observation.get("transport_dispatch_started") is True
        and observation.get("done") is True
        and observation.get("stream_complete") is True
        and observation.get("done_reason") == "stop"
        and observation.get("error_type") is None
        and observation.get("tokens_measured") is not None
    )
    schema = bool(model.get("solution"))
    checked = model.get("check") or {}
    # Check results retain actual invocation outputs; program_error is not meaning failure.
    executable = (
        schema
        and bool(checked)
        and bool(transcripts)
        and all(
            t["observed"].get("state") == "completed"
            and not (t["observed"].get("result") or {}).get("program_error")
            for t in transcripts
        )
    )
    error = result.get("error_type") or record.get("error_type")
    if error:
        executable = False
    stage = (
        1
        if not normal
        else 2
        if not schema
        else 4
        if not executable
        else 0
        if record["succeeded"]
        else 5
    )
    return {"normal": normal, "schema": schema, "executable": executable, "stage": stage}


def screen_decision(rows, current, visited):
    if len(rows) != 8 or any(
        not all(r[k] for k in ("normal", "schema", "executable")) for r in rows
    ):
        return {"selected": None, "next": None, "reason": "boundary_or_incomplete_stop"}
    k = sum(r["succeeded"] for r in rows)
    if 2 <= k <= 5:
        return {"selected": current, "next": None, "reason": "observed_middle_band"}
    step = -1 if k <= 1 else 1
    index = LEVELS.index(current) + step
    next_level = LEVELS[index] if 0 <= index < len(LEVELS) else None
    if next_level in visited:
        next_level = None
    return {
        "selected": None,
        "next": next_level,
        "reason": "floor_narrow_slots" if step < 0 else "ceiling_expand_slots",
    }


async def controls(family, level, seeds):
    """Independent control worlds, never inserted into any learned stock."""
    from accumulation_primitives import bounded_execute

    random_hits, constant_hits, rule_hits = [], None, []
    for seed in seeds:
        world = World(seed, "independent-control")
        problem = world.problem(family, level, "control")
        candidates = slot_candidates(family, problem.difficulty)
        hits = [
            compare(
                await bounded_execute(compile_slots(problem, c), problem), world.expected(problem)
            )
            for c in candidates
        ]
        if sum(hits) != 1:
            raise ValueError("functional candidate witnesses are ambiguous")
        constant_hits = (
            [int(h) for h in hits]
            if constant_hits is None
            else [a + int(b) for a, b in zip(constant_hits, hits, strict=True)]
        )
        selected = random.Random(f"044-control-uniform/{seed}/{family}/{level}").randrange(
            len(hits)
        )
        random_hits.append(hits[selected])
        rule_hits.append(
            compare(
                await bounded_execute(
                    compile_slots(problem, semantic_rule_baseline(problem)), problem
                ),
                world.expected(problem),
            )
        )
    n = len(seeds)
    return {
        "classification": "nonlearning_control_not_model_inference",
        "seeds": seeds,
        "functional_classes": 2 ** (int(level[-1]) + 1),
        "uniform_random": {"passed": sum(random_hits), "offered": n, "rate": sum(random_hits) / n},
        "best_constant": {
            "passed": max(constant_hits),
            "offered": n,
            "rate": max(constant_hits) / n,
        },
        "semantic_rule": {"passed": sum(rule_hits), "offered": n, "rate": sum(rule_hits) / n},
        "scope": "best constant chosen on independent control worlds; no learned or oracle stock",
    }


def locked_gate(rows, selected, control_results, *, g0=True, stock_ready=False):
    families = {}
    for family in FAMILIES:
        subset = [r for r in rows if r["family"] == family]
        report = proportion(subset)
        blocks = [proportion([r for r in subset if r["block"] == b]) for b in (0, 1)]
        interface = len(subset) == 12 and all(
            all(r[k] for k in ("normal", "schema", "executable")) for r in subset
        )
        quality = (
            report["offered"] == 12
            and 3 <= report["passed"] <= 8
            and all(b["offered"] == 6 and 0 < b["passed"] < 6 for b in blocks)
        )
        control = control_results.get(family, {})
        classes = control.get("functional_classes", 2)
        above_controls = (
            bool(subset)
            and classes >= 4
            and all(
                report["rate"] > control.get(k, {}).get("rate", 1)
                for k in ("uniform_random", "best_constant")
            )
        )
        report.update(
            level=selected.get(family),
            blocks=blocks,
            interface_ready=interface,
            observed_band_ready=quality,
            above_independent_controls=above_controls,
            uniform_chance_p_descriptive=binomtest(
                report["passed"], report["offered"], 1 / classes, alternative="greater"
            ).pvalue
            if subset
            else None,
            ready=interface and quality and above_controls,
        )
        families[family] = report
    assay = g0 and all(f["interface_ready"] and f["observed_band_ready"] for f in families.values())
    chance = assay and not all(f["above_independent_controls"] for f in families.values())
    ready = assay and not chance and stock_ready
    status = (
        "READY_FOR_COMPARISON"
        if ready
        else (
            "chance_dominated_or_unresolved"
            if chance
            else "intervention_unavailable"
            if assay and not stock_ready
            else "assay_not_ready"
        )
    )
    return {
        "status": status,
        "families": families,
        "G0": g0,
        "G3": stock_ready,
        "confirmation_authorized": ready,
        "confirmation_started": False,
        "true_probability_20_70_proved": False,
        "inference_scope": "descriptive pilot; broad intervals, no significant intelligence claim",
    }
