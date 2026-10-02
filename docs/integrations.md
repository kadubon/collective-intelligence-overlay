# SDK integration

`examples/reference_registration.py` exposes `register_reference(registry, checker)`
for the installed CSV aggregation and report rendering functions. It returns three
`(Binding, Capability)` pairs, including actual MAF composition whose children call
`Registry.execute` with their own arguments and assessment. The host publishes the
new v2 candidates and obtains independent checks before ordinary reuse. Explicit
read-only checker probes are permitted before PASS; their success is not evidence.
Old v1 evidence is not reinterpreted as binding verification. The `peer --reference`
application uses these packaged registrations. The CSV demo checks provider bindings,
installs explicit receiver-side A2A imports, checks those imports, and invokes them
through Executor. Reinitializing a peer requires reinstalling its configured remote
imports before starting new calls; existing invocation lookup remains durable.

Run the real-service example test with the PostgreSQL/OPA test environment:
`uv run pytest tests/integration/test_reference_registration.py -q`. It covers
pre-PASS denial, checker probes, independently checked results, held-out CSV and
dependency withdrawal. For durable invocation results and receipts, invoke these
registered bindings through `Executor`, as in the external document application.

The tested combinations are in [compatibility](compatibility.md). Install the `agents`
extra for MAF/A2A/MCP, and additionally `model` for the optional provider example.
Core imports do not load these SDKs.

