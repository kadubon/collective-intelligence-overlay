"""Isolated finite document comparison; raw negative results are retained."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import random
import re
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from a2a.client import AgentCardResolutionError
from adaptive_documents import ENVIRONMENT, configure_application, write_json
from sqlalchemy import select
from sqlalchemy.engine import make_url

from collective_intelligence_overlay.accounting import metrics_page
from collective_intelligence_overlay.adapters.a2a import send
from collective_intelligence_overlay.bindings import fingerprint
from collective_intelligence_overlay.demo import initialize
from collective_intelligence_overlay.invocations import invocations
from collective_intelligence_overlay.queries import RecordCursor, RecordQuery
from collective_intelligence_overlay.storage import budgets, leases

ALLOWANCES = {
    "baseline": {"producer": Decimal(50), "receiver": Decimal(50), "verifier": Decimal(50)},
    "verification": {"producer": Decimal(50), "receiver": Decimal(50), "verifier": Decimal(14)},
    "connection": {"producer": Decimal(50), "receiver": Decimal(50), "verifier": Decimal(50)},
}
TRAINING = "calibration vocabulary"
HELD_OUT = (
    "A separate evaluation document has seven words.",
    "one",
    "Unicode 文書\twith\nwhitespace",
)


def export_owner(config: Any, destination: Path) -> dict[str, Any]:
    """Export original signed records and page-local costs without private config."""
    _, overlay = config.runtime()
    store = overlay.store
    try:
        pages = []
        cursor = None
        for _ in range(128):
            page = metrics_page(store, cursor=cursor, limit=128)
            pages.append(page)
            if page["complete"]:
                break
            cursor = RecordCursor.model_validate(page["next_cursor"])
        else:
            raise ValueError("metric export exceeded declared page bound")
        signed = []
        for kinds in (
            ("capability", "evidence", "revocation", "event"),
            ("opportunity", "proposal"),
        ):
            cursor = None
            for _ in range(128):
                page = store.record_page(RecordQuery(kinds=kinds), cursor=cursor, limit=128)
                for item in page.items:
                    key = item.subject.key if item.kind == "capability" else item.id
                    signed.append(store.signed_record(store.reference(item.kind, item.issuer, key)))
                if page.next_cursor is None:
                    break
                cursor = page.next_cursor
            else:
                raise ValueError("record export exceeded declared page bound")
        with store.engine.connect() as conn:
            execution_states = [
                dict(row)
                for row in conn.execute(
                    select(
                        invocations.c.caller,
                        invocations.c.id,
                        invocations.c.lease_id,
                        invocations.c.state,
                        invocations.c.phase,
                        invocations.c.reservation_state,
                        invocations.c.release_reason,
                    )
                ).mappings()
            ]
            remaining = {row.unit: str(row.remaining) for row in conn.execute(select(budgets))}
            reserved = [
                {
                    "task": row.task_id,
                    "unit": row.unit,
                    "reservation": str(row.reservation),
                    "state": row.state,
                    "actual": str(row.actual) if row.actual is not None else None,
                }
                for row in conn.execute(select(leases))
            ]
        write_json(
            destination,
            {
                "owner": store.owner,
                "database_identity": make_url(config.database_url.get_secret_value()).database,
                "public_identities": {
                    key: value.model_dump(mode="json") for key, value in config.identities.items()
                },
                "invocations": execution_states,
                "metrics_pages": pages,
                "signed_records": signed,
                "remaining": remaining,
                "reservations": reserved,
            },
        )
        return {
            "report": destination.name,
            "remaining": remaining,
            "signed_record_count": len(signed),
        }
    finally:
        store.close()


async def run_arm(
    directory: Path, admin_url: str, opa: str, mode: str, scenario: str
) -> dict[str, Any]:
    if mode not in {"static-run", "adaptive-run"} or scenario not in ALLOWANCES:
        raise ValueError("unknown experiment assignment")
    if await asyncio.to_thread(directory.exists):
        raise FileExistsError("experiment arm directory already exists")
    started = time.perf_counter()
    report: dict[str, Any] = {
        "mode": mode,
        "scenario": scenario,
        "status": "incomplete",
        "calls": [],
        "business_results": [],
        "missing_costs": ["CPU_seconds", "tokens", "USD"],
        "allowance_is_measured_cost": False,
        "time_to_success_seconds": None,
    }
    configs: dict[str, Any] = {}
    identities = {}
    processes = []
    logs = []
    stage = "initialize"

    async def call(owner: str, **data: Any) -> dict[str, Any]:
        if len(report["calls"]) >= 128:
            raise ValueError("external call bound exceeded")
        call_started = time.perf_counter()
        item = {"owner": owner, "operation": data["operation"], "status": "unknown"}
        report["calls"].append(item)
        try:
            value = await send(configs[owner], identities[owner], owner, data)
            item["status"] = "returned"
            return value
        finally:
            item["wall_seconds"] = time.perf_counter() - call_started

    async def sync(owner: str, source: str) -> None:
        if not (await call(owner, operation="sync", peer=source, page_size=4))["complete"]:
            raise ValueError("incomplete initial synchronization")

    try:
        async with asyncio.timeout(240):
            allowance = ALLOWANCES[scenario]
            report["initial_allowance"] = {owner: str(value) for owner, value in allowance.items()}
            initializing = asyncio.create_task(
                asyncio.to_thread(initialize, directory, admin_url, opa, work_allowances=allowance)
            )
            try:
                configs = await asyncio.shield(initializing)
            except asyncio.CancelledError:
                configs = await initializing
                raise
            for owner, original in configs.items():
                config = original.model_copy(
                    update={"execution_environment": ENVIRONMENT, "max_seconds": 300}
                )
                configs[owner] = config
                value = config.model_dump(mode="json")
                value["database_url"] = config.database_url.get_secret_value()
                write_json(config.private_key.parent / "config.json", value)
                identity, overlay = config.runtime()
                identities[owner] = identity
                overlay.store.close()
            configure_application(configs, TRAINING, connection_mismatch=scenario == "connection")
            stage = "startup"
            for owner, config in configs.items():
                log = (config.private_key.parent / "experiment.log").open("wb")
                logs.append(log)
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    str(Path(__file__).with_name("adaptive_documents.py").resolve()),
                    "--config",
                    str(config.private_key.parent / "config.json"),
                    stdout=log,
                    stderr=log,
                )
                processes.append(process)
                async with asyncio.timeout(25):
                    while True:
                        if process.returncode is not None:
                            raise RuntimeError("peer exited during startup")
                        try:
                            await send(config, identities[owner], owner, {"operation": "metrics"})
                            break
                        except (httpx.HTTPError, ConnectionError, AgentCardResolutionError):
                            await asyncio.sleep(0.1)
            stage = "initial_checks"
            for provider, name, arguments in (
                ("producer", "words", {"text": "initial primitive check"}),
                ("receiver", "render", {"words": 7}),
                ("receiver", "remote-words", {"text": "remote primitive check"}),
            ):
                result = await call(
                    "verifier",
                    operation="verify",
                    attempt="initial-" + name,
                    provider=provider,
                    name=name,
                    arguments=arguments,
                )
                if result["evidence"]["verdict"] != "PASS":
                    raise ValueError("initial primitive check did not pass")
                if name == "words":
                    await sync("producer", "verifier")
                    await sync("receiver", "producer")
                    await sync("receiver", "verifier")
            await sync("receiver", "verifier")
            for target in ("verifier", "receiver"):
                checked = await call("producer", operation="certify-checker", target=target)
                report.setdefault("checker_calibration", []).append(checked)
                if checked.get("evidence", {}).get("verdict") != "PASS":
                    raise ValueError("checker calibration not PASS")
                if target == "verifier":
                    await sync("verifier", "producer")
                    await sync("receiver", "verifier")
                await sync("receiver", "producer")
            report["setup_wall_seconds"] = time.perf_counter() - started
            stage = "formation"
            run = await call("receiver", operation=mode, max_steps=8)
            report["run"] = run
            report["passed_formation_checks"] = len(
                {
                    item["evidence"]["binding_digest"]
                    for item in run["history"]
                    if item["kind"] == "verification"
                    and item.get("evidence")
                    and item["evidence"]["verdict"] == "PASS"
                }
            )
            stage = "business_evaluation"
            if run["reason"] == "goals_satisfied":
                target = await call("receiver", operation="describe", name="triage")
                from collective_intelligence_overlay.bindings import Binding

                binding = Binding.model_validate(target["binding"])
                for index, text in enumerate(HELD_OUT):
                    output = await call(
                        "receiver",
                        operation="invoke",
                        invocation_id=f"evaluation-{index}",
                        binding_id=binding.id,
                        binding_digest=binding.digest,
                        arguments={"text": text},
                    )
                    expected = {
                        "long": len(re.findall(r"\S+", text)) > len(re.findall(r"\S+", TRAINING)),
                        "threshold": len(re.findall(r"\S+", TRAINING)),
                    }
                    passed = output.get("state") == "completed" and output.get("result") == expected
                    report["business_results"].append(
                        {
                            "task": index,
                            "input": text,
                            "expected": expected,
                            "output": output,
                            "passed": passed,
                        }
                    )
                if all(item["passed"] for item in report["business_results"]):
                    report["time_to_success_seconds"] = time.perf_counter() - started
            report["status"] = "finished" if run["reason"] == "goals_satisfied" else "censored"
    except Exception as exc:
        report.update(status="failed", failed_stage=stage, error_type=type(exc).__name__)
    finally:
        report["time_to_last_outcome_seconds"] = time.perf_counter() - started
        for process in processes:
            if process.returncode is None:
                process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 10)
            except TimeoutError:
                process.kill()
                await process.wait()
        for log in logs:
            log.close()
        report["owners"] = {}
        for owner, config in configs.items():
            try:
                report["owners"][owner] = await asyncio.to_thread(
                    export_owner, config, directory / f"{owner}-observations.json"
                )
            except Exception as exc:
                report["owners"][owner] = {"export_error": type(exc).__name__}
                report["status"] = "incomplete_export"
        report["passed_business_tasks"] = sum(item["passed"] for item in report["business_results"])
        report["unreached_business_tasks"] = len(HELD_OUT) - len(report["business_results"])
        report["wall_including_export_seconds"] = time.perf_counter() - started
        if configs:
            write_json(directory / "result.json", report)
    return report


async def compare(directory: Path, admin_url: str, opa: str, seed: int = 0) -> dict[str, Any]:
    await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=False)
    assignments = [
        (scenario, mode) for scenario in ALLOWANCES for mode in ("static-run", "adaptive-run")
    ]
    random.Random(seed).shuffle(assignments)
    protocol = {
        "version": "documents-comparison.v3",
        "initial_work_allowance": {
            scenario: {owner: str(value) for owner, value in amounts.items()}
            for scenario, amounts in ALLOWANCES.items()
        },
        "pilot_adjustment": (
            "v1 verifier=10 stopped during calibration; v2 verifier=14 tests "
            "post-calibration checking scarcity; v3 adds input-contract mismatch; "
            "all previous results retained"
        ),
        "connection_condition": {
            "initial_report_contract": "report.in.v1",
            "requested_report_contract": "report.in.v2",
            "adapter": "installed document-to-text transformation in both policies",
            "initial_candidate": "operator-installed, no PASS or formation receipt",
        },
        "sources": {
            name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in (
                "evaluate_documents.py",
                "adaptive_documents.py",
                "document_application.py",
            )
        },
        "seed": seed,
        "assignments": assignments,
        "training": TRAINING,
        "held_out": HELD_OUT,
        "arm_timeout_seconds": 240,
        "step_bound": 8,
        "exclusions": "none; all failures and censoring retained",
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("collective-intelligence-overlay", "agent-framework-core", "a2a-sdk")
        },
    }
    source_directory = directory / "sources"
    await asyncio.to_thread(source_directory.mkdir)
    for name in protocol["sources"]:
        await asyncio.to_thread(
            (source_directory / name).write_bytes, Path(__file__).with_name(name).read_bytes()
        )
    write_json(directory / "protocol.json", protocol)
    results = []
    for index, (scenario, mode) in enumerate(assignments):
        result = await run_arm(directory / f"arm-{index}", admin_url, opa, mode, scenario)
        results.append({"directory": f"arm-{index}", **result})
        write_json(
            directory / "results.json",
            {
                "protocol_digest": fingerprint(protocol),
                "arms": results,
                "limitations": [
                    "one deterministic run per condition; no statistical superiority claim",
                    "connection covers input adaptation, not arbitrary environment portability",
                    "wall times are inclusive observations, never summed across parent/child calls",
                ],
            },
        )
        print(
            json.dumps(
                {
                    "arm": index,
                    "scenario": scenario,
                    "mode": mode,
                    "status": result["status"],
                    "passed_business_tasks": result["passed_business_tasks"],
                }
            ),
            flush=True,
        )
    return {"protocol": protocol, "arms": results}


def validate_results(directory: Path) -> dict[str, Any]:
    """Verify saved public observations and isolation, not universal business truth."""
    from securesystemslib.signer import Key

    from collective_intelligence_overlay.models import Evidence
    from collective_intelligence_overlay.security import Principal, verify

    protocol = json.loads((directory / "protocol.json").read_text(encoding="utf-8"))
    saved = json.loads((directory / "results.json").read_text(encoding="utf-8"))
    if saved["protocol_digest"] != fingerprint(protocol):
        raise ValueError("protocol digest mismatch")
    if len(saved["arms"]) != len(protocol["assignments"]):
        raise ValueError("comparison has unfinished assignments")
    for name, expected in protocol["sources"].items():
        if (
            Path(name).name != name
            or hashlib.sha256((directory / "sources" / name).read_bytes()).hexdigest() != expected
        ):
            raise ValueError("recorded implementation source mismatch")
    databases: set[str] = set()
    prior_keys: set[str] = set()
    verified_records = 0
    for index, ((scenario, mode), arm) in enumerate(
        zip(protocol["assignments"], saved["arms"], strict=True)
    ):
        if arm["directory"] != f"arm-{index}":
            raise ValueError("unexpected arm report directory")
        if (scenario, mode) != (arm["scenario"], arm["mode"]):
            raise ValueError("assignment order changed")
        if arm["initial_allowance"] != protocol["initial_work_allowance"][scenario]:
            raise ValueError("arm allowance differs from preregistered condition")
        if set(arm["owners"]) != {"producer", "verifier", "receiver"}:
            raise ValueError("owner report missing")
        current_keys: set[str] = set()
        evidence = {}
        for owner, summary in arm["owners"].items():
            if summary["report"] != f"{owner}-observations.json":
                raise ValueError("unexpected owner report path")
            report = json.loads(
                (directory / arm["directory"] / summary["report"]).read_text(encoding="utf-8")
            )
            if report["owner"] != owner or report["database_identity"] in databases:
                raise ValueError("owner/database isolation violated")
            databases.add(report["database_identity"])
            principals = {
                name: Principal(
                    Key.from_dict(value["keyid"], value["key"]),
                    value["trust_group"],
                    frozenset(value["methods"]),
                )
                for name, value in report["public_identities"].items()
            }
            current_keys.update(value["keyid"] for value in report["public_identities"].values())
            for envelope in report["signed_records"]:
                item = verify(envelope, principals)
                verified_records += 1
                if isinstance(item, Evidence):
                    evidence[item.issuer, item.id] = item
            invocations_by_lease = {item["lease_id"]: item for item in report["invocations"]}
            held_or_consumed = sum(
                (
                    Decimal(item["reservation"])
                    for item in report["reservations"]
                    if invocations_by_lease.get(item["task"], {}).get("reservation_state")
                    != "released"
                ),
                Decimal(0),
            )
            if Decimal(report["remaining"]["work"]) + held_or_consumed != Decimal(
                arm["initial_allowance"][owner]
            ):
                raise ValueError("allowance conservation violated")
        if current_keys & prior_keys:
            raise ValueError("signing identities reused between arms")
        prior_keys.update(current_keys)
        for item in arm.get("run", {}).get("history", []):
            if item.get("evidence"):
                claimed = Evidence.model_validate(item["evidence"])
                if evidence.get((claimed.issuer, claimed.id)) != claimed:
                    raise ValueError("reported check lacks matching signed evidence")
        if [item["task"] for item in arm["business_results"]] != list(
            range(len(arm["business_results"]))
        ):
            raise ValueError("held-out tasks reordered, repeated or skipped")
        passed = 0
        for item in arm["business_results"]:
            text = protocol["held_out"][item["task"]]
            threshold = len(re.findall(r"\S+", protocol["training"]))
            expected = {"long": len(re.findall(r"\S+", text)) > threshold, "threshold": threshold}
            actual_pass = (
                item["output"].get("state") == "completed"
                and item["output"].get("result") == expected
            )
            if (
                item["input"] != text
                or item["expected"] != expected
                or item["passed"] != actual_pass
            ):
                raise ValueError("held-out evaluation mismatch")
            passed += int(actual_pass)
        if passed != arm["passed_business_tasks"] or len(arm["business_results"]) + arm[
            "unreached_business_tasks"
        ] != len(protocol["held_out"]):
            raise ValueError("business outcome counts mismatch")
    return {
        "validator": "documents-report-validation.v1",
        "arms": len(saved["arms"]),
        "separate_databases": len(databases),
        "verified_signed_records": verified_records,
        "allowance_conserved": True,
        "statistical_superiority": "not established",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    targets = parser.add_mutually_exclusive_group(required=True)
    targets.add_argument("--directory", type=Path)
    targets.add_argument("--verify", type=Path)
    parser.add_argument("--opa")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    if args.verify:
        print(json.dumps(validate_results(args.verify.resolve()), indent=2))
        return
    url = os.environ.get("CIO_TEST_DATABASE_URL")
    if not url or not args.opa:
        parser.error("CIO_TEST_DATABASE_URL must name a dedicated PostgreSQL admin database")
    asyncio.run(compare(args.directory.resolve(), url, str(Path(args.opa).resolve()), args.seed))


if __name__ == "__main__":
    main()
