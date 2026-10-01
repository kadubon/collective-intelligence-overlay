"""Source-only matched protocol using installed CLI peers and public production APIs.

This harness reuses the actual HTTPS/restricted-role test setup and existing signed
observation exporter. It creates no alternate runtime, queue, budget or checker.
Private runtime homes are separate from the shareable results directory.
"""

import argparse
import asyncio
import hashlib
import importlib.metadata
import itertools
import json
import os
import platform
import random
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from sqlalchemy import text

from collective_intelligence_overlay.adapters.a2a import send
from collective_intelligence_overlay.bindings import Binding, fingerprint
from collective_intelligence_overlay.starter.adaptive_documents import (
    ENVIRONMENT,
    configure_application,
    write_json,
)
from collective_intelligence_overlay.starter.documents import APPLICATION_FACTORY

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests/e2e"), str(ROOT / "examples")]
SEEDS = (17, 29, 43, 71, 101)
CONDITIONS = ("normal", "verification_bottleneck", "connection_mismatch", "normal", "normal")


def digest_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def installed_wheel_provenance(candidate_directory, candidate):
    """Verify actual installed wheel files; Direct URL hashes are optional in PyPA."""
    distribution = importlib.metadata.distribution("collective-intelligence-overlay")
    direct_text = distribution.read_text("direct_url.json")
    direct = json.loads(direct_text) if direct_text else {}
    wheels = [name for name in candidate if name.endswith(".whl")]
    if len(wheels) != 1:
        raise ValueError("exactly one fixed candidate wheel is required")
    wheel = (candidate_directory / "dist" / wheels[0]).resolve()
    if direct.get("dir_info", {}).get("editable") or direct.get("url") != wheel.as_uri():
        raise ValueError("normal installed wheel origin differs from the fixed candidate")
    optional_hash = direct.get("archive_info", {}).get("hashes", {}).get("sha256")
    if optional_hash is not None and optional_hash != candidate[wheels[0]]:
        raise ValueError("installed origin hash differs from the fixed candidate")
    verified = 0
    prefix = Path(sys.prefix).resolve()
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.endswith("/") or name.endswith(".dist-info/RECORD"):
                continue
            installed = Path(distribution.locate_file(name)).resolve()
            if not installed.is_relative_to(prefix) or installed.read_bytes() != archive.read(name):
                raise ValueError("installed file bytes differ from the fixed candidate wheel")
            verified += 1
    return {
        "wheel": wheels[0],
        "sha256": candidate[wheels[0]],
        "verified_installed_files": verified,
        "excluded": (
            "installer-generated RECORD/bytecode/launcher metadata; no package code excluded"
        ),
    }


def cases(seed, split, count):
    """Disjoint deterministic public fixtures; never selected using an outcome."""
    rng = random.Random(f"production-040/{seed}/{split}")
    alphabet = ("文書", "alpha", "Δ", "データ", "résumé", "42")
    separators = (" ", "\t", "\n", "  ", "\u3000")
    return [
        {
            "id": f"{split}-{index}",
            "input": rng.choice(separators).join(
                [f"{split}_{seed}_{index}"]
                + [
                    rng.choice(alphabet)
                    for _ in range(rng.randint(0, 80 if split == "held-out" else 8))
                ]
            ),
        }
        for index in range(count)
    ]


def process_sample():
    """Actual Linux /proc RSS/CPU counters, including process start identity."""
    ticks, page = os.sysconf("SC_CLK_TCK"), os.sysconf("SC_PAGE_SIZE")
    result = {}
    vanished = 0
    for path in Path("/proc").iterdir():
        if not path.name.isdecimal():
            continue
        try:
            fields = (path / "stat").read_text().rsplit(") ", 1)[1].split()
            result[int(path.name)] = {
                "parent_pid": int(fields[1]),
                "start_ticks": int(fields[19]),
                "rss_bytes": int(fields[21]) * page,
                "user_seconds": int(fields[11]) / ticks,
                "system_seconds": int(fields[12]) / ticks,
                "reaped_children_user_seconds": int(fields[13]) / ticks,
                "reaped_children_system_seconds": int(fields[14]) / ticks,
            }
        except (OSError, ValueError, IndexError):
            vanished += 1
    return result, vanished


def subtree(snapshot, roots):
    included = set(roots) & snapshot.keys()
    for _ in range(len(snapshot)):
        children = {pid for pid, value in snapshot.items() if value["parent_pid"] in included}
        if children <= included:
            break
        included |= children
    return {str(pid): snapshot[pid] for pid in included}


