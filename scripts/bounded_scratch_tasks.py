"""Private finite laws and independent Python/Decimal oracle for slot procedures.

The proposer never imports this module. Every form contains predeclared witnesses;
all functional candidates differ without injecting failures or changing cases.
"""

import random
from dataclasses import dataclass
from decimal import Decimal

from accumulation_primitives import Problem
from accumulation_tasks import table
from bounded_scratch_application import FIXED, compile_slots, slot_names

from collective_intelligence_overlay.bindings import fingerprint

LEVELS = {"L0": "low", "L1": "middle", "L2": "high"}


@dataclass(frozen=True)
class World:
    seed: int
    stage: str

    @property
    def id(self):
        return "world-044-" + fingerprint(["bounded-scratch-v1", self.stage, self.seed])[:20]

    def rng(self, split):
        return random.Random(f"bounded-scratch-044/{self.stage}/{self.seed}/{split}")

    def slots(self, family, level):
        r = self.rng("law/" + family + "/" + level)
        all_values = {
            "sql": {
                "negative_policy": r.choice(("include", "exclude")),
                "null_policy": r.choice(("zero", "drop")),
                "boundary": r.choice(("closed", "half_open")),
            },
            "composition": {
                "order": r.choice(("transform_then_reduce", "reduce_then_transform")),
                "input_field": r.choice(("net", "gross")),
                "scale_choice": r.choice(("unit", "double")),
            },
        }[family]
        selected = {n: all_values[n] for n in slot_names(family, LEVELS[level])}
        return {**FIXED[family], **selected}

    def problem(self, family, level, split):
        difficulty = LEVELS[level]
        selected, r = self.slots(family, level), self.rng(family + "/" + level + "/" + split)
        parameters = {"start": 5, "stop": 25}
        if family == "sql":
            # Null-only, negative, duplicate, exact-start/stop and outside witnesses.
            # Both wrong and right candidates remain nonvacuous and syntactically valid.
            rows = [
                [1, "a", 8, -7],
                [2, "a", 10, 11],
                [3, "a", 10, 11],
                [4, "null_only", 12, None],
                [5, "edge", 25, 19],
                [6, "start", 5, 13],
                [7, "outside", 4, 17],
                [8, "outside", 26, 23],
            ]
            rows += [[i, "b", r.randint(6, 24), r.randint(2, 18)] for i in range(9, 19)]
            clauses = [
                "Sum readings by bucket, counting duplicate rows separately; "
                "omit a bucket with no eligible rows."
            ]
            clauses += [
                "Negative amounts are signed credits and remain in the total."
                if selected["negative_policy"] == "include"
                else "Amounts below zero are ineligible and must be discarded."
            ]
            clauses += [
                "A null row contributes zero and its bucket remains, "
                "even if all its eligible amounts are null."
                if selected["null_policy"] == "zero"
                else "Null amounts are discarded; "
                "a bucket with only null eligible amounts is absent."
            ]
            clauses += [
                "The UTC window includes both start and stop."
                if selected["boundary"] == "closed"
                else "The UTC window includes start and excludes stop."
            ]
            columns = {"event_id": "INTEGER", "bucket": "TEXT", "utc": "INTEGER", "amount": "REAL"}
        else:
            law = self.rng("public-affine/" + level)
            parameters.update(
                offset=law.randint(3, 7), slope=law.randint(2, 4), unit_scale=1, double_scale=2
            )
            rows = [
                [
                    i,
                    "a" if i <= 9 else "b",
                    6 + (i % 18),
                    20 + r.randint(0, 15),
                    120 + r.randint(0, 15),
                ]
                for i in range(1, 19)
            ]
            # At least two rows per bucket, nonzero intercept and separated fields
            # make all 2/4/8 allowed candidates functionally distinct on every form.
            columns = {
                "event_id": "INTEGER",
                "bucket": "TEXT",
                "utc": "INTEGER",
                "net": "REAL",
                "gross": "REAL",
            }
            clauses = [
                "Use the installed extraction, public affine transformation and sum primitives. "
                "Keep start <= utc < stop, count duplicate rows, and group by bucket."
            ]
            clauses += [
                "Apply the affine instrument separately to each reading "
                "before the bucket total is settled."
                if selected["order"] == "transform_then_reduce"
                else "Settle the bucket total of raw readings first, then apply the affine "
                "instrument once to that total."
            ]
            clauses += [
                "Use the base charge stored in net, excluding the all-inclusive gross charge."
                if selected["input_field"] == "net"
                else "Use the all-inclusive charge stored in gross, including additions to net."
            ]
            clauses += [
                "Raw charges enter at their original scale."
                if selected["scale_choice"] == "unit"
                else "Double every raw charge before any affine or sum operation."
            ]
            clauses += [
                f"The public instrument is y={parameters['offset']}+{parameters['slope']}*x; "
                "the reducer is sum."
            ]
        specification = " ".join(clauses)
        if split.endswith("/independent") or split == "hidden":
            # Heldout forms include fresh group names and a disjoint value range.
            # Retain every preregistered null/negative/boundary witness.
            for row in rows:
                row[1] = "heldout_" + row[1]
                for i in range(3, len(row)):
                    if row[i] is not None:
                        row[i] *= 3
        return Problem(
            id="task-044-" + fingerprint([self.id, family, level, split])[:24],
            family=family,
            contract=f"bounded044-{family}-{level}-{self.id}",
            revision="1",
            difficulty=difficulty,
            condition="formation" if family == "composition" else "near",
            specification=specification,
            tables={"readings": table(columns=columns, rows=rows)},
            parameters=parameters,
            component_contracts=(f"bounded044-composition-L{int(level[-1]) - 1}-{self.id}",)
            if family == "composition" and level != "L0"
            else (),
        )

    def expected(self, problem):
        family = problem.family
        level = problem.contract.split("-")[2]
        slots = self.slots(family, level)
        groups = {}
        for row in problem.tables["readings"].rows:
            _, bucket, utc, *values = row
            inside = problem.parameters["start"] <= utc and (
                utc <= problem.parameters["stop"]
                if slots.get("boundary") == "closed"
                else utc < problem.parameters["stop"]
            )
            if not inside:
                continue
            if family == "sql":
                value = values[0]
                if value is None and slots["null_policy"] == "drop":
                    continue
                if value is not None and value < 0 and slots["negative_policy"] == "exclude":
                    continue
                numeric = Decimal(str(value if value is not None else 0))
            else:
                numeric = Decimal(str(values[0 if slots["input_field"] == "net" else 1]))
                if slots["scale_choice"] == "double":
                    numeric *= 2
            groups.setdefault(bucket, []).append(numeric)
        output = []
        for group, values in sorted(groups.items()):
            if family == "sql":
                value = sum(values)
            else:
                a, b = (
                    Decimal(str(problem.parameters["offset"])),
                    Decimal(str(problem.parameters["slope"])),
                )
                value = (
                    sum(a + b * x for x in values)
                    if slots["order"] == "transform_then_reduce"
                    else a + b * sum(values)
                )
            output.append({"group": group, "value": float(value)})
        return {"rows": output}

    def oracle(self, problem):
        level = problem.contract.split("-")[2]
        values = {
            n: self.slots(problem.family, level)[n]
            for n in slot_names(problem.family, problem.difficulty)
        }
        return compile_slots(problem, values)


def semantic_rule_baseline(problem):
    """Nonlearning public-text automation baseline, never reads world/expected data."""
    text = problem.specification
    all_values = {
        "negative_policy": "include" if "signed credits" in text else "exclude",
        "null_policy": "zero" if "contributes zero" in text else "drop",
        "boundary": "closed" if "includes both start and stop" in text else "half_open",
        "order": "transform_then_reduce"
        if "separately to each reading" in text
        else "reduce_then_transform",
        "input_field": "net" if "base charge stored in net" in text else "gross",
        "scale_choice": "double" if "Double every raw charge" in text else "unit",
    }
    return {n: all_values[n] for n in slot_names(problem.family, problem.difficulty)}
