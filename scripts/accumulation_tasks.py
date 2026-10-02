"""Private-to-proposers synthetic world generator and independent task comparator.

Only this trusted runner/verifier module has world seeds, reference queries and
expected results. The application imports primitives/stock, never this module.
Reference queries are positive calibration controls, not initial main-arm skills.
"""

import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from accumulation_primitives import Problem, Solution, Table

from collective_intelligence_overlay.bindings import fingerprint

LEVELS = ("low", "middle", "high")


def table(*, columns, rows):
    return Table(columns=columns, column_order=tuple(columns), rows=rows)


@dataclass(frozen=True)
class World:
    seed: int

    @property
    def id(self):
        return "world-" + fingerprint(["accumulation-v1", self.seed])[:20]

    def rng(self, split):
        return random.Random(f"accumulation-v1/{self.seed}/{split}")

    def coefficients(self, difficulty, revision="1"):
        r = self.rng("latent-calibration/" + difficulty + "/" + revision)
        if difficulty == "low":
            return (Decimal(r.randint(-8, 8)), Decimal(r.randint(2, 7)), Decimal(0))
        if difficulty == "middle":
            return (
                Decimal(r.randint(-17, 19)) / 10,
                Decimal(r.randint(11, 37)) / 10,
                Decimal(r.randint(-8, 8)) / 20,
            )
        return (
            Decimal(r.randint(-51, 51)) / 13,
            Decimal(r.randint(11, 37)) / 7,
            Decimal(r.randint(2, 5)) / 97,
        )

    def y(self, x, difficulty, revision="1"):
        a, b, c = self.coefficients(difficulty, revision)
        value = Decimal(str(x))
        return float(a + b * value + c * value * value)

    def calibration(self, split, difficulty, *, condition="near", revision="1"):
        r = self.rng(split)
        values = [round(r.uniform(-9, 12), 4) for _ in range(12)]
        observations = [(x, self.y(x, difficulty, revision)) for x in (-4, 0, 7, 10)]
        return Problem(
            id="task-" + fingerprint([self.id, split, "calibration"])[:24],
            family="calibration",
            contract="sensor-" + difficulty,
            revision=revision,
            difficulty=difficulty,
            condition=condition,
            specification=(
                (
                    "An instrument has a noiseless affine response. "
                    "Its quadratic coefficient is zero. "
                    if difficulty == "low"
                    else "An instrument has a noiseless response of degree at most two. "
                )
                + "Infer "
                "the reusable polynomial from the four public (x,y) observations. "
                "Return calibrated values in input order on fresh inputs. Coefficients "
                "may be fractional; absolute tolerance 1e-5 plus relative tolerance 1e-5. "
                "Do not interpolate by a table lookup or hardcode current output values."
            ),
            values=values,
            observations=observations,
        )

    def names(self, revision="1"):
        tag = self.rng("schema/" + revision).choice(("a", "b", "c", "d", "e"))
        return {
            name: name + "_" + tag
            for name in ("oid", "cid", "state", "stamp", "seq", "sku", "amount", "unit")
        }

    def sales(self, split, difficulty, *, condition="near", revision="1", reduction="sum"):
        r, names = self.rng(split), self.names(revision)
        latent = self.rng("latent-sales/" + revision)
        accepted = latent.choice(("settled", "ok", "final", "cleared"))
        offset = latent.choice((-9, -5, 1, 8, 9)) * 3600
        cutoff, start = 1700000000, 1700000000 - 7200
        orders, lines = [], []
        regions = ["north", "south", "east"]
        for oid in range(1, 17):
            cid = r.randint(1, 6)
            for seq in (1, 2):
                stamp = cutoff + r.choice((-8000, -4000, -100, 1000))
                local = datetime.fromtimestamp(stamp + offset, UTC).strftime("%Y-%m-%d %H:%M:%S")
                state = accepted if r.random() < 0.72 else "void"
                if seq == 2 and oid <= 4:
                    # Pre-outcome generator invariant: every form has positive
                    # occupancy in several groups, rather than a vacuous [] PASS.
                    cid, state = oid, accepted
                    stamp = cutoff - 4000 + oid * 100
                    local = datetime.fromtimestamp(stamp + offset, UTC).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                row = [oid, cid, state, local, seq]
                if difficulty == "low":
                    row += [None if r.random() < 0.12 else r.randint(-30, 90) / 10, "u"]
                    if seq == 2 and oid <= 4:
                        row[-2] = oid / 2
                orders.append(row)
            if difficulty != "low":
                for sku in ("p", "q"):
                    for seq in (1, 2):
                        lines.append(
                            [
                                oid,
                                sku,
                                None if r.random() < 0.1 else r.randint(-30, 90) / 10,
                                r.choice(("u", "milli", "unknown")),
                                seq,
                            ]
                        )
                        if seq == 2 and oid <= 4:
                            lines[-1][2:4] = [oid / 2, "u"]
        order_columns = {
            names["oid"]: "INTEGER",
            names["cid"]: "INTEGER",
            names["state"]: "TEXT",
            names["stamp"]: "TEXT",
            names["seq"]: "INTEGER",
        }
        if difficulty == "low":
            order_columns.update({names["amount"]: "REAL", names["unit"]: "TEXT"})
        tables = {"orders": table(columns=order_columns, rows=orders)}
        if difficulty != "low":
            tables.update(
                {
                    "items": table(
                        columns={
                            names["oid"]: "INTEGER",
                            names["sku"]: "TEXT",
                            names["amount"]: "REAL",
                            names["unit"]: "TEXT",
                            names["seq"]: "INTEGER",
                        },
                        rows=lines,
                    ),
                    "customers": table(
                        columns={names["cid"]: "INTEGER", "region": "TEXT", "enabled": "INTEGER"},
                        rows=[[cid, regions[(cid - 1) % 3], int(cid != 6)] for cid in range(1, 7)],
                    ),
                    "conversions": table(
                        columns={
                            names["unit"]: "TEXT",
                            "factor": "REAL",
                            "from_utc": "INTEGER",
                            "to_utc": "INTEGER",
                            "seq": "INTEGER",
                        },
                        rows=[
                            ["u", 1, 0, None, 1],
                            ["milli", 0.001, 0, None, 1],
                            ["milli", 0.002, cutoff - 1500, None, 2],
                        ],
                    ),
                }
            )
        if difficulty == "high":
            tables["rebates"] = table(
                columns={
                    names["cid"]: "INTEGER",
                    "rate": "REAL",
                    "active": "INTEGER",
                    names["seq"]: "INTEGER",
                },
                rows=[[cid, 0.1, 1, 1] for cid in range(1, 5)] + [[1, 0.2, 1, 2], [2, 0.7, 0, 3]],
            )
        spec = (
            f"Business sales contract ({difficulty}). Column meanings: {names}. "
            "Deduplicate orders by order id using greatest seq BEFORE filtering. "
            "Interpret stamp as local ISO wall time; UTC epoch seconds equal "
            "strftime('%s',stamp) minus parameter offset. Keep latest orders only "
            "when state equals :accepted and start <= UTC < cutoff. Ignore null amounts, "
            "retain negative refunds. "
        )
        if difficulty == "low":
            spec += "Group by textual customer id and use orders.amount in base units. "
        else:
            spec += (
                "Deduplicate items by (order id,sku) using greatest seq before filtering. "
                "Join latest items to latest eligible orders and enabled customers; group "
                "by region. Join unit conversions valid at order UTC: from_utc <= UTC and "
                "(to_utc is null or UTC < to_utc); if multiple valid rows use greatest "
                "conversion seq. Exclude unknown units. Each amount times factor is its "
                "base-unit contribution. Do not multiply rows through obsolete versions. "
            )
        if difficulty == "high":
            spec += (
                "Apply customer rebate: greatest seq among active=1 rows; absent rebate "
                "means zero. Contribution is amount*factor*(1-rate). "
            )
        spec += (
            f"Reduce eligible contributions by {reduction} for each nonempty group. "
            "Output exactly group,value. Use query parameters; write a general query, "
            "not a SELECT of literal current answers. Absolute/relative tolerance 1e-5."
        )
        return Problem(
            id="task-" + fingerprint([self.id, split, difficulty, revision, reduction])[:24],
            family="sql",
            contract=f"sales-{difficulty}-{reduction}",
            revision=revision,
            difficulty=difficulty,
            condition=condition,
            specification=spec,
            tables=tables,
            parameters={"accepted": accepted, "offset": offset, "start": start, "cutoff": cutoff},
            component_contracts=(f"sales-{difficulty}-sum",) if reduction != "sum" else (),
        )

    def composition(self, split):
        sales = self.sales(split, "middle")
        tables = {k: v for k, v in sales.tables.items() if k in {"orders", "customers"}}
        oid = self.names()["oid"]
        r = self.rng(split + "/readings")
        tables["readings"] = table(
            columns={oid: "INTEGER", "raw": "REAL", "seq": "INTEGER"},
            rows=[[i, round(r.uniform(-7, 11), 4), seq] for i in range(1, 17) for seq in (1, 2)],
        )
        return Problem(
            id="task-" + fingerprint([self.id, split, "new-connector"])[:24],
            family="composition",
            contract="calibrated-regional-readings-mean",
            revision="1",
            difficulty="high",
            condition="formation",
            tables=tables,
            parameters=sales.parameters,
            component_contracts=("sales-middle-sum", "sensor-middle"),
            observations=self.calibration(split, "middle").observations,
            specification=(
                "NEW connector/contract, not a sales total or a renamed calibrator. "
                f"Order column meanings: {self.names()}. Deduplicate orders by greatest "
                "seq per order id BEFORE filtering. UTC equals strftime('%s',stamp) "
                "minus :offset. Keep :accepted orders with :start <= UTC < :cutoff, "
                "join enabled customers and latest readings by greatest readings.seq "
                "per order id. SQL must return individual (region as group,raw as value) "
                "readings. Infer the degree-at-most-two sensor-middle calibration from "
                "the public observations. Produce each region's mean calibrated reading, "
                "rather than a calibration of a regional summary. Select the order of the "
                "numerical and aggregation operators. Return a combined SQL+polynomial callable."
            ),
        )

    def expected(self, problem):
        if problem.family == "calibration":
            return {
                "values": [self.y(x, problem.difficulty, problem.revision) for x in problem.values]
            }
        if problem.family == "composition":
            return self.expected_composition(problem)
        names, p = self.names(problem.revision), problem.parameters
        convert = lambda row, table: dict(zip(table.column_order, row, strict=True))  # noqa: E731
        order_rows = [
            convert(row, problem.tables["orders"]) for row in problem.tables["orders"].rows
        ]
        latest = {}
        for row in order_rows:
            if (
                row[names["oid"]] not in latest
                or row[names["seq"]] > latest[row[names["oid"]]][names["seq"]]
            ):
                latest[row[names["oid"]]] = row
        customers = (
            {row[0]: row[1:] for row in problem.tables["customers"].rows}
            if "customers" in problem.tables
            else {}
        )
        items = {}
        if "items" in problem.tables:
            for raw in problem.tables["items"].rows:
                row = convert(raw, problem.tables["items"])
                key = row[names["oid"]], row[names["sku"]]
                if key not in items or row[names["seq"]] > items[key][names["seq"]]:
                    items[key] = row
        grouped = {}
        for order in latest.values():
            epoch = (
                datetime.strptime(order[names["stamp"]], "%Y-%m-%d %H:%M:%S")
                .replace(tzinfo=UTC)
                .timestamp()
                - p["offset"]
            )
            if order[names["state"]] != p["accepted"] or not p["start"] <= epoch < p["cutoff"]:
                continue
            cid = order[names["cid"]]
            if problem.difficulty != "low" and not customers[cid][1]:
                continue
            group = str(cid) if problem.difficulty == "low" else customers[cid][0]
            rows = (
                [order]
                if problem.difficulty == "low"
                else [v for v in items.values() if v[names["oid"]] == order[names["oid"]]]
            )
            for row in rows:
                if row[names["amount"]] is None:
                    continue
                factor = 1
                if problem.difficulty != "low":
                    matches = [
                        c
                        for c in problem.tables["conversions"].rows
                        if c[0] == row[names["unit"]]
                        and c[2] <= epoch
                        and (c[3] is None or epoch < c[3])
                    ]
                    if not matches:
                        continue
                    factor = max(matches, key=lambda c: c[4])[1]
                rate = 0
                if problem.difficulty == "high":
                    matches = [
                        v for v in problem.tables["rebates"].rows if v[0] == cid and v[2] == 1
                    ]
                    rate = max(matches, key=lambda v: v[3])[1] if matches else 0
                grouped.setdefault(group, []).append(
                    float(
                        Decimal(str(row[names["amount"]]))
                        * Decimal(str(factor))
                        * (1 - Decimal(str(rate)))
                    )
                )
        reduction = problem.contract.rsplit("-", 1)[-1]
        return {
            "rows": [
                {
                    "group": group,
                    "value": len(v)
                    if reduction == "count"
                    else sum(v) / (len(v) if reduction == "mean" else 1),
                }
                for group, v in sorted(grouped.items())
            ]
        }

    def expected_composition(self, problem):
        names, p = self.names(), problem.parameters
        orders = {}
        for row in problem.tables["orders"].rows:
            if row[0] not in orders or row[4] > orders[row[0]][4]:
                orders[row[0]] = row
        readings = {}
        for row in problem.tables["readings"].rows:
            if row[0] not in readings or row[2] > readings[row[0]][2]:
                readings[row[0]] = row
        customers = {row[0]: row for row in problem.tables["customers"].rows}
        grouped = {}
        for oid, row in orders.items():
            epoch = datetime.strptime(row[3], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).timestamp()
            epoch -= p["offset"]
            customer = customers[row[1]]
            if row[2] == p["accepted"] and p["start"] <= epoch < p["cutoff"] and customer[2]:
                grouped.setdefault(customer[1], []).append(self.y(readings[oid][1], "middle"))
        # The independent comparator operates directly on original fixture rows.
        # It never calls the SQL, MAF workflow or candidate calibrator.
        assert names["oid"] in problem.tables["orders"].columns
        return {
            "rows": [{"group": k, "value": sum(v) / len(v)} for k, v in sorted(grouped.items())]
        }

    def oracle(self, problem):
        """Positive calibration control only. Never provided to model/main stock."""
        if problem.family == "calibration":
            return Solution(
                family="calibration",
                coefficients=tuple(
                    float(c) for c in self.coefficients(problem.difficulty, problem.revision)
                ),
            )
        n = self.names(problem.revision)
        oid, cid, state, stamp, seq, sku, amount, unit = (
            n[k] for k in ("oid", "cid", "state", "stamp", "seq", "sku", "amount", "unit")
        )
        base = (
            f"WITH latest AS (SELECT *,row_number() OVER(PARTITION BY {oid} "
            f"ORDER BY {seq} DESC) AS rn FROM orders), eligible AS (SELECT *,"
            f"CAST(strftime('%s',{stamp}) AS INTEGER)-:offset AS utc "
            "FROM latest WHERE rn=1) "
        )
        where = f"o.{state}=:accepted AND o.utc>=:start AND o.utc<:cutoff"
        if problem.family == "composition":
            query = (
                base.rstrip()
                + f", readings_latest AS (SELECT *,row_number() OVER(PARTITION BY {oid} "
                "ORDER BY seq DESC) AS rn FROM readings) "
                'SELECT c.region AS "group",r.raw AS value FROM eligible o '
                f"JOIN customers c ON c.{cid}=o.{cid} AND c.enabled=1 "
                f"JOIN readings_latest r ON r.{oid}=o.{oid} AND r.rn=1 WHERE {where}"
            )
            return Solution(
                family="composition",
                sql=query,
                reduction="mean",
                calibration_order="calibrate-then-reduce",
                coefficients=tuple(float(c) for c in self.coefficients("middle")),
            )
        reduction = problem.contract.rsplit("-", 1)[-1]
        function = {"sum": "SUM", "mean": "AVG", "count": "COUNT"}[reduction]
        if problem.difficulty == "low":
            query = (
                base + f'SELECT CAST(o.{cid} AS TEXT) AS "group",{function}(o.{amount}) AS value '
                f"FROM eligible o WHERE {where} AND o.{amount} IS NOT NULL GROUP BY o.{cid}"
            )
        else:
            base = (
                base.rstrip() + f", li AS (SELECT *,row_number() OVER(PARTITION BY {oid},{sku} "
                f"ORDER BY {seq} DESC) AS irn FROM items) "
            )
            value = f"i.{amount}*v.factor"
            rebate_join = ""
            if problem.difficulty == "high":
                value += "*(1-coalesce(b.rate,0))"
                rebate_join = (
                    f" LEFT JOIN rebates b ON b.{cid}=o.{cid} AND b.active=1 "
                    f"AND b.{seq}=(SELECT MAX(x.{seq}) FROM rebates x "
                    f"WHERE x.{cid}=o.{cid} AND x.active=1) "
                )
            query = (
                base + f'SELECT c.region AS "group",{function}({value}) AS value FROM eligible o '
                f"JOIN li i ON i.{oid}=o.{oid} AND i.irn=1 JOIN customers c "
                f"ON c.{cid}=o.{cid} AND c.enabled=1 JOIN conversions v "
                f"ON v.{unit}=i.{unit} AND v.from_utc<=o.utc "
                "AND (v.to_utc IS NULL OR o.utc<v.to_utc) "
                f"AND v.seq=(SELECT MAX(x.seq) FROM conversions x WHERE x.{unit}=i.{unit} "
                "AND x.from_utc<=o.utc AND (x.to_utc IS NULL OR o.utc<x.to_utc)) "
                f"{rebate_join} WHERE {where} AND i.{amount} IS NOT NULL GROUP BY c.region"
            )
        return Solution(family="sql", sql=query, reduction=reduction)


def compare(actual, expected):
    """Exact shape/group/multiplicity with declared finite numerical tolerance."""
    if not isinstance(actual, dict) or set(actual) != set(expected):
        return False
    if "values" in expected:
        a, b = actual["values"], expected["values"]
        return (
            isinstance(a, list)
            and len(a) == len(b)
            and all(close(x, y) for x, y in zip(a, b, strict=True))
        )
    rows = actual.get("rows")
    if not isinstance(rows, list) or any(
        not isinstance(r, dict) or set(r) != {"group", "value"} or not isinstance(r["group"], str)
        for r in rows
    ):
        return False
    a, b = sorted(rows, key=lambda r: r["group"]), expected["rows"]
    return len(a) == len(b) and all(
        x["group"] == y["group"] and close(x["value"], y["value"])
        for x, y in zip(a, b, strict=True)
    )


def close(actual, expected):
    return (
        isinstance(actual, int | float)
        and not isinstance(actual, bool)
        and math.isfinite(actual)
        and abs(actual - expected) <= 1e-5 + 1e-5 * abs(expected)
    )
