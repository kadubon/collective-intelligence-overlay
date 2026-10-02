"""Offline inspection of frozen synthetic physical-fault test evidence.

This verifies preserved source/DSSE and executed assertions. It cannot independently
re-observe past OS processes or infer arbitrary external effects from these files.
"""

import argparse
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree

from securesystemslib.signer import Key

from collective_intelligence_overlay.models import Event
from collective_intelligence_overlay.security import Principal, verify

LABELS = {
    "dispatch-legacy-False",
    "dispatch-legacy-True",
    "completed-legacy-False",
    "completed-legacy-True",
    "lost-response-legacy-False",
    "nested",
    "nested-complete",
    "partial-provider",
    "fenced-alive-worker",
}


def verify_audit(directory):
    inputs = json.loads((directory / "inputs.json").read_bytes())
    result = json.loads((directory / "result.json").read_bytes())
    if result["exit_code"] != 0 or result["source_unchanged"] is not True:
        raise ValueError("frozen source execution did not pass")
    for name, expected in inputs["source"].items():
        path = directory / "source" / name
        if not path.resolve().is_relative_to((directory / "source").resolve()):
            raise ValueError("source path escapes snapshot")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("source snapshot changed: " + name)
    suites = ElementTree.parse(directory / "pytest.xml").findall(".//testsuite")
    if not suites or sum(int(s.attrib["tests"]) for s in suites) != 48:
        raise ValueError("fault cohort is incomplete")
    if any(int(s.attrib[k]) for s in suites for k in ("failures", "errors", "skipped")):
        raise ValueError("failed or skipped mandatory tests")
    files = list((directory / "raw").glob("*/observations.json"))
    if {p.parent.name for p in files} != LABELS:
        raise ValueError("physical raw cohort missing or changed")
    counts, anchors, closures = 0, 0, 0
    for path in files:
        raw = json.loads(path.read_bytes())
        principals = {
            owner: Principal(
                Key.from_dict(value["keyid"], value["key"]),
                value["trust_group"],
                frozenset(value["methods"]),
            )
            for owner, value in raw["keys"].items()
        }
        row = raw["original_invocation"]
        if (
            row["state"] != "unknown"
            or row["phase"] != "dispatched"
            or row["reservation_state"] != "held"
            or row["receipt_id"] is not None
            or row["result"] is not None
            or raw["worker_exit_code"] in (None, 0)
            or raw["model_inference_performed"] is not False
        ):
            raise ValueError("original receiptless UNKNOWN/physical-kill proof changed")
        indexed = {}
        for signed in raw["records"].values():
            for envelope in signed:
                record = verify(envelope, principals)
                key = (record.issuer, record.id) if isinstance(record, Event) else None
                if key:
                    if key in indexed and indexed[key] != record:
                        raise ValueError("conflicting original signed event")
                    indexed[key] = record
                counts += 1
        matched = []
        for event in indexed.values():
            if event.invocation_observation:
                anchors += 1
            receipt = event.resolution
            if receipt and receipt.invocation_id == row["id"] and event.schema_version == "6":
                if (
                    receipt.original_receipt is not None
                    or receipt.original_fingerprint != row["fingerprint"]
                    or receipt.independent_verification != "UNKNOWN"
                    or receipt.allowance_changed is not False
                    or not receipt.worker_quiescent
                    or not receipt.original_request_checked
                    or not receipt.all_children_checked
                ):
                    raise ValueError("closure changed original facts or quality")
                basis = indexed[(receipt.basis.issuer, receipt.basis.id)]
                observation = basis.invocation_observation
                if (
                    observation is None
                    or observation.request_fingerprint != row["fingerprint"]
                    or observation.binding_digest != row["binding_digest"]
                    or observation.origin != receipt.basis_origin
                ):
                    raise ValueError("closure basis differs from pinned original")
                matched.append(event)
                closures += 1
        if len(matched) != 1:
            raise ValueError("physical case has no unique historical closure")
    return {
        "status": "verified_frozen_synthetic_fault_evidence",
        "tests": 48,
        "skips": 0,
        "physical_cases": len(files),
        "verified_signed_records": counts,
        "anchor_events": anchors,
        "receiptless_parent_closures": closures,
        "limits": "past process termination is an executed test witness, not re-observed now",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify_audit(args.run), indent=2))


if __name__ == "__main__":
    main()
