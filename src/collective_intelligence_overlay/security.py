"""Pinned local identities and standard DSSE. No public transparency service."""

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from pydantic import TypeAdapter
from securesystemslib.dsse import Envelope
from securesystemslib.signer import CryptoSigner, Key  # type: ignore[attr-defined]

from .models import Capability, Event, Evidence, Record

PAYLOAD_TYPE = "application/vnd.collective-intelligence-overlay.record.v1+json"
PAYLOAD_TYPE_V2 = "application/vnd.collective-intelligence-overlay.record.v2+json"
PAYLOAD_TYPE_V3 = "application/vnd.collective-intelligence-overlay.record.v3+json"
PAYLOAD_TYPE_V4 = "application/vnd.collective-intelligence-overlay.record.v4+json"
MAX_RECORD_BYTES = 262144
record_adapter: TypeAdapter[Record] = TypeAdapter(Record)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Principal:
    key: Key
    trust_group: str
    methods: frozenset[str] = frozenset()
    historical_keys: tuple[Key, ...] = ()
    compromised_keyids: frozenset[str] = frozenset()


class Identity:
    def __init__(self, name: str, signer: CryptoSigner) -> None:
        self.name = name
        self.signer = signer

    def sign(self, record: Record) -> dict[str, Any]:
        if record.issuer != self.name:
            raise ValueError("issuer does not match signer")
        exclude = (
            {"binding_digest"}
            if isinstance(record, Capability | Evidence) and record.schema_version == "1"
            else set()
        )
        if isinstance(record, Event) and record.schema_version == "1":
            exclude = {"execution", "formation"}
        if isinstance(record, Event) and record.schema_version != "3":
            exclude.add("work")
        if isinstance(record, Event) and record.schema_version != "4":
            exclude.add("reconciliation")
        if isinstance(record, Capability) and record.schema_version == "1":
            exclude.add("dependency_issuers")
        if isinstance(record, Capability) and record.schema_version != "3":
            exclude.add("formation_inputs")
        payload_type = {
            "1": PAYLOAD_TYPE,
            "2": PAYLOAD_TYPE_V2,
            "3": PAYLOAD_TYPE_V3,
            "4": PAYLOAD_TYPE_V4,
        }[record.schema_version]
        envelope = Envelope(record.model_dump_json(exclude=exclude).encode(), payload_type, {})
        envelope.sign(self.signer)
        return envelope.to_dict()


def verify(
    envelope_data: dict[str, Any],
    principals: dict[str, Principal],
    *,
    require_authority: bool = True,
) -> Record:
    if len(json.dumps(envelope_data).encode()) > MAX_RECORD_BYTES:
        raise ValueError("record too large")
    envelope = Envelope.from_dict(copy.deepcopy(envelope_data))
    if envelope.payload_type not in {
        PAYLOAD_TYPE,
        PAYLOAD_TYPE_V2,
        PAYLOAD_TYPE_V3,
        PAYLOAD_TYPE_V4,
    }:
        raise ValueError("unsupported payload type")
    untrusted = json.loads(envelope.payload)
    if not isinstance(untrusted, dict) or not isinstance(untrusted.get("issuer"), str):
        raise ValueError("record issuer missing")
    principal = principals.get(untrusted["issuer"])
    if principal is None:
        raise ValueError("untrusted issuer")
    keys = [principal.key, *principal.historical_keys]
    if require_authority:
        keys = [key for key in keys if key.keyid not in principal.compromised_keyids]
    if not keys:
        raise ValueError("issuer has no uncompromised verification key")
    envelope.verify(keys, 1)
    record = record_adapter.validate_json(envelope.payload)
    expected = {
        "1": PAYLOAD_TYPE,
        "2": PAYLOAD_TYPE_V2,
        "3": PAYLOAD_TYPE_V3,
        "4": PAYLOAD_TYPE_V4,
    }[record.schema_version]
    if envelope.payload_type != expected:
        raise ValueError("record schema and DSSE media type differ")
    return record


def allowed_url(url: str, allowed: frozenset[str], *, local: bool = False) -> str:
    """Exact operator-maintained endpoints; never follow peer-supplied redirects."""
    parsed = urlsplit(url)
    if url not in allowed or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("endpoint not allowed")
    if parsed.scheme != "https":
        if not (local and parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "::1"}):
            raise ValueError("HTTPS required except explicit loopback development")
    return url
