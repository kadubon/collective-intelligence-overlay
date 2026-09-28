# Collective Intelligence Overlay development

Build a thin overlay for evidence sharing and receiver-local capability admission.
Do not build an agent runtime, workflow engine, protocol implementation or global manager.
Use neutral reasoning and distinguish observations from claims.

`src/collective_intelligence_overlay` holds typed records, PostgreSQL storage,
OPA admission, SDK adapters and deterministic reference applications. Keep example
business logic out of the generic core. `tests` covers unit, integration and E2E paths.

Use `uv sync --all-extras --frozen`, `uv run ruff check .`, `uv run ruff format --check .`,
`uv run mypy`, `uv run pytest`, and `uv build`. PostgreSQL and OPA tests need
`CIO_TEST_DATABASE_URL` and `CIO_OPA`; skipped services are not validation success.
Real restore tests also require `pg_dump`/`pg_restore` (or `CIO_PG_TOOL_PREFIX` for
the WSL test client). The default suite runs 1,000/10,000-record scale profiles;
`CIO_SCALE_COUNTS=100000` selects stress. Keep timing observations separate from
assertions on bounded rows, signature checks and query counts. See `docs/scale.md`.
Check generated schemas/docs with `uv run python scripts/check_docs.py`, and clean
artifacts with `uv run python scripts/check_package.py` after `uv build`.

Preserve generated != verified != reusable. UNKNOWN never becomes PASS because of
delivery, timeout or missing data. Authentication is not truth. Retain dissent,
obligations, typed costs and invalidation lineage. Recheck at the actuator boundary.
Admission belongs to the receiver; keys, policy, permissions and budgets belong to
the operator. Do not execute received code or promote tool text into permissions.

New execution paths use explicit Registry bindings and persistent Executor IDs.
Recheck actual child inputs independently; never inherit a parent's semantic fit.
Verification probes require read-only operator grants and do not create PASS,
ordinary reuse or observed-use formation links. Remote interface pins are not
code attestation. Preserve caller/resource-owner boundaries and UNKNOWN outcomes
after uncertain side effects; reservations are not measured consumption.
For 0.2.1 invocation release, lock budget then invocation then lease. Confirm
reserved phase and matching worker/fence, revoke dispatch and return allowance in
one transaction. Never release from an exception type or Python cancellation flag.
Keep measured inspection overhead and legacy/uncertain reservations; old workers
must not settle replacement leases. Test delayed DB-thread commits and cancellation.

Keep original v1 DSSE bytes/envelopes during migration. Indexes are projections,
not replacement records. Preserve legacy issuer/binding ambiguity. Feed sequence
allocation must remain commit ordered; completed scoped sync, not heartbeat, grants
freshness. Do not let replay or backup restoration renew stale observations. Follow
`docs/deployment.md` for offline generation rotation and post-backup reconciliation.

Add dependencies only for a demonstrated public integration, with license and
compatibility evidence. Keep optional SDK imports out of the core import path.
Public API changes need corresponding behavioral tests, docs and changelog entries.
Do not duplicate OPA rules in Python. Use maintained cryptographic/protocol libraries.

Never commit credentials, private artifacts or local research downloads. Paid model
tests require explicit opt-in; discovering credentials is not opt-in. Tests may use
loopback services. Production endpoints require HTTPS and explicit allowlists.

Publish only through `.github/workflows/workflow.yml`, environment `pypi`, using
Trusted Publishing. Release only after required checks and artifact installation
tests pass. Preserve environment protections and existing history. Report genuine
blockers and unverified cases. Never disguise a failed release with skip-existing.
