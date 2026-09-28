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
    ):
        cmd = commands.add_parser(name)
        cmd.add_argument("--config", type=Path, required=True)
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
            cmd.add_argument("--work", action="store_true", help="report scoped opportunity work")
            cmd.add_argument(
                "--requests-file", type=Path, help="evaluate up to 32 explicit UseRequests"
            )
        if name == "peer":
            cmd.add_argument(
                "--reference",
                action="store_true",
                help="enable the bundled compatibility reference application",
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
        if args.command == "binding-check":
            from .bindings import Binding

            binding = Binding.model_validate(_json_file(args.manifest))
            result = {
                "valid": True,
                "binding_digest": binding.digest,
                "binding": binding.model_dump(mode="json"),
                "registered": False,
            }
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
            identity, overlay = config.runtime()
            if args.command == "check-config":
                result = {"valid": True, "owner": config.owner}
            elif args.command == "migrate":
                migrate(overlay.store.engine)
                result = {"migration": "head"}
            elif args.command == "restore-state":
                result = {
                    "generation": overlay.store.reset_sync_after_restore(),
                    "freshness": "invalidated",
                    "required": "reconcile post-backup work and resynchronize before use",
                }
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

                from .adapters.a2a import application
                from .peer import PeerService

                service = PeerService(config)
                if args.reference:
                    from .reference_peer import ReferencePeerService

                    service.overlay.store.close()
                    service = ReferencePeerService(config)
                url = urlsplit(config.url)
                try:
                    # Production TLS terminates at the operator's authenticated reverse proxy.
                    uvicorn.run(
                        application(config, service.handle),
                        host="127.0.0.1",
                        port=url.port or 8000,
                        access_log=False,
                        log_level="warning",
                        limit_concurrency=config.max_concurrency + 8,
                        timeout_graceful_shutdown=10,
                    )
                finally:
                    service.overlay.store.close()
                return 0
            elif args.command == "inspect":
                query, cursor = _inspection(args, args.kind)
                result = overlay.store.record_page(
                    query, cursor=cursor, limit=args.page_size
                ).model_dump(mode="json")
            elif args.command == "metrics":
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
        if (
            args.command in {"inspect", "metrics"}
            and isinstance(result, dict)
            and result.get("next_cursor")
        ):
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
