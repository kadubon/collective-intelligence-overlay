# Implementation status

0.4.0 is published and the predeclared permissioned single-owner profile passes.
[Immutable tag CI / PyPA OIDC](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36911991678) and
[cache-disabled actual-PyPI CI](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36922605705) are whole-workflow successful at `f3f6ae30de6f088c160e0c69f49796e4f52d2546`.
Both validate all 12 native profiles, four cross readers, mixed Python and the
unchanged formal originals: 20 numerical and three additional gates, no pending validation.
Actual-index verification also matches all 36 root-inclusive resolved name/version audits,
with no findings or skips. [GitHub Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.4.0) contains the exact
tested wheel/sdist and checked evidence ZIP; actual downloads match their recorded hashes.
See [machine-readable actual results](release-040-results.json),
[Japanese final report](release-040-report.ja.md) and [declared scope](production-040.md).
The Linux one-hour observation, negative matched result and unverified wider scope
remain explicit. The immutable tag preserves its historical prepublication documentation;
the current actual results are recorded here on main without changing packaged files.


## 0.3.2 audit follow-up

| Requirement | Implementation and regression | Boundary |
| --- | --- | --- |
| CIO-031-01 capacity recovery | Shared fenced expiry in `invocations.py`; bounded owner cleanup and one maintenance/retry on new-claim refusal; real PostgreSQL `test_invocation_cleanup.py` | Old-ID lookup is unnecessary. Logical capacity recovery does not prove physical termination or completion of an outside effect |
| Allowance and UNKNOWN | Budget -> invocation -> lease locking, reserved-phase/worker/fence checks and owner unresolved-effects policy; process death, cross-unit races, delayed DB threads, rollback and restart regressions | Positive undispatched proof releases once; uncertain effects remain UNKNOWN/held with original IDs/maps |
| Offline compatibility | Index-only 0015 and actual published-0.3.1 fixture in migration/restore tests | Original records, signed bytes, lifecycle rows and remote references are compared; stop old writers and use tested backup restoration |
| CIO-031-02 native setup | Explicit package OPA installer, reviewed Darwin assets, private native PostgreSQL and Unicode/path/mode/TLS/process tests | Platform mocks test refusal paths. Native support requires real reports for each CPU; no Rosetta, Docker Desktop or global service cleanup |
| Distribution/runtime gates | Single candidate, 12-pair manifest, full source/installed/rebuilt-sdist gates, mixed HTTP peers and four installed cross-platform readers | Hashes, actual child/build runtimes and zero mandatory skips are required; current completion and publication state are in the linked records |
| Representative stress | Completed mixed-history, exact authenticated revoke, work-history and invocation-cleanup 100k profiles | Separate run outcomes are retained; bounded fixture work is not a general latency or resource guarantee |

The immutable tag at `b172c0d` passed all 12 native gates, four shared readers,
mixed HTTP and OIDC publication. The original pair then passed fresh actual-PyPI
verification on every native identity, including 36 root-inclusive supply-chain
profiles. The GitHub Release includes the exact distributions and 641 selected
sanitized reports. See [validation](validation.md), [compatibility](compatibility.md),
[scale reports](scale.md) and [release state](releasing.md). No v0.4.0 production
behavior or empirical intelligence improvement is claimed by this patch.

## 0.3.1 audit follow-up

| Audit | Change and regression evidence | Final CI and limits |
| --- | --- | --- |
| CIO-030-01 | `7f5d566`; `PeerService._revoke`, `test_cio_030_01_authenticated_exact_revoke_with_mixed_capability_history`: authenticated real A2A/PG at 1,000/1,001/10,000 records | All six source and installed agents suites passed; 3 signature checks / 4 SELECTs / 4 rows at every size. New optional 100k revoke stress unrun |
| CIO-030-02 | `9cf41ec`; `ProposalRejected`, per-alternative collection/selection; `test_cio_030_02_*` in opportunities and hostile real A2A replies, bounded owner categories and real DB-failure propagation | All six source and installed suites passed, including both orders, same-peer siblings, malicious signed builders, all-invalid and real storage failures. Interim exclusions remain labeled in validation |
| CIO-030-03 | `f7f6d1e`; `reobservation.py`, opportunities/steps/invocations, 0013 and owner CLI; 20 `test_reobservation.py` cases, controlled expiry and actual published 0.3.0 DB migration/restore | All six source and installed suites passed, including durable cooldown/count/receipts and completed/uncertain/proven-undispatched guards. No automatic external retry or refund |
| CIO-030-04 | `dd2bf3b`, follow-up `58d9401`; `calls.py`, Registry/Executor/public MAF IDs, 0014; ten `test_call_identity.py` cases with real HTTP/DB, namespaces/content conflicts, workflow, concurrent retry, cancellation, provider/caller restart after response loss | All six source and installed suites passed. Provider reuse admission is preserved; querying a completed child never settles UNKNOWN parent work. Stable host/session IDs are required |

