import pytest
from pydantic import SecretStr

from collective_intelligence_overlay.config import Config, TrustedIdentity


@pytest.fixture
def app_config(store, identities, policy, tmp_path):
    key = tmp_path / "identity.pem"
    key.write_bytes(identities["receiver"].signer.private_bytes)
    return Config(
        owner="receiver",
        database_url=SecretStr(store.engine.url.render_as_string(hide_password=False)),
        private_key=key,
        artifact_directory=tmp_path / "artifacts",
        opa_binary=policy.binary,
        url="https://receiver.example.test/",
        application="collective_intelligence_overlay.starter.application:configure",
        identities={
            name: TrustedIdentity(
                keyid=identity.signer.public_key.keyid,
                key=identity.signer.public_key.to_dict(),
                trust_group=name,
            )
            for name, identity in identities.items()
        },
    )
