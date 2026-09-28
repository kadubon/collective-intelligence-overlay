from datetime import timedelta

import pytest
from pydantic import ValidationError

from collective_intelligence_overlay.models import BindingRef, Opportunity, Proposal, RecordRef
from collective_intelligence_overlay.security import digest, verify


def proposal(opportunity):
    return Proposal(
        id="alternative-a",
        issuer="producer",
        subject=opportunity.subject,
        scope=opportunity.scope,
        receivers=("receiver",),
        goal_id=opportunity.goal_id,
        goal_digest=opportunity.goal_digest,
        opportunity=RecordRef(
            kind="opportunity",
            issuer=opportunity.issuer,
            id=opportunity.id,
            payload_digest=digest(b"opportunity payload"),
        ),
        builder=BindingRef(issuer="receiver", id="installed-builder", digest=digest(b"builder")),
        arguments={"threshold": 3},
        alternative="calibrated",
        expires_at=opportunity.expires_at,
    )


def test_signed_records_are_not_execution_receipts(opportunity, identities, principals):
    for item in (opportunity, proposal(opportunity)):
        envelope = identities[item.issuer].sign(item)
        assert verify(envelope, principals) == item
        assert "execution" not in item.model_dump()
        assert "formation" not in item.model_dump()
        with pytest.raises(ValidationError):
            type(item).model_validate({**item.model_dump(), "schema_version": "2"})


@pytest.mark.parametrize(
    "change",
    [
        {"receivers": ()},
        {"basis": ()},
        {"permissions": ("unsafe permission",)},
        {
            "estimates": (
                {"category": "verification", "status": "measured", "quantity": 1, "unit": "work"},
            )
        },
    ],
)
def test_opportunity_rejects_missing_scope_and_fabricated_actuals(opportunity, change):
    with pytest.raises(ValidationError):
        Opportunity.model_validate({**opportunity.model_dump(), **change})


def test_duplicate_basis_expiry_and_argument_bounds(opportunity):
    with pytest.raises(ValidationError):
        Opportunity.model_validate({**opportunity.model_dump(), "basis": opportunity.basis * 2})
    with pytest.raises(ValidationError):
        Opportunity.model_validate(
            {
                **opportunity.model_dump(),
                "expires_at": opportunity.created_at - timedelta(seconds=1),
            }
        )
    item = proposal(opportunity)
    for arguments in ({"text": "x" * 8192}, {"number": float("nan")}):
        with pytest.raises(ValidationError):
            Proposal.model_validate({**item.model_dump(), "arguments": arguments})
    with pytest.raises(ValidationError):
        Proposal.model_validate({**item.model_dump(), "opportunity": opportunity.basis[0]})
