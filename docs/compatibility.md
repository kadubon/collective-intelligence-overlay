# Compatibility and licensing

## 0.3.2 native release validation (2026-09-30)

All 12 mandatory native pairs passed the immutable release commit `b172c0d` in
[tag CI, attempt 2](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36705746853),
including source and normally resolved installed artifacts. The table below records
that tag's original pair; completed actual-index native checks are reported below.
The first attempt's two Mac Intel 3.14.7 source failures,
unchanged retry and reused successful jobs are retained in [validation](validation.md).
Every completed tag suite has zero failures/errors/skips; core smoke,
actual child/build runtime, licensing, known-vulnerability and SBOM checks passed.
Source elapsed times are observations, not normalized performance comparisons.

| Actual native runtime | Frozen source | Installed agents | Model | Rebuilt sdist | Resolved core/agents/model |
| --- | --- | --- | --- | --- | --- |
| Darwin amd64 / 3.12.14 | 291; 1670.429 s | 290 | 1 | 41 | 31/63/66 |
| Darwin amd64 / 3.13.15 | 291; 979.676 s | 290 | 1 | 41 | 31/59/63 |
| Darwin amd64 / 3.14.7 | 291; 1285.354 s | 290 | 1 | 41 | 31/59/63 |
| Darwin arm64 / 3.12.14 | 291; 571.807 s | 290 | 1 | 41 | 31/63/66 |
| Darwin arm64 / 3.13.15 | 291; 533.946 s | 290 | 1 | 41 | 31/59/63 |
| Darwin arm64 / 3.14.7 | 291; 492.769 s | 290 | 1 | 41 | 31/59/63 |
| Linux amd64 / 3.12.14 | 291; 606.759 s | 290 | 1 | 41 | 31/63/66 |
| Linux amd64 / 3.13.15 | 291; 561.461 s | 290 | 1 | 41 | 31/59/63 |
| Linux amd64 / 3.14.7 | 291; 646.362 s | 290 | 1 | 41 | 31/59/63 |
| Windows amd64 / 3.12.14 | 291; 618.986 s | 290 | 1 | 41 | 31/64/67 |
| Windows amd64 / 3.13.15 | 291; 1006.430 s | 290 | 1 | 41 | 31/60/64 |
| Windows amd64 / 3.14.7 | 291; 548.555 s | 290 | 1 | 41 | 31/60/64 |

Native Mac hosts reported macOS 15.7.9; Windows reported Server 2025.
Linux PostgreSQL was 16.15, native Windows/Homebrew PostgreSQL was 17.11,
and native OPA was 1.21.0. Four native readers passed all 12 producers' shared
golden artifacts and signatures; minimum/latest installed HTTP peers passed both
directions. Future interpreters, PyPy, free-threaded and other OS/CPU combinations
remain unverified. Actual tag/PyPI status is maintained in [releasing](releasing.md).

Fresh cache-disabled normal [actual-PyPI validation](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36716542836)
passed on the same 12 identities and original hashes. Every suite has zero
failures/errors/skips; all 36 installed profiles include the published root in
audit/license/SBOM checks. Actual child/backend interpreters, four readers, mixed
HTTP and final report validation also passed. Resolved counts include the root.
The source elapsed observations below do not measure normalized performance.

| Actual PyPI native runtime | Frozen source | Installed agents | Model | Rebuilt sdist | Resolved core/agents/model |
| --- | --- | --- | --- | --- | --- |
| Darwin amd64 / 3.12.14 | 291; 1048.877 s | 290 | 1 | 41 | 31/63/66 |
| Darwin amd64 / 3.13.15 | 291; 1025.786 s | 290 | 1 | 41 | 31/59/63 |
| Darwin amd64 / 3.14.7 | 291; 1107.395 s | 290 | 1 | 41 | 31/59/63 |
| Darwin arm64 / 3.12.14 | 291; 612.003 s | 290 | 1 | 41 | 31/63/66 |
| Darwin arm64 / 3.13.15 | 291; 633.354 s | 290 | 1 | 41 | 31/59/63 |
| Darwin arm64 / 3.14.7 | 291; 456.039 s | 290 | 1 | 41 | 31/59/63 |
| Linux amd64 / 3.12.14 | 291; 580.317 s | 290 | 1 | 41 | 31/63/66 |
| Linux amd64 / 3.13.15 | 291; 484.147 s | 290 | 1 | 41 | 31/59/63 |
| Linux amd64 / 3.14.7 | 291; 478.190 s | 290 | 1 | 41 | 31/59/63 |
| Windows amd64 / 3.12.14 | 291; 632.577 s | 290 | 1 | 41 | 31/64/67 |
| Windows amd64 / 3.13.15 | 291; 592.107 s | 290 | 1 | 41 | 31/60/64 |
| Windows amd64 / 3.14.7 | 291; 676.119 s | 290 | 1 | 41 | 31/60/64 |

