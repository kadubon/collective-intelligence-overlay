# Collective Intelligence Overlay

The [v0.4.4 bounded procedure pilot](docs/bounded-scratch-044.md) selects one to
three semantic enums and builds executable SQL/MAF procedures. It measures this
finite selection and reuse scope. Scratch SQL was 8/8 at both visited levels;
formation was 6/8 and 7/8. Both reached the declared ceiling, so independent
locked validation and confirmation were not started. All four M/C transfer and
restart paths worked; that diagnostic establishes no accumulation benefit.
[All results](docs/studies/bounded-scratch-044/results-v1/report.en.md) retain
failed offers and costs. The [v0.4.3 pilot](docs/near-transfer-043.md) and older
observations remain unchanged.

Let agents share tools and procedures with evidence and conditions for reuse.
For example, one agent offers a document workflow, a separate checker tests it,
and a receiver decides whether that exact version fits its data and permissions.
Each participant keeps its own keys, database, policy and budget:
**Evidence is shared; admission is local.**

This Python package adds qualified reuse and durable operation records to existing
Microsoft Agent Framework (MAF), A2A and MCP integrations. Existing SDKs run tools
and compose workflows; each owner chooses its own work. No collective manager is
required. The host and database operator remain trusted.

[日本語](README.ja.md) · [Tutorial](docs/quickstart.md) · [API/CLI](docs/api.md)

