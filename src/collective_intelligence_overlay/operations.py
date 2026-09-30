"""Single-owner service intake, dependency readiness and physical-work tracking."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.resources import files
from typing import Any, Literal

from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

from .blocking import BlockingWork, run_blocking
from .peer import PeerService
from .security import digest
from .storage import Store

State = Literal["starting", "ready", "degraded", "draining", "stopped"]
_logger = logging.getLogger("collective_intelligence_overlay.operations")


class OwnerAlreadyRunning(ValueError):
    """Another live service owns this database/owner's process lock."""


class OwnerLock:
    """PostgreSQL session advisory lock; losing that session closes new effects."""

    def __init__(self, store: Store) -> None:
        self.store = store
        self.connection: Connection | None = None
        self.backend: int | None = None
        self._check_mutex = threading.Lock()
        self._lost = False
        self.key = int.from_bytes(
            hashlib.sha256(("cio-service-owner:" + store.owner).encode()).digest()[:8],
            "big",
            signed=True,
        )

    def acquire(self) -> None:
        if self.connection is not None:
            raise ValueError("owner process lock already acquired")
        conn = self.store.engine.connect()
        try:
            if not conn.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": self.key}
            ).scalar():
                raise OwnerAlreadyRunning("OWNER_PROCESS_ALREADY_RUNNING")
            self.backend = conn.execute(text("SELECT pg_backend_pid()")).scalar_one()
            conn.commit()
            self.connection = conn
        except BaseException:
            conn.close()
            raise

    def check(self) -> bool:
        conn = self.connection
        if self._lost or conn is None or conn.closed or conn.invalidated:
            return False
        if not self._check_mutex.acquire(timeout=5):
            return False
        try:
            # Connections are not shared concurrently across DB threads. Check the
            # actual held lock as well as the backend, without reacquiring it.
            unsigned = self.key & ((1 << 64) - 1)
            held = conn.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE pid=pg_backend_pid() "
                    "AND pid=:backend AND locktype='advisory' AND granted "
                    "AND classid::bigint=:high AND objid::bigint=:low AND objsubid=1)"
                ),
                {"backend": self.backend, "high": unsigned >> 32, "low": unsigned & 0xFFFFFFFF},
            ).scalar()
            conn.commit()
            if not held:
                self._lost = True
            return bool(held)
        except DBAPIError:
            self._lost = True
            return False
        finally:
            self._check_mutex.release()

    def close(self) -> None:
        if self.connection is not None:
            # A pooled connection must not retain a session advisory lock.
            conn, self.connection = self.connection, None
            try:
                if not conn.closed and not conn.invalidated:
                    conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": self.key})
                    conn.commit()
            finally:
                conn.close()


