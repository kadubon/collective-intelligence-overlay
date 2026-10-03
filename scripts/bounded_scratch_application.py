"""Source-only finite semantic slots, compiled to the existing installed factory.

No oracle/task generator is imported. Schema, public host constants and selected
model values suffice to compile every allowed plan; syntax never selects an answer.
"""

import itertools
import json
from typing import Literal

from accumulation_application import AccumulationApplication
from accumulation_application import configure as configure_base
from accumulation_primitives import Solution
from check_gemma_transport import validate_wire
from pydantic import ConfigDict, create_model

from collective_intelligence_overlay.bindings import fingerprint

SLOTS = {
    "sql": {
        "negative_policy": ("include", "exclude"),
        "null_policy": ("zero", "drop"),
        "boundary": ("closed", "half_open"),
    },
    "composition": {
        "order": ("transform_then_reduce", "reduce_then_transform"),
        "input_field": ("net", "gross"),
        "scale_choice": ("unit", "double"),
    },
}
LEVEL = {"low": 0, "middle": 1, "high": 2}
FIXED = {
    "sql": {"null_policy": "zero", "boundary": "half_open"},
    "composition": {"input_field": "net", "scale_choice": "unit"},
}
COMPONENTS = {
    "sqlite_extract": "readonly-sql-v3",
    "affine": "public-affine-v1",
    "reduce": "sum-v1",
    "workflow": "installed-MAF-v1",
}


def slot_names(family, difficulty):
    return tuple(SLOTS[family])[: LEVEL[difficulty] + 1]


def slot_candidates(family, difficulty):
    names = slot_names(family, difficulty)
    return [
        dict(zip(names, values, strict=True))
        for values in itertools.product(*(SLOTS[family][name] for name in names))
    ]


