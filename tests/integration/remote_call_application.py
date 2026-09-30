"""Trusted test host, also executed in separate provider/caller processes.

The counter is a persistent test witness for sampling calls, not a declared business
effect. All invocation state, idempotency, authentication and results use real CIO.
"""

import argparse
import asyncio
import json
import platform
import sys
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
from sqlalchemy import text

from collective_intelligence_overlay.adapters.a2a import application
from collective_intelligence_overlay.bindings import (
    Binding,
    ExecutionContext,
    Registry,
    Target,
    callable_digest,
    fingerprint,
)
from collective_intelligence_overlay.config import load_config
from collective_intelligence_overlay.invocations import Executor, Reservation
from collective_intelligence_overlay.models import Capability, Evidence, Scope, Subject, now
from collective_intelligence_overlay.peer import PeerService
from collective_intelligence_overlay.synchronization import Feed, FeedFilter, Receiver


def provider_binding():
    code = callable_digest(sample_for(None))
    return Binding(
        id="observe",
        revision="1",
        issuer="producer",
        registrar="producer",
        subject=Subject(id="sample.counter", version="1", digest=code),
        scope=Scope(
            task="observe",
            input_contract="integer.v1",
            output_contract="sample.v1",
            environment={"application": "1"},
        ),
        target=Target(
            kind="local", name="observe", interface_digest=code, implementation_identity="installed"
        ),
        input_schema={
            "type": "object",
            "required": ["value"],
            "additionalProperties": False,
            "properties": {"value": {"type": "integer"}},
        },
        output_schema={"type": "integer"},
        callers=("receiver", "verifier"),
        effects="read-only",
    )


def sample_for(registry):
    async def sample(arguments):
        def increment():
            with registry.overlay.store.engine.begin() as conn:
                return conn.execute(
                    text(
                        "UPDATE test_call_witness SET count = count + 1 "
                        "WHERE id = 1 RETURNING count"
                    )
                ).scalar_one()

        return await asyncio.to_thread(increment)

    return sample


def register_provider(registry):
    registry.register_local(provider_binding(), sample_for(registry), lambda _: True)


def proxy_binding(config):
    provider = provider_binding()
    endpoint = next(p.url for p in config.peers if p.identity == "producer")
    return provider.model_copy(
        update={
            "id": "remote-observe",
            "issuer": config.owner,
            "registrar": config.owner,
            "subject": Subject(id="proxy.sample", version="1", digest=fingerprint(endpoint)),
            "target": Target(
                kind="a2a",
                name=provider.id,
                peer="producer",
                endpoint=endpoint,
                interface_digest=provider.digest,
                implementation_identity="remote-unknown",
            ),
            "callers": ("receiver", "verifier"),
        }
    )


def capability(binding):
    return Capability(
        schema_version="2",
        binding_digest=binding.digest,
        issuer=binding.issuer,
        subject=binding.subject,
        scope=binding.scope,
        entrypoint=binding.id,
        claim="sample",
        license="Apache-2.0",
        provenance="installed test host",
        classification="declared-new",
        expires_at=now() + timedelta(hours=1),
    )


def checked(binding, verifier="verifier"):
    return Evidence(
        schema_version="2",
        binding_digest=binding.digest,
        issuer=verifier,
        subject=binding.subject,
        scope=binding.scope,
        claim="sample",
        receivers=(binding.registrar,),
        verdict="PASS",
        method="reference-check",
        verifier_version="1",
        artifact_digest=fingerprint(["sample", binding.digest]),
        expires_at=now() + timedelta(hours=1),
    )


def admit(overlay, identity, binding, verifier_config, *, dependency=None):
    cap = capability(binding)
    if dependency is not None:
        cap = cap.model_copy(
            update={
                "dependencies": (dependency.subject,),
                "dependency_issuers": (dependency.issuer,),
            }
        )
    overlay.store.put(identity.sign(cap))
    verifier_identity, verifier_overlay = verifier_config.runtime()
    try:
        verifier_overlay.store.put(verifier_identity.sign(checked(binding, verifier_config.owner)))
        filt = FeedFilter(subjects=(binding.subject,))
        Receiver(overlay.store).apply(
            verifier_config.owner,
            filt,
            Feed(verifier_overlay.store, verifier_identity).page(identity.name, filt),
        )
    finally:
        verifier_overlay.store.close()


