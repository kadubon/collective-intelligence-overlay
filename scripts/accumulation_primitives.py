"""Source-only synthetic study primitives. No task answers or world generator.

Untrusted SQL uses SQLite's compiled authorizer and resource limits over bounded
in-memory fixtures. Plans are reconstruction data for installed code, never Python,
shell, imports, a replacement executor, or a new query language.
"""

import asyncio
import json
import math
import re
import sqlite3
import time
from contextlib import closing
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from collective_intelligence_overlay.bindings import fingerprint

ENVIRONMENT = {"application": "accumulation-v1", "primitive_contract": "3"}
IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,47}\Z")


class Table(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    columns: dict[str, Literal["TEXT", "REAL", "INTEGER"]] = Field(min_length=1, max_length=12)
    column_order: tuple[str, ...] = Field(min_length=1, max_length=12)
    rows: list[list[JsonValue]] = Field(max_length=256)

    @model_validator(mode="after")
    def bounded_fixture(self):
        if any(not IDENTIFIER.fullmatch(c) for c in self.columns):
            raise ValueError("invalid column identifier")
        if len(set(self.column_order)) != len(self.column_order) or set(self.column_order) != set(
            self.columns
        ):
            raise ValueError("explicit column order must identify every column exactly once")
        if any(len(r) != len(self.columns) for r in self.rows):
            raise ValueError("fixture row width changed")
        if any(isinstance(x, dict | list) for r in self.rows for x in r):
            raise ValueError("fixture cells must be scalar")
        if any(isinstance(x, float) and not math.isfinite(x) for r in self.rows for x in r):
            raise ValueError("fixture cells must be finite")
        if len(self.model_dump_json().encode()) > 65536:
            raise ValueError("fixture table exceeds byte bound")
        return self


class Problem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(max_length=96)
    family: Literal["sql", "calibration", "composition"]
    contract: str = Field(max_length=96)
    revision: str = Field(max_length=16)
    difficulty: Literal["low", "middle", "high"]
    condition: Literal["near", "unseen", "drift", "negative", "formation"]
    specification: str = Field(max_length=6000)
    tables: dict[str, Table] = Field(default_factory=dict, max_length=6)
    parameters: dict[str, JsonValue] = Field(default_factory=dict, max_length=12)
    values: list[float] = Field(default_factory=list, max_length=128)
    observations: list[tuple[float, float]] = Field(default_factory=list, max_length=8)
    component_contracts: tuple[str, ...] = Field(default=(), max_length=2)

    @model_validator(mode="after")
    def bounded_problem(self):
        if any(not IDENTIFIER.fullmatch(t) for t in self.tables):
            raise ValueError("invalid table identifier")
        if len(self.model_dump_json().encode()) > 131072:
            raise ValueError("problem byte bound exceeded")
        if any(not math.isfinite(v) for v in self.values):
            raise ValueError("non-finite input")
        if any(not math.isfinite(v) for pair in self.observations for v in pair):
            raise ValueError("non-finite observation")
        return self

    @property
    def schema_digest(self):
        return fingerprint(
            {
                name: {"columns": table.columns, "column_order": table.column_order}
                for name, table in self.tables.items()
            }
        )


class Solution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    family: Literal["sql", "calibration", "composition"]
    sql: str = Field(default="", max_length=12000)
    coefficients: tuple[float, float, float] = (0, 1, 0)
    reduction: Literal["sum", "mean", "count"] = "sum"
    calibration_order: (
        Literal["calibrate-then-reduce", "reduce-then-calibrate", "not-applicable"] | None
    ) = Field(default=None, exclude_if=lambda value: value is None)
    uses: tuple[str, ...] = Field(default=(), max_length=3)
    explanation: str = Field(default="", max_length=1400)

    @model_validator(mode="after")
    def callable_parameters(self):
        if self.family in {"sql", "composition"} and not self.sql.strip():
            raise ValueError("query is required")
        if self.family == "calibration" and self.sql:
            raise ValueError("calibration has no query")
        if any(not math.isfinite(c) or abs(c) > 10**6 for c in self.coefficients):
            raise ValueError("finite coefficient bound exceeded")
        return self


FUNCTIONS = frozenset(
    {
        "sum",
        "avg",
        "count",
        "max",
        "min",
        "round",
        "coalesce",
        "nullif",
        "abs",
        "lower",
        "upper",
        "trim",
        "substr",
        "length",
        "cast",
        "strftime",
        "datetime",
        "date",
        "julianday",
        "unixepoch",
        "row_number",
        "rank",
        "dense_rank",
    }
)


def readonly_sql(query: str, problem: Problem, *, maximum_steps=200000, seconds=2):
    """Compile and run exactly one SELECT against only the declared fixture tables."""
    if len(query.encode()) > 12000 or "\x00" in query:
        raise ValueError("query byte bound exceeded")
    with closing(sqlite3.connect(":memory:")) as connection:
        if disable_extensions := getattr(connection, "enable_load_extension", None):
            disable_extensions(False)
        connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 12000)
        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 65536)
        connection.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 32)
        connection.setlimit(sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 64)
        connection.setlimit(sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 8)
        connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 32)
        for name, table in problem.tables.items():
            columns = ",".join(f'"{c}" {table.columns[c]}' for c in table.column_order)
            connection.execute(f'CREATE TABLE "{name}" ({columns})')
            placeholders = ",".join("?" for _ in table.columns)
            connection.executemany(f'INSERT INTO "{name}" VALUES ({placeholders})', table.rows)
        connection.execute("PRAGMA query_only=ON")
        connection.commit()

        def authorize(action, first, second, database, source):
            if action == sqlite3.SQLITE_SELECT:
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_READ and (
                database == "main" or (database is None and second == "")
            ):
                table = problem.tables.get(first)
                if table and (second in table.columns or second == ""):
                    return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_FUNCTION and (second or "").lower() in FUNCTIONS:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY

        ticks, started = 0, time.perf_counter()

        def progress():
            nonlocal ticks
            ticks += 100
            return int(ticks > maximum_steps or time.perf_counter() - started > seconds)

        connection.set_authorizer(authorize)
        connection.set_progress_handler(progress, 100)
        cursor = connection.execute(query, problem.parameters)
        if cursor.description is None:
            raise ValueError("query returned no columns")
        names = [d[0] for d in cursor.description]
        if names != ["group", "value"]:
            raise ValueError("query must return exactly group,value in that order")
        rows = cursor.fetchmany(257)
        if len(rows) > 256:
            raise ValueError("query row bound exceeded")
        output = []
        for group, value in rows:
            if not isinstance(group, str) or len(group) > 128:
                raise ValueError("bounded text group required")
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueError("finite numeric value required")
            if not math.isfinite(value) or abs(value) > 10**12:
                raise ValueError("query value magnitude bound exceeded")
            output.append({"group": group, "value": float(value)})
        if len(json.dumps(output).encode()) > 32768:
            raise ValueError("query output byte bound exceeded")
        return output


