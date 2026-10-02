# 0.4.1 audit and local-model work in progress

This page describes locally observed candidate behavior. 0.4.1 is not yet
published; full candidate/native validation, preregistered A/B
comparison and public raw assets remain pending. The historical 0.4.0 release,
signed originals and failed formal run are unchanged. The machine-readable
[status and original-attempt catalog](audit-041-status.json) is the current
requirement register; success is not inferred from a later rerun.

The substantive five-pair pilot is complete and its original request/response,
signed receipt and CAS records passed offline verification. Both arms passed
30/30 heldout tasks; measured totals are 4,956 static and 4,970 adaptive tokens.
See [task design, result table and interpretation](gemma-041.md). The primary
episode quality difference is zero at a ceiling; it does not establish equivalence.

## Audit boundaries

| Issue | Candidate change | Local evidence | Remaining limit |
| --- | --- | --- | --- |
| CIO-040-01 | One validator matches saved A2A identity, outbound principal, provider/binding/arguments/purpose and actual result digest in invoke and reconcile | 12 actual PostgreSQL/OPA/authenticated A2A malformed/mismatched replies; existing reconciliation regressions | Provider fingerprint format is not equality to an unexposed request; matching response is not result truth |
| CIO-040-02 | Owner actor and original caller are distinct selectors; original mapping/ID remains immutable | Actual C→B→A processes, loss of valid response, B restart/lookup, C/other denial, ID separation | Standalone old calls without receipts may need their original manifest for a new signed observation |
| CIO-040-03 | Explicit whole-invocation owner review and indexed resolution projection | Actual default 32 held UNKNOWN parents; complete/partial/absent/unknown, concurrent close/claim, restore, signature/stale/authorization refusal | Application must positively establish every local/remote effect/result and physical quiescence; no refund, retry or PASS |
| CIO-040-04 | One applicability filter controls evidence support, source issuers and deadlines | Actual PostgreSQL/OPA unrelated binding/claim/receiver/scope/method and support-expiry checks, existing negative-admission regressions | Scoped synchronization/freshness and relevant negative evidence remain required |
| CIO-040-05 | Same-volume separate staging; locked abandoned-write recovery and retained legacy quarantine | Native Windows process kills at five boundaries, capacity/concurrency/symlink; Linux kills with actual pg_dump/pg_restore | Native Mac candidate checks pending; process-kill tests do not prove power-loss durability |
| CIO-040-06 | Typed complete schema-1 inventory/references and bounded archive inspection | 29 actual dump structural/TLS/CAS cases, separate actual restore and old-schema migrations | Unsigned checksum manifest is not an authenticity anchor; verify does not restore or authorize resume |

The unchanged published 0.4.0 wheel was separately extracted after its SHA256
matched `33898a964443c5276853dc15069247ff8642012332c980d085f9fa9a4faf11d7`.
With canonical dependencies and real PostgreSQL/OPA/A2A, the delegated owner
selector is absent, killed writers leave `.write-*` inside CAS, and confirming
effects at the default 32 limit does not restore intake. The 32-parent observation
retains original UNKNOWN receipts and held allowance. Other baseline/regression
attempts include explicitly retained setup and test-fixture errors; they are not
all independent successful candidate tests.

## MCP and historical duplicate failure

Pinned MCP 2.2.0 has an SSE limit of 1 MiB, while its JSON path buffers the
response before decoding. An actual SDK loopback probe confirms the missing JSON
byte bound. Candidate public HTTP client hooks now impose raw bytes, nesting,
elapsed time and aggregate tool-list bounds. Thirteen native Windows receive
tests pass, including large JSON/SSE, lexical-string boundaries, slow chunks,
compression/redirect refusal and early cancellation. The combined real-service
boundary batch passed 34 tests; this is local evidence, not full native release CI.

The failed formal run `36848916312` retains its original files. Duplicate fault 3
records ValueError, but the underlying call journal records A2AClientError at
1513.422 seconds after session start, with 0.183 seconds client elapsed. The
original completed call was offered at 21.418 seconds and took 0.809 seconds.
The fixture compared a caught transport error dictionary with the saved result
and called that inequality a changed receipt. Raw records do not establish the
transport root cause or a mutated database receipt.

