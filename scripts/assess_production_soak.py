"""Audit original invocation projections, uncertainty and fixed sampling slots.

This supplements quantitative validation. Missing old projections remain pending;
no aggregate count or clean driver exit substitutes for original-ID validation.
"""

import argparse
import base64
import json
from pathlib import Path

from validate_production_soak import validate

from collective_intelligence_overlay.bindings import fingerprint


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def explain_uncertainty(exports, originals, calls, faults):
    """Report bounded original lineage and observed causes, never settle effects.

    Quantitative validation has already verified every original signed envelope.
    A coincident fault window alone is insufficient: an original journal root,
    signed child lineage and the failing owned MCP transport must also match.
    """
    contexts = {fingerprint(list(key)): key for key in originals}
    receipts, children, parents = {}, {}, {}
    for owner, exported in exports.items():
        for envelope in exported["signed_records"]:
            record = json.loads(base64.b64decode(envelope["payload"], validate=True))
            if record["kind"] == "event" and record["issuer"] == owner and record.get("execution"):
                receipts[owner, record["id"]] = record["execution"]
    for key, row in originals.items():
        receipt = receipts.get((key[0], row["receipt_id"]), {})
        if receipt and (
            receipt["invocation_id"] != key[2]
            or receipt["caller"] != key[1]
            or receipt["resource_owner"] != key[0]
            or receipt["binding_digest"] != row["binding_digest"]
            or receipt["arguments_digest"] != fingerprint(row["request"]["arguments"])
        ):
            raise ValueError("uncertainty receipt differs from original request")
        parent = contexts.get(receipt.get("parent_invocation"))
        if parent is not None:
            children.setdefault(parent, set()).add(key)
            parents.setdefault(key, set()).add(parent)
    for exported in exports.values():
        for mapping in exported["remote_calls"]:
            parent = contexts.get(mapping["invocation_context"])
            child = mapping["provider"], mapping["owner"], mapping["remote_invocation_id"]
            if parent is not None and child in originals:
                local, remote = originals[parent], originals[child]
                if (
                    local["binding_digest"] != mapping["binding_digest"]
                    or remote["binding_digest"] != mapping["provider_binding_digest"]
                    or fingerprint(remote["request"]["arguments"]) != mapping["arguments_digest"]
                ):
                    raise ValueError(
                        "uncertain remote lineage differs from original binding/arguments"
                    )
                children.setdefault(parent, set()).add(child)
                parents.setdefault(child, set()).add(parent)
    roots = {}
    for call in sorted(calls, key=lambda item: item["offered_seconds"]):
        request = call["request"]
        if call["operation"] == "invoke":
            key = call["owner"], call["owner"], request["invocation_id"]
        elif call["operation"] == "app.verify":
            key = request["provider"], call["owner"], request["attempt"]
        else:
            continue
        original = originals.get(key)
        if original is None or fingerprint(request["arguments"]) != fingerprint(
            original["request"]["arguments"]
        ):
            continue
        if call["operation"] == "invoke" and (
            request["binding_id"] != original["binding_id"]
            or request["binding_digest"] != original["binding_digest"]
        ):
            continue
        # Later retries cannot move an original effect into a new fault window.
        roots.setdefault(key, call)

    def related(key, links):
        pending, visited = [key], set()
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            if len(visited) > 128:
                raise ValueError("uncertainty lineage exceeds declared bounded review")
            pending.extend(links.get(current, ()))
        return visited

    refusal_reasons = {
        "owner_budget_refused",
        "owner_execution_capacity_refused",
        "owner_unresolved_effects_refused",
        "owner_blocking_capacity_refused",
    }
    findings = {}
    for key, row in originals.items():
        receipt = receipts.get((key[0], row["receipt_id"]))
        if (
            row["state"] not in {"unknown", "cancelled", "rejected"}
            or row["reservation_state"] not in {"held", "legacy_unknown"}
            or receipt is None
            or receipt["invocation_id"] != key[2]
            or receipt["caller"] != key[1]
            or receipt["resource_owner"] != key[0]
        ):
            continue
        if row["reason"] in refusal_reasons:
            findings[key] = {"cause": row["reason"], "original": list(key)}
            continue
        if receipt["transport"] != "mcp" or row["phase"] != "dispatched":
            continue
        for ancestor in related(key, parents):
            call = roots.get(ancestor)
            if call is None or call.get("latency_censored", True):
                continue
            for fault in faults.values():
                unavailable = fault.get("provider_unavailable", {})
                if (
                    fault.get("status") == "executed"
                    and unavailable.get("owner") == key[0]
                    and unavailable.get("transport") == "mcp"
                    and isinstance(unavailable.get("pid"), int)
                    and (
                        unavailable.get("physical_stop_confirmed") is True
                        or unavailable.get("physical_exit_confirmed") is True
                    )
                    and 0
                    <= unavailable.get("from_seconds", -1)
                    < unavailable.get("until_seconds", -1)
                    and call["offered_seconds"] < unavailable["until_seconds"]
                    and call["offered_seconds"] + call["wall_seconds"] > unavailable["from_seconds"]
                ):
                    findings[key] = {
                        "cause": "original_mcp_failure_during_observed_provider_unavailability",
                        "original": list(key),
                        "root": list(ancestor),
                        "journal_call_index": call["call_index"],
                        "fault_index": fault["index"],
                        "provider_process": unavailable,
                    }
                    break
            if key in findings:
                break
    explained, unexplained = [], []
    for key, row in originals.items():
        if row["state"] not in {"unknown", "cancelled", "rejected"} or row[
            "reservation_state"
        ] not in {"held", "legacy_unknown"}:
            continue
        causes = [findings[child] for child in sorted(related(key, children)) if child in findings]
        if causes:
            explained.append({"original": list(key), "retained_causes": causes})
        else:
            unexplained.append(list(key))
    return {
        "basis": (
            "original saved refusal or signed lineage to a failing owned MCP transport with an "
            "original journal interval overlapping observed physical unavailability; "
            "effect absence and independent PASS remain unconfirmed"
        ),
        "explained": explained,
        "unexplained": unexplained,
    }


