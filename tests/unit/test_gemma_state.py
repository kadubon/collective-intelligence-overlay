"""Actual completed negative trajectories and independent cognitive-state edits.

These are state-reader fixtures, not substitutes for the separate full original
DSSE/CAS/raw-response checks. No model or network is invoked by this reader.
"""

import copy
import hashlib
import json
import socket
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from check_gemma_state import check_state_files, reconstruct_states  # noqa: E402


def read(path):
    return json.loads(path.read_bytes())


@pytest.fixture
def original(tmp_path, monkeypatch):
    archive = ROOT / "tests/fixtures/accumulation-state-v2-first-world.zip"
    manifest = read(archive.with_suffix(".json"))
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == (
        "ff1e744eb606fce42b46a5ea4cf83b2810942de792e45aae060ef275d3cb54d8"
    )
    with zipfile.ZipFile(archive) as source:
        assert set(source.namelist()) == set(manifest["original_file_sha256"])
        for name, digest in manifest["original_file_sha256"].items():
            assert not Path(name).is_absolute() and ".." not in Path(name).parts
            assert hashlib.sha256(source.read(name)).hexdigest() == digest
        source.extractall(tmp_path)

    def blocked(*args, **kwargs):
        raise AssertionError("state reconstruction attempted network access")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    return tmp_path, read(tmp_path / "protocol.json")


def data(original, arm="M"):
    directory = original[0] / ("world-e72d6fd2bb3903cd1cf8-" + arm)
    return directory, read(directory / "arm-result.json"), original[1]


@pytest.mark.parametrize(("arm", "offered"), [("E", 38), ("M", 51)])
def test_real_ordered_failure_trajectories_reconstruct_exact_original_states(
    original, arm, offered
):
    directory, summary, protocol = data(original, arm)
    states = reconstruct_states(summary, protocol)
    check_state_files(directory, states, read)
    assert len(states["offers"]) == offered
    assert set(states["checkpoints"]) == {"0", "3", "6"}
    assert not states["final"].skills
    assert summary["placebo_matching"]["nonempty"] is False


@pytest.mark.parametrize(
    "target",
    [
        "offer_order",
        "learning_permission",
        "snapshot_digest",
        "missing_checkpoint",
        "changed_transition",
        "false_matching",
        "missing_failed_offer",
        "extra_receiver_qualification",
        "world_seed",
        "changed_contract",
        "evaluation_as_training",
        "different_arm",
    ],
)
def test_changed_state_history_cannot_be_self_authenticated(original, target):
    _directory, saved, protocol = data(original)
    summary = copy.deepcopy(saved)
    training = next(o for o in summary["offers"] if o["phase"] == "training")
    if target == "offer_order":
        summary["offers"][0], summary["offers"][1] = summary["offers"][1], summary["offers"][0]
    elif target == "learning_permission":
        training["learn"] = False
    elif target == "snapshot_digest":
        training["snapshot_digest"] = "0" * 64
    elif target == "missing_checkpoint":
        summary["snapshots"].pop("3")
    elif target == "changed_transition":
        training["stock_digest_after"] = training["snapshot_digest"]
    elif target == "false_matching":
        summary["placebo_matching"]["nonempty"] = True
    elif target == "missing_failed_offer":
        summary["offers"].remove(training)
    elif target == "extra_receiver_qualification":
        summary["qualification"].append({"id": "qualify-0", "succeeded": True})
    elif target == "world_seed":
        summary["seed"] += 1
    elif target == "changed_contract":
        training["problem"]["contract"] = "another-business"
    elif target == "evaluation_as_training":
        summary["offers"][0]["learn"] = True
    elif target == "different_arm":
        training["arm"] = "C"
    with pytest.raises(ValueError):
        reconstruct_states(summary, protocol)


@pytest.mark.parametrize(
    "name",
    [
        "initial-stock.json",
        "final-stock.json",
        "irrelevant-stock.json",
        "new-receiver-stock.json",
        "snapshot-0.json",
        "snapshot-3.json",
        "snapshot-6.json",
    ],
)
def test_missing_immutable_state_is_not_a_valid_empty_state(original, name):
    directory, summary, protocol = data(original)
    states = reconstruct_states(summary, protocol)
    (directory / name).unlink()
    with pytest.raises(FileNotFoundError):
        check_state_files(directory, states, read)


def test_replaced_final_state_file_is_not_accepted_from_its_own_digest(original):
    directory, summary, protocol = data(original)
    states = reconstruct_states(summary, protocol)
    changed = read(directory / "final-stock.json")
    changed["checkpoint"] = 3
    (directory / "final-stock.json").write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="immutable stock"):
        check_state_files(directory, states, read)
