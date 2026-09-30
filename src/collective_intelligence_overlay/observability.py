"""Standard rotating logs and owner-local observations over existing DB rows."""

import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from .config import Config
from .invocations import invocations
from .storage import Store, budgets, leases, records
from .synchronization import checkpoints


class OwnerLogFormatter(logging.Formatter):
    """Fixed metadata only; no exception messages, prompts, headers or request bodies."""

    def format(self, record: logging.LogRecord) -> str:
        channel = record.name.split(".")[0]
        if channel not in {
            "collective_intelligence_overlay",
            "uvicorn",
            "a2a",
            "agent_framework",
            "mcp",
            "httpx",
            "httpcore",
            "openai",
            "sqlalchemy",
        }:
            channel = "library"
        result: dict[str, Any] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": channel,
            "reason": "LIBRARY_LOG",
        }
        if record.name == "collective_intelligence_overlay.operations":
            try:
                data = json.loads(record.getMessage())
            except (ValueError, TypeError):
                data = {}
            if isinstance(data, dict):
                for name in ("owner", "reason", "state", "correlation"):
                    value = data.get(name)
                    if isinstance(value, str) and len(value) <= 160:
                        result[name] = value
                for name in (
                    "elapsed_seconds",
                    "physical_request_tasks",
                    "physical_blocking_work",
                    "handled",
                    "refused",
                    "failed",
                ):
                    value = data.get(name)
                    if isinstance(value, int | float) and 0 <= value < 10**12:
                        result[name] = value
        if record.exc_info:
            result["exception_type"] = (
                record.exc_info[0].__name__[:80] if record.exc_info[0] else "unknown"
            )
        encoded = json.dumps(result, allow_nan=False)
        if len(encoded.encode()) > 2048:
            return json.dumps({"level": record.levelname, "reason": "LOG_METADATA_OVERSIZED"})
        return encoded


def configure_logging(config: Config) -> RotatingFileHandler:
    """Explicit service CLI configuration; SDK import does not alter host logging."""
    directory = (config.log_directory or config.private_key.parent / "logs").resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    path = directory / "owner.jsonl"
    for number in range(config.log_backup_segments + 1):
        candidate = Path(str(path) + (f".{number}" if number else ""))
        if candidate.is_symlink():
            raise ValueError("unsafe operational log path")
    handler = RotatingFileHandler(
        path,
        maxBytes=config.log_segment_bytes,
        backupCount=config.log_backup_segments,
        encoding="utf-8",
    )
    os.chmod(path, 0o600)
    handler.setFormatter(OwnerLogFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "a2a", "agent_framework", "mcp"):
        logger = logging.getLogger(name)
        for previous in logger.handlers[:]:
            logger.removeHandler(previous)
        logger.propagate = True
    return handler


def database_observations(store: Store) -> dict[str, Any]:
    """Aggregate authoritative rows; this creates no event, charge or quality claim."""
    with store.engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        states: dict[str, int] = dict(
            conn.execute(
                select(invocations.c.state, func.count())
                .where(invocations.c.owner == store.owner)
                .group_by(invocations.c.state)
            ).all()
        )
        unresolved = conn.execute(
            select(func.count())
            .select_from(invocations)
            .where(
                (invocations.c.owner == store.owner)
                & invocations.c.state.in_(("unknown", "cancelled", "rejected"))
                & invocations.c.reservation_state.in_(("held", "legacy_unknown"))
            )
        ).scalar_one()
        orphan = conn.execute(
            select(func.count())
            .select_from(invocations.join(leases, invocations.c.lease_id == leases.c.task_id))
            .where(
                (invocations.c.owner == store.owner)
                & (invocations.c.state == "running")
                & (leases.c.expires_at <= func.clock_timestamp())
            )
        ).scalar_one()
        balances = {unit: str(value) for unit, value in conn.execute(select(budgets)).all()}
        prefixes = [
            dict(row)
            for row in conn.execute(
                select(
                    checkpoints.c.source,
                    checkpoints.c.filter_digest,
                    checkpoints.c.complete,
                    checkpoints.c.anchor,
                    checkpoints.c.completed_at,
                ).limit(2049)
            ).mappings()
        ]
        if len(prefixes) > 2048:
            raise ValueError("operational synchronization scope bound exceeded")
        for row in prefixes:
            for field in ("anchor", "completed_at"):
                row[field] = row[field].isoformat() if row[field] else None
        retained: dict[str, int] = dict(
            conn.execute(select(records.c.kind, func.count()).group_by(records.c.kind)).all()
        )
        return {
            "invocation_states": states,
            "unresolved_effects": int(unresolved),
            "expired_running_invocations": int(orphan),
            "allowance_remaining": balances,
            "source_prefixes": prefixes,
            "retained_record_counts": retained,
            "database_bytes": int(
                conn.execute(select(func.pg_database_size(func.current_database()))).scalar_one()
            ),
            "measured_consumption_from_allowance": False,
            "unavailable_resources": ["CPU", "model_tokens", "currency", "per_provider_latency"],
            "automatic_history_purge": False,
        }
