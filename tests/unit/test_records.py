from decimal import Context, Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from collective_intelligence_overlay.accounting import metrics
from collective_intelligence_overlay.models import Cost, Event, Evidence
from collective_intelligence_overlay.security import allowed_url, verify
from collective_intelligence_overlay.storage import Conflict


def test_roundtrip_unknown_version(records):
    _, evidence = records
    assert Evidence.model_validate_json(evidence.model_dump_json()) == evidence
    with pytest.raises(ValidationError):
        Evidence.model_validate({**evidence.model_dump(), "schema_version": "2"})


def test_dsse_tamper_issuer_and_payload(identities, principals, records):
    cap, _ = records
    signed = identities["producer"].sign(cap)
    assert verify(signed, principals) == cap
    with pytest.raises(ValueError):
        identities["other"].sign(cap)
    signed["payload"] = signed["payload"][:-4] + "AAAA"
    with pytest.raises(ValueError):
        verify(signed, principals)


@given(st.decimals(min_value=0, max_value=10000, places=6, allow_nan=False, allow_infinity=False))
def test_cost_decimal_precision(value):
    cost = Cost(category="formation", status="measured", quantity=value, unit="USD")
    assert Cost.model_validate_json(cost.model_dump_json()).quantity == value


def test_unavailable_cost_and_dedupe(records):
    cap, _ = records
    with pytest.raises(ValidationError):
        Cost(category="use", status="unavailable", quantity=0, unit="USD")
    event = Event(
        issuer="producer",
        subject=cap.subject,
        action="formation",
        task_id="t",
        attempt_id="a",
        correlation_id="c",
        costs=(
            Cost(category="formation", status="measured", quantity=Decimal("0.1"), unit="USD"),
            Cost(category="formation", status="unavailable", quantity=None, unit="seconds"),
        ),
    )
    result = metrics([event, event])
    assert result["events"] == 1
    assert result["costs"][0]["quantity"] == "0.1"
    assert result["unavailable"][0]["count"] == 1
    with pytest.raises(Conflict):
        metrics([event, event.model_copy(update={"action": "replication"})])


@pytest.mark.parametrize(
    "url", ["http://evil.test", "file:///etc/passwd", "https://a@b", "https://b#x"]
)
def test_url_boundary(url):
    with pytest.raises(ValueError):
        allowed_url(url, frozenset({url}))


def test_large_cost_aggregation_keeps_all_decimal_places(records):
    charge = Cost(
        category="use", status="measured", unit="USD", quantity=Decimal("999999999999999.999999999")
    )
    event = Event(
        issuer="producer",
        subject=records[0].subject,
        action="reuse",
        task_id="task",
        attempt_id="attempt",
        correlation_id="costs",
        costs=(charge,) * 64,
    )
    result = metrics([event.model_copy(update={"id": f"cost-{index}"}) for index in range(200)])
    expected = Context(prec=50).multiply(charge.quantity, Decimal(12800))
    assert Decimal(result["costs"][0]["quantity"]) == expected


def test_capability_v3_formation_inputs_and_signed_version_boundary(
    identities, principals, records
):
    import base64
    import json

    from securesystemslib.dsse import Envelope

    from collective_intelligence_overlay.models import Capability, FormationInput, Subject
    from collective_intelligence_overlay.security import PAYLOAD_TYPE_V2, PAYLOAD_TYPE_V3, verify

    original = records[0]
    source = FormationInput(
        subject=Subject(id="source", version="1", digest="a" * 64),
        issuer="producer",
        binding_digest="b" * 64,
    )
    v2 = Capability.model_validate(
        {**original.model_dump(), "schema_version": "2", "binding_digest": "c" * 64}
    )
    signed_v2 = identities[v2.issuer].sign(v2)
    assert "formation_inputs" not in json.loads(base64.b64decode(signed_v2["payload"]))
    with pytest.raises(ValueError, match="require capability v3"):
        Capability.model_validate({**v2.model_dump(), "formation_inputs": [source]})
    v3 = Capability.model_validate(
        {**v2.model_dump(), "schema_version": "3", "formation_inputs": [source]}
    )
    signed = identities[v3.issuer].sign(v3)
    assert signed["payloadType"] == PAYLOAD_TYPE_V3
    assert verify(signed, principals) == v3
    mismatched = Envelope(base64.b64decode(signed["payload"]), PAYLOAD_TYPE_V2, {})
    mismatched.sign(identities[v3.issuer].signer)
    with pytest.raises(ValueError, match="media type differ"):
        verify(mismatched.to_dict(), principals)
    with pytest.raises(ValueError, match="duplicate"):
        Capability.model_validate({**v3.model_dump(), "formation_inputs": [source, source]})
    with pytest.raises(ValueError, match="once"):
        Capability.model_validate(
            {
                **v3.model_dump(),
                "dependencies": [source.subject],
                "dependency_issuers": [source.issuer],
            }
        )


def test_work_event_cannot_claim_execution_or_truth(identities, principals, records):
    import base64
    import json

    from collective_intelligence_overlay.models import WorkObservation

    cap = records[0]
    work = WorkObservation(
        receiver="receiver",
        scope=cap.scope,
        policy_digest="a" * 64,
        goal_id="goal",
        goal_digest="b" * 64,
        stage="discovery",
        result="deduplicated",
    )
    event = Event(
        schema_version="3",
        issuer="receiver",
        subject=cap.subject,
        action="recommendation",
        task_id="goal",
        attempt_id="attempt",
        correlation_id="goal",
        work=work,
    )
    assert verify(identities["receiver"].sign(event), principals) == event
    for changes in (
        {"schema_version": "2"},
        {"outcome": "PASS"},
        {"action": "reuse"},
        {"issuer": "producer"},
    ):
        with pytest.raises(ValueError):
            Event.model_validate({**event.model_dump(), **changes})
    legacy = Event(
        issuer="receiver",
        subject=cap.subject,
        action="recommendation",
        task_id="goal",
        attempt_id="old",
        correlation_id="goal",
    )
    assert "work" not in json.loads(
        base64.b64decode(identities["receiver"].sign(legacy)["payload"])
    )
