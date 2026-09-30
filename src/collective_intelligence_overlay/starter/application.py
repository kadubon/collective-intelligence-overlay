"""A minimal trusted application. Publishing this candidate creates no PASS."""

from datetime import timedelta
from typing import Any

from collective_intelligence_overlay.application import ApplicationHost
from collective_intelligence_overlay.bindings import Binding, Target, callable_digest
from collective_intelligence_overlay.models import Capability, Scope, Subject, now


async def count_words(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"words": len(arguments["text"].split())}


def configure(host: ApplicationHost) -> None:
    scope = Scope(
        task="word-count", input_contract="text.v1", output_contract="words.v1", environment={}
    )
    subject = Subject(id="word-count", version="1", digest=callable_digest(count_words))
    binding = Binding(
        id="word-count",
        revision="1",
        issuer=host.config.owner,
        registrar=host.config.owner,
        subject=subject,
        scope=scope,
        target=Target(
            kind="local",
            name="word-count",
            interface_digest=callable_digest(count_words),
            implementation_identity="installed",
        ),
        input_schema={
            "type": "object",
            "required": ["text"],
            "additionalProperties": False,
            "properties": {"text": {"type": "string", "maxLength": 32768}},
        },
        output_schema={
            "type": "object",
            "required": ["words"],
            "additionalProperties": False,
            "properties": {"words": {"type": "integer", "minimum": 0}},
        },
        callers=(host.config.owner,),
        verification_callers=(host.config.owner,),
        effects="read-only",
    )
    host.registry.register_local(binding, count_words, lambda args: isinstance(args["text"], str))
    host.publish_candidate(
        binding,
        Capability(
            schema_version="2",
            issuer=host.config.owner,
            subject=subject,
            scope=scope,
            binding_digest=binding.digest,
            entrypoint="word-count",
            claim="whitespace-delimited-count",
            license="Apache-2.0",
            provenance="operator-selected installed starter; independently unchecked",
            classification="declared-new",
            expires_at=now() + timedelta(days=1),
        ),
    )