Python/artifact/CI commit `e7e2459` passed both main and tag gates and published
the original pair through one OIDC job. Minimum/latest actual-PyPI full regressions
each passed 257 agents tests, one model test and 31 rebuilt-sdist tests; the middle
stable minor passed fresh core/agents/model and rebuild checks. All have zero
failures/errors/skips. The immutable tag's GitHub Release includes the exact
distributions and sanitized reports. See [current validation](validation.md) and
[release state](releasing.md).

## Two-stage delivery

Stage A, 0.2.1, is published and verified at `3026c39`. Stage B, 0.3.0, is
published and verified at `a2fc32b`: exact-commit source and clean-artifact CI,
OIDC publication and an actual-PyPI fresh installation (89 tests, zero
failures/errors/skips) passed. Both releases retain their own immutable artifacts.
See [validation](validation.md) and [actual release state](releasing.md). The matrix
below maps the completed A1–A4, B1–B12 and C1–C5 requirements and their limits.

| Requirement | Implementation and evidence | Validation boundary |
| --- | --- | --- |
| A1–A3 reservation safety | invocations/storage; real 0.2.0 reproductions, `test_invocations.py`, `test_concurrency.py`, staged migration | Proven undispatched work refunded once after fencing; uncertain effects retained |
| A4 patch release | 0.2.1 exact CI artifacts, OIDC, actual-PyPI 34-test regression | Complete; tag/artifacts unchanged |
| B1–B2 thin finite integration | Registry/Executor, FormationSession, MAF/A2A/MCP; three-process E2Es | No second lifecycle, runtime or mandatory manager |
| B3 scoped opportunities | models/opportunities, original payload references; `test_opportunity_storage.py`, `test_opportunities.py` | Semantic cause deduplication; goals and grants remain operator configuration |
| B4 discovery and alternatives | Actual indexed qualification, MAF typed drafts, authenticated A2A; `test_proposal_maf.py`, `test_proposal_exchange.py` | Deterministic client tests do not demonstrate LLM discovery superiority |
| B5 local bottleneck allocation | allocation/steps; checker qualification, full goal window, protected allowance, capacity, persistent cooldown tests | Bounded local diagnostics, no network-wide optimum or remote capacity grant |
| B6 finite execution | Durable choices reuse existing invocation IDs; restart, races, shortage, UNKNOWN, bounded loop tests | UNKNOWN needs reconciliation; no automatic fresh-ID retry |
| B7 real materialization and feedback | Content-addressed parameters, installed factory; `test_persisted_bindings.py`, adaptive document C3→C4 E2E | Actual observed-use formation, no received code or functional-novelty claim |
| B8 checking and relationship roles | Independently calibrated checker, v3 formation inputs, runtime dependencies; `test_lineage.py`, document E2Es | Unchecked checker cannot grant PASS; source problems conservatively require requalification |
| B9 measurements | Existing owner event pages, work receipt resources, capability ages/checks, exact lineage links and isolated business reports | Missing CPU/tokens/currency remain unavailable; inclusive elapsed observations are not summed |
| B10 matched experiments | Fixed/adaptive normal, checking-constrained and connection arms; public protocol/source/raw archives, `test_document_experiment.py` | Equal checked outcomes and allowance; higher adaptive elapsed observations in one pilot, no superiority claim |
| B11 integration/failures | 189-test source regression plus named schema, grant, concurrency, restart, checker, withdrawal, cost/isolation cases | Source and clean-artifact suites passed without service skips |
| B12 bounded scale/security | Existing indexed snapshots/feed and new signed-work profiles at 1k/10k/100k; HTTP limits/redaction tests | Saved stress reports have completed assertions; terminal stress exit status not retained; no SLO |
| C1 compatibility/recovery | Original 0.1/0.2/0.2.1 fixtures, migrations 0009–0012, actual dump/restore tests | Stop old workers; no rolling interoperability claim |
| C2 docs/skill | README EN/JA and canonical API/semantics/deployment/evaluation/skill | Published; main documentation records verified release facts |
| C3 artifacts/dependencies | Frozen uv resolution, lint/type/docs/skill, build/twine, audit/license/SBOM and clean artifacts passed | Exact final guard source, clean artifacts and actual-index regressions passed |
| C4 two-stage publication | Existing workflow.yml / pypi OIDC with tested-artifact transfer | Both versions complete: exact CI/tag/PyPI/post-install and GitHub Release |
| C5 completion report | Separate version evidence and explicit limitations | Release gates and actual-index checks complete; documented empirical limits remain |

