"""Actual stopped-writer 0.3.2 -> 0.4.0 CSV application migration and recovery.

Run with a normally installed candidate and a separate normally installed 0.3.2
interpreter. This is a POSIX loopback legacy compatibility protocol, not an HTTPS
production-profile measurement. Private configs/backups never enter the report.
"""

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request
import zipfile
from contextlib import ExitStack
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from collective_intelligence_overlay.adapters.a2a import send
from collective_intelligence_overlay.config import load_config
from collective_intelligence_overlay.recovery import backup, verify_backup

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests/e2e"), str(ROOT / "tests/integration")]
ORDERS = {
    "records": "kind, issuer, record_id",
    "remote_calls": "caller, call_key",
    "invocations": "caller, id",
    "leases": "task_id",
    "budgets": "unit",
}
LEGACY_WHEEL = "collective_intelligence_overlay-0.3.2-py3-none-any.whl"
LEGACY_SHA256 = "cc4086d5e27cbdc1d13d2d79b7438e4c787cea208b9e321b8fc0fcbc4e279ae9"


def write(path, data):
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    path.chmod(0o600)


def saved_rows(config):
    engine = create_engine(config.database_url.get_secret_value(), hide_parameters=True)
    try:
        with engine.connect() as conn:
            return {
                name: json.loads(
                    json.dumps(
                        [
                            dict(row)
                            for row in conn.execute(
                                text(f"SELECT * FROM {name} ORDER BY {order}")
                            ).mappings()
                        ],
                        default=str,
                    )
                )
                for name, order in ORDERS.items()
            }
    finally:
        engine.dispose()


def assert_preserved(before, after):
    for name, rows in before.items():
        actual = after[name]
        assert len(actual) == len(rows), (name, "row count changed during offline migration")
        for old, new in zip(rows, actual, strict=True):
            assert {column: new[column] for column in old} == old, (name, "old projection changed")
    assert before["records"] and before["remote_calls"]
    assert any(row["state"] == "unknown" for row in before["invocations"])


def assert_original_response(original, current):
    # The additive reported invocation argument digest is separate from the
    # missing legacy provider mapping identity; preserve every old response field.
    assert {key: current[key] for key in original} == original


