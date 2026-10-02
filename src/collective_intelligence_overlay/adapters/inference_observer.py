"""One inference attempt recorded through the public HTTPX transport interface.

No token estimator, alternate model runtime or SDK retry. Files are observations,
not signed business facts. Use only synthetic/public messages in a publishable run.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from collective_intelligence_overlay.bindings import fingerprint

COUNTERS = (
    "prompt_eval_count",
    "prompt_eval_cached_count",
    "eval_count",
    "total_duration",
    "load_duration",
    "prompt_eval_duration",
    "eval_duration",
)


def write_new(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.flush()
        os.fsync(output.fileno())


class RawInferenceTransport(httpx.AsyncBaseTransport):
    """Single-send transport: stable intent and actual payload precede dispatch.

    Missing/partial usage retains a conservative reservation; it is never a zero
    token observation. The caller includes host/tool/verification work separately
    and uses one inclusive episode wall interval rather than summing children.
    """

    def __init__(
        self,
        directory: Path,
        *,
        identity: dict[str, str],
        requested: dict[str, Any],
        provenance: dict[str, Any],
        token_reservation: int,
        real_model: bool,
        delegate: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if token_reservation <= 0 or not identity or not provenance:
            raise ValueError("explicit attempt identity, provenance and reservation required")
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=False)
        self.intent: dict[str, Any] = {
            "identity": identity,
            "requested": requested,
            "provenance": provenance,
            "settings_digest": fingerprint(requested),
            "token_reservation": token_reservation,
            "created_at": datetime.now(UTC).isoformat(),
            "real_model": real_model,
        }
        write_new(directory / "intent.json", self.intent)
        self.delegate = delegate if delegate is not None else httpx.AsyncHTTPTransport(retries=0)
        self.started = time.perf_counter()
        self.sent = False
        self.dispatch_started = False
        self.finished = False
        self.status: int | None = None
        self.content_type: str | None = None
        self.received = bytearray()
        self.raw_output: Any = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self.sent:
            raise ValueError("one inference send per stable attempt; retries need a new attempt")
        if request.method != "POST" or request.url.path not in {
            "/api/chat",
            "/v1/chat/completions",
            "/v1/responses",
        }:
            raise ValueError("observer accepts only explicit inference endpoints")
        body = await request.aread()
        if len(body) > 262144:
            raise ValueError("inference request byte bound exceeded")
        payload = json.loads(body)
        if payload.get("model") != self.intent["provenance"]["model_name"]:
            raise ValueError("actual model differs from pinned intent")
        self.sent = True
        with (self.directory / "request.raw").open("xb") as actual_request:
            actual_request.write(body)
            actual_request.flush()
            os.fsync(actual_request.fileno())
        await asyncio.to_thread(
            write_new,
            self.directory / "request.json",
            {
                "identity": self.intent["identity"],
                "method": request.method,
                "path": request.url.path,
                "payload": payload,
                "payload_digest": hashlib.sha256(body).hexdigest(),
                "byte_count": len(body),
                "sent_at": datetime.now(UTC).isoformat(),
            },
        )
        self.raw_output = (self.directory / "response.raw").open("xb")
        self.started = time.perf_counter()
        self.dispatch_started = True
        try:
            response = await self.delegate.handle_async_request(request)
        except BaseException as error:
            await self.finish(type(error).__name__, complete=False)
            raise
        self.status = response.status_code
        self.content_type = response.headers.get("content-type")
        if not isinstance(response.stream, httpx.AsyncByteStream):
            await self.finish("InvalidAsyncResponse", complete=False)
            raise ValueError("expected public asynchronous response stream")
        if response.is_stream_consumed:
            # A public transport can return a prebuffered response (e.g. a test
            # fixture). Retain those exact bytes; never reserialize the payload.
            self.append(await response.aread())
            await self.finish(None, complete=True)
            return response
        response.stream = _ObservedStream(self, response.stream)
        return response

    def append(self, chunk: bytes) -> None:
        if len(self.received) + len(chunk) > 2 * 1024 * 1024:
            raise ValueError("raw model response byte bound exceeded")
        self.received.extend(chunk)
        self.raw_output.write(chunk)
        self.raw_output.flush()

    async def finish(self, error: str | None, *, complete: bool) -> None:
        if self.finished:
            return
        self.finished = True
        elapsed = time.perf_counter() - self.started
        if self.raw_output is not None:
            self.raw_output.flush()
            os.fsync(self.raw_output.fileno())
            self.raw_output.close()
        else:
            (self.directory / "response.raw").write_bytes(b"")
        frames, parse_errors = [], []
        raw = bytes(self.received)
        parts = raw.splitlines() if "ndjson" in (self.content_type or "") else [raw]
        for index, part in enumerate(parts):
            if not part:
                continue
            try:
                frames.append(json.loads(part))
            except (ValueError, UnicodeError):
                parse_errors.append(index)
        final = next((p for p in reversed(frames) if isinstance(p, dict) and p.get("done")), {})
        counts = {key: final.get(key) for key in COUNTERS}
        prompt, generated = final.get("prompt_eval_count"), final.get("eval_count")
        token_total = (
            prompt + generated
            if isinstance(prompt, int)
            and not isinstance(prompt, bool)
            and isinstance(generated, int)
            and not isinstance(generated, bool)
            and min(prompt, generated) >= 0
            else None
        )
        measured = complete and self.status == 200 and not parse_errors and token_total is not None
        observation = {
            "identity": self.intent["identity"],
            "transport_dispatch_started": self.dispatch_started,
            "status": self.status,
            "error_type": error,
            "stream_complete": complete,
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "received_bytes": len(raw),
            "content_type": self.content_type,
            "raw_parse_error_indices": parse_errors,
            "frame_count": len(frames),
            "final_model": final.get("model"),
            "done": final.get("done"),
            "done_reason": final.get("done_reason"),
            "usage_native": counts,
            "usage_unit": "tokens and nanoseconds",
            "durations_seconds": {
                key: value / 1_000_000_000 if isinstance(value, int) else None
                for key, value in counts.items()
                if key.endswith("duration")
            },
            "client_elapsed_seconds": elapsed,
            "token_status": "measured" if measured else "unavailable",
            "tokens_measured": token_total if measured else None,
            "budget_charge": token_total
            if measured
            else (self.intent["token_reservation"] if self.dispatch_started else 0),
            "budget_charge_status": "measured"
            if measured
            else ("reserved_upper_bound" if self.dispatch_started else "not_sent_proven"),
            "queue_wait_seconds": None,
            "effective_options": "not returned by chat API",
            "energy": "unavailable",
            "api_charge": {"quantity": 0, "currency": "JPY"},
            "observations_are_signed_business_facts": False,
        }
        await asyncio.to_thread(write_new, self.directory / "observation.json", observation)

    async def aclose(self) -> None:
        if not self.finished:
            await self.finish(
                "ClosedBeforeFinalResponse" if self.dispatch_started else "ClosedBeforeSend",
                complete=False,
            )
        await self.delegate.aclose()


class _ObservedStream(httpx.AsyncByteStream):
    def __init__(self, owner: RawInferenceTransport, stream: httpx.AsyncByteStream) -> None:
        self.owner, self.stream = owner, stream

    async def __aiter__(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self.stream:
                self.owner.append(chunk)
                yield chunk
        except BaseException as error:
            await self.owner.finish(type(error).__name__, complete=False)
            raise
        else:
            await self.owner.finish(None, complete=True)

    async def aclose(self) -> None:
        await self.stream.aclose()
        if not self.owner.finished:
            await self.owner.finish("StreamClosedBeforeEOF", complete=False)
