"""Cross-interpreter test host; only installed CIO APIs perform business operations."""

import argparse
import asyncio
import base64
import inspect
import json
import os
import platform
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import jwt
import uvicorn
from remote_call_application import (
    capability,
    checked,
    context,
    provider_binding,
    proxy_binding,
    register_consumer,
    register_provider,
)
from securesystemslib.signer import Key
from sqlalchemy import text
from test_persisted_bindings import calibrated_factory

import collective_intelligence_overlay as package
from collective_intelligence_overlay.adapters.a2a import application, send
from collective_intelligence_overlay.artifacts import Artifacts
from collective_intelligence_overlay.bindings import (
    ArtifactSpec,
    Binding,
    Registry,
    Target,
    callable_digest,
    fingerprint,
)
from collective_intelligence_overlay.calls import call_instance
from collective_intelligence_overlay.config import load_config
from collective_intelligence_overlay.invocations import invocation_request
from collective_intelligence_overlay.models import Subject, now
from collective_intelligence_overlay.peer import PeerService
from collective_intelligence_overlay.security import Principal, digest, record_adapter, verify


def runtime():
    assert Path(package.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()), (
        "mixed peer imported checkout source"
    )
    return {
        "version": sys.version,
        "patch": platform.python_version(),
        "executable": sys.executable,
        "os": platform.system(),
        "import": package.__file__,
    }


def legacy():
    fixture = json.loads((Path(__file__).parents[1] / "fixtures/v030_database.json").read_text())
    principals = {
        name: Principal(
            Key.from_dict(item["keyid"], item["key"]),
            item["trust_group"],
            frozenset(item["methods"]),
        )
        for name, item in fixture["principals"].items()
    }
    envelopes = [row["envelope"] for row in fixture["tables"]["records"]]
    hashes = []
    versions = set()
    for envelope in envelopes:
        raw = base64.b64decode(envelope["payload"])
        record = verify(envelope, principals)
        assert base64.b64decode(envelope["payload"]) == raw
        versions.add(record.schema_version)
        hashes.append(digest(raw))
    assert versions == {"1", "2", "3"}
    golden = json.loads(
        (Path(__file__).parents[1] / "fixtures/python_compatibility.json").read_text()
    )
    assert hashes == golden["legacy_payloads"], "original 0.3.0 signed bytes changed"
    return envelopes, hashes


def fixed(config):
    binding = provider_binding()
    arguments = {
        "large": 2**80 + 1,
        "decimal": "12.3400",
        "unicode": "日本語😀e\u0301",
        "time": "2026-09-30T00:00:00+09:00",
        "null": None,
        "ordered": [3, 1, 2],
    }
    request = invocation_request("receiver", binding.id, binding.digest, arguments, context(config))
    assert fingerprint(arguments) == fingerprint(dict(reversed(list(arguments.items()))))
    assert fingerprint(arguments) != fingerprint({**arguments, "ordered": [1, 2, 3]})
    try:
        fingerprint({"decimal": Decimal("12.3400")})
    except TypeError:
        pass
    else:
        raise AssertionError("raw Decimal must not silently redefine the JSON hash contract")
    spec = ArtifactSpec(
        builder_id="calibrated",
        builder_version="1",
        builder_source=digest(inspect.getsource(calibrated_factory).encode()),
        parameters={"factor": 3},
        environment={"application": "1"},
    )
    instance = call_instance("receiver", "fixed-call", "fixed-session", None, request)
    values = {
        "binding": binding.digest,
        "request": fingerprint(request),
        "call": instance.key,
        "manifest": digest(spec.model_dump_json().encode()),
        "json": fingerprint(arguments),
        "raw_decimal": "rejected",
    }
    golden = json.loads(
        (Path(__file__).parents[1] / "fixtures/python_compatibility.json").read_text()
    )
    assert values == golden["fixed"], "fixed cross-version hash contract changed"
    return values


def artifact_binding(artifacts):
    spec = ArtifactSpec(
        builder_id="calibrated",
        builder_version="1",
        builder_source=digest(inspect.getsource(calibrated_factory).encode()),
        parameters={"factor": 3},
        environment={"application": "1"},
    )
    saved = spec.persist(artifacts)
    source = callable_digest(calibrated_factory(spec.parameters))
    return provider_binding().model_copy(
        update={
            "binding_schema": "2",
            "artifact_digest": saved,
            "id": "calibrated",
            "registrar": "receiver",
            "subject": Subject(id="calibrated", version="3", digest=saved),
            "target": Target(
                kind="local",
                name="calibrated",
                interface_digest=source,
                implementation_identity="installed",
            ),
            "output_schema": {"type": "object"},
        }
    )