def calibrate(values, coefficients):
    c0, c1, c2 = coefficients
    result = [c0 + c1 * x + c2 * x * x for x in values]
    if any(not math.isfinite(x) or abs(x) > 10**12 for x in result):
        raise ValueError("calibrated value bound exceeded")
    return result


async def execute_solution(solution: Solution, problem: Problem):
    if solution.family != problem.family:
        raise ValueError("wrong callable family")
    if solution.family == "calibration":
        return {"values": calibrate(problem.values, solution.coefficients)}
    if solution.family == "sql":
        return {"rows": readonly_sql(solution.sql, problem)}
    # A genuine cross-family composition uses the installed MAF public workflow.
    # It reconstructs only the current plan; it retains no provider or old closure.
    from agent_framework import WorkflowBuilder, WorkflowContext, executor

    @executor(id="sql")
    async def query(data: dict, ctx: WorkflowContext[dict]):
        await ctx.send_message({"rows": readonly_sql(solution.sql, problem)})

    reverse = solution.calibration_order == "reduce-then-calibrate"
    if solution.calibration_order not in {"calibrate-then-reduce", "reduce-then-calibrate"}:
        raise ValueError("composition requires an explicit model-selected operator order")

    @executor(id="calibration")
    async def numerical(data: dict, ctx: WorkflowContext[dict]):
        rows = data["rows"]
        values = calibrate([r["value"] for r in rows], solution.coefficients)
        transformed = {
            "rows": [{"group": r["group"], "value": v} for r, v in zip(rows, values, strict=True)]
        }
        if reverse:
            await ctx.yield_output(transformed)
        else:
            await ctx.send_message(transformed)

    @executor(id="reduce")
    async def reduce(data: dict, ctx: WorkflowContext[dict, dict]):
        grouped = {}
        for row in data["rows"]:
            grouped.setdefault(row["group"], []).append(row["value"])
        rows = []
        for group, values in sorted(grouped.items()):
            value = len(values) if solution.reduction == "count" else sum(values)
            if solution.reduction == "mean":
                value /= len(values)
            rows.append({"group": group, "value": value})
        if reverse:
            await ctx.send_message({"rows": rows})
        else:
            await ctx.yield_output({"rows": rows})

    first, second = (reduce, numerical) if reverse else (numerical, reduce)
    workflow = (
        WorkflowBuilder(start_executor=query, max_iterations=4)
        .add_edge(query, first)
        .add_edge(first, second)
        .build()
    )
    outputs = (await workflow.run({})).get_outputs()
    if len(outputs) != 1:
        raise ValueError("composition produced no unique output")
    return outputs[0]


def factory(parameters):
    """Registry's pinned installed factory; data is re-read for every invocation."""
    solution = Solution.model_validate(parameters)

    async def operation(arguments):
        # Current inputs come from the invocation, never a captured old fixture.
        problem = Problem.model_validate(arguments["problem"])
        try:
            return await bounded_execute(solution, problem)
        except (sqlite3.Error, ValueError, TimeoutError) as error:
            # These bounded installed read-only primitives can report a known
            # program rejection. Transport/host cancellation still propagates.
            return {"program_error": type(error).__name__}

    return operation


async def bounded_execute(solution, problem):
    async with asyncio.timeout(3):
        return await execute_solution(solution, problem)