def log_observations(mesh):
    """Keep each timing series separate: nested durations are never a total cost."""
    result = {}
    for owner, config in mesh.configs.items():
        by_reason = {}
        for path in (config.private_key.parent / "logs").glob("owner.jsonl*"):
            for line in path.read_text(encoding="utf-8").splitlines():
                item = json.loads(line)
                if "elapsed_seconds" in item:
                    by_reason.setdefault(item["reason"], []).append(item["elapsed_seconds"])
        result[owner] = {
            reason: {"count": len(values), "durations_seconds": values}
            for reason, values in by_reason.items()
        }
    return result


async def run_arm(private_home, results, admin_url, opa, caddy, seed, mode, condition, maximum):
    from evaluate_documents import export_owner
    from production_mesh import ProductionMesh, stop_process
    from validate_production_experiment import export_check_artifacts

    results.mkdir(mode=0o700, parents=True, exist_ok=False)
    started = time.monotonic()
    driver_cpu_start = os.times()
    formation = cases(seed, "formation", 6)
    held_out = cases(seed, "held-out", 24)
    training = "\n".join(item["input"] for item in formation)
    threshold = len(training.split())
    report = {
        "seed": seed,
        "mode": mode,
        "condition": condition,
        "status": "initializing",
        "initial_allowance": {name: "500" for name in ("producer", "verifier", "receiver")},
        "formation_cases": formation,
        "held_out": [
            {**item, "outcome": "unreached", "passed": False, "output": None, "check": None}
            for item in held_out
        ],
        "missing_resources": ["model_tokens", "currency"],
        "paid_inference": False,
        "allowance_is_measured_consumption": False,
        "time_to_first_checked_task_seconds": None,
        "calls": [],
    }
    mesh, configs, identities, processes, logs = None, {}, {}, {}, []
    snapshots = []
    owner_lifetimes = {}
    stage = "setup"
    sampler = None
    stop_sampling = asyncio.Event()
    pg_pid = None
    with (results / "calls.jsonl").open("x", encoding="utf-8") as call_log:

        async def call(owner, **data):
            if len(report["calls"]) >= 512:
                raise ValueError("predeclared external call bound exceeded")
            item = {
                "call_index": len(report["calls"]),
                "owner": owner,
                "operation": data["operation"],
                "invocation_id": data.get("invocation_id"),
                "attempt": data.get("attempt"),
                "offered_seconds": time.monotonic() - started,
                "status": "censored",
            }
            report["calls"].append(item)
            before = time.monotonic()
            try:
                value = await send(configs[owner], identities[owner], owner, data)
                item.update(status="returned", result=value)
                return value
            except Exception as error:
                item.update(status="failed", error_type=type(error).__name__)
                return {"error_type": type(error).__name__}
            finally:
                item["wall_seconds"] = time.monotonic() - before
                item["latency_censored"] = item["status"] == "censored"
                call_log.write(json.dumps(item, ensure_ascii=False) + "\n")
                call_log.flush()

        async def sync(owner, source):
            result = await call(owner, operation="sync", peer=source, page_size=32, max_pages=16)
            if not result.get("complete"):
                raise ValueError("initial source synchronization incomplete")

        async def sample():
            while True:
                snapshot, vanished = await asyncio.to_thread(process_sample)
                row = {
                    "seconds": time.monotonic() - started,
                    "vanished_or_unreadable_process_entries": vanished,
                    "owners": {
                        owner: subtree(snapshot, (process.pid,))
                        for owner, process in processes.items()
                    },
                    "proxy": subtree(snapshot, [process.pid for process in mesh.proxies]),
                    "mcp": subtree(snapshot, [process.pid for process in mesh.workers]),
                    "driver": snapshot.get(os.getpid()),
                    "postgresql_shared_cluster": subtree(snapshot, (pg_pid,)) if pg_pid else None,
                }
                snapshots.append(row)
                if stop_sampling.is_set():
                    break
                try:
                    await asyncio.wait_for(stop_sampling.wait(), 5)
                except TimeoutError:
                    continue

        async def start(owner):
            config = configs[owner]
            log = (config.private_key.parent / "experiment-process.log").open("ab")
            logs.append(log)
            processes[owner] = await asyncio.to_thread(
                subprocess.Popen,
                [
                    sys.executable,
                    "-m",
                    "collective_intelligence_overlay.cli",
                    "peer",
                    "--config",
                    str(config.private_key.parent / "config.json"),
                ],
                cwd=private_home,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            owner_lifetimes[owner] = {
                "started_seconds": time.monotonic() - started,
                "pid": processes[owner].pid,
            }
            async with asyncio.timeout(30):
                while True:
                    if processes[owner].poll() is not None:
                        raise RuntimeError("installed peer exited during startup")
                    status = await call(owner, operation="status")
                    if status.get("state") == "ready":
                        return
                    await asyncio.sleep(0.1)

        async def check(item, prefix):
            value = await call(
                "verifier",
                operation="app.verify",
                provider="receiver",
                name="triage",
                attempt=f"{prefix}-check-{item['id']}",
                arguments={"text": item["input"]},
                binding_digest=binding.digest,
            )
            item["check"] = value
            item["passed"] = (
                item["output"].get("state") == "completed"
                and item["output"].get("result")
                == {"long": len(item["input"].split()) > threshold, "threshold": threshold}
                and value.get("evidence", {}).get("verdict") == "PASS"
                and value["evidence"]["binding_digest"] == binding.digest
            )
            item["outcome"] = "PASS" if item["passed"] else "not_independently_passed"
            if item["passed"] and report["time_to_first_checked_task_seconds"] is None:
                report["time_to_first_checked_task_seconds"] = time.monotonic() - started

        try:
            # The profile's seconds allowance is a wall-time envelope, separate
            # from the existing work-credit ledger. Include setup/idle/all work
            # and reserve the declared 30 seconds for concurrent physical stop.
            async with asyncio.timeout(min(maximum, 500 - 30)):
                initializing = asyncio.create_task(
                    asyncio.to_thread(ProductionMesh, private_home, admin_url, opa, caddy, 500)
                )
                try:
                    mesh = await asyncio.shield(initializing)
                except asyncio.CancelledError:
                    mesh = await initializing
                    raise
                with mesh.admin.connect() as connection:
                    data_home = connection.execute(text("SHOW data_directory")).scalar_one()
                pg_pid = int((Path(data_home) / "postmaster.pid").read_text().splitlines()[0])
                for owner, original in mesh.configs.items():
                    config = original.model_copy(
                        update={
                            "execution_environment": ENVIRONMENT,
                            "max_seconds": 120,
                            "application": APPLICATION_FACTORY,
                            "application_settings": original.private_key.parent
                            / "application.json",
                        }
                    )
                    configs[owner] = config
                    data = config.model_dump(mode="json", exclude={"database_url"})
                    data["database_url_file"] = "secrets/database-url"
                    write_json(config.private_key.parent / "config.json", data)
                mesh.configs = configs
                await mesh.configure_mcp(configs["producer"])
                await asyncio.to_thread(
                    configure_application,
                    configs,
                    training,
                    connection_mismatch=condition == "connection_mismatch",
                )
                settings = configs["receiver"].application_settings
                data = json.loads(settings.read_text(encoding="utf-8"))
                data["allocation"] = {
                    "mode": "static" if mode == "strong_static_local" else "adaptive",
                    "minimum_samples": 1,
                    "verification_threshold": 1,
                    "connection_threshold": 1,
                }
                write_json(settings, data)
                for owner, config in configs.items():
                    identity, overlay = config.runtime()
                    identities[owner] = identity
                    overlay.store.close()
                await asyncio.to_thread(mesh.start_proxies)
                for owner in configs:
                    await start(owner)
                sampler = asyncio.create_task(sample())
                stage = "initial-checks"
                for provider, name, arguments in (
                    ("producer", "words", {"text": "initial primitive check"}),
                    ("receiver", "render", {"words": 7}),
                    ("receiver", "remote-words", {"text": "remote primitive check"}),
                ):
                    value = await call(
                        "verifier",
                        operation="app.verify",
                        attempt="initial-" + name,
                        provider=provider,
                        name=name,
                        arguments=arguments,
                    )
                    if value.get("evidence", {}).get("verdict") != "PASS":
                        raise ValueError("initial primitive check did not pass")
                    if name == "words":
                        await sync("producer", "verifier")
                        await sync("receiver", "producer")
                        await sync("receiver", "verifier")
                await sync("receiver", "verifier")
                for target in ("verifier", "receiver"):
                    value = await call("producer", operation="app.certify-checker", target=target)
                    if value.get("evidence", {}).get("verdict") != "PASS":
                        raise ValueError("initial checker calibration did not pass")
                    if target == "verifier":
                        await sync("verifier", "producer")
                        await sync("receiver", "verifier")
                    await sync("receiver", "producer")
                stage = "formation"
                report["run"] = await call("receiver", operation="run", max_steps=8)
                if report["run"].get("reason") != "goals_satisfied":
                    report["status"] = "censored_formation"
                else:
                    description = await call("receiver", operation="app.describe", name="triage")
                    binding = Binding.model_validate(description["binding"])
                    report["target"] = binding.model_dump(mode="json")
                    stage = "formation-cases"
                    for item in formation:
                        item["output"] = await call(
                            "receiver",
                            operation="invoke",
                            invocation_id=item["id"],
                            binding_id=binding.id,
                            binding_digest=binding.digest,
                            arguments={"text": item["input"]},
                        )
                        await check(item, "formation")
                    report["time_to_first_checked_task_seconds"] = None
                    stage = "held-out"
                    group = []
                    for item in report["held_out"]:
                        item["output"] = await call(
                            "receiver",
                            operation="invoke",
                            invocation_id=item["id"],
                            binding_id=binding.id,
                            binding_digest=binding.digest,
                            arguments={"text": item["input"]},
                        )
                        if condition == "verification_bottleneck":
                            group.append(item)
                            if len(group) == 8:
                                await asyncio.gather(*(check(value, "held-out") for value in group))
                                group.clear()
                        else:
                            await check(item, "held-out")
                    if group:
                        await asyncio.gather(*(check(value, "held-out") for value in group))
                    report["status"] = "executed"
                report["operational_end"] = {
                    owner: await call(owner, operation="operational_metrics") for owner in configs
                }
        except Exception as error:
            report.update(status="failed", failed_stage=stage, error_type=type(error).__name__)
        finally:
            report["elapsed_before_export_seconds"] = time.monotonic() - started
            driver_cpu_end = os.times()
            report["driver_cpu_seconds"] = {
                "user": driver_cpu_end.user - driver_cpu_start.user,
                "system": driver_cpu_end.system - driver_cpu_start.system,
                "basis": "harness only; excludes peer/child CPU; not wall time or allowance",
            }
            stop_sampling.set()
            if sampler is not None:
                await sampler

            async def stop_owner(owner, process):
                await asyncio.to_thread(stop_process, process)
                owner_lifetimes[owner].update(
                    stopped_seconds=time.monotonic() - started,
                    physical_stop_confirmed=process.poll() is not None,
                )

            await asyncio.gather(*(stop_owner(owner, p) for owner, p in processes.items()))
            report["owner_time_allowance"] = {
                "unit": "wall_seconds",
                "quantity": 500,
                "basis": "common arm deadline begins before setup; includes owner idle and work",
                "work_deadline_seconds": min(maximum, 500 - 30),
                "physical_shutdown_reserve_seconds": 30,
                "owners": owner_lifetimes,
            }
            for log in logs:
                log.close()
            report["owners"] = {}
            for owner, config in configs.items():
                try:
                    report["owners"][owner] = await asyncio.to_thread(
                        export_owner, config, results / f"{owner}-observations.json"
                    )
                except Exception as error:
                    report["owners"][owner] = {"error_type": type(error).__name__}
                    report["status"] = "incomplete_export"
            if "verifier" in configs:
                write_json(
                    results / "check-artifacts.json",
                    export_check_artifacts(
                        configs["verifier"].artifacts(), formation + report["held_out"]
                    ),
                )
            if mesh is not None:
                report["monitoring_durations"] = log_observations(mesh)
                with mesh.admin.connect() as connection:
                    report["postgresql_version"] = connection.execute(
                        text("SELECT version()")
                    ).scalar_one()
                await asyncio.to_thread(mesh.close)
            report["passed_business_tasks"] = sum(item["passed"] for item in report["held_out"])
            report["denominator"] = 24
            report["elapsed_including_export_seconds"] = time.monotonic() - started
            write_json(results / "process-samples.json", snapshots)
            write_json(results / "result.json", report)
    return report


async def main(args):
    if platform.system() != "Linux":
        raise ValueError("this external /proc measurement runner requires actual native Linux")
    output_path = await asyncio.to_thread(args.output.resolve)
    private_path = await asyncio.to_thread(args.private.resolve)
    if output_path.is_relative_to(private_path) or private_path.is_relative_to(output_path):
        raise ValueError("private runtime homes and export directories must be disjoint")
    profile_path = ROOT / "docs/profiles/production-040.json"
    profile = json.loads(profile_path.read_text())
    specification = profile["matched_experiment"]
    assert specification["seeds"] == list(SEEDS)
    assert specification["formation_cases_per_arm"] == 6
    assert specification["held_out_cases_per_arm"] == 24
    assert specification["allowance_per_owner_seconds"] == 500
    if args.development_seed is not None and args.development_seed in SEEDS:
        raise ValueError("development fixtures must use a seed separate from formal inputs")
    if args.development_seed is None and args.development_condition is not None:
        raise ValueError("formal condition assignment cannot be overridden")
    candidate = None
    provenance = None
    if args.candidate is not None:
        candidate = json.loads((args.candidate / "artifacts.json").read_text())
        actual = {
            path.name: digest_file(path)
            for path in (args.candidate / "dist").iterdir()
            if path.name.endswith((".whl", ".tar.gz"))
        }
        if candidate != actual:
            raise ValueError("candidate files differ from their fixed manifest")
    if args.development_seed is None:
        if candidate is None:
            raise ValueError("formal experiment requires the fixed candidate pair")
        distribution = importlib.metadata.distribution("collective-intelligence-overlay")
        if distribution.version != profile["target_version"]:
            raise ValueError("installed version differs from the predeclared target")
        provenance = await asyncio.to_thread(installed_wheel_provenance, args.candidate, candidate)
        installed = await asyncio.to_thread(
            Path(distribution.locate_file("collective_intelligence_overlay")).resolve
        )
        prefix = await asyncio.to_thread(Path(sys.prefix).resolve)
        if not installed.is_relative_to(prefix):
            raise ValueError("formal package import is outside the selected environment")
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    args.private.mkdir(mode=0o700, parents=True, exist_ok=False)
    seeds = (args.development_seed,) if args.development_seed is not None else SEEDS
    protocol = {
        "profile_id": profile["profile_id"],
        "profile_sha256": fingerprint(profile),
        "artifacts": candidate,
        "installed_wheel_provenance": provenance,
        "protocol": "production-documents-matched-040-v1",
        "development_only": args.development_seed is not None,
        "seeds": list(seeds),
        "conditions_by_seed": {
            str(seed): condition for seed, condition in zip(SEEDS, CONDITIONS, strict=True)
        },
        "condition_assignment_basis": "fixed before any run; pair is the independent unit",
        "formation_cases": 6,
        "held_out_cases": 24,
        "training": "all six formation inputs concatenate to one operator calibration document",
        "held_out": "disjoint deterministic identifiers/generator; no retuning",
        "verification_bottleneck": (
            "batch eight independent checks after sequential uses; unchanged caller/owner/"
            "execution limits; no failed-check retry"
        ),
        "connection_mismatch": (
            "same initially installed v1 candidate and requested v2 adapter in both arms"
        ),
        "static_policy": (
            "existing fixed report/check/triage/check policy; "
            "ordinary admission and own durable cache"
        ),
        "maximum_arm_seconds": specification["maximum_elapsed_seconds_per_arm"],
        "owner_time_allowance": {
            "unit": "wall_seconds",
            "quantity": specification["allowance_per_owner_seconds"],
            "basis": "common monotonic arm deadline including setup; 30 seconds reserved for stop",
            "work_credits_are_separate": True,
        },
        "cost_basis": (
            "original signed events plus separate OS process and monotonic call/log observations; "
            "no sum of nested durations or allowance as consumption"
        ),
        "rss_basis": (
            "Linux /proc resident set of each owner and living descendants "
            "at five-second intervals; short-lived child peaks may be missed"
        ),
        "cpu_basis": (
            "OS process and reaped child counters; overlapping live/reaped observations not added; "
            "missing tokens/currency stay unavailable"
        ),
        "postgresql_basis": (
            "shared private test cluster and descendants sampled separately; "
            "background/shared work is not attributed as exact per-arm CPU consumption"
        ),
        "exclusions": "none; all 24 held-out tasks including absent/failed/UNKNOWN/censored remain",
        "versions": {
            name: importlib.metadata.version(name)
            for name in (
                "collective-intelligence-overlay",
                "agent-framework-core",
                "a2a-sdk",
                "mcp",
                "sqlalchemy",
            )
        },
        "runtime": {
            "python": sys.version,
            "executable": sys.executable,
            "platform": platform.platform(),
            "logical_cpus": os.cpu_count(),
        },
        "source_commit": (
            await asyncio.to_thread(
                subprocess.check_output, ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            )
        ).strip(),
        "runner_sha256": digest_file(Path(__file__)),
        "validator_sha256": digest_file(
            Path(__file__).with_name("validate_production_experiment.py")
        ),
        "opa_sha256": digest_file(args.opa),
        "proxy_sha256": digest_file(args.caddy),
        "development_condition": args.development_condition,
        "contention_notes": args.contention_notes,
        "paid_inference": False,
    }
    sources = {
        path.name: path.read_bytes()
        for path in (
            Path(__file__),
            Path(__file__).with_name("validate_production_experiment.py"),
            ROOT / "tests/e2e/production_mesh.py",
            ROOT / "examples/evaluate_documents.py",
        )
    }
    protocol["sources"] = {
        name: hashlib.sha256(content).hexdigest() for name, content in sources.items()
    }
    (args.output / "sources").mkdir(mode=0o700)
    for name, content in sources.items():
        (args.output / "sources" / name).write_bytes(content)
    write_json(args.output / "protocol.json", protocol)
    if fingerprint(json.loads((args.output / "protocol.json").read_text())) != fingerprint(
        protocol
    ):
        raise ValueError("protocol JSON round trip changed its digest before execution")
    completed = []
    for pair, seed in enumerate(seeds):
        condition = CONDITIONS[SEEDS.index(seed)] if seed in SEEDS else "normal"
        if args.development_condition is not None:
            condition = args.development_condition
        modes = ("strong_static_local", "observation_adaptive")
        if pair % 2:
            modes = tuple(reversed(modes))
        for mode in modes:
            label = f"pair-{pair}-{seed}-{mode}"
            print(json.dumps({"stage": "arm-start", "arm": label}), flush=True)
            result = await run_arm(
                args.private / label,
                args.output / label,
                args.database_url,
                str(args.opa.resolve()),
                str(args.caddy.resolve()),
                seed,
                mode,
                condition,
                specification["maximum_elapsed_seconds_per_arm"],
            )
            completed.append(
                {
                    "directory": label,
                    "seed": seed,
                    "mode": mode,
                    "status": result["status"],
                    "passed": result["passed_business_tasks"],
                    "denominator": result["denominator"],
                }
            )
            write_json(args.output / "results.json", {"arms": completed, "complete": False})
            print(json.dumps({"stage": "arm-finished", **completed[-1]}), flush=True)
    differences = []
    for seed in seeds:
        paired = {
            row["mode"]: row["passed"] / row["denominator"]
            for row in completed
            if row["seed"] == seed
        }
        differences.append(paired["observation_adaptive"] - paired["strong_static_local"])
    write_json(
        args.output / "results.json",
        {
            "arms": completed,
            "complete": True,
            "independent_pairs": len(seeds),
            "paired_fraction_differences": differences,
            "descriptive_mean_difference": sum(differences) / len(differences),
            "descriptive_observed_range": [min(differences), max(differences)],
            "task_level_independence_assumed": False,
            "general_adaptive_benefit_claimed": False,
            "development_only": args.development_seed is not None,
            "protocol_sha256": fingerprint(protocol),
            "paired_bootstrap_mean_interval": paired_interval(differences),
        },
    )
    from validate_production_experiment import validate

    write_json(args.output / "validation.json", validate(args.output))


def paired_interval(differences):
    """Exact empirical resampling of pairs; no task-level independence claim."""
    if len(differences) < 2:
        return None
    means = sorted(
        sum(values) / len(values)
        for values in itertools.product(differences, repeat=len(differences))
    )
    return {
        "basis": "descriptive 2.5/97.5 empirical paired-bootstrap percentiles; small-sample limits",
        "independent_units": len(differences),
        "interval": [means[int(len(means) * 0.025)], means[int(len(means) * 0.975)]],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("CIO_TEST_DATABASE_URL"))
    parser.add_argument("--opa", type=Path, required=True)
    parser.add_argument("--caddy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--development-seed", type=int)
    parser.add_argument("--development-condition", choices=sorted(set(CONDITIONS)))
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--contention-notes", default="not isolated; external activity unmeasured")
    arguments = parser.parse_args()
    if not arguments.database_url:
        parser.error("explicit operator database URL or CIO_TEST_DATABASE_URL required")
    asyncio.run(main(arguments))