These instructions target **0.4.4**. Check the [release records](docs/releasing.md)
for actual publication, candidate hashes and validation status. The
[0.4.1 audit and local Gemma experiment](docs/gemma-041.md) records its measured scope;
the [0.4.0 production profile](docs/production-040.md) remains historical evidence.
0.4.1 is published on [PyPI](https://pypi.org/project/collective-intelligence-overlay/0.4.1/).
[GitHub Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.4.1) contains raw experiment/failure/native records and checksums.
The fixed 30-pair Gemma assessment passed 180/180 heldout tasks per arm; B−A was 0
at a ceiling, with no demonstrated adaptive advantage or equivalence.
See the [nine-part report](docs/release-041-report.ja.md).

The 0.4.2 work adds receiptless UNKNOWN recovery and a separate
[longitudinal study](docs/accumulation-042.md). Its [audit status](docs/audit-042.md)
distinguishes smoke, deterministic controls, completed calibration, independent
confirmation and actual publication. The second calibration retained 205 real
requests and found empty learned memory and insensitive family strata. Its
results establish neither retained-state benefit nor CIO-specific advantage.

## What it provides

- Versioned capabilities and independently issued PASS / FAIL / UNKNOWN evidence.
- Receiver-specific OPA decisions using exact bindings, actual inputs, environment,
  permissions, evidence freshness and known withdrawals.
- Owner-local PostgreSQL records, finite allowances, fenced leases and stable invocation IDs.
- Registered local functions, MAF workflows, MCP tools and A2A services; no received-code imports.
- Bounded discovery, proposal selection, formation and checking through existing executors.
- Installed application factories, readiness/drain, original-ID
  reconciliation, coherent backup, closed restore and scoped change trials.

Generated, verified and reusable are distinct states. A signature identifies an issuer,
and remote completion reports an operation state; neither establishes business truth.
Missing evidence and uncertain effects remain UNKNOWN. See [semantics](docs/semantics.md)
and [security](docs/security.md) for application scope, infrastructure trust and remote freshness.

## First run from the installed package

Use Python **>=3.12** and [uv](https://docs.astral.sh/uv/). Measured 0.4.1 candidate support covers
CPython 3.12.14/3.13.15/3.14.7 on Linux x86_64, Windows x86_64 and native macOS Intel/arm64.
Future interpreters are not covered by those results. In a fresh directory, on Linux/macOS:

```sh
uv venv --python 3.12.14 .venv
. .venv/bin/activate
uv pip install 'collective-intelligence-overlay[agents]==0.4.3'
collective-intelligence-overlay --version
collective-intelligence-overlay opa-install --target ./bin/opa
```

On Windows PowerShell:

```powershell
uv venv --python 3.12.14 .venv
. .venv/Scripts/Activate.ps1
uv pip install 'collective-intelligence-overlay[agents]==0.4.3'
collective-intelligence-overlay --version
collective-intelligence-overlay opa-install --target ./bin/opa.exe
```

The reference demo also needs a dedicated development PostgreSQL cluster and an operator
allowed to create test databases and roles. Follow [native OS setup](docs/quickstart.md);
Docker Desktop is not required. Set its URL in `CIO_TEST_DATABASE_URL`, then run:

```sh
collective-intelligence-overlay demo --directory ./demo-run --opa ./bin/opa
```

On Windows use `--opa ./bin/opa.exe`. No source checkout or model key is needed.
Expected fields: `processes: 3`, `admission: ACCEPT`, report total `117.00`,
`changed_environment: REQUALIFY`, `after_dependency_revocation: REJECT`.
Child processes stop; private keys, databases and artifacts remain. Use a fresh output
directory for each repeat. Demo authentication and DB setup are development fixtures;
[production deployment](docs/deployment.md) uses restricted roles and HTTPS.

Core supports records, policy and CLI. The `agents` extra adds MAF/MCP/A2A;
`model` adds the optional actual-model example. Paid inference is off by default and
requires explicit opt-in. PostgreSQL and OPA are external prerequisites. Installation
and import do not start services or download binaries.

The `ollama` extra adds the public MAF local Ollama client. It requires an explicit
loopback server and never pulls weights or selects a cloud fallback. The
[Gemma experiment guide](docs/gemma-041.md) describes execution from a clean installed package and
offline `verify` / `analyze` commands. The separate five-pair pilot and 30-pair
assessment both reached a ceiling. This establishes no adaptive quality advantage.
Use already installed exact `gemma4:e4b` on a dedicated cloud-disabled loopback
Ollama server; the measured CPU Q4_K_M profile used context 4096, one request at
a time and about 8.51 GB peak runner working set. Weights are not downloaded by CIO.

## Register your application

The wheel includes a complete local registration example.
After installation, generate its inert starter files:

```sh
collective-intelligence-overlay starter --directory ./my-application
```

The generated `application.py` contains schemas, caller grants, Registry registration
and candidate publication. Its installed equivalent is
`collective_intelligence_overlay.starter.application:configure`. Adapt it in your own
reviewed, installed package and select that factory explicitly in the owner configuration.
The tool body in the complete example is:

```python
async def count_words(arguments: dict) -> dict:
    return {"words": len(arguments["text"].split())}
```

Registration creates no independent PASS. Register a suitable checker and obtain scoped
evidence before ordinary reuse. [Integration](docs/integrations.md) shows complete
Registry/Executor and MAF/MCP/A2A wiring; [API](docs/api.md) specifies factory settings
and persistent call identities.

The installed document reference connects three configured peers: discover alternatives,
form a MAF report, independently check it, reuse it to form a classifier, and qualify
that classifier for a receiver. Known withdrawal blocks subsequent use until valid new
evidence and admission exist. Application contracts determine correctness; the core is
not confined to this reference task.

## Operate and assess

The declared initial profile has three permissioned owners, one service process and
restricted DB role per owner, configured HTTPS peers, installed tools and paid inference off.
HA, multiple active writers for one owner, external exactly-once and universal SLA claims
are outside its scope.

Read [configuration](docs/configuration.md), [deployment/recovery](docs/deployment.md)
and [troubleshooting](docs/troubleshooting.md). `drain` closes new effects;
original result queries remain available. Restored intake stays closed until verification,
full source sync, application-specific reconciliation and explicit owner resume.
Reconciliation queries saved provider IDs; it does not resend or automatically refund.

[Validation](docs/validation.md) retains native checks and failures.
[Soak](docs/production-soak.md) includes all offered outcomes.
[Matched experiments](docs/production-experiments.md) keep independent pairs, negative
results and separate resource units. They establish no general adaptive advantage or
intelligence growth.

For source development, clone this repository, run `uv sync --all-extras --frozen` and
follow [contributing](CONTRIBUTING.md). Mandatory service skips are not release validation.

New code is Apache-2.0: [LICENSE](LICENSE), [NOTICE](NOTICE),
[compatibility/licensing](docs/compatibility.md), [research mapping](docs/research-mapping.md)
and [release/upgrade history](docs/releasing.md).
