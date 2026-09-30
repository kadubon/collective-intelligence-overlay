# Validation status

## 0.3.2 native pre-publication validation

Implementation commit `a03a59e3b5ac94425785a3e8d3e3d944699db6bc` passed
[main CI](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36700000778).
Every Linux/Windows/Mac Intel/Mac arm64 x CPython 3.12.14/3.13.15/3.14.7 pair
passed **291 frozen source tests, 290 normally installed agents tests, one model
test and 41 rebuilt-sdist tests**, plus core import/CLI/resources. Every mandatory
suite had zero failures, errors and skips. Actual child/backend interpreters and
native CPUs, lint/format/type/docs, license/audit/SBOM and candidate hashes passed.
Linux used PostgreSQL 16.15; Windows and both Mac CPUs used native PostgreSQL
17.11; OPA was 1.21.0. Four installed native readers each verified 228 new
signatures from all 12 producers and the same legacy payload/golden hashes.
Minimum/latest installed peers passed actual HTTP in both directions. These are
shared-artifact cross-platform checks and within-runner HTTP, not cross-host
public networking or independent external audit.

The complete reports were also downloaded and checked with `check_matrix.py`.
Native safety gates are complete; tag/OIDC publication and actual-PyPI checks
remain required. The documentation-finalized tag must test its own single original
pair before publication. Exact runtime observations are in
[compatibility](compatibility.md), and publication state is in [releasing](releasing.md).

CIO-031-01 was reproduced on Windows CPython 3.12.14 with real PostgreSQL
16.15 under WSL: two expired reserved/dispatched cases refused a distinct ID with
`owner invocation capacity exhausted`, without old-ID queries. Both failed before
the change. After common fenced expiry and capacity-triggered cleanup, both cases
plus 31 existing invocation regressions passed: **33 tests / 57.66 s**, zero skips.
These are controlled real-DB expiry cases, not physical process-stop evidence.

Actual worker/cleanup process-tree termination, DB backend disconnection, cross-unit
cleanup/claim/get/cancel/finish races, native paths/socket restart/TLS verification
passed **15 tests / 32.33 s** after correcting Windows venv-launcher termination.
Separate cleanup/installer failure checks passed **22 / 21.43 s**. Original
0.1.0–0.3.0 and actual-0.3.1 migration/restore checks plus delayed DB-thread commit
passed **23 / 46.84 s**. Suites overlap and are not added as independent cases.
The 0.3.1 fixture was produced with its actual published wheel/hash; all original
rows, signatures and remote call references survive 0015 and backup restoration.
Expired undispatched work releases once; uncertain effects keep held allowance.

The local complete source run had **289 passes and one test-config failure**:
its `SimpleNamespace` omitted the new finite owner limits. After making that
fixture explicit, all **22 related service/native/cleanup tests passed in 68.43 s**,
zero skips, including the public unresolved-effects reason and continued old-ID
queries. This focused correction is not substituted for the complete native CI.

The next native candidate passed full source/installed gates on all three Linux
and all three Mac arm64 patches, but Windows 3.14.7 had **289 passes / one error**
from pg8000's socket-buffer finalizer after backend termination. It is not a passed
matrix. A real owned-transport cutoff reproduced Windows 10038 locally; after the
scoped resource-close shim, both physical-cutoff and backend-termination regressions
passed on Windows CPython 3.14.7 (**2 / 3.24 s**, zero skips). Original errors,
rollback, rerunnable cleanup and held/released balances remain checked. Native
matrix validation of the corrected implementation subsequently passed above.
The corrected Windows 3.14.7 focused suite then passed **64 / 135.30 s**, zero
failures/errors/skips: cleanup, original invocations, all historical migrations/
restore, reference registration, native paths/process restart and TLS.

Representative Linux x86_64 / WSL CPython 3.12.14, PostgreSQL 16.15 and native OPA
1.21.0 passed the 100,000-record mixed-history, exact-owner authenticated revoke
and invocation-cleanup profiles at source commit `6f13d3e`; these observations
precede the later driver-close compatibility change. Each qualification verified four
signatures and returned nine rows with nine statements. Exact revoke used three
signature checks and returned four rows. Cleanup returned one row with 17 statements
and retained live work and balances. These are fixture bounds, not latency SLOs.
The combined run had three passes and one pre-setup work-history failure because
pytest reused Windows bytecode in WSL, leaving an unavailable Windows source path.
With separate caches, the remaining work-history profile passed **1 / 318.18 s**,
zero skips. No product code or comparison bounds changed for this rerun.
The first combined run is not reported as four passes. Raw completed observations
are in [mixed history](measurements/scale-032-100000.json) and
[invocation cleanup](measurements/invocation-cleanup-032-100000.json), plus
[work history](measurements/work-scale-032-100000.json).