The manifest table at the end declares required identities.
Its authority is `scripts/runtime-matrix.json`; Actions and report validation load
it, and `runtime_matrix.py --write-docs/--check-docs` generate/check that table.
Official [runner labels](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
identify `macos-15` as arm64 and `macos-15-intel` as Intel. Native PostgreSQL uses
Homebrew's located 17 tools in a private cluster, without Linux service containers
or an existing brew service. PostgreSQL retains its own license; Homebrew and macOS
retain separate terms. No Docker Desktop is required.

OPA's official [1.21.0 release](https://github.com/open-policy-agent/opa/releases/tag/v1.21.0)
provides reviewed Darwin amd64/arm64 assets; the package's `opa_install.py` is the
single pinned-checksum authority. It verifies native execution/version after the
download. No dependency range or license exception is added. `amd64` is normalized
x86_64; metadata >=3.12 still does not guarantee every future OS/CPU/Python.
Current observations and unverified gates are in [validation](validation.md).

The reviewed pg8000 1.31.5 is still the latest published driver. Its protocol
close can drop a buffered socket file after a failed flush, producing a later
unraisable Windows 10038 finalizer error. Store uses SQLAlchemy's documented
`do_connect` hook and a small connection subclass that delegates protocol close
then explicitly closes that buffer, retaining the original failure. This isolated
compatibility shim reads the known private `_sock` resource; it does not replace
the driver, protocol or transaction handling. That field is a maintenance constraint
to review when the driver changes, covered by physical-disconnect tests and the
mandatory native source/installed gates. No dependency range or license exception
is changed, and unraisable warnings remain errors. See
[pg8000](https://pypi.org/project/pg8000/) and
[SQLAlchemy's connection hook](https://docs.sqlalchemy.org/en/21/core/events.html#sqlalchemy.events.DialectEvents.do_connect).

## 0.3.1 published Python extension (2026-09-30)

Published metadata is `Requires-Python: >=3.12`, without an upper bound. The
[official release list](https://www.python.org/downloads/) was checked on
2026-09-30: stable CPython 3.12.14, 3.13.15 and 3.14.7 are mandatory. Python 3.15
was still prerelease at the final pre-publication check. Future Python, PyPy,
free-threaded builds and macOS are not verified support claims.

| Actual tag-CI runtime / OS | Frozen source | Original wheel: core / agents / model | Rebuilt sdist | Result |
| --- | --- | --- | --- | --- |
| Linux CPython 3.12.14 | 258; 539.884 s | Smoke / 257 / 1 | 31 | Passed |
| Linux CPython 3.13.15 | 258; 513.252 s | Smoke / 257 / 1 | 31 | Passed |
| Linux CPython 3.14.7 | 258; 444.310 s | Smoke / 257 / 1 | 31 | Passed |
| Windows CPython 3.12.14 | 258; 770.897 s | Smoke / 257 / 1 | 31 | Passed |
| Windows CPython 3.13.15 | 258; 702.762 s | Smoke / 257 / 1 | 31 | Passed |
| Windows CPython 3.14.7 | 258; 646.843 s | Smoke / 257 / 1 | 31 | Passed |

Every counted suite has zero failures, errors and skips. Core smoke checks version,
site-packages import, CLI and bundled resources. Both [main CI](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36672022262)
and [tag CI / OIDC publication](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36674642405)
passed on `e7e245920be3687eebb4b0a0817d60a82ed2c1b9`. Linux uses PostgreSQL
16.15; Windows CI uses a private native PostgreSQL 17.11 cluster. OPA is 1.21.0.
Windows runner OS is Windows Server 2025; local post-publication checks use Windows 11.
Elapsed observations are not normalized interpreter-performance comparisons.

Actual-PyPI core/agents/model installs use fresh environments, cache-disabled normal
index resolution and observed exact interpreters. All results below have zero
failures/errors/skips; all nine profiles passed license/audit/SBOM, including the
published root. Real local services are PostgreSQL 16.15 under WSL and OPA 1.21.0.

| Actual PyPI runtime / OS | Core | Agents | Model | Rebuilt sdist | Resolved core/agents/model |
| --- | --- | --- | --- | --- | --- |
| Windows 11 CPython 3.12.14 | Passed | 257; 1,060.63 s | 1; 5.07 s | 31; 4.18 s | 31/64/67 |
| Windows 11 CPython 3.13.15 | Passed | 30 unit; 3.64 s | 1; 3.55 s | 31; 3.27 s | 31/60/64 |
| Windows 11 CPython 3.14.7 | Passed | 257; 1,060.79 s | 1; 4.37 s | 31; 3.95 s | 31/60/64 |

Minimum/latest agents checks include all four installed audit regressions and the
complete service/E2E suite. The middle minor has full source/wheel service coverage
in CI and additional actual-PyPI unit/smoke coverage here. These are distinct runs,
not summed as independent evidence. See [validation](validation.md) and the
[public release reports](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.3.1).

Windows local services are PostgreSQL 16.15 under WSL and OPA 1.21.0. Earlier
prototype observations are retained in validation and are distinct from the final
release artifacts. The six jobs use the same
`ci_validate.py` definition, actual interpreter reports and separate coverage,
resolved-dependency, license, audit and SBOM artifacts. No required-service skip
passes the gate. `check_package.py --python` controls fresh venvs and records
actual CLI, pytest, demo children and PEP 517 backend interpreters. A test-only
startup guard contains no CIO application source and rejects checkout imports.

An ordinary-resolution installed-wheel test passed in both 3.12.14→3.14.7 and
3.14.7→3.12.14 directions: all 19 original 0.3.0 v1/v2/v3 DSSE payloads remained
byte-identical, each interpreter's 19 new signatures verified on the other,
and golden binding/request/call/manifest hashes matched. It covers large JSON
integers, Unicode, null, object/list ordering, explicit Decimal strings and aware
timestamps; raw Decimal arguments remain rejected by the existing JSON hash
contract. Saved parameterized bindings executed after cross-interpreter
reconstruction and real Numeric/timestamp/JSON PostgreSQL round trips. Real mixed
A2A peers synchronized evidence, returned samples 1/2/1 for two calls plus retry,
queried both saved IDs and blocked execution after withdrawal. This establishes
tested interpreter interoperability, not rolling old-package interoperability.

`uv.lock` retains all 135 previous third-party name/version pairs; only the project
version and additional platform/interpreter wheels changed. Ordinary resolution
is separate: the final clean installs also selected PyJWT 2.15.1, OpenAI 3.22.1, google-api-core
2.40.0, google-auth 2.59.0, proto-plus 1.29.0 and sse-starlette 3.5.0. Python 3.12
includes SDK marker dependencies aiologic/culsans/wrapt that newer minors omit.
Each actual profile is audited; no new allowlist exception or dependency range was
introduced. Actual uv_build 0.12.21 remained within the existing backend range.

Tag-CI normal-resolution distribution counts, including the first-party root, are
31/63/66 for Linux 3.12, 31/59/63 for Linux 3.13 and 3.14, 31/64/67 for Windows
3.12, and 31/60/64 for Windows 3.13 and 3.14 (core/agents/agents-model).
Frozen source counts are 132/129/129 on Linux and 133/130/130 on Windows.
Every actual profile has its own license, audit and CycloneDX report. Before
publication the candidate audit omitted only the unpublished first-party root;
actual-PyPI post-publication audits include it. No vulnerability ID or new license
was added to an ignore/allow list to pass the gates. Third-party packages retain
their own notices and redistribution obligations.

`.python-version` remains the minimum development pin. Select a different patch
with both `uv sync --python 3.14.7 --all-extras --frozen` and
`uv run --python 3.14.7 ...`. Pinned setup-uv v6's public `python-version` input sets
`UV_PYTHON` for CI; each matrix job also checks the observed exact patch.

The 0.3.1 changes add migrations 0013/0014, not a new DSSE,
binding or A2A format. Cause grouping and command receipts stay in owner-local
tables. Initial semantic observation fingerprints and original signed bytes are
preserved; renewed instances use the existing `supersedes` field and fresh bases.
The local Event 3 discovery validator additionally accepts expired/superseded
observations. Stop 0.3.0 writers before upgrading; this does not establish rolling
interoperability. The actual published 0.3.0 database fixture covers original v1/v2/v3
records and retained execution/lease/reservation states, with genuine PostgreSQL
backup/restore and interrupted-backfill rollback. See [validation](validation.md).

New A2A Registry child calls require explicit logical IDs plus a persisted host
scope or an existing Executor parent. Executor IDs supply this automatically;
MAF tools use public SDK call IDs and an explicit persisted host/session scope.
Local unscoped APIs retain their previous behavior. Migration 0014 preserves every
old invocation/remote ID and leaves unknown legacy child mappings empty. See
[the API](api.md#031-logical-remote-calls) for retry/query migration.

Version 0.3.0 adds Capability schema 3 and its DSSE media type
`application/vnd.collective-intelligence-overlay.record.v3+json` for explicit
formation inputs. Event schema 3 uses the same media type for local work
observations, with no execution/formation receipt or truth verdict. Existing record
versions are unchanged. Old readers reject
this new version; rolling interoperability is not claimed. Original v1/v2 payloads
remain stored verbatim, and signing those versions omits the new field. Admission
loads the new relationships through the existing bounded indexed subject closure;
the existing reverse `dependency` query continues to mean runtime dependencies.
This record version is distinct from package, binding, database and A2A versions.

Historical 0.3.0 resolution, observed 2026-09-28. `pyproject.toml` is authoritative for supported ranges;
`uv.lock` fixes the tested resolution. Initial interpreter support is Python 3.12.
Local checks used Windows CPython 3.12.10 and PostgreSQL 16.15 on WSL Ubuntu.

| Component | Observed version | License | Used public surface / source |
| --- | --- | --- | --- |
| agent-framework-core | 1.19.0 | MIT | [Agent, function middleware, workflow](https://learn.microsoft.com/en-us/agent-framework/concepts/agents/middleware/) |
| agent-framework-openai | 1.14.4 | MIT | Optional provider; Responses API via current public client; mock HTTP test |
| a2a-sdk | 1.1.5 | Apache-2.0 | [Official Python SDK](https://github.com/a2aproject/a2a-python); protobuf v1, JSONRPC, required extension |
| mcp | 2.2.0 | MIT | [Official SDK v2](https://github.com/modelcontextprotocol/python-sdk); Streamable HTTP client/server |
| Pydantic | 2.13.5 | MIT | Typed records, JSON/schema; installed distribution metadata |
| jsonschema | 4.26.0 | MIT | Direct core dependency for registered input/output contracts; [Draft 2020-12 validator](https://python-jsonschema.readthedocs.io/en/stable/validate/) |
| SQLAlchemy / Alembic | 2.1.1 / 1.20.0 | MIT | Transactions, PostgreSQL, explicit migrations |
| pg8000 | 1.31.5 | BSD-3-Clause | PostgreSQL driver; installed LICENSE inspected |
| securesystemslib | 1.5.1 | MIT | DSSE Envelope and CryptoSigner; no custom canonicalization |
| cryptography | 50.0.1 | Apache-2.0 OR BSD-3-Clause | Ed25519 and key loading; installed license inspected |
| PyJWT | 2.15.0 | MIT | [JWT validation](https://pyjwt.readthedocs.io/en/stable/usage.html); pinned EdDSA, aud/iss/exp |
| httpx / httpx2 | 0.28.1 / 2.13.1 | BSD-3-Clause | A2A and MCP SDK transport dependencies respectively |
| OPA | 1.21.0 | Apache-2.0 | [Official policy engine](https://www.openpolicyagent.org/docs); local `eval`, Rego v1 |
| PostgreSQL | 16.15 | PostgreSQL License | [Upstream license](https://www.postgresql.org/about/licence/); actual WSL binary tested |
| uv / uv_build | 0.12.19 | MIT OR Apache-2.0 | [Build backend](https://docs.astral.sh/uv/concepts/build-backend/); wheel/sdist and lock |

The MAF provider moved to a separate distribution and A2A/MCP changed their public
APIs in the tested release lines. Old import paths are deliberately not supported.

0.2.0 promotes the already resolved `jsonschema` package to a direct
core dependency; it does not update the existing SDK versions. This reuses JSON
Schema validation for MCP and application contracts instead of creating a schema
interpreter or compiling JSON Schema into new Pydantic types. External `$ref`
resolution is disabled. Contract shape does not establish semantic applicability.
No private SDK methods are patched. Different compatible patch releases still need
the same integration suite; a schema match alone does not prove semantic compatibility.

Core, `agents`, and `agents,model` are distinct installation scopes. Actual MAF tool
execution, A2A HTTP exchange, MCP HTTP and mocked provider HTTP are tested. Paid
model inference and arbitrary third-party A2A implementations are not claimed tested.
The 2026-09-30 clean candidate installation also resolved allowed patch/minor
versions including PyJWT 2.15.1 and uvicorn 0.54.0, while MAF 1.19.0, A2A 1.1.5
and MCP 2.2.0 remained as above. Its 188 agents tests plus separate provider test
passed; the fresh agents environment's 72 distributions passed the existing license
allowlist and known-vulnerability audit. This is a tested resolution, not blanket
support for every version in the dependency ranges. The project version itself
could not be vulnerability-index audited before publication. The published
0.3.0 actual-index environment subsequently passed the existing license
allowlist and known-vulnerability audit for all 72 distributions, including
the project, with no index skip. Public reports accompany the GitHub Release.
The standard non-overlay A2A adapter is tested against a separate official-SDK
HTTP server with an immediate JSON Message contract. Tests include card pins,
destination substitution, required extensions, unexpected Task/text responses,
oversized output and durable retry. No additional dependency or protocol engine
was introduced. Standard long-running Task continuation is not implemented.

`pip-licenses` supplies the full dependency report; `check_licenses.py` rejects unknown
or unreviewed metadata. This checks existing tool output rather than implementing a
license parser. Reviewed weak/file-level copyleft exceptions: certifi/fqdn (MPL-2.0,
runtime/transitive), hypothesis/pathspec (MPL-2.0, development), chardet (LGPL-2.1-or-later,
development), docutils (mixed public-domain/BSD/GPL development files). These packages
are not copied into this wheel; their own distributions retain notices/source terms.
Redistributors bundling dependencies must preserve their respective obligations.

No BSL, SSPL, evaluation-only service or proprietary container is required. The
PostgreSQL example uses the upstream official container image; its OS packages carry
their own licenses. Binary tests do not establish container security or full-image
license audit. SBOM generation uses cyclonedx-bom; known-vulnerability checks use
pip-audit. Metadata scanning does not replace legal review or supply-chain attestation.


<!-- runtime-matrix:start -->
| OS | Native CPU | Runner | CPython patches | Required scope |
| --- | --- | --- | --- | --- |
| Linux | amd64 | `ubuntu-latest` | 3.12.14, 3.13.15, 3.14.7 | full |
| Windows | amd64 | `windows-latest` | 3.12.14, 3.13.15, 3.14.7 | full |
| Darwin | arm64 | `macos-15` | 3.12.14, 3.13.15, 3.14.7 | full |
| Darwin | amd64 | `macos-15-intel` | 3.12.14, 3.13.15, 3.14.7 | full |
<!-- runtime-matrix:end -->
