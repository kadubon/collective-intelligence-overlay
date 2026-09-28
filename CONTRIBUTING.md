# Contributing

Read [AGENTS.md](AGENTS.md) and [architecture](docs/architecture.md). Use Python 3.12
and `uv sync --all-extras --frozen`. Run Ruff, mypy, pytest and package checks from
the README. Full tests require a dedicated PostgreSQL admin URL and an OPA binary.
Paid model calls must remain explicit opt-in.

Update tests and the relevant documentation with behavioral/API changes. Regenerate
schemas with `uv run python scripts/check_docs.py --write-schemas`. Add forward
Alembic revisions for database changes; preserve the released initial schema snapshot.
Keep SDK adapters thin and optional. Explain new dependencies and their license.
Do not weaken a negative-path test to obtain a release. New code uses Apache-2.0;
retain third-party notices where applicable.