class Operations:
    """Operational intake only; invocation state remains in the existing store."""

    def __init__(self, service: PeerService, lock: OwnerLock | None = None) -> None:
        self.service = service
        self.lock = lock or OwnerLock(service.overlay.store)
        self.blocking = BlockingWork(8)
        self.state: State = "starting"
        self.reason = "STARTING"
        self._active: set[asyncio.Task[Any]] = set()
        self._policy_processes: set[asyncio.subprocess.Process] = set()
        self._monitor: asyncio.Task[None] | None = None
        self.handled = self.refused = self.failed = 0
        self._restored = False
        self._recovery_mutex = asyncio.Lock()

    def _database_ready(self) -> bool:
        if not self.lock.check():
            return False
        config = AlembicConfig()
        config.set_main_option(
            "script_location", str(files("collective_intelligence_overlay") / "migrations")
        )
        with self.service.overlay.store.engine.connect() as conn:
            heads = MigrationContext.configure(conn).get_current_heads()
            if set(heads) != set(ScriptDirectory.from_config(config).get_heads()):
                return False
            if not self.service.config.local_development:
                privileged: bool = conn.execute(
                    text(
                        "SELECT rolsuper OR rolcreatedb OR rolcreaterole "
                        "OR has_schema_privilege(current_user, current_schema(), 'CREATE') "
                        "OR EXISTS (SELECT 1 FROM pg_database WHERE datname=current_database() "
                        "AND datdba=(SELECT oid FROM pg_roles WHERE rolname=current_user)) "
                        "FROM pg_roles WHERE rolname=current_user"
                    )
                ).scalar_one()
                if privileged:
                    return False
            return conn.execute(text("SELECT 1")).scalar_one() == 1

    async def ready(self) -> bool:
        process = None
        try:
            with self.blocking.scope():
                if not await run_blocking(self._database_ready):
                    self.reason = "DATABASE_SCHEMA_OR_ROLE_NOT_READY"
                    return False
                if await run_blocking(self.service.overlay.store.restore_pending):
                    self.reason = "RESTORE_RECONCILIATION_REQUIRED"
                    return False
            policy = self.service.overlay.policy
            current = digest(policy.path.read_bytes() + policy.settings.model_dump_json().encode())
            if current != policy.digest:
                self.reason = "POLICY_CHANGED"
                return False
            process = await asyncio.create_subprocess_exec(
                policy.binary,
                "eval",
                "--format=json",
                "--data",
                str(policy.path),
                "true",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            self._policy_processes.add(process)
            output, _ = await asyncio.wait_for(process.communicate(), 5)
            if process.returncode != 0 or len(output) > 65536:
                self.reason = "POLICY_NOT_READY"
                return False
            value = json.loads(output)["result"][0]["expressions"][0]["value"]
            if value is not True:
                self.reason = "POLICY_NOT_READY"
                return False
            # Revalidate the actual private key/current pin without opening another DB.
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            from securesystemslib.signer import CryptoSigner  # type: ignore[attr-defined]

            key = load_pem_private_key(self.service.config.private_key.read_bytes(), password=None)
            if CryptoSigner(key).public_key != self.service.identity.signer.public_key:
                self.reason = "IDENTITY_CHANGED"
                return False
            self.reason = "DEPENDENCIES_READY"
            return True
        except Exception:
            self.reason = "DEPENDENCY_CHECK_FAILED"
            return False
        finally:
            if process is not None:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
                self._policy_processes.discard(process)

    async def start(self) -> None:
        if self.state != "starting":
            raise ValueError("service already started")
        with self.blocking.scope():
            if self.lock.connection is None:
                await run_blocking(self.lock.acquire)
        self.state = "ready" if await self.ready() else "degraded"
        self._restored = await run_blocking(self.service.overlay.store.restore_pending)
        self._monitor = asyncio.create_task(self._watch_dependencies())

    async def _watch_dependencies(self) -> None:
        while True:
            await asyncio.sleep(5)
            if self.state == "ready" and not await self.ready():
                self.state = "degraded"

    def snapshot(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "reason": self.reason,
            "physical_request_tasks": len(self._active),
            "physical_blocking_work": self.blocking.pending,
            "readiness_policy_processes": len(self._policy_processes),
            "handled": self.handled,
            "refused": self.refused,
            "failed": self.failed,
            "blocking_elapsed_seconds": self.blocking.elapsed_seconds,
            "business_unknown_is_process_failure": False,
        }

    @property
    def physical_work_remaining(self) -> bool:
        return bool(
            self._active or self.blocking.pending or self._monitor or self._policy_processes
        )

    def close(self) -> None:
        if self.physical_work_remaining:
            raise ValueError("physical work remains; drain before closing")
        self.lock.close()
        self.blocking.close()

    async def handle(self, caller: str, data: dict[str, Any]) -> dict[str, Any]:
        # During recovery, serialize state mutations and operator resume. Once
        # resumed, the existing executor/HTTP bounds retain normal concurrency.
        if self._restored:
            async with self._recovery_mutex:
                return await self._handle(caller, data)
        return await self._handle(caller, data)

    async def _handle(self, caller: str, data: dict[str, Any]) -> dict[str, Any]:
        operation = data.get("operation")
        if operation in {"status", "drain", "resume"}:
            if caller != self.service.config.owner:
                raise ValueError("operator operation is owner-only")
            if operation == "drain":
                self.state, self.reason = "draining", "OPERATOR_DRAIN"
            elif operation == "resume":
                if self.state == "stopped":
                    raise ValueError("stopped host requires restart")
                if self._restored:
                    recovery = getattr(self.service, "recovery", None)
                    if recovery is None or self._active or self.blocking.pending:
                        self.reason = "RESTORE_RECONCILIATION_REQUIRED"
                        return self.snapshot()
                    try:
                        with self.blocking.scope():
                            await run_blocking(recovery.authorize_resume, caller)
                    except (ValueError, DBAPIError):
                        self.reason = "RESTORE_RECONCILIATION_REQUIRED"
                        return self.snapshot()
                    self._restored = False
                self.state = "ready" if await self.ready() else "degraded"
            elif self.state == "ready" and not await self.ready():
                self.state = "degraded"
            return self.snapshot()
        allowed_during_drain = {
            "invocation",
            "cancel_invocation",
            "revoke",
            "metrics",
            "capability_metrics",
            "discover",
            "remote_calls",
            "reconcile",
            "sync",
            "recovery_state",
            "recovery_review",
            "operational_metrics",
        }
        if self.state != "ready" and operation not in allowed_during_drain:
            self.refused += 1
            return {"error": "SERVICE_INTAKE_CLOSED", "state": self.state, "reason": self.reason}
        task = asyncio.current_task()
        assert task is not None
        self._active.add(task)
        started = time.perf_counter()
        try:
            with self.blocking.scope():
                if not await run_blocking(self.lock.check):
                    self.state, self.reason = "degraded", "OWNER_SESSION_LOST"
                    self.refused += 1
                    return {"error": "SERVICE_INTAKE_CLOSED", "reason": self.reason}
                if operation == "operational_metrics":
                    if caller != self.service.config.owner:
                        raise ValueError("operational metrics are owner-only")
                    from .observability import database_observations

                    result: dict[str, Any] = {
                        "operations": self.snapshot(),
                        "database": await run_blocking(
                            database_observations, self.service.overlay.store
                        ),
                        "artifacts": await run_blocking(self.service.config.artifacts().usage),
                        "last_allocation": None,
                    }
                    steps = getattr(self.service, "steps", None)
                    if steps is not None:
                        allocation = await run_blocking(steps.last_allocation)
                        result["last_allocation"] = (
                            allocation.model_dump(mode="json") if allocation else None
                        )
                else:
                    result = await self.service.handle(caller, data)
            self.handled += 1
            return result
        except BaseException:
            self.failed += 1
            raise
        finally:
            self._active.discard(task)
            _logger.info(
                json.dumps(
                    {
                        "owner": self.service.config.owner,
                        "reason": "REQUEST_FINISHED",
                        "elapsed_seconds": round(time.perf_counter() - started, 6),
                        "correlation": hashlib.sha256(
                            str(data.get("invocation_id", "")).encode()
                        ).hexdigest()[:16],
                    }
                )
            )

    async def stop(self, seconds: float = 30) -> dict[str, Any]:
        if not 0 <= seconds <= 30:
            raise ValueError("invalid shutdown wait")
        self.state, self.reason = "draining", "SHUTDOWN_DRAIN"
        deadline = time.monotonic() + seconds
        if self._monitor is not None:
            self._monitor.cancel()
            try:
                await self._monitor
            except asyncio.CancelledError:
                pass
            self._monitor = None
        if self._active:
            await asyncio.wait(tuple(self._active), timeout=seconds)
        await self.blocking.wait(max(0, deadline - time.monotonic()))
        if self._active or self.blocking.pending or self._policy_processes:
            self.reason = "SHUTDOWN_PHYSICAL_WORK_UNKNOWN"
            return self.snapshot()
        self.close()
        self.state, self.reason = "stopped", "PHYSICAL_WORK_FINISHED"
        return self.snapshot()

    @asynccontextmanager
    async def lifespan(self, _: Any) -> AsyncIterator[None]:
        try:
            await self.start()
            yield
        finally:
            report = await self.stop()
            _logger.info(json.dumps(report))
