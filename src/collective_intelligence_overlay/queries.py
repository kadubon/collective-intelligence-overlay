"""Owner-local bounded inspection queries; cursors grant no execution authority."""

from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .models import Decision, Digest, Identifier, Record, Scope, Subject


class RecordQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kinds: tuple[Literal["capability", "evidence", "revocation", "event", "decision"], ...] = Field(
        default=("capability", "evidence", "revocation", "event"), min_length=1, max_length=4
    )
    issuer: Identifier | None = None
    subject: Subject | None = None
    scope: Scope | None = None
    policy_digest: Digest | None = None
    task_id: Identifier | None = None
    attempt_id: Identifier | None = None
    since: AwareDatetime | None = None
    until: AwareDatetime | None = None

    @model_validator(mode="after")
    def interval(self) -> Self:
        if "decision" in self.kinds and (
            self.kinds != ("decision",) or self.task_id or self.attempt_id
        ):
            raise ValueError("decision pages cannot mix record kinds or filter invocation tasks")
        if self.since and self.until and self.since >= self.until:
            raise ValueError("query period must be a nonempty half-open interval")
        return self


class RecordCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    owner: Identifier
    generation: str = Field(min_length=1, max_length=64)
    query_digest: Digest
    anchor: AwareDatetime
    after: int = Field(ge=0)
    upper: int = Field(ge=0)

    @model_validator(mode="after")
    def interval(self) -> Self:
        if self.after > self.upper:
            raise ValueError("cursor passed its snapshot upper bound")
        return self


class RecordPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    items: tuple[Record | Decision, ...]
    snapshot: RecordCursor
    next_cursor: RecordCursor | None
    encoded_bytes: int = Field(ge=0)
