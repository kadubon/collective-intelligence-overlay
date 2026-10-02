"""Explicit finite local Gemma connection smoke; no confirmatory inference.

The supplied server must already be cloud-disabled. No pull, unload, fallback or
configuration change occurs here. Raw metadata is private until path redaction.
"""

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import platform
import time
from pathlib import Path

import httpx
from agent_framework import Content, Message
from ollama_observer import RawInferenceTransport, write_new
from pydantic import BaseModel, ConfigDict

from collective_intelligence_overlay.adapters.ollama import local_ollama_client
from collective_intelligence_overlay.bindings import fingerprint

MODEL = "gemma4:e4b"
EXPECTED_DIGEST = "dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c"
ROOT = Path(__file__).resolve().parents[1]


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: int


async def metadata(http, output, prefix):
    result = {}
    for name in ("version", "tags", "show", "ps"):
        response = (
            await http.post("/api/show", json={"model": MODEL})
            if name == "show"
            else await http.get("/api/" + name)
        )
        response.raise_for_status()
        (output / f"{prefix}-{name}.raw").write_bytes(response.content)
        result[name] = response.json()
    exact = next(item for item in result["tags"]["models"] if item["name"] == MODEL)
    if exact["digest"] != EXPECTED_DIGEST:
        raise ValueError("exact installed model digest changed")
    if result["show"].get("remote_host") or result["show"].get("remote_model"):
        raise ValueError("remote model is not allowed")
    return result


