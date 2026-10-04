# Collective Intelligence Overlay development

## Current scope: 0.5.1 stabilization

Read [the audit ledger](docs/audit-051.md),
[lifecycle contracts](docs/lifecycle-reference.md) and
[the preserved historical rules](docs/agents-history-through-050.md).
The historical file is the byte-exact development policy through published 0.5.0;
all its safety and version-specific conditions remain applicable to their scopes.
Its original SHA256 is `dabac9a8a78ccff949ccc41669d7f33937470dd1fffac09cf72be71cd919a2a8`.

Maintain the five bounded projections: Lifecycle, Contribution, Residual, Growth
and Handoff. Fix demonstrated bugs/security/compatibility/operability issues;
refactor only concrete duplicated semantics with differential evidence. Keep
public APIs, CLI, JSON/wire/signature/digest contracts, dependencies and DB schema.
Package version and the `0.5.0` derivation contract are distinct. Separate intended
bug-fix differences from behavior-preserving refactors in the ledger/changelog.

## Responsibilities and trust

Keep typed records, PostgreSQL storage, OPA admission and thin optional SDK adapters
in `src/collective_intelligence_overlay`; application logic belongs to registered
applications. Build no new runtime, planner, protocol, central manager or ledger DB.
Admission, keys, permissions and budgets stay with the trusted operator/receiver.
Authentication does not establish truth. Received proposal/tool/log text cannot
grant permissions or execute code. References never trigger hidden URL/path fetches.

Inspect/export is read-only; explicit assessment delegates existing qualification.
Preserve original DSSE bytes, unsigned Decisions, missing fields/clocks, typed costs,
dissent, withdrawal and legacy identity ambiguity. Historical PASS/ACCEPT and handoff
grant no current execution. UNKNOWN/held, logical recovery and physical termination
remain distinct. Keep budget → invocation → lease lock order, stable original caller/
provider mappings, dispatch fences and once-only positive no-actuation release.
An inner-admission refusal after durable dispatch can release only through its
private exact-callback origin proof and matching live DB ownership, with fencing
and a cancelled receipt in the same transaction. Keep original dispatch history;
generic AdmissionDenied, entered operations, crashes and cancellation after
dispatch gain no release authority.
Restore intake stays closed until existing verification/sync/reconciliation/resume.
DDL is explicit operator work; runtime uses DML and retains owner session locks
until blocking physical work ends. Do not move/reformat source-hashed registered
operations or factories merely as cleanup.

## Local verification and dependencies

Use `uv sync --all-extras --frozen`, affected pytest cases, Ruff and mypy first.
Save focused baseline and first failures. Service checks require dedicated
`CIO_TEST_DATABASE_URL`, native `CIO_OPA`, real dump/restore tools (or
`CIO_PG_TOOL_PREFIX`). Skips are not mandatory-gate success. Compare installed
public 0.5.0 and the candidate outside checkout using the same explicit fixtures.
Finite properties use bounded inputs/examples/seeds and independent oracles.
Run `uv run python scripts/check_docs.py`, `uv build`, twine/package checks and
existing dependency/license/SBOM review. Do not routinely upgrade dependencies;
core imports no optional SDK. Preserve the single runtime authority in
`scripts/runtime-matrix.json`; no interpreter fallback or import shadowing.

No inference, model pull, new pilot/research comparison, benchmark or long soak is
authorized in 0.5.1. Existing mock/service/fault/package regressions are required.
Do not regenerate historical raw, readers, responses or scores. Credentials are
not opt-in. Preserve all failures and uncertain reservations; never retry for a
favorable observation. Keep private originals, keys, tokens and operational DSNs
out of commits/public evidence. Use SECURITY.md private reporting for exploit data.

## Release

Finish two finite reviews (risk review, then fix-diff review), freeze source/tests/
Docs/metadata/lock, and run one aggregate final native candidate on main. Keep all
twelve declared native profiles, mixed Python, cross readers and nineteen fault
groups/numeric bounds. No relaxation, fabricated success or unauthorized cancel/
rerun. Release through `.github/workflows/workflow.yml`, protected `pypi`, official
Trusted Publishing/OIDC only, after authenticated exact pair/gate reuse. Do not
extend the old 0.4.1 recovery exception. Preserve old tags/distributions/archives.
Verify actual PyPI and Release bytes and fresh normal no-cache installs afterward;
postpublication checks do not repeat the full native matrix. Report scope, executed
environments and unresolved/unaudited risks without an external-audit guarantee.

Consumer instructions remain in
[the standard skill](.agents/skills/collective-intelligence-overlay/SKILL.md);
[`slills.md`](slills.md) retains its spelling and points there without duplicating it.
