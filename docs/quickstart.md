# Quickstart and tutorial

Start with Python 3.12 and uv, then `uv sync --all-extras --frozen`.
`uv run python scripts/fetch_opa.py` downloads OPA 1.21.0 and checks a pinned hash.
Windows x64 and Linux x64 downloads are supported. For another platform, install
the official OPA binary yourself and set `CIO_OPA`.

Use a dedicated development PostgreSQL instance. Example with Docker:

```sh
docker run --name cio-postgres -p 127.0.0.1:5432:5432 -e POSTGRES_PASSWORD=development-only -d postgres:16.15
export CIO_TEST_DATABASE_URL='postgresql+pg8000://postgres:development-only@127.0.0.1:5432/postgres'
export CIO_OPA="$PWD/.local/bin/opa"
```

PowerShell environment syntax:

```powershell
$env:CIO_TEST_DATABASE_URL='postgresql+pg8000://postgres:development-only@127.0.0.1:5432/postgres'
$env:CIO_OPA=(Resolve-Path .local/bin/opa.exe).Path
```

An existing PostgreSQL 16 installation also works; point the URL at a dedicated
development cluster. The bootstrap user needs `CREATEDB` and `CREATEROLE`; peer
runtime roles do not. Do not bootstrap into an unrelated production cluster.

```sh
uv run collective-intelligence-overlay demo --directory .local/demo
uv run collective-intelligence-overlay doctor --config .local/demo/receiver/config.json
uv run collective-intelligence-overlay inspect --config .local/demo/receiver/config.json decision
uv run collective-intelligence-overlay metrics --config .local/demo/receiver/config.json
```

The demo creates random database roles/databases, per-peer signing keys, bounded
work budgets and three A2A server processes. It writes real evaluation CSVs into
the chosen directory. The producer registers aggregate, renderer and composite
candidates. The verifier probes those bindings and independently checks the output;
the receiver imports remote-service bindings and obtains separate checks for them.
It applies its own OPA policy before calling the provider through A2A. MAF executes
the two-stage report, with separate child admission. This installs known functions;
the document application below demonstrates observed-use formation.
Changing the environment requires requalification; revoking the aggregate blocks
the composite. Child processes stop, but keys, databases and result artifacts remain.

Inspect `result.json`, per-owner `artifacts`, and immutable DB records. Never publish
the generated config or key files. A new run requires a new directory because prior
records and revocations must not be overwritten. To restart a peer:

```sh
uv run collective-intelligence-overlay peer --reference --config .local/demo/receiver/config.json
```

Restarting does not clear revocations. Remote source freshness must be re-established
through a successful `sync`, and the previously revoked candidate stays rejected.

For a matched mechanism microbenchmark:

```sh
uv run python scripts/evaluate_reference.py --directory .local/evaluation
```

See [evaluation](evaluation.md) before interpreting its timings. The demo is a finite
test driver, not an autonomous global planner. [Configuration](configuration.md)
describes bounded controls and ownership. [Troubleshooting](troubleshooting.md)
explains common failures.

## Registered document application (0.2.0 development checkout)

With the same dedicated PostgreSQL/OPA environment and a new output directory:

```sh
uv run python examples/document_application.py --directory .local/documents
```

This application lives outside the package. A publishes an installed whitespace
word counter; B probes it under an explicit read-only verification grant and checks
its output using a separate implementation. C registers a remote-service binding
and a local renderer, composes C3 with the actual MAF workflow API, then uses C3's
calibration output to construct a threshold-based document triage capability C4.
B independently checks each candidate before ordinary reuse. Formation, checking
and held-out inputs differ; the example contains no finite lookup table or model call.

`document-results.json` records C3/C4 execution-receipt links, held-out output,
three distinct peer PIDs, restart/replay, current admission and paged metrics.
Expected results include two accepted capabilities before withdrawal, zero after
withdrawal, and two REJECT decisions for the descendants. C restarts from its
owner-local artifacts and retains the original completed invocation result.
The preinstalled functions reconstruct only this known application; artifacts do
not contain executable code or a workflow language.

`propose_document_formation` is a public MAF `FunctionTool` and can be supplied to
an ordinary `Agent(client=operator_client, tools=[propose_document_formation])`.
It returns a bounded proposal for an installed stage, without granting authority.
The no-key driver invokes that same tool with deterministic inputs and submits the
proposal as the receiver's operator. The receiver still checks its own construction
limits, bindings and budget. Model-based autonomous discovery is not claimed.

The script provisions and drives a finite test sequence, with independent peer
processes, keys, databases, policies and budgets. This is a local interoperability
test, not evidence of organizational/statistical independence or causal improvement.
Construction is an operator action; interrupted construction must be inspected,
not blindly retried as a new attempt. The generic invocation route supplies durable
result lookup and retry for actual capability calls. Restart one application peer:

```sh
uv run python examples/document_application.py --config .local/documents/receiver/config.json
```
