"""Run the standard OPA binary locally; no parallel Python rule implementation."""

import asyncio
import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from pydantic import Field

from .models import Model, Outcome
from .security import digest


class PolicySettings(Model):
    licenses: tuple[str, ...] = ("Apache-2.0", "MIT", "BSD-3-Clause", "CC0-1.0")
    permissions: tuple[str, ...] = ()
    max_evidence_age_seconds: int = Field(default=86400, ge=1, le=31536000)
    max_source_age_seconds: int = Field(default=300, ge=1, le=86400)


class Policy:
    def __init__(self, binary: str, settings: PolicySettings, path: Path | None = None) -> None:
        self.binary = binary
        self.settings = settings
        self.path = path or Path(str(files("collective_intelligence_overlay") / "policy.rego"))
        self.digest = digest(self.path.read_bytes() + settings.model_dump_json().encode())

    async def decide(self, facts: dict[str, Any]) -> tuple[Outcome, tuple[str, ...]]:
        facts = {**facts, "settings": self.settings.model_dump(mode="json")}
        process = None
        try:
            # Pin the checked policy bytes against unnoticed configuration changes.
            current = digest(self.path.read_bytes() + self.settings.model_dump_json().encode())
            if current != self.digest:
                return Outcome.UNKNOWN, ("policy_changed",)
            process = await asyncio.create_subprocess_exec(
                self.binary,
                "eval",
                "--format=json",
                "--stdin-input",
                "--data",
                str(self.path),
                "data.overlay.decision",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(json.dumps(facts).encode()), 5)
            if process.returncode != 0 or len(stdout) > 65536:
                return Outcome.UNKNOWN, ("policy_error",)
            value = json.loads(stdout)["result"][0]["expressions"][0]["value"]
            outcome = Outcome(value["outcome"])
            reasons = value["reasons"]
            if (
                not isinstance(reasons, list)
                or not reasons
                or not all(isinstance(r, str) for r in reasons)
            ):
                return Outcome.UNKNOWN, ("invalid_policy_result",)
            return outcome, tuple(reasons)
        except (OSError, ValueError, KeyError, IndexError, TypeError, TimeoutError):
            return Outcome.UNKNOWN, ("policy_unavailable_or_undefined",)
        finally:
            if process and process.returncode is None:
                process.kill()
                await process.wait()
