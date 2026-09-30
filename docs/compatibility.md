# Compatibility and licensing

The unreleased 0.3.1 reobservation change adds migration 0013, not a new DSSE,
binding or A2A format. Cause grouping and command receipts stay in owner-local
tables. Initial semantic observation fingerprints and original signed bytes are
preserved; renewed instances use the existing `supersedes` field and fresh bases.
The local Event 3 discovery validator additionally accepts expired/superseded
observations. Stop 0.3.0 writers before upgrading; this does not establish rolling
interoperability. The actual published 0.3.0 database fixture covers original v1/v2/v3
records and retained execution/lease/reservation states, with genuine PostgreSQL
backup/restore and interrupted-backfill rollback. See [validation](validation.md).

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

Observed 2026-09-28. `pyproject.toml` is authoritative for supported ranges;
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