def snapshot(root, output):
    config = load_config(root / "receiver/config.json")
    envelopes, old_hashes = legacy()
    signed = []
    for envelope in envelopes:
        record = record_adapter.validate_json(base64.b64decode(envelope["payload"]))
        owner = load_config(root / record.issuer / "config.json")
        identity, overlay = owner.runtime()
        try:
            signed.append(identity.sign(record))
        finally:
            overlay.store.close()
    output.write_text(
        json.dumps(
            {
                "runtime": runtime(),
                "fixed": fixed(config),
                "legacy_payloads": old_hashes,
                "signed": signed,
            }
        ),
        encoding="utf-8",
    )


def seed(root, output):
    configs = {
        name: load_config(root / name / "config.json")
        for name in ("producer", "verifier", "receiver")
    }
    runtimes = {name: config.runtime() for name, config in configs.items()}
    try:
        provider = provider_binding()
        proxy = proxy_binding(configs["receiver"])
        saved = artifact_binding(Artifacts(root / "saved-artifacts"))
        (root / "artifact-binding.json").write_text(saved.model_dump_json(), encoding="utf-8")
        for binding in (provider, proxy, saved):
            identity, overlay = runtimes[binding.issuer]
            overlay.store.put(identity.sign(capability(binding)))
            verifier, verifier_overlay = runtimes["verifier"]
            verifier_overlay.store.put(verifier.sign(checked(binding)))
        with runtimes["producer"][1].store.engine.begin() as conn:
            conn.execute(
                text("CREATE TABLE test_call_witness (id integer PRIMARY KEY, count integer)")
            )
            conn.execute(text("INSERT INTO test_call_witness VALUES (1, 0)"))
        with runtimes["receiver"][1].store.engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE test_python_values "
                    "(amount numeric(24,9), observed timestamptz, payload json)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO test_python_values "
                    "VALUES (:amount, :observed, CAST(:payload AS json))"
                ),
                {
                    "amount": Decimal("12.3400"),
                    "observed": datetime(2026, 9, 29, 15, tzinfo=UTC),
                    "payload": json.dumps({"large": 2**80 + 1, "text": "日本語😀", "null": None}),
                },
            )
        output.write_text(
            json.dumps(
                {"runtime": runtime(), "binding": saved.digest, "manifest": saved.artifact_digest}
            ),
            encoding="utf-8",
        )
    finally:
        for _, overlay in runtimes.values():
            overlay.store.close()


async def verify_saved(root, other, output):
    config = load_config(root / "receiver/config.json")
    _, overlay = config.runtime()
    try:
        original = json.loads(other.read_text(encoding="utf-8"))
        _, old_hashes = legacy()
        assert original["fixed"] == fixed(config)
        assert original["legacy_payloads"] == old_hashes
        for envelope in original["signed"]:
            verify(envelope, overlay.store.principals)
        binding = Binding.model_validate_json((root / "artifact-binding.json").read_bytes())
        registry = Registry(overlay)
        registry.register_artifact(
            binding,
            Artifacts(root / "saved-artifacts"),
            calibrated_factory,
            lambda _: True,
            builder_id="calibrated",
            builder_version="1",
        )
        assert await registry.execute(
            binding.id, binding.digest, {"value": 9}, context(config)
        ) == {"value": 27}
        # Real pg8000/SQLAlchemy Numeric, aware timestamp and JSON round trips;
        # the writer and reader here deliberately use different interpreters.
        with overlay.store.engine.connect() as conn:
            row = conn.execute(
                text("SELECT amount, observed, payload FROM test_python_values")
            ).one()
            assert row.amount == Decimal("12.340000000")
            assert row.observed == datetime(2026, 9, 29, 15, tzinfo=UTC)
            assert row.payload == {"large": 2**80 + 1, "text": "日本語😀", "null": None}
        output.write_text(
            json.dumps(
                {
                    "runtime": runtime(),
                    "fixed": fixed(config),
                    "legacy_payloads": old_hashes,
                    "signed_records": len(original["signed"]),
                    "artifact_result": {"value": 27},
                    "database": "passed",
                }
            ),
            encoding="utf-8",
        )
    finally:
        overlay.store.close()


