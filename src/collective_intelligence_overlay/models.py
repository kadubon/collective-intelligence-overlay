"""Versioned wire records. Authenticity is established outside these untrusted models."""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal, Self
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=160, pattern=r"^[a-zA-Z0-9_.:/-]+$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
RecordId = Annotated[str, Field(min_length=1, max_length=330, pattern=r"^[a-zA-Z0-9_.:@/-]+$")]


WorkKind = Literal["formation", "connection", "verification", "observation", "repair"]


def now() -> datetime:
    return datetime.now(UTC)


def uid() -> str:
    return str(uuid4())


class RecordModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_max_length=16384)


class Model(RecordModel):
    schema_version: Literal["1"] = "1"


class Verdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class Outcome(StrEnum):
    ACCEPT = "ACCEPT"
    REQUALIFY = "REQUALIFY"
    REJECT = "REJECT"
    UNKNOWN = "UNKNOWN"


class Subject(Model):
    id: Identifier
    version: Identifier
    digest: Digest

    @property
    def key(self) -> str:
        return f"{self.id}@{self.version}"


class Scope(Model):
    """Exact operational applicability; schema equality does not prove semantic fit."""

    task: Identifier
    input_contract: Identifier
    output_contract: Identifier
    environment: dict[Identifier, Identifier] = Field(max_length=64)
    permissions: tuple[Identifier, ...] = Field(default=(), max_length=64)


class FormationInput(Model):
    """Exact construction input; not a runtime call or independent proof."""

    subject: Subject
    issuer: Identifier
    binding_digest: Digest


