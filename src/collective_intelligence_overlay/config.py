"""Operator-owned configuration; credentials are referenced by local path."""

import json
import ssl
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.serialization import load_pem_private_key
from pydantic import Field, SecretStr
from securesystemslib.signer import CryptoSigner, Key  # type: ignore[attr-defined]

from .models import Identifier, Model
from .overlay import Overlay
from .policy import Policy, PolicySettings
from .security import Identity, Principal, allowed_url
from .storage import Store


class Peer(Model):
    identity: Identifier
    url: str


class TrustedIdentity(Model):
    keyid: str
    key: dict[str, Any]
    trust_group: Identifier
    methods: tuple[Identifier, ...] = ()


class Config(Model):
    owner: Identifier
    database_url: SecretStr
    private_key: Path
    artifact_directory: Path
    opa_binary: str
    url: str
    local_development: bool = False
    share_records: bool = False
    peers: tuple[Peer, ...] = Field(default=(), max_length=64)
    identities: dict[Identifier, TrustedIdentity] = Field(max_length=128)
    policy: PolicySettings = Field(default_factory=PolicySettings)
    max_concurrency: int = Field(default=4, ge=1, le=32)
    max_unresolved: int = Field(default=32, ge=1, le=1024)
    max_steps: int = Field(default=20, ge=1, le=1000)
    max_children: int = Field(default=4, ge=0, le=32)
    max_rechecks: int = Field(default=2, ge=0, le=10)
    max_seconds: int = Field(default=120, ge=1, le=3600)
    execution_environment: dict[Identifier, Identifier] = Field(default_factory=dict, max_length=64)
    application: str | None = Field(default=None, max_length=256)
    application_settings: Path | None = None
    listen_port: int | None = Field(default=None, ge=1024, le=65535)
    tls_ca_certificate: Path | None = None

    def tls_context(self) -> ssl.SSLContext:
        """System trust or an explicit operator CA; hostname verification stays on."""
        return ssl.create_default_context(cafile=self.tls_ca_certificate)

    def runtime(self) -> tuple[Identity, Overlay]:
        allowed_url(self.url, frozenset({self.url}), local=self.local_development)
        for peer in self.peers:
            allowed_url(peer.url, frozenset({peer.url}), local=self.local_development)
            if peer.identity not in self.identities:
                raise ValueError("peer is not pinned")
        principals = {
            name: Principal(
                Key.from_dict(item.keyid, dict(item.key)), item.trust_group, frozenset(item.methods)
            )
            for name, item in self.identities.items()
        }
        key = load_pem_private_key(self.private_key.read_bytes(), password=None)
        signer = CryptoSigner(key)
        if self.owner not in principals or signer.public_key != principals[self.owner].key:
            raise ValueError("private key does not match configured owner")
        identity = Identity(self.owner, signer)
        return identity, Overlay(
            Store(self.database_url.get_secret_value(), self.owner, principals),
            Policy(self.opa_binary, self.policy),
            persistent_sources=True,
        )


def load_config(path: Path) -> Config:
    if path.stat().st_size > 262144:
        raise ValueError("configuration too large")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("configuration must be an object")
    # The installed setup writes public metadata separately from its secret DSN.
    # Legacy single-file configurations continue to work. No environment expansion
    # or remote secret loading is implicit.
    secret_path = data.pop("database_url_file", None)
    if secret_path is not None:
        if "database_url" in data or not isinstance(secret_path, str):
            raise ValueError("ambiguous database credential source")
        source = Path(secret_path)
        if not source.is_absolute():
            source = path.resolve().parent / source
        if source.stat().st_size > 8192:
            raise ValueError("database credential file too large")
        data["database_url"] = source.read_text(encoding="utf-8").strip()
    for name in ("private_key", "artifact_directory", "application_settings", "tls_ca_certificate"):
        if data.get(name) is not None:
            value = Path(data[name])
            if not value.is_absolute():
                data[name] = path.resolve().parent / value
    return Config.model_validate(data)