def restrict_and_migrate(config, admin_url, config_path):
    runtime = make_url(config.database_url.get_secret_value())
    admin = make_url(admin_url).set(database=runtime.database)
    role, owner = runtime.username, admin.username
    assert re.fullmatch(r"cio_[0-9a-f]{32}", role)
    assert re.fullmatch(r"[a-z][a-z0-9_]{0,62}", owner)
    engine = create_engine(admin, hide_parameters=True)
    try:
        with engine.begin() as conn:
            conn.execute(text(f'REASSIGN OWNED BY "{role}" TO "{owner}"'))
            conn.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
            conn.execute(text(f'GRANT CONNECT ON DATABASE "{runtime.database}" TO "{role}"'))
    finally:
        engine.dispose()
    environment = {**os.environ, "CIO_UPGRADE_DDL_URL": admin.render_as_string(hide_password=False)}
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "collective_intelligence_overlay.cli",
            "migrate",
            "--config",
            str(config_path),
            "--database-url-env",
            "CIO_UPGRADE_DDL_URL",
        ],
        capture_output=True,
        timeout=60,
        env=environment,
        cwd=config_path.parent,
    )
    assert completed.returncode == 0, "installed operator migration failed"
    engine = create_engine(admin, hide_parameters=True)
    try:
        with engine.begin() as conn:
            conn.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))
            conn.execute(
                text(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
                    f'TO "{role}"'
                )
            )
            conn.execute(text(f'REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM "{role}"'))
            conn.execute(text(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}"'))
    finally:
        engine.dispose()
    engine = create_engine(config.database_url.get_secret_value(), hide_parameters=True)
    try:
        with engine.connect() as conn:
            assert not conn.execute(
                text(
                    "SELECT has_schema_privilege(current_user,'public','CREATE') OR "
                    "has_table_privilege(current_user,'alembic_version','UPDATE') OR "
                    "EXISTS(SELECT 1 FROM pg_database WHERE datname=current_database() "
                    "AND datdba=(SELECT oid FROM pg_roles WHERE rolname=current_user))"
                )
            ).scalar_one()
    finally:
        engine.dispose()


def initialize_runtime(args):
    assert os.name == "posix", "legacy graceful-stop protocol requires POSIX SIGTERM"
    assert importlib.metadata.version("collective-intelligence-overlay") in {
        "0.4.0",
        "0.4.1",
        "0.4.2",
        "0.4.3",
        "0.4.4",
    }
    assert (
        Path(
            importlib.metadata.distribution("collective-intelligence-overlay").locate_file(
                "collective_intelligence_overlay/__init__.py"
            )
        )
        .resolve()
        .is_relative_to(Path(sys.prefix).resolve())
    ), "normal installed candidate required"
    distribution = importlib.metadata.distribution("collective-intelligence-overlay")
    verified = 0
    with zipfile.ZipFile(args.candidate_wheel) as archive:
        for name in archive.namelist():
            if name.endswith("/") or name.endswith(".dist-info/RECORD"):
                continue
            assert Path(distribution.locate_file(name)).read_bytes() == archive.read(name)
            verified += 1
    assert verified > 0
    if args.legacy_python is None:
        assert args.legacy_wheel is None, "automatic legacy setup needs both legacy options omitted"
        args.private.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        args.legacy_wheel = args.private.parent / LEGACY_WHEEL
        with urllib.request.urlopen(
            "https://pypi.org/pypi/collective-intelligence-overlay/0.3.2/json", timeout=30
        ) as response:
            metadata = json.load(response)
        entry = next(item for item in metadata["urls"] if item["filename"] == LEGACY_WHEEL)
        assert entry["digests"]["sha256"] == LEGACY_SHA256
        assert entry["url"].startswith("https://files.pythonhosted.org/")
        with urllib.request.urlopen(entry["url"], timeout=30) as response:
            content = response.read(4 * 1024 * 1024 + 1)
        assert len(content) <= 4 * 1024 * 1024
        assert hashlib.sha256(content).hexdigest() == LEGACY_SHA256
        args.legacy_wheel.write_bytes(content)
        venv = args.private.parent / "legacy-env"
        subprocess.run(["uv", "venv", "--python", sys.executable, str(venv)], check=True)
        args.legacy_python = venv / "bin/python"
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(args.legacy_python),
                str(args.legacy_wheel) + "[agents]",
            ],
            check=True,
        )
    assert args.legacy_wheel is not None
    # Preserve the venv launcher path: resolving its symlink invokes the base
    # interpreter and loses the normally installed legacy environment.
    args.legacy_python = args.legacy_python.absolute()
    legacy_environment = {
        **os.environ,
        "CIO_PACKAGE_RUNTIME_EXE": str(args.legacy_python.resolve()),
    }
    args.private.mkdir(mode=0o700, parents=True, exist_ok=False)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    legacy_check = subprocess.run(
        [
            str(args.legacy_python),
            "-c",
            "import importlib.metadata,pathlib,sys,collective_intelligence_overlay as c; "
            "assert importlib.metadata.version('collective-intelligence-overlay')=='0.3.2'; "
            "assert pathlib.Path(c.__file__).resolve().is_relative_to("
            "pathlib.Path(sys.prefix).resolve()); "
            "import zipfile,hashlib; p=pathlib.Path(sys.argv[1]); "
            "assert hashlib.sha256(p.read_bytes()).hexdigest()=="
            "'cc4086d5e27cbdc1d13d2d79b7438e4c787cea208b9e321b8fc0fcbc4e279ae9'; "
            "d=importlib.metadata.distribution('collective-intelligence-overlay'); "
            "z=zipfile.ZipFile(p); "
            "assert all(pathlib.Path(d.locate_file(n)).read_bytes()==z.read(n) "
            "for n in z.namelist() if not n.endswith('/') and "
            "not n.endswith('.dist-info/RECORD'))",
            str(args.legacy_wheel.resolve()),
        ],
        capture_output=True,
        timeout=20,
        cwd=args.private,
        env=legacy_environment,
    )
    assert legacy_check.returncode == 0, "normal installed legacy 0.3.2 required"
    environment = {
        **legacy_environment,
        "CIO_UPGRADE_ADMIN_URL": args.database_url,
        "CIO_TEST_DATABASE_URL": args.database_url,
    }
    os.environ["CIO_TEST_DATABASE_URL"] = args.database_url
    initialized = subprocess.run(
        [
            str(args.legacy_python),
            "-c",
            "import os,sys; from pathlib import Path; from collective_intelligence_overlay.demo "
            "import initialize; initialize(Path(sys.argv[1]),"
            "os.environ['CIO_UPGRADE_ADMIN_URL'],sys.argv[2])",
            str(args.private / "legacy"),
            str(args.opa.resolve()),
        ],
        capture_output=True,
        timeout=60,
        env=environment,
        cwd=args.private,
    )
    assert initialized.returncode == 0, "legacy database initialization failed"
    homes = {name: args.private / "legacy" / name for name in ("producer", "verifier", "receiver")}
    configs = {name: load_config(home / "config.json") for name, home in homes.items()}
    identities = {
        name: config.identity(name, config.private_key) for name, config in configs.items()
    }
    return homes, configs, identities