def register_consumer(config):
    identity, overlay = config.runtime()
    proxy = proxy_binding(config)
    registry = Registry(overlay)
    registry.register_a2a(proxy, lambda _: True, config, identity)
    return identity, registry, proxy


def parent_binding(proxy, operation, *, name="parent"):
    return proxy.model_copy(
        update={
            "id": name,
            "subject": Subject(id=name, version="1", digest=callable_digest(operation)),
            "target": Target(
                kind="local",
                name=name,
                interface_digest=callable_digest(operation),
                implementation_identity="installed",
            ),
            "output_schema": {"type": "array", "items": {"type": "integer"}},
            "components": (proxy.digest,),
        }
    )


def context(config):
    return ExecutionContext(caller=config.owner, environment=config.execution_environment)


def register_parent(registry, proxy, execution_context):
    async def pair(arguments):
        first = await registry.execute(
            proxy.id, proxy.digest, arguments, execution_context, call_id="first"
        )
        second = await registry.execute(
            proxy.id, proxy.digest, arguments, execution_context, call_id="second"
        )
        return [first, second]

    parent = parent_binding(proxy, pair)
    registry.register_local(parent, pair, lambda _: True)
    return parent


class LoseResponse:
    """Drop one real HTTP result *after* its real provider transaction completed."""

    def __init__(self, app, armed=True):
        self.app, self.armed = app, armed

    async def __call__(self, scope, receive, send):
        messages = []

        async def capture(message):
            messages.append(message)

        if self.armed and scope["type"] == "http" and scope["method"] == "POST":
            await self.app(scope, receive, capture)
            body = b"".join(m.get("body", b"") for m in messages)
            if b"completed" in body:
                self.armed = False
                await send(
                    {
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                await send({"type": "http.response.body", "body": b"{lost-response"})
                return
            for message in messages:
                await send(message)
        else:
            await self.app(scope, receive, send)


async def run_caller(config, mode, output):
    identity, registry, proxy = register_consumer(config)
    parent = register_parent(registry, proxy, context(config))
    try:
        runner = Executor(registry, identity, Reservation())
        result = await runner.invoke(
            "lost-parent", parent.id, parent.digest, {"value": 7}, context(config)
        )
        calls = registry.remote_calls(context(config), invocation_id="lost-parent")
        queries = (
            [
                await registry.query_remote_call(c.call_key, context(config), config, identity)
                for c in calls
            ]
            if mode == "resume"
            else []
        )
        output.write_text(
            json.dumps(
                {
                    "result": result,
                    "calls": [c.model_dump(mode="json") for c in calls],
                    "queries": queries,
                    "runtime": runtime(),
                }
            ),
            encoding="utf-8",
        )
    finally:
        registry.overlay.store.close()


def runtime():
    import collective_intelligence_overlay as package

    return {
        "version": sys.version,
        "minor": list(sys.version_info[:2]),
        "executable": sys.executable,
        "os": platform.platform(),
        "import": package.__file__,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("provider", "caller", "resume"))
    parser.add_argument("config", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--lose-response", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.mode == "provider":
        service = PeerService(config, register_provider)
        if args.output is not None:
            args.output.write_text(json.dumps(runtime()), encoding="utf-8")
        app = application(config, service.handle)
        if args.lose_response:
            app = LoseResponse(app)
        try:
            uvicorn.run(
                app,
                host="127.0.0.1",
                port=urlsplit(config.url).port,
                log_level="critical",
                access_log=False,
            )
        finally:
            service.overlay.store.close()
    else:
        if args.output is None:
            parser.error("caller needs --output")
        asyncio.run(run_caller(config, args.mode, args.output))


if __name__ == "__main__":
    main()