Bounded diagnostic `cio-041-duplicate-local-v3` predeclared 12 duplicates and four
post-disconnection recovery queries over the existing restricted-role HTTPS
mesh. Four immediate and four two-second-aged replies match the saved original.
Four confirmed receiver-proxy exits produce transport errors, and all four
recovery queries match the original. Actual MCP actuator witnesses remain 9→9.
All 225 service/control/readiness calls are retained. V1 had a Path/string setup
validation failure before any request. V2 executed its 12 trials, but its assumed
proxy index addressed the verifier because MCP adds another proxy; its intended
disconnection comparison is invalid. Both are preserved. V3 uses the actual owned
receiver process path and confirms exit. This finite diagnostic does not recreate
the historical 1200-second soak state or resolve that historical cause.

## Real Gemma connection smoke

The dedicated loopback server reports Ollama 0.35.0 and logs `Ollama cloud
disabled: true` with `OLLAMA_NO_CLOUD=1`. It uses the already installed exact
`gemma4:e4b` digest
`dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c`,
reported 7.5B / Q4_K_M. No pull, existing-server configuration change, global unload
or external-model fallback occurred. The machine has Ryzen 7 8840HS, about 61.8
GiB RAM and Radeon 780M driver 32.0.21010.10. Default discovery excluded the iGPU;
the observed llama-server uses CPU, `/api/ps` reports `size_vram: 0` and context
4096. The installed model declares an MTP draft and default draft count 3; native
smoke requests explicitly send draft count 0. Compatibility requests use their
own documented surface and caused a separate default-draft runner load. Requested
settings and actual backend observations are distinct.

`cio-041-ollama-connection-smoke-v1` completed all ten offered attempts in 33.361
seconds, before any pilot or confirmatory evaluation. Native structured output
returned `{"answer":7}` and passed the program check. Deliberately plain `INVALID`
failed JSON parsing and was retained. Thinking with `num_predict=32` returned an
empty answer while reporting 36 prompt / 32 generated tokens. Tool-result history
and complete streaming returned usage from the same responses. Stream interruption
and the 50 ms deadline retain missing final usage and upper reservations; no
accounting retry was sent. Native duration fields are nanoseconds and are divided
by 1e9, and thinking tokens already belong to `eval_count`.

Chat Completions and stateless Responses returned 200 with numeric compatible
usage. The case named `responses-stateful-rejected` unexpectedly returned 200 for
a nonexistent `previous_response_id`; a successful HTTP response does not prove
stateful support. The official documentation says that flavor is unsupported.
The A/B harness will use native `/api/chat` through the public MAF integration,
which preserves explicit context/seed/think/options and raw native durations.
This smoke's initial observer conservatively reserved bounds for compatible
responses rather than parsing their usage; raw responses contain those counters
for a separate offline recalculation. Initial aggregate reservation/charge is
22755, which is not a claim of 22755 measured tokens. Five complete native
responses report 227 tokens, three compatible responses report another 54, and
two interrupted/timeout attempts have unavailable totals. No electricity meter is
available; local API charge zero does not mean zero compute or energy cost.

The optional packages are `agent-framework-ollama==1.0.0b260813` and
`ollama==0.5.3`, both MIT. Existing MAF core 1.19.0 remains locked. Five HTTP
test-double instrumentation tests are separately labelled; they are not Gemma
data. Raw `/api/show` includes third-party calibration paths and remains private
pending a documented original/public hash and path redaction. Weights are not
part of the code, wheel or planned result assets; model license metadata is
tracked separately from code Apache-2.0 and dataset/output provenance.

## Commands and sources

From the repository's frozen development environment, with an already prepared,
dedicated cloud-disabled server and public synthetic inputs:

```text
uv sync --all-extras --frozen
uv run python scripts/probe_local_ollama.py --host http://127.0.0.1:11439 --output NEW_RUN --server-log PRIVATE_SERVER_LOG
```

Every output directory is new. Intent and actual payload are saved before
dispatch; partial raw streams and host validation are separate files. This
command performs real local inference and is not the API-key-free deterministic
unit/demo command. The [task guide](gemma-041.md) documents completed pilot and
offline analysis commands. Preregistered confirmation and public raw assets
remain pending.

Primary interfaces:
[MAF native Ollama sample](https://github.com/microsoft/agent-framework/blob/main/python/samples/02-agents/providers/ollama/README.md),
[native chat counters](https://docs.ollama.com/api/chat),
[compatibility and stateless Responses](https://docs.ollama.com/api/openai-compatibility),
[cloud disable](https://docs.ollama.com/faq),
[exact model metadata/license](https://ollama.com/library/gemma4:e4b),
[public MCP transport customization](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/client/transports.md).