async def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    private = output / "private-metadata"
    private.mkdir()
    log = await asyncio.to_thread(args.server_log.read_text, encoding="utf-8")
    if 'msg="Ollama cloud disabled: true"' not in log:
        raise ValueError("explicit server cloud-disable log required")
    sources = {
        name: hashlib.sha256(await asyncio.to_thread((ROOT / name).read_bytes)).hexdigest()
        for name in (
            "scripts/probe_local_ollama.py",
            "scripts/ollama_observer.py",
            "src/collective_intelligence_overlay/adapters/ollama.py",
            "pyproject.toml",
            "uv.lock",
        )
    }
    plan = {
        "id": "cio-041-ollama-connection-smoke-v1",
        "classification": "connection smoke",
        "real_model": True,
        "model_name": MODEL,
        "model_digest": EXPECTED_DIGEST,
        "sources": sources,
        "schema_digest": fingerprint(Answer.model_json_schema()),
        "maximum_seconds": 1800,
        "token_budget_upper": 65536,
        "per_request_seconds": 180,
        "parallel_requests": 1,
        "hidden_retries": 0,
        "cases": [
            "structured",
            "invalid-json",
            "thinking-truncation",
            "tool-result-input",
            "stream-final-usage",
            "stream-interruption",
            "deadline",
            "chat-completions",
            "responses-stateless",
            "responses-stateful-rejected",
        ],
        "count": 10,
        "native_vs_compatible_prompts_are_distinct": True,
        "energy": "unavailable",
        "confirmatory_or_pilot_episode": False,
        "platform": platform.platform(),
    }
    write_new(output / "protocol.json", plan)
    sdk_versions = {
        name: importlib.metadata.version(name)
        for name in ("agent-framework-core", "agent-framework-ollama", "ollama", "httpx")
    }
    results, charged = [], 0
    started = time.perf_counter()
    async with httpx.AsyncClient(
        base_url=args.host,
        trust_env=False,
        follow_redirects=False,
        timeout=10,
        transport=httpx.AsyncHTTPTransport(retries=0),
    ) as http:
        environment = await metadata(http, private, "before")
        write_new(
            output / "environment-summary.json",
            {
                "model_digest": EXPECTED_DIGEST,
                "version": environment["version"],
                "details": environment["show"]["details"],
                "parameters": environment["show"].get("parameters"),
                "capabilities": environment["show"].get("capabilities"),
                "think_info": environment["show"].get("think_info"),
                "cloud_disabled_log_observed": True,
                "sdk_versions": sdk_versions,
                "initial_resident_models": environment["ps"],
                "model_license_sha256": hashlib.sha256(
                    environment["show"].get("license", "").encode()
                ).hexdigest(),
                "raw_metadata_privacy": "private paths require redaction before publication",
            },
        )
        async with asyncio.timeout(1800):
            for index, name in enumerate(plan["cases"]):
                current = (await http.get("/api/tags")).json()
                if (
                    next(m for m in current["models"] if m["name"] == MODEL)["digest"]
                    != EXPECTED_DIGEST
                ):
                    raise ValueError("model changed during smoke")
                native = {
                    "temperature": 0,
                    "top_p": 0.95,
                    "top_k": 64,
                    "num_ctx": 4096,
                    "num_predict": 256,
                    "seed": 4100 + index,
                    "draft_num_predict": 0,
                }
                options = {"options": native, "think": False, "keep_alive": "5m"}
                prompt = "Return a JSON object with answer equal to 2 plus 5. No prose."
                if name == "invalid-json":
                    prompt = "Output exactly the plain text INVALID. Do not output JSON."
                elif name == "thinking-truncation":
                    prompt = "Explain by reasoning how to factor the integer 1234567891."
                    native["num_predict"] = 32
                    options["think"] = True
                elif name == "tool-result-input":
                    prompt = "The provided public tool result is the count 3; return JSON answer 3."
                elif name == "stream-interruption":
                    prompt = "Reason carefully about the first one hundred prime numbers."
                    options["think"] = True
                    native["num_predict"] = 1024
                elif name == "deadline":
                    prompt = (
                        "Compute the sum of integers from 1 through 9999 and explain every step."
                    )
                    options["think"] = True
                if name in {"structured", "stream-final-usage", "tool-result-input"}:
                    options["response_format"] = Answer
                reservation = native["num_ctx"] + native["num_predict"]
                if charged + reservation > plan["token_budget_upper"]:
                    raise ValueError("smoke token reservation exhausted")
                attempt_dir = output / f"attempt-{index:02}-{name}"
                observer = RawInferenceTransport(
                    attempt_dir,
                    identity={
                        "run": plan["id"],
                        "episode": "smoke",
                        "arm": "surface-probe",
                        "peer": "proposer",
                        "attempt": str(index),
                    },
                    requested={
                        "native_options": native,
                        "think": options["think"],
                        "keep_alive": "5m",
                        "stream": name.startswith("stream"),
                    },
                    provenance={
                        "model_name": MODEL,
                        "model_digest": EXPECTED_DIGEST,
                        "sources": sources,
                        "prompt_digest": fingerprint(prompt),
                        "schema_digest": plan["schema_digest"],
                        "sdk_versions": sdk_versions,
                    },
                    token_reservation=reservation,
                    real_model=True,
                )
                item = {"index": index, "case": name, "status": "not_returned"}
                try:
                    if name in {
                        "chat-completions",
                        "responses-stateless",
                        "responses-stateful-rejected",
                    }:
                        endpoint = (
                            "/v1/chat/completions"
                            if name == "chat-completions"
                            else "/v1/responses"
                        )
                        payload = {"model": MODEL, "stream": False, "think": False}
                        if name == "chat-completions":
                            payload.update(
                                messages=[{"role": "user", "content": "Say BLUE."}],
                                max_tokens=32,
                                response_format={"type": "json_object"},
                            )
                        else:
                            payload.update(
                                input="Say GREEN." if name.endswith("stateless") else "Say ORANGE.",
                                max_output_tokens=32,
                            )
                            if name.endswith("rejected"):
                                payload["previous_response_id"] = "nonexistent-smoke-id"
                        async with httpx.AsyncClient(
                            base_url=args.host,
                            transport=observer,
                            timeout=180,
                            trust_env=False,
                            follow_redirects=False,
                        ) as compat:
                            response = await compat.post(endpoint, json=payload)
                            item.update(
                                status="returned",
                                http_status=response.status_code,
                                compatible_payload=response.json(),
                            )
                    else:
                        messages = [Message(role="user", contents=[prompt])]
                        if name == "tool-result-input":
                            # A public synthetic result, not a hidden answer or model critic.
                            messages.extend(
                                [
                                    Message(
                                        role="assistant",
                                        contents=[
                                            Content.from_function_call(
                                                "public-fixture-count",
                                                "count_rows",
                                                arguments={"fixture": "public-three-row-fixture"},
                                            )
                                        ],
                                    ),
                                    Message(
                                        role="tool",
                                        contents=[
                                            Content.from_function_result(
                                                "public-fixture-count",
                                                result={"count": 3},
                                            )
                                        ],
                                    ),
                                ]
                            )
                        async with local_ollama_client(
                            args.host,
                            model=MODEL,
                            seconds=180,
                            transport=observer,
                        ) as client:
                            async with asyncio.timeout(0.05 if name == "deadline" else 180):
                                if name.startswith("stream"):
                                    stream = client.get_response(
                                        messages, options=options, stream=True
                                    )
                                    async for update in stream:
                                        if name == "stream-interruption":
                                            item["first_update"] = {
                                                "text": str(update),
                                                "model": update.model,
                                                "finish_reason": str(update.finish_reason),
                                            }
                                            break
                                    if name == "stream-final-usage":
                                        response = await stream.get_final_response()
                                        item.update(
                                            text=response.text, sdk_usage=response.usage_details
                                        )
                                    else:
                                        # Close the owned transport; retain received bytes and
                                        # missing final usage. No full-response retry follows.
                                        await observer.aclose()
                                else:
                                    response = await client.get_response(messages, options=options)
                                    item.update(
                                        text=response.text, sdk_usage=response.usage_details
                                    )
                                    if name == "structured":
                                        item["host_check"] = response.value.answer == 7
                                    elif name == "invalid-json":
                                        try:
                                            Answer.model_validate_json(response.text)
                                            item["host_parse"] = "valid"
                                        except ValueError:
                                            item["host_parse"] = "invalid"
                                item["status"] = "returned"
                except Exception as error:
                    item.update(status="failed", error_type=type(error).__name__)
                finally:
                    await observer.aclose()
                    observation = json.loads((attempt_dir / "observation.json").read_bytes())
                    charged += observation["budget_charge"]
                    item["observation"] = observation
                    write_new(attempt_dir / "host-validation.json", item)
                    results.append(item)
                    print(
                        json.dumps(
                            {
                                "case": name,
                                "status": item["status"],
                                "tokens": observation["tokens_measured"],
                                "charge": observation["budget_charge"],
                            }
                        )
                    )
                    resident = await http.get("/api/ps")
                    (private / f"resident-{index:02}.raw").write_bytes(resident.content)
                    if name in {"stream-interruption", "deadline"}:
                        await asyncio.sleep(2)
        await metadata(http, private, "after")
    write_new(
        output / "result.json",
        {
            "classification": "connection smoke, no A/B inference",
            "offered_attempts": 10,
            "observed_attempts": len(results),
            "results": results,
            "aggregate_budget_charge": charged,
            "elapsed_seconds": time.perf_counter() - started,
            "energy": "unavailable",
            "confirmatory_comparison_complete": False,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--server-log", required=True, type=Path)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
