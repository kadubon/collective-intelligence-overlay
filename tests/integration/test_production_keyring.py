from dataclasses import replace

import httpx
import jwt
from securesystemslib.exceptions import VerificationError
from securesystemslib.signer import CryptoSigner

from collective_intelligence_overlay.adapters.a2a import application
from collective_intelligence_overlay.config import TrustedIdentity
from collective_intelligence_overlay.models import UseRequest
from collective_intelligence_overlay.security import Identity, Principal, verify
from collective_intelligence_overlay.storage import Conflict


async def test_routine_and_compromised_history_current_http_authority(
    app_config, store, identities, records, policy
):
    from datetime import timedelta

    import pytest

    from collective_intelligence_overlay.models import now
    from collective_intelligence_overlay.overlay import Overlay

    cap, evidence = records
    old = identities["producer"]
    new = Identity("producer", CryptoSigner.generate_ed25519())
    old_envelope = old.sign(cap)
    store.put(old_envelope)
    store.put(identities["verifier"].sign(evidence))
    replacement = Principal(
        new.signer.public_key, "producer", historical_keys=(old.signer.public_key,)
    )
    store.principals["producer"] = replacement
    assert verify(old_envelope, store.principals) == cap
    overlay = Overlay(store, policy)
    overlay.observed("producer")
    overlay.observed("verifier")
    request = UseRequest(
        receiver="receiver", subject=cap.subject, scope=cap.scope, semantic_fit="confirmed"
    )
    assert (await overlay.qualify(request)).outcome == "ACCEPT"
    entry = TrustedIdentity(
        keyid=new.signer.public_key.keyid,
        key=new.signer.public_key.to_dict(),
        trust_group="producer",
        historical_keys={old.signer.public_key.keyid: old.signer.public_key.to_dict()},
    )
    config = app_config.model_copy(
        update={"identities": {**app_config.identities, "producer": entry}}
    )
    called = []

    async def handler(caller, data):
        called.append(caller)
        return {}

    app = application(config, handler)
    timestamp = now()
    claims = {
        "iss": "producer",
        "sub": "producer",
        "aud": config.url,
        "iat": timestamp,
        "exp": timestamp + timedelta(seconds=60),
    }
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url=config.url) as client:
        for identity, expected in ((old, 400), (new, 200)):
            token = jwt.encode(
                claims,
                identity.signer.private_bytes,
                algorithm="EdDSA",
                headers={"kid": identity.signer.public_key.keyid},
            )
            response = await client.get(
                ".well-known/agent-card.json", headers={"Authorization": "Bearer " + token}
            )
            assert response.status_code == expected
    store.principals["producer"] = replace(
        replacement, compromised_keyids=frozenset({old.signer.public_key.keyid})
    )
    # A backdated claim cannot convert a compromised origin into current authority.
    assert verify(old_envelope, store.principals, require_authority=False) == cap
    assert store.capabilities() == [cap]
    with pytest.raises(VerificationError):
        store.put(old_envelope)
    assert (await overlay.qualify(request)).outcome == "UNKNOWN"
    ref = store.reference("capability", "producer", cap.subject.key)
    assert store.signed_record(ref) == old_envelope
    # Unknown keys never become pins, and rotation never replaces saved record bytes.
    with pytest.raises(VerificationError):
        verify(Identity("producer", CryptoSigner.generate_ed25519()).sign(cap), store.principals)
    changed = cap.model_copy(update={"claim": "forged-replacement"})
    with pytest.raises(Conflict):
        store.put(new.sign(changed))


def test_offline_rotation_bundle_preserves_original_key_state_and_requires_peer_updates(
    app_config, tmp_path
):
    import pytest

    from collective_intelligence_overlay.application import load_application
    from collective_intelligence_overlay.config import load_config
    from collective_intelligence_overlay.operations import OwnerAlreadyRunning
    from collective_intelligence_overlay.setup import rotate_key

    original_key = app_config.private_key.read_bytes()
    host = load_application(app_config)
    candidate = host.overlay.store.capabilities()[0]
    old_keyid = app_config.identities[app_config.owner].keyid
    bundle = tmp_path / "rotated-key"
    try:
        with pytest.raises(OwnerAlreadyRunning):
            rotate_key(app_config, bundle)
        assert not bundle.exists()
    finally:
        host.close()
    result = rotate_key(app_config, bundle, compromised=(old_keyid,))
    config = load_config(bundle / "config.json")
    assert result["peer_trust_updated"] is False
    assert result["current_keyid"] != old_keyid
    assert old_keyid in config.identities[config.owner].historical_keys
    assert old_keyid in config.identities[config.owner].compromised_keyids
    assert app_config.private_key.read_bytes() == original_key
    identity, overlay = config.runtime()
    try:
        assert identity.signer.public_key.keyid == result["current_keyid"]
        assert overlay.store.capabilities() == [candidate]
        reference = overlay.store.reference("capability", config.owner, candidate.subject.key)
        assert (
            verify(
                overlay.store.signed_record(reference),
                overlay.store.principals,
                require_authority=False,
            )
            == candidate
        )
    finally:
        overlay.store.close()
    with pytest.raises(FileExistsError):
        rotate_key(app_config, bundle)
