import json

import pytest

from collective_intelligence_overlay.lifecycle_cli import _file


def test_material_depth_rejected_before_serialization(monkeypatch):
    from collective_intelligence_overlay.lifecycle import snapshot_from_material

    nested = 0
    for _ in range(65):
        nested = [nested]
    material = {"view_schema_version": "1", "context": nested, "records": []}

    def serialize(*args, **kwargs):
        raise AssertionError("tree bound must precede serialization")

    monkeypatch.setattr(json, "dumps", serialize)
    with pytest.raises(ValueError, match="depth bound"):
        snapshot_from_material(material, owner="receiver", caller="receiver")


def test_json_depth_rejected_before_decoder(tmp_path, monkeypatch):
    path = tmp_path / "deep.json"
    path.write_bytes(b"[" * 65 + b"0" + b"]" * 65)

    def decode(*args, **kwargs):
        raise AssertionError("depth bound must precede decoder")

    monkeypatch.setattr(json, "loads", decode)
    with pytest.raises(ValueError, match="depth bound"):
        _file(path)


def test_json_duplicate_keys_are_rejected(tmp_path):
    path = tmp_path / "ambiguous.json"
    path.write_text('{"owner":"receiver","owner":"another"}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        _file(path)


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity"])
def test_json_nonfinite_constants_are_rejected(tmp_path, number):
    path = tmp_path / "nonfinite.json"
    path.write_text('{"quantity":' + number + "}", encoding="utf-8")
    with pytest.raises(ValueError, match="nonfinite JSON"):
        _file(path)


def test_json_brackets_and_escaped_quotes_in_strings_are_not_nesting(tmp_path):
    value = {"text": '["' * 100 + "\\" + "]" * 100, "scope": {"tool": "1"}}
    path = tmp_path / "strings.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    assert _file(path) == value
