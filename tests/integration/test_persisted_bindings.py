import asyncio
import inspect
import json
import sys
from pathlib import Path

import pytest

from collective_intelligence_overlay.artifacts import Artifacts
from collective_intelligence_overlay.bindings import (
    ArtifactSpec,
    Binding,
    ExecutionContext,
    Registry,
    Target,
    callable_digest,
    fingerprint,
)
from collective_intelligence_overlay.models import Capability, Subject
from collective_intelligence_overlay.overlay import AdmissionDenied
from collective_intelligence_overlay.security import digest


def calibrated_factory(parameters):
    factor = parameters["factor"]

    async def transform(arguments):
        return {"value": arguments["value"] * factor}

    return transform


def installed(overlay, records, tmp_path, factor=3):
    artifacts = Artifacts(tmp_path / "artifacts")
    spec = ArtifactSpec(
        builder_id="calibrated",
        builder_version="1",
        builder_source=digest(inspect.getsource(calibrated_factory).encode()),
        parameters={"factor": factor},
        environment=records[0].scope.environment,
    )
    saved = spec.persist(artifacts)
    binding = Binding(
        binding_schema="2",
        artifact_digest=saved,
        id="calibrated",
        revision=str(factor),
        issuer="producer",
        registrar="receiver",
        subject=Subject(id="calibrated", version=str(factor), digest=saved),
        target=Target(
            kind="local",
            name="calibrated",
            implementation_identity="installed",
            interface_digest=callable_digest(calibrated_factory(spec.parameters)),
        ),
        scope=records[0].scope,
        callers=("receiver",),
        effects="read-only",
        input_schema={
            "type": "object",
            "required": ["value"],
            "properties": {"value": {"type": "integer"}},
        },
        output_schema={"type": "object"},
    )
    return binding, artifacts


def register(registry, binding, artifacts):
    registry.register_artifact(
        binding,
        artifacts,
        calibrated_factory,
        lambda args: True,
        builder_id="calibrated",
        builder_version="1",
    )


async def test_persisted_parameters_restart_and_changed_evidence(
    overlay, identities, records, tmp_path
):
    binding, artifacts = installed(overlay, records, tmp_path)
    registry = Registry(overlay)
    register(registry, binding, artifacts)
    candidate = Capability.model_validate(
        {
            **records[0].model_dump(),
            "schema_version": "2",
            "subject": binding.subject,
            "binding_digest": binding.digest,
        }
    )
    evidence = records[1].model_copy(
        update={
            "schema_version": "2",
            "subject": binding.subject,
            "binding_digest": binding.digest,
            "id": "calibration-check",
        }
    )
    for record in (candidate, evidence):
        overlay.store.put(identities[record.issuer].sign(record))
    context = ExecutionContext(caller="receiver", environment=binding.scope.environment)
    assert await registry.execute(binding.id, binding.digest, {"value": 7}, context) == {
        "value": 21
    }
    # Normal registration from the saved manifest restores the same identity/result.
    saved_binding = binding.model_dump_json()
    bundle = tmp_path / "restart.json"
    bundle.write_text(
        json.dumps(
            {
                "binding": json.loads(saved_binding),
                "artifacts": str(artifacts.directory),
                "database": overlay.store.engine.url.render_as_string(hide_password=False),
                "opa": overlay.policy.binary,
                "principals": {
                    name: {
                        "keyid": p.key.keyid,
                        "key": p.key.to_dict(),
                        "group": p.trust_group,
                        "methods": sorted(p.methods),
                    }
                    for name, p in overlay.store.principals.items()
                },
            }
        )
    )
    # A separate interpreter reads only the saved binding/artifact and installed
    # factory. It performs real PostgreSQL/OPA qualification before calling it.
    script = """
import asyncio, json, sys
from pathlib import Path
from securesystemslib.signer import Key
from collective_intelligence_overlay.security import Principal
from collective_intelligence_overlay.storage import Store
from collective_intelligence_overlay.policy import Policy, PolicySettings
from collective_intelligence_overlay.overlay import Overlay
from collective_intelligence_overlay.bindings import Binding, Registry, ExecutionContext
from collective_intelligence_overlay.artifacts import Artifacts
from test_persisted_bindings import register
data = json.loads(Path(sys.argv[1]).read_text())
principals = {name: Principal(Key.from_dict(p['keyid'], p['key']),
                             p['group'], frozenset(p['methods']))
              for name,p in data['principals'].items()}
store = Store(data['database'], 'receiver', principals)
overlay = Overlay(store, Policy(data['opa'], PolicySettings()))
for name in principals:
    overlay.observed(name)
binding = Binding.model_validate(data['binding'])
registry = Registry(overlay)
register(registry, binding, Artifacts(Path(data['artifacts'])))
try:
    result = asyncio.run(registry.execute(binding.id, binding.digest, {'value': 9},
        ExecutionContext(caller='receiver', environment=binding.scope.environment)))
    print(json.dumps({'digest': binding.digest, 'result': result}))
finally:
    store.close()
"""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        script,
        str(bundle),
        cwd=Path(__file__).parent,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), 30)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    assert process.returncode == 0, stderr.decode()
    assert json.loads(stdout) == {"digest": binding.digest, "result": {"value": 27}}
    restarted = Registry(overlay)
    restored = Binding.model_validate_json(saved_binding)
    register(restarted, restored, Artifacts(artifacts.directory))
    assert restored.digest == binding.digest
    assert await restarted.execute(restored.id, restored.digest, {"value": 8}, context) == {
        "value": 24
    }
    changed, _ = installed(overlay, records, tmp_path, factor=4)
    assert changed.target.interface_digest == binding.target.interface_digest
    assert changed.digest != binding.digest and changed.subject.digest != binding.subject.digest
    register(restarted, changed, artifacts)
    new_candidate = candidate.model_copy(
        update={"subject": changed.subject, "binding_digest": changed.digest}
    )
    overlay.store.put(identities["producer"].sign(new_candidate))
    with pytest.raises(AdmissionDenied):
        await restarted.execute(changed.id, changed.digest, {"value": 8}, context)


def test_artifact_identity_cannot_use_plain_registration_or_changed_factory(
    overlay, records, tmp_path
):
    binding, artifacts = installed(overlay, records, tmp_path)
    registry = Registry(overlay)
    with pytest.raises(ValueError, match="register_artifact"):
        registry.register_local(binding, calibrated_factory({"factor": 99}), lambda args: True)
    with pytest.raises(ValueError, match="builder"):
        registry.register_artifact(
            binding,
            artifacts,
            calibrated_factory,
            lambda args: True,
            builder_id="calibrated",
            builder_version="other",
        )
    with pytest.raises(ValueError, match="environment"):
        register(
            registry,
            binding.model_copy(
                update={
                    "scope": binding.scope.model_copy(
                        update={"environment": {"reference": "changed"}}
                    )
                }
            ),
            artifacts,
        )
    target = Path(artifacts.directory) / binding.artifact_digest
    target.write_bytes(b"tampered data")
    with pytest.raises(ValueError, match="digest mismatch"):
        register(registry, binding, artifacts)


def test_v1_binding_digest_preserves_pre_extension_identity(overlay, records, tmp_path):
    binding, _ = installed(overlay, records, tmp_path)
    legacy_wire = binding.model_dump(mode="json", exclude={"artifact_digest"})
    legacy_wire["binding_schema"] = "1"
    legacy = Binding.model_validate(legacy_wire)
    assert legacy.digest == fingerprint(legacy_wire)
    assert Binding.model_validate_json(legacy.model_dump_json()).digest == fingerprint(legacy_wire)
