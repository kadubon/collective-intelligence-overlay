"""Authenticated, bounded feed pages over the existing peer transport.

Tokens describe a source-declared committed prefix, not global truth or availability.
No cursor is stored in a signed business record.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    String,
    Table,
    Text,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .models import Cost, Event, Subject, now
from .security import Identity, Principal, digest, verify
from .storage import Conflict, Store, feed_state, metadata, projection_digest, records, subject_key

checkpoints = Table(
    "sync_checkpoints",
    metadata,
    Column("source", String(160), primary_key=True),
    Column("filter_digest", String(64), primary_key=True),
    Column("generation", String(64)),
    Column("through", BigInteger, nullable=False),
    Column("upper", BigInteger, nullable=False),
    Column("anchor", DateTime(timezone=True)),
    Column("cursor", Text),
    Column("complete", Boolean, nullable=False),
    Column("last_receipt", String(64)),
    Column("subjects", JSONB, nullable=False),
)


class FeedFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal["1"] = "1"
    subjects: tuple[Subject, ...] = Field(default=(), max_length=64)

    @property
    def digest(self) -> str:
        return projection_digest(sorted({subject_key(subject) for subject in self.subjects}))


class FeedPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    records: list[dict[str, Any]] = Field(max_length=128)
    receipt: str = Field(max_length=16384)
    next_cursor: str | None = Field(default=None, max_length=16384)


class ResnapshotRequired(ValueError):
    """An expired cursor or changed feed generation needs explicit snapshot restart."""


def decode_token(token: str, principal: Principal, source: str, receiver: str) -> dict[str, Any]:
    key = Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(principal.key.to_dict()["keyval"]["public"])
    )
    try:
        result: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=["EdDSA"],
            issuer=source,
            audience=receiver,
            options={"require": ["iss", "aud", "iat", "exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise ResnapshotRequired("feed token expired; restart snapshot explicitly") from exc
    if result.get("sub") != receiver or result["exp"] - result["iat"] > 1800:
        raise ValueError("invalid feed token scope")
    return result


class Feed:
    def __init__(self, store: Store, identity: Identity) -> None:
        if store.owner != identity.name:
            raise ValueError("feed signer must own the store")
        self.store, self.identity = store, identity

    def _token(self, claims: dict[str, Any]) -> str:
        return jwt.encode(claims, self.identity.signer.private_bytes, algorithm="EdDSA")

    def page(
        self,
        receiver: str,
        filter: FeedFilter,
        *,
        cursor: str | None = None,
        since: int = 0,
        generation: str | None = None,
        limit: int = 32,
        byte_limit: int = 196608,
    ) -> FeedPage:
        if receiver not in self.store.principals:
            raise ValueError("unknown feed receiver")
        if not 1 <= limit <= 128 or not 8192 <= byte_limit <= 196608 or since < 0:
            raise ValueError("invalid feed page bound")
        with self.store.engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as conn:
            with conn.begin():
                state = (
                    conn.execute(select(feed_state).where(feed_state.c.id == 1)).mappings().one()
                )
                if cursor:
                    claims = decode_token(
                        cursor, self.store.principals[self.store.owner], self.store.owner, receiver
                    )
                    if claims.get("type") != "cursor" or claims.get("filter") != filter.digest:
                        raise ValueError("cursor belongs to another operation or filter")
                    if claims.get("generation") != state["generation"]:
                        raise ResnapshotRequired("feed generation changed")
                    after, upper = claims["after"], claims["upper"]
                    if upper > state["sequence"]:
                        raise ResnapshotRequired("feed prefix was restored or truncated")
                else:
                    if (
                        generation is not None and generation != state["generation"]
                    ) or since > state["sequence"]:
                        raise ResnapshotRequired("feed checkpoint no longer exists")
                    if since and generation is None:
                        raise ValueError("delta checkpoint must include generation")
                    timestamp = now()
                    after, upper = since, state["sequence"]
                    claims = {
                        "iss": self.store.owner,
                        "aud": receiver,
                        "sub": receiver,
                        "iat": int(timestamp.timestamp()),
                        "exp": int((timestamp + timedelta(minutes=30)).timestamp()),
                        "anchor": timestamp.isoformat(),
                        "generation": state["generation"],
                        "filter": filter.digest,
                        "upper": upper,
                    }
                if not isinstance(after, int) or not 0 <= after <= upper:
                    raise ValueError("invalid feed interval")
                condition = (
                    (records.c.issuer == self.store.owner)
                    & (records.c.kind != "event")
                    & (records.c.sequence > after)
                    & (records.c.sequence <= upper)
                )
                if filter.subjects:
                    # Include all withdrawals even if an old record gave an
                    # inconsistent subject alongside its authoritative evidence id.
                    condition &= or_(
                        records.c.kind == "revocation",
                        records.c.subject_key.in_(
                            [subject_key(subject) for subject in filter.subjects]
                        ),
                    )
                candidates: Any = conn.execute(
                    select(records.c.sequence, records.c.envelope)
                    .where(condition)
                    .order_by(records.c.sequence)
                    .limit(limit + 1)
                ).all()
                chosen: list[dict[str, Any]] = []
                sequences: list[int] = []
                used = 0
                for sequence, envelope in candidates[:limit]:
                    size = len(json.dumps(envelope).encode())
                    if size > byte_limit:
                        raise ValueError("one record exceeds page byte bound; cannot skip it")
                    if used + size > byte_limit:
                        break
                    chosen.append(envelope)
                    sequences.append(int(sequence))
                    used += size
                complete = len(chosen) == len(candidates)
                through = upper if complete else sequences[-1]
                receipt = {
                    **claims,
                    "type": "page",
                    "after": after,
                    "through": through,
                    "complete": complete,
                    "sequences": sequences,
                    "records_hash": projection_digest(chosen),
                }
                next_cursor = (
                    None
                    if complete
                    else self._token(
                        {
                            **claims,
                            "type": "cursor",
                            "after": through,
                        }
                    )
                )
                result = FeedPage(
                    records=chosen, receipt=self._token(receipt), next_cursor=next_cursor
                )
                if len(result.model_dump_json().encode()) > 262144:
                    raise ValueError("complete page exceeds transport bound")
                return result


def verify_page(
    page: FeedPage, principal: Principal, source: str, receiver: str, filter: FeedFilter
) -> dict[str, Any]:
    claims = decode_token(page.receipt, principal, source, receiver)
    if claims.get("type") != "page" or claims.get("filter") != filter.digest:
        raise ValueError("page source/scope mismatch")
    if claims.get("records_hash") != projection_digest(page.records):
        raise ValueError("feed page record set changed")
    sequences = claims["sequences"]
    if (
        len(sequences) != len(page.records)
        or sequences != sorted(set(sequences))
        or any(not claims["after"] < seq <= claims["through"] for seq in sequences)
        or not 0 <= claims["after"] <= claims["through"] <= claims["upper"]
    ):
        raise ValueError("invalid feed prefix")
    if claims["complete"]:
        if page.next_cursor is not None or claims["through"] != claims["upper"]:
            raise ValueError("invalid completed feed prefix")
    else:
        if not page.next_cursor or not sequences or claims["through"] != sequences[-1]:
            raise ValueError("nonterminal page did not advance")
        cursor = decode_token(page.next_cursor, principal, source, receiver)
        if cursor.get("type") != "cursor":
            raise ValueError("next token is not a continuation cursor")
        if (
            any(
                cursor.get(key) != claims.get(key)
                for key in ("generation", "upper", "filter", "anchor", "iat", "exp")
            )
            or cursor.get("after") != claims["through"]
        ):
            raise ValueError("cursor does not continue this page")
    return claims


class Receiver:
    """Atomic import/checkpoint and restart support for one owner database."""

    def __init__(self, store: Store) -> None:
        self.store = store

    def checkpoint(self, source: str, filter: FeedFilter) -> dict[str, Any] | None:
        with self.store.engine.connect() as conn:
            row = (
                conn.execute(
                    select(checkpoints).where(
                        (checkpoints.c.source == source)
                        & (checkpoints.c.filter_digest == filter.digest)
                    )
                )
                .mappings()
                .one_or_none()
            )
        return dict(row) if row else None

    def begin(self, source: str, filter: FeedFilter) -> None:
        """Invalidate freshness before network IO; retain the durable continuation."""
        with self.store.engine.begin() as conn:
            conn.execute(
                pg_insert(checkpoints)
                .values(
                    source=source,
                    filter_digest=filter.digest,
                    through=0,
                    upper=0,
                    complete=False,
                    subjects=[subject_key(s) for s in filter.subjects],
                )
                .on_conflict_do_update(
                    index_elements=["source", "filter_digest"], set_={"complete": False}
                )
            )

    def observations(self, keys: set[str]) -> dict[str, datetime | None]:
        with self.store.engine.connect() as conn:
            rows = (
                conn.execute(
                    select(checkpoints)
                    .where(
                        or_(
                            checkpoints.c.filter_digest == FeedFilter().digest,
                            *[checkpoints.c.subjects.contains([key]) for key in keys],
                        )
                    )
                    .limit(2049)
                )
                .mappings()
                .all()
            )
        if len(rows) > 2048:
            raise ValueError("related synchronization scope bound exceeded")
        result: dict[str, datetime | None] = {}
        for key in keys:
            for source in self.store.principals:
                applicable = [
                    r
                    for r in rows
                    if r["source"] == source and (not r["subjects"] or key in r["subjects"])
                ]
                anchors = [r["anchor"] for r in applicable if r["complete"] and r["anchor"]]
                result[source + ":" + key] = (
                    max(anchors) if anchors and all(r["complete"] for r in applicable) else None
                )
        return result

    def restart(self, source: str, filter: FeedFilter) -> None:
        """Explicitly discard transport progress, never received records or tombstones."""
        with self.store.engine.begin() as conn:
            conn.execute(
                pg_insert(checkpoints)
                .values(
                    source=source,
                    filter_digest=filter.digest,
                    through=0,
                    upper=0,
                    complete=False,
                    subjects=[subject_key(s) for s in filter.subjects],
                )
                .on_conflict_do_update(
                    index_elements=["source", "filter_digest"],
                    set_={
                        "generation": None,
                        "through": 0,
                        "upper": 0,
                        "anchor": None,
                        "cursor": None,
                        "complete": False,
                        "last_receipt": None,
                    },
                )
            )

    def apply(
        self,
        source: str,
        filter: FeedFilter,
        page: FeedPage,
        *,
        identity: Identity | None = None,
        network_seconds: Decimal | None = None,
    ) -> bool:
        principal = self.store.principals.get(source)
        if principal is None:
            raise ValueError("untrusted synchronization source")
        claims = verify_page(page, principal, source, self.store.owner, filter)
        checked = [(verify(envelope, self.store.principals), envelope) for envelope in page.records]
        keys = {subject_key(subject) for subject in filter.subjects}
        for record, _ in checked:
            if record.issuer != source:
                raise ValueError("relay records cannot establish original issuer freshness")
            if record.kind == "event" or (
                keys and record.kind != "revocation" and subject_key(record.subject) not in keys
            ):
                raise ValueError("record outside synchronized filter")
        anchor = datetime.fromisoformat(claims["anchor"])
        if anchor.tzinfo is None or anchor > now():
            raise ValueError("invalid snapshot time")
        receipt_hash = digest(page.receipt.encode())
        transfer = None
        if identity is not None:
            if identity.name != self.store.owner or network_seconds is None:
                raise ValueError("transfer accounting must belong to the receiver")
            if checked:
                transfer = Event(
                    id="transfer-" + receipt_hash,
                    issuer=self.store.owner,
                    subject=checked[0][0].subject,
                    action="import",
                    task_id="sync/" + source,
                    attempt_id=receipt_hash,
                    correlation_id=filter.digest,
                    costs=(
                        Cost(
                            category="transfer",
                            status="measured",
                            quantity=network_seconds,
                            unit="wall_seconds",
                        ),
                    ),
                )
        selector = (checkpoints.c.source == source) & (checkpoints.c.filter_digest == filter.digest)
        with self.store.engine.begin() as conn:
            conn.execute(
                pg_insert(checkpoints)
                .values(
                    source=source,
                    filter_digest=filter.digest,
                    through=0,
                    upper=0,
                    complete=False,
                    subjects=[subject_key(s) for s in filter.subjects],
                )
                .on_conflict_do_nothing()
            )
            state = (
                conn.execute(select(checkpoints).where(selector).with_for_update()).mappings().one()
            )
            if state["last_receipt"] == receipt_hash:
                return False
            if state["generation"] is not None and state["generation"] != claims["generation"]:
                raise ResnapshotRequired("receiver checkpoint generation changed")
            if state["through"] != claims["after"]:
                raise Conflict("page does not continue committed receiver checkpoint")
            if state["cursor"] is not None and (
                state["upper"] != claims["upper"] or state["anchor"] != anchor
            ):
                raise Conflict("page changed the pending snapshot")
            if state["anchor"] is not None and anchor < state["anchor"]:
                raise Conflict("old snapshot cannot refresh the receiver")
            for record, envelope in checked:
                self.store._insert(conn, record, envelope)
            if transfer is not None and identity is not None:
                self.store._insert(conn, transfer, identity.sign(transfer))
            conn.execute(
                update(checkpoints)
                .where(selector)
                .values(
                    generation=claims["generation"],
                    through=claims["through"],
                    upper=claims["upper"],
                    anchor=anchor,
                    cursor=page.next_cursor,
                    complete=claims["complete"],
                    last_receipt=receipt_hash,
                    subjects=[subject_key(s) for s in filter.subjects],
                )
            )
        return True

    def freshness(self, source: str, filter: FeedFilter) -> datetime | None:
        state = self.checkpoint(source, filter)
        return state["anchor"] if state and state["complete"] else None
