# SDK integration

The tested combinations are in [compatibility](compatibility.md). Install the `agents`
extra for MAF/A2A/MCP, and additionally `model` for the optional provider example.
Core imports do not load these SDKs.

## Microsoft Agent Framework

`AdmissionMiddleware(overlay, {tool_name: request})` uses public `FunctionMiddleware`
and `FunctionInvocationContext`. Add it to `Agent(..., middleware=[...])`. Unmapped
functions fail closed with `MiddlewareFailure`; mapped functions call the same
use-time admission path as the SDK. Bind requests in trusted host configuration.
Changing arguments requires the application's own contract validation.

The reference composition uses public `executor`, `WorkflowContext`, `WorkflowBuilder`
and `workflow.run`. The tool-loop test uses an actual `Agent` with a deterministic
`FunctionInvocationLayer`/`BaseChatClient`, not a network model or private SDK patch.

## A2A

The adapter uses SDK 1.x protobuf `AgentCard`, `Message`, `Part` and the official
client/server JSON-RPC implementation. Required extension v1 carries domain data.
Unknown required extensions, substituted endpoints and inconsistent card identity
are rejected. Cards remain self-description, not verified capability evidence.

Supported domain operations are discover, submit, owner sync, qualify, metrics,
revoke and bounded reference work. These are application payloads inside A2A; no
parallel RPC protocol is implemented. A2A completion only reports delivery/execution
state; the Decision/Evidence payload contains business acceptance.

## MCP

`adapters.mcp.call_tool` uses MCP 2.x `Client` and `streamable_http_client`. Both
endpoint and tool name must appear in operator allowlists; admission is rechecked
before the call. Tool success never produces a verification PASS. The initial adapter
supports Streamable HTTP; additional transports are not claimed as overlay-tested.

```sh
uv run python -m collective_intelligence_overlay.reference_mcp --port 8050
```

## Model-backed opt-in example

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
