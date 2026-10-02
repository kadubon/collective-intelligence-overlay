"""Finite real-Gemma paired harness over the existing three-owner production mesh.

Only a dedicated cloud-disabled local server is permitted. No pull/fallback or
outcome-driven rerun. First use is a task smoke, then a distinct exploratory pilot;
confirmation additionally requires a committed preregistration (added after pilot).
"""

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import platform
import random
import subprocess
import sys
import time
import traceback
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from ollama_observer import write_new
from production_session import ProductionSession
from tabular_evaluation import Evaluator, family

from collective_intelligence_overlay.application import ApplicationHost
from collective_intelligence_overlay.bindings import Binding, Target
from collective_intelligence_overlay.models import Evidence, UseRequest, Verdict, now
from collective_intelligence_overlay.proposal_exchange import ProposalContract
from collective_intelligence_overlay.starter.adaptive_documents import write_json
from collective_intelligence_overlay.starter.tabular import (
    ENVIRONMENT,
    FACTORY,
    NAMES,
    TabularApplication,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests/e2e"), str(ROOT / "examples")]
from production_mesh import ProductionMesh  # noqa: E402

MODEL = "gemma4:e4b"
DIGEST = "dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c"


def source_hashes():
    names = [
        "scripts/run_gemma_tabular.py",
        "scripts/ollama_observer.py",
        "scripts/tabular_evaluation.py",
        "scripts/production_session.py",
        "scripts/analyze_gemma_tabular.py",
        "tests/e2e/production_mesh.py",
        "pyproject.toml",
        "uv.lock",
    ]
    names.extend(str(p.relative_to(ROOT)).replace("\\", "/") for p in (ROOT / "src").rglob("*.py"))
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sorted(names)}


def confirm_registration(args, sources):
    if args.classification != "confirmation":
        return None
    if args.preregistration is None or args.prereg_commit is None or args.candidate_wheel is None:
        raise ValueError("confirmation requires committed preregistration and immutable wheel")
    path = args.preregistration.resolve()
    relative = path.relative_to(ROOT).as_posix()
    committed = subprocess.check_output(
        ["git", "show", args.prereg_commit + ":" + relative], cwd=ROOT
    )
    if committed != path.read_bytes():
        raise ValueError("preregistration is not the committed original")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", args.prereg_commit, "HEAD"], cwd=ROOT, check=True
    )
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", args.prereg_commit, "origin/main"],
        cwd=ROOT,
        check=True,
    )
    registration = json.loads(committed)
    if (
        registration["pairs"] != args.pairs
        or registration["sources"] != sources
        or registration["model_digest"] != DIGEST
    ):
        raise ValueError("frozen preregistered protocol/source mismatch")
    if datetime.fromisoformat(registration["registered_at"]) >= datetime.now(UTC):
        raise ValueError("preregistration timestamp must precede inference")
    wheel = args.candidate_wheel.resolve()
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != registration["wheel_sha256"]:
        raise ValueError("immutable wheel hash mismatch")
    package = importlib.metadata.distribution("collective-intelligence-overlay")
    if package.version != "0.4.1":
        raise ValueError("confirmation requires actual installed 0.4.1")
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.startswith("collective_intelligence_overlay/") and not name.endswith("/"):
                installed = Path(package.locate_file(name)).resolve()
                if not installed.is_relative_to(
                    Path(sys.prefix).resolve()
                ) or installed.read_bytes() != archive.read(name):
                    raise ValueError("inference import is not the immutable installed wheel")
    return {
        "commit": args.prereg_commit,
        "path": relative,
        "sha256": hashlib.sha256(committed).hexdigest(),
        "wheel_sha256": registration["wheel_sha256"],
        "status": "exploratory_limited_power",
    }


