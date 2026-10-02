"""Offline verification/analysis of retained tabular raw data; never calls a model.

Incomplete data yield UNKNOWN. Episode fractions are recomputed from independent
reference cases and original signed execution receipts, not summary pass flags.
"""

import argparse
import base64
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from ollama_observer import write_new
from securesystemslib.exceptions import FormatError, VerificationError
from securesystemslib.signer import Key
from tabular_evaluation import Evaluator

from collective_intelligence_overlay.bindings import fingerprint
from collective_intelligence_overlay.security import Principal, verify
from collective_intelligence_overlay.starter.tabular import PLANS

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    if path.is_symlink() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("unsafe or oversized report file")
    return json.loads(path.read_bytes())


def signed_records(directory):
    events, proposals, states, artifacts = {}, {}, {}, {}
    for owner in ("producer", "verifier", "receiver"):
        exported = read(directory / (owner + "-observations.json"))
        principals = {
            name: Principal(
                Key.from_dict(value["keyid"], dict(value["key"])),
                value["trust_group"],
                frozenset(value["methods"]),
            )
            for name, value in exported["public_identities"].items()
        }
        for envelope in exported["signed_records"]:
            record = verify(envelope, principals)
            if record.kind == "event":
                events[record.issuer, record.id] = record
            elif record.kind == "proposal":
                proposals[record.issuer, record.id] = record
        for invocation in exported["invocations"]:
            states[owner, invocation["caller"], invocation["id"]] = invocation
        cas = read(directory / (owner + "-artifacts.json"))
        for digest, encoded in cas["original_bytes_base64"].items():
            raw = base64.b64decode(encoded, validate=True)
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError("original CAS digest mismatch")
            artifacts[owner, digest] = raw
    return events, proposals, states, artifacts


def verify_attempt(directory, protocol, expected_identity):
    intent, observation, host = (
        read(directory / name)
        for name in ("intent.json", "observation.json", "host-validation.json")
    )
    if (
        intent["real_model"] is not True
        or intent["provenance"]["model_digest"] != protocol["model_digest"]
    ):
        raise ValueError("mixed mock/model or unpinned attempt")
    for field, value in expected_identity.items():
        if intent["identity"][field] != str(value):
            raise ValueError("attempt identity mismatch")
    if observation["transport_dispatch_started"] is False:
        raw = (directory / "response.raw").read_bytes()
        if (
            raw
            or observation["budget_charge"] != 0
            or observation["budget_charge_status"] != "not_sent_proven"
            or observation["tokens_measured"] is not None
            or observation["status"] is not None
            or host["parsed_plan"] is not None
            or observation["raw_sha256"] != hashlib.sha256(raw).hexdigest()
        ):
            raise ValueError("inconsistent proven pre-send failure")
        return {
            "goal": host["goal"],
            "plan": None,
            "opportunity": host["opportunity"],
            "charge": 0,
            "prompt": 0,
            "generated": 0,
            "missing": False,
            "dispatched": False,
        }
    request = read(directory / "request.json")
    actual_request = (directory / "request.raw").read_bytes()
    if (
        hashlib.sha256(actual_request).hexdigest() != request["payload_digest"]
        or json.loads(actual_request) != request["payload"]
    ):
        raise ValueError("actual request bytes mismatch")
    payload = request["payload"]
    if request["path"] != "/api/chat" or payload["model"] != protocol["model_name"]:
        raise ValueError("inference surface/model mismatch")
    if intent["settings_digest"] != fingerprint(intent["requested"]):
        raise ValueError("intent options digest mismatch")
    for key, value in intent["requested"]["native_options"].items():
        if payload["options"].get(key) != value:
            raise ValueError("actual native options differ from intent")
    if payload.get("think") is not False:
        raise ValueError("unexpected thinking policy")
    raw = (directory / "response.raw").read_bytes()
    if hashlib.sha256(raw).hexdigest() != observation["raw_sha256"]:
        raise ValueError("original response bytes mismatch")
    frames, parse_errors = [], []
    parts = raw.splitlines() if "ndjson" in (observation["content_type"] or "") else [raw]
    for index, part in enumerate(parts):
        if not part:
            continue
        try:
            frames.append(json.loads(part))
        except (ValueError, UnicodeError):
            parse_errors.append(index)
    if parse_errors != observation["raw_parse_error_indices"]:
        raise ValueError("recorded partial/raw parsing classification mismatch")
    final = next(
        (frame for frame in reversed(frames) if isinstance(frame, dict) and frame.get("done")), {}
    )
    input_tokens, generated = final.get("prompt_eval_count"), final.get("eval_count")
    measured = (
        observation["stream_complete"]
        and not parse_errors
        and observation["status"] == 200
        and type(input_tokens) is int
        and type(generated) is int
        and min(input_tokens, generated) >= 0
    )
    charge = input_tokens + generated if measured else intent["token_reservation"]
    if (
        observation["tokens_measured"] != (charge if measured else None)
        or observation["budget_charge"] != charge
    ):
        raise ValueError("usage/upper reservation mismatch")
    for key in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
        native = final.get(key)
        if observation["durations_seconds"][key] != (native / 1e9 if type(native) is int else None):
            raise ValueError("nanosecond conversion mismatch")
    parsed = None
    try:
        parsed = (
            PLANS[host["goal"]]
            .model_validate_json(final["message"]["content"])
            .model_dump(mode="json")
        )
    except (ValueError, KeyError, TypeError):
        pass
    if host["parsed_plan"] != parsed:
        raise ValueError("raw response to parsed plan mismatch")
    return {
        "goal": host["goal"],
        "plan": parsed,
        "opportunity": host["opportunity"],
        "charge": charge,
        "prompt": input_tokens if measured else None,
        "generated": generated if measured else None,
        "missing": not measured,
        "dispatched": True,
    }


