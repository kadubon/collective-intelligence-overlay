# Validation status

## 0.3.1 work in progress

CIO-030-01 was reproduced on Windows CPython 3.12.10 with PostgreSQL 16.15
and OPA 1.21.0. At 1,000 capabilities the old handler verified 1,002 signatures;
1,001/10,000 failed at the compatibility history-reader bound. The corrected real
authenticated A2A HTTP profiles at all three sizes passed (3 tests, 92.66 seconds).
Each revoke used 3 signature checks, 4 SELECT statements and 4 returned rows.
The fixtures mix original v1/v2 records, old versions, imported issuers and an
identical foreign subject. They also verify authentication/ownership/digest/missing
subject rejection, retained revocation, actual receiver synchronization and
rejection of the target and its dependent after sync. `CIO_REVOKE_COUNTS=100000`
selects optional stress; that new revoke stress has not been run.

CIO-030-02's signed unauthorized builder aborted both proposal orders before the
fix. The category/reverse-order regression set passed 18 tests in 32.22 seconds.
Real hostile A2A fixtures exercise normal candidates, reversed mixed same-peer
siblings, multiple peers, bad signatures, substituted references, oversized/malformed
containers, malformed JSON/RPC/card responses, all rejected candidates and unavailable
peers. A targeted source gate covering these cases, unit tests, existing exchange,
HTTP/authentication and revoke passed 84 tests in 113.73 seconds, with the known
CIO-030-03 expiry regression explicitly deselected. Database connection refusal,
immutable external conflicts, host assessment failures and cancellation remain
observable. This is local Windows CPython 3.12.10 evidence, not a released artifact.

After cancellation cleanup was added, the broader existing source regression passed
**222 tests in 992.87 seconds**, zero failures/errors/skips. The two still-failing
new reproductions for CIO-030-03 expiry and CIO-030-04 nested call identity were
explicitly deselected for this interim gate; it is not the final complete suite.
This run includes actual PostgreSQL/OPA/A2A/MCP/MAF, three-process applications,
backup/restore, invocation/allowance/cancellation and the default signed-history
profiles. Ruff, format, strict typing and generated-schema/doc-link checks passed.

CIO-030-03's initial expired-instance reproduction failed before its fix. The
current reobservation suite exercises 20 real PostgreSQL cases with controlled
clocks: expiry/proposal refusal, stable causes, fresh bases, owner checks, cooldown,
limits, concurrent requests, idempotent receipts, distinct CLI processes, budget
recovery, checker recovery, satisfied goals, revisions, retained negatives and
execution guards. Actual OPA freshness refusal yields an undispatched UNKNOWN with
fenced/released reservation; a later explicit owner attempt proceeds without
rewriting that original result. Dispatched/uncertain/pending work stays blocked.
Completed result reuse requires the original signed observation as well as request
content; changing evidence does not replay an old result as a current check.

A Windows CPython 3.12.10 source gate passed **67 tests in 178.29 seconds**, zero
failures/errors/skips: the new cases, existing opportunity tests, eight migration
tests and one actual three-process adaptive document case. A broader checkpoint
had 113 passes and two application refusals; the installed host needed explicit
checker intent under the new guard. Both previously failing parameter cases passed
after that host fix, including a separate two-case OPA-refusal/application gate
(64.77 seconds). These checkpoints are not the final complete source suite.
The 0.3.0 fixture was generated with the actual published wheel, outside checkout
on Python 3.12.10 at revision 0012. Original v1/v2/v3 signed history, selection,
six invocation/lease states and budget survive migration 0013 and real pg_dump/
pg_restore. Interrupted backfill rolls back. Missing legacy fields remain unknown;
the captured legacy remote ID is an actual old hash/InvocationStore fixture, not
proof of an old HTTP exchange.

