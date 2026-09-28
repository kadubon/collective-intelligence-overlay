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
work budgets and three A2A server processes. It writes real formation/evaluation
CSVs into the chosen directory. The producer registers aggregate, renderer and
composite candidates. The verifier uses a separate checker; the receiver imports
signed evidence and applies its own OPA policy. MAF executes the two-stage report.
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
