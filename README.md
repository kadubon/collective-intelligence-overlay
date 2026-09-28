# Collective Intelligence Overlay

**Evidence is shared; admission is local.**

A Python overlay for teams that want agents to exchange reusable tools and procedures
without treating every generated result as verified. Each participant keeps its own
keys, database, acceptance policy and budget. A receiver can inspect a candidate,
request more checking, reject it, or reuse it under a specific contract.

The package connects Microsoft Agent Framework (MAF), A2A and MCP. It is not an
agent runtime or a central manager. Existing SDKs run tools and compose workflows;
the overlay records evidence, qualifies reuse and stops known-invalid dependencies.

[日本語](README.ja.md) · [Tutorial](docs/quickstart.md) · [Architecture](docs/architecture.md)

## What works

- Signed, versioned capability and evidence records, including PASS / FAIL / UNKNOWN.
- Receiver-specific OPA decisions: ACCEPT / REQUALIFY / REJECT / UNKNOWN.
- PostgreSQL persistence, duplicate/conflict detection, budgets and fenced result commits.
- Real A2A HTTP exchange, MAF function middleware/workflow composition and MCP HTTP calls.
- A three-process demo: form CSV tools, independently check outputs, reuse an HTML
  report workflow, then invalidate it by revoking its aggregate dependency.
- Typed costs and an explicitly limited deterministic comparison.

The 0.2.0 development checkout also supports typed local/MCP/A2A bindings,
durable invocations, paged synchronization/history and observed formation receipts.
An [external document application](examples/document_application.py) demonstrates
three peers building and checking C3, using it to construct C4, restarting and
stopping both descendants after withdrawal. See the [tutorial](docs/quickstart.md)
and [current validation scope](docs/implementation-status.md); 0.2.0 is not yet published.

A signature establishes origin, not truth. Sample checks do not prove correctness on
all future data. Distinct local identities are not independent organizations or
statistically independent evidence. This software does not prove intelligence growth.

## Run from source

Python 3.12, [uv](https://docs.astral.sh/uv/), PostgreSQL 16 and the OPA binary are
required for the reference path. No model API key is needed. There is no broker,
vector database, mandatory cloud service or always-running OPA server.

```sh
git clone https://github.com/kadubon/collective-intelligence-overlay.git
cd collective-intelligence-overlay
uv sync --all-extras --frozen
uv run python scripts/fetch_opa.py
```

Start a **dedicated development** PostgreSQL instance. The setup account must be able
to create roles and databases. See the [tutorial](docs/quickstart.md) for Docker,
Linux and PowerShell commands. Then:

```sh
export CIO_TEST_DATABASE_URL='postgresql+pg8000://postgres:development-only@127.0.0.1:5432/postgres'
export CIO_OPA="$PWD/.local/bin/opa"
uv run collective-intelligence-overlay demo --directory .local/demo
```

Expected fields: `processes: 3`, `admission: ACCEPT`, report total `117.00`,
`changed_environment: REQUALIFY`, `after_dependency_revocation: REJECT`.
Timings vary. The command preserves owner-local artifacts and databases and stops
its child processes. Use a new output directory for another run.

Version [0.1.0 is published on PyPI](https://pypi.org/project/collective-intelligence-overlay/0.1.0/).
To install into an activated Python 3.12 environment:

```sh
uv pip install 'collective-intelligence-overlay[agents]==0.1.0'
collective-intelligence-overlay --version
```

PostgreSQL and OPA are still required for the reference demo. Publication hashes
and clean-install verification are recorded in [releasing](docs/releasing.md).

## Add to an existing agent

Importing the core never opens a database or runs a migration. The host supplies
an `Overlay`, a pinned `UseRequest` and a trusted local operation:

```python
decision = await overlay.qualify(request)
result = await overlay.execute(request, registered_operation)
```

`execute` requalifies immediately before calling the operation. A previous ACCEPT
is not a permanent permission. [Integration](docs/integrations.md) shows MAF
middleware and the real, opt-in model example. See [API and CLI](docs/api.md) for
configuration, exceptions, cancellation and the operator/agent boundary.

For example, a verifier's PASS for `csv-sum@1` in environment `reference=1` does not
admit it in `reference=2`. The receiver requests requalification. A valid in-scope
counterexample is retained alongside the PASS and takes precedence in the standard policy.

## Trust and operation

Peers authenticate with distinct pinned Ed25519 identities. Local Rego policy,
keys and budgets must be protected from the agent process. Evidence sharing is
disabled by default; the demonstration enables it for its configured peers.
The DB/host operator is trusted. A malicious infrastructure administrator is outside
this model. See [security](docs/security.md) and [deployment](docs/deployment.md).

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv build
uv run twine check --strict dist/*
uv run python scripts/check_package.py
```

Integration/E2E tests require PostgreSQL and OPA; missing services are explicit skips,
not production validation. Paid model calls are off by default. Current checks and
unverified boundaries are in [validation](docs/validation.md). Windows and Linux are
the initial target platforms; the network reference deployment is Linux-oriented.

New code is Apache-2.0. See [LICENSE](LICENSE), [NOTICE](NOTICE),
[dependency compatibility/licensing](docs/compatibility.md),
[research mapping](docs/research-mapping.md), and [contributing](CONTRIBUTING.md).
