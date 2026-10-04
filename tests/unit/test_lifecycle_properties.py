"""Finite properties with independent set/Decimal/count expectations."""

import copy
from decimal import Decimal

import pytest
from hypothesis import given, seed, settings
from hypothesis import strategies as st
from test_lifecycle import capability, context, snapshot, target, use

from collective_intelligence_overlay.lifecycle import (
    HandoffRole,
    build_handoff,
    inspect_lifecycle,
    observe_contributions,
    snapshot_from_material,
)
from collective_intelligence_overlay.models import Cost


@seed(511)
@settings(max_examples=24, deadline=None)
@given(st.lists(st.integers(0, 7), min_size=1, max_size=16))
def test_duplicate_sources_keep_distinct_invocations_and_input_unchanged(ids):
    cap = capability()
    events = [use(cap, f"event-{i}", invocation=f"invocation-{i}") for i in ids]
    material = {
        "view_schema_version": "1",
        "context": context().model_dump(mode="json"),
        "records": [
            {
                "format": "unsigned",
                "document": e.model_dump(mode="json"),
                "received_at": None,
                "sequence": None,
            }
            for e in events
        ],
    }
    before = copy.deepcopy(material)
    observed = observe_contributions(
        snapshot_from_material(material, owner="receiver", caller="receiver")
    )
    assert {x.invocation_id for x in observed} == {f"invocation-{i}" for i in set(ids)}
    assert len(observed) == len(set(ids))
    assert material == before


@seed(512)
@settings(max_examples=24, deadline=None)
@given(st.lists(st.integers(0, 100000), min_size=1, max_size=8))
def test_typed_quantity_subtotal_matches_decimal_oracle_and_missing_stays_missing(amounts):
    cap = capability()
    events = [
        use(
            cap,
            f"cost-{i}",
            invocation=f"cost-{i}",
            costs=(
                Cost(
                    category="use",
                    status="measured",
                    quantity=Decimal(amount) / 1000,
                    unit="tokens",
                ),
            ),
        )
        for i, amount in enumerate(amounts)
    ]
    events.append(
        use(
            cap,
            "missing-cost",
            invocation="missing-cost",
            costs=(Cost(category="use", status="unavailable", quantity=None, unit="tokens"),),
        )
    )
    view = inspect_lifecycle(snapshot(cap, *events), target(cap))
    assert len(view.costs) == len(amounts) + 1
    assert len(view.cost_subtotals) == 1
    assert view.cost_subtotals[0].quantity == sum((Decimal(x) / 1000 for x in amounts), Decimal(0))
    assert any(x.cost.quantity is None and x.cost.status == "unavailable" for x in view.costs)


@seed(513)
@settings(max_examples=16, deadline=None)
@given(st.sampled_from(["partial", "complete", "inconsistent"]))
def test_handoff_keeps_page_coverage_and_never_grants_authority(coverage):
    cap = capability()
    view = inspect_lifecycle(snapshot(cap, ctx=context(coverage=coverage)), target(cap))
    handoff = build_handoff(
        view,
        source_role=HandoffRole.GENERATE,
        target_role=HandoffRole.VERIFY,
        producer="producer",
        receiver="receiver",
        contract_identity="view.v1",
    )
    assert handoff.context.coverage == view.context.coverage
    assert handoff.authority == "not_granted"
    assert handoff.residuals == view.residuals


@seed(514)
@settings(max_examples=16, deadline=None)
@given(st.text(alphabet="abcxyz", min_size=1, max_size=12))
def test_denied_owner_is_checked_before_material_is_read(caller):
    with pytest.raises(PermissionError):
        snapshot_from_material({}, owner="receiver", caller=caller)


@seed(515)
@settings(max_examples=16, deadline=None)
@given(st.integers(1, 100000))
def test_same_source_changed_content_is_rejected(quantity):
    cap = capability()
    first = use(cap)
    changed = first.model_copy(
        update={
            "costs": (Cost(category="use", status="measured", quantity=quantity, unit="tokens"),)
        }
    )
    with pytest.raises(ValueError, match="source identity content conflict"):
        snapshot(first, changed)