class Capability(RecordModel):
    schema_version: Literal["1", "2", "3"] = "1"
    binding_digest: Digest | None = None
    kind: Literal["capability"] = "capability"
    subject: Subject
    issuer: Identifier
    scope: Scope
    entrypoint: Identifier
    claim: Identifier
    dependencies: tuple[Subject, ...] = Field(default=(), max_length=64)
    dependency_issuers: tuple[Identifier, ...] = Field(default=(), max_length=64)
    formation_inputs: tuple[FormationInput, ...] = Field(default=(), max_length=64)
    evidence: tuple[Identifier, ...] = Field(default=(), max_length=64)
    license: str | None = None
    provenance: str
    classification: Literal["declared-new", "imported", "replicated", "scope-qualified"]
    created_at: AwareDatetime = Field(default_factory=now)
    expires_at: AwareDatetime
    obligations: tuple[str, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def valid_lifetime(self) -> Self:
        if (self.schema_version in {"2", "3"}) != (self.binding_digest is not None):
            raise ValueError("v2 capability requires binding identity; v1 cannot invent it")
        if (
            self.schema_version in {"2", "3"}
            and len(self.dependency_issuers) != len(self.dependencies)
        ) or (self.schema_version == "1" and self.dependency_issuers):
            raise ValueError(
                "v2 dependencies require exact issuer identities; v1 leaves them unknown"
            )
        if self.expires_at <= self.created_at:
            raise ValueError("expiry must follow creation")
        if self.subject in self.dependencies:
            raise ValueError("self dependency")
        if self.schema_version != "3" and self.formation_inputs:
            raise ValueError("formation inputs require capability v3")
        keys = [(item.subject, item.issuer) for item in self.formation_inputs]
        if len(set(keys)) != len(keys) or any(
            item.subject == self.subject for item in self.formation_inputs
        ):
            raise ValueError("duplicate or self formation input")
        if set(keys) & set(zip(self.dependencies, self.dependency_issuers, strict=False)):
            raise ValueError("declare an input once; runtime dependency takes precedence")
        return self


class Evidence(RecordModel):
    schema_version: Literal["1", "2"] = "1"
    binding_digest: Digest | None = None
    kind: Literal["evidence"] = "evidence"
    id: Identifier = Field(default_factory=uid)
    issuer: Identifier
    subject: Subject
    claim: Identifier
    scope: Scope
    receivers: tuple[Identifier, ...] = Field(min_length=1, max_length=64)
    verdict: Verdict
    method: Identifier
    verifier_version: Identifier
    artifact_digest: Digest
    sources: tuple[Identifier, ...] = Field(default=(), max_length=64)
    evidence_dependencies: tuple[Identifier, ...] = Field(default=(), max_length=64)
    objections: tuple[Identifier, ...] = Field(default=(), max_length=64)
    obligations: tuple[str, ...] = Field(default=(), max_length=64)
    declared_origin: dict[str, str] = Field(default_factory=dict, max_length=32)
    created_at: AwareDatetime = Field(default_factory=now)
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def valid_lifetime(self) -> Self:
        if (self.schema_version == "2") != (self.binding_digest is not None):
            raise ValueError("v2 evidence requires checked binding identity; v1 cannot invent it")
        if self.expires_at <= self.created_at:
            raise ValueError("expiry must follow creation")
        return self


class Revocation(Model):
    kind: Literal["revocation"] = "revocation"
    id: Identifier = Field(default_factory=uid)
    issuer: Identifier
    subject: Subject
    evidence_id: Identifier | None = None
    reason: str
    created_at: AwareDatetime = Field(default_factory=now)


class Cost(Model):
    category: Literal[
        "formation",
        "verification",
        "transfer",
        "use",
        "maintenance",
        "revocation",
        "failure",
        "connection",
        "observation",
        "repair",
        "overhead",
    ]
    status: Literal["measured", "estimated", "unavailable"]
    quantity: Annotated[Decimal, Field(ge=0, max_digits=24, decimal_places=9)] | None
    unit: Identifier

    @model_validator(mode="after")
    def missing_is_not_zero(self) -> Self:
        if (self.status == "unavailable") != (self.quantity is None):
            raise ValueError("only unavailable costs must have null quantity")
        return self


class ReceiptRef(Model):
    issuer: Identifier
    id: Identifier


class ExecutionReceipt(Model):
    purpose: Literal["reuse", "verification"] = "reuse"
    invocation_id: Identifier
    caller: Identifier
    resource_owner: Identifier
    capability_issuer: Identifier
    binding_digest: Digest
    arguments_digest: Digest
    result_digest: Digest | None = None
    scope: Scope
    policy_digest: Digest
    state: Literal["completed", "unknown", "cancelled"]
    transport: Literal["local", "mcp", "a2a"]
    parent_invocation: Identifier | None = None

    @model_validator(mode="after")
    def result_state(self) -> Self:
        if (self.state == "completed") != (self.result_digest is not None):
            raise ValueError("only completed executions have a committed result digest")
        return self


class FormationReceipt(Model):
    receipts: tuple[ReceiptRef, ...] = Field(min_length=1, max_length=64)
    scope: Scope
    binding_digest: Digest
    policy_digest: Digest
    relationship: Literal["observed-use", "declared"]
    functional_novelty: Literal["unknown"] = "unknown"
    verification: Literal["candidate"] = "candidate"


class WorkObservation(Model):
    receiver: Identifier
    scope: Scope
    policy_digest: Digest
    goal_id: Identifier
    goal_digest: Digest
    opportunity_id: Identifier | None = None
    work_kind: WorkKind | None = None
    stage: Literal["discovery", "selection", "allocation"]
    result: Identifier
    proposals_received: int | None = Field(default=None, ge=0, le=128)
    rule_digest: Digest | None = None
    reasons: tuple[Identifier, ...] = Field(default=(), max_length=16)
    rank: int | None = Field(default=None, ge=0, le=31)

    @model_validator(mode="after")
    def valid_stage(self) -> Self:
        if self.stage == "discovery":
            if self.proposals_received is not None or self.result not in {
                "discovered",
                "deduplicated",
                "expired",
                "superseded",
                "satisfied",
                "interrupted",
            }:
                raise ValueError("invalid discovery observation")
        elif self.stage == "allocation":
            if (
                self.opportunity_id is None
                or self.rule_digest is None
                or self.result not in {"eligible", "deferred"}
                or (self.result == "eligible") != (self.rank is not None)
                or self.proposals_received is not None
            ):
                raise ValueError("invalid allocation observation")
        elif self.opportunity_id is None or self.proposals_received is None:
            raise ValueError("selection observation requires opportunity and received count")
        if self.stage != "allocation" and (
            self.rule_digest or self.reasons or self.rank is not None
        ):
            raise ValueError("allocation fields require allocation stage")
        return self


class Event(RecordModel):
    schema_version: Literal["1", "2", "3"] = "1"
    execution: ExecutionReceipt | None = None
    formation: FormationReceipt | None = None
    work: WorkObservation | None = None
    kind: Literal["event"] = "event"
    id: Identifier = Field(default_factory=uid)
    issuer: Identifier
    subject: Subject
    action: Literal[
        "proposal",
        "formation",
        "verification",
        "admission",
        "reuse",
        "composition",
        "revocation",
        "failure",
        "replication",
        "import",
        "recommendation",
    ]
    task_id: Identifier
    attempt_id: Identifier
    correlation_id: Identifier
    causation_id: Identifier | None = None
    occurred_at: AwareDatetime = Field(default_factory=now)
    costs: tuple[Cost, ...] = Field(default=(), max_length=64)
    outcome: Outcome | Verdict | None = None
    duration_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def receipt_version(self) -> Self:
        count = int(self.execution is not None) + int(self.formation is not None)
        if self.schema_version == "3":
            if (
                count
                or self.work is None
                or self.action != "recommendation"
                or self.outcome is not None
            ):
                raise ValueError(
                    "v3 work events require one observation and no execution/truth claim"
                )
            if self.work.receiver != self.issuer:
                raise ValueError("work observations belong to their local owner")
        elif self.work is not None:
            raise ValueError("work observations require event v3")
        if (self.schema_version == "1" and count) or (self.schema_version == "2" and count != 1):
            raise ValueError("v2 events require one scoped execution or formation receipt")
        if self.execution and self.execution.resource_owner != self.issuer:
            raise ValueError("execution receipt must be signed by its resource owner")
        if self.formation and self.action not in {"formation", "composition"}:
            raise ValueError("formation receipt requires a formation action")
        return self


class UseRequest(Model):
    purpose: Literal["reuse", "verification"] = "reuse"
    receiver: Identifier
    subject: Subject
    scope: Scope
    semantic_fit: Literal["confirmed", "unknown"] = "unknown"
    capability_issuer: Identifier | None = None
    binding_digest: Digest | None = None
    arguments_digest: Digest | None = None


class Decision(Model):
    id: Identifier = Field(default_factory=uid)
    request: UseRequest
    outcome: Outcome
    reasons: tuple[str, ...]
    policy_digest: Digest
    evaluated_at: AwareDatetime = Field(default_factory=now)
    evidence_ids: tuple[str, ...] = ()
    record_count: int = Field(default=0, ge=0)
    revisions: dict[str, int] = Field(default_factory=dict, max_length=2048)
    source_observations: dict[str, AwareDatetime | None] = Field(
        default_factory=dict, max_length=4096
    )
    valid_until: AwareDatetime = Field(default_factory=now)


class RecordRef(Model):
    """Exact observation identity; a reference is not execution or checking authority."""

    kind: Literal[
        "capability", "evidence", "revocation", "event", "decision", "opportunity", "proposal"
    ]
    issuer: Identifier
    id: RecordId
    payload_digest: Digest


class BindingRef(Model):
    issuer: Identifier
    id: Identifier
    digest: Digest


class Opportunity(Model):
    """A scoped, signed description of a deficit, never a grant or success receipt."""

    kind: Literal["opportunity"] = "opportunity"
    id: Identifier
    issuer: Identifier
    subject: Subject
    scope: Scope
    receivers: tuple[Identifier, ...] = Field(min_length=1, max_length=32)
    goal_id: Identifier
    goal_digest: Digest
    goal_contract_digest: Digest | None = None
    work_kind: WorkKind
    basis: tuple[RecordRef, ...] = Field(min_length=1, max_length=32)
    observation_digest: Digest
    policy_digest: Digest
    reasons: tuple[Identifier, ...] = Field(min_length=1, max_length=16)
    expected_contract: Identifier
    checker: BindingRef
    permissions: tuple[Identifier, ...] = Field(default=(), max_length=32)
    estimates: tuple[Cost, ...] = Field(default=(), max_length=8)
    supersedes: Identifier | None = None
    created_at: AwareDatetime = Field(default_factory=now)
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def proposal_is_not_observation(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("opportunity expiry must follow observation")
        if any(cost.status == "measured" for cost in self.estimates):
            raise ValueError("opportunity estimates cannot claim measured spending")
        if len(set((ref.kind, ref.issuer, ref.id) for ref in self.basis)) != len(self.basis):
            raise ValueError("duplicate opportunity basis")
        return self


class Proposal(Model):
    """An alternative input to an installed builder, not received executable code."""

    kind: Literal["proposal"] = "proposal"
    id: Identifier
    issuer: Identifier
    subject: Subject
    scope: Scope
    receivers: tuple[Identifier, ...] = Field(min_length=1, max_length=32)
    goal_id: Identifier
    goal_digest: Digest
    opportunity: RecordRef
    builder: BindingRef
    arguments: dict[str, Any] = Field(max_length=32)
    alternative: Identifier
    estimates: tuple[Cost, ...] = Field(default=(), max_length=8)
    created_at: AwareDatetime = Field(default_factory=now)
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def bounded_untrusted_builder_input(self) -> Self:
        import json

        if self.opportunity.kind != "opportunity":
            raise ValueError("proposal must refer to an opportunity")
        if self.expires_at <= self.created_at:
            raise ValueError("proposal expiry must follow creation")
        if any(cost.status == "measured" for cost in self.estimates):
            raise ValueError("proposal estimates are not measured results")
        if len(json.dumps(self.arguments, allow_nan=False).encode()) > 8192:
            raise ValueError("proposal arguments exceed byte bound")
        return self


Record = Capability | Evidence | Revocation | Event | Opportunity | Proposal
