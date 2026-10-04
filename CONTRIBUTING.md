# Contributing

Read [AGENTS.md](AGENTS.md) and [architecture](docs/architecture.md). Use Python 3.12
and `uv sync --all-extras --frozen`. Run Ruff, mypy, pytest and package checks from
the README. Full tests require a dedicated PostgreSQL admin URL and an OPA binary.
Paid model calls must remain explicit opt-in.

The 0.5.x maintenance scope prioritizes demonstrated bugs, security, compatibility,
operability and small usability corrections. Submit a minimized reproduction and
the affected trust boundary. Preserve originals and first failures; distinguish
intentional corrections from behavior-preserving refactors. Broader architecture
or feature proposals belong in separate issues and do not extend patch scope.
No response-time SLA, ongoing monitoring or feature delivery is promised.

Update tests and the relevant documentation with behavioral/API changes. Regenerate
schemas with `uv run python scripts/check_docs.py --write-schemas`. Add forward
Alembic revisions for database changes; preserve the released initial schema snapshot.
Keep SDK adapters thin and optional. Explain new dependencies and their license.
Do not weaken a negative-path test to obtain a release. New code uses Apache-2.0;
retain third-party notices where applicable.
