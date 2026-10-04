"""Owner-authorized Store bridge for finite lifecycle inspection; no new storage."""

from __future__ import annotations

import base64
import json
from time import monotonic
from typing import Any

from sqlalchemy import and_, or_, select

from ._lifecycle_json import check_json_bytes, load_json
from .lifecycle import (
    CapabilityIdentity,
    Coverage,
    LifecycleSnapshot,
    ObservationContext,
    ObservedRecord,
    SourceObservation,
    original_record_metadata,
    record_identity,
)
from .models import Decision, now
from .queries import RecordCursor, RecordQuery
from .security import digest, verify
from .storage import Store, decisions, projection_digest, records, subject_key


def _check_deadline(started: float) -> None:
    if monotonic() - started > 5:
        raise TimeoutError("lifecycle read/export exceeded its five-second operation bound")


def read_lifecycle_page(
    store: Store,
    target: CapabilityIdentity | None = None,
    *,
    caller: str,
    receiver: str | None = None,
    record_cursor: RecordCursor | None = None,
    decision_cursor: RecordCursor | None = None,
    limit: int = 128,
    byte_limit: int = 1048576,
) -> LifecycleSnapshot:
    """Two pages share one committed prefix; coverage describes only these pages.

    Uses existing owner inspection access. Foreign peers must use the existing
    filtered Feed/export path, never this owner-local method. No related URL,
    dependency or private record is followed. Cursors preserve the original
    cutoff/query across pages; a source revision change is explicitly inconsistent.
    """
    if caller != store.owner:
        raise PermissionError("owner inspection authorization required")
    started = monotonic()
    if not 2 <= limit <= 256 or not 4096 <= byte_limit <= 1048576:
        raise ValueError("invalid lifecycle page bound")
    query = RecordQuery(subject=target.subject if target else None)
    dquery = RecordQuery(kinds=("decision",), subject=target.subject if target else None)
    continuing = record_cursor is not None or decision_cursor is not None
    if record_cursor is None and decision_cursor is not None:
        record_cursor = RecordCursor(
            owner=store.owner,
            generation=decision_cursor.generation,
            query_digest=projection_digest(query.model_dump(mode="json")),
            anchor=decision_cursor.anchor,
            after=decision_cursor.upper,
            upper=decision_cursor.upper,
        )
    keys = {subject_key(target.subject)} if target else set()
    before = store.revisions(keys)
    page = store.record_page(
        query, cursor=record_cursor, limit=limit // 2, byte_limit=byte_limit // 2
    )
    base = page.snapshot
    if decision_cursor is None:
        decision_cursor = RecordCursor(
            owner=store.owner,
            generation=base.generation,
            query_digest=projection_digest(dquery.model_dump(mode="json")),
            anchor=base.anchor,
            after=base.upper if continuing else 0,
            upper=base.upper,
        )
    if (decision_cursor.generation, decision_cursor.upper, decision_cursor.anchor) != (
        base.generation,
        base.upper,
        base.anchor,
    ):
        raise ValueError("lifecycle cursors must share generation, prefix and local cutoff")
    dpage = store.record_page(
        dquery, cursor=decision_cursor, limit=limit - limit // 2, byte_limit=byte_limit // 2
    )
    items = page.items + dpage.items
    refs = []
    for item in items:
        _check_deadline(started)
        refs.append(store.reference(*record_identity(item, store.owner)))
    signed_refs = [ref for ref in refs if ref.kind != "decision"]
    by_key: dict[tuple[str, str, str], Any] = {}
    drows: dict[str, Any] = {}
    # Only original visible record identities are loaded. In particular no
    # transitive lookup grants access to a not-yet-shared peer record.
    with store.engine.connect() as conn:
        if signed_refs:
            rows = conn.execute(
                select(records).where(
                    or_(
                        *(
                            and_(
                                records.c.kind == ref.kind,
                                records.c.issuer == ref.issuer,
                                records.c.record_id == ref.id,
                                records.c.sequence <= base.upper,
                            )
                            for ref in signed_refs
                        )
                    )
                )
            ).mappings()
            by_key = {(row["kind"], row["issuer"], row["record_id"]): row for row in rows}
        if any(ref.kind == "decision" for ref in refs):
            drows = {
                row["id"]: row
                for row in conn.execute(
                    select(decisions).where(
                        decisions.c.id.in_([ref.id for ref in refs if ref.kind == "decision"]),
                        decisions.c.sequence <= base.upper,
                    )
                ).mappings()
            }
    observations = []
    for item, ref in zip(items, refs, strict=True):
        _check_deadline(started)
        if isinstance(item, Decision):
            row = drows[ref.id]
            if projection_digest(row["body"]) != ref.payload_digest:
                raise ValueError("decision projection changed")
            item = Decision.model_validate(row["body"])
            occurred, defaults = original_record_metadata(item, row["body"])
            source = SourceObservation(
                reference=ref,
                payload_basis="unsigned_json_projection",
                signature="unsigned",
                current_key_authority="unsigned",
                occurred_at=occurred,
                received_at=None,
                sequence=row["sequence"],
                decoder_default_fields=defaults,
            )
        else:
            row = by_key[ref.kind, ref.issuer, ref.id]
            envelope = row["envelope"]
            payload = base64.b64decode(envelope["payload"], validate=True)
            check_json_bytes(payload)
            verified = verify(envelope, store.principals, require_authority=False)
            original_body = load_json(payload)
            if (
                record_identity(verified, store.owner) != (ref.kind, ref.issuer, ref.id)
                or digest(payload) != ref.payload_digest
                or original_body != row["body"]
            ):
                raise ValueError("original payload mismatch")
            # Separate decodes can generate different legacy defaults. Use the
            # verified original, rather than comparing or adopting those defaults.
            item = verified
            occurred, defaults = original_record_metadata(item, original_body)
            principal = store.principals[item.issuer]
            compromised = any(
                s["keyid"] in principal.compromised_keyids for s in envelope["signatures"]
            )
            source = SourceObservation(
                reference=ref,
                payload_basis="original_dsse_payload",
                signature="historical_verified",
                current_key_authority="compromised_key_observed" if compromised else "unassessed",
                occurred_at=occurred,
                received_at=row["received_at"],
                sequence=row["sequence"],
                decoder_default_fields=defaults,
            )
        observations.append(ObservedRecord(record=item, source=source))
    after = store.revisions(keys)
    # A final existing cursor check catches a concurrent restore/generation change.
    store.record_page(query, cursor=base.model_copy(update={"after": base.upper}), limit=1)
    _check_deadline(started)
    coverage = (
        Coverage.INCONSISTENT
        if before != after
        else Coverage.PARTIAL
        if (record_cursor is not None or page.next_cursor or dpage.next_cursor or target is None)
        else Coverage.COMPLETE
    )
    observed = now()
    context = ObservationContext(
        owner=store.owner,
        receiver=receiver,
        scope=None,
        policy_digest=None,
        cutoff=base.anchor,
        observed_at=observed,
        feed_generation=base.generation,
        prefix=base.upper,
        revisions=before,
        coverage=coverage,
        coverage_basis=(
            "Owner-local committed subject prefix; exhaustion is not world history. "
            "Related revision changes are inconsistent."
        ),
        query=query,
        record_cursor=page.next_cursor,
        decision_cursor=dpage.next_cursor,
        record_limit=limit,
        byte_limit=byte_limit,
    )
    return LifecycleSnapshot(context=context, records=tuple(observations))