def verify_episode(directory, protocol, block, arm, evaluator):
    summary = read(directory / "result.json")
    events, proposals, states, artifacts = signed_records(directory)
    if "treatment" in protocol and arm == "static":
        allocated = Counter(
            event.correlation_id
            for event in events.values()
            if event.issuer == "receiver"
            and event.work is not None
            and event.work.stage == "allocation"
        )
        if any(count != 1 for count in allocated.values()):
            raise ValueError("static arm received a multi-goal adaptive backlog")
        observed_goals = [
            event.work.goal_id
            for event in sorted(events.values(), key=lambda e: e.occurred_at)
            if event.issuer == "receiver"
            and event.work is not None
            and event.work.stage == "discovery"
        ]
        indices = [list(PLANS).index(name) for name in observed_goals]
        if indices != sorted(indices):
            raise ValueError("static arm departed from its preregistered fixed local plan")
    identity = {"run": protocol["id"], "episode": block, "arm": arm}
    attempts = sorted((directory / "model").glob("attempt-*"))
    if len(attempts) > protocol["max_inference_requests_per_arm"]:
        raise ValueError("finite model attempt bound exceeded")
    model = [verify_attempt(path, protocol, identity) for path in attempts]
    calls = [
        json.loads(line)
        for line in (directory / "calls.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    # Indices identify dispatch order. Concurrent monitoring requests are
    # journaled on completion, so their lines may legitimately be reordered.
    if (
        sorted(call["call_index"] for call in calls) != list(range(len(calls)))
        or len(calls) != summary["all_calls"]
    ):
        raise ValueError("call count/sequence mismatch")
    count = passed = false_accepts = unknown = 0
    for name in PLANS:
        expected_cases = evaluator.cases("heldout", name)
        actual_cases = summary["evaluations"].get(name, {}).get("trials", [])
        if len(actual_cases) != len(expected_cases):
            raise ValueError("missing heldout task observations")
        for actual, case in zip(actual_cases, expected_cases, strict=True):
            if actual["case"] != case:
                raise ValueError("hidden reference dataset/checker mismatch")
            observed = actual["observed"]
            success = (
                observed.get("state") == "completed" and observed.get("result") == case["expected"]
            )
            if actual["passed"] != success:
                raise ValueError("saved task flag disagrees with raw result")
            count += 1
            passed += success
            false_accepts += observed.get("state") == "completed" and not success
            unknown += observed.get("state") != "completed"
            if "receipt_id" in observed:
                event = events["receiver", observed["receipt_id"]]
                receipt = event.execution
                if (
                    receipt is None
                    or receipt.invocation_id != observed["id"]
                    or receipt.arguments_digest != fingerprint({"rows": case["rows"]})
                ):
                    raise ValueError("heldout original signed receipt mismatch")
                if receipt.result_digest != (
                    fingerprint(observed["result"]) if observed["state"] == "completed" else None
                ):
                    raise ValueError("signed result digest mismatch")
                if states["receiver", observed["caller"], observed["id"]]["receipt_id"] != event.id:
                    raise ValueError("receipt has no matching persisted invocation")
    formation = summary["formation_result"] or {}
    for item in formation.get("history", []):
        if item["kind"] == "verification" or "formation" not in item:
            continue
        selected = item["step"]["selection"]["proposal"]
        proposal = proposals[selected["issuer"], selected["id"]]
        matching = [m for m in model if m["opportunity"] == proposal.opportunity.id]
        if len(matching) != 1 or matching[0]["plan"] != proposal.arguments["plan"]:
            raise ValueError("raw model draft to selected proposal mismatch")
        binding = item["binding"]
        manifest = json.loads(artifacts["receiver", binding["subject"]["digest"]])
        if manifest["parameters"] != proposal.arguments["plan"]:
            raise ValueError("selected proposal to executable manifest mismatch")
        event = events["receiver", item["formation"]["id"]]
        if event.model_dump(mode="json") != item["formation"]:
            raise ValueError("original signed formation record mismatch")
    if count != 6 or passed != summary["passed_tasks"] or passed / 6 != summary["primary_fraction"]:
        raise ValueError("episode denominator/summary mismatch")
    charge = sum(m["charge"] for m in model)
    if (
        charge != summary["token_budget_charge"]
        or charge > protocol["aggregate_episode_tokens_upper"]
    ):
        raise ValueError("aggregate model budget mismatch")
    missing = sum(m["missing"] for m in model)
    return {
        "block": block,
        "arm": arm,
        "passed": passed,
        "tasks": 6,
        "fraction": passed / 6,
        "attempts": len(model),
        "dispatched_inference_requests": sum(m["dispatched"] for m in model),
        "missing_usage": missing,
        "token_budget_charge": charge,
        "input_tokens": None if missing else sum(m["prompt"] for m in model),
        "generated_tokens": None if missing else sum(m["generated"] for m in model),
        "wall_seconds": summary["inclusive_active_wall_seconds"],
        "first_valid_heldout_seconds": summary.get("first_valid_heldout_seconds"),
        "false_accepts": false_accepts,
        "unknown_tasks": unknown,
        "failure": summary["failure"],
        "stop": formation.get("reason", formation.get("error_type")),
        "qualified_ordinary_execution_receipts": sum(
            e.execution is not None
            and e.execution.purpose == "reuse"
            and e.execution.state == "completed"
            for e in events.values()
        ),
        "remote_uncertain_invocations": sum(
            s["state"] == "unknown" and s["binding_id"] == "checker" for s in states.values()
        ),
        "formation_receipts": sum(e.formation is not None for e in events.values()),
    }


def verify_run(directory):
    protocol = read(directory / "protocol.json")
    errors, episodes = [], []
    for name, digest in protocol["sources"].items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("unsafe source snapshot reference")
        if (
            hashlib.sha256((directory / "source-snapshot" / path).read_bytes()).hexdigest()
            != digest
        ):
            errors.append("source snapshot mismatch: " + name)
    if (
        protocol["sources"]["scripts/tabular_evaluation.py"]
        != hashlib.sha256((ROOT / "scripts/tabular_evaluation.py").read_bytes()).hexdigest()
    ):
        errors.append("current evaluator differs from frozen checker")
    for block in range(protocol["pairs"]):
        settings = read(directory / "private-metadata" / f"evaluation-block-{block:03}.json")
        evaluator = Evaluator(settings)
        for arm in ("static", "adaptive"):
            try:
                episodes.append(
                    verify_episode(
                        directory / f"block-{block:03}-{arm}", protocol, block, arm, evaluator
                    )
                )
            except (
                OSError,
                ValueError,
                KeyError,
                TypeError,
                FormatError,
                VerificationError,
            ) as error:
                errors.append(
                    {
                        "block": block,
                        "arm": arm,
                        "error_type": type(error).__name__,
                        "reason": str(error)[:200],
                    }
                )
    if not any(e["dispatched_inference_requests"] for e in episodes):
        errors.append("required real-model inference was not dispatched")
    return {
        "status": "verified" if not errors else "UNKNOWN",
        "protocol": protocol,
        "errors": errors,
        "episodes": episodes,
        "inference_performed": False,
    }


def analyze(report):
    import importlib.metadata

    import numpy as np
    from scipy import stats

    if report["status"] != "verified":
        return {"status": "UNKNOWN", "errors": report["errors"], "inference_performed": False}
    episodes = report["episodes"]
    static = np.array([e["fraction"] for e in episodes if e["arm"] == "static"])
    adaptive = np.array([e["fraction"] for e in episodes if e["arm"] == "adaptive"])

    def difference(a, b, axis=-1):
        return np.mean(b - a, axis=axis)

    interval = (
        stats.bootstrap(
            (static, adaptive),
            difference,
            paired=True,
            vectorized=True,
            method="percentile",
            n_resamples=9999,
            rng=np.random.default_rng(41031),
        ).confidence_interval
        if len(static) >= 2
        else None
    )
    test = (
        stats.permutation_test(
            (static, adaptive),
            difference,
            permutation_type="samples",
            vectorized=True,
            n_resamples=9999,
            alternative="two-sided",
            rng=np.random.default_rng(41032),
        )
        if len(static) >= 2
        else None
    )
    contrast = adaptive - static
    arms = {}
    for arm in ("static", "adaptive"):
        values = [e for e in episodes if e["arm"] == arm]
        arms[arm] = {
            "episodes": len(values),
            "passed_tasks": sum(e["passed"] for e in values),
            "offered_tasks": sum(e["tasks"] for e in values),
            "mean_episode_fraction": float(np.mean([e["fraction"] for e in values])),
            "model_attempts": sum(e["attempts"] for e in values),
            "dispatched_inference_requests": sum(
                e["dispatched_inference_requests"] for e in values
            ),
            "missing_usage": sum(e["missing_usage"] for e in values),
            "token_budget_charge": sum(e["token_budget_charge"] for e in values),
            "input_tokens": sum(e["input_tokens"] for e in values)
            if all(e["input_tokens"] is not None for e in values)
            else None,
            "generated_tokens": sum(e["generated_tokens"] for e in values)
            if all(e["generated_tokens"] is not None for e in values)
            else None,
            "mean_inclusive_wall_seconds": float(np.mean([e["wall_seconds"] for e in values])),
            "false_accepts": sum(e["false_accepts"] for e in values),
            "unknown_tasks": sum(e["unknown_tasks"] for e in values),
            "stops": dict(Counter(e["stop"] for e in values)),
        }
    sd = float(np.std(contrast, ddof=1)) if len(contrast) >= 2 else None
    z = stats.norm.ppf(0.975) + stats.norm.ppf(0.8)
    return {
        "status": "analyzed",
        "classification": report["protocol"]["classification"],
        "paired_episodes": len(static),
        "arms": arms,
        "paired_differences": contrast.tolist(),
        "mean_adaptive_minus_static": float(np.mean(contrast)),
        "confidence_interval": [float(interval.low), float(interval.high)] if interval else None,
        "confidence_interval_method": "95% paired percentile bootstrap; 9999 samples; seed41031",
        "degenerate_pilot_variance": sd == 0,
        "paired_randomization_p_two_sided": float(test.pvalue) if test is not None else None,
        "randomization_seed": 41032,
        "mcid": report["protocol"]["mcid"],
        "pilot_paired_sd": sd,
        "normal_approximation_n_at_pilot_sd": None
        if sd in (None, 0)
        else int(np.ceil((z * sd / report["protocol"]["mcid"]) ** 2)),
        "normal_approximation_n_at_worst_case_sd1": int(
            np.ceil((z / report["protocol"]["mcid"]) ** 2)
        ),
        "equivalence_tested": False,
        "inference_performed": False,
        "analysis_versions": {n: importlib.metadata.version(n) for n in ("numpy", "scipy")},
        "episodes": episodes,
        "limits": [
            "synthetic finite task families and one shared model/CPU backend",
            "correlated tasks within episode; episode is the statistical unit",
            "small-sample/degenerate bootstrap does not prove population equivalence",
            "shared model cache is not reset; balanced arm order",
            "cold inclusive wall is not the sum of nested receipt times",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify", "analyze"))
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        verification = verify_run(args.run.resolve())
    except (OSError, ValueError, KeyError, TypeError, FormatError, VerificationError) as error:
        verification = {
            "status": "UNKNOWN",
            "errors": [{"error_type": type(error).__name__, "reason": str(error)[:200]}],
            "inference_performed": False,
        }
    result = analyze(verification) if args.command == "analyze" else verification
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
        write_new(args.output / "result.json", result)
        if result.get("episodes"):
            with (args.output / "episodes.csv").open("x", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(result["episodes"][0]))
                writer.writeheader()
                writer.writerows(result["episodes"])
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "status",
                    "errors",
                    "paired_episodes",
                    "mean_adaptive_minus_static",
                    "confidence_interval",
                )
                if key in result
            }
        )
    )
    raise SystemExit(0 if result["status"] in {"verified", "analyzed"} else 1)


if __name__ == "__main__":
    main()