def assess(directory):
    measured = validate(directory)
    protocol = json.loads((directory / "protocol.json").read_text())
    result = json.loads((directory / "result.json").read_text())
    calls = lines(directory / "calls.jsonl")
    samples = lines(directory / "samples.jsonl")
    operations = lines(directory / "operational-samples.jsonl")
    owner_exports = {
        owner: json.loads((directory / f"{owner}-observations.json").read_text())
        for owner in ("producer", "verifier", "receiver")
    }
    pending = set(measured["pending_validation"])
    gates, details = {}, {}

    scheduled = [row for row in samples if "schedule" in row]
    if len(scheduled) == len(samples) and scheduled:
        schedules = [row["schedule"] for row in scheduled]
        due = [row["due_session_seconds"] for row in schedules]
        late = [row["sampling_started_seconds"] - d for row, d in zip(scheduled, due, strict=True)]
        start = result["measurement_started_seconds"]
        end = start + protocol["measurement_seconds"]
        coverage = (
            [row["slot"] for row in schedules] == list(range(len(scheduled)))
            and all(row["interval_seconds"] == 5 for row in schedules)
            and all(abs((b - a) - 5) < 0.000001 for a, b in zip(due, due[1:], strict=False))
            and due[0] <= start
            and due[-1] >= end - 5
            # A sample must begin within its own declared five-second slot.
            # Scheduling jitter and actual intervals are retained separately.
            and all(0 <= delay < 5 for delay in late)
            and all(
                row["sampling_completed_seconds"] >= row["sampling_started_seconds"]
                for row in scheduled
            )
        )
        gates["continuous_declared_os_sample_slots"] = coverage
        details["sampling"] = {
            "nominal_interval_seconds": 5,
            "slots": len(scheduled),
            "first_due_seconds": due[0],
            "last_due_seconds": due[-1],
            "maximum_start_lateness_seconds": max(late),
            "basis": "one OS observation begun per declared slot; actual jitter retained",
        }
        pending.discard("uninterrupted_five_second_sample_coverage")

    complete = all(
        "remote_calls" in exported
        and all("request" in row and "reason" in row for row in exported["invocations"])
        for exported in owner_exports.values()
    )
    if complete:
        originals = {}
        uncertainty = []
        mapping_count = 0
        for owner, exported in owner_exports.items():
            reservations = {row["task"]: row for row in exported["reservations"]}
            ids = [(row["caller"], row["id"]) for row in exported["invocations"]]
            lease_ids = [row["lease_id"] for row in exported["invocations"]]
            if len(ids) != len(set(ids)) or len(lease_ids) != len(set(lease_ids)):
                raise ValueError("duplicate original invocation or reservation")
            maps = exported["remote_calls"]
            keys = [(row["caller"], row["call_key"]) for row in maps]
            remote = [(row["provider"], row["remote_invocation_id"]) for row in maps]
            if len(keys) != len(set(keys)) or len(remote) != len(set(remote)):
                raise ValueError("duplicate original logical/provider call mapping")
            mapping_count += len(maps)
            for row in exported["invocations"]:
                originals[owner, row["caller"], row["id"]] = row
                if row["owner"] != owner or row["lease_id"] not in reservations:
                    raise ValueError("original invocation lost its owner or reservation")
                if row["reservation_state"] == "released" and (
                    row["phase"] != "reserved" or not row["release_reason"]
                ):
                    raise ValueError("uncertain dispatched invocation was refunded")
                if row["state"] in {"unknown", "cancelled", "rejected"} and row[
                    "reservation_state"
                ] in {"held", "legacy_unknown"}:
                    uncertainty.append(
                        {
                            "owner": owner,
                            "caller": row["caller"],
                            "id": row["id"],
                            "phase": row["phase"],
                            "reason": row["reason"],
                            "receipt_id": row["receipt_id"],
                            "created_at": row["created_at"],
                            "allowance_retained": True,
                        }
                    )
        retained, refusals, unchanged_queries = 0, 0, 0
        for call in calls:
            request, response = call["request"], call.get("result", {})
            owner = call["owner"]
            if call["operation"] == "invoke":
                row = originals.get((owner, owner, request["invocation_id"]))
                if response.get("error") == "SERVICE_INTAKE_CLOSED":
                    if row is not None:
                        raise ValueError("closed intake request acquired an execution row")
                    refusals += 1
                if response.get("state") == "completed":
                    if (
                        row is None
                        or row["binding_id"] != request["binding_id"]
                        or row["binding_digest"] != request["binding_digest"]
                        or row["result_digest"] != fingerprint(response["result"])
                        or row["receipt_id"] != response["receipt_id"]
                    ):
                        raise ValueError("completed original changed its binding/result/receipt")
                    retained += 1
            queried = response.get("invocation")
            if call["operation"] == "invocation" and queried is not None:
                row = originals.get((owner, owner, request["invocation_id"]))
                if (
                    row is None
                    or queried["id"] != request["invocation_id"]
                    or queried["caller"] != owner
                    or queried["fingerprint"] != row["fingerprint"]
                    or queried["binding_digest"] != row["binding_digest"]
                    or queried["arguments_digest"] != fingerprint(row["request"]["arguments"])
                    or (
                        queried["state"] == "completed"
                        and queried["result_digest"] != row["result_digest"]
                    )
                ):
                    raise ValueError("original-ID query differs from preserved request/result")
                unchanged_queries += 1
            if call["operation"] == "reconcile" and "event" in response:
                receipt = response["event"]["reconciliation"]
                if receipt["independent_verification"] != "UNKNOWN":
                    raise ValueError("effect observation created independent PASS")
        details["originals"] = {
            "invocations": len(originals),
            "remote_mappings": mapping_count,
            "completed_calls_matched": retained,
            "original_queries_matched": unchanged_queries,
            "closed_intake_requests_without_execution": refusals,
            "held_uncertainty": uncertainty,
        }
        faults = {row["index"]: row for row in result["faults"]}
        fault_checks = (
            faults.get(3, {}).get("original_receipt_unchanged") is True
            and faults.get(4, {}).get("withdrawn_support_not_accepted") is True
            and faults.get(4, {}).get("checker_quiescent_during_withdrawal") is True
            and faults.get(4, {}).get("fresh_check_id") is not None
            and faults.get(4, {}).get("observations", [{}])[-1].get("decision", {}).get("outcome")
            == "ACCEPT"
            and faults.get(7, {}).get("new_effect_refused") is True
            and faults.get(10, {}).get("budget_refused") is True
        )
        gates["original_effect_signature_and_refusal_audit"] = fault_checks
        pending.discard("all_original_effect_and_signature_safety_invariants")

        # Explain every retained uncertain original through its saved failure
        # receipt. Generic execution_unknown alone is not a root-cause finding;
        # it remains pending rather than being relabelled as explained growth.
        unexplained = [row for row in uncertainty if not row["reason"] or not row["receipt_id"]]
        details["uncertainty_without_original_reason_or_receipt"] = unexplained
        details["uncertainty_requires_fault_cause_review"] = [
            row for row in uncertainty if row["reason"] == "execution_unknown"
        ]
        causal_review = explain_uncertainty(owner_exports, originals, calls, faults)
        details["original_uncertainty_cause_review"] = causal_review
        targets = [
            row["observation"]
            for row in operations
            if row["owner"] == "receiver-current-targets" and "targets" in row["observation"]
        ]
        unexplained_targets = [
            target
            for observation in targets
            for target in observation["targets"]
            if target["decision"]["outcome"] != "ACCEPT" and not target["decision"]["reasons"]
        ]
        details["backlog_decisions_without_reasons"] = len(unexplained_targets)
        if not causal_review["unexplained"] and targets:
            gates["unexplained_unresolved_or_backlog_growth"] = not (
                unexplained or unexplained_targets
            )
            pending.discard("unexplained_backlog_growth")

    passed = (
        not protocol["development_only"]
        and not pending
        and all(measured["gates"].values())
        and all(gates.values())
    )
    return {
        "assessment": "production-soak-original-audit.v1",
        "profile_id": protocol["profile_id"],
        "profile_sha256": protocol["profile_sha256"],
        "artifacts": protocol["artifacts"],
        "quantitative_validation": measured,
        "additional_gates": gates,
        "details": details,
        "pending_validation": sorted(pending),
        "passed": passed,
        "release_approval": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(assess(args.directory.resolve()), indent=2))