async def configure(session, shared, evaluation, args, identity, sources):
    session.mesh = await asyncio.to_thread(
        ProductionMesh, session.home, session.database, str(args.opa), str(args.caddy), 500
    )
    session.configs = {
        owner: original.model_copy(
            update={
                "application": FACTORY,
                "application_settings": original.private_key.parent / "application.json",
                "execution_environment": ENVIRONMENT,
                "max_seconds": 300,
                "max_concurrency": 4,
                "max_steps": 12,
                "max_children": 8,
            }
        )
        for owner, original in session.mesh.configs.items()
    }
    session.mesh.configs = session.configs
    for config in session.configs.values():
        data = config.model_dump(mode="json", exclude={"database_url"})
        data["database_url_file"] = "secrets/database-url"
        write_json(config.private_key.parent / "config.json", data)
    verifier = session.configs["verifier"]
    write_json(
        verifier.application_settings,
        {
            **shared,
            "evaluation": evaluation,
            "evaluator": str(ROOT / "scripts/tabular_evaluation.py"),
        },
    )
    previews = []
    try:
        verifier_host = ApplicationHost(verifier)
        previews.append(verifier_host)
        verifier_app = TabularApplication(verifier_host)
        original = verifier_app.checker
        proxy = original.model_copy(
            update={
                "issuer": "receiver",
                "registrar": "receiver",
                "target": Target(
                    kind="a2a",
                    name="checker",
                    peer="verifier",
                    endpoint=verifier.url,
                    interface_digest=original.digest,
                    implementation_identity="remote-unknown",
                ),
            }
        )
        receiver = session.configs["receiver"]
        receiver.artifacts().put(verifier.artifacts().get(original.subject.digest))
        write_json(
            receiver.application_settings, {**shared, "checker": proxy.model_dump(mode="json")}
        )
        receiver_host = ApplicationHost(receiver)
        previews.append(receiver_host)
        TabularApplication(receiver_host)
        goals = tuple(receiver_host.opportunities.goal(name) for name in NAMES)
        model_output = session.output / "model"
        model_output.mkdir()
        producer = session.configs["producer"]
        write_json(
            producer.application_settings,
            {
                **shared,
                "contracts": [ProposalContract.from_goal(g).model_dump(mode="json") for g in goals],
                "model": {
                    "host": args.host,
                    "output": str(model_output),
                    "seed": identity["seed"],
                    "identity": {k: str(v) for k, v in identity.items() if k != "seed"},
                    "token_budget": 18432,
                    "max_requests": 4,
                    "provenance": {"model_name": MODEL, "model_digest": DIGEST, "sources": sources},
                },
            },
        )
    finally:
        for host in previews:
            host.close()
    for owner, config in session.configs.items():
        peer_identity, overlay = config.runtime()
        session.identities[owner] = peer_identity
        overlay.store.close()
    await asyncio.to_thread(session.mesh.start_proxies)
    for owner in session.configs:
        await session.start(owner)
    # Actual external comparison calibration, no model/hidden evaluator inputs.
    calibration = await session.call(
        "producer", destination="verifier", operation="app.calibration"
    )
    write_new(session.output / "checker-calibration.json", calibration)
    if calibration != {"positive": True, "negative": False}:
        raise ValueError("independent comparator calibration failed")
    # Independent verifier runs the safe parameter validators on public fixtures.
    # Their claim is parameter-validation, never task quality of an LLM proposal.
    plans = {
        "numeric": {
            k: evaluation["truth"][k]
            for k in ("decimal_separator", "thousands_separator", "affix", "divisor")
        },
        "status": {k: evaluation["truth"][k] for k in ("trim", "casefold", "accepted")},
        "aggregate": {k: evaluation["truth"][k] for k in ("operation", "group_casefold")},
    }
    for name in NAMES:
        description = await session.call("receiver", operation="app.describe", name="build-" + name)
        binding = Binding.model_validate(description["binding"])
        observed = await session.call(
            "verifier",
            destination="receiver",
            **{
                "operation": "invoke",
                "purpose": "verification",
                "invocation_id": "initial-" + name,
                "binding_id": binding.id,
                "binding_digest": binding.digest,
                "arguments": {"plan": plans[name]},
            },
        )
        passed = (
            observed.get("state") == "completed"
            and observed.get("result", {}).get("plan") == plans[name]
        )
        write_new(
            session.output / ("validator-calibration-" + name + ".json"),
            {"observed": observed, "passed": passed},
        )
        if not passed:
            raise ValueError("public parameter validator calibration failed")
        sign_evidence(session, "verifier", binding, "parameter-validation", {"observed": observed})
    # Installed checker is certified by another identity for its positive and
    # negative exact-comparison behavior. Broader external validity is not claimed.
    sign_evidence(session, "producer", original, "checker-contract", calibration)
    sign_evidence(session, "producer", proxy, "checker-contract", calibration)
    for owner, source in (
        ("verifier", "producer"),
        ("receiver", "producer"),
        ("receiver", "verifier"),
    ):
        if not (await session.sync(owner, source)).get("complete"):
            raise ValueError("initial source sync incomplete")
    for owner, binding in (("verifier", original), ("receiver", proxy)):
        decision = await session.call(
            owner,
            operation="qualify",
            request=UseRequest(
                receiver=owner,
                capability_issuer=binding.issuer,
                subject=binding.subject,
                binding_digest=binding.digest,
                scope=binding.scope,
                semantic_fit="confirmed",
            ).model_dump(mode="json"),
        )
        if decision.get("decision", {}).get("outcome") != "ACCEPT":
            raise ValueError("initial checker ordinary admission not ready")