async def wait_ready(config, identity):
    timestamp = now()
    token = jwt.encode(
        {
            "iss": identity.name,
            "sub": identity.name,
            "aud": config.url,
            "iat": timestamp,
            "exp": timestamp.timestamp() + 60,
        },
        identity.signer.private_bytes,
        algorithm="EdDSA",
    )
    async with httpx.AsyncClient(
        trust_env=False, headers={"Authorization": "Bearer " + token}
    ) as http:
        for _ in range(200):
            try:
                response = await http.get(config.url + ".well-known/agent-card.json")
                assert response.status_code == 200
                return
            except httpx.ConnectError:
                await asyncio.sleep(0.05)
    raise AssertionError("mixed interpreter peer not ready")


async def exercise(root, output):
    configs = {
        name: load_config(root / name / "config.json")
        for name in ("producer", "verifier", "receiver")
    }
    config = configs["receiver"]
    identity, registry, proxy = register_consumer(config)
    producer_identity, producer_overlay = configs["producer"].runtime()
    try:
        for item in configs.values():
            await wait_ready(item, identity)
        # Every support used by runtime admission arrives through actual A2A HTTP.
        await send(
            configs["producer"],
            producer_identity,
            "producer",
            {"operation": "sync", "peer": "verifier"},
        )
        await send(config, identity, "receiver", {"operation": "sync", "peer": "producer"})
        await send(config, identity, "receiver", {"operation": "sync", "peer": "verifier"})
        first = await registry.execute(
            proxy.id,
            proxy.digest,
            {"value": 7},
            context(config),
            call_id="first",
            call_scope="mixed-session",
        )
        second = await registry.execute(
            proxy.id,
            proxy.digest,
            {"value": 7},
            context(config),
            call_id="second",
            call_scope="mixed-session",
        )
        retry = await registry.execute(
            proxy.id,
            proxy.digest,
            {"value": 7},
            context(config),
            call_id="first",
            call_scope="mixed-session",
        )
        assert (first, second, retry) == (1, 2, 1)
        refs = registry.remote_calls(context(config), call_scope="mixed-session")
        queried = [
            await registry.query_remote_call(ref.call_key, context(config), config, identity)
            for ref in refs
        ]
        assert sorted(item["result"] for item in queried) == [1, 2]
        assert all(item["state"] == "completed" for item in queried)
        revoked = await send(
            configs["producer"],
            producer_identity,
            "producer",
            {
                "operation": "revoke",
                "subject": provider_binding().subject.model_dump(mode="json"),
                "reason": "cross-Python withdrawal",
            },
        )
        assert revoked["envelope"]["payload"]
        await send(config, identity, "receiver", {"operation": "sync", "peer": "producer"})
        with producer_overlay.store.engine.connect() as conn:
            assert conn.execute(text("SELECT count FROM test_call_witness")).scalar_one() == 2
        denied = await send(
            config,
            identity,
            "producer",
            {
                "operation": "invoke",
                "invocation_id": "after-revoke",
                "binding_id": provider_binding().id,
                "binding_digest": provider_binding().digest,
                "arguments": {"value": 7},
            },
        )
        assert denied["state"] == "unknown" and denied["reason"] == "admission_denied", denied
        assert denied["phase"] == "reserved" and denied["reservation_state"] == "released"
        with producer_overlay.store.engine.connect() as conn:
            assert conn.execute(text("SELECT count FROM test_call_witness")).scalar_one() == 2
        output.write_text(
            json.dumps(
                {
                    "runtime": runtime(),
                    "results": [first, second, retry],
                    "remote_ids": [ref.remote_invocation_id for ref in refs],
                    "queries": len(queried),
                    "revocation": denied["reason"],
                }
            ),
            encoding="utf-8",
        )
    finally:
        registry.overlay.store.close()
        producer_overlay.store.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("seed", "snapshot", "verify", "peer", "exercise"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--owner")
    parser.add_argument("--other", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    observed = runtime()
    assert observed["patch"] == os.environ["CIO_INTEROP_PATCH"], "mixed child interpreter mismatch"
    if args.mode == "seed":
        seed(args.root, args.output)
    elif args.mode == "snapshot":
        snapshot(args.root, args.output)
    elif args.mode == "verify":
        asyncio.run(verify_saved(args.root, args.other, args.output))
    elif args.mode == "exercise":
        asyncio.run(exercise(args.root, args.output))
    else:
        config = load_config(args.root / args.owner / "config.json")
        service = PeerService(config, register_provider if args.owner == "producer" else None)
        args.output.write_text(json.dumps(observed), encoding="utf-8")
        try:
            uvicorn.run(
                application(config, service.handle),
                host="127.0.0.1",
                port=urlsplit(config.url).port,
                log_level="critical",
                access_log=False,
            )
        finally:
            service.overlay.store.close()


if __name__ == "__main__":
    main()
