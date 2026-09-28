import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from securesystemslib.signer import CryptoSigner
from sqlalchemy import create_engine, text

from collective_intelligence_overlay.models import Capability, Evidence, Scope, Subject, now
from collective_intelligence_overlay.overlay import Overlay
from collective_intelligence_overlay.policy import Policy, PolicySettings
from collective_intelligence_overlay.security import Identity, Principal, digest
from collective_intelligence_overlay.storage import Store, migrate


@pytest.fixture
def identities():
    return {
        name: Identity(name, CryptoSigner.generate_ed25519())
        for name in ("producer", "verifier", "receiver", "other")
    }


@pytest.fixture
def principals(identities):
    return {
        name: Principal(identity.signer.public_key, name, frozenset({"csv-check", "report-check"}))
        for name, identity in identities.items()
    }


@pytest.fixture
def unmigrated_store(principals):
    url = os.environ.get("CIO_TEST_DATABASE_URL")
    if not url:
        pytest.skip("CIO_TEST_DATABASE_URL required: real PostgreSQL tests not run")
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    db = "cio_test_" + uuid4().hex
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db}"'))
    store = Store(url.rsplit("/", 1)[0] + "/" + db, "receiver", principals)
    yield store
    store.close()
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE "{db}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture
def store(unmigrated_store):
    migrate(unmigrated_store.engine)
    return unmigrated_store


@pytest.fixture
def policy():
    binary = os.environ.get("CIO_OPA")
    if not binary:
        candidate = Path(".local/bin/opa_windows_amd64.exe")
        if candidate.exists():
            binary = str(candidate.resolve())
        else:
            pytest.skip("CIO_OPA required: real policy engine tests not run")
    return Policy(binary, PolicySettings())


@pytest.fixture
def records():
    scope = Scope(
        task="csv-sum",
        input_contract="csv.amount.v1",
        output_contract="sum.v1",
        environment={"reference": "1"},
    )
    subject = Subject(id="csv-sum", version="1", digest=digest(b"registered local csv-sum v1"))
    cap = Capability(
        subject=subject,
        issuer="producer",
        scope=scope,
        entrypoint="csv-sum",
        claim="conserves-total",
        license="Apache-2.0",
        provenance="local reference",
        classification="declared-new",
        expires_at=now() + timedelta(hours=1),
    )
    evidence = Evidence(
        subject=subject,
        issuer="verifier",
        scope=scope,
        claim=cap.claim,
        receivers=("receiver",),
        verdict="PASS",
        method="csv-check",
        verifier_version="1",
        artifact_digest=digest(b"checked"),
        expires_at=now() + timedelta(hours=1),
    )
    return cap, evidence


@pytest.fixture
def overlay(store, policy, identities, records):
    for record in records:
        store.put(identities[record.issuer].sign(record))
    overlay = Overlay(store, policy)
    overlay.observed("producer")
    overlay.observed("verifier")
    return overlay