def export_originals(store: Store, references: tuple[Any, ...], *, caller: str) -> dict[str, Any]:
    """Explicit owner export of exact finite references; never redact signed bytes.

    Signed payload bytes are in the original DSSE envelopes. The database retains
    envelope JSON, not its original transport whitespace. Decisions remain unsigned.
    """
    from .models import RecordRef

    if caller != store.owner:
        raise PermissionError("owner export authorization required")
    started = monotonic()
    if not 1 <= len(references) <= 256 or any(not isinstance(ref, RecordRef) for ref in references):
        raise ValueError("invalid original export bound or reference")
    unique = {projection_digest(ref.model_dump(mode="json")): ref for ref in references}
    for ref in unique.values():
        _check_deadline(started)
        store.resolve_reference(ref)  # Existing digest/signature/owner check, no fallback.
    exported = []
    document: Any
    with store.engine.connect() as conn:
        for ref in unique.values():
            _check_deadline(started)
            if ref.kind == "decision":
                document = conn.execute(
                    select(decisions.c.body).where(decisions.c.id == ref.id)
                ).scalar_one()
                exported.append(
                    {
                        "reference": ref.model_dump(mode="json"),
                        "format": "unsigned",
                        "document": document,
                    }
                )
            else:
                document = conn.execute(
                    select(records.c.envelope).where(
                        records.c.kind == ref.kind,
                        records.c.issuer == ref.issuer,
                        records.c.record_id == ref.id,
                    )
                ).scalar_one()
                exported.append(
                    {
                        "reference": ref.model_dump(mode="json"),
                        "format": "dsse",
                        "document": document,
                    }
                )
    result = {
        "export_schema_version": "1",
        "owner": store.owner,
        "records": exported,
        "non_claim": "Explicit authorized originals, not semantic truth or downstream credentials.",
    }
    if len(json.dumps(result).encode()) > 1048576:
        raise ValueError("original export byte bound exceeded")
    _check_deadline(started)
    return result
