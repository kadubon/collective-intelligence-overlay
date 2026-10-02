"""Actual smoke transport bytes plus explicitly synthetic adverse binding tests."""

import copy
import hashlib
import json
import socket
import sys
import zipfile
from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError as SchemaError
from pydantic import ValidationError

from collective_intelligence_overlay.artifacts import Artifacts

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from accumulation_application import wire_schema  # noqa: E402
from accumulation_primitives import Solution  # noqa: E402
from check_gemma_transport import (  # noqa: E402
    check_model_attempt,
    check_native_observation,
    check_originals,
    check_requested_payload,
    check_selected_identity,
    persist_originals,
    validate_wire,
)


@pytest.fixture
def original(tmp_path, monkeypatch):
    archive = ROOT / "tests/fixtures/accumulation-smoke-v4.zip"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == (
        "793c7f34f4f5cbac4a72d2fb32b926467e22dd53a36160cd6e126a8d2b3eb55d"
    )
    with zipfile.ZipFile(archive) as zipped:
        names = [
            n
            for n in zipped.namelist()
            if "/model/smoke-0-draft-0/" in n
            and Path(n).name
            in {"intent.json", "observation.json", "request.raw", "request.json", "response.raw"}
        ]
        assert len(names) == 5
        directory = tmp_path / "original"
        directory.mkdir()
        for name in names:
            (directory / Path(name).name).write_bytes(zipped.read(name))

    def blocked(*args, **kwargs):
        raise AssertionError("offline transport test attempted network")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    return directory


def read(path):
    return json.loads(path.read_bytes())


def test_actual_smoke_native_counters_and_classifications_are_recomputed(original):
    final = check_native_observation(
        (original / "response.raw").read_bytes(),
        read(original / "observation.json"),
        read(original / "intent.json"),
    )
    assert final["done"] is True and final["model"] == "gemma4:e4b"


@pytest.mark.parametrize(
    "target", ["original", "seed", "world", "protocol", "extra_draft", "other_offer"]
)
def test_actual_longitudinal_seed_recomputed_from_fixed_world_problem_and_draft(original, target):
    archive = ROOT / "tests/fixtures/accumulation-state-v2-first-world.zip"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == (
        "ff1e744eb606fce42b46a5ea4cf83b2810942de792e45aae060ef275d3cb54d8"
    )
    with zipfile.ZipFile(archive) as zipped:
        protocol = json.loads(zipped.read("protocol.json"))
        summary = json.loads(zipped.read("world-e72d6fd2bb3903cd1cf8-E/arm-result.json"))
    offer = summary["offers"][0]
    attempt = offer["attempts"][0]
    world = protocol["world_seeds"][0]
    if target == "seed":
        attempt["model_seed"] += 1
    elif target == "world":
        world += 1
    elif target == "protocol":
        protocol["id"] += "-changed"
    elif target == "extra_draft":
        attempt["id"] = offer["id"] + "-draft-2"
    elif target == "other_offer":
        attempt["id"] = "different-offer-draft-0"
    if target == "original":
        check_model_attempt(offer, attempt, protocol, world, 1)
    else:
        with pytest.raises(ValueError):
            check_model_attempt(offer, attempt, protocol, world, 1)


def payload_case(original):
    request, intent = read(original / "request.json"), read(original / "intent.json")
    options = request["payload"]["options"]
    protocol = {
        "model": "gemma4:e4b",
        "model_options": {k: v for k, v in options.items() if k != "seed"},
    }
    return (
        request,
        intent,
        protocol,
        options["seed"],
        request["payload"]["format"],
        request["payload"]["messages"][0]["content"],
    )


def test_actual_complete_native_request_matches_declared_schema_and_options(original):
    request, intent, protocol, seed, schema, text = payload_case(original)
    check_requested_payload(
        request, (original / "request.raw").read_bytes(), intent, protocol, seed, schema, text
    )


@pytest.mark.parametrize(
    "target",
    ["extra_option", "extra_payload_field", "tools", "stream_type", "keep_alive", "second_message"],
)
def test_consistently_rehashed_extra_or_changed_request_settings_fail(original, target):
    request, intent, protocol, seed, schema, text = payload_case(original)
    payload = request["payload"]
    if target == "extra_option":
        payload["options"]["num_thread"] = 99
    elif target == "extra_payload_field":
        payload["ignored_by_old_subset_check"] = True
    elif target == "tools":
        payload["tools"] = [{"function": {"name": "hidden-tool"}}]
    elif target == "stream_type":
        payload["stream"] = 0
    elif target == "keep_alive":
        payload["keep_alive"] = "0s"
    else:
        payload["messages"].append({"role": "system", "content": "extra state"})
    raw = json.dumps(payload).encode()
    request["payload_digest"] = hashlib.sha256(raw).hexdigest()
    request["byte_count"] = len(raw)
    with pytest.raises(ValueError, match="complete declared payload"):
        check_requested_payload(request, raw, intent, protocol, seed, schema, text)