async def main(args):
    from a2a.client import AgentCardResolutionError
    from document_recovery_protocol import close_restored_intake, restore_home

    from collective_intelligence_overlay.reference_peer import load_reference

    homes, configs, identities = await asyncio.to_thread(initialize_runtime, args)
    processes, logs, calls = {}, [], []
    report = {
        "status": "running",
        "legacy": "0.3.2",
        "candidate": importlib.metadata.version("collective-intelligence-overlay"),
        "scope": "POSIX stopped-writer loopback CSV compatibility; no HTTPS-profile claim",
        "legacy_wheel_sha256": hashlib.sha256(args.legacy_wheel.read_bytes()).hexdigest(),
        "candidate_wheel_sha256": hashlib.sha256(args.candidate_wheel.read_bytes()).hexdigest(),
    }
    started = time.monotonic()

    async def call(owner, **data):
        result = await send(configs[owner], identities[owner], owner, data)
        calls.append(
            {
                "owner": owner,
                "operation": data["operation"],
                "invocation_id": data.get("invocation_id"),
                "result": result,
            }
        )
        return result

    async def start(owner, python, home):
        log = (home / f"peer-{len(logs)}.log").open("wb")
        logs.append(log)
        process = await asyncio.create_subprocess_exec(
            str(python),
            "-m",
            "collective_intelligence_overlay.cli",
            "peer",
            "--reference",
            "--config",
            str(home / "config.json"),
            stdout=log,
            stderr=log,
            cwd=home,
            env={**os.environ, "CIO_PACKAGE_RUNTIME_EXE": str(python)},
        )
        processes[owner] = process
        for _ in range(120):
            assert process.returncode is None, "peer exited during startup; private log retained"
            try:
                await call(owner, operation="metrics")
                return
            except (httpx.HTTPError, ConnectionError, AgentCardResolutionError):
                await asyncio.sleep(0.1)
        raise AssertionError("peer startup timeout")

    async def stop(owner):
        process = processes.pop(owner)
        process.terminate()
        await asyncio.wait_for(process.wait(), 15)
        # Uvicorn restores and reraises captured SIGTERM after graceful shutdown.
        assert process.returncode in (0, -signal.SIGTERM), "owner terminal witness unavailable"
        try:
            await send(configs[owner], identities[owner], owner, {"operation": "metrics"})
        except (httpx.HTTPError, ConnectionError, AgentCardResolutionError):
            return
        raise AssertionError("stopped owner still receives new connections")

    async def check(owner, item, source, invocation):
        binding, cap = item["binding"], item["capability"]
        probe = await send(
            configs["verifier"],
            identities["verifier"],
            owner,
            {
                "operation": "invoke",
                "invocation_id": invocation,
                "binding_id": binding["id"],
                "binding_digest": binding["digest"]
                if "digest" in binding
                else cap["binding_digest"],
                "arguments": {"source": source},
                "purpose": "verification",
            },
        )
        assert probe["state"] == "completed"
        result = await call(
            "verifier",
            operation="work",
            mode="verify-registered",
            attempt=invocation + "-check",
            capability=cap,
            binding=binding,
            source=source,
            result=probe["result"],
            receiver="receiver",
        )
        assert result["evidence"]["verdict"] == "PASS"
        await call(owner, operation="sync", peer="verifier")

    try:
        report["stage"] = "legacy-live-work"
        for owner in homes:
            await start(owner, args.legacy_python, homes[owner])
        registered = (await call("producer", operation="reference-register"))["registrations"][0]
        source = "category,amount\na,3.50\nb,-1.25\n"
        await check("producer", registered, source, "old-independent-probe")
        for peer in ("producer", "verifier"):
            await call("receiver", operation="sync", peer=peer)
        imported = await call(
            "receiver", operation="reference-import", binding=registered["binding"]
        )
        await check("receiver", imported, source, "old-import-probe")
        binding, cap = imported["binding"], imported["capability"]
        request = {
            "operation": "invoke",
            "invocation_id": "old-completed-original",
            "binding_id": binding["id"],
            "binding_digest": cap["binding_digest"],
            "arguments": {"source": source},
        }
        completed = await call("receiver", **request)
        assert completed["state"] == "completed" and completed["result"]["total"] == "2.25"
        await stop("producer")
        unknown_request = {**request, "invocation_id": "old-uncertain-original"}
        unknown = await call("receiver", **unknown_request)
        assert unknown["state"] == "unknown" and unknown["reservation_state"] == "held"
        await start("producer", args.legacy_python, homes["producer"])
        for owner in tuple(processes):
            await stop(owner)
        before = {owner: saved_rows(config) for owner, config in configs.items()}
        assert all(
            not any(row["state"] == "running" for row in state["invocations"])
            for state in before.values()
        )
        archives = {}
        report["stage"] = "coherent-backup-and-offline-migration"
        for owner, config in configs.items():
            archives[owner] = await asyncio.to_thread(
                backup,
                config,
                args.private / ("legacy-backup-" + owner),
                operator_url=args.database_url,
            )
            verify_backup(args.private / ("legacy-backup-" + owner))
            await asyncio.to_thread(
                restrict_and_migrate, config, args.database_url, homes[owner] / "config.json"
            )
            after = saved_rows(config)
            # Each owner preserves all old columns. The receiver additionally
            # carries actual cross-peer call mappings and uncertain work.
            if owner == "receiver":
                assert_preserved(before[owner], after)
                assert all(row["arguments_digest"] is None for row in after["remote_calls"])
            else:
                for table, rows in before[owner].items():
                    assert len(rows) == len(after[table])
                    assert all(
                        {key: new[key] for key in old} == old
                        for old, new in zip(rows, after[table], strict=True)
                    )
        report["offline_old_columns_and_signed_envelopes_preserved"] = True
        report["legacy_backup_manifests"] = archives
        report["stage"] = "upgraded-original-id-and-drain"
        for owner in homes:
            await start(owner, sys.executable, homes[owner])
        assert_original_response(
            completed,
            (
                await call(
                    "receiver", operation="invocation", invocation_id=request["invocation_id"]
                )
            )["invocation"],
        )
        assert_original_response(
            unknown,
            (
                await call(
                    "receiver",
                    operation="invocation",
                    invocation_id=unknown_request["invocation_id"],
                )
            )["invocation"],
        )
        await call("receiver", operation="drain")
        assert (await call("receiver", **{**request, "invocation_id": "upgrade-drain-refused"}))[
            "error"
        ] == "SERVICE_INTAKE_CLOSED"
        assert (await call("receiver", operation="resume"))["state"] == "ready"
        await stop("receiver")
        home = homes["receiver"]
        settings = home / "application-settings.json"
        write(settings, {"recovery_reference_config": "preserved-reference.json"})
        data = json.loads((home / "config.json").read_text())
        data["application_settings"] = str(settings)
        write(home / "config.json", data)
        write(home / "preserved-reference.json", data)
        original = load_config(home / "config.json")
        host = load_reference(original)
        host.close()  # Publish only the explicit unchecked query candidate before backup.
        archive = args.private / "upgraded-backup"
        await asyncio.to_thread(backup, original, archive, operator_url=args.database_url)
        verify_backup(archive)
        report["stage"] = "closed-restoration-and-external-review"
        with ExitStack() as stack:
            restored = await asyncio.to_thread(
                restore_home, original, archive, args.private / "restored", stack
            )
            configs["receiver"] = restored
            await asyncio.to_thread(close_restored_intake, restored)
            await start("receiver", sys.executable, restored.private_key.parent)
            assert (await call("receiver", operation="status"))["state"] == "degraded"
            assert (await call("receiver", operation="resume"))["state"] == "degraded"
            for peer in ("producer", "verifier"):
                assert (await call("receiver", operation="sync", peer=peer))["complete"]
            review = await call(
                "receiver",
                operation="recovery_review",
                command_id="upgrade-review",
                checker="reference-recovery-state",
                arguments={},
            )
            assert review["business_state"] == "matched"
            assert review["independent_verification"] == "UNKNOWN"
            assert (await call("receiver", operation="status"))["state"] == "degraded"
            assert (await call("receiver", operation="resume"))["state"] == "ready"
            for invocation, expected in (
                (request["invocation_id"], completed),
                (unknown_request["invocation_id"], unknown),
            ):
                assert_original_response(
                    expected,
                    (await call("receiver", operation="invocation", invocation_id=invocation))[
                        "invocation"
                    ],
                )
            retained = saved_rows(restored)
            assert_original_response(unknown, await call("receiver", **unknown_request))
            assert saved_rows(restored)["budgets"] == retained["budgets"]
            assert saved_rows(restored)["remote_calls"] == retained["remote_calls"]
            local = await call(
                "receiver", operation="reference-import", binding=registered["binding"]
            )
            assert local["binding"] == imported["binding"]
            new_result = await call(
                "receiver", **{**request, "invocation_id": "after-upgrade-reuse"}
            )
            assert (
                new_result["state"] == "completed" and new_result["result"] == completed["result"]
            )
            report["closed_restore_external_match_explicit_resume"] = review
            report["new_business_reuse_after_recovery"] = new_result["state"]
            await stop("receiver")
        report["status"] = "passed"
    except BaseException as error:
        report["status"] = "failed"
        report["failure_type"] = type(error).__name__
        raise
    finally:
        for owner in tuple(processes):
            process = processes.pop(owner)
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), 15)
                except TimeoutError:
                    process.kill()
                    await process.wait()
        for log in logs:
            log.close()
        report["elapsed_seconds"] = time.monotonic() - started
        report["call_count"] = len(calls)
        write(args.output / "calls.json", calls)
        report["calls_sha256"] = hashlib.sha256(
            (args.output / "calls.json").read_bytes()
        ).hexdigest()
        write(args.output / "report.json", report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-python", type=Path)
    parser.add_argument("--legacy-wheel", type=Path)
    parser.add_argument("--candidate-wheel", type=Path, required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--opa", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(main(parser.parse_args()))
