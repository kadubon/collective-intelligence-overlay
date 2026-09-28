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

Preserve generated != verified != reusable. UNKNOWN never becomes PASS because of
delivery, timeout or missing data. Authentication is not truth. Retain dissent,
obligations, typed costs and invalidation lineage. Recheck at the actuator boundary.
Admission belongs to the receiver; keys, policy, permissions and budgets belong to
the operator. Do not execute received code or promote tool text into permissions.

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
