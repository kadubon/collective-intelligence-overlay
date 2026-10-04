"""Small JSON CLI over the same SDK operations."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import __version__
from .accounting import capability_metrics, metrics_page, work_metrics_page
from .config import load_config
from .models import UseRequest
from .queries import RecordCursor, RecordQuery
from .storage import migrate


def main() -> int:
    parser = argparse.ArgumentParser(prog="collective-intelligence-overlay")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="run the API-key-free three-peer demonstration")
    demo.add_argument("--directory", type=Path, required=True)
    demo.add_argument("--database-url", default=os.environ.get("CIO_TEST_DATABASE_URL"))
    demo.add_argument("--opa", default=os.environ.get("CIO_OPA", "opa"))
    binding_check = commands.add_parser(
        "binding-check", help="validate a manifest; does not register it"
    )
    binding_check.add_argument("--manifest", type=Path, required=True)
    opa_install = commands.add_parser("opa-install", help="explicitly install reviewed native OPA")
    opa_install.add_argument("--target", type=Path, required=True)
    setup = commands.add_parser("setup", help="create a production owner home; no DB or download")
    setup.add_argument("--directory", type=Path, required=True)
    setup.add_argument("--owner", required=True)
    setup.add_argument("--url", required=True)
    setup.add_argument("--database-url-env", default="CIO_RUNTIME_DATABASE_URL")
    setup.add_argument("--opa", required=True)
    setup.add_argument("--application")
    setup.add_argument("--listen-port", type=int, default=8000)
    starter_cmd = commands.add_parser(
        "starter", help="generate installed application and TLS assets"
    )
    starter_cmd.add_argument("--directory", type=Path, required=True)
    backup_check = commands.add_parser(
        "verify-backup", help="verify backup structure, digests and archive format; no restore"
    )
    backup_check.add_argument("--directory", type=Path, required=True)
    lifecycle_cmd = commands.add_parser(
        "lifecycle", help="read-only lifecycle views; current assessment is explicit"
    )
    from .lifecycle_cli import configure as configure_lifecycle

    configure_lifecycle(lifecycle_cmd)
    for name in (
        "check-config",
        "migrate",
        "peer",
        "inspect",
        "metrics",
        "doctor",
        "sync",
        "restore-state",
        "invoke",
        "invocation",
        "cancel-invocation",
        "invocation-cleanup",
        "reobserve",
        "status",
        "drain",
        "resume",
        "goals",
        "opportunities",
        "step",
        "run",
        "database-bootstrap",
        "remote-calls",
        "reconcile",
        "backup",
        "key-rotate",
        "recovery-state",
        "recovery-review",
        "resolve-invocation",
    ):
        cmd = commands.add_parser(name)
        cmd.add_argument("--config", type=Path, required=True)
        if name in {"status", "drain", "resume"}:
            cmd.add_argument("--identity-name", help="explicit current pinned control caller")
            cmd.add_argument("--identity-private-key", type=Path, help="separate caller PEM key")
        if name == "key-rotate":
            cmd.add_argument("--directory", type=Path, required=True)
            cmd.add_argument("--compromised-key-id", action="append", default=[])
        if name == "backup":
            cmd.add_argument("--directory", type=Path, required=True)
            cmd.add_argument("--database-url-env", default="CIO_BACKUP_DATABASE_URL")
            cmd.add_argument(
                "--pg-prefix-file",
                type=Path,
                help="explicit JSON argv prefix for native client wrapper",
            )
            cmd.add_argument("--tls-private-key", type=Path)
        if name == "database-bootstrap":
            cmd.add_argument("--database-url-env", default="CIO_BOOTSTRAP_DATABASE_URL")
            cmd.add_argument("--allowance-work", required=True)
        if name in {
            "status",
            "drain",
            "resume",
            "goals",
            "opportunities",
            "step",
            "run",
            "remote-calls",
            "reconcile",
            "recovery-state",
            "recovery-review",
            "resolve-invocation",
        }:
            cmd.add_argument("--peer", help="configured destination; defaults to the owner")
        if name == "remote-calls":
            scope = cmd.add_mutually_exclusive_group(required=True)
            scope.add_argument("--invocation-id")
            scope.add_argument("--call-scope")
            cmd.add_argument("--limit", type=int, default=32)
            cmd.add_argument("--after")
        if name in {"remote-calls", "reconcile", "resolve-invocation"}:
            cmd.add_argument("--original-caller", help="owner-selected original delegated caller")
        if name == "reconcile":
            cmd.add_argument("--call-key", required=True)
            cmd.add_argument("--command-id", required=True)
            cmd.add_argument("--invocation-id")
            cmd.add_argument(
                "--reconciler", help="operator-installed read-only effect query binding"
            )
        if name in {"recovery-review", "resolve-invocation"}:
            cmd.add_argument("--command-id", required=True)
            cmd.add_argument("--checker", required=True)
            cmd.add_argument("--arguments-file", type=Path, required=True)
        if name == "resolve-invocation":
            cmd.add_argument("--invocation-id", required=True)
            cmd.add_argument("--observations-file", type=Path, required=True)
        if name in {"opportunities", "run"}:
            cmd.add_argument("--max-candidates", type=int, default=8)
        if name == "opportunities":
            cmd.add_argument("--start", type=int, default=0)
        if name == "step":
            cmd.add_argument("--opportunity-id", required=True)
        if name == "run":
            cmd.add_argument("--max-steps", type=int, default=20)
            cmd.add_argument("--seconds", type=int, default=120)
        if name == "invocation-cleanup":
            cmd.add_argument("--limit", type=int, default=32)
            cmd.add_argument("--seconds", type=int, default=5)
            cmd.add_argument("--dry-run", action="store_true")
        if name == "reobserve":
            cmd.add_argument("--goal-file", type=Path, required=True)
            cmd.add_argument("--opportunity-id", required=True)
            cmd.add_argument("--request-id", required=True)
            cmd.add_argument("--reason", required=True)
            cmd.add_argument("--new-attempt", action="store_true")
        if name in {"invoke", "invocation", "cancel-invocation"}:
            cmd.add_argument("--peer", required=True)
            cmd.add_argument("--invocation-id", required=True)
        if name == "invoke":
            cmd.add_argument("--binding-id", required=True)
            cmd.add_argument("--binding-digest", required=True)
            cmd.add_argument("--arguments-file", type=Path, required=True)
            cmd.add_argument("--purpose", choices=["reuse", "verification"], default="reuse")
        if name in {"inspect", "metrics"}:
            cmd.add_argument("--query-file", type=Path)
            cmd.add_argument("--cursor-file", type=Path)
            cmd.add_argument("--page-size", type=int, default=128)
        if name == "metrics":
            cmd.add_argument("--operational", action="store_true")
            cmd.add_argument("--peer", help="operational owner endpoint")
            cmd.add_argument("--work", action="store_true", help="report scoped opportunity work")
            cmd.add_argument(
                "--requests-file", type=Path, help="evaluate up to 32 explicit UseRequests"
            )
        if name == "peer":
            cmd.add_argument("--application", help="explicit installed module:factory")
            cmd.add_argument(
                "--reference",
                action="store_true",
                help="enable the bundled compatibility reference application",
            )
        if name == "migrate":
            cmd.add_argument(
                "--database-url-env",
                help="separate operator bootstrap DSN; not runtime credentials",
            )
        if name == "inspect":
            cmd.add_argument(
                "kind",
                choices=[
                    "capability",
                    "evidence",
                    "revocation",
                    "event",
                    "decision",
                    "opportunity",
                    "proposal",
                ],
            )
        if name == "sync":
            cmd.add_argument("--peer", required=True)
            cmd.add_argument("--page-size", type=int, default=32)
            cmd.add_argument("--max-pages", type=int, default=16)
            cmd.add_argument("--filter-file", type=Path)
            cmd.add_argument("--restart", action="store_true")
    args = parser.parse_args()
    overlay = None
    try:
        result: Any
        if args.command == "lifecycle":
            from .lifecycle_cli import run as run_lifecycle

            result = run_lifecycle(args)
        elif args.command == "opa-install":
            from .opa_install import VERSION, install_opa

            result = {"path": str(install_opa(args.target)), "version": VERSION}
        elif args.command == "binding-check":
            from .bindings import Binding

            binding = Binding.model_validate(_json_file(args.manifest))
            result = {
                "valid": True,
                "binding_digest": binding.digest,
                "binding": binding.model_dump(mode="json"),
                "registered": False,
            }
        elif args.command == "setup":
            from .setup import initialize as initialize_owner

            database_url = os.environ.get(args.database_url_env)
            if not database_url:
                raise ValueError("runtime database URL environment variable is required")
            result = {
                "config": str(
                    initialize_owner(
                        args.directory,
                        owner=args.owner,
                        url=args.url,
                        database_url=database_url,
                        opa=args.opa,
                        application=args.application,
                        listen_port=args.listen_port,
                    )
                ),
                "database_created": False,
                "ready": False,
            }
        elif args.command == "starter":
            from .setup import starter

            result = starter(args.directory)
        elif args.command == "verify-backup":
            from .recovery import verify_backup

            result = verify_backup(args.directory)
        elif args.command == "demo":
            from .demo import initialize, run_demo

            if not args.database_url:
                raise ValueError(
                    "set CIO_TEST_DATABASE_URL to a dedicated PostgreSQL admin database"
                )
            configs = initialize(args.directory, args.database_url, args.opa)
            result = asyncio.run(run_demo(args.directory, configs))
        else:
            config = load_config(args.config)
            if args.command in {"status", "drain", "resume"} and (
                args.identity_name is not None or args.identity_private_key is not None
            ):
                if args.identity_name is None or args.identity_private_key is None:
                    raise ValueError("explicit control identity needs both its name and PEM key")
                from .adapters.a2a import send

                caller_identity = config.identity(args.identity_name, args.identity_private_key)
                result = asyncio.run(
                    send(
                        config,
                        caller_identity,
                        args.peer or config.owner,
                        {"operation": args.command},
                    )
                )
                print(json.dumps(result, default=str))
                return 2 if result.get("error") else 0
            if args.command == "key-rotate":
                from .setup import rotate_key

                print(
                    json.dumps(
                        rotate_key(
                            config, args.directory, compromised=tuple(args.compromised_key_id)
                        )
                    )
                )
                return 0
            identity, overlay = config.runtime()
            if args.command == "check-config":
                result = {"valid": True, "owner": config.owner}
            elif args.command == "database-bootstrap":
                from decimal import Decimal

                from .setup import bootstrap_database

                operator_url = os.environ.get(args.database_url_env)
                if not operator_url:
                    raise ValueError("operator bootstrap URL environment variable is required")
                result = bootstrap_database(config, operator_url, Decimal(args.allowance_work))
            elif args.command == "migrate":
                if args.database_url_env:
                    from .storage import Store

                    bootstrap_url = os.environ.get(args.database_url_env)
                    if not bootstrap_url:
                        raise ValueError("bootstrap database URL environment variable is required")
                    bootstrap = Store(bootstrap_url, config.owner, overlay.store.principals)
                    try:
                        migrate(bootstrap.engine)
                    finally:
                        bootstrap.close()
                else:
                    migrate(overlay.store.engine)
                result = {"migration": "head"}
            elif args.command == "restore-state":
                from .operations import OwnerLock

                lock = OwnerLock(overlay.store)
                try:
                    lock.acquire()
                    generation = overlay.store.reset_sync_after_restore()
                finally:
                    lock.close()
                result = {
                    "generation": generation,
                    "freshness": "invalidated",
                    "intake": "closed across process restarts",
                    "required": "reconcile post-backup work and resynchronize before use",
                }
            elif args.command == "backup":
                from .recovery import backup

                operator_url = os.environ.get(args.database_url_env)
                if not operator_url:
                    raise ValueError("separate backup operator DSN environment variable required")
                prefix = _json_file(args.pg_prefix_file) if args.pg_prefix_file else []
                if not isinstance(prefix, list) or not all(isinstance(arg, str) for arg in prefix):
                    raise ValueError("PostgreSQL client prefix must be JSON argv")
                result = backup(
                    config,
                    args.directory,
                    operator_url=operator_url,
                    pg_prefix=tuple(prefix),
                    tls_private_key=args.tls_private_key,
                )
            elif args.command == "invocation-cleanup":
                from .invocations import InvocationStore

                result = InvocationStore(overlay.store).cleanup_expired(
                    owner=config.owner,
                    limit=args.limit,
                    seconds=args.seconds,
                    dry_run=args.dry_run,
                )
            elif args.command == "reobserve":
                from .bindings import Registry
                from .opportunities import Goal, Opportunities

                goal = Goal.model_validate(_json_file(args.goal_file))
                host = Opportunities(Registry(overlay), identity, (goal,))
                result = asyncio.run(
                    host.reobserve(
                        args.opportunity_id,
                        args.request_id,
                        args.reason,
                        caller=config.owner,
                        new_attempt=args.new_attempt,
                    )
                ).model_dump(mode="json")
            elif args.command in {
                "status",
                "drain",
                "resume",
                "goals",
                "opportunities",
                "step",
                "run",
                "remote-calls",
                "reconcile",
                "recovery-state",
                "recovery-review",
                "resolve-invocation",
            }:
                from .adapters.a2a import send

                operation = {"operation": args.command.replace("-", "_")}
                for name in (
                    "max_candidates",
                    "start",
                    "opportunity_id",
                    "max_steps",
                    "seconds",
                    "invocation_id",
                    "call_scope",
                    "limit",
                    "after",
                    "call_key",
                    "original_caller",
                    "command_id",
                    "reconciler",
                    "checker",
                ):
                    if hasattr(args, name):
                        operation[name] = getattr(args, name)
                if args.command in {"recovery-review", "resolve-invocation"}:
                    operation["arguments"] = _json_file(args.arguments_file)
                if args.command == "resolve-invocation":
                    operation["observations"] = _json_file(args.observations_file)
                result = asyncio.run(send(config, identity, args.peer or config.owner, operation))
                if result.get("error"):
                    print(json.dumps(result))
                    return 2
            elif args.command in {"invoke", "invocation", "cancel-invocation"}:
                from .adapters.a2a import send

                request = {
                    "operation": args.command.replace("-", "_"),
                    "invocation_id": args.invocation_id,
                }
                if args.command == "invoke":
                    arguments = _json_file(args.arguments_file)
                    if not isinstance(arguments, dict):
                        raise ValueError("invocation arguments must be a JSON object")
                    request.update(
                        binding_id=args.binding_id,
                        binding_digest=args.binding_digest,
                        arguments=arguments,
                        purpose=args.purpose,
                    )
                result = asyncio.run(send(config, identity, args.peer, request))
            elif args.command == "sync":
                from .adapters.a2a import synchronize

                filter_data = None
                if args.filter_file:
                    if args.filter_file.stat().st_size > 65536:
                        raise ValueError("filter exceeds size bound")
                    filter_data = json.loads(args.filter_file.read_text(encoding="utf-8"))
                result = asyncio.run(
                    synchronize(
                        config,
                        identity,
                        overlay.store,
                        args.peer,
                        filter_data=filter_data,
                        max_pages=args.max_pages,
                        page_size=args.page_size,
                        restart=args.restart,
                    )
                )
            elif args.command == "peer":
                import uvicorn

                from .observability import configure_logging

                configure_logging(config)

                from .adapters.a2a import application
                from .peer import PeerService

                service: PeerService
                if args.reference and (args.application or config.application):
                    raise ValueError("reference and explicit application modes cannot be combined")
                if args.application or config.application:
                    from .application import load_application

                    service = load_application(config, args.application)
                elif not args.reference and not config.local_development:
                    raise ValueError("production peer requires an explicit installed application")
                else:
                    service = PeerService(config)
                if args.reference:
                    from .reference_peer import load_reference

                    service.overlay.store.close()
                    service = load_reference(config)
                url = urlsplit(config.url)
                lifecycle = getattr(service, "operations", None)
                try:
                    # Production TLS terminates at the operator's authenticated reverse proxy.
                    uvicorn.run(
                        application(
                            config,
                            lifecycle.handle if lifecycle is not None else service.handle,
                            lifespan=lifecycle.lifespan if lifecycle is not None else None,
                        ),
                        host="127.0.0.1",
                        port=config.listen_port or url.port or 8000,
                        access_log=False,
                        log_level="warning",
                        # Keep transport connections bounded while leaving room
                        # for the authenticated 16/4 gate to return Retry-After.
                        # Execution slots and idle/body-receipt connections differ.
                        limit_concurrency=2 * config.max_owner_requests,
                        timeout_graceful_shutdown=30,
                        log_config=None,
                    )
                finally:
                    if lifecycle is not None:
                        service.close()
                    else:
                        service.overlay.store.close()
                return 0
            elif args.command == "inspect":
                query, cursor = _inspection(args, args.kind)
                result = overlay.store.record_page(
                    query, cursor=cursor, limit=args.page_size
                ).model_dump(mode="json")
            elif args.command == "metrics":
                if args.operational:
                    from .adapters.a2a import send

                    if args.work or args.query_file or args.cursor_file or args.requests_file:
                        raise ValueError("operational metrics cannot combine history/query modes")
                    result = asyncio.run(
                        send(
                            config,
                            identity,
                            args.peer or config.owner,
                            {"operation": "operational_metrics"},
                        )
                    )
                    print(json.dumps(result, default=str))
                    return 2 if result.get("error") else 0
                if args.requests_file:
                    if (
                        args.work
                        or args.query_file
                        or args.cursor_file
                        or args.requests_file.stat().st_size > 65536
                    ):
                        raise ValueError(
                            "request metrics cannot combine history filters or exceed byte bound"
                        )
                    requests = json.loads(args.requests_file.read_text(encoding="utf-8"))
                    if not isinstance(requests, list) or not 1 <= len(requests) <= 32:
                        raise ValueError("expected 1 to 32 explicit use requests")
                    result = asyncio.run(
                        capability_metrics(
                            overlay, tuple(UseRequest.model_validate(r) for r in requests)
                        )
                    )
                else:
                    query, cursor = _inspection(args, "opportunity" if args.work else "event")
                    report = work_metrics_page if args.work else metrics_page
                    result = report(overlay.store, query, cursor=cursor, limit=args.page_size)
            else:
                import shutil

                from sqlalchemy import text

                with overlay.store.engine.connect() as conn:
                    db = conn.execute(text("select 1")).scalar() == 1
                opa = shutil.which(config.opa_binary) is not None
                result = {
                    "database": db,
                    "opa": opa,
                    "owner": config.owner,
                    "paid_model_test": "not_run",
                }
                if not opa:
                    print(json.dumps(result))
                    return 2
        print(json.dumps(result, ensure_ascii=False, default=str))
        if args.command == "recovery-review" and result.get("business_state") != "matched":
            return 2
        if args.command in {"invoke", "invocation", "cancel-invocation"}:
            if result.get("error"):
                return 2
            invocation = result if args.command == "invoke" else result.get("invocation")
            if invocation is None:
                return 4
            state = invocation.get("state")
            if state == "running":
                return 3
            if args.command == "cancel-invocation" and state == "cancelled":
                return 0
            return 0 if state == "completed" else 2
        if args.command == "sync" and not result["complete"]:
            return 3
        if args.command == "invocation-cleanup" and result["has_more"]:
            return 3
        if (
            args.command in {"inspect", "metrics"}
            and isinstance(result, dict)
            and result.get("next_cursor")
        ):
            return 3
        if args.command == "lifecycle" and isinstance(result, dict):
            context = result.get("context", {})
            if context.get("record_cursor") or context.get("decision_cursor"):
                return 3
        return 0
    except Exception as exc:
        from .synchronization import ResnapshotRequired

        if isinstance(exc, ResnapshotRequired):
            print(
                json.dumps(
                    {
                        "error": "RESNAPSHOT_REQUIRED",
                        "message": "use sync --restart explicitly; records are retained",
                    }
                ),
                file=sys.stderr,
            )
            return 2
        # Avoid dumping connection strings, request bodies, bearer tokens or private material.
        print(
            json.dumps(
                {
                    "error": type(exc).__name__,
                    "message": "operation failed; check configuration and services",
                }
            ),
            file=sys.stderr,
        )
        if os.environ.get("CIO_DEBUG") == "1":
            raise
        return 2
    finally:
        if overlay is not None:
            overlay.store.close()


def _json_file(path: Path) -> Any:
    with path.open("rb") as source:
        content = source.read(65537)
    if len(content) > 65536:
        raise ValueError("JSON argument file exceeds byte bound")
    return json.loads(content)


def _inspection(args: argparse.Namespace, kind: str) -> tuple[RecordQuery, RecordCursor | None]:
    query = RecordQuery.model_validate(
        _json_file(args.query_file) if args.query_file else {"kinds": [kind]}
    )
    if query.kinds != (kind,):
        raise ValueError("inspection query kind differs from command")
    cursor = RecordCursor.model_validate(_json_file(args.cursor_file)) if args.cursor_file else None
    return query, cursor


if __name__ == "__main__":
    raise SystemExit(main())
