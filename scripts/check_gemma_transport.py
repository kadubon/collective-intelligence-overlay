"""Original-byte checks for the source-only Gemma study, using the existing CAS.

Schema 2 binds transport observations through the signed parsed artifact. These
are trusted-host observations, not an attestation by the model or its server.
Legacy records retain their original, weaker binding; nothing is backfilled.
"""

import hashlib
import json
import math

from jsonschema import Draft202012Validator

from collective_intelligence_overlay.adapters.inference_observer import COUNTERS
from collective_intelligence_overlay.bindings import fingerprint

REQUIRED = ("intent.json", "observation.json", "response.raw", "model-identity.json")
REQUEST = ("request.raw", "request.json")


def original_bytes(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("missing, unsafe or oversized original transport record")
    return path.read_bytes()


def original_names(directory, observed):
    present = tuple(name for name in REQUEST if (directory / name).exists())
    if len(present) == 1 or (observed["transport_dispatch_started"] and len(present) != 2):
        raise ValueError("missing original request pair")
    return (*REQUIRED, *present)


def persist_originals(directory, observed, artifacts):
    return {
        name: artifacts.put(original_bytes(directory / name))
        for name in original_names(directory, observed)
    }


def check_originals(directory, observed, parsed, owner, artifacts):
    expected = original_names(directory, observed)
    links = parsed.get("original_transport_artifacts")
    if parsed.get("observation_binding_schema") != "2" or set(links or ()) != set(expected):
        raise ValueError("incomplete signed original transport binding")
    for name in expected:
        raw = original_bytes(directory / name)
        digest = hashlib.sha256(raw).hexdigest()
        if links[name] != digest or artifacts.get((owner, digest)) != raw:
            raise ValueError("signed original transport byte changed")


def validate_wire(text, schema, solution_type):
    """Validate the actual JSON before any legacy-default Solution conversion."""
    value = json.loads(text)
    Draft202012Validator(schema).validate(value)
    return solution_type.model_validate(value)


def check_model_attempt(offer, attempt, protocol, world_seed, maximum):
    prefix = offer["id"] + "-draft-"
    suffix = attempt["id"].removeprefix(prefix)
    if not attempt["id"].startswith(prefix) or suffix not in {"0", "1"} or int(suffix) >= maximum:
        raise ValueError("model attempt is outside the fixed offered draft budget")
    seed = int(
        hashlib.sha256(
            f"{protocol['id']}/{world_seed}/{offer['problem']['id']}/{suffix}".encode()
        ).hexdigest()[:8],
        16,
    ) % (2**31 - 1)
    if type(attempt["model_seed"]) is not int or attempt["model_seed"] != seed:
        raise ValueError("model seed differs from the independently declared attempt")


def check_requested_payload(request, raw, intent, protocol, seed, schema, text):
    options = {**protocol["model_options"], "seed": seed}
    expected = {
        "model": protocol["model"],
        "stream": False,
        "options": options,
        "format": schema,
        "keep_alive": "5m",
        "messages": [{"role": "user", "content": text}],
        "tools": [],
        "think": False,
    }
    requested = {"native_options": options, "think": False, "keep_alive": "5m"}
    if (
        hashlib.sha256(raw).hexdigest() != request["payload_digest"]
        or len(raw) != request["byte_count"]
        or fingerprint(json.loads(raw)) != fingerprint(expected)
        or fingerprint(request["payload"]) != fingerprint(expected)
        or fingerprint(intent["requested"]) != fingerprint(requested)
        or intent["settings_digest"] != fingerprint(requested)
        or intent["provenance"]["schema_digest"] != fingerprint(schema)
        or intent["provenance"]["prompt_digest"] != fingerprint(text)
        or intent["token_reservation"] != options["num_ctx"] + options["num_predict"]
        or request["identity"] != intent["identity"]
        or request["method"] != "POST"
        or request["path"] != "/api/chat"
    ):
        raise ValueError("actual request differs from the complete declared payload")


def check_native_observation(raw, observed, intent):
    """Recompute all API-native classifications and counters from original bytes."""
    if hashlib.sha256(raw).hexdigest() != observed["raw_sha256"]:
        raise ValueError("raw inference response changed")
    parts = raw.splitlines() if "ndjson" in (observed["content_type"] or "") else [raw]
    frames, errors = [], []
    for index, part in enumerate(parts):
        if not part:
            continue
        try:
            frames.append(json.loads(part))
        except (ValueError, UnicodeError):
            errors.append(index)
    final = next((f for f in reversed(frames) if isinstance(f, dict) and f.get("done")), {})
    counts = {key: final.get(key) for key in COUNTERS}
    prompt, generated = counts["prompt_eval_count"], counts["eval_count"]
    valid_tokens = type(prompt) is int and type(generated) is int and min(prompt, generated) >= 0
    measured = (
        observed["stream_complete"] is True
        and observed["status"] == 200
        and not errors
        and valid_tokens
    )
    dispatched = observed["transport_dispatch_started"] is True
    charge = prompt + generated if measured else (intent["token_reservation"] if dispatched else 0)
    expected = {
        "identity": intent["identity"],
        "received_bytes": len(raw),
        "raw_parse_error_indices": errors,
        "frame_count": len(frames),
        "final_model": final.get("model"),
        "done": final.get("done"),
        "done_reason": final.get("done_reason"),
        "usage_native": counts,
        "durations_seconds": {
            key: value / 1e9 if isinstance(value, int) else None
            for key, value in counts.items()
            if key.endswith("duration")
        },
        "token_status": "measured" if measured else "unavailable",
        "tokens_measured": prompt + generated if measured else None,
        "budget_charge": charge,
        "budget_charge_status": "measured"
        if measured
        else ("reserved_upper_bound" if dispatched else "not_sent_proven"),
    }
    if any(observed.get(key) != value for key, value in expected.items()):
        raise ValueError("native usage, response or transport classification changed")
    elapsed = observed["client_elapsed_seconds"]
    if type(elapsed) not in (float, int) or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError("invalid observed client interval")
    if not dispatched and (raw or observed["status"] is not None or measured):
        raise ValueError("inconsistent pre-send transport proof")
    return final


def check_selected_identity(identity, protocol, *, dispatched):
    if (
        identity.get("identity_schema") != "1"
        or identity.get("endpoint") != "/api/tags"
        or identity.get("projection_scope") != "selected-model-only"
    ):
        raise ValueError("unknown selected-model observation scope")
    selected = identity.get("selected_model")
    if dispatched and (
        not isinstance(selected, dict)
        or selected.get("name") != protocol["model"]
        or selected.get("digest") != protocol["model_digest"]
        or identity.get("status") != 200
        or identity.get("transport_dispatch_started") is not True
        or identity.get("error_type") is not None
    ):
        raise ValueError("dispatched request lacks pinned selected-model observation")
    digest = identity.get("native_response_sha256")
    if digest is not None and (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(c not in "0123456789abcdef" for c in digest)
    ):
        raise ValueError("invalid native model-inventory response hash")
    if dispatched and digest is None:
        raise ValueError("missing native model-inventory response hash")
