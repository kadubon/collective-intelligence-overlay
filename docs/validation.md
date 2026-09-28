# Validation status

## 0.3.0 development checkpoint

The external observation-driven document application passed both three-process
E2E cases in 97.17 seconds, zero skips, with actual PostgreSQL, OPA, A2A HTTP and
MAF composition. Separate calibration inputs produced thresholds 2 and 4. Each
case retained two peer alternatives, rejected ordinary use of unverified C3,
restarted before checking C3, continued through independent checking and C4
formation with real receipts, replayed the saved business result after another
restart, and stopped after dependency withdrawal. The existing document E2E also
passed in the preceding combined three-test run (133.33 seconds); its implementation
was unchanged. Lint, formatting, package typing and generated documentation checks
passed. This is a deterministic application with a fixed domain priority, not a
completed adaptive allocation experiment or a 0.3.0 release gate.

The public proposal-contract increment passed 21 record, opportunity/step and real
A2A HTTP tests in 27.42 seconds, zero skips. The transport test exports only public
contract configuration, observes actual outgoing requests, and confirms private
checker input is absent. Exact targets remain the default; an explicit proposer
opt-in permits candidate versions while rejecting changed contract commitments,
scopes, checkers and output contracts. This tests authenticated assertions and local
constraints, not the truth of a foreign private decision. Lint, formatting, strict
typing (48 files) and generated schema/documentation checks passed. The full
three-process adaptive application and publication gates remain outstanding.

The candidate-target increment passed 15 opportunity/step and actual A2A proposal
tests in 31.50 seconds, zero skips. The host transition preserves the registered
contract, rejects changed issuer/scope/logical identity and stale goal versions,
invalidates old proposals, and rediscovers verification after configuration restore.
Candidate selection does not create PASS. Lint, formatting, generated docs/schema
checks and strict typing of 48 source files passed. The adaptive three-process
application, matched experiments and final release-wide gates remain incomplete.

The cooldown increment passed 19 opportunity/allocation, migration and actual
backup/restore tests in 27.34 seconds, zero skips. A new Steps instance reads the
saved allocation, keeps a qualified priority inside its window without renewing
that window, switches after expiry, and lets withdrawal-triggered repair override
cooldown. Strict typing covers 48 source files; release-wide validation is pending.

The claim-capacity increment passed 39 opportunity/allocation and invocation tests
in 59.75 seconds, zero skips, including the 0.2.1 allowance/cancellation/crash
regressions. A subsequent extended cross-page/reserved-allowance case passed in
the 12-test opportunity set (19.47 seconds). Concurrent claims in two budget units
admit only one at a configured capacity of one. Generated work cannot consume its
protected remainder; an explicitly configured checking claim can use that unit.
All checks are owner-local; they do not constrain trusted host code that elects to
use a different operator contract. Strict typing covers 47 source files.

The allocation increment passed 13 opportunity/allocation/step and real A2A tests
in 27.61 seconds, zero skips. Actual Registry/OPA checks cause verification work
to precede formation when a checker qualifies; withdrawal removes that priority
and cannot bypass the unverified-page limit. Static ordering remains available.
Lint, formatting and strict typing (46 source files) passed. Cooldown, reserved
capacity and cross-page backlog enforcement are not covered as completed features.

The finite-loop increment passed 12 opportunity/step and real A2A proposal tests
in 22.94 seconds, zero skips. Added cases cover no-progress termination, restart
without reproposal, zero allowance and a one-second deadline. This does not prove
adaptive allocation or concurrent capacity control across different opportunities.

The A2A proposal increment passed 15 proposal exchange, authentication, HTTP limit
and opportunity/step tests in 17.61 seconds, zero skips. Two real HTTP endpoints
returned different signed alternatives and stable replay IDs. Disabling one
peer's proposal authority preserved the other response and marked the disabled
peer unavailable. Foreign-goal substitutions and authenticated-issuer mismatch
were refused. These endpoints ran in one test process; this is transport evidence,
not the future three-process adaptive formation demonstration.

The persisted-binding increment passed 20 focused binding, reconstruction and
opportunity/step tests in 26.74 seconds, zero skips. Reconstruction includes a
separate interpreter loading the saved manifest, verifying stored evidence in
PostgreSQL and executing through OPA admission. Equal source with changed
parameters cannot reuse prior evidence. Lint, formatting, strict typing and
generated schemas passed. This does not yet verify the full adaptive application.

The subsequent single-step increment passed 15 focused opportunity, concurrent
choice, restart, UNKNOWN, migration and actual backup/restore tests in 18.54 seconds,
zero skips. Strict mypy covers 44 source files. This is incremental evidence, not
a replacement for the final full distribution and service release gates.

The first opportunity/proposal increment passed all 144 source tests in 296.21
seconds with zero skips, using actual PostgreSQL, OPA, MAF, A2A and MCP, including
the existing three-process applications, migration/restore and 1k/10k profiles.
Ruff, formatting, strict mypy (42 source files) and generated-schema/documentation
checks passed. The focused opportunity, reference, MAF and feed set passed 22
tests in 22.69 seconds. MAF proposal tests use deterministic local responses;
there were no paid model calls. This is not a 0.3.0 release gate: local selection,
durable steps, new formation experiments and clean 0.3.0 distributions remain
incomplete. The following 0.2.1 observations remain historical release evidence.

## 0.2.1

0.2.1 is published and verified. Final tag CI passed 129 Linux source tests,
128 installed agents tests plus one model check, and Windows package checks.
Actual PyPI installation passed 34 allowance/migration/restore/E2E checks, zero
skips, in 105.58 seconds. Artifact hashes and links are in [releasing](releasing.md).
The local checkpoint results below preceded that final gate.

Against actual PostgreSQL/OPA, new reproduction tests
failed on 0.2.0 for (a) authenticated/authorized binding use refused by input
applicability, with zero operation calls but balance 10 -> 9, and (b) cancellation
while reserved, balance 2 -> 1. Environment mismatch already failed before
reservation and was not treated as a newly discovered defect.

The current implementation passed 23 focused invocation tests (34.05 seconds),
including late DB-thread dispatch/claim completion, child refusal after a parent
effect, concurrent claim/cancel/dispatch/finish/cleanup, separate-unit conservation,
rollback and old-worker ownership. Subsequent ownership-read hardening is awaiting
its final run. Six migration/restore checks passed (8.43 seconds), including a
fixture generated by the actual published 0.2.0 package with original signed
payloads, PASS/FAIL/UNKNOWN, withdrawal and reserved/dispatched/completed histories.
Old reservations remain legacy unknown without changing balances.
An earlier full patch checkpoint passed 120 tests with zero skips (265.10 seconds);
later added cases were included in final CI and actual PyPI regression validation.

The [v0.2.0 release workflow](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36379126931)
passed on `394ba59`: 108 Linux source tests, 107 clean agents tests plus one
separately installed model check, and Windows unit/package tests. OIDC publication
succeeded. Both actual PyPI files matched CI hashes; a cache-disabled fresh PyPI
installation passed version/import/CLI and both E2Es (2 passed, zero skips,
68.97 seconds). Full artifact provenance and the initial index propagation delay
are recorded in [releasing](releasing.md).

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
checks plus one separately installed model check). Release CI subsequently checked
the final documentation and distributions on the exact tagged commit. These local
observations are separate from the release and post-install evidence above.

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
