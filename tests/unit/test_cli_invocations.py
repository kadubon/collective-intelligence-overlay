import json
from types import SimpleNamespace

import pytest

from collective_intelligence_overlay import cli


@pytest.mark.parametrize(
    "command,state,code",
    [
        ("invoke", "completed", 0),
        ("invocation", "running", 3),
        ("invocation", "unknown", 2),
        ("invocation", None, 4),
        ("cancel-invocation", "cancelled", 0),
        ("invoke", "conflict", 2),
    ],
)
def test_cli_forwards_authenticated_invocation_operations(
    command, state, code, tmp_path, monkeypatch, capsys
):
    import collective_intelligence_overlay.adapters.a2a as a2a

    calls = []
    identity = object()
    config = SimpleNamespace(
        runtime=lambda: (identity, SimpleNamespace(store=SimpleNamespace(close=lambda: None)))
    )
    monkeypatch.setattr(cli, "load_config", lambda path: config)

    async def send(actual_config, actual_identity, peer, request):
        assert actual_config is config and actual_identity is identity
        calls.append((peer, request))
        item = {"state": state} if state else None
        return item if command == "invoke" else {"invocation": item}

    monkeypatch.setattr(a2a, "send", send)
    argv = [
        "cio",
        command,
        "--config",
        "owner.json",
        "--peer",
        "provider",
        "--invocation-id",
        "stable-42",
    ]
    if command == "invoke":
        path = tmp_path / "arguments.json"
        path.write_text(json.dumps({"text": "held-out input"}))
        argv += [
            "--binding-id",
            "words",
            "--binding-digest",
            "a" * 64,
            "--arguments-file",
            str(path),
        ]
    monkeypatch.setattr("sys.argv", argv)
    assert cli.main() == code
    assert json.loads(capsys.readouterr().out)
    peer, request = calls[0]
    assert peer == "provider"
    assert request["operation"] == command.replace("-", "_")
    assert request["invocation_id"] == "stable-42"
    assert "caller" not in request and "permissions" not in request
    if command == "invoke":
        assert request["arguments"] == {"text": "held-out input"}
        assert request["purpose"] == "reuse"


def test_json_argument_reader_bounds_input(tmp_path):
    path = tmp_path / "large.json"
    path.write_bytes(b" " * 65537)
    with pytest.raises(ValueError, match="byte bound"):
        cli._json_file(path)


def test_binding_check_reports_digest_without_registration(records, tmp_path, monkeypatch, capsys):
    from collective_intelligence_overlay.bindings import Binding, Target

    cap, _ = records
    binding = Binding(
        id="sample",
        revision="1",
        issuer="producer",
        registrar="receiver",
        subject=cap.subject,
        scope=cap.scope,
        target=Target(
            kind="local",
            name="installed",
            interface_digest="a" * 64,
            implementation_identity="installed",
        ),
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        callers=("receiver",),
        effects="read-only",
    )
    path = tmp_path / "binding.json"
    path.write_text(binding.model_dump_json())
    monkeypatch.setattr("sys.argv", ["cio", "binding-check", "--manifest", str(path)])
    assert cli.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["binding_digest"] == binding.digest
    assert result["registered"] is False
