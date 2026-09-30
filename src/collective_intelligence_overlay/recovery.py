"""Offline coherent backup using PostgreSQL tools and existing owner process lock."""

from __future__ import annotations

import base64
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy import select, update
from sqlalchemy.engine import make_url

from .bindings import ExecutionContext, Registry, fingerprint
from .blocking import run_blocking
from .calls import RemoteCall, remote_calls
from .config import Config
from .invocations import invocations
from .models import Capability, Cost, Digest, Event, Identifier, Subject
from .operations import OwnerLock
from .queries import RecordQuery
from .security import Identity, digest, verify
from .setup import _write
from .storage import Conflict, budgets, feed_state, leases, records
from .synchronization import FeedFilter, checkpoints


def _copy(source: Path, target: Path, maximum: int) -> str:
    if source.is_symlink() or not source.is_file() or source.stat().st_size > maximum:
        raise ValueError("unsafe or oversized backup source")
    _write(target, source.read_bytes(), private=True)
    return digest(target.read_bytes())


def backup(
    config: Config,
    directory: Path,
    *,
    operator_url: str,
    pg_prefix: tuple[str, ...] = (),
    tls_private_key: Path | None = None,
) -> dict[str, Any]:
    """Back up a stopped owner; retain incomplete destinations without a manifest.

    Protect this directory and encrypt it with the operator's existing backup tool.
    No archive upload, encryption implementation or destructive restore is implicit.
    """
    started = time.monotonic()
    runtime_url, operator = make_url(config.database_url.get_secret_value()), make_url(operator_url)
    if operator.drivername != runtime_url.drivername or (operator.host, operator.port) != (
        runtime_url.host,
        runtime_url.port,
    ):
        raise ValueError("backup operator must address the runtime PostgreSQL server")
    destination = directory.resolve()
    artifacts = config.artifact_directory.resolve()
    if destination == artifacts or artifacts in destination.parents:
        raise ValueError("backup destination must be outside active artifacts")
    identity, overlay = config.runtime()
    lock = OwnerLock(overlay.store)
    manifest: dict[str, Any] = {}
    try:
        lock.acquire()  # Reject a live peer before creating or copying anything.
        if not pg_prefix and not shutil.which("pg_dump"):
            raise ValueError("explicit PostgreSQL pg_dump client required")
        destination.mkdir(parents=True, exist_ok=False, mode=0o700)
        os.chmod(destination, 0o700)
        copied: dict[str, str] = {}
        data = config.model_dump(mode="json", exclude={"database_url"})
        data.update(
            private_key="identity.pem",
            artifact_directory="artifacts",
            database_url_file="database-url",
            log_directory="logs" if config.log_directory is not None else None,
        )
        copied["identity.pem"] = _copy(config.private_key, destination / "identity.pem", 8192)
        _write(
            destination / "database-url",
            config.database_url.get_secret_value().encode(),
            private=True,
        )
        copied["database-url"] = digest((destination / "database-url").read_bytes())
        for field in ("application_settings", "tls_ca_certificate"):
            source = getattr(config, field)
            if source is not None:
                name = field + ".data"
                copied[name] = _copy(source, destination / name, 262144)
                data[field] = name
        if tls_private_key is not None:
            copied["tls-private.pem"] = _copy(
                tls_private_key, destination / "tls-private.pem", 16384
            )
        _write(destination / "config.json", json.dumps(data, indent=2).encode(), private=True)
        copied["config.json"] = digest((destination / "config.json").read_bytes())
        output_artifacts = destination / "artifacts"
        output_artifacts.mkdir(mode=0o700)
        total = 0
        if artifacts.exists():
            for source in artifacts.iterdir():
                if time.monotonic() - started >= 60 or len(copied) >= 65536:
                    raise ValueError("backup file/time bound exceeded")
                if len(source.name) != 64 or any(c not in "0123456789abcdef" for c in source.name):
                    raise ValueError("backup artifact is not a content-addressed file")
                total += source.stat().st_size
                if total > 256 * 1024 * 1024:
                    raise ValueError("backup artifact capacity exceeded")
                value = _copy(source, output_artifacts / source.name, 1048576)
                if value != source.name:
                    raise ValueError("backup artifact content digest mismatch")
                copied["artifacts/" + source.name] = value
        # Credentials stay in the child environment, never argv, output or manifest.
        environment = os.environ.copy()
        if operator.password is not None:
            environment["PGPASSWORD"] = operator.password
        environment["PGCONNECT_TIMEOUT"] = "5"
        command = [
            *pg_prefix,
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-acl",
            "-h",
            operator.host or "127.0.0.1",
            "-p",
            str(operator.port or 5432),
            "-U",
            operator.username or "",
            "--dbname",
            runtime_url.database or "",
        ]
        dump_path = destination / "database.dump"
        with dump_path.open("xb") as output, tempfile.TemporaryFile() as errors:
            os.chmod(dump_path, 0o600)
            completed = subprocess.run(
                command,
                env=environment,
                stdout=output,
                stderr=errors,
                timeout=max(1, 60 - (time.monotonic() - started)),
            )
            output.flush()
            os.fsync(output.fileno())
        if completed.returncode:
            raise ValueError("PG_BACKUP_FAILED")
        if dump_path.stat().st_size > 512 * 1024 * 1024:
            raise ValueError("backup database size bound exceeded")
        with dump_path.open("rb") as source:
            if source.read(5) != b"PGDMP":
                raise ValueError("invalid PostgreSQL custom backup")
        with dump_path.open("rb") as source:
            copied["database.dump"] = hashlib.file_digest(source, "sha256").hexdigest()
        if not lock.check():
            raise ValueError("owner lock lost during backup")
        with overlay.store.engine.connect() as conn:
            generation: str = conn.execute(
                select(feed_state.c.generation).where(feed_state.c.id == 1)
            ).scalar_one()
        manifest = {
            "backup_schema": "1",
            "owner": identity.name,
            "complete": True,
            "files": copied,
            "artifact_bytes": total,
            "feed_generation": generation,
            "application": config.application,
            "runtime": {
                "python": platform.python_version(),
                "os": platform.system(),
                "machine": platform.machine(),
                "distribution": importlib.metadata.version("collective-intelligence-overlay"),
            },
            "post_backup_effects_reconciled": False,
            "tls_private_key_included": tls_private_key is not None,
        }
        encoded = json.dumps(manifest, indent=2).encode()
        if len(encoded) > 16 * 1024 * 1024:
            raise ValueError("backup manifest size bound exceeded")
        _write(destination / "manifest.json", encoded, private=True)
        return {
            "complete": True,
            "owner": identity.name,
            "files": len(copied),
            "manifest_sha256": digest(encoded),
            "business_restore_verified": False,
        }
    finally:
        lock.close()
        overlay.store.close()


