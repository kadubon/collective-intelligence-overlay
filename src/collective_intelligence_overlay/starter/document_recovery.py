"""Conservative document recovery against an operator-preserved, unrewound database.

This optional reference is useful for rollback recovery while the original database
still exists. It cannot confirm recovery after loss of that original or account for
external effects/inference outside this read-only document application's contracts.
"""

from __future__ import annotations

import base64
import json
import time
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from collective_intelligence_overlay.application import ApplicationHost
from collective_intelligence_overlay.artifacts import Artifacts
from collective_intelligence_overlay.bindings import Binding, Target, callable_digest, fingerprint
from collective_intelligence_overlay.blocking import run_blocking
from collective_intelligence_overlay.calls import remote_calls
from collective_intelligence_overlay.config import Config, load_config
from collective_intelligence_overlay.invocations import invocations
from collective_intelligence_overlay.models import Capability, Event, Scope, Subject, now
from collective_intelligence_overlay.operations import OwnerAlreadyRunning, OwnerLock
from collective_intelligence_overlay.recovery import RecoveryObservation
from collective_intelligence_overlay.security import verify
from collective_intelligence_overlay.storage import Store, budgets, feed_state, leases, records


def snapshot(store: Store, reviewed_generation: str, artifacts: Artifacts) -> dict[str, Any]:
    """Read exact business originals; new recovery observations are separate overhead."""
    started = time.monotonic()
    with store.engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        result: dict[str, Any] = {}
        for name, table, order in (
            ("invocations", invocations, (invocations.c.caller, invocations.c.id)),
            ("leases", leases, (leases.c.task_id,)),
            ("remote_calls", remote_calls, (remote_calls.c.caller, remote_calls.c.call_key)),
        ):
            rows = [
                dict(row)
                for row in conn.execute(select(table).order_by(*order).limit(65537)).mappings()
            ]
            if len(rows) > 65536 or any(
                row.get("owner", store.owner) != store.owner for row in rows
            ):
                raise ValueError("reference business row bound or owner mismatch")
            if name == "invocations":
                if any(row["state"] == "running" for row in rows):
                    raise ValueError("reference original work is unfinished")
                result["uncertain_original_calls"] = [
                    [row["caller"], row["id"]] for row in rows if row["state"] == "unknown"
                ]
            result[name] = fingerprint(json.loads(json.dumps(rows, default=str)))
        allowance: dict[str, Decimal] = dict(
            conn.execute(select(budgets).order_by(budgets.c.unit)).all()
        )
        if len(allowance) > 32 or any(amount < 0 for amount in allowance.values()):
            raise ValueError("reference allowance bound or balance invalid")
        result["allowance_remaining"] = {unit: str(amount) for unit, amount in allowance.items()}
        originals = []
        review_artifacts = set()
        for index, row in enumerate(
            conn.execute(
                select(records)
                .where(records.c.issuer == store.owner)
                .order_by(records.c.kind, records.c.record_id)
                .limit(65537)
            ).mappings()
        ):
            if index >= 65536 or time.monotonic() - started > 10:
                raise ValueError("reference signed history exceeds bound")
            record = verify(row["envelope"], store.principals, require_authority=False)
            original = json.loads(base64.b64decode(row["envelope"]["payload"], validate=True))
            key = record.subject.key if isinstance(record, Capability) else record.id
            if (
                row["body"] != original
                or row["kind"] != record.kind
                or row["issuer"] != record.issuer
                or row["record_id"] != key
            ):
                raise ValueError("reference signed original/projection mismatch")
            if (
                isinstance(record, Event)
                and record.subject.id == "recovery-review"
                and record.subject.version == reviewed_generation
                and record.task_id == reviewed_generation
            ):
                proof = json.loads(artifacts.get(record.subject.digest))
                if (
                    proof["state"]["owner"] != store.owner
                    or proof["state"]["generation"] != reviewed_generation
                ):
                    raise ValueError("reference recovery observation generation mismatch")
                review_artifacts.add(record.subject.digest)
                continue
            originals.append([row["kind"], row["record_id"], row["envelope"]])
        if not originals or len(originals) > 65536:
            raise ValueError("reference signed history unavailable or exceeds bound")
        result["signed_originals"] = fingerprint(originals)
        inventory: list[str] = []
        total = 0
        for path in sorted(artifacts.directory.iterdir()):
            if path.name in review_artifacts:
                continue
            total += path.stat().st_size
            if len(inventory) >= 65536 or total > 256 * 1048576 or time.monotonic() - started > 10:
                raise ValueError("reference artifact/time bound exceeded")
            artifacts.get(path.name)
            inventory.append(path.name)
        result["artifacts"] = fingerprint(inventory)
        return result


