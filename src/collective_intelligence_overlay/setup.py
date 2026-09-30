"""Explicit installed-package onboarding; never download or create a DB on import."""

import json
import os
import re
from decimal import Decimal
from importlib.resources import files
from pathlib import Path
from typing import Any

from pydantic import SecretStr
from securesystemslib.signer import CryptoSigner  # type: ignore[attr-defined]

from .config import Config, Peer, TrustedIdentity
from .security import allowed_url
from .storage import Store, migrate


def initialize(
    directory: Path,
    *,
    owner: str,
    url: str,
    database_url: str,
    opa: str,
    application: str | None = None,
    listen_port: int = 8000,
) -> Path:
    """Create an owner home for an existing restricted database, without overwrite.

    Database bootstrap/migration are separate explicit operator actions. The DSN
    and private key stay outside the public config and identity document.
    """
    allowed_url(url, frozenset({url}))
    # Validate before creating files, including owner/schema/DSN driver constraints.
    signer = CryptoSigner.generate_ed25519()
    entry = TrustedIdentity(
        keyid=signer.public_key.keyid, key=signer.public_key.to_dict(), trust_group=owner
    )
    config = Config(
        owner=owner,
        url=url,
        database_url=SecretStr(database_url),
        opa_binary=opa,
        private_key=Path("identity.pem"),
        artifact_directory=Path("artifacts"),
        application=application,
        listen_port=listen_port,
        identities={owner: entry},
        peers=(Peer(identity=owner, url=url),),
    )
    if not database_url.startswith("postgresql+pg8000://"):
        raise ValueError("PostgreSQL pg8000 runtime URL required")
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    private = directory / "secrets"
    private.mkdir(mode=0o700)
    _write(private / "database-url", database_url.encode(), private=True)
    _write(directory / "identity.pem", signer.private_bytes, private=True)
    data = config.model_dump(mode="json", exclude={"database_url"})
    data["database_url_file"] = "secrets/database-url"
    _write(directory / "config.json", json.dumps(data, indent=2).encode())
    _write(
        directory / "public-identity.json",
        json.dumps({"owner": owner, "url": url, "identity": entry.model_dump()}, indent=2).encode(),
    )
    return (directory / "config.json").resolve()


def _write(path: Path, content: bytes, *, private: bool = False) -> None:
    # Exclusive creation also protects against an unexpected preexisting symlink.
    with path.open("xb") as target:
        target.write(content)
        target.flush()
        os.fsync(target.fileno())
    os.chmod(path, 0o600 if private else 0o640)


def starter(directory: Path) -> dict[str, Any]:
    """Copy inert application/deployment resources from the installed wheel."""
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    resource = files("collective_intelligence_overlay") / "starter"
    names = ("application.py", "Caddyfile", "README.txt")
    for name in names:
        _write(directory / name, (resource / name).read_bytes())
    return {"directory": str(directory.resolve()), "files": list(names), "registered": False}


def rotate_key(
    config: Config, directory: Path, *, compromised: tuple[str, ...] = ()
) -> dict[str, Any]:
    """Prepare an offline operator key/config bundle; peers never update trust automatically."""
    from .operations import OwnerLock

    previous = config.identities[config.owner]
    known = {previous.keyid, *previous.historical_keys}
    if not set(compromised) <= known:
        raise ValueError("compromised key IDs must be explicitly pinned existing keys")
    signer = CryptoSigner.generate_ed25519()
    replacement = previous.model_copy(
        update={
            "keyid": signer.public_key.keyid,
            "key": signer.public_key.to_dict(),
            "historical_keys": {**previous.historical_keys, previous.keyid: previous.key},
            "compromised_keyids": tuple(
                sorted(set(previous.compromised_keyids) | set(compromised))
            ),
        }
    )
    TrustedIdentity.model_validate(replacement.model_dump())
    store = Store(config.database_url.get_secret_value(), config.owner, {})
    lock = OwnerLock(store)
    try:
        lock.acquire()
        directory.mkdir(parents=True, exist_ok=False, mode=0o700)
        _write(directory / "identity.pem", signer.private_bytes, private=True)
        _write(
            directory / "database-url",
            config.database_url.get_secret_value().encode(),
            private=True,
        )
        data = config.model_dump(mode="json", exclude={"database_url"})
        data.update(private_key="identity.pem", database_url_file="database-url")
        for field in ("artifact_directory", "application_settings", "tls_ca_certificate"):
            source = getattr(config, field)
            if source is not None:
                data[field] = str(source.resolve())
        data["identities"][config.owner] = replacement.model_dump(mode="json")
        # Refer to the existing absolute artifacts/settings/CA, never copy or clear state.
        _write(directory / "config.json", json.dumps(data, indent=2).encode(), private=True)
        public = {"owner": config.owner, "identity": replacement.model_dump(mode="json")}
        _write(directory / "public-identity.json", json.dumps(public, indent=2).encode())
        return {
            "config": str((directory / "config.json").resolve()),
            "current_keyid": replacement.keyid,
            "historical_keyids": sorted(replacement.historical_keys),
            "compromised_keyids": replacement.compromised_keyids,
            "peer_trust_updated": False,
            "required": "update peer pins and restart; compromised history grants no authority",
        }
    finally:
        lock.close()
        store.close()


