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
from .accounting import metrics
from .config import load_config
from .storage import migrate


def main() -> int:
    parser = argparse.ArgumentParser(prog="collective-intelligence-overlay")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="run the API-key-free three-peer demonstration")
    demo.add_argument("--directory", type=Path, required=True)
    demo.add_argument("--database-url", default=os.environ.get("CIO_TEST_DATABASE_URL"))
    demo.add_argument("--opa", default=os.environ.get("CIO_OPA", "opa"))
    for name in ("check-config", "migrate", "peer", "inspect", "metrics", "doctor", "sync"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--config", type=Path, required=True)
        if name == "inspect":
            cmd.add_argument(
                "kind", choices=["capability", "evidence", "revocation", "event", "decision"]
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
        if args.command == "demo":
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
                result = (
                    overlay.store.decision_records()
                    if args.kind == "decision"
                    else [r.model_dump(mode="json") for r in overlay.store.read_records(args.kind)]
                )
            elif args.command == "metrics":
                result = metrics(overlay.store.events())
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
        if args.command == "sync" and not result["complete"]:
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


if __name__ == "__main__":
    raise SystemExit(main())
