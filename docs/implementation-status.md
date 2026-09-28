# Implementation status

See [validation](validation.md) for current checks and [release state](releasing.md)
for publication. Historical development checkpoints are in Git history.

Implemented: typed records, DSSE, distinct peer authentication, PostgreSQL/Alembic,
OPA admission, bounded dependencies, local budgets/fencing, MAF/A2A/MCP connections,
three-process CSV/report lifecycle, opt-in provider example, microbenchmark,
documentation, schemas, skill and package/CI tooling.

Intentional scope: no global manager, new runtime/planner, broker, trustless database,
remote code execution, autonomous model spending or universal intelligence metrics.
Research inspection and non-guarantees are in [research mapping](research-mapping.md).
