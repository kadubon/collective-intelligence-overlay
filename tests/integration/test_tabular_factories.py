"""Model involvement: different valid parameters change actual executable results.

These are primitive/instrumentation checks, not real Gemma samples. The paired
local harness retains the full real raw -> proposal -> receipt -> checker chain.
"""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from collective_intelligence_overlay.starter.tabular import (
    AggregatePlan,
    NumericPlan,
    StatusPlan,
    aggregate,
    normalize,
    select_status,
)

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
from tabular_evaluation import Evaluator, family  # noqa: E402


@pytest.mark.parametrize("variant", range(4))
def test_independent_fraction_checker_agrees_for_multiple_hidden_inputs(variant):
    truth, _ = family(variant)
    evaluator = Evaluator({"truth": truth, "seeds": {"validation": 831 + variant}})
    numeric = NumericPlan.model_validate({k: truth[k] for k in NumericPlan.model_fields})
    status = StatusPlan.model_validate({k: truth[k] for k in StatusPlan.model_fields})
    composition = AggregatePlan.model_validate({k: truth[k] for k in AggregatePlan.model_fields})
    for name in ("numeric", "status", "aggregate"):
        for case in evaluator.cases("validation", name):
            values = normalize(case["rows"], numeric)
            selected = select_status(case["rows"], status)
            actual = {"numeric": values, "status": selected}.get(name)
            if name == "aggregate":
                actual = aggregate(
                    case["rows"], values["values"], selected["selected"], composition
                )
            assert actual == case["expected"]


def test_valid_alternative_changes_outcome_and_invalid_is_not_replaced():
    rows = [{"amount": "123", "status": " PAID ", "group": "East"}]
    units = NumericPlan(decimal_separator=".", thousands_separator="", affix="", divisor=1)
    cents = units.model_copy(update={"divisor": 100})
    assert normalize(rows, units) == {"values": ["123.00"]}
    assert normalize(rows, cents) == {"values": ["1.23"]}
    status = StatusPlan(trim=True, casefold=True, accepted=["paid"])
    assert select_status(rows, status) == {"selected": [True]}
    assert select_status(rows, status.model_copy(update={"trim": False})) == {"selected": [False]}
    with pytest.raises(ValidationError):
        NumericPlan.model_validate_json("INVALID")
    with pytest.raises(ValidationError):
        NumericPlan.model_validate_json('{"decimal_separator":".","divisor":7}')