Test filenames refer to [integration tests](../tests/integration) and
[E2E tests](../tests/e2e); records, application sources and exact measurement limits
are linked from their canonical docs. Chronological intermediate checkpoints are
preserved in Git history, rather than treated as current missing implementations.

The B11 adverse-case audit uses these behavioral tests, included in successful
current-source and installed-artifact runs:

| B11 case | Test evidence |
| --- | --- |
| 1–2 duplicate cause / relevant changes | `test_real_deficit_stable_ids_concurrency_and_evidence_change`, concurrent first discovery and candidate-transition cases |
| 3 independent alternatives | `test_authenticated_a2a_alternative_proposers_and_unavailable_peer`, deterministic alternative/replay case |
| 4–5 authority / tampering / unknown schema | `test_proposal_validates_real_reference_goal_and_installed_authority`, opportunity storage and DSSE record tests |
| 6 racing execution/reservation | `test_step_concurrency_replay_and_one_allowance`, invocation capacity/claim/cancel concurrency cases |
| 7 restart / UNKNOWN | `test_restart_after_choice_uses_original_alternative`, `test_step_unknown_is_not_reexecuted`, process-death invocation tests |
| 8 bounded backlog / budget stop | allocation readiness/unverified queue, full-goal-window, protected floor, finite deadline/allowance cases |
| 9 untrusted model / repeated proposals | actual MAF structured-output bounded repair and invalid authority fields, finite no-progress loop |
| 10 unchecked checker | Adaptive document E2E normal-use denial before calibration and insufficient-calibration UNKNOWN/replay |
| 11 C3→C4 | real document and adaptive document three-process E2Es plus actual MAF composition/lineage test |
| 12–13 saved actual parameters / changes | persisted-binding separate-interpreter restart, changed calibration/factory/component evidence rejection |
| 14 withdrawal / counterexample | materialized-input adversity, ordinary dependency withdrawal, all document descendant cases |
| 15 cost gaps / negative outcome | accounting properties, work receipt metrics, saved raw pilot budget/censored-result checks |
| 16 experiment isolation | fresh owner keys/databases/allowances, existing directory preservation and tampered outcome/budget rejection |

## 0.2.0 implementation and validation

The 0.2.0 incremental specification was supplied on 2026-09-28. Implementation
and validation are complete. Release CI, OIDC publication and actual PyPI
post-install verification succeeded; exact commits, hashes and observations are
recorded in [releasing](releasing.md).

- [x] Typed local/MCP/A2A bindings, actual argument/resource/issuer enforcement,
  provider-local authorization, generic peer and application-side registration.
- [x] Indexed exact subject/claim/scope/dependency queries and reverse dependency
  pages; bounded database work, asynchronous offload and relevant revisions.
- [x] Resumable receiver/filter/generation-bound snapshot/delta synchronization,
  commit-order-safe prefixes, atomic checkpoints and completion-bound freshness.
- [x] Persistent caller-scoped invocation/result/cancel, uncertain-effect retention,
  fencing and reservations separated from measured consumption.
- [x] Actual C1/C2/C3/C4 construction with independent checking, ordinary-use
  execution receipts, scoped lineage/metrics and cost attribution.
- [x] Original 0.1.0 signed payload preservation, transactional migration and
  actual PostgreSQL backup/restore, including post-restore freshness invalidation.
- [x] Real PostgreSQL, OPA, MAF, A2A HTTP and MCP tests; three-process CSV and
  external document applications; 1k/10k/100k mixed signed-history measurements.
- [x] CLI, API, deployment/recovery, research mapping, dependency review and skill
  documentation. No paid model calls are needed for these checks.
- [x] Final exact-commit CI, OIDC release and clean installation from actual PyPI,
  followed by both three-process E2Es (2 passed, zero skips, 68.97 seconds).

The default CSV application uses explicit registrations, independently checked
provider and receiver-imported bindings, and persistent A2A execution. It installs
known functions; it does not claim algorithm discovery. The external document
application, outside the package, demonstrates observed C3 use in subsequent C4
formation with actual MAF composition, held-out inputs, restart/replay and source
withdrawal. Remote service use does not transfer executable code or attest it.

See [validation](validation.md) for test observations and their limits,
[scale](scale.md) for raw measurements, and [research mapping](research-mapping.md)
for the operational interpretation and omitted theoretical guarantees. Earlier
implementation checkpoints remain in Git history; the original v0.1.0 tag is
unchanged at `7e4f1191aaf7e9bca8a6091e1758204e189cb924`.

Intentional scope: no global manager, new runtime/planner, broker, trustless
database, received-code execution, automatic model spending or universal
intelligence metric. Standard non-overlay A2A support covers immediate JSON
responses; unexpected long-running tasks remain UNKNOWN and require reconciliation.