def verify_backup(directory: Path) -> dict[str, Any]:
    """Validate bytes only; this does not restore a DB or confirm external effects."""
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink() or manifest_path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("invalid backup manifest")
    manifest = json.loads(manifest_path.read_bytes())
    if manifest.get("backup_schema") != "1" or manifest.get("complete") is not True:
        raise ValueError("incomplete backup")
    entries = manifest["files"]
    if not isinstance(entries, dict) or not 1 <= len(entries) <= 65536:
        raise ValueError("invalid backup entries")
    root = directory.resolve()
    started = time.monotonic()
    total = 0
    for name, expected in entries.items():
        relative = Path(name)
        target = root / relative
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or target.is_symlink()
            or any(
                parent.is_symlink()
                for parent in target.parents
                if parent != root and root in parent.parents
            )
        ):
            raise ValueError("unsafe backup entry")
        if not target.is_file() or target.stat().st_size > 512 * 1024 * 1024:
            raise ValueError("backup digest mismatch")
        total += target.stat().st_size
        if total > 768 * 1024 * 1024 or time.monotonic() - started > 60:
            raise ValueError("backup verification capacity/time exceeded")
        with target.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != expected:
                raise ValueError("backup digest mismatch")
    return {
        "complete": True,
        "files": len(entries),
        "manifest_sha256": digest(manifest_path.read_bytes()),
        "business_restore_verified": False,
    }