CIO-031-02 adds native OPA assets, atomic explicit installation, isolated native
PostgreSQL and one 12-pair manifest. Windows actual OPA installation passed in a
Unicode/space directory. **Native Mac CI, the complete 12-pair implementation
matrix and cross-platform reports passed. Tag and actual-PyPI checks remain pending.**
Platform mocks are unit failure checks, not Mac execution evidence. Paid inference,
independent external audit and v0.4.0 production behavior remain unrun.

## 0.3.1 released-artifact validation

The exact release commit `e7e2459` passed [main CI](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36672022262)
and [tag CI / OIDC publication](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36674642405).
All six Linux/Windows × CPython 3.12.14/3.13.15/3.14.7 jobs passed 258 frozen
source tests, 257 installed agents tests, one installed model test and 31 rebuilt
sdist tests each. Core import/CLI/resources, explicit child/backend interpreter
checks, lint/format/strict typing/docs, security/license/SBOM and strict twine
passed. Every mandatory suite has zero failures, errors and skips. Both source
and installed agents include all four audit regressions, real PostgreSQL/OPA/
A2A/MCP/MAF, eight E2Es, cancellation/UNKNOWN/allowance, original signed history,
upgrade/restore and default 1k/10k bounded-history profiles. No audit case was
deselected or converted to xfail/skip in either final run.

Minimum/latest mixed installed peers passed both directions on the original
release wheel, including original DSSE payload bytes, opposite-interpreter
signatures, golden binding/request/call/manifest hashes, PostgreSQL round trips,
parameterized reconstruction and actual HTTP sync/invoke/query/revoke.
See [compatibility](compatibility.md) for exact runtime/time/profile tables.
Source coverage was 87–88%, with interpreter-dependent denominators; subprocess
coverage is not aggregated. Coverage and elapsed times do not establish performance
improvement or independent collective capability formation.

Actual PyPI wheel/sdist downloads match the six-pair tested candidate hashes.
Cache-disabled actual-index CPython 3.13.15 core/agents/model installs passed
core smoke, agents 30, model 1 and rebuilt sdist 31; all three profiles passed
license/SBOM and known-vulnerability checks, including the first-party root.
The first immediate index attempt failed before that version propagated; its
failure log is retained separately from the successful new-environment retry.
Minimum/latest full post-publication agents regressions each passed 257 tests:
3.12.14 in 1,060.63 seconds and 3.14.7 in 1,060.79 seconds. Both passed the separate
model test and 31 rebuilt-sdist tests; core import/path/version/CLI/resources and
actual child/PEP 517 backend patches matched the requested interpreter. Every
counted suite had zero failures, errors and skips, with strict unraisable subprocess
warnings. All nine installed profiles completed license, vulnerability and SBOM
checks, including the published first-party root. Concurrent audit-cache writes
emitted nonfatal permission warnings; all actual audit JSON reports were complete
and contained zero known vulnerabilities, without skipped package rows.
The [GitHub Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.3.1)
attaches the exact PyPI distributions and 174 selected CI/post-publication reports
with a report-byte hash manifest. Local account prefixes are redacted; raw logs,
configs, keys and credentials are excluded. See [release evidence](releasing.md);
historical checkpoints below remain unchanged.

## 0.3.1 source development checkpoints

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

The first complete CPython 3.14.7 frozen source run had **248 passes and 10
failures in 880.61 seconds**, with two subprocess transport warnings. All eight
E2Es exposed an unintended C4 purpose-forwarding change: local proxy verification
had started requiring a separate provider verification grant. The same three-peer
failure reproduced on 3.12.14. The fix retains local purpose in the content hash,
but preserves the original provider reuse contract, without enlarging any grant.
Two scale fixtures had changed revisions of the original Goal; stable cause
grouping correctly superseded it. Fresh benchmark profiles now use distinct Goal
IDs while keeping the original live deduplication assertions. Pipe cleanup joins
`communicate()` after provider termination; warnings are not ignored.

Corrected Windows 3.14.7 service/scale gates passed 18 tests (one new Revocation
fixture construction error was corrected separately); the provider-grant regression
plus all eight E2Es then passed **9 tests in 371.11 seconds**, zero skips, with
unraisable subprocess warnings treated as errors. Complete frozen Windows 3.13.15
source passed **258 tests in 1,103.00 seconds**, zero failures/errors/skips, under
the same strict warning setting. The installed-wheel mixed 3.12.14/3.14.7 test
passed both directions, including original DSSE bytes, golden content/identity
hashes, persisted reconstruction and actual HTTP sync/invoke/query/revoke.

These interim local observations preceded the final six-pair multi-Python,
installed-artifact and release gates reported above; see
[the runtime table](compatibility.md). Prototype distribution checks are distinct
from the final candidate: 3.14.7 core smoke, 30 agents unit tests, one model test,
31 rebuilt-sdist tests, three license/audit/SBOM profiles, and actual child/build
interpreter recording passed. No paid model or native-backend interpreter shortcut
was used.
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
