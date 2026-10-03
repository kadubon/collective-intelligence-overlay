"""Actual MAF/Ollama serialization with an explicitly labelled HTTP test double.

These validate instrumentation; they are not Gemma inference observations.
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest
from agent_framework import Message
from pydantic import BaseModel

from collective_intelligence_overlay.adapters.inference_observer import RawInferenceTransport
from collective_intelligence_overlay.adapters.ollama import local_ollama_client

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))


class Answer(BaseModel):
    answer: int


def recorded(tmp_path, delegate):
    return RawInferenceTransport(
        tmp_path / "attempt",
        identity={"request": "test-double-1"},
        requested={"num_ctx": 4096, "num_predict": 32},
        provenance={"model_name": "gemma4:e4b", "model_digest": "a" * 64},
        token_reservation=4128,
        real_model=False,
        delegate=delegate,
    )


async def test_actual_sdk_payload_typed_response_and_same_response_usage(tmp_path):
    captured = []

    async def handle(request):
        # Actual intent and payload are durable before the downstream sees a send.
        assert (tmp_path / "attempt/intent.json").is_file()
        assert (tmp_path / "attempt/request.json").is_file()
        assert (tmp_path / "attempt/request.raw").read_bytes() == request.content
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "gemma4:e4b",
                "created_at": "2026-10-02T00:00:00Z",
                "message": {"role": "assistant", "content": '{"answer":7}', "thinking": "check"},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 41,
                "eval_count": 9,
                "prompt_eval_cached_count": 3,
                "total_duration": 2_000_000_000,
                "load_duration": 1_000_000_000,
            },
        )

    observer = recorded(tmp_path, httpx.MockTransport(handle))
    async with local_ollama_client(
        "http://127.0.0.1:11435",
        model="gemma4:e4b",
        transport=observer,
    ) as client:
        response = await client.get_response(
            [Message(role="user", contents=["public test"])],
            options={
                "response_format": Answer,
                "think": False,
                "keep_alive": "5m",
                "options": {"num_ctx": 4096, "num_predict": 32, "draft_num_predict": 0, "seed": 17},
            },
        )
        assert response.value.answer == 7
        assert response.usage_details["input_token_count"] == 41
        assert response.usage_details["output_token_count"] == 9
    assert len(captured) == 1
    assert captured[0]["options"]["draft_num_predict"] == 0
    assert captured[0]["think"] is False and captured[0]["format"]["type"] == "object"
    observed = json.loads((tmp_path / "attempt/observation.json").read_bytes())
    assert observed["budget_charge"] == 50 and observed["token_status"] == "measured"
    assert observed["usage_native"]["prompt_eval_cached_count"] == 3
    assert observed["durations_seconds"]["total_duration"] == 2
    with pytest.raises(ValueError, match="one inference"):
        await observer.handle_async_request(httpx.Request("POST", "http://127.0.0.1/api/chat"))


class Interrupted(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield (
            b'{"model":"gemma4:e4b",'
            b'"message":{"role":"assistant","thinking":"partial"},"done":false}\n'
        )
        raise httpx.ReadError("test interruption")

    async def aclose(self):
        pass


async def test_interrupted_stream_retains_partial_thinking_and_missing_usage(tmp_path):
    observer = recorded(
        tmp_path,
        httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                headers={"content-type": "application/x-ndjson"},
                stream=Interrupted(),
            )
        ),
    )
    async with local_ollama_client(
        "http://127.0.0.1:11435",
        model="gemma4:e4b",
        transport=observer,
    ) as client:
        with pytest.raises(httpx.ReadError):
            async for _ in client.get_response(
                [Message(role="user", contents=["public test"])],
                stream=True,
            ):
                pass
    observed = json.loads((tmp_path / "attempt/observation.json").read_bytes())
    assert observed["error_type"] == "ReadError" and not observed["stream_complete"]
    assert observed["tokens_measured"] is None and observed["budget_charge"] == 4128
    assert b"partial" in (tmp_path / "attempt/response.raw").read_bytes()


async def test_deadline_without_response_retains_upper_reservation(tmp_path):
    deadline = asyncio.timeout(None)

    async def handle(_):
        # Start the response deadline after durable intent and actual dispatch,
        # rather than racing SDK/client setup and disk writes on loaded hosts.
        deadline.reschedule(asyncio.get_running_loop().time() + 0.05)
        await asyncio.sleep(1)
        raise AssertionError("must be cancelled")

    observer = recorded(tmp_path, httpx.MockTransport(handle))
    with pytest.raises(TimeoutError):
        async with (
            deadline,
            local_ollama_client(
                "http://127.0.0.1:11435",
                model="gemma4:e4b",
                transport=observer,
            ) as client,
        ):
            await client.get_response([Message(role="user", contents=["public test"])])
    observed = json.loads((tmp_path / "attempt/observation.json").read_bytes())
    assert observed["transport_dispatch_started"] is True
    assert observed["budget_charge_status"] == "reserved_upper_bound"
    assert observed["status"] is None and observed["token_status"] == "unavailable"
    assert observed["budget_charge"] == 4128 and observed["received_bytes"] == 0


@pytest.mark.parametrize("host", ["https://127.0.0.1:11435", "http://example.com:11435"])
async def test_adapter_rejects_external_or_implicit_host(host):
    with pytest.raises(ValueError):
        async with local_ollama_client(host, model="gemma4:e4b"):
            raise AssertionError("invalid host entered")