def register(host: ApplicationHost, reference_path: Path) -> Binding:
    """Pin an operator config, never accept a reference URL from a recovery request."""
    reference: Config = load_config(reference_path)
    if reference.owner != host.config.owner:
        raise ValueError("document recovery reference must preserve the same owner")
    reference_url = reference.database_url.get_secret_value()

    async def query(arguments: dict[str, Any]) -> dict[str, Any]:
        state = arguments["state"]
        if (await run_blocking(host.recovery.inspect))["state_digest"] != state["state_digest"]:
            raise ValueError("document recovery request no longer identifies restored state")

        def observe() -> tuple[dict[str, Any], str, bool]:
            external = Store(reference_url, host.config.owner, host.overlay.store.principals)
            lock = OwnerLock(external)
            try:
                lock.acquire()
                with external.engine.connect() as conn:
                    pending: bool = conn.execute(
                        select(feed_state.c.restore_pending).where(feed_state.c.id == 1)
                    ).scalar_one()
                if pending:
                    return {}, "REFERENCE_NOT_UNRESTORED", False
                actual = snapshot(external, state["generation"], reference.artifacts())
                restored = snapshot(
                    host.overlay.store, state["generation"], host.config.artifacts()
                )
                matched = actual == restored
                return (
                    actual,
                    (
                        "PRESERVED_REFERENCE_STATE_MATCHED"
                        if matched
                        else "REFERENCE_POST_BACKUP_MISMATCH"
                    ),
                    matched,
                )
            except OwnerAlreadyRunning:
                return {}, "REFERENCE_OWNER_ACTIVE", False
            except (DBAPIError, OSError, ValueError):
                return {}, "REFERENCE_STATE_UNAVAILABLE", False
            finally:
                lock.close()
                external.close()

        actual, reason, matched = await run_blocking(observe)
        return RecoveryObservation(
            owner=host.config.owner,
            generation=state["generation"],
            state_digest=state["state_digest"],
            post_backup_state="matched" if matched else "unknown",
            observation_digest=fingerprint({"reference": actual, "reason": reason}),
            allowance_remaining=actual.get("allowance_remaining", {}),
            uncertain_original_calls=tuple(
                tuple(pair) for pair in actual.get("uncertain_original_calls", [])
            ),
            reason=reason,
        ).model_dump(mode="json")

    source = callable_digest(query)
    subject = Subject(
        id="document-recovery-state",
        version="1",
        digest=fingerprint(
            {
                "source": source,
                "snapshot": callable_digest(snapshot),
                "reference": reference_url,
            }
        ),
    )
    binding = Binding(
        id=subject.id,
        revision="1",
        issuer=host.config.owner,
        registrar=host.config.owner,
        subject=subject,
        scope=Scope(
            task=subject.id,
            input_contract="document-recovery.in.v1",
            output_contract="document-recovery.out.v1",
            environment=host.config.execution_environment,
        ),
        target=Target(
            kind="local",
            name=subject.id,
            interface_digest=source,
            implementation_identity="installed",
        ),
        input_schema={
            "type": "object",
            "required": ["state", "arguments"],
            "properties": {"state": {"type": "object"}, "arguments": {"type": "object"}},
            "additionalProperties": False,
        },
        output_schema=RecoveryObservation.model_json_schema(),
        callers=(host.config.owner,),
        verification_callers=(host.config.owner,),
        effects="read-only",
    )
    host.registry.register_local(binding, query, lambda _: True)
    host.publish_candidate(
        binding,
        Capability(
            schema_version="2",
            issuer=host.config.owner,
            subject=subject,
            scope=binding.scope,
            binding_digest=binding.digest,
            entrypoint=binding.id,
            claim="preserved-document-business-state",
            license="Apache-2.0",
            provenance="operator-pinned preserved original database; independently unchecked",
            classification="imported",
            expires_at=now() + timedelta(days=1),
        ),
    )
    host.recovery.register(binding.id)
    return binding
