"""Publication keeps proof bytes distinct from explicitly transformed metadata."""

import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def publication(monkeypatch):
    path = Path(__file__).parents[2] / "scripts/prepare_gemma_public.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("tested_gemma_public", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "path",
    [
        "source/scripts/application.py",
        "source-snapshot/src/application.py",
        "world-E/model/request/intent.json",
        "world-M/offers/train-1/result.json",
        "world-C/receiver-decisions.json",
        "world-C/snapshot-6.json",
        "world-C/irrelevant-stock.json",
        "world-C/new-receiver-stock.json",
        "world-C/calls.jsonl",
        "protocol.json",
        "cohort.json",
    ],
)
def test_frozen_source_and_longitudinal_proof_bytes_are_never_path_redacted(publication, path):
    original = b'{"diagnostic_path":"C:/Users/synthetic/example"}\n'
    assert publication.public_bytes(Path(path), original) == (original, [])


def test_unsigned_host_metadata_removes_only_unrelated_model_inventory(publication):
    original = json.dumps(
        {
            "requested_model": "gemma4:e4b",
            "digest": "a" * 64,
            "tags": {"models": [{"name": "gemma4:e4b", "digest": "a" * 64}, {"name": "other"}]},
        }
    ).encode()
    public, changes = publication.public_bytes(Path("model-manifest.json"), original)
    value = json.loads(public)
    assert value["tags"]["models"] == [{"name": "gemma4:e4b", "digest": "a" * 64}]
    assert value["digest"] == "a" * 64
    assert changes == [{"kind": "unrelated_installed_model_metadata", "count": 1}]
    assert json.loads(original)["tags"]["models"][-1]["name"] == "other"


def test_secret_dsn_in_proof_is_rejected_without_rewriting_original(publication):
    original = b'{"private_dsn":"postgresql+pg8000://user:secret@localhost/database"}'
    with pytest.raises(ValueError, match="private DSN"):
        publication.public_bytes(Path("world-E/calls.jsonl"), original)
    source = Path("source/examples/example.py")
    assert publication.public_bytes(source, original) == (original, [])


def test_actual_private_key_material_is_rejected_even_in_protected_source(publication):
    original = b"-----BEGIN PRIVATE KEY-----\nsynthetic-secret\n-----END PRIVATE KEY-----\n"
    with pytest.raises(ValueError, match="private key material"):
        publication.public_bytes(Path("source/example.py"), original)