CIO-030-04 was reproduced through the actual Registry parent/A2A path: two equal
inputs caused only one provider execution before the fix (the direct Executor
path already passed). Explicit child IDs now separate those calls. A new real
PostgreSQL/A2A gate passed **8 tests in 66.24 seconds** on Windows CPython 3.12.10:
sequential and parallel changing read-only samples, concurrent retry, changed
arguments/binding/purpose/permissions/environment, owner/caller/session/parent
namespaces, bounded lookup and unauthorized caller refusal, real MAF tool calls
and exported/restored AgentSession, and actual MAF composite workflow.
The test's counter is a persistent sampling witness; it is not a promised domain
side effect or a provider cache double. A real HTTP result is dropped after the
provider completes; distinct provider and caller processes then restart. Query
returns the saved child's completed result without another sample, while the
parent remains UNKNOWN/dispatched/held and its second child remains unissued.
Initial fixture digest, unauthenticated readiness and response-drop matching errors
were corrected separately and are not audit reproduction evidence.

The final C4 source checkpoint passed **102 tests in 233.36 seconds**, zero
failures/errors/skips, on the same Windows CPython 3.12.10 services. It includes
ten C4 cases, all unit tests, existing invocation/lease/cancellation/allowance,
eight migration/backup tests, registered bindings, MAF/MCP/A2A SDKs, lineage,
standard A2A and persisted reconstruction. Added checks retain the provider's
verification-purpose grant and join a delayed real mapping commit before cancelled
host cleanup. Actual 0.3.0 upgrade to 0014 keeps the legacy remote UNKNOWN and its
held allowance, queryable by original caller/ID, with an empty new mapping.
The preceding broader run had 98 passes and three fixture errors (unchanged binding
revision and wrong legacy caller); those errors were fixed, not marked skip/xfail.

These local observations do not establish the new multi-Python, installed-artifact
or release gates. The complete new-Python suite and support extension are pending.
Existing released-version facts below are historical evidence.

## 0.3.0 released artifacts

The exact release commit `a2fc32b` passed [main CI](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36637949588)
and [tag CI](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36639581573); the existing OIDC workflow published those tested files.
Tag CI: 189 passed in 427.35 seconds; clean agents 188 passed in 299.24 seconds; separate
model adapter 1 passed in 1.10 seconds. Windows source/installed unit tests and the
mock provider, core import/CLI/resources, sdist rebuild/reinstall, lint/type/docs,
security/license/SBOM/build gates passed. No mandatory-service skips or paid calls.
Linux used CPython 3.12.3 and Windows used 3.12.10. Source coverage was 85%;
subprocess coverage is not aggregated.
The actual-index environment's 72 distributions also passed the existing license
allowlist and a known-vulnerability audit with no project-version index skip.

An actual-PyPI, cache-disabled fresh Python 3.12.10 installation outside checkout
passed **89 tests in 532.69 seconds**, zero failures/errors/skips, including all eight
three-process E2E cases and migration/restore/UNKNOWN/allowance regressions. Installed
MAF 1.19.0, A2A 1.1.5 and MCP 2.2.0 used their public APIs with real
PostgreSQL 16.15/OPA 1.21.0.
Actual downloaded wheel/sdist SHA-256 match tag CI. See [release facts](releasing.md)
and its public sanitized install report. These checks verify the declared finite
integration; they do not establish adaptive benefit, external independence or audit.

## 0.3.0 source checkpoints

The release-wide source suite for the code at `e94ce84` passed **189 tests in
910.96 seconds, zero skips**, on Windows CPython 3.12.10 with real PostgreSQL
16.15 in WSL, OPA 1.21.0 and MAF/A2A/MCP. It includes both mixed-history and
signed-work 1k/10k profiles. Coverage is 85%; subprocess coverage is not aggregated.
Ruff/format/mypy, schema/docs links and canonical skill validation passed.
`pip-audit` found no known vulnerabilities in auditable dependencies; it explicitly
could not audit the unpublished project 0.3.0 against PyPI. The existing license
allowlist accepted 129 installed distributions; CycloneDX 1.6 contains 133 components.
Wheel/sdist build and strict twine checks passed. The clean installed-artifact suite
passed 188 agents tests (874.19 seconds) plus one model adapter test (2.56 seconds),
zero skips, outside the checkout; core import/CLI, packaged resources and sdist
rebuild/reinstall also passed. Those artifacts contain the code at `e94ce84`.
The final lineage delay guard retains UNKNOWN/probe/foreign-owner observations but
does not assign them completed-use delays; four focused real-service tests passed
in 14.30 seconds after that change. The exact-commit CI and actual-index
validation subsequently passed as recorded above.
Historical checkpoints below apply to their source and are not substitutes for
the final installed-artifact/release checks.

