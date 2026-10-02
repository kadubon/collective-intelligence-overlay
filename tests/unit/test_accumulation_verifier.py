"""Original real smoke bytes and adverse edits; no network or inference in tests."""

import hashlib
import json
import shutil
import socket
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_gemma_accumulation import verify_run  # noqa: E402


@pytest.fixture
def original(tmp_path, monkeypatch):
    archive = ROOT / "tests/fixtures/accumulation-smoke-v4.zip"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == (
        "793c7f34f4f5cbac4a72d2fb32b926467e22dd53a36160cd6e126a8d2b3eb55d"
    )
    with zipfile.ZipFile(archive) as z:
        assert all(not Path(n).is_absolute() and ".." not in Path(n).parts for n in z.namelist())
        z.extractall(tmp_path)

    def blocked(*args, **kwargs):
        raise AssertionError("offline verification attempted a network operation")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    return tmp_path


def edit(path, operation):
    data = json.loads(path.read_bytes())
    operation(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def arm_path(root):
    return root / "world-fe00a32aa32aa020b99c-E"


def mutate_offer(root, operation):
    directory = arm_path(root)
    data = json.loads((directory / "arm-result.json").read_bytes())
    operation(data["offers"][0])
    (directory / "arm-result.json").write_text(json.dumps(data), encoding="utf-8")
    (directory / "offers/smoke-0/result.json").write_text(
        json.dumps(data["offers"][0]), encoding="utf-8"
    )
    edit(root / "cohort.json", lambda c: c["arms"].__setitem__(0, data))


def test_real_smoke_original_signatures_execution_raw_usage_and_failures_verify_offline(original):
    result = verify_run(original)
    assert result["verified"] and result["classification"] == "smoke"
    assert result["arms"][0]["offered"] == 2 and result["arms"][0]["passed"] == 0
    assert sum(v["charge"] for v in result["arms"][0]["model"].values()) == 2320
    assert result["network_or_inference_sent_by_verifier"] is False


@pytest.mark.parametrize(
    "target",
    [
        "result",
        "usage",
        "arm",
        "checkpoint",
        "snapshot",
        "seed",
        "mock",
        "options",
        "source",
        "CAS",
        "signed-record",
        "missing-failure",
        "duplicate-attempt",
        "hidden-answer",
    ],
)
def test_tampering_or_missing_failed_attempt_is_rejected(original, target):
    directory = arm_path(original)
    model = directory / "model/smoke-0-draft-0"
    if target == "result":
        mutate_offer(original, lambda o: o.__setitem__("succeeded", True))
    elif target == "usage":
        edit(model / "observation.json", lambda d: d.__setitem__("tokens_measured", 1))
    elif target == "arm":
        mutate_offer(original, lambda o: o.__setitem__("arm", "C"))
    elif target == "checkpoint":
        mutate_offer(original, lambda o: o.__setitem__("checkpoint", 3))
    elif target == "snapshot":
        edit(model / "parsed.json", lambda d: d.__setitem__("full_snapshot_digest", "0" * 64))
    elif target == "seed":
        mutate_offer(original, lambda o: o["attempts"][0].__setitem__("model_seed", 10))
    elif target == "mock":
        edit(model / "intent.json", lambda d: d.__setitem__("real_model", False))
    elif target == "options":
        edit(
            model / "request.json", lambda d: d["payload"]["options"].__setitem__("num_predict", 8)
        )
    elif target == "source":
        (original / "source/scripts/accumulation_tasks.py").write_text("changed", encoding="utf-8")
    elif target == "CAS":
        edit(
            directory / "verifier-artifacts.json",
            lambda d: d["original_bytes_base64"].__setitem__(
                next(iter(d["original_bytes_base64"])), "e30="
            ),
        )
    elif target == "signed-record":
        edit(directory / "producer-observations.json", lambda d: d["signed_records"].pop())
    elif target == "missing-failure":
        (model / "response.raw").unlink()
    elif target == "duplicate-attempt":
        shutil.copytree(model, directory / "model/undeclared-duplicate")
    elif target == "hidden-answer":
        edit(
            model / "request.json",
            lambda d: d["payload"]["messages"][0].__setitem__("content", "hidden expected answer"),
        )
    with pytest.raises((ValueError, KeyError, FileNotFoundError)):
        verify_run(original)


@pytest.mark.parametrize("name", ["intent.json", "request.json", "parsed.json", "observation.json"])
def test_missing_raw_chain_file_is_not_a_success(original, name):
    (arm_path(original) / "model/smoke-0-draft-0" / name).unlink()
    with pytest.raises(FileNotFoundError):
        verify_run(original)
