"""Bounded read models; original records and execution authority stay elsewhere.

No view is a Record, credential, current-use grant or proof of functional novelty.
Only ``assess_stock`` performs explicitly requested qualification; all other
functions operate on finite, already authorized material without I/O.
"""

from __future__ import annotations

import base64
import json
from collections import defaultdict
from datetime import datetime
from decimal import Context, Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from ._lifecycle_json import check_json_bytes, load_json, validate_json_tree
from .models import (
    Capability,
    Cost,
    Decision,
    Digest,
    Event,
    Evidence,
    ExecutionReceipt,
    Identifier,
    ReceiptRef,
    Record,
    RecordRef,
    Revocation,
    Scope,
    Subject,
    UseRequest,
    now,
)
from .queries import RecordCursor, RecordQuery
from .security import Principal, digest, record_adapter, verify
from .storage import Conflict, projection_digest

if TYPE_CHECKING:
    from .overlay import Overlay

MAX_OBSERVATIONS = 256
MAX_VIEW_BYTES = 1048576
# Recognized duration labels only classify observations conservatively. No unit
# conversion or inclusive/exclusive physical-time inference is performed.
DURATION_UNITS = frozenset(
    {
        "ns",
        "nanosecond",
        "nanoseconds",
        "us",
        "microsecond",
        "microseconds",
        "ms",
        "millisecond",
        "milliseconds",
        "s",
        "second",
        "seconds",
        "minute",
        "minutes",
        "hour",
        "hours",
        "day",
        "days",
        "wall_seconds",
        "wall_ms",
        "cpu_seconds",
        "cpu_ms",
    }
)
RecordKind = Literal[
    "capability", "evidence", "revocation", "event", "decision", "opportunity", "proposal"
]
Availability = Literal["accepted", "nonaccepted", "unknown"]
NON_CLAIMS = (
    "No semantic truth, functional novelty, causal contribution or intelligence growth claim.",
    (
        "Historical signature/PASS/ACCEPT, coverage and reception grant no current execution "
        "authority."
    ),
    "Local bounded observations are not complete world history; missing costs are not zero.",
)


class ViewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_max_length=16384)


class CapabilityIdentity(ViewModel):
    issuer: Identifier
    subject: Subject
    binding_digest: Digest | None

    @property
    def key(self) -> str:
        return projection_digest(self.model_dump(mode="json"))