class RecoveryObservation(BaseModel):
    """An installed business query's finding; never an independent quality PASS.

    The trusted query must check external work/consumption absent from the backup.
    Merely copying the structural input is not a valid application implementation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    owner: Identifier
    generation: Identifier
    state_digest: Digest
    post_backup_state: Literal["matched", "unknown"]
    observation_digest: Digest
    allowance_remaining: dict[Identifier, Decimal] = Field(max_length=32)
    uncertain_original_calls: tuple[tuple[Identifier, Identifier], ...] = Field(max_length=1024)
    reason: Identifier
    independent_verification: Literal["UNKNOWN"] = "UNKNOWN"


class Recovery:
    """Check restored state and record an operator query; only explicit resume opens it."""

    def __init__(self, registry: Registry, config: Config, identity: Identity) -> None:
        self.registry, self.config, self.identity = registry, config, identity
        self.store = registry.overlay.store
        self.artifacts = config.artifacts()
        self._queries: dict[str, str] = {}

    def register(self, binding_id: str) -> None:
        binding = self.registry.inspect(binding_id)
        if (
            binding.issuer != self.store.owner
            or binding.effects != "read-only"
            or self.store.owner not in binding.verification_callers
            or binding_id in self._queries
        ):
            raise ValueError("recovery requires an explicit owner-approved read-only binding")
        self._queries[binding_id] = binding.digest

    def inspect(self, *, exclude_event: str | None = None) -> dict[str, Any]:
        """Bounded repeatable-read inspection, with original signatures and IDs retained."""
        started = time.monotonic()
        excluded_artifact = None
        with self.store.engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as conn:
            gate = dict(
                conn.execute(select(feed_state).where(feed_state.c.id == 1)).mappings().one()
            )
            if not gate["restore_pending"] or gate["restored_at"] is None:
                raise ValueError("no closed restored generation to review")
            signed = hashlib.sha256()
            count = 0
            query = select(records).order_by(records.c.sequence).limit(65537)
            for row in conn.execute(query).mappings():
                if (
                    row["kind"] == "event"
                    and row["issuer"] == self.store.owner
                    and row["record_id"] == exclude_event
                ):
                    excluded_artifact = verify(
                        row["envelope"], self.store.principals
                    ).subject.digest
                    continue
                count += 1
                if count > 65536 or time.monotonic() - started > 30:
                    raise ValueError("recovery record/time bound exceeded; intake stays closed")
                record = verify(row["envelope"], self.store.principals, require_authority=False)
                original = json.loads(base64.b64decode(row["envelope"]["payload"], validate=True))
                key = record.subject.key if isinstance(record, Capability) else record.id
                if (
                    row["body"] != original
                    or row["kind"] != record.kind
                    or row["issuer"] != record.issuer
                    or row["record_id"] != key
                ):
                    raise ValueError("restored signed bytes/projection mismatch")
                signed.update(
                    fingerprint([row["kind"], row["issuer"], key, row["envelope"]]).encode()
                )
            balances: dict[str, Decimal] = dict(
                conn.execute(select(budgets).order_by(budgets.c.unit)).all()
            )
            if len(balances) > 32 or any(value < 0 for value in balances.values()):
                raise ValueError("invalid restored allowance")
            calls = list(
                conn.execute(
                    select(invocations)
                    .order_by(invocations.c.caller, invocations.c.id)
                    .limit(65537)
                ).mappings()
            )
            held = list(
                conn.execute(select(leases).order_by(leases.c.task_id).limit(65537)).mappings()
            )
            maps = list(
                conn.execute(
                    select(remote_calls).order_by(remote_calls.c.call_key).limit(65537)
                ).mappings()
            )
            if max(len(calls), len(held), len(maps)) > 65536:
                raise ValueError("recovery invocation/map bound exceeded")
            for row in calls:
                TypeAdapter(Identifier).validate_python(row["id"])
                if row["owner"] != self.store.owner:
                    raise ValueError("restored invocation owner mismatch")
                if row["state"] == "running":
                    raise ValueError("fence unfinished original invocations before recovery review")
                if row["result_digest"] and fingerprint(row["result"]) != row["result_digest"]:
                    raise ValueError("restored result digest mismatch")
            for row in maps:
                RemoteCall.model_validate({k: row[k] for k in RemoteCall.model_fields})
                if row["owner"] != self.store.owner:
                    raise ValueError("restored remote call owner mismatch")
            synced = list(
                conn.execute(
                    select(checkpoints)
                    .order_by(checkpoints.c.source, checkpoints.c.filter_digest)
                    .limit(2049)
                ).mappings()
            )
            if len(synced) > 2048:
                raise ValueError("recovery synchronization bound exceeded")
            for peer in self.config.peers:
                if peer.identity == self.store.owner:
                    continue
                full = [
                    r
                    for r in synced
                    if r["source"] == peer.identity and r["filter_digest"] == FeedFilter().digest
                ]
                if not full or not all(
                    r["complete"]
                    and r["anchor"]
                    and r["completed_at"]
                    and r["completed_at"] >= gate["restored_at"]
                    for r in full
                ):
                    raise ValueError("complete post-restore peer synchronization required")
            state = {
                "owner": self.store.owner,
                "generation": gate["generation"],
                "restored_at": gate["restored_at"].isoformat(),
                "signed_records_digest": signed.hexdigest(),
                "signed_records": count,
                "allowance_remaining": {k: str(v) for k, v in balances.items()},
                "invocations_digest": fingerprint(
                    json.loads(json.dumps([dict(r) for r in calls], default=str))
                ),
                "leases_digest": fingerprint(
                    json.loads(json.dumps([dict(r) for r in held], default=str))
                ),
                "remote_calls_digest": fingerprint(
                    json.loads(json.dumps([dict(r) for r in maps], default=str))
                ),
                "sync_digest": fingerprint(
                    json.loads(json.dumps([dict(r) for r in synced], default=str))
                ),
                "uncertain_original_calls": [
                    [r["caller"], r["id"]] for r in calls if r["state"] == "unknown"
                ],
                "policy_digest": self.registry.overlay.policy.digest,
                "application": self.config.application,
                "configuration_digest": fingerprint(
                    self.config.model_dump(
                        mode="json", exclude={"database_url", "private_key", "artifact_directory"}
                    )
                ),
                "settings_digest": digest(self.config.application_settings.read_bytes())
                if self.config.application_settings
                else None,
            }
            inventory: list[str] = []
            total = 0
            for source in sorted(self.artifacts.directory.iterdir()):
                if source.name == excluded_artifact:
                    continue
                total += source.stat().st_size
                if (
                    len(inventory) >= 65536
                    or total > 256 * 1048576
                    or time.monotonic() - started > 30
                ):
                    raise ValueError("recovery artifact/time capacity exceeded")
                self.artifacts.get(source.name)  # Verify actual content, not just a filename.
                inventory.append(source.name)
            state["artifact_inventory_digest"] = fingerprint(inventory)
            state["artifact_bytes"] = total
            encoded = json.dumps(state, sort_keys=True).encode()
            if len(encoded) > 262144 or time.monotonic() - started > 30:
                raise ValueError("recovery structural inspection bound exceeded")
            state["state_digest"] = fingerprint(state)
            return state

    async def review(
        self, caller: str, command_id: str, checker: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        started = time.perf_counter()
        if caller != self.store.owner:
            raise ValueError("recovery review is owner-only")
        TypeAdapter(Identifier).validate_python(command_id)
        if len(json.dumps(arguments).encode()) > 8192:
            raise ValueError("business recovery arguments exceed bound")
        pinned = self._queries[checker]
        with self.store.engine.connect() as conn:
            generation: str = conn.execute(
                select(feed_state.c.generation).where(feed_state.c.id == 1)
            ).scalar_one()
        event_id = "recovery-" + fingerprint([caller, generation, command_id])
        page = await run_blocking(
            self.store.record_page,
            RecordQuery(kinds=("event",), issuer=caller, record_id=event_id),
            limit=1,
        )
        if page.items:
            previous = page.items[0]
            if not isinstance(previous, Event):
                raise Conflict("recovery command used by another record")
            proof = json.loads(await run_blocking(self.artifacts.get, previous.subject.digest))
            if (
                proof["checker_digest"] != pinned
                or proof["checker"] != checker
                or proof["arguments_digest"] != fingerprint(arguments)
            ):
                raise Conflict("recovery command changed its query")
            return self._report(previous, proof)
        binding = self.registry.inspect(checker)
        if binding.digest != pinned or binding.effects != "read-only":
            raise ValueError("recovery query contract changed")
        state = await run_blocking(self.inspect)
        observed = RecoveryObservation.model_validate(
            await self.registry.execute(
                checker,
                pinned,
                {"state": state, "arguments": arguments},
                ExecutionContext(
                    caller=caller,
                    purpose="verification",
                    environment=self.config.execution_environment,
                    permissions=frozenset(self.config.policy.permissions),
                ),
                call_id=command_id,
                call_scope="recovery/" + state["generation"],
            )
        )
        matched = not (
            observed.owner != caller
            or observed.generation != state["generation"]
            or observed.state_digest != state["state_digest"]
            or observed.post_backup_state != "matched"
            or observed.allowance_remaining
            != {k: Decimal(v) for k, v in state["allowance_remaining"].items()}
            or set(observed.uncertain_original_calls)
            != {tuple(v) for v in state["uncertain_original_calls"]}
        )
        if (await run_blocking(self.inspect))["state_digest"] != state["state_digest"]:
            raise Conflict("restored state changed during review")
        proof = {
            "state": state,
            "observation": observed.model_dump(mode="json"),
            "checker": checker,
            "checker_digest": pinned,
            "arguments_digest": fingerprint(arguments),
            "matched": matched,
        }
        artifact = await run_blocking(
            self.artifacts.put, json.dumps(proof, sort_keys=True).encode()
        )
        event = Event(
            id=event_id,
            issuer=caller,
            subject=Subject(id="recovery-review", version=state["generation"], digest=artifact),
            action="recommendation",
            task_id=state["generation"],
            attempt_id=command_id,
            correlation_id=state["generation"],
            costs=(
                Cost(
                    category="observation",
                    status="measured",
                    quantity=Decimal(str(round(time.perf_counter() - started, 9))),
                    unit="wall_seconds",
                ),
            ),
        )
        await run_blocking(self.store.put, self.identity.sign(event))
        await run_blocking(self._save_review, state, event.id, artifact)
        return self._report(event, proof)

    @staticmethod
    def _report(event: Event, proof: dict[str, Any]) -> dict[str, Any]:
        return {
            "receipt": event.id,
            "observation_digest": event.subject.digest,
            "business_state": "matched" if proof["matched"] else "unknown",
            "intake": "closed; explicit resume required",
            "independent_verification": "UNKNOWN",
            "allowance_unchanged": True,
        }

    def _save_review(self, state: dict[str, Any], receipt: str, artifact: str) -> None:
        with self.store.engine.begin() as conn:
            gate = (
                conn.execute(select(feed_state).where(feed_state.c.id == 1).with_for_update())
                .mappings()
                .one()
            )
            if not gate["restore_pending"] or gate["generation"] != state["generation"]:
                raise Conflict("restored generation changed during review")
            conn.execute(
                update(feed_state)
                .where(feed_state.c.id == 1)
                .values(recovery_receipt=receipt, recovery_digest=artifact)
            )

    def authorize_resume(self, caller: str) -> None:
        if caller != self.store.owner:
            raise ValueError("recovery resume is owner-only")
        with self.store.engine.connect() as conn:
            gate = conn.execute(select(feed_state).where(feed_state.c.id == 1)).mappings().one()
        if not gate["recovery_receipt"] or not gate["recovery_digest"]:
            raise ValueError("review post-backup business state before resume")
        proof = json.loads(self.artifacts.get(gate["recovery_digest"]))
        if proof.get("matched") is not True:
            raise ValueError("business recovery remains UNKNOWN")
        reference = self.store.reference("event", caller, gate["recovery_receipt"])
        record = verify(self.store.signed_record(reference), self.store.principals)
        if (
            not isinstance(record, Event)
            or record.subject.digest != gate["recovery_digest"]
            or proof["checker_digest"] != self._queries.get(proof["checker"])
        ):
            raise ValueError("recovery review/query authority changed")
        state = self.inspect(exclude_event=record.id)
        if state["state_digest"] != proof["state"]["state_digest"]:
            raise Conflict("restored state changed; review again before resume")
        with self.store.engine.begin() as conn:
            current = (
                conn.execute(select(feed_state).where(feed_state.c.id == 1).with_for_update())
                .mappings()
                .one()
            )
            if (
                current["generation"] != state["generation"]
                or current["recovery_digest"] != gate["recovery_digest"]
            ):
                raise Conflict("recovery generation/review changed")
            conn.execute(
                update(feed_state).where(feed_state.c.id == 1).values(restore_pending=False)
            )
