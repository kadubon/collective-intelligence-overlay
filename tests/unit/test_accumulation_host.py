"""Finite metadata accounting and native process sample shape; no model generation."""

import hashlib
import json
import os
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
import accumulation_host  # noqa: E402
import run_production_experiment  # noqa: E402


@pytest.mark.parametrize("failure", [None, "disconnect", "oversized"])
async def test_owned_metadata_has_actual_bytes_errors_and_finite_call_cap(tmp_path, failure):
    server = accumulation_host.OwnedOllama(tmp_path / "private", tmp_path, metadata_cap=1)
    raw = b'{"version":"unit-transport"}' if failure != "oversized" else b"x" * 1048577

    def respond(request):
        if failure == "disconnect":
            raise httpx.ConnectError("deliberate unit fault", request=request)
        return httpx.Response(200, content=raw)

    async with httpx.AsyncClient(
        base_url=server.host, transport=httpx.MockTransport(respond), trust_env=False
    ) as client:
        if failure:
            with pytest.raises((httpx.ConnectError, ValueError)):
                await server.metadata(client, "GET", "/api/version")
        else:
            assert (await server.metadata(client, "GET", "/api/version")).content == raw
        with pytest.raises(ValueError, match="observation cap"):
            await server.metadata(client, "GET", "/api/version")
    rows = [
        json.loads(line)
        for line in (tmp_path / "model-metadata-calls.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 1 and rows[0]["index"] == 1
    observed = rows[0]
    assert observed["client_elapsed_seconds"] >= 0
    assert not observed["raw_inventory_or_private_model_path_republished"]
    if failure == "disconnect":
        assert observed["error_type"] == "ConnectError" and observed["response_bytes"] is None
    else:
        assert observed["response_bytes"] == len(raw)
        assert observed["native_response_sha256"] == hashlib.sha256(raw).hexdigest()
        assert observed["error_type"] == ("ValueError" if failure else None)


def test_linux_observer_unpacks_native_snapshot_and_retains_vanished_processes(
    tmp_path, monkeypatch
):
    sample = {
        os.getpid(): {
            "parent_pid": 0,
            "start_ticks": 123,
            "rss_bytes": 4,
            "user_seconds": 2,
            "system_seconds": 1,
        }
    }
    monkeypatch.setattr(accumulation_host, "sys_platform_windows", lambda: False)
    monkeypatch.setattr(run_production_experiment, "process_sample", lambda: (sample, 7))
    observer = accumulation_host.ProcessObserver(tmp_path / "processes.jsonl", 60)
    try:
        observer.sample()
    finally:
        observer.close()
    observed = json.loads((tmp_path / "processes.jsonl").read_text())
    assert observed["status"] == "measured", observed
    assert observed["vanished_during_sample"] == 7
    assert observed["processes"] == {str(pid): value for pid, value in sample.items()}


@pytest.mark.parametrize("target", ["original", "missing", "duplicate", "cap", "negative", "final"])
def test_complete_metadata_counter_review_rejects_missing_or_changed_observations(target):
    paths = [
        "/api/version",
        "/api/version",
        "/api/tags",
        "/api/show",
        "/api/ps",
        "/api/ps",
        "/api/version",
    ]
    rows = [
        {
            "index": i + 1,
            "method": "POST" if path == "/api/show" else "GET",
            "path": path,
            "client_elapsed_seconds": 0.1,
            "response_bytes": 2,
            "native_response_sha256": "a" * 64,
            "status": 200,
            "raw_inventory_or_private_model_path_republished": False,
        }
        for i, path in enumerate(paths)
    ]
    manifest = {"metadata_observation_call_cap": 8, "metadata_observations_before_inference": 5}
    if target == "missing":
        rows.pop(2)
    elif target == "duplicate":
        rows[1]["index"] = 1
    elif target == "cap":
        manifest["metadata_observation_call_cap"] = 7
    elif target == "negative":
        rows[0]["client_elapsed_seconds"] = -1
    elif target == "final":
        rows[-1]["path"] = "/api/tags"
    if target == "original":
        assert accumulation_host.check_metadata_observations(rows, manifest, 8)["total_calls"] == 7
    else:
        with pytest.raises(ValueError):
            accumulation_host.check_metadata_observations(rows, manifest, 8)


def test_server_environment_projection_pins_private_settings_without_exposing_values():
    environment = {"OLLAMA_MODELS": "private path", "HTTP_PROXY": "private credential", "PATH": "x"}
    original = accumulation_host.server_environment_digest(environment)
    assert len(original) == 64 and "private" not in original
    assert original == accumulation_host.server_environment_digest({**environment, "PATH": "y"})
    assert original != accumulation_host.server_environment_digest(
        {**environment, "OLLAMA_MODELS": "other"}
    )


def test_runtime_show_hash_survives_public_redaction_and_pins_blob_and_options():
    import copy

    from prepare_gemma_public import public_bytes

    manifest = {
        "requested_model": "gemma4:e4b",
        "tags": {"models": [{"name": "gemma4:e4b", "digest": "a" * 64, "details": {}}]},
        "version": {"version": "test-only"},
        "ollama_binary_sha256": "b" * 64,
        "hardware": {"python": "test-only", "selected_dependencies": {}},
        "operating_system": "test-only",
        "machine": "test-only",
        "settings": {},
        "owned_server_environment_sha256": "c" * 64,
        "show": {
            "modelfile": "FROM C:/Users/private-user/models/sha256-weight\n"
            'DRAFT """\nFROM C:/Users/private-user/models/sha256-draft\n"""\n'
            "PARAMETER draft_num_predict 3\n",
            "model_info": {"quantize.imatrix.file": "/Users/upstream/private.imatrix"},
            "parameters": "draft_num_predict 3\ntemperature 1\ntop_k 64\ntop_p 0.95",
        },
    }
    original = accumulation_host.runtime_contract(manifest)
    raw, changes = public_bytes(Path("model-manifest.json"), json.dumps(manifest).encode())
    assert changes and b"private-user" not in raw
    assert original == accumulation_host.runtime_contract(json.loads(raw))
    assert original["model_show_projection_schema"] == "home-path-unique-parameter-order-v2"
    import itertools

    lines = manifest["show"]["parameters"].split("\n")
    for order in itertools.permutations(lines):
        reordered = copy.deepcopy(manifest)
        reordered["show"]["parameters"] = "\n".join(order)
        assert original == accumulation_host.runtime_contract(reordered)
    for before, after in (("3", "0"), ("1", "0.2"), ("64", "32"), ("0.95", "0.90")):
        changed = copy.deepcopy(manifest)
        changed["show"]["parameters"] = changed["show"]["parameters"].replace(before, after)
        assert original != accumulation_host.runtime_contract(changed)
    for invalid in ("top_k 64\ntop_k 32", "top_k", {"top_k": 64}):
        changed = copy.deepcopy(manifest)
        changed["show"]["parameters"] = invalid
        with pytest.raises(ValueError):
            accumulation_host.runtime_contract(changed)
    changed = copy.deepcopy(manifest)
    changed["show"]["modelfile"] = changed["show"]["modelfile"].replace(
        "sha256-draft", "sha256-other"
    )
    assert original != accumulation_host.runtime_contract(changed)
    changed = copy.deepcopy(manifest)
    changed["show"]["parameters"] = "draft_num_predict 0"
    assert original != accumulation_host.runtime_contract(changed)
