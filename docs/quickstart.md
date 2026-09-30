# Quickstart and tutorial

Start with Python >=3.12 and uv. Minimum-version development uses the
`.python-version` pin; choose another interpreter explicitly, for example
`uv sync --python 3.14.7 --all-extras --frozen` and
`uv run --python 3.14.7 ...` for subsequent commands. See
[compatibility](compatibility.md) for measured release support.
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

## Register goals and run finite formation (0.3.0)

With the same services and a fresh directory, the complete external application
can be exercised without model credentials:

```sh
uv run python examples/evaluate_documents.py --directory .local/document-comparison --opa "$CIO_OPA" --seed 0
```

In PowerShell use `--opa "$env:CIO_OPA"`. This runs six isolated fixed/adaptive
arms, creating three peer identities/processes/databases for each arm. See
[evaluation](evaluation.md) for the signed raw pilot, inclusive costs, failed
checking-constrained arms and interpretation. Exit zero means collection completed,
not that every held-out contract passed. The data directory and private configs
remain local; publish only the explicit public export, never generated keys/configs.

The minimal application registration is in
[`configure_application`](../examples/adaptive_documents.py): it installs a word
counter and renderer, pins an independent checker, and registers two `Goal` values
with exact `UseRequest`, builder references, fixed checker inputs and allowed
proposal peers. The report builder consumes actual word counts; its output
parameterizes a persisted classifier. Checker calibration and ordinary-use denial
before PASS are part of the [three-process E2E](../tests/e2e/test_adaptive_documents.py).
To add your own tool, use `Registry.register_local(binding, operation, assess)`;
parameterized saved procedures use `register_artifact` with an installed factory.
The [registration example](../examples/reference_registration.py) shows actual
bindings and meaningful input assessments; the checker registration in
`AdaptiveDocuments.__init__` uses the same public interface. Do not load received
Python or let generated arguments replace the host's checker or permissions.

After registering bindings and obtaining their independent evidence, an existing
async host wires the public APIs as follows. `goals`, `registry`, `identity`,
`executor`, `owner_context` and `config` are the application's trusted registrations,
not values accepted from an agent. The external application supplies these and
persists target transitions; it is the runnable implementation of this wiring.

```python
from collective_intelligence_overlay.opportunities import Opportunities
from collective_intelligence_overlay.proposal_exchange import collect
from collective_intelligence_overlay.steps import Steps

opportunities = Opportunities(registry, identity, goals)
steps = Steps(opportunities, executor, owner_context, max_concurrent=4)


async def proposals(opportunity):
    goal = opportunities.goal(opportunity.goal_id)
    collection = await collect(config, registry.overlay.store, identity, goal, opportunity.id)
    return collection.replies


# One owner-controlled observation and step; handle an empty page explicitly.
page = await opportunities.discover(max_candidates=8)
if page.opportunities:
    opportunity = page.opportunities[0]
    result = await steps.step(opportunity.id, await proposals(opportunity))

# Or a finite host loop over the same durable choices and Executor.
run = await steps.run(proposals, max_steps=8, max_candidates=8, seconds=120)
```

Single-step use lets the host review one choice or materialize its output before
updating the target. The finite loop performs bounded discovery/allocation and stops
on no progress, allowance, deadline or step limit; it does not install returned code
or establish PASS. The document host surrounds actual construction with
`FormationSession`, publishes its signed candidate, persists `select_target`, and
then discovers the new verification deficit. Use that host pattern when your
builder needs materialization, rather than assuming `Steps.run` invents a procedure.

Inspect `opportunity`, `proposal`, `event` and `decision` with the existing CLI.
`metrics --work --query-file QUERY.json` requires local issuer, scope, policy digest
and creation period; ordinary event metrics describe the event period. Follow
`next_cursor` without summing repeated pages. Invocation lookup supplies durable
results after restart. For UNKNOWN reconcile the original ID; for unavailable
checking or shortage defer work; for withdrawal stop/requalify. The [API](api.md)
defines complete signatures, reasons, resource attribution and exit codes.

For a new host, the goal declaration fixes the target and independent checker
before proposals arrive. This is the declaration pattern in the tested document
setup; `target`, `checker` and `builder` are installed Binding objects, and
`readiness_arguments` are fixed operator checker inputs:

```python
from collective_intelligence_overlay.models import BindingRef, UseRequest
from collective_intelligence_overlay.opportunities import Goal


def ref(binding):
    return BindingRef(issuer=binding.issuer, id=binding.id, digest=binding.digest)


goal = Goal(
    id="report",
    revision="1",
    request=UseRequest(
        receiver=identity.name,
        capability_issuer=target.issuer,
        subject=target.subject,
        binding_digest=target.digest,
        scope=target.scope,
        semantic_fit="confirmed",
    ),
    checker=ref(checker),
    checker_arguments=readiness_arguments,
    builders=(ref(builder), ref(checker)),
    peers=("producer", "verifier"),
)
```

Confirm semantic fit only after the application's actual input/domain assessment.
The host installs the checker/builder, establishes their scoped evidence and
explicit grants, and supplies an existing owner allowance separately. Proposal
peers see the public commitment, not private checker inputs. Use [API](api.md)
for schemas, target persistence and `ProposalContract` registration.

## Registered document application (0.2.0 source checkout)

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
