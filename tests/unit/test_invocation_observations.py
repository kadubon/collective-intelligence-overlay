"""Versioned owner facts must not invent old terminal receipts or truth."""

import base64
import json

import pytest
from pydantic import ValidationError

from collective_intelligence_overlay.models import (
    Event,
    InvocationObservation,
    ReceiptRef,
    Scope,
    Subject,
)
from collective_intelligence_overlay.security import verify


def observed():
    return InvocationObservation(
        caller="receiver",
        invocation_id="sample",
        resource_owner="receiver",
        binding_id="operation",
        binding_digest="b" * 64,
        request_fingerprint="c" * 64,
        arguments_digest="d" * 64,
        scope=Scope(
            task="operation",
            input_contract="integer.v1",
            output_contract="integer.v1",
            environment={"application": "1"},
        ),
        lease_id="invoke-sample",
        worker="worker",
        fence=1,
        phase="accepted",
        origin="execution_transaction",
    )


def event(observation=None, **changes):
    body = dict(
        issuer="receiver",
        subject=Subject(id="operation", version="1", digest="a" * 64),
        action="recommendation",
        task_id="sample",
        attempt_id="invoke-sample",
        correlation_id="c" * 64,
    )
    if observation is not None:
        body.update(schema_version="6", invocation_observation=observation)
    return Event(**{**body, **changes})


def test_v6_dsse_roundtrip_and_unmodified_old_serialization(identities, principals):
    identity = identities["receiver"]
    anchored = event(observed())
    signed = identity.sign(anchored)
    assert signed["payloadType"].endswith(".v6+json")
    assert verify(signed, principals) == anchored
    old = event()
    assert "invocation_observation" not in old.model_dump(mode="json")
    assert "invocation_observation" not in json.loads(
        base64.b64decode(identity.sign(old)["payload"])
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"phase": "dispatched"},
        {"phase": "accepted", "accepted_receipt": ReceiptRef(issuer="receiver", id="accepted")},
        {"phase": "recovered"},
        {"origin": "legacy_recovery_observation"},
        {"observed_state_digest": "e" * 64},
    ],
)
def test_missing_or_backfilled_transaction_facts_are_rejected(changes):
    with pytest.raises(ValidationError):
        InvocationObservation.model_validate({**observed().model_dump(), **changes})


@pytest.mark.parametrize(
    "changes",
    [{"outcome": "PASS"}, {"schema_version": "5"}, {"issuer": "other"}, {"action": "reuse"}],
)
def test_anchor_is_not_completion_admission_or_quality(changes):
    with pytest.raises(ValidationError):
        event(observed(), **changes)


def test_recovery_observation_is_new_current_state_with_missing_acceptance():
    recovery = InvocationObservation.model_validate(
        {
            **observed().model_dump(),
            "phase": "recovered",
            "origin": "legacy_recovery_observation",
            "observed_state_digest": "e" * 64,
        }
    )
    assert recovery.accepted_receipt is None
    assert event(recovery).execution is None
    with pytest.raises(ValidationError):
        InvocationObservation.model_validate(
            {
                **recovery.model_dump(),
                "accepted_receipt": ReceiptRef(issuer="receiver", id="fabricated"),
            }
        )