class Coverage(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    INCONSISTENT = "inconsistent"


class SourceObservation(ViewModel):
    reference: RecordRef
    payload_basis: Literal["original_dsse_payload", "unsigned_json_projection"]
    signature: Literal["historical_verified", "unsigned"]
    current_key_authority: Literal["unassessed", "compromised_key_observed", "unsigned"]
    occurred_at: AwareDatetime | None
    received_at: AwareDatetime | None
    sequence: int | None = Field(ge=0)
    decoder_default_fields: tuple[str, ...] | None = Field(default=None, max_length=64)


def original_record_metadata(
    record: Record | Decision, body: dict[str, Any]
) -> tuple[datetime | None, tuple[str, ...]]:
    """Separate legacy decoder defaults from fields present in original JSON.

    The typed record keeps its existing wire-decoder contract. Default markers
    describe the projection, not additional source facts. Nested purpose markers
    matter because a decoder's reuse default is not an observed reuse purpose.
    """
    if not isinstance(record, Capability) and "id" not in body:
        raise ValueError("original record identity missing; decoder ID is not a source identity")
    clock = (
        "evaluated_at"
        if isinstance(record, Decision)
        else "occurred_at"
        if isinstance(record, Event)
        else "created_at"
    )
    occurred = getattr(record, clock) if clock in body else None
    defaults = set(type(record).model_fields) - body.keys()
    if isinstance(record, Event) and record.execution and "purpose" not in body["execution"]:
        defaults.add("execution.purpose")
    if isinstance(record, Decision) and "purpose" not in body["request"]:
        defaults.add("request.purpose")
    return occurred, tuple(sorted(defaults))


def _decode_original(
    document: dict[str, Any], principals: dict[str, Principal]
) -> tuple[Record, dict[str, Any], str]:
    """One exact-byte DSSE read shared by explicit material and Store projections."""
    payload = base64.b64decode(document["payload"], validate=True)
    check_json_bytes(payload)
    record = verify(document, principals, require_authority=False)
    return record, load_json(payload), digest(payload)


def _historical_key_authority(
    document: dict[str, Any], principal: Principal
) -> Literal["unassessed", "compromised_key_observed"]:
    compromised = any(
        signature["keyid"] in principal.compromised_keyids for signature in document["signatures"]
    )
    return "compromised_key_observed" if compromised else "unassessed"


class ObservationContext(ViewModel):
    owner: Identifier
    receiver: Identifier | None
    scope: Scope | None
    policy_digest: Digest | None
    cutoff: AwareDatetime
    observed_at: AwareDatetime
    feed_generation: str | None = Field(max_length=64)
    prefix: int | None = Field(ge=0)
    revisions: dict[str, int] = Field(default_factory=dict, max_length=2048)
    coverage: Coverage
    coverage_basis: str
    query: RecordQuery | None = None
    record_cursor: RecordCursor | None = None
    decision_cursor: RecordCursor | None = None
    record_limit: int = Field(default=MAX_OBSERVATIONS, ge=1, le=MAX_OBSERVATIONS)
    byte_limit: int = Field(default=MAX_VIEW_BYTES, ge=1024, le=MAX_VIEW_BYTES)
    period_start: AwareDatetime | None = None
    period_end: AwareDatetime | None = None

    @model_validator(mode="after")
    def period(self) -> Self:
        if (self.period_start is None) != (self.period_end is None):
            raise ValueError("both local period endpoints are required")
        if self.period_start and self.period_end and self.period_start >= self.period_end:
            raise ValueError("period must be nonempty")
        return self


class ObservedRecord(ViewModel):
    record: Record | Decision
    source: SourceObservation


class LifecycleSnapshot(ViewModel):
    """Finite authorized input, not a persisted authority or general graph cache."""

    context: ObservationContext
    records: tuple[ObservedRecord, ...] = Field(max_length=MAX_OBSERVATIONS)

    @model_validator(mode="after")
    def bounds(self) -> Self:
        if len(self.records) > self.context.record_limit:
            raise ValueError("snapshot record bound exceeded")
        if len(self.model_dump_json().encode()) > self.context.byte_limit:
            raise ValueError("snapshot byte bound exceeded")
        keys: dict[tuple[str, str, str], str] = {}
        for item in self.records:
            ref = item.source.reference
            key = (ref.kind, ref.issuer, ref.id)
            if key in keys and keys[key] != ref.payload_digest:
                raise Conflict("source identity content conflict")
            keys[key] = ref.payload_digest
            if item.source.received_at and item.source.received_at > self.context.cutoff:
                raise ValueError("record received after snapshot cutoff")
            decision_owner = ref.issuer if isinstance(item.record, Decision) else self.context.owner
            kind, issuer, rid = record_identity(item.record, decision_owner)
            if (kind, issuer, rid) != key:
                raise ValueError("source reference does not identify its record")
        _check_visible_cycles(self.records)
        return self


class ResidualKind(StrEnum):
    MISSING_EVIDENCE = "missing_evidence"
    UNRESOLVED_EFFECT = "unresolved_effect"
    UNKNOWN_COST = "unknown_cost"
    UNKNOWN_CAUSALITY = "unknown_causality"
    INCOMPATIBLE_UNIT = "incompatible_unit"
    STALE_SOURCE = "stale_source"
    AUTHORITY_MISSING = "authority_missing"
    MISSING_HISTORY = "missing_history"
    AMBIGUOUS_IDENTITY = "ambiguous_identity"
    UNKNOWN_RELATION = "unknown_relation"
    ATTRIBUTION_UNRESOLVED = "attribution_unresolved"
    PARTIAL_SNAPSHOT = "partial_snapshot"
    POLICY_MISMATCH = "policy_mismatch"
    UNMAPPED_REASON = "unmapped_reason"
    RECORDED_OBLIGATION = "recorded_obligation"


class Residual(ViewModel):
    id: Digest
    kind: ResidualKind
    target: CapabilityIdentity | None
    sources: tuple[RecordRef, ...] = Field(max_length=MAX_OBSERVATIONS)
    prevents: tuple[str, ...]
    observed_at: AwareDatetime
    scope: Scope | None
    explanation: str
    next_check: str | None = None
    responsible_owner: Identifier | None = None
    due_at: AwareDatetime | None = None
    resolved_by: RecordRef | None = None


class Report(ViewModel):
    view_schema_version: Literal["1"] = "1"
    derivation_version: Literal["0.5.0"] = "0.5.0"
    generated_at: AwareDatetime = Field(default_factory=now)
    context: ObservationContext
    sources: tuple[SourceObservation, ...] = Field(max_length=MAX_OBSERVATIONS)
    residuals: tuple[Residual, ...] = Field(max_length=1024)
    non_claims: tuple[str, ...] = NON_CLAIMS

    @property
    def projection_digest(self) -> str:
        return projection_digest(self.model_dump(mode="json"))


class ContributionRelation(StrEnum):
    COPY = "COPY"
    IMPORT = "IMPORT"
    REUSE = "REUSE"
    FORMATION_INPUT = "FORMATION_INPUT"
    NEW_CANDIDATE = "NEW_CANDIDATE"


class CostReference(ViewModel):
    source: RecordRef
    position: int = Field(ge=0, le=63)

    @property
    def key(self) -> str:
        return projection_digest(self.model_dump(mode="json"))


class CostObservation(ViewModel):
    reference: CostReference
    owner: Identifier
    cost: Cost
    occurred_at: AwareDatetime | None
    duration_basis: Literal["inclusive_or_unspecified", "recorded_quantity"]
    physical_cost_correspondence: Literal["unresolved"] = "unresolved"


class CostSubtotal(ViewModel):
    owner: Identifier
    category: str
    unit: Identifier
    status: Literal["measured", "estimated"]
    quantity: Decimal
    observation_count: int = Field(ge=1)
    basis: Literal["known_recorded_subtotal_not_complete_consumption"] = (
        "known_recorded_subtotal_not_complete_consumption"
    )


class ContributionObservation(Report):
    observation_id: Digest
    resulting_capability: CapabilityIdentity | None
    source_capability: CapabilityIdentity | None
    relations: tuple[ContributionRelation, ...]
    strength: Literal["declared", "observed", "unresolved"]
    basis: str
    receiver: Identifier | None
    transport: Literal["local", "mcp", "a2a"] | None = None
    invocation_id: Identifier | None = None
    observed_outcome: str | None = None
    cost_refs: tuple[CostReference, ...] = Field(max_length=64)
    receipt_links: tuple[RecordRef, ...] = Field(default=(), max_length=64)
    unavailable_receipt_links: tuple[ReceiptRef, ...] = Field(default=(), max_length=64)
    functional_novelty: Literal["unknown"] = "unknown"
    local_installation: Literal["unobserved"] = "unobserved"


class ExecutionObservation(ViewModel):
    source: RecordRef
    receipt: ExecutionReceipt


class CapabilityLifecycleView(Report):
    target: CapabilityIdentity
    candidate_observed: bool | None
    generation_observed: bool | None
    evidence: tuple[dict[str, Any], ...] = Field(max_length=MAX_OBSERVATIONS)
    decisions: tuple[Decision, ...] = Field(max_length=MAX_OBSERVATIONS)
    executions: tuple[ExecutionObservation, ...] = Field(max_length=MAX_OBSERVATIONS)
    owner_observations: tuple[dict[str, Any], ...] = Field(max_length=MAX_OBSERVATIONS)
    withdrawals: tuple[RecordRef, ...] = Field(max_length=MAX_OBSERVATIONS)
    contributions: tuple[ContributionObservation, ...] = Field(max_length=512)
    costs: tuple[CostObservation, ...] = Field(max_length=16384)
    cost_subtotals: tuple[CostSubtotal, ...] = Field(max_length=16384)
    runtime_dependencies: tuple[CapabilityIdentity, ...] = Field(max_length=64)
    formation_inputs: tuple[CapabilityIdentity, ...] = Field(max_length=64)
    evidence_support: tuple[tuple[Identifier, Identifier], ...] = Field(max_length=16384)
    current_admission: Literal["unassessed"] = "unassessed"
    execution_authority: Literal["not_granted"] = "not_granted"


class StockCoordinates(ViewModel):
    receiver: Identifier
    scope: Scope
    policy_digest: Digest
    target_universe: tuple[CapabilityIdentity, ...] = Field(min_length=1, max_length=32)
    identity_rule: Literal["issuer_subject_version_digest_binding"] = (
        "issuer_subject_version_digest_binding"
    )
    availability_definition: Literal["consistent_explicit_qualification_at_observation"] = (
        "consistent_explicit_qualification_at_observation"
    )
    unit: Literal["admitted_entry"] = "admitted_entry"

    @model_validator(mode="after")
    def unique(self) -> Self:
        if len({target.key for target in self.target_universe}) != len(self.target_universe):
            raise ValueError("duplicate stock target")
        return self


class StockEntry(ViewModel):
    target: CapabilityIdentity
    availability: Literal["accepted", "nonaccepted", "unknown"]
    decision: Decision
    reference: RecordRef


class StockObservation(Report):
    coordinates: StockCoordinates
    entries: tuple[StockEntry, ...] = Field(min_length=1, max_length=32)
    assessment_started_at: AwareDatetime
    assessment_completed_at: AwareDatetime
    evaluation: Literal["per_target_current_decisions_not_atomic"] = (
        "per_target_current_decisions_not_atomic"
    )

    @model_validator(mode="after")
    def target_set(self) -> Self:
        targets = {target.key for target in self.coordinates.target_universe}
        if {entry.target.key for entry in self.entries} != targets or len(self.entries) != len(
            targets
        ):
            raise ValueError("stock entries must cover the explicit target universe once")
        if self.context.receiver != self.coordinates.receiver:
            raise ValueError("stock receiver mismatch")
        if self.context.owner != self.coordinates.receiver:
            raise ValueError("explicit stock assessment belongs to the local receiver")
        if (self.context.scope, self.context.policy_digest) != (
            self.coordinates.scope,
            self.coordinates.policy_digest,
        ):
            raise ValueError("stock context coordinates mismatch")
        if not self.assessment_started_at <= self.assessment_completed_at == self.context.cutoff:
            raise ValueError("stock assessment clock mismatch")
        for entry in self.entries:
            request = entry.decision.request
            if not self.assessment_started_at <= entry.decision.evaluated_at <= self.context.cutoff:
                raise ValueError("stock decision is outside explicit assessment window")
            if (
                request.receiver != self.coordinates.receiver
                or request.scope != self.coordinates.scope
                or entry.decision.policy_digest != self.coordinates.policy_digest
                or request.subject != entry.target.subject
                or request.capability_issuer != entry.target.issuer
                or request.binding_digest != entry.target.binding_digest
            ):
                raise ValueError("stock decision coordinates mismatch")
            if (
                entry.reference.kind != "decision"
                or entry.reference.issuer != self.context.owner
                or entry.reference.id != entry.decision.id
                or entry.reference.payload_digest
                != projection_digest(entry.decision.model_dump(mode="json"))
                or not any(s.reference == entry.reference for s in self.sources)
            ):
                raise ValueError("stock decision projection reference mismatch")
            if entry.availability == "accepted" and (
                entry.decision.outcome != "ACCEPT"
                or not entry.decision.evaluated_at
                <= self.context.cutoff
                < entry.decision.valid_until
            ):
                raise ValueError("accepted entry requires an in-window ACCEPT observation")
            if entry.availability == "nonaccepted" and entry.decision.outcome != "REJECT":
                raise ValueError("confirmed nonacceptance requires an actual REJECT")
        return self


class GrowthObservation(Report):
    opening: StockObservation
    closing: StockObservation
    reconciled: bool | None
    opening_admitted_entry_count: int = Field(ge=0)
    closing_admitted_entry_count: int = Field(ge=0)
    opening_unknown_entry_count: int = Field(ge=0)
    closing_unknown_entry_count: int = Field(ge=0)
    count_basis: Literal["observed_admitted_entries_not_functional_abilities"] = (
        "observed_admitted_entries_not_functional_abilities"
    )
    history_context: ObservationContext | None
    entries_added_net: tuple[CapabilityIdentity, ...] | None
    entries_lost_net: tuple[CapabilityIdentity, ...] | None
    lost_confirmed_availability: tuple[CapabilityIdentity, ...] | None
    became_unassessed: tuple[CapabilityIdentity, ...] | None
    gross_additions: int | None = Field(ge=0)
    gross_losses: int | None = Field(ge=0)
    re_admissions: int | None = Field(ge=0)
    source_observation_count: int = Field(ge=0)
    service_use_count: int | None = Field(ge=0)
    copy_observation_count: int | None = Field(ge=0)
    import_observation_count: int | None = Field(ge=0)
    costs: tuple[CostObservation, ...] = Field(max_length=16384)
    cost_subtotals: tuple[CostSubtotal, ...] = Field(max_length=16384)
    functional_growth: Literal["not_estimated"] = "not_estimated"


class HandoffRole(StrEnum):
    GENERATE = "GENERATE"
    VERIFY = "VERIFY"
    REUSE = "REUSE"
    ACCOUNT = "ACCOUNT"
    REALLOCATE = "REALLOCATE"


class HandoffObservation(Report):
    source_role: HandoffRole
    target_role: HandoffRole
    producer: Identifier
    receiver: Identifier
    target: CapabilityIdentity
    state: Literal["proposed", "received", "assessed"]
    state_basis: RecordRef | None
    contract_identity: Identifier
    cost_refs: tuple[CostReference, ...] = Field(max_length=16384)
    admission: Literal["historical_only_unassessed_current"] = "historical_only_unassessed_current"
    authority: Literal["not_granted"] = "not_granted"
    disposition: Literal["review", "stop", "handoff"]


def record_identity(record: Record | Decision, owner: str) -> tuple[RecordKind, str, str]:
    if isinstance(record, Decision):
        return "decision", owner, record.id
    return (
        record.kind,
        record.issuer,
        record.subject.key if isinstance(record, Capability) else record.id,
    )


def _check_visible_cycles(items: tuple[ObservedRecord, ...]) -> None:
    """Reject cycles among supplied records only; never fetch transitive material."""
    graph: dict[str, set[str]] = {}
    for item in items:
        record = item.record
        if isinstance(record, Capability):
            key = projection_digest([record.issuer, record.subject.model_dump(mode="json")])
            graph[key] = {
                projection_digest([issuer, subject.model_dump(mode="json")])
                for issuer, subject in zip(
                    record.dependency_issuers, record.dependencies, strict=False
                )
            } | {
                projection_digest([f.issuer, f.subject.model_dump(mode="json")])
                for f in record.formation_inputs
            }
        elif isinstance(record, Event) and record.formation:
            key = projection_digest(["receipt", record.issuer, record.id])
            graph[key] = {
                projection_digest(["receipt", ref.issuer, ref.id])
                for ref in record.formation.receipts
            }
        elif isinstance(record, Evidence):
            # Legacy support links carry IDs without issuer qualification. Check
            # every visible matching ID conservatively; never invent provenance.
            key = projection_digest(["evidence", record.id])
            graph.setdefault(key, set()).update(
                projection_digest(["evidence", dependency])
                for dependency in record.evidence_dependencies
            )
    done: set[str] = set()
    visiting: set[str] = set()

    def visit(key: str) -> None:
        if key in visiting:
            raise ValueError("cyclic supplied lifecycle references")
        if key in done or key not in graph:
            return
        visiting.add(key)
        for child in graph[key]:
            visit(child)
        visiting.remove(key)
        done.add(key)

    for key in graph:
        visit(key)


def _unique(snapshot: LifecycleSnapshot) -> tuple[ObservedRecord, ...]:
    unique: dict[tuple[str, str, str], ObservedRecord] = {}
    for item in snapshot.records:
        ref = item.source.reference
        key = (ref.kind, ref.issuer, ref.id)
        old = unique.get(key)
        if old and old.source.reference != ref:
            raise Conflict("source identity content conflict")
        unique[key] = old or item
    return tuple(unique.values())


def _residual(
    context: ObservationContext,
    kind: ResidualKind,
    explanation: str,
    *,
    target: CapabilityIdentity | None = None,
    sources: tuple[RecordRef, ...] = (),
    prevents: tuple[str, ...] = (),
    next_check: str | None = None,
) -> Residual:
    return Residual(
        id=projection_digest(
            [
                kind,
                context.owner,
                context.receiver,
                context.scope.model_dump(mode="json") if context.scope else None,
                context.policy_digest,
                target.model_dump(mode="json") if target else None,
                [ref.model_dump(mode="json") for ref in sources],
                explanation,
                prevents,
            ]
        ),
        kind=kind,
        target=target,
        sources=sources,
        prevents=prevents,
        observed_at=context.observed_at,
        scope=context.scope,
        explanation=explanation,
        next_check=next_check,
    )


def _bounded[T: Report](report: T) -> T:
    if len(report.model_dump_json().encode()) > report.context.byte_limit:
        raise ValueError("derived view exceeds byte bound")
    return report


def snapshot_from_material(
    material: dict[str, Any],
    *,
    owner: str,
    caller: str,
    principals: dict[str, Principal] | None = None,
) -> LifecycleSnapshot:
    """Explicit finite input; host owner/caller and pins are not read from the file.

    ``unsigned`` entries are plainly labeled projections, useful for public
    synthetic examples. DSSE entries always require host-supplied public pins and
    verify original payload bytes. No URL/path is followed and no closure fetched.
    """
    if caller != owner:
        raise PermissionError("owner inspection authorization required")
    if (
        set(material) != {"view_schema_version", "context", "records"}
        or material["view_schema_version"] != "1"
    ):
        raise ValueError("unknown material schema or fields")
    validate_json_tree(material)
    if len(json.dumps(material).encode()) > MAX_VIEW_BYTES:
        raise ValueError("material byte bound exceeded")
    context = ObservationContext.model_validate(material["context"])
    if context.owner != owner:
        raise PermissionError("material owner mismatch")
    entries = material["records"]
    if not isinstance(entries, list) or len(entries) > context.record_limit:
        raise ValueError("material record bound exceeded")
    observed: list[ObservedRecord] = []
    for entry in entries:
        required = {"format", "document", "received_at", "sequence"}
        if not required <= set(entry) or set(entry) - required - {"reference"}:
            raise ValueError("unknown source fields")
        document = entry["document"]
        record: Record | Decision
        signature: Literal["historical_verified", "unsigned"]
        authority: Literal["unassessed", "compromised_key_observed", "unsigned"]
        basis: Literal["original_dsse_payload", "unsigned_json_projection"]
        if entry["format"] == "dsse":
            record, original_body, payload_hash = _decode_original(document, principals or {})
            signature = "historical_verified"
            principal = (principals or {})[record.issuer]
            authority = _historical_key_authority(document, principal)
            basis = "original_dsse_payload"
        elif entry["format"] == "unsigned":
            original_body = document
            record = (
                Decision.model_validate(document)
                if "request" in document
                else record_adapter.validate_python(document)
            )
            payload_hash = projection_digest(document)
            signature, authority, basis = "unsigned", "unsigned", "unsigned_json_projection"
        else:
            raise ValueError("unknown source format")
        supplied_ref = (
            RecordRef.model_validate(entry["reference"]) if "reference" in entry else None
        )
        claimed_owner = (
            supplied_ref.issuer if supplied_ref and isinstance(record, Decision) else owner
        )
        kind, issuer, rid = record_identity(record, claimed_owner)
        ref = RecordRef(kind=kind, issuer=issuer, id=rid, payload_digest=payload_hash)
        if supplied_ref is not None and supplied_ref != ref:
            raise ValueError("supplied original reference mismatch")
        occurred, defaults = original_record_metadata(record, original_body)
        observed.append(
            ObservedRecord(
                record=record,
                source=SourceObservation(
                    reference=ref,
                    payload_basis=basis,
                    signature=signature,
                    current_key_authority=authority,
                    occurred_at=occurred,
                    received_at=entry["received_at"],
                    sequence=entry["sequence"],
                    decoder_default_fields=defaults,
                ),
            )
        )
    return LifecycleSnapshot(context=context, records=tuple(observed))


def _target_matches(record: Record | Decision, target: CapabilityIdentity) -> bool:
    if isinstance(record, Decision):
        return (
            record.request.subject == target.subject
            and record.request.capability_issuer == target.issuer
            and record.request.binding_digest == target.binding_digest
        )
    if record.subject != target.subject:
        return False
    if isinstance(record, Capability):
        return record.issuer == target.issuer and record.binding_digest == target.binding_digest
    if isinstance(record, Evidence):
        return record.binding_digest == target.binding_digest
    if isinstance(record, Event) and record.execution:
        return (
            record.execution.capability_issuer == target.issuer
            and record.execution.binding_digest == target.binding_digest
        )
    if isinstance(record, Event) and record.formation:
        return (
            record.issuer == target.issuer
            and record.formation.binding_digest == target.binding_digest
        )
    return True  # subject-level legacy observation; its exact binding/issuer remains unassessed


def _costs(
    items: tuple[ObservedRecord, ...],
) -> tuple[tuple[CostObservation, ...], tuple[CostSubtotal, ...]]:
    costs: dict[str, CostObservation] = {}
    groups: dict[tuple[str, str, str, Literal["measured", "estimated"]], list[Decimal]] = (
        defaultdict(list)
    )
    for item in items:
        if not isinstance(item.record, Event):
            continue
        for position, cost in enumerate(item.record.costs):
            ref = CostReference(source=item.source.reference, position=position)
            wall = cost.unit in DURATION_UNITS
            observation = CostObservation(
                reference=ref,
                owner=item.record.issuer,
                cost=cost,
                occurred_at=item.source.occurred_at,
                duration_basis="inclusive_or_unspecified" if wall else "recorded_quantity",
            )
            if ref.key in costs:
                continue
            costs[ref.key] = observation
            if cost.quantity is not None and not wall and cost.status != "unavailable":
                groups[(item.record.issuer, cost.category, cost.unit, cost.status)].append(
                    cost.quantity
                )
    arithmetic = Context(prec=40)
    subtotals = []
    for (owner, category, unit, status), quantities in sorted(groups.items()):
        total = Decimal(0)
        for quantity in quantities:
            total = arithmetic.add(total, quantity)
        subtotals.append(
            CostSubtotal(
                owner=owner,
                category=category,
                unit=unit,
                status=status,
                quantity=total,
                observation_count=len(quantities),
            )
        )
    return tuple(costs.values()), tuple(subtotals)


def observe_contributions(snapshot: LifecycleSnapshot) -> tuple[ContributionObservation, ...]:
    """Recorded relations, deduplicated by original source and invocation identity."""
    results: list[ContributionObservation] = []
    unique = _unique(snapshot)
    receipt_sources = {
        (i.source.reference.issuer, i.source.reference.id): i
        for i in unique
        if isinstance(i.record, Event)
    }
    invocations: dict[tuple[str, str, str], str] = {}
    for item in unique:
        record, source = item.record, item.source
        refs = (
            tuple(
                CostReference(source=source.reference, position=i) for i in range(len(record.costs))
            )
            if isinstance(record, Event)
            else ()
        )
        relations: tuple[ContributionRelation, ...] = ()
        strength: Literal["declared", "observed", "unresolved"] = "observed"
        target: CapabilityIdentity | None = None
        receiver = None
        transport = None
        invocation = None
        outcome = None
        basis = ""
        inputs: list[CapabilityIdentity] = []
        receipt_links: list[RecordRef] = []
        missing_links: list[ReceiptRef] = []
        linked_inputs: list[tuple[CapabilityIdentity, SourceObservation]] = []
        if isinstance(record, Capability):
            target = CapabilityIdentity(
                issuer=record.issuer, subject=record.subject, binding_digest=record.binding_digest
            )
            relations = (ContributionRelation.NEW_CANDIDATE,)
            basis = "Exact candidate record observed; classification is a declaration, not novelty."
            if record.classification in {"replicated", "imported"}:
                relations += (
                    ContributionRelation.COPY
                    if record.classification == "replicated"
                    else ContributionRelation.IMPORT,
                )
                strength = "declared"
            inputs = [
                CapabilityIdentity(
                    issuer=f.issuer, subject=f.subject, binding_digest=f.binding_digest
                )
                for f in record.formation_inputs
            ]
        elif isinstance(record, Event):
            outcome = str(record.outcome) if record.outcome is not None else None
            if record.execution:
                e = record.execution
                target = CapabilityIdentity(
                    issuer=e.capability_issuer,
                    subject=record.subject,
                    binding_digest=e.binding_digest,
                )
                receiver, transport, invocation = e.caller, e.transport, e.invocation_id
                outcome = e.state
                purpose_observed = (
                    source.decoder_default_fields is not None
                    and "execution.purpose" not in source.decoder_default_fields
                )
                if e.state == "completed" and purpose_observed:
                    key = (e.resource_owner, e.caller, e.invocation_id)
                    identity = projection_digest(
                        [record.subject.model_dump(mode="json"), e.model_dump(mode="json")]
                    )
                    if key in invocations:
                        if invocations[key] != identity:
                            raise Conflict("invocation receipt content conflict")
                        continue
                    invocations[key] = identity
                if e.purpose == "reuse" and e.state == "completed":
                    relations = (ContributionRelation.REUSE,)
                    if purpose_observed:
                        basis = "Completed reuse receipt; no quality or installation inferred."
                    else:
                        strength = "unresolved"
                        basis = (
                            "Decoder reuse purpose is not observed in the original receipt; "
                            "reuse versus verification remains unresolved."
                        )
            elif record.action in {"replication", "import"}:
                relations = (
                    ContributionRelation.COPY
                    if record.action == "replication"
                    else ContributionRelation.IMPORT,
                )
                strength = "unresolved"
                basis = "Recorded action has no exact source/binding identity."
            elif record.formation:
                target = CapabilityIdentity(
                    issuer=record.issuer,
                    subject=record.subject,
                    binding_digest=record.formation.binding_digest,
                )
                relations = (ContributionRelation.FORMATION_INPUT,)
                strength = "declared" if record.formation.relationship == "declared" else "observed"
                basis = "Formation receipt links prior receipts; no causal effect inferred."
                for link in record.formation.receipts:
                    linked = receipt_sources.get((link.issuer, link.id))
                    linked_record = linked.record if linked else None
                    if (
                        not linked
                        or not isinstance(linked_record, Event)
                        or not linked_record.execution
                    ):
                        missing_links.append(link)
                        continue
                    execution = linked_record.execution
                    if (
                        execution.state != "completed"
                        or execution.purpose != "reuse"
                        or linked.source.decoder_default_fields is None
                        or "execution.purpose" in linked.source.decoder_default_fields
                    ):
                        missing_links.append(link)
                        continue
                    receipt_links.append(linked.source.reference)
                    linked_inputs.append(
                        (
                            CapabilityIdentity(
                                issuer=execution.capability_issuer,
                                subject=linked_record.subject,
                                binding_digest=execution.binding_digest,
                            ),
                            linked.source,
                        )
                    )
                if missing_links:
                    strength = "unresolved"
        if not relations:
            continue
        residual = _residual(
            snapshot.context,
            ResidualKind.UNKNOWN_CAUSALITY,
            "Functional novelty, causal credit and independent source origin are unassessed.",
            target=target,
            sources=(source.reference,),
            prevents=("causal_credit", "functional_growth"),
        )
        relation_residuals = [residual]
        if missing_links:
            relation_residuals.append(
                _residual(
                    snapshot.context,
                    ResidualKind.MISSING_HISTORY,
                    (
                        "Referenced formation receipts are unavailable or do not report "
                        "completed reuse."
                    ),
                    target=target,
                    sources=(source.reference,),
                    prevents=("observed_formation_inputs",),
                )
            )
        if strength == "unresolved" and not missing_links:
            relation_residuals.append(
                _residual(
                    snapshot.context,
                    ResidualKind.UNKNOWN_RELATION,
                    (
                        "Original execution purpose is absent; decoder reuse is not observed reuse."
                        if isinstance(record, Event) and record.execution
                        else (
                            "Exact source identity is absent; declared copy/import is not "
                            "resolved origin."
                        )
                    ),
                    target=target,
                    sources=(source.reference,),
                )
            )
        results.append(
            ContributionObservation(
                context=snapshot.context,
                sources=(source,),
                residuals=tuple(relation_residuals),
                observation_id=projection_digest(
                    [source.reference.model_dump(mode="json"), "record"]
                ),
                resulting_capability=target,
                source_capability=None,
                relations=relations,
                strength=strength,
                basis=basis,
                receiver=receiver,
                transport=transport,
                invocation_id=invocation,
                observed_outcome=outcome,
                cost_refs=refs,
                receipt_links=tuple(receipt_links),
                unavailable_receipt_links=tuple(missing_links),
            )
        )
        for input_target in inputs:
            results.append(
                ContributionObservation(
                    context=snapshot.context,
                    sources=(source,),
                    residuals=(residual,),
                    observation_id=projection_digest(
                        [source.reference.model_dump(mode="json"), input_target.key]
                    ),
                    resulting_capability=target,
                    source_capability=input_target,
                    relations=(ContributionRelation.FORMATION_INPUT,),
                    strength="declared",
                    basis="Declared construction input; no executed dependency or causal proof.",
                    receiver=snapshot.context.receiver,
                    cost_refs=refs,
                )
            )
        for input_target, linked_source in linked_inputs:
            results.append(
                ContributionObservation(
                    context=snapshot.context,
                    sources=(source, linked_source),
                    residuals=tuple(relation_residuals),
                    observation_id=projection_digest(
                        [
                            source.reference.model_dump(mode="json"),
                            linked_source.reference.model_dump(mode="json"),
                        ]
                    ),
                    resulting_capability=target,
                    source_capability=input_target,
                    relations=(ContributionRelation.FORMATION_INPUT,),
                    strength=strength,
                    basis="Formation link to completed reuse; no causal credit.",
                    receiver=receiver,
                    cost_refs=refs,
                    receipt_links=(linked_source.reference,),
                )
            )
    for result in results:
        _bounded(result)
    if (
        len(results) > 512
        or len(json.dumps([result.model_dump(mode="json") for result in results]).encode())
        > MAX_VIEW_BYTES
    ):
        raise ValueError("contribution aggregate bound exceeded")
    return tuple(results)


def inspect_lifecycle(
    snapshot: LifecycleSnapshot, target: CapabilityIdentity
) -> CapabilityLifecycleView:
    """Inspect an exact target without qualification, traversal or any I/O."""
    items = tuple(item for item in _unique(snapshot) if _target_matches(item.record, target))
    caps = [item.record for item in items if isinstance(item.record, Capability)]
    residuals: list[Residual] = []
    if snapshot.context.coverage != Coverage.COMPLETE:
        residuals.append(
            _residual(
                snapshot.context,
                ResidualKind.PARTIAL_SNAPSHOT,
                snapshot.context.coverage_basis,
                target=target,
                prevents=("complete_history", "exact_totals"),
            )
        )
    if not caps:
        residuals.append(
            _residual(
                snapshot.context,
                ResidualKind.MISSING_HISTORY,
                (
                    "Exact candidate is not present in the authorized finite material; absence "
                    "is not nonexistence."
                ),
                target=target,
            )
        )
    if target.binding_digest is None:
        residuals.append(
            _residual(
                snapshot.context,
                ResidualKind.AMBIGUOUS_IDENTITY,
                "Legacy binding identity is unavailable.",
                target=target,
                prevents=("binding_equivalence",),
            )
        )
    evidence = []
    decisions = []
    executions = []
    owner_observations = []
    withdrawals = []
    support: list[tuple[str, str]] = []
    for item in items:
        record, ref = item.record, item.source.reference
        if item.source.occurred_at is None:
            residuals.append(
                _residual(
                    snapshot.context,
                    ResidualKind.MISSING_HISTORY,
                    (
                        "Original occurrence/creation clock is absent; decoder defaults are "
                        "not observations."
                    ),
                    target=target,
                    sources=(ref,),
                    prevents=("source_time_order", "period_membership"),
                )
            )
        if item.source.current_key_authority == "compromised_key_observed":
            residuals.append(
                _residual(
                    snapshot.context,
                    ResidualKind.AUTHORITY_MISSING,
                    (
                        "Historical signature uses a currently compromised key; historical "
                        "bytes remain verified."
                    ),
                    target=target,
                    sources=(ref,),
                    prevents=("current_authority",),
                )
            )
        if isinstance(record, Evidence):
            evidence.append(
                {
                    "reference": ref.model_dump(mode="json"),
                    "verdict": record.verdict,
                    "method": record.method,
                    "verifier_version": record.verifier_version,
                    "scope": record.scope.model_dump(mode="json"),
                    "receivers": record.receivers,
                    "created_at": item.source.occurred_at.isoformat()
                    if item.source.occurred_at is not None
                    else None,
                    "expires_at": record.expires_at.isoformat(),
                    "expired_at_cutoff": record.expires_at <= snapshot.context.cutoff,
                    "binding_digest": record.binding_digest,
                }
            )
            support.extend((record.issuer, rid) for rid in record.evidence_dependencies)
        if isinstance(record, Decision):
            decisions.append(record)
            for reason in record.reasons:
                residuals.append(
                    _residual(
                        snapshot.context,
                        ResidualKind.UNMAPPED_REASON,
                        reason,
                        target=target,
                        sources=(ref,),
                    )
                )
        if isinstance(record, Event) and record.execution:
            executions.append(ExecutionObservation(source=ref, receipt=record.execution))
        if isinstance(record, Event):
            for name in ("invocation_observation", "reconciliation", "resolution", "work"):
                observation = getattr(record, name)
                if observation is not None:
                    owner_observations.append(
                        {
                            "source": ref.model_dump(mode="json"),
                            "kind": name,
                            "observation": observation.model_dump(mode="json"),
                        }
                    )
        if isinstance(record, Revocation):
            withdrawals.append(ref)
        expires = getattr(record, "expires_at", getattr(record, "valid_until", None))
        if (
            isinstance(record, Decision)
            and item.source.decoder_default_fields is not None
            and "valid_until" in item.source.decoder_default_fields
        ):
            expires = None
            residuals.append(
                _residual(
                    snapshot.context,
                    ResidualKind.MISSING_HISTORY,
                    "Original Decision validity is absent; decoder expiry is not an observation.",
                    target=target,
                    sources=(ref,),
                    prevents=("source_validity",),
                )
            )
        if expires and expires <= snapshot.context.cutoff:
            residuals.append(
                _residual(
                    snapshot.context,
                    ResidualKind.STALE_SOURCE,
                    "Recorded validity expired by this local cutoff; history is retained.",
                    target=target,
                    sources=(ref,),
                    prevents=("current_admission",),
                )
            )
        for obligation in getattr(record, "obligations", ()):
            residuals.append(
                _residual(
                    snapshot.context,
                    ResidualKind.RECORDED_OBLIGATION,
                    obligation,
                    target=target,
                    sources=(ref,),
                )
            )
        if isinstance(record, Event) and (
            record.execution
            and record.execution.state != "completed"
            or record.invocation_observation
            or record.reconciliation
            or record.resolution
        ):
            residuals.append(
                _residual(
                    snapshot.context,
                    ResidualKind.UNRESOLVED_EFFECT,
                    (
                        "Retained execution/owner observation is not a quality PASS, refund or "
                        "authorization; inspect the original resolution basis."
                    ),
                    target=target,
                    sources=(ref,),
                    prevents=("implicit_retry", "implicit_refund"),
                )
            )
    if not evidence:
        residuals.append(
            _residual(
                snapshot.context,
                ResidualKind.MISSING_EVIDENCE,
                "No matching evidence is observed in this bounded material.",
                target=target,
            )
        )
    residuals.append(
        _residual(
            snapshot.context,
            ResidualKind.AUTHORITY_MISSING,
            "Current use requires explicit qualification and the existing Executor use-time gate.",
            target=target,
            prevents=("execution_from_view",),
            next_check="Use existing qualification/Executor with host authority.",
        )
    )
    costs, subtotals = _costs(items)
    if not costs or any(c.cost.status == "unavailable" for c in costs):
        residuals.append(
            _residual(
                snapshot.context,
                ResidualKind.UNKNOWN_COST,
                (
                    "Costs are absent or explicitly unavailable; known subtotals are not full "
                    "consumption."
                ),
                target=target,
            )
        )
    if any(c.duration_basis == "inclusive_or_unspecified" for c in costs):
        residuals.append(
            _residual(
                snapshot.context,
                ResidualKind.INCOMPATIBLE_UNIT,
                (
                    "Inclusive/unspecified wall observations are listed, never added to nested "
                    "wall or other units."
                ),
                target=target,
            )
        )
    contributions = tuple(
        c
        for c in observe_contributions(snapshot)
        if c.resulting_capability == target
        or any(s.reference in {i.source.reference for i in items} for s in c.sources)
    )
    residuals.extend(r for c in contributions for r in c.residuals)
    visible_ids = {i.record.id for i in _unique(snapshot) if isinstance(i.record, Evidence)}
    needed_evidence = {eid for cap in caps for eid in cap.evidence} | {rid for _, rid in support}
    if needed_evidence - visible_ids:
        residuals.append(
            _residual(
                snapshot.context,
                ResidualKind.MISSING_EVIDENCE,
                (
                    "Referenced evidence/support is outside the authorized finite material; no "
                    "lookup performed."
                ),
                target=target,
                prevents=("complete_evidence_closure",),
            )
        )
    residuals = list({r.id: r for r in residuals}.values())
    runtime = tuple(
        CapabilityIdentity(issuer=cap.dependency_issuers[i], subject=subject, binding_digest=None)
        for cap in caps
        for i, subject in enumerate(cap.dependencies)
        if cap.dependency_issuers
    )
    formation = tuple(
        CapabilityIdentity(issuer=f.issuer, subject=f.subject, binding_digest=f.binding_digest)
        for cap in caps
        for f in cap.formation_inputs
    )
    if any(cap.dependencies and not cap.dependency_issuers for cap in caps):
        residuals.append(
            _residual(
                snapshot.context,
                ResidualKind.AMBIGUOUS_IDENTITY,
                (
                    "Legacy runtime dependency issuers are unavailable; no transitive source "
                    "lookup performed."
                ),
                target=target,
            )
        )
    return _bounded(
        CapabilityLifecycleView(
            context=snapshot.context,
            sources=tuple(i.source for i in items),
            residuals=tuple(residuals),
            target=target,
            candidate_observed=True if caps else None,
            generation_observed=True
            if any(isinstance(i.record, Event) and i.record.action == "formation" for i in items)
            else None,
            evidence=tuple(evidence),
            decisions=tuple(decisions),
            executions=tuple(executions),
            owner_observations=tuple(owner_observations),
            withdrawals=tuple(withdrawals),
            contributions=contributions,
            costs=costs,
            cost_subtotals=subtotals,
            runtime_dependencies=runtime,
            formation_inputs=formation,
            evidence_support=tuple(support),
        )
    )


async def assess_stock(overlay: Overlay, requests: tuple[UseRequest, ...]) -> StockObservation:
    """Explicitly creates current Decisions/cost observations via existing metrics.

    The bounded target universe and coordinates must be exact. Each evaluation has
    its own clock; the result is not an atomic replay of an earlier opening time.
    """
    from .accounting import capability_metrics

    if not requests or any(r.capability_issuer is None for r in requests):
        raise ValueError("stock assessment requires exact capability issuers")
    if len(requests) > 32:
        raise ValueError("stock assessment requires 1 to 32 explicit use requests")
    if any(r.scope != requests[0].scope or r.receiver != requests[0].receiver for r in requests):
        raise ValueError("stock assessment requires one receiver/scope coordinate")
    target_keys = {(r.capability_issuer, r.subject, r.binding_digest) for r in requests}
    if len(target_keys) != len(requests):
        raise ValueError("duplicate stock target")
    result = await capability_metrics(overlay, requests)
    policy: str = result["historical_reuse_policy_digest"]
    started = datetime.fromisoformat(result["started_at"])
    completed = datetime.fromisoformat(result["completed_at"])
    context = ObservationContext(
        owner=overlay.store.owner,
        receiver=requests[0].receiver,
        scope=requests[0].scope,
        policy_digest=policy,
        cutoff=completed,
        observed_at=completed,
        feed_generation=None,
        prefix=None,
        coverage=Coverage.COMPLETE if not result["inconsistent_targets"] else Coverage.INCONSISTENT,
        coverage_basis="Finite targets; per-target qualification, not atomic or global history.",
    )
    entries, sources, residuals = [], [], []
    for item in result["targets"]:
        decision = Decision.model_validate(item["decision"])
        request = decision.request
        assert request.capability_issuer is not None
        target = CapabilityIdentity(
            issuer=request.capability_issuer,
            subject=request.subject,
            binding_digest=request.binding_digest,
        )
        ref = RecordRef(
            kind="decision",
            issuer=context.owner,
            id=decision.id,
            payload_digest=projection_digest(item["decision"]),
        )
        availability: Availability = "unknown"
        if item["consistent"] and decision.evaluated_at <= completed < decision.valid_until:
            availability = (
                "accepted"
                if decision.outcome == "ACCEPT"
                else "nonaccepted"
                if decision.outcome == "REJECT"
                else "unknown"
            )
        entries.append(
            StockEntry(target=target, availability=availability, decision=decision, reference=ref)
        )
        sources.append(
            SourceObservation(
                reference=ref,
                payload_basis="unsigned_json_projection",
                signature="unsigned",
                current_key_authority="unsigned",
                occurred_at=decision.evaluated_at,
                received_at=None,
                sequence=None,
                decoder_default_fields=original_record_metadata(decision, item["decision"])[1],
            )
        )
        if availability == "unknown":
            residuals.append(
                _residual(
                    context,
                    ResidualKind.AUTHORITY_MISSING,
                    (
                        "This target's current availability is unassessed/inconsistent; not "
                        "confirmed functional loss."
                    ),
                    target=target,
                    sources=(ref,),
                )
            )
    coordinates = StockCoordinates(
        receiver=requests[0].receiver,
        scope=requests[0].scope,
        policy_digest=policy,
        target_universe=tuple(e.target for e in entries),
    )
    return _bounded(
        StockObservation(
            context=context,
            sources=tuple(sources),
            residuals=tuple(residuals),
            coordinates=coordinates,
            entries=tuple(entries),
            assessment_started_at=started,
            assessment_completed_at=completed,
        )
    )


def observe_growth(
    opening: StockObservation,
    closing: StockObservation,
    *,
    history: LifecycleSnapshot | None = None,
) -> GrowthObservation:
    """Compare independently retained endpoint observations in fixed coordinates."""
    context = closing.context
    residuals = list(opening.residuals + closing.residuals)

    def accepted(stock: StockObservation) -> dict[str, CapabilityIdentity]:
        return {e.target.key: e.target for e in stock.entries if e.availability == "accepted"}

    before, after = accepted(opening), accepted(closing)
    a = opening.coordinates.model_dump(mode="json")
    b = closing.coordinates.model_dump(mode="json")
    a["target_universe"] = sorted(a["target_universe"], key=projection_digest)
    b["target_universe"] = sorted(b["target_universe"], key=projection_digest)
    comparable = (
        a == b
        and opening.context.owner == context.owner
        and opening.context.coverage == context.coverage == Coverage.COMPLETE
        and opening.context.cutoff < context.cutoff
    )
    if not comparable:
        residuals.append(
            _residual(
                context,
                ResidualKind.POLICY_MISMATCH if a != b else ResidualKind.PARTIAL_SNAPSHOT,
                (
                    "Endpoint coordinates, order or declared local coverage do not support an "
                    "exact set reconciliation."
                ),
                prevents=("exact_net_change",),
            )
        )
    added = tuple(after[k] for k in sorted(after.keys() - before.keys())) if comparable else None
    lost = tuple(before[k] for k in sorted(before.keys() - after.keys())) if comparable else None
    closing_states = {e.target.key: e.availability for e in closing.entries}
    confirmed = (
        tuple(t for t in lost or () if closing_states[t.key] == "nonaccepted")
        if comparable
        else None
    )
    unassessed = (
        tuple(t for t in lost or () if closing_states[t.key] == "unknown") if comparable else None
    )
    if comparable:
        assert len(after) == len(before) + len(added or ()) - len(lost or ())
    history_matches = bool(
        history
        and history.context.owner == context.owner
        and history.context.receiver == closing.coordinates.receiver
        and history.context.scope == closing.coordinates.scope
        and history.context.policy_digest == closing.coordinates.policy_digest
        and history.context.period_start == opening.context.cutoff
        and history.context.period_end == history.context.cutoff == context.cutoff
    )
    all_items = _unique(history) if history else ()
    relevant_items = tuple(
        item
        for item in all_items
        if history_matches
        and any(
            _target_matches(item.record, target) for target in closing.coordinates.target_universe
        )
        and (
            getattr(item.record, "scope", closing.coordinates.scope) == closing.coordinates.scope
            if not isinstance(item.record, Decision)
            else (
                item.record.request.scope == closing.coordinates.scope
                and item.record.request.receiver == closing.coordinates.receiver
                and item.record.policy_digest == closing.coordinates.policy_digest
                and item.source.reference.issuer == closing.coordinates.receiver
            )
        )
        and (
            not isinstance(item.record, Event)
            or item.record.formation is None
            or (
                item.record.formation.scope == closing.coordinates.scope
                and item.record.formation.policy_digest == closing.coordinates.policy_digest
            )
        )
        and (
            not isinstance(item.record, Event)
            or item.record.work is None
            or (
                item.record.work.scope == closing.coordinates.scope
                and item.record.work.receiver == closing.coordinates.receiver
                and item.record.work.policy_digest == closing.coordinates.policy_digest
            )
        )
        and (
            not isinstance(item.record, Event)
            or item.record.execution is None
            or (
                item.record.execution.scope == closing.coordinates.scope
                and item.record.execution.caller == closing.coordinates.receiver
                and item.record.execution.policy_digest == closing.coordinates.policy_digest
            )
        )
    )
    period_clocks_complete = all(item.source.occurred_at is not None for item in relevant_items)
    items = tuple(
        item
        for item in relevant_items
        if item.source.occurred_at is not None
        and opening.context.cutoff <= item.source.occurred_at < context.cutoff
    )
    period_purposes_complete = all(
        not isinstance(item.record, Event)
        or item.record.execution is None
        or (
            item.source.decoder_default_fields is not None
            and "execution.purpose" not in item.source.decoder_default_fields
        )
        for item in items
    )
    if not period_purposes_complete:
        residuals.append(
            _residual(
                context,
                ResidualKind.UNKNOWN_RELATION,
                "Original execution purposes are absent; reuse versus verification is unknown.",
                prevents=("period_service_count",),
            )
        )
    if not period_clocks_complete:
        residuals.append(
            _residual(
                context,
                ResidualKind.MISSING_HISTORY,
                "Relevant original clocks are absent; period membership and totals are unknown.",
                sources=tuple(
                    item.source.reference
                    for item in relevant_items
                    if item.source.occurred_at is None
                ),
                prevents=("period_service_count", "period_costs", "gross_churn"),
            )
        )
    period_snapshot = LifecycleSnapshot(context=history.context, records=items) if history else None
    contributions = (
        observe_contributions(period_snapshot) if history_matches and period_snapshot else ()
    )
    costs, subtotals = _costs(items)
    if history and not history_matches:
        residuals.append(
            _residual(
                context,
                ResidualKind.POLICY_MISMATCH,
                "History coordinates/period differ; service and cost counts are unavailable.",
                prevents=("period_service_count", "period_costs", "gross_churn"),
            )
        )
    if not costs or any(c.cost.status == "unavailable" for c in costs):
        residuals.append(
            _residual(
                context,
                ResidualKind.UNKNOWN_COST,
                "Missing period costs remain unknown; subtotals are not full consumption.",
                prevents=("complete_consumption",),
            )
        )
    if any(c.duration_basis == "inclusive_or_unspecified" for c in costs):
        residuals.append(
            _residual(
                context,
                ResidualKind.INCOMPATIBLE_UNIT,
                "Inclusive wall observations are retained separately and never summed.",
            )
        )
    gross_additions = gross_losses = readmissions = None
    full_period = bool(
        history
        and comparable
        and history_matches
        and period_clocks_complete
        and history.context.coverage == Coverage.COMPLETE
        and history.context.owner == context.owner
        and history.context.receiver == closing.coordinates.receiver
        and history.context.scope == closing.coordinates.scope
        and history.context.policy_digest == closing.coordinates.policy_digest
        and history.context.period_start == opening.context.cutoff
        and history.context.period_end == context.cutoff
    )
    if full_period:
        gross = _gross_stock_changes(opening, closing, items)
        if gross is None:
            residuals.append(
                _residual(
                    context,
                    ResidualKind.MISSING_HISTORY,
                    (
                        "Period decisions do not reproduce closing states; "
                        "expiry/late/unobserved changes remain unresolved."
                    ),
                    prevents=("gross_churn",),
                )
            )
        else:
            gross_additions, gross_losses, readmissions = gross
    else:
        residuals.append(
            _residual(
                context,
                ResidualKind.MISSING_HISTORY,
                (
                    "Endpoint differences do not identify intermediate churn, re-admission or "
                    "complete costs."
                ),
                prevents=("gross_churn", "complete_consumption"),
            )
        )
    sources = {
        projection_digest(s.reference.model_dump(mode="json")): s
        for s in opening.sources + closing.sources + tuple(i.source for i in all_items)
    }
    residuals.extend(r for c in contributions for r in c.residuals)
    residuals = list({r.id: r for r in residuals}.values())
    return _bounded(
        GrowthObservation(
            context=context,
            sources=tuple(sources.values()),
            residuals=tuple(residuals),
            opening=opening,
            closing=closing,
            reconciled=True if comparable else None,
            opening_admitted_entry_count=len(before),
            closing_admitted_entry_count=len(after),
            opening_unknown_entry_count=sum(e.availability == "unknown" for e in opening.entries),
            closing_unknown_entry_count=sum(e.availability == "unknown" for e in closing.entries),
            history_context=history.context if history else None,
            entries_added_net=added,
            entries_lost_net=lost,
            lost_confirmed_availability=confirmed,
            became_unassessed=unassessed,
            gross_additions=gross_additions,
            gross_losses=gross_losses,
            re_admissions=readmissions,
            source_observation_count=len(all_items),
            service_use_count=sum(
                ContributionRelation.REUSE in c.relations and c.strength == "observed"
                for c in contributions
            )
            if history_matches and period_clocks_complete and period_purposes_complete
            else None,
            copy_observation_count=sum(
                ContributionRelation.COPY in c.relations for c in contributions
            )
            if history_matches and period_clocks_complete
            else None,
            import_observation_count=sum(
                ContributionRelation.IMPORT in c.relations for c in contributions
            )
            if history_matches and period_clocks_complete
            else None,
            costs=costs,
            cost_subtotals=subtotals,
        )
    )


def _gross_stock_changes(
    opening: StockObservation, closing: StockObservation, items: tuple[ObservedRecord, ...]
) -> tuple[int, int, int] | None:
    """Bounded owner-clock observations, including expiry; no execution state changes."""
    start, end = opening.context.cutoff, closing.context.cutoff
    states = {e.target.key: e.availability for e in opening.entries}
    active = {e.target.key: e.decision.id for e in opening.entries}
    ever = {key for key, state in states.items() if state == "accepted"}
    # kind 0 is expiration, kind 1 a new decision. A new decision at exactly an
    # old expiration can re-admit; expiration applies only to its still-active ID.
    timeline: list[tuple[datetime, int, int, str, str, Availability]] = []
    for entry in opening.entries:
        if entry.availability == "accepted" and start < entry.decision.valid_until <= end:
            timeline.append(
                (entry.decision.valid_until, 0, 0, entry.target.key, entry.decision.id, "unknown")
            )
    decision_times: dict[tuple[str, datetime], set[int | None]] = {}
    for item in items:
        d = item.record
        if not isinstance(d, Decision) or d.request.capability_issuer is None:
            continue
        t = CapabilityIdentity(
            issuer=d.request.capability_issuer,
            subject=d.request.subject,
            binding_digest=d.request.binding_digest,
        )
        if (
            t.key not in states
            or d.request.receiver != closing.coordinates.receiver
            or d.request.scope != closing.coordinates.scope
            or d.policy_digest != closing.coordinates.policy_digest
            or item.source.reference.issuer != closing.coordinates.receiver
            or not start <= d.evaluated_at < end
        ):
            continue
        if (
            item.source.decoder_default_fields is None
            or "valid_until" in item.source.decoder_default_fields
            or "request.purpose" in item.source.decoder_default_fields
        ):
            return None  # No inferred expiry or assessment purpose from decoder defaults.
        clock = (t.key, d.evaluated_at)
        sequences = decision_times.setdefault(clock, set())
        if sequences and (
            item.source.sequence is None or None in sequences or item.source.sequence in sequences
        ):
            return None  # No invented ordering of same-clock, unsequenced observations.
        sequences.add(item.source.sequence)
        value: Availability = (
            "accepted"
            if d.outcome == "ACCEPT" and d.valid_until > d.evaluated_at
            else "nonaccepted"
            if d.outcome == "REJECT"
            else "unknown"
        )
        timeline.append((d.evaluated_at, 1, item.source.sequence or 0, t.key, d.id, value))
        if value == "accepted" and start <= d.valid_until <= end:
            timeline.append((d.valid_until, 0, 0, t.key, d.id, "unknown"))
    additions = losses = readmissions = 0
    for _, kind, _, key, decision_id, value in sorted(timeline):
        if kind == 0 and active[key] != decision_id:
            continue
        old = states[key]
        if old != "accepted" and value == "accepted":
            additions += 1
            readmissions += int(key in ever)
            ever.add(key)
        if old == "accepted" and value != "accepted":
            losses += 1
        states[key], active[key] = value, decision_id
    if states != {e.target.key: e.availability for e in closing.entries}:
        return None
    return additions, losses, readmissions


def build_handoff(
    view: CapabilityLifecycleView,
    *,
    source_role: HandoffRole,
    target_role: HandoffRole,
    producer: str,
    receiver: str,
    contract_identity: str,
    state: Literal["proposed", "received", "assessed"] = "proposed",
    state_basis: RecordRef | None = None,
) -> HandoffObservation:
    """Read-only typed envelope; no stage, permission or execution is promoted."""
    visible = {s.reference for s in view.sources}
    if state != "proposed" and (state_basis is None or state_basis not in visible):
        raise ValueError("received/assessed handoff requires a visible exact basis")
    if state_basis is not None and state_basis not in visible:
        raise ValueError("handoff basis is outside authorized material")
    if state == "received" and not any(
        source.reference == state_basis and source.received_at is not None
        for source in view.sources
    ):
        raise ValueError("received handoff requires an observed local reception clock")
    if state == "received" and receiver != view.context.owner:
        raise ValueError("local reception does not prove another receiver received it")
    if state == "assessed":
        decision_sources = tuple(s for s in view.sources if s.reference.kind == "decision")
        if len(decision_sources) != len(view.decisions) or not any(
            source.reference == state_basis
            and source.reference.issuer == receiver
            and decision.id == source.reference.id
            and decision.request.receiver == receiver
            # inspect_lifecycle retains these streams in original source order.
            # Pairing avoids global-ID collisions and re-encoding original clocks.
            for source, decision in zip(decision_sources, view.decisions, strict=True)
        ):
            raise ValueError("assessed handoff requires that receiver's actual Decision")
    if (
        source_role == HandoffRole.REUSE
        and target_role == HandoffRole.ACCOUNT
        and not any(
            ContributionRelation.REUSE in contribution.relations
            and contribution.strength == "observed"
            and any(
                execution.source in {source.reference for source in contribution.sources}
                and execution.source.issuer == execution.receipt.resource_owner
                and execution.receipt.purpose == "reuse"
                and execution.receipt.state == "completed"
                and execution.receipt.capability_issuer == view.target.issuer
                and execution.receipt.binding_digest == view.target.binding_digest
                and (view.context.scope is None or execution.receipt.scope == view.context.scope)
                and (
                    view.context.receiver is None
                    or execution.receipt.caller == view.context.receiver
                )
                and (
                    view.context.policy_digest is None
                    or execution.receipt.policy_digest == view.context.policy_digest
                )
                for execution in view.executions
            )
            for contribution in view.contributions
        )
    ):
        raise ValueError("REUSE to ACCOUNT requires an actual reuse receipt")
    return _bounded(
        HandoffObservation(
            context=view.context,
            sources=view.sources,
            residuals=view.residuals,
            source_role=source_role,
            target_role=target_role,
            producer=producer,
            receiver=receiver,
            target=view.target,
            state=state,
            state_basis=state_basis,
            contract_identity=contract_identity,
            cost_refs=tuple(c.reference for c in view.costs),
            disposition="stop"
            if view.context.coverage in {Coverage.UNAVAILABLE, Coverage.INCONSISTENT}
            else "review"
            if view.residuals
            else "handoff",
        )
    )
