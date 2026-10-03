"""New small difficulty ladder; private oracle and independent Decimal/Python checks.

This module is never imported by the proposer application. Contracts, seeds and
inputs are separate from the immutable 0.4.2 worlds. Oracle queries are controls.
"""

import random
from dataclasses import dataclass
from decimal import Decimal

from accumulation_primitives import Problem, Solution
from accumulation_tasks import table

from collective_intelligence_overlay.bindings import fingerprint

LEVELS = {
    "sql": ("S0", "S1", "S2", "S3"),
    "calibration": ("K0", "K1", "K2", "K3"),
    "composition": ("F0", "F1", "F2"),
}


@dataclass(frozen=True)
class World:
    seed: int
    stage: str

    @property
    def id(self):
        return "world-043-" + fingerprint([self.stage, self.seed])[:20]

    def rng(self, split):
        return random.Random(f"near-transfer-043/{self.stage}/{self.seed}/{split}")

    def coefficients(self, level):
        r = self.rng("latent/" + level)
        a, b = Decimal(r.choice((-7, -3, 2, 5))), Decimal(r.randint(2, 5))
        if level == "K0":
            return a, b, Decimal(0)
        if level == "K1":
            return a / 2, b / 2, Decimal(0)
        if level == "K2":
            return a, b, Decimal(r.choice((-1, 1, 2)))
        if level == "K3":
            return a / 2, b / 2, Decimal(r.choice((-1, 1, 2))) / 2
        return a, b, Decimal(0)

    def problem(self, family, level, split):
        if level not in LEVELS[family]:
            raise ValueError("unknown frozen difficulty")
        r = self.rng(split)
        base = dict(
            id="task-043-" + fingerprint([self.id, level, split])[:24],
            family=family,
            contract="near-043-" + level + "-" + self.id,
            revision="1",
            difficulty="middle",
            condition="formation" if family == "composition" else "near",
        )
        a, b, c = self.coefficients(level)
        if family == "calibration":
            observations = [(x, float(a + b * x + c * x * x)) for x in (-4, 0, 4, 8)]
            spec = "Infer the polynomial from exact observations; return reusable coefficients. "
            spec += (
                "The degree is at most one."
                if level in {"K0", "K1"}
                else "The degree is at most two."
            )
            if level == "K2":
                spec += f" The quadratic coefficient c2 is known to be {c}."
            return Problem(
                **base,
                specification=spec,
                observations=observations,
                values=[r.randint(-24, 32) / 4 for _ in range(12)],
            )
        rows = []
        for i in range(1, 19):
            group = "abc"[(i - 1) % 3]
            amount = (
                r.randint(1, 16)
                if family == "composition"
                else r.choice((-5, 0, 3, 11, 17) if level == "S0" else (None, -5, 0, 3, 11, 17))
            )
            rows.append([i, 1, group, r.randint(0, 30), amount])
            if level in {"S2", "S3"} and i % 3 == 0:
                rows.append([i, 2, group, r.randint(0, 30), r.choice((None, -2, 7, 19))])
        tables = {
            "readings": table(
                columns={
                    "event_id": "INTEGER",
                    "version": "INTEGER",
                    "bucket": "TEXT",
                    "utc": "INTEGER",
                    "amount": "REAL",
                },
                rows=rows,
            )
        }
        parameters = {"start": 5, "stop": 26}
        spec = "Keep rows with :start <= utc < :stop; timestamps are UTC integers. "
        if family == "sql":
            spec += "Sum amount per bucket; omit groups with no eligible rows. "
            if level != "S0":
                spec += "Exclude negative amounts and treat null amounts as zero. "
            if level in {"S2", "S3"}:
                spec = (
                    "First select the unique highest version for each event_id, "
                    "then apply filters. " + spec
                )
            if level == "S3":
                tables["groups"] = table(
                    columns={"bucket": "TEXT", "label": "TEXT", "enabled": "INTEGER"},
                    rows=[["a", "north", 1], ["b", "south", 1], ["c", "other", 0]],
                )
                spec += "Join groups one-to-one on bucket; keep enabled=1 and group by label."
            return Problem(**base, specification=spec, tables=tables, parameters=parameters)
        # A nonzero intercept and multiple records make SUM and calibration noncommutative.
        spec += "Query individual bucket/amount readings, without GROUP BY or aggregation. "
        if level == "F0":
            spec += f"The polynomial is y={a}+{b}*x. "
        else:
            spec += "Infer the affine polynomial from the exact observations. "
        reverse = self.rng("formation-order/" + level).choice((True, False))
        spec += (
            "Sum the raw readings per bucket, then calibrate each sum."
            if reverse
            else "Calibrate every reading, then sum calibrated readings per bucket."
        )
        if level == "F2":
            parameters["scale"] = 2
            spec += " Before calibration multiply each raw amount by :scale in SQL."
        return Problem(
            **base,
            specification=spec,
            tables=tables,
            parameters=parameters,
            observations=[(x, float(a + b * x)) for x in (-4, 0, 4)],
            component_contracts=("readonly-sql", "polynomial"),
        )

    def expected(self, problem):
        level = problem.contract.split("-")[2]
        a, b, c = self.coefficients(level)
        if problem.family == "calibration":
            return {
                "values": [
                    float(a + b * Decimal(str(x)) + c * Decimal(str(x)) ** 2)
                    for x in problem.values
                ]
            }
        rows = problem.tables["readings"].rows
        if level in {"S2", "S3"}:
            latest = {}
            for row in rows:
                if row[0] not in latest or row[1] > latest[row[0]][1]:
                    latest[row[0]] = row
            rows = list(latest.values())
        grouped = {}
        for _, _, bucket, utc, value in rows:
            if not problem.parameters["start"] <= utc < problem.parameters["stop"]:
                continue
            if problem.family == "sql" and level != "S0" and value is not None and value < 0:
                continue
            group = bucket
            if level == "S3":
                mapping = {r[0]: r[1] for r in problem.tables["groups"].rows if r[2] == 1}
                if bucket not in mapping:
                    continue
                group = mapping[bucket]
            grouped.setdefault(group, []).append(Decimal(str(value or 0)))
        result = []
        reverse = "then calibrate each sum" in problem.specification
        for group, values in sorted(grouped.items()):
            if problem.family == "composition":
                values = [v * int(problem.parameters.get("scale", 1)) for v in values]
                value = a + b * sum(values) if reverse else sum(a + b * v for v in values)
            else:
                value = sum(values)
            result.append({"group": group, "value": float(value)})
        return {"rows": result}

    def oracle(self, problem):
        level = problem.contract.split("-")[2]
        coefficients = tuple(float(x) for x in self.coefficients(level))
        if problem.family == "calibration":
            return Solution(family="calibration", coefficients=coefficients)
        prefix = ""
        source = "readings r"
        if level in {"S2", "S3"}:
            prefix = (
                "WITH latest AS (SELECT * FROM readings r WHERE version="
                "(SELECT MAX(version) FROM readings x WHERE x.event_id=r.event_id)) "
            )
            source = "latest r"
        group, value = "r.bucket", "r.amount"
        where = "r.utc>=:start AND r.utc<:stop"
        if problem.family == "sql":
            if level != "S0":
                value = "coalesce(r.amount,0)"
                where += " AND (r.amount IS NULL OR r.amount>=0)"
            if level == "S3":
                source += " JOIN groups g ON g.bucket=r.bucket AND g.enabled=1"
                group = "g.label"
            return Solution(
                family="sql",
                sql=prefix
                + f'SELECT {group} AS "group", SUM({value}) AS value '
                + f"FROM {source} WHERE {where} GROUP BY {group}",
            )
        if level == "F2":
            value += "*:scale"
        return Solution(
            family="composition",
            sql=f'SELECT {group} AS "group", {value} AS value FROM {source} WHERE {where}',
            coefficients=coefficients,
            reduction="sum",
            calibration_order="reduce-then-calibrate"
            if "then calibrate each sum" in problem.specification
            else "calibrate-then-reduce",
        )