def wire_schema(problem, skills=()):
    fields = {
        name: (Literal[SLOTS[problem.family][name]], ...)
        for name in slot_names(problem.family, problem.difficulty)
    }
    # Matching executable reuse is selected by the existing host/session and
    # verified by its real receipt. The model cannot declare a lineage reference.
    return create_model(
        "BoundedSlots_" + problem.family + "_" + problem.difficulty,
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


def public_fixed_fields(problem):
    result = {
        "family": problem.family,
        "aliases": ["group", "value"],
        "reduction": "sum",
        "uses_when_scratch": [],
    }
    result.update(
        {
            k: v
            for k, v in FIXED[problem.family].items()
            if k not in slot_names(problem.family, problem.difficulty)
        }
    )
    if problem.family == "composition":
        result.update(
            coefficients=[problem.parameters["offset"], problem.parameters["slope"], 0],
            components=COMPONENTS,
        )
    return result


def compile_slots(problem, model_values, skills=()):
    schema = wire_schema(problem, skills).model_json_schema()
    selected = validate_wire(
        json.dumps(model_values, allow_nan=False), schema, wire_schema(problem, skills)
    ).model_dump(mode="json")
    slots = {**FIXED[problem.family], **selected}
    uses = ()
    manifest = {
        "schema_revision": "bounded-slots-v1",
        "model_fields": selected,
        "host_fixed": public_fixed_fields(problem),
        "components": COMPONENTS,
    }
    explanation = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    if problem.family == "sql":
        filters = [
            "r.utc >= :start",
            "r.utc <= :stop" if slots["boundary"] == "closed" else "r.utc < :stop",
        ]
        if slots["negative_policy"] == "exclude":
            filters.append("(r.amount IS NULL OR r.amount >= 0)")
        if slots["null_policy"] == "drop":
            filters.append("r.amount IS NOT NULL")
        query = (
            'SELECT r.bucket AS "group", SUM(COALESCE(r.amount,0)) AS value FROM readings r WHERE '
            + " AND ".join(filters)
            + " GROUP BY r.bucket"
        )
        return Solution(family="sql", sql=query, uses=uses, explanation=explanation)
    field = {"net": "net", "gross": "gross"}[slots["input_field"]]
    # Field names are fixed installed identifiers; values use normal parameters.
    scale = "unit_scale" if slots["scale_choice"] == "unit" else "double_scale"
    query = (
        f'SELECT r.bucket AS "group", r."{field}" * :{scale} AS value '
        "FROM readings r WHERE r.utc >= :start AND r.utc < :stop"
    )
    order = {
        "transform_then_reduce": "calibrate-then-reduce",
        "reduce_then_transform": "reduce-then-calibrate",
    }[slots["order"]]
    return Solution(
        family="composition",
        sql=query,
        coefficients=(problem.parameters["offset"], problem.parameters["slope"], 0),
        reduction="sum",
        calibration_order=order,
        uses=uses,
        explanation=explanation,
    )


def model_prompt(problem, skills):
    public = problem.model_dump(mode="json")
    public.pop("id")
    # Opaque operational world/contract IDs are not semantic hints to the model.
    public.pop("contract")
    public.pop("component_contracts")
    public["tables"] = {
        name: {
            "columns": t.columns,
            "column_order": t.column_order,
            "examples": [*t.rows[:3], *t.rows[-1:]],
        }
        for name, t in problem.tables.items()
    }
    options = [{"values": c} for c in slot_candidates(problem.family, problem.difficulty)]
    # Row presentation depends only on shown data, independently of correct slots.
    options.sort(key=lambda c: fingerprint([public["tables"], c]))
    payload = {
        "problem": public,
        "candidate_meanings": options,
        "host_fixed_fields": public_fixed_fields(problem),
        "visible_skills": [
            {"id": s.id, "contract": s.contract, "solution": s.solution.model_dump(mode="json")}
            for s in skills
        ],
    }
    instruction = (
        "Select only the semantic fields required by the JSON schema. "
        "Return a short JSON object, no explanation. "
        "For SQL, include keeps signed amounts, exclude discards negative amounts; "
        "zero retains null-only groups with zero, drop omits null rows; "
        "closed includes stop, half_open excludes stop. "
        "For formation, transform_then_reduce applies the public affine function "
        "to every selected row and then sums by bucket; reduce_then_transform "
        "sums first and applies it once per bucket. input_field selects the declared "
        "net or gross column; scale_choice multiplies each raw row by one or two "
        "before all subsequent operations. All syntax, aliases, fixed constants "
        "and primitive implementations are supplied equally by the host. "
        "Do not invent SQL, coefficients, skill IDs or fields. The model never "
        "declares skill references. Any direct executable reuse is separately "
        "performed and receipted by the host.\n"
    )
    text = instruction + json.dumps(payload, allow_nan=False)
    if len(text.encode()) > 20000:
        raise ValueError("finite context byte cap")
    return text


class BoundedScratchApplication(AccumulationApplication):
    def draft_schema_for_view(self, problem, skills):
        return wire_schema(problem, skills)

    def check_declared_schema(self, problem, skills, schema):
        if (
            self.settings["model"].get("schema_policy") != "bounded-slots-v1"
            or schema != wire_schema(problem, skills).model_json_schema()
        ):
            raise ValueError("fixed semantic-slot schema policy changed")

    def minimum_model_output(self):
        return 128

    def model_prompt(self, problem, skills):
        return model_prompt(problem, skills)

    def decode_model_response(self, text, schema, problem, skills):
        fields = validate_wire(text, schema, wire_schema(problem, skills)).model_dump(mode="json")
        return compile_slots(problem, fields, skills)

    def response_metadata(self, text, schema, problem, skills, solution):
        try:
            fields = json.loads(text) if text is not None else None
        except json.JSONDecodeError:
            fields = None
        return {
            "slot_schema_revision": "bounded-slots-v1",
            "model_fields": fields,
            "host_fixed_fields": public_fixed_fields(problem),
            "wire_schema": schema,
        }


def configure(host):
    return configure_base(host, application_class=BoundedScratchApplication)