For finite owner goals and installed builders, use the
[document registration and host loop](quickstart.md#register-goals-and-run-finite-formation-030).
`examples/adaptive_documents.py` is outside the package and registers goals,
checker bindings, public proposal contracts and parameterized factories through
public APIs. Two authenticated A2A proposers return retained alternatives; the
receiver selects against its current permissions and budget.

In 0.3.1, pass the complete result of `collect` to `Steps.step` (or
return it from the finite run callback) to preserve unavailable peers and rejected
alternative summaries. Malformed A2A response parsing uses the SDK's public
`parse_agent_card`, protobuf types and its existing JSONRPC response dependency at
a pure input boundary. The transport retains its byte, destination and time bounds.
Public wire/schema and signed payload versions are unchanged by proposal isolation;
category observations are owner-local. See [rejected alternatives](api.md#031-rejected-alternatives).
`adapters.maf.propose_structured` uses a public Agent with typed output, bounded
repair and no tools. Its deterministic client tests verify SDK behavior, not
model discovery superiority. [API](api.md) defines bounds and signatures.

## Microsoft Agent Framework

`AdmissionMiddleware(overlay, {tool_name: request})` uses public `FunctionMiddleware`
and `FunctionInvocationContext`. Add it to `Agent(..., middleware=[...])`. Unmapped
functions fail closed with `MiddlewareFailure`; mapped functions call the same
use-time admission path as the SDK. Bind requests in trusted host configuration.
Changing arguments requires the application's own contract validation.

The reference composition uses public `executor`, `WorkflowContext`, `WorkflowBuilder`
and `workflow.run`. The tool-loop test uses an actual `Agent` with a deterministic
`FunctionInvocationLayer`/`BaseChatClient`, not a network model or private SDK patch.

For 0.3.1, `bound_tool(registry, binding_id, context, call_scope=...)`
receives call IDs from the public `FunctionTool.invoke(tool_call_id=...)` parameter
or public middleware `FunctionInvocationContext.metadata["call_id"]`. Conflicting
context/parameter IDs fail. The actual 1.19.0 SDK has no `context.tool_call_id`
attribute; the adapter subclasses the public tool and never patches SDK code.
Its tool input schema contains only business `arguments`, not identity or grants.
Use an existing Executor parent or a host-persisted scope, for example the public
`AgentSession.session_id` supplied explicitly by the host. Persist a new session
before invoking tools; `AgentSession.to_dict/from_dict` retains that namespace.
The SDK's implicit new session, occurrence ID, and call arrival order are not retry
identities. See [logical remote calls](api.md#031-logical-remote-calls).

## A2A

The adapter uses SDK 1.x protobuf `AgentCard`, `Message`, `Part` and the official
client/server JSON-RPC implementation. Required extension v2 carries domain data.
Its data part contains `application_json`, an opaque JSON string: Protobuf Struct
uses double-precision numbers and would otherwise change integer/schema
representations and binding digests. A2A still supplies the message types,
serialization, authentication boundary and transport; this is extension payload
encoding, not a second RPC implementation. Standard non-overlay service bindings
retain their native data-part contracts and are documented in [API](api.md).
Unknown required extensions, substituted endpoints and inconsistent card identity
are rejected. Cards remain self-description, not verified capability evidence.

Supported domain operations include discover, submit, owner sync, qualify, metrics,
capability metrics, revoke, invoke, invocation lookup and cancellation. The bundled
reference app explicitly enables candidate registration, configured service import
and independent checking/baseline work. Its normal reuse path is registered execution. These are
application payloads inside A2A; no
parallel RPC protocol is implemented. A2A completion only reports delivery/execution
state; the Decision/Evidence payload contains business acceptance.

## MCP

The 0.4.1 candidate uses the public `httpx2.AsyncClient` response hook with pinned
MCP 2.2.0. Defaults bound raw received bytes to 262144, JSON nesting to 64,
aggregate tools to 128, pages to 16 and the complete exchange to 20 seconds.
`ReceiveLimits` permits only finite operator bounds (at most 1 MiB / 128 levels /
1024 tools / 30 seconds). Both JSON and SSE are bounded before SDK JSON parsing;
the official SDK still parses protocol messages, discovery and tools. Compression
and redirects are refused at this pinned endpoint. Violations and cancellation
cannot yield a result or PASS. The SDK's existing SSE 1 MiB limit does not cover
its whole-buffer JSON response path. These are application receive bounds, not a
claim that a Python client prevents every infrastructure denial of service.

`adapters.mcp.call_tool` uses MCP 2.x `Client` and `streamable_http_client`. Both
endpoint and tool name must appear in operator allowlists; admission is rechecked
before the call. Tool success never produces a verification PASS. The initial adapter
supports Streamable HTTP; additional transports are not claimed as overlay-tested.

```sh
uv run python -m collective_intelligence_overlay.reference_mcp --port 8050
```

## Model-backed opt-in example

### Explicit local Ollama

Install the candidate's `[agents,ollama]` extras to use its public
`adapters.ollama.local_ollama_client` context manager. It injects the official
`ollama.AsyncClient` into MAF's `OllamaChatClient`, accepts an explicit loopback IP
and finite timeout, disables environment proxies/redirects/retries and closes its
owned public HTTP transport. It does not start a server or change installed weights.
The operator separately disables cloud, verifies `/api/version`, `/api/tags`,
`/api/show`, `/api/ps`, and pins the actual model digest. Loopback alone is insufficient.

```python
from agent_framework import Message
from collective_intelligence_overlay.adapters.ollama import local_ollama_client

async with local_ollama_client("http://127.0.0.1:11439", model="gemma4:e4b") as client:
    response = await client.get_response(
        [Message(role="user", contents=["Return a small public JSON example."])],
        options={
            "response_format": "json",
            "think": False,
            "keep_alive": "5m",
            "options": {
                "seed": 17,
                "num_ctx": 4096,
                "num_predict": 256,
                "draft_num_predict": 0,
                "temperature": 0,
            },
        },
    )
```

The nested native options preserve parameters that the MAF top-level translation
does not enumerate. Requested values are not automatically effective settings.
MAF exposes input/output usage from the same response; the source-only
`scripts/ollama_observer.py` additionally preserves exact actual payloads, native
final counters/durations and partial raw streams before any host validation.
Missing usage retains its upper reservation. Thinking tokens are already included
in native `eval_count` and must not be added again. Model output remains untrusted
builder input; no model response grants a checker, key, permission or quality PASS.
See [local connection observations and remaining comparison work](audit-041.md).

`examples/live_agent.py` performs authenticated A2A discovery, installs MAF middleware,
and exposes a function that calls the real MCP adapter. Supply an owner config,
valid `UseRequest` JSON, configured model/base URL/API key and a running MCP endpoint.

```sh
uv sync --all-extras --frozen
uv run python examples/live_agent.py --allow-model-calls --config OWNER_CONFIG --request USE_REQUEST_JSON --mcp http://127.0.0.1:8050/mcp --prompt 'Summarize the provided CSV'
```

Set `CIO_MODEL`, `CIO_MODEL_BASE_URL`, `CIO_MODEL_API_KEY` explicitly. Without
`--allow-model-calls`, the example exits before calling a model. Output remains
generated/UNKNOWN. The selected provider uses its current Responses API; compatible
local providers must implement that API. Tests exercise the real provider adapter
with mock HTTP; paid model inference is separately unverified.
