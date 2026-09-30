import json
import os

import pytest

from collective_intelligence_overlay.config import Config, load_config
from collective_intelligence_overlay.setup import initialize, starter


def test_explicit_operator_pins_and_signer_need_no_runtime_database(tmp_path, monkeypatch):
    paths = [
        initialize(
            tmp_path / name,
            owner=name,
            url=f"https://{name}.example.test/",
            database_url="postgresql+pg8000://runtime@localhost/absent",
            opa="opa",
        )
        for name in ("owner", "operator")
    ]
    owner, operator = (load_config(path) for path in paths)
    data = owner.model_dump()
    data["identities"] = {**owner.identities, **operator.identities}
    data["operator_callers"] = ("operator",)
    config = Config.model_validate(data)
    assert owner.operators() == {"owner"}
    assert config.operators() == {"operator"}

    def database_forbidden(*args, **kwargs):
        pytest.fail("control signer loading opened the runtime database")

    monkeypatch.setattr("collective_intelligence_overlay.config.Store", database_forbidden)
    loaded = config.identity("operator", operator.private_key)
    assert loaded.name == "operator"
    assert loaded.signer.public_key.keyid == config.identities["operator"].keyid
    for callers in (("unknown",), ("operator", "operator")):
        with pytest.raises(ValueError, match="unique explicitly pinned"):
            Config.model_validate({**data, "operator_callers": callers})
    with pytest.raises(ValueError, match="not pinned"):
        config.identity("unknown", operator.private_key)
    with pytest.raises(ValueError, match="uncompromised caller pin"):
        config.identity("operator", owner.private_key)
    entry = config.identities["operator"]
    compromised = config.model_copy(
        update={
            "identities": {
                **config.identities,
                "operator": entry.model_copy(update={"compromised_keyids": (entry.keyid,)}),
            }
        }
    )
    with pytest.raises(ValueError, match="uncompromised caller pin"):
        compromised.identity("operator", operator.private_key)


def test_setup_separates_secret_and_resolves_paths_without_overwrite(tmp_path, monkeypatch):
    home = tmp_path / "owner home 文書"
    secret = "postgresql+pg8000://runtime:private-test-value@127.0.0.1/owner"
    config_path = initialize(
        home,
        owner="analyst",
        url="https://analyst.example.test/",
        database_url=secret,
        opa="opa",
        application="collective_intelligence_overlay.starter.application:configure",
    )
    public = config_path.read_text()
    identity = (home / "public-identity.json").read_text()
    assert "private-test-value" not in public + identity
    assert "database_url" not in json.loads(public)
    assert json.loads(public)["database_url_file"] == "secrets/database-url"
    monkeypatch.chdir(tmp_path)
    config = load_config(config_path)
    assert config.database_url.get_secret_value() == secret
    assert config.private_key == home / "identity.pem"
    assert config.artifact_directory == home / "artifacts"
    assert config.local_development is False
    assert config.identities.keys() == {"analyst"}
    assert "private-test-value" not in repr(config)
    bounded = config.model_copy(
        update={"artifact_capacity_bytes": 1048576, "artifact_max_files": 1}
    )
    cas = bounded.artifacts()
    original_object = cas.put(b"owner input")
    assert bounded.artifacts().put(b"owner input") == original_object
    with pytest.raises(ValueError, match="ARTIFACT_CAPACITY_EXCEEDED"):
        bounded.artifacts().put(b"different input")
    assert cas.get(original_object) == b"owner input"
    assert bounded.artifacts().usage()["capacity_bytes"] == 1048576
    if os.name != "nt":
        assert (home / "identity.pem").stat().st_mode & 0o777 == 0o600
        assert (home / "secrets/database-url").stat().st_mode & 0o777 == 0o600
    original = (home / "identity.pem").read_bytes()
    with pytest.raises(FileExistsError):
        initialize(home, owner="analyst", url=config.url, database_url=secret, opa="opa")
    assert (home / "identity.pem").read_bytes() == original


@pytest.mark.parametrize(
    "url,dsn",
    [
        ("http://127.0.0.1:8000/", "postgresql+pg8000://runtime@localhost/db"),
        ("https://peer.example/", "sqlite:///db"),
    ],
)
def test_invalid_setup_does_not_create_directory(tmp_path, url, dsn):
    home = tmp_path / "invalid"
    with pytest.raises(ValueError):
        initialize(home, owner="owner", url=url, database_url=dsn, opa="opa")
    assert not home.exists()


def test_installed_starter_is_inert_and_exclusive(tmp_path):
    home = tmp_path / "starter"
    report = starter(home)
    assert report["registered"] is False
    assert set(report["files"]) == {"application.py", "Caddyfile", "README.txt"}
    assert "verify=False" not in (home / "application.py").read_text()
    assert "tls {$CIO_TLS_CERTIFICATE}" in (home / "Caddyfile").read_text()
    with pytest.raises(FileExistsError):
        starter(home)


def test_ambiguous_secret_source_is_rejected(tmp_path):
    config_path = initialize(
        tmp_path / "owner",
        owner="owner",
        url="https://peer.example/",
        database_url="postgresql+pg8000://runtime@localhost/db",
        opa="opa",
    )
    data = json.loads(config_path.read_text())
    data["database_url"] = "postgresql+pg8000://another@localhost/db"
    config_path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="ambiguous"):
        load_config(config_path)