[Candidate CI at e94ce84](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36635267408)
passed Linux source 189 tests (399.08 seconds), clean agents 188 tests (270.68
seconds), model one test (0.94 seconds), all audit/license/build/docs gates and
Windows source/installed unit 30/30 tests plus model/package checks. These are
pre-publication checkpoints. The final guard subsequently passed the exact
release CI's source and clean-artifact gates and actual-index regression above.

| Completed observation | Result and scope |
| --- | --- |
| Full source at `5034100` | 185 passed, zero skips, 792.81 seconds; Windows CPython 3.12.10, real PostgreSQL 16.15 in WSL/OPA, MAF/A2A/MCP |
| Staged migration/restore at `7e9a50f` | 7 passed, zero skips, 9.59 seconds; original 0.1/0.2/actual-PyPI 0.2.1 signed records and budget/invocation rows |
| New signed-work 1k/10k discovery | 2 passed, zero skips, 57.08 seconds; fresh/deduplication bounded-query assertions |
| 100k mixed/work stress | Both raw reports saved after profile assertions; terminal footer/exit status unavailable after interrupted session |
| Resource/lineage metrics increment | 4 passed, zero skips, 14.70 seconds; no receipt-context double charge or invented checking/installation |
| Connection/application/experiment increment | 11 passed, zero skips, 369.44 seconds; same installed adapter and checker, real three-process E2E |
| Saved experiment archive consistency | 5 passed, zero skips, 10.24 seconds; both pilot archives plus tampered budget/outcome rejection |

The first attempts at the current metrics tests failed to connect to a stopped
test PostgreSQL. Its existing data directory recovered normally after restart;
the focused suite then passed. These infrastructure failures are not counted as
passing tests or hidden as skips. The final source log is retained locally.

Migration tests explicitly inspect 0.2.0 at 0009 before advancing to head. The
0.2.1 fixture comes from isolated Python execution against the verified actual-PyPI
installation, retains seven signed records and five lifecycle states, and contains
public keys only. Tests compare complete record/budget/lease/invocation rows across
migration and real pg_dump/pg_restore. Unknown consumption, original envelopes,
result lookup and release-once behavior persist. This is lifecycle compatibility,
not rolling support with old live workers or a business-quality proof.

The six isolated [matched pilot arms](evaluation.md) retain 858 signed records,
18 databases, original source/protocol and all failures/censored outcomes. Normal
and connection arms each check two formations and pass three held-out business
tasks; checking-constrained arms check one formation and do not reach those tasks.
There is no observed outcome or allowance benefit, and adaptive elapsed time is
higher in each single-run pair. CPU/tokens/currency are unavailable; local identities
are not independent organizations. [Scale methodology and raw data](scale.md)
distinguish old qualification from new discovery profiles.

Critical branches cover duplicate causes, stale/altered references, unknown schemas,
independent alternatives, unavailable peers, untrusted MAF output, denied checker,
capacity/budget races, durable choice replay, delayed DB-thread cancellation,
uncertain effects, parameter/component changes, source withdrawal, bounded sync and
exact policy/scope/time filtering. The [completion matrix](implementation-status.md)
maps requirements to code and tests. Coverage is a development diagnostic, not a
business-quality or security certificate. Paid model inference, external audit,
long-term operation and multi-organization superiority remain untested.

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
rollback and old-worker ownership. Subsequent ownership-read hardening was included in the final release suite. Six migration/restore checks passed (8.43 seconds), including a
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
