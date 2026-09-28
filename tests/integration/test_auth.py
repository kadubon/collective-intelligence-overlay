from datetime import timedelta

import httpx
import jwt
from pydantic import SecretStr

from collective_intelligence_overlay.adapters.a2a import application
from collective_intelligence_overlay.config import Config, TrustedIdentity
from collective_intelligence_overlay.models import now


def test_extension_preserves_exact_json_numbers_through_protobuf():
    from google.protobuf.struct_pb2 import Value

    from collective_intelligence_overlay.adapters.a2a import extension_data, read_extension_data
    from collective_intelligence_overlay.bindings import fingerprint

    original = {"integer": 2**80 + 7, "schema": {"maximum": 4096}, "decimal": 1.0}
    restored = read_extension_data(Value.FromString(extension_data(original).SerializeToString()))
    assert restored == original
    assert fingerprint(restored) == fingerprint(original)
    assert isinstance(restored["schema"]["maximum"], int)


async def test_authentication_expiry_wrong_audience_and_size(identities, tmp_path):
    identity = identities["producer"]
    config = Config(
        owner="producer",
        database_url=SecretStr("unused"),
        private_key=tmp_path / "unused",
        artifact_directory=tmp_path,
        opa_binary="unused",
        url="http://127.0.0.1:1234/",
        local_development=True,
        identities={
            "producer": TrustedIdentity(
                keyid=identity.signer.public_key.keyid,
                key=identity.signer.public_key.to_dict(),
                trust_group="producer",
            )
        },
    )

    async def handler(caller, data):
        return {"caller": caller}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application(config, handler)), base_url=config.url
    ) as http:
        assert (await http.get("/.well-known/agent-card.json")).status_code == 400
        for audience, delta in ((config.url, -1), ("https://wrong.example/", 60)):
            token = jwt.encode(
                {
                    "iss": "producer",
                    "sub": "producer",
                    "aud": audience,
                    "iat": now() - timedelta(seconds=10),
                    "exp": now() + timedelta(seconds=delta),
                },
                identity.signer.private_bytes,
                algorithm="EdDSA",
            )
            response = await http.get(
                "/.well-known/agent-card.json", headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 400
        token = jwt.encode(
            {
                "iss": "producer",
                "sub": "producer",
                "aud": config.url,
                "iat": now(),
                "exp": now() + timedelta(seconds=60),
            },
            identity.signer.private_bytes,
            algorithm="EdDSA",
        )
        headers = {"Authorization": f"Bearer {token}"}
        assert (await http.get("/.well-known/agent-card.json", headers=headers)).status_code == 200
        response = await http.post("/", content=b"x" * 262145, headers=headers)
        assert response.status_code == 413
        assert token not in response.text