def sign_evidence(session, signer, binding, claim, observation):
    config = session.configs[signer]
    identity, overlay = config.runtime()
    try:
        artifact = config.artifacts().put(json.dumps(observation, sort_keys=True).encode())
        evidence = Evidence(
            schema_version="2",
            id="initial-" + binding.digest,
            issuer=signer,
            subject=binding.subject,
            binding_digest=binding.digest,
            scope=binding.scope,
            claim=claim,
            receivers=(binding.issuer,),
            verdict=Verdict.PASS,
            method="reference-check",
            verifier_version="public-validator-calibration.v1",
            artifact_digest=artifact,
            expires_at=now() + timedelta(hours=1),
        )
        overlay.store.put(identity.sign(evidence))
    finally:
        overlay.store.close()


async def episode(args, output, home, block, arm, evaluation, public, practice, followup, sources):
    output.mkdir()
    session = ProductionSession(
        home,
        output,
        os.environ["CIO_TEST_DATABASE_URL"],
        str(args.opa),
        str(args.caddy),
        500,
        "unused",
    )
    session.phase = "setup"
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    failure, result, evaluations = None, None, {}
    inference_seed = {"task-smoke": 41000, "pilot": 51000, "confirmation": 61000}[
        args.classification
    ]
    identity = {
        "run": args.run_id,
        "episode": str(block),
        "arm": arm,
        "seed": inference_seed + block * 11,
    }
    try:
        async with asyncio.timeout(600):
            await configure(
                session,
                {
                    "mode": arm,
                    "public_contract": public,
                    "practice": practice,
                    "followup_practice": followup,
                },
                evaluation,
                args,
                identity,
                sources,
            )
            setup_seconds = time.perf_counter() - started
            await session.sample()
            session.phase = "formation"
            result = await session.call(
                "receiver", operation="run", max_steps=12, max_candidates=3, seconds=300
            )
            session.phase = "heldout"
            for name in NAMES:
                evaluations[name] = await session.call(
                    "verifier", operation="app.evaluate", name=name
                )
            await session.sample()
    except Exception as error:
        failure = type(error).__name__
        private_failure = output / "private-metadata"
        private_failure.mkdir(exist_ok=True)
        (private_failure / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        if hasattr(error, "errors"):
            write_new(output / "validation-errors.json", error.errors(include_input=False))
    finally:
        active_seconds = time.perf_counter() - started
        try:
            exported = await session.finish()
        except Exception as error:
            exported = {"export_error": type(error).__name__}
            if session.mesh:
                await asyncio.to_thread(session.mesh.close)
        attempts = sorted((output / "model").glob("attempt-*/observation.json"))
        observations = [json.loads(p.read_bytes()) for p in attempts]
        trials = [t for value in evaluations.values() for t in value.get("trials", [])]
        succeeded_at = [
            datetime.fromisoformat(t["observed"]["updated_at"])
            for t in trials
            if t["passed"] and t["observed"].get("updated_at")
        ]
        value = {
            "identity": identity,
            "real_model": True,
            "inference_performed": any(o["transport_dispatch_started"] for o in observations),
            "failure": failure,
            "started_at": started_at.isoformat(),
            "completed": failure is None and len(trials) == 6,
            "formation_error": result.get("error_type") if result else None,
            "formation_result": result,
            "evaluations": evaluations,
            "offered_tasks": 6,
            "observed_tasks": len(trials),
            "passed_tasks": sum(t["passed"] for t in trials),
            "primary_fraction": sum(t["passed"] for t in trials) / 6,
            "first_valid_heldout_seconds": (min(succeeded_at) - started_at).total_seconds()
            if succeeded_at
            else None,
            "false_accepts": sum(
                t["observed"].get("state") == "completed" and not t["passed"] for t in trials
            ),
            "unknown_tasks": sum(t["observed"].get("state") != "completed" for t in trials),
            "wall_per_success": active_seconds / sum(t["passed"] for t in trials)
            if any(t["passed"] for t in trials)
            else None,
            "attempts": len(observations),
            "token_budget_charge": sum(o["budget_charge"] for o in observations),
            "prompt_tokens": sum(o["usage_native"]["prompt_eval_count"] or 0 for o in observations),
            "generated_tokens": sum(o["usage_native"]["eval_count"] or 0 for o in observations),
            "missing_usage_attempts": sum(o["tokens_measured"] is None for o in observations),
            "inclusive_active_wall_seconds": active_seconds,
            "inclusive_with_cleanup_seconds": time.perf_counter() - started,
            "setup_seconds": locals().get("setup_seconds"),
            "all_calls": len(session.calls),
            "exports": exported,
            "energy": "unavailable",
            "api_fee_jpy": 0,
        }
        write_new(output / "result.json", value)
        print(
            json.dumps(
                {
                    "block": block,
                    "arm": arm,
                    "passed": value["passed_tasks"],
                    "attempts": len(observations),
                    "failure": failure,
                    "seconds": active_seconds,
                }
            ),
            flush=True,
        )
    return value


async def run(args):
    if not 1 <= args.pairs <= (30 if args.classification == "confirmation" else 5):
        raise ValueError("predeclared finite paired episode limit exceeded")
    args.opa, args.caddy = args.opa.resolve(), args.caddy.resolve()
    output, home = args.output.resolve(), args.home.resolve()
    output.mkdir(parents=True, exist_ok=False)
    args.created_output = True
    write_new(
        output / "launch-intent.json",
        {
            "id": args.run_id,
            "classification": args.classification,
            "pairs": args.pairs,
            "started_at": datetime.now(UTC).isoformat(),
            "real_model_required": True,
            "sources": source_hashes(),
        },
    )
    home.mkdir(parents=True, exist_ok=False)
    if 'msg="Ollama cloud disabled: true"' not in args.server_log.read_text(encoding="utf-8"):
        raise ValueError("dedicated cloud-disabled server evidence required")
    sources = source_hashes()
    preregistration = confirm_registration(args, sources)
    snapshot = output / "source-snapshot"
    for name in sources:
        path = snapshot / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / name).read_bytes())
    source_commit = await asyncio.to_thread(
        subprocess.check_output, ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    )
    dirty_diff = await asyncio.to_thread(
        subprocess.check_output, ["git", "diff", "--binary"], cwd=ROOT
    )
    order = ["static", "adaptive"] * ((args.pairs + 1) // 2)
    order_seed = {"task-smoke": 41021, "pilot": 51021, "confirmation": 61021}[args.classification]
    random.Random(order_seed).shuffle(order)
    order = order[: args.pairs]
    protocol = {
        "id": args.run_id,
        "classification": args.classification,
        "real_model": True,
        "pairs": args.pairs,
        "arms": ["static", "adaptive"],
        "first_arms": order,
        "order_seed": order_seed,
        "source_commit": source_commit.strip(),
        "dirty_diff_sha256": hashlib.sha256(dirty_diff).hexdigest(),
        "sources": sources,
        "preregistration": preregistration,
        "model_name": MODEL,
        "model_digest": DIGEST,
        "aggregate_episode_tokens_upper": 18432,
        "episode_wall_seconds": 600,
        "per_request_seconds": 25,
        "native_context": 4096,
        "max_generated_tokens": 512,
        "max_inference_requests_per_arm": 4,
        "treatment": {
            "static": "fixed three-goal plan; observe only current goal; static allocation",
            "adaptive": "bounded three-goal shortage discovery and adaptive allocation",
        },
        "automatic_model_retries": 0,
        "primary": "six heldout tasks passed divided by six per arm; paired episode difference",
        "warmup": "none; setup/loading included; keep_alive5m both arms; balanced order",
        "shared_server_parallelism": 1,
        "cache_reset": "unavailable; no global unload",
        "mcid": 0.10,
        "analysis_unit": "paired episode; task responses are correlated subsamples",
        "checker_calibration_scope": "parameter validation and output comparison; finite scope",
        "failure_policy": "all offered tasks remain denominator; no outcome-driven repeat",
        "model_file_tools": [],
        "evaluator_inputs_in_model_messages": False,
    }
    write_new(output / "protocol.json", protocol)
    write_new(
        output / "runtime.json",
        {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "installed_distribution": importlib.metadata.version("collective-intelligence-overlay"),
            "resolved_dependencies": sorted(
                (
                    {"name": d.metadata["Name"], "version": d.version}
                    for d in importlib.metadata.distributions()
                ),
                key=lambda d: d["name"].lower(),
            ),
            "versions": {
                n: importlib.metadata.version(n)
                for n in (
                    "agent-framework-core",
                    "agent-framework-ollama",
                    "ollama",
                    "a2a-sdk",
                    "mcp",
                )
            },
        },
    )
    private = output / "private-metadata"
    private.mkdir()
    async with httpx.AsyncClient(base_url=args.host, timeout=10, trust_env=False) as http:
        for name in ("version", "tags", "show", "ps"):
            response = (
                await http.post("/api/show", json={"model": MODEL})
                if name == "show"
                else await http.get("/api/" + name)
            )
            response.raise_for_status()
            (private / ("before-" + name + ".raw")).write_bytes(response.content)
        tags = json.loads((private / "before-tags.raw").read_bytes())
        if next(m for m in tags["models"] if m["name"] == MODEL)["digest"] != DIGEST:
            raise ValueError("model digest mismatch")
        show = json.loads((private / "before-show.raw").read_bytes())
        if show.get("remote_host") or show.get("remote_model"):
            raise ValueError("cloud model forbidden")
    all_results = []
    started = time.perf_counter()
    async with asyncio.timeout(args.pairs * 1200 + 60):
        for block in range(args.pairs):
            truth, public = family(block)
            seed_base = {"task-smoke": 71000, "pilot": 86000, "confirmation": 310000}[
                args.classification
            ]
            evaluation = {
                "truth": truth,
                "seeds": {
                    "validation": seed_base + block * 17,
                    "heldout": seed_base + block * 17 + 1,
                },
                "checker_digest": sources["scripts/tabular_evaluation.py"],
            }
            practice_offset = {"task-smoke": 0, "pilot": 5000, "confirmation": 10000}[
                args.classification
            ]
            training = Evaluator(
                {
                    "truth": truth,
                    "seeds": {
                        "practice": practice_offset + 101 + block,
                        "followup": practice_offset + 201 + block,
                    },
                }
            )
            practice = training.cases("practice", "numeric")[0]["rows"]
            followup = training.cases("followup", "numeric")[0]["rows"]
            # Private until the completed run; never copied into proposer settings.
            write_new(private / f"evaluation-block-{block:03}.json", evaluation)
            for arm in (order[block], "adaptive" if order[block] == "static" else "static"):
                value = await episode(
                    args,
                    output / f"block-{block:03}-{arm}",
                    home / f"block-{block:03}-{arm}",
                    block,
                    arm,
                    evaluation,
                    public,
                    practice,
                    followup,
                    sources,
                )
                all_results.append(value)
            async with httpx.AsyncClient(base_url=args.host, timeout=5, trust_env=False) as http:
                response = await http.get("/api/ps")
                (private / f"resident-block-{block:03}.raw").write_bytes(response.content)
    write_new(
        output / "result.json",
        {
            "id": args.run_id,
            "classification": args.classification,
            "offered_paired_episodes": args.pairs,
            "observed_arm_episodes": len(all_results),
            "elapsed_seconds": time.perf_counter() - started,
            "episodes": all_results,
            "status": "executed" if len(all_results) == 2 * args.pairs else "incomplete",
        },
    )
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "home", "opa", "caddy", "server-log"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--pairs", type=int, required=True)
    parser.add_argument(
        "--classification", choices=("task-smoke", "pilot", "confirmation"), required=True
    )
    parser.add_argument("--preregistration", type=Path)
    parser.add_argument("--prereg-commit")
    parser.add_argument("--candidate-wheel", type=Path)
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args))
    except BaseException as error:
        if getattr(args, "created_output", False):
            write_new(
                args.output / "termination.json",
                {
                    "completed": False,
                    "classification": "retained_global_or_startup_failure",
                    "error_type": type(error).__name__,
                    "at": datetime.now(UTC).isoformat(),
                    "inference_observation_files": len(
                        list(args.output.glob("block-*/model/attempt-*/observation.json"))
                    ),
                },
            )
        raise
    raise SystemExit(result)


if __name__ == "__main__":
    main()
