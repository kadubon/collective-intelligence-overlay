# Collective Intelligence Overlay

Collective Intelligence Overlay is an evidence-preserving capability lifecycle layer.
It connects original records of a tool or procedure to its verification, receiver
decisions, uses, costs and unresolved checks. It does not certify functional novelty,
causal contribution or intelligence growth.

For example, before using another agent's CSV tool, inspect the exact tool version,
what a separate checker tested, who accepted or rejected it, and which costs or
effects remain unknown. Each participant retains its own policy, keys and budget:
**Evidence is shared; admission is local.**

[日本語](README.ja.md) · [Start here](docs/start.md) ·
[Tutorial](docs/lifecycle-tutorial.md) · [API reference](docs/lifecycle-reference.md)

## Install and services

**These instructions target 0.5.1, the latest stabilization candidate.**
It corrects observation identity, missing purpose/validity, period coordinates,
handoff basis matching, bounded JSON input and standard A2A client cleanup.
It also releases execution allowance once when a fenced, still-owned invocation
is denied at the inner admission check before its actuator is entered.
The finite review and compatibility boundaries are in [the audit ledger](docs/audit-051.md).
At this source snapshot, native gates and publication are pending; the index
commands below become available when 0.5.1 is published. Check [release status](docs/releasing.md)
for actual hashes and verification. Published 0.5.0 and earlier versions remain
in the [archive](docs/research-archive.md).

Core record models and offline views need no running service or model. Owner database
inspection uses PostgreSQL; explicit qualification additionally uses OPA. Optional `[agents]`
integrates Microsoft Agent Framework (MAF), A2A and MCP; `[model]` and `[ollama]`
are separate optional model integrations. Finding credentials does not enable inference.

## First run from the installed package

Run from a fresh directory outside the repository. On Linux/macOS:

```sh
uv venv .venv --python 3.12.14
source .venv/bin/activate
uv pip install --no-cache --no-config --default-index https://pypi.org/simple collective-intelligence-overlay==0.5.1
collective-intelligence-overlay lifecycle inspect --fixture
```

On Windows PowerShell:

```powershell
uv venv .venv --python 3.12.14
. .venv/Scripts/Activate.ps1
uv pip install --no-cache --no-config --default-index https://pypi.org/simple collective-intelligence-overlay==0.5.1
collective-intelligence-overlay lifecycle inspect --fixture
```

The bundled input is **explicitly synthetic**. JSON retains PASS, different receiver
decisions, completed reuse, unavailable cost and withdrawal as separate observations.
It reports `current_admission: unassessed` and `execution_authority: not_granted`.
No database, network, model, tool or policy is invoked. Residual means a recorded
unresolved check, not an automatically assigned task or legal responsibility.

## Connect an existing tool

<a id="register-your-application"></a>

Follow the [model-free service tutorial](docs/lifecycle-tutorial.md): install `[agents]`,
register trusted local tools through the existing Registry/Executor, use independent
checks and receiver-local OPA decisions, then inspect actual reuse and withdrawal.
The tutorial uses a dedicated PostgreSQL service and OPA; it launches no model.
For a three-process peer deployment and your own application, continue with
[registration and network setup](docs/quickstart.md) and [integrations](docs/integrations.md).

## Five observations

<a id="what-it-provides"></a>

| Type | What it exposes |
|---|---|
| `CapabilityLifecycleView` | Exact candidate, evidence, historical decisions, use, costs and withdrawal |
| `ContributionObservation` | Copy, import, reuse, formation inputs and new candidate; no causal credit |
| `Residual` | Missing, unknown, stale or incompatible material with original references |
| `GrowthObservation` | Independent stock endpoints, period service observations and typed costs |
| `HandoffObservation` | Typed proposed/received/assessed material; no transport or execution grant |

The [SDK and CLI](docs/lifecycle-reference.md) use finite material or bounded owner pages.
`inspect_lifecycle`, `observe_contributions`, `observe_growth` and `build_handoff` are
read-only. Explicit `assess_stock` delegates to existing qualification and saves Decisions.
Core lifecycle imports no agent or transport SDK. Existing MAF/A2A/MCP adapters
retain execution responsibility; there is no new scheduler, event store or central manager.

## History, authority and data

<a id="operate-and-assess"></a>

Historical PASS, ACCEPT, a valid signature and a completed receipt are distinct from
current admission, execution permission and business quality. Execution still passes
the existing Executor gate. UNKNOWN, absent, FAIL, unperformed and expired material
remain distinct. Entry counts use declared record identities, not semantic ability counts.

The host, database operator and installed checker remain trusted. Read access is owner
restricted. References never fetch URLs or paths automatically. Explicit original export
preserves signed payload bytes; view JSON has its own digest. Keep private originals,
keys and logs protected. Pagination, expiry and deletion do not resolve uncertain effects.
See [concepts](docs/lifecycle-concepts.md), [security](SECURITY.md) and
[deployment/recovery](docs/deployment.md).

## Compatibility and verification

Python >=3.12; declared Linux, Windows, macOS Intel and Apple Silicon profiles remain
in the [runtime matrix](docs/validation.md). All twelve native profiles, mixed Python
and four cross readers passed for the exact published **0.5.0** pair; actual PyPI bytes and
clean-install checks are in [the implementation register](docs/lifecycle-050-implementation.md).
No DB migration or wire record change is introduced by the lifecycle layer.
[Migration](docs/migration-050.md) explains legacy missing bindings and clocks.

Source checks: `uv sync --all-extras --frozen`, `uv run ruff check .`, `uv run mypy`,
`uv run pytest`, `uv run python scripts/check_docs.py`, `uv build`.
Service skips are not evidence of a passing deployment. The repository is Apache-2.0;
dependency conditions are in [compatibility](docs/compatibility.md).

Historical negative and limited results remain in the [research archive](docs/research-archive.md).
CIO-specific accumulation benefit is unproven. No new model generation, research
comparison, benchmark or long soak is part of this stabilization release.
