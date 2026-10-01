"""Actual offline key bundles, current HTTPS authority and retained DSSE history."""

import asyncio
import json
import subprocess
import sys
from datetime import timedelta

import httpx
import jwt
from document_recovery_protocol import originals

from collective_intelligence_overlay.adapters.a2a import send
from collective_intelligence_overlay.bindings import Binding
from collective_intelligence_overlay.config import load_config
from collective_intelligence_overlay.models import now


async def run(configs, identities, mesh, start, stop, call, sync, target, root):
    target = Binding.model_validate(target)
    request = {
        "receiver": "receiver",
        "capability_issuer": target.issuer,
        "subject": target.subject.model_dump(mode="json"),
        "scope": target.scope.model_dump(mode="json"),
        "binding_digest": target.digest,
        "semantic_fit": "confirmed",
    }
    assert (await call("receiver", operation="qualify", request=request))["decision"][
        "outcome"
    ] == "ACCEPT"
    before = {
        owner: await asyncio.to_thread(originals, config) for owner, config in configs.items()
    }
    effects = mesh.mcp_audit.read_bytes()
    old_identity = identities["producer"]
    old_keyid = configs["producer"].identities["producer"].keyid
    old_path = configs["producer"].private_key
    old_private_bytes = old_path.read_bytes()
    retained = next(
        envelope
        for (kind, issuer, _), envelope in before["producer"][0].items()
        if kind == "capability" and issuer == "producer"
    )
    observations = []

    async def rotate(label, compromised=False):
        for owner in configs:
            await stop(owner)
        original = configs["producer"]
        directory = root / ("producer-rotation-" + label)
        command = [
            sys.executable,
            "-m",
            "collective_intelligence_overlay.cli",
            "key-rotate",
            "--config",
            str(original.private_key.parent / "config.json"),
            "--directory",
            str(directory),
        ]
        if compromised:
            command += ["--compromised-key-id", old_keyid]
        result = await asyncio.to_thread(
            subprocess.run,
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        bundle = json.loads(result.stdout)
        assert bundle["peer_trust_updated"] is False
        rotated = load_config(directory / "config.json")
        current = rotated.identities["producer"]
        assert current.keyid != original.identities["producer"].keyid
        assert old_keyid in current.historical_keys
        assert (old_keyid in current.compromised_keyids) == compromised
        configs["producer"] = rotated
        for owner, config in tuple(configs.items()):
            configs[owner] = config.model_copy(
                update={"identities": {**config.identities, "producer": current}}
            )
            path = configs[owner].private_key.parent / "config.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["identities"]["producer"] = current.model_dump(mode="json")
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        identity, overlay = configs["producer"].runtime()
        identities["producer"] = identity
        overlay.store.close()
        for owner in configs:
            await start(owner)
        assert old_path.read_bytes() == old_private_bytes
        await sync("receiver", "producer")
        return bundle

    async def old_http_refused():
        config = configs["receiver"]
        timestamp = now()
        token = jwt.encode(
            {
                "iss": "producer",
                "sub": "producer",
                "aud": config.url,
                "iat": timestamp,
                "exp": timestamp + timedelta(seconds=60),
            },
            old_identity.signer.private_bytes,
            algorithm="EdDSA",
            headers={"kid": old_keyid},
        )
        async with httpx.AsyncClient(
            verify=config.tls_context(), trust_env=False, timeout=5
        ) as http:
            response = await http.get(
                config.url + ".well-known/agent-card.json",
                headers={"Authorization": "Bearer " + token},
            )
        assert response.status_code == 400
        assert (await call("producer", operation="status"))["state"] == "ready"
        return response.status_code

    async def preserved():
        for owner, config in configs.items():
            after = await asyncio.to_thread(originals, config)
            assert all(after[0][key] == envelope for key, envelope in before[owner][0].items())
            assert after[1] == before[owner][1]
        assert mesh.mcp_audit.read_bytes() == effects

    routine = await rotate("routine")
    assert (await call("receiver", operation="qualify", request=request))["decision"][
        "outcome"
    ] == "ACCEPT"
    assert await old_http_refused() == 400
    await preserved()
    observations.append(
        {
            "injection": "routine key rotation",
            "bundle": routine,
            "old_http_status": 400,
            "historical_admission": "ACCEPT",
        }
    )
    (root / "key-observations.json").write_text(
        json.dumps(observations, indent=2), encoding="utf-8"
    )

    compromised = await rotate("compromised", compromised=True)
    decision = (await call("receiver", operation="qualify", request=request))["decision"]
    assert decision["outcome"] == "UNKNOWN"
    assert await old_http_refused() == 400
    # Authenticate with the new current key while submitting the old, genuinely
    # signed payload. Known compromised origin must still be rejected.
    try:
        await send(
            configs["producer"],
            identities["producer"],
            "receiver",
            {"operation": "submit", "envelope": retained},
        )
    except Exception as error:
        assert type(error).__name__ == "InternalError"
    else:
        raise AssertionError("compromised historical DSSE accepted as current authority")
    await preserved()
    observations.append(
        {
            "injection": "compromised historical key",
            "bundle": compromised,
            "old_http_status": 400,
            "decision": decision,
            "historical_payload_retained": True,
            "current_authenticated_submit_refused": True,
        }
    )
    (root / "key-observations.json").write_text(
        json.dumps(observations, indent=2), encoding="utf-8"
    )