def bootstrap_database(config: Config, operator_url: str, allowance: Decimal) -> dict[str, Any]:
    """Create a new dedicated DB/role; DDL credentials never enter runtime config.

    PostgreSQL CREATE DATABASE is necessarily outside a transaction. On partial
    failure, retain the created resources for explicit operator diagnosis rather
    than deleting an existing role/database or silently reusing it.
    """
    from sqlalchemy import text
    from sqlalchemy.engine import make_url

    runtime_url = make_url(config.database_url.get_secret_value())
    operator = make_url(operator_url)
    database, role, password = runtime_url.database, runtime_url.username, runtime_url.password
    if (
        runtime_url.drivername != "postgresql+pg8000"
        or operator.drivername != "postgresql+pg8000"
        or (runtime_url.host, runtime_url.port) != (operator.host, operator.port)
        or database is None
        or role is None
        or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", database)
        or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", role)
        or database in {"postgres", "template0", "template1"}
        or role == operator.username
        or password is None
        or not 16 <= len(password) <= 1024
        or not allowance.is_finite()
        or allowance < 0
    ):
        raise ValueError("dedicated restricted runtime DB/role and valid bootstrap bounds required")
    admin = Store(operator_url, config.owner, {})
    try:
        with admin.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            exists: bool = conn.execute(
                text(
                    "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=:database) "
                    "OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:role)"
                ),
                {"database": database, "role": role},
            ).scalar_one()
            if exists:
                raise FileExistsError("database or role already exists; bootstrap never overwrites")
            # Identifiers are restricted above; PostgreSQL quotes the password.
            literal: str = conn.execute(
                text("SELECT quote_literal(:password)"), {"password": password}
            ).scalar_one()
            from sqlalchemy.exc import DBAPIError

            try:
                conn.exec_driver_sql(
                    f'CREATE ROLE "{role}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE '
                    f"PASSWORD {literal}"
                )
            except DBAPIError:
                # DDL must contain a quoted password; never propagate that SQL
                # string through an exception or debug traceback.
                raise ValueError("BOOTSTRAP_ROLE_CREATE_FAILED") from None
            conn.execute(text(f'CREATE DATABASE "{database}"'))
            conn.execute(text(f'REVOKE ALL ON DATABASE "{database}" FROM PUBLIC'))
            conn.execute(text(f'GRANT CONNECT ON DATABASE "{database}" TO "{role}"'))
    finally:
        admin.close()
    ddl = Store(
        operator.set(database=database).render_as_string(hide_password=False), config.owner, {}
    )
    try:
        migrate(ddl.engine)
        with ddl.engine.begin() as conn:
            conn.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
            conn.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))
            conn.execute(
                text(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
                    f'TO "{role}"'
                )
            )
            conn.execute(text(f'REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM "{role}"'))
            conn.execute(text(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}"'))
            conn.execute(
                text(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{role}"'
                )
            )
            conn.execute(
                text(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    f'GRANT USAGE, SELECT ON SEQUENCES TO "{role}"'
                )
            )
        ddl.set_budget("work", allowance)
    finally:
        ddl.close()
    return {
        "database": database,
        "runtime_role": role,
        "migration": "head",
        "runtime_ddl": False,
        "initial_allowance": {"unit": "work", "quantity": str(allowance)},
        "external_service_readiness": "not checked by bootstrap",
    }
