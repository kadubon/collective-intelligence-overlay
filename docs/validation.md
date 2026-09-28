# Validation status

Observed on 2026-09-28 with Windows CPython 3.12.10, PostgreSQL 16.15 on WSL
Ubuntu, OPA 1.21.0 and the frozen dependency set in `uv.lock`.

| Check | Observed result |
| --- | --- |
| Complete local service suite after registered CSV conversion | 106 passed, zero skips, 242.72 seconds |
| Subsequent commit/rollback and registered-checker negative cases, with focused suites | 10 passed, zero skips, 17.09 seconds |
| Clean wheel with core then agents, outside checkout, including both new cases | 107 passed, zero skips, 232.54 seconds |
| Model extra installed separately; actual provider adapter with mock HTTP | 1 passed, 1.70 seconds; no paid inference |
| Core import/version/path and CLI; sdist rebuild and reinstall | Passed, version 0.2.0 |
| Ruff check/format, strict mypy, generated schemas and documentation links | Passed |
| Build and strict twine check | Wheel and sdist passed |
| pip-audit | No known vulnerabilities among auditable dependencies; unpublished project 0.2.0 explicitly skipped by index lookup |
| License metadata | 129 distributions reviewed against the existing allowlist |
| CycloneDX 1.6 | 133 components generated |

The clean distribution run covers the full 108-test implementation (107 agents
checks plus one separately installed model check). Subsequent documentation-only
changes are checked again by release CI. These local observations do not by
themselves establish publication; exact-commit CI and actual PyPI installation
are recorded in [releasing](releasing.md).

The standalone evaluation command completed the three-process registered-A2A path:
ACCEPT, held-out total 117.00, changed environment REQUALIFY, dependency withdrawal
REJECT, with a durable execution receipt. All four deterministic comparison arms
returned 3/3 correct. This does not establish model-quality gains or a speed advantage.
The external document E2E separately verifies C3 composition, C3-based C4 formation,
independent checks, held-out results, CLI invocation, restart/result lookup, delta
synchronization and transitive withdrawal across three actual peer processes.

The suite uses real PostgreSQL, OPA subprocesses, official MAF APIs, A2A HTTP and
MCP HTTP. Negative paths cover identity/endpoint/tool/binding substitution, actual
child input/permission checks, FAIL/UNKNOWN/expiry, concurrent withdrawal, invocation
replay/conflict/cancellation, process death after an effect, and fenced budgets.
Sync tests cover complete prefixes under commit and rollback, scoped cursors,
interrupted/duplicate pages, final-page withdrawal and freshness that only advances
on completion. A signature or completed invocation never manufactures PASS.

Migration tests start from original v0.1.0 signed records, apply revisions through
0008 and preserve payload bytes, dissent, revocations and budgets. Interrupted
backfill is transactional. Actual PostgreSQL custom dump/restore is exercised,
including offline feed-generation rotation and freshness invalidation. Recovery of
operator keys/artifacts and reconciliation of work absent from a backup remain
operator responsibilities; see [deployment](deployment.md).

The mixed signed-history harness passed 1,000/10,000/100,000 profiles in 673.69
seconds. Each of five qualifications per profile verified four signatures, executed
nine DB statements and returned nine SELECT rows. [Raw reports and methodology](scale.md)
include type counts, dependencies, plans, bytes, Python allocation peaks, latency,
OPA cost and host conditions. The first stress attempt returned UNKNOWN because
fixture freshness preceded a long bulk load; the corrected fixture observes after
loading, without changing production freshness rules. No universal O(1) or latency
SLO is claimed.

The original v0.1.0 release passed 43 Linux source and clean-wheel tests, Windows
package checks, OIDC publication and actual PyPI hash/install verification. Its
history and artifacts are preserved in [releasing](releasing.md).

Service tests skip when explicit PostgreSQL/OPA configuration is absent. Release
Linux CI provides those services and must execute all mandatory checks; skips are
not successful validation. Windows CI covers portable unit/package behavior;
full Windows-to-WSL service checks are the separate local observations above.

Not established: paid model quality, resource-matched real-model comparisons,
independent organizations, external security audit, long-duration operation,
general semantic correctness, instantaneous remote revocation, arbitrary external
effect exactly-once behavior, physical erasure or general intelligence growth.
Dependency scanning is a point-in-time tool result, not an external security audit.