@pytest.mark.parametrize(
    "key",
    [
        "identity",
        "received_bytes",
        "frame_count",
        "done_reason",
        "final_model",
        "budget_charge_status",
        "token_status",
        "usage_native",
        "client_elapsed_seconds",
    ],
)
def test_native_metadata_and_counter_edits_fail(original, key):
    observed = read(original / "observation.json")
    observed[key] = -1
    with pytest.raises(ValueError):
        check_native_observation(
            (original / "response.raw").read_bytes(), observed, read(original / "intent.json")
        )


def identity():
    return {
        "identity_schema": "1",
        "endpoint": "/api/tags",
        "projection_scope": "selected-model-only",
        "selected_model": {"name": "gemma4:e4b", "digest": "a" * 64},
        "native_response_sha256": "b" * 64,
        "status": 200,
        "transport_dispatch_started": True,
        "error_type": None,
    }


def test_unit_cas_binding_rejects_balanced_usage_edits_and_missing_original(original, tmp_path):
    # This derived unit binding is not inserted into the archived legacy study.
    (original / "model-identity.json").write_text(json.dumps(identity()), encoding="utf-8")
    store = Artifacts(tmp_path / "CAS")
    observed = read(original / "observation.json")
    links = persist_originals(original, observed, store)
    parsed = {"observation_binding_schema": "2", "original_transport_artifacts": links}
    originals = {("producer", digest): store.get(digest) for digest in links.values()}
    check_originals(original, observed, parsed, "producer", originals)
    raw = read(original / "response.raw")
    raw["prompt_eval_count"] += 1
    raw["eval_count"] -= 1
    (original / "response.raw").write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="signed original transport byte"):
        check_originals(original, observed, parsed, "producer", originals)
    (original / "request.raw").unlink()
    with pytest.raises(ValueError, match="missing original request pair"):
        check_originals(original, observed, parsed, "producer", originals)


@pytest.mark.parametrize(
    "key",
    [
        "selected_model",
        "native_response_sha256",
        "status",
        "error_type",
        "projection_scope",
        "transport_dispatch_started",
    ],
)
def test_dispatched_request_requires_selected_exact_model_identity(key):
    value = identity()
    value[key] = "TestFailure" if key == "error_type" else None
    with pytest.raises(ValueError):
        check_selected_identity(
            value, {"model": "gemma4:e4b", "model_digest": "a" * 64}, dispatched=True
        )


def test_selected_model_projection_is_valid_but_not_a_model_attestation():
    check_selected_identity(
        identity(), {"model": "gemma4:e4b", "model_digest": "a" * 64}, dispatched=True
    )


def wire():
    return {
        "family": "calibration",
        "explanation": "unit schema test",
        "sql": "",
        "coefficients": [2.0, 3.0, 0],
        "reduction": "sum",
        "calibration_order": "not-applicable",
        "uses": [],
    }


@pytest.mark.parametrize("missing", list(wire()))
def test_required_wire_fields_cannot_be_completed_by_legacy_defaults(missing):
    value = wire()
    del value[missing]
    with pytest.raises(SchemaError):
        validate_wire(
            json.dumps(value), wire_schema("calibration", "low").model_json_schema(), Solution
        )


@pytest.mark.parametrize("coefficient", [True, "2", None, {}, 1000001])
def test_numeric_wire_coercion_and_coefficient_overflow_fail(coefficient):
    value = wire()
    value["coefficients"][0] = coefficient
    with pytest.raises((SchemaError, ValidationError)):
        validate_wire(
            json.dumps(value), wire_schema("calibration", "low").model_json_schema(), Solution
        )


def test_valid_complete_affine_wire_and_wrong_family_remain_distinct():
    value = wire()
    solution = validate_wire(
        json.dumps(value), wire_schema("calibration", "low").model_json_schema(), Solution
    )
    assert solution.coefficients == (2, 3, 0)
    changed = copy.deepcopy(value)
    changed["family"] = "sql"
    with pytest.raises(SchemaError):
        validate_wire(
            json.dumps(changed), wire_schema("calibration", "low").model_json_schema(), Solution
        )
