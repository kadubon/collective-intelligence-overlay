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

In the 0.3.1 candidate, pass the complete result of `collect` to `Steps.step` (or
return it from the finite run callback) to preserve unavailable peers and rejected
alternative summaries. Malformed A2A response parsing uses the SDK's public
`parse_agent_card`, protobuf types and its existing JSONRPC response dependency at
a pure input boundary. The transport retains its byte, destination and time bounds.
Public wire/schema and signed payload versions are unchanged by proposal isolation;
category observations are owner-local. See [rejected alternatives](api.md#031-candidate-rejected-alternatives).
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

For the 0.3.1 candidate, `bound_tool(registry, binding_id, context, call_scope=...)`
receives call IDs from the public `FunctionTool.invoke(tool_call_id=...)` parameter
or public middleware `FunctionInvocationContext.metadata["call_id"]`. Conflicting
context/parameter IDs fail. The actual 1.19.0 SDK has no `context.tool_call_id`
attribute; the adapter subclasses the public tool and never patches SDK code.
Its tool input schema contains only business `arguments`, not identity or grants.
Use an existing Executor parent or a host-persisted scope, for example the public
`AgentSession.session_id` supplied explicitly by the host. Persist a new session
before invoking tools; `AgentSession.to_dict/from_dict` retains that namespace.
The SDK's implicit new session, occurrence ID, and call arrival order are not retry
identities. See [logical remote calls](api.md#031-candidate-logical-remote-calls).

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
