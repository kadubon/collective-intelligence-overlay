"""Verify saved matched experiment original DSSE, isolation, inputs and allowances."""

import argparse
import base64
import json
import sys
from decimal import Decimal
from pathlib import Path

from collective_intelligence_overlay.bindings import fingerprint
from collective_intelligence_overlay.models import Evidence
from collective_intelligence_overlay.security import digest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "examples"), str(ROOT / "scripts")]


def export_check_artifacts(artifacts, items):
    """These inputs are public fixtures; no private application settings are exported."""
    return {
        value["artifact_digest"]: base64.b64encode(artifacts.get(value["artifact_digest"])).decode()
        for item in items
        if (value := (item.get("check") or {}).get("evidence"))
    }


def validate(directory):
    from evaluate_documents import validate_owner_observations
    from run_production_experiment import SEEDS, cases

    protocol = json.loads((directory / "protocol.json").read_text(encoding="utf-8"))
    summary = json.loads((directory / "results.json").read_text(encoding="utf-8"))
    if summary.get("protocol_sha256") is not None:
        if summary["protocol_sha256"] != fingerprint(protocol):
            raise ValueError("saved protocol digest mismatch")
    elif not protocol["development_only"]:
        raise ValueError("formal protocol digest missing")
    for name, expected in protocol.get("sources", {}).items():
        if (
            Path(name).name != name
            or digest((directory / "sources" / name).read_bytes()) != expected
        ):
            raise ValueError("saved source changed")
    if not summary["complete"] or len(summary["arms"]) != 2 * len(protocol["seeds"]):
        raise ValueError("experiment assignments unfinished")
    if not protocol["development_only"] and protocol["seeds"] != list(SEEDS):
        raise ValueError("formal seed set differs from the declaration")
    databases, previous_keys = set(), set()
    signed_count = 0
    arms = []
    for index, assignment in enumerate(summary["arms"]):
        arm_dir = directory / assignment["directory"]
        if arm_dir.parent.resolve() != directory.resolve():
            raise ValueError("unsafe arm report path")
        report = json.loads((arm_dir / "result.json").read_text(encoding="utf-8"))
        seed = protocol["seeds"][index // 2]
        modes = ("strong_static_local", "observation_adaptive")
        if index // 2 % 2:
            modes = tuple(reversed(modes))
        if (report["seed"], report["mode"]) != (seed, modes[index % 2]):
            raise ValueError("assignment order or mode changed")
        if report["initial_allowance"] != {
            owner: "500" for owner in ("producer", "verifier", "receiver")
        }:
            raise ValueError("initial allowance changed")
        if report["elapsed_before_export_seconds"] > protocol["maximum_arm_seconds"] + 1:
            raise ValueError("arm exceeded declared bound")
        formation = cases(seed, "formation", 6)
        expected_inputs = cases(seed, "held-out", 24)
        if [(v["id"], v["input"]) for v in report["formation_cases"]] != [
            (v["id"], v["input"]) for v in formation
        ]:
            raise ValueError("formation inputs changed")
        if [(v["id"], v["input"]) for v in report["held_out"]] != [
            (v["id"], v["input"]) for v in expected_inputs
        ]:
            raise ValueError("held-out cases changed, omitted or reordered")
        threshold = len("\n".join(v["input"] for v in formation).split())
        evidence, events, current_keys = {}, {}, set()
        if set(report["owners"]) != {"producer", "receiver", "verifier"}:
            raise ValueError("three independent owner exports required")
        for owner in report["owners"]:
            owner_report = json.loads(
                (arm_dir / f"{owner}-observations.json").read_text(encoding="utf-8")
            )
            checked = validate_owner_observations(owner_report, owner, Decimal(500))
            if checked["database_identity"] in databases:
                raise ValueError("database reused between owners/arms")
            databases.add(checked["database_identity"])
            current_keys |= checked["keyids"]
            evidence.update(checked["evidence"])
            events.update(checked["events"])
            signed_count += checked["verified_signed_records"]
        if current_keys & previous_keys:
            raise ValueError("signing keys reused between arms")
        previous_keys |= current_keys
        proofs = json.loads((arm_dir / "check-artifacts.json").read_text(encoding="utf-8"))
        passed = 0
        for item in report["held_out"]:
            output = item["output"] or {}
            expected = {"long": len(item["input"].split()) > threshold, "threshold": threshold}
            checked = (item["check"] or {}).get("evidence")
            actually_passed = False
            if checked is not None:
                claim = Evidence.model_validate(checked)
                if claim != evidence.get((claim.issuer, claim.id)) or claim.issuer != "verifier":
                    raise ValueError("check has no matching independently signed evidence")
                raw = base64.b64decode(proofs[claim.artifact_digest], validate=True)
                if digest(raw) != claim.artifact_digest:
                    raise ValueError("independent check artifact digest mismatch")
                proof = json.loads(raw)
                if (
                    proof["request"]["arguments"] != {"text": item["input"]}
                    or proof["request"]["provider"] != "receiver"
                    or proof["request"]["name"] != "triage"
                    or proof["binding"] != claim.binding_digest
                    or proof["observed"] != item["check"]["observed"]
                ):
                    raise ValueError("independent check does not cover this task/binding")
                for observed, caller, purpose in (
                    (output, "receiver", "reuse"),
                    (proof["observed"], "verifier", "verification"),
                ):
                    if observed.get("state") != "completed":
                        continue
                    receipt = events.get(("receiver", observed.get("receipt_id")))
                    if (
                        receipt is None
                        or receipt.execution is None
                        or receipt.execution.caller != caller
                        or receipt.execution.purpose != purpose
                        or receipt.execution.invocation_id != observed["id"]
                        or receipt.execution.arguments_digest
                        != fingerprint({"text": item["input"]})
                        or receipt.execution.result_digest != fingerprint(observed["result"])
                        or receipt.execution.binding_digest != claim.binding_digest
                    ):
                        raise ValueError("task result lacks matching original invocation receipt")
                actually_passed = (
                    output.get("state") == "completed"
                    and output.get("result") == expected
                    and claim.verdict == "PASS"
                    and claim.binding_digest == output.get("binding_digest")
                )
            if item["passed"] != actually_passed:
                raise ValueError("reported business PASS differs from original evidence/result")
            passed += actually_passed
        if report["denominator"] != 24 or passed != report["passed_business_tasks"]:
            raise ValueError("denominator or outcome count changed")
        if assignment["passed"] != passed or assignment["denominator"] != 24:
            raise ValueError("summary outcome count changed")
        if report["mode"] == "strong_static_local" and any(
            "proposers" in item for item in report.get("run", {}).get("history", [])
        ):
            raise ValueError("static baseline accidentally executed adaptive allocation")
        raw_calls = [
            json.loads(line)
            for line in (arm_dir / "calls.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        if raw_calls != report["calls"]:
            raise ValueError("raw offered calls differ from the report")
        arms.append({"seed": seed, "mode": report["mode"], "passed": passed, "denominator": 24})
    differences = []
    for seed in protocol["seeds"]:
        paired = {arm["mode"]: arm["passed"] / 24 for arm in arms if arm["seed"] == seed}
        differences.append(paired["observation_adaptive"] - paired["strong_static_local"])
    if (
        summary["paired_fraction_differences"] != differences
        or summary["descriptive_mean_difference"] != sum(differences) / len(differences)
        or summary["descriptive_observed_range"] != [min(differences), max(differences)]
    ):
        raise ValueError("reported paired statistics differ from original task outcomes")
    return {
        "validator": "production-documents-matched-validation.v1",
        "arms": arms,
        "separate_databases": len(databases),
        "verified_original_signed_records": signed_count,
        "allowance_conserved": True,
        "development_only": protocol["development_only"],
        "general_adaptive_advantage_established": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.directory.resolve()), indent=2))
