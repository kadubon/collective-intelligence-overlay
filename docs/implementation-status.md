# Implementation status

## 0.2.1 then 0.3.0 work in progress

Baseline: clean main `bb24512`, published v0.2.0 at `394ba59`; actual GitHub CI
and PyPI confirm 0.2.0, with neither target release present at task start.

Stage A: reproduce pre-dispatch allowance retention against PostgreSQL/OPA;
implement an atomic fenced, idempotent release only for durably proven undispatched
work, preserve uncertain effects and measured inspection overhead; test cancellation,
expiry, dispatch, delayed DB-thread commits, old workers and migration. Run every
existing distribution/security/service gate and publish/verify 0.2.1 separately.

Stage B starts only after Stage A safety gates pass. Add bounded typed opportunities
and peer proposals, owner-local explainable selection and finite steps using the
existing Executor/MAF/A2A/Store. Persist actual builder artifacts and C3-to-C4 use;
retain independent checking, receiver admission and conservative withdrawal.
Run isolated static-versus-adaptive matched experiments for verification and
connection/environment bottlenecks, including failures, costs and censoring.
Validate migration, restart/concurrency, bounded discovery/scale, docs/skill and
clean distributions; publish/verify 0.3.0 after 0.2.1. No positive effect is assumed.

Stage A is complete: v0.2.1 at `3026c39` passed full CI, OIDC publication,
artifact hash comparison and 34 actual-PyPI allowance/migration/restore/E2E checks
(105.58 seconds, zero skips). Its release artifacts and records are preserved.
Stage B remains incomplete. The specification's A1-A4, B1-B12 and C1-C5,
including all named adverse cases, artifacts and publication gates, remain the
completion criteria; this plan does not replace or narrow them.

The host can now select a formed candidate as a goal's exact target while preserving
its scope, logical identity, issuer, checker and allowlists. It verifies the signed
candidate against the installed binding, invalidates old proposals and rediscovers
the checking deficit. Applications must persist the returned configuration. Foreign
proposers can explicitly opt into candidate versions within an approved public
contract; neither collection nor that exported configuration contains private
checker inputs.

The external document application now connects actual observations to two peer
alternatives, stable Steps invocations, FormationSession publication, independent
checking and subsequent C3-to-C4 use in three processes. It persists target goals
and reconstructs callables from existing manifests. Its current candidate/checking
priority is a fixed domain rule, not the core adaptive allocator; checking still
uses the existing verifier lease path outside Steps. Adaptive integration, failure
coverage, relation-role semantics, full metrics and matched experiments remain
required, along with all final distribution and publication gates.

The first 0.3.0 working-tree increment adds versioned Opportunity/Proposal models,
generated schemas, bounded exact record inspection and original-payload reference
checks. These records neither change admission revisions nor enter the existing
evidence synchronization feed. Generic peer submission refuses them until a
registered goal exchange validates them. This increment does not yet implement
the full selection/step loop, adaptive experiments or the 0.3.0 release.
The next increment adds bounded operator goal discovery using actual qualification,
stable semantic IDs, concurrent deduplication, retained alternative proposals and
host checks against changed observations and installed bindings. The optional MAF
adapter uses actual structured-output Agent calls with bounded repair and no tools;
tests use a deterministic local client and do not demonstrate model superiority.
An owner-local single-step API now persists one immutable choice and connects it
to the existing Executor using stable invocation identity. It retains alternatives,
checks allowance before choosing, and reuses running/completed/UNKNOWN state on
replay. Tests cover concurrent replies in different orders, restart between choice
and claim, insufficient allowance and a response lost after the actual operation.
This is still a static choice rule; bounded adaptive allocation and the complete
multi-peer formation cycle remain to be implemented and evaluated.
Persisted binding v2 now binds installed builder configuration, parameters,
environment and components to the subject digest. A separate Python process
restores the saved manifest and executes after actual PostgreSQL/OPA admission.
Changed calibration values with identical callable source get different identities
and cannot reuse old evidence. The existing v1 binding digest is retained.
Explicitly registered foreign-goal contracts now support signed proposal replies
over existing A2A authentication and HTTP limits. Two real HTTP endpoints produce
different retained alternatives; disabling one endpoint's proposal authority leaves
the other reply and records the disabled peer as unavailable. This transport test
runs services in one process and is not the required three-process adaptive E2E.
The finite host loop now connects bounded discovery and a registered proposal
callback to durable steps. It stops on no progress, deadline, allowance shortage
or round limit and avoids reproposing saved work after restart. Discovery emits
measured qualification overhead without affecting opportunity novelty. Target
ordering remains static; adaptive allocation and per-owner cross-worker capacity
enforcement are not yet complete.
The loop now applies small configurable adaptive rules and retains allocation
observations with its local choices. Real Registry/OPA readiness checks gate
verification priority; checker withdrawal removes that readiness. An unverified
page limit suppresses formation, and a static mode preserves the comparison rule.
These are bounded page observations. Persistent cooldown, reserved allowance,
cross-worker capacity and a complete cross-page backlog bound still need work.
Subsequent work completes all registered-goal pages before allocation and enforces
same-unit protected allowance plus owner-local concurrency in the existing claim
transaction. Migration 0011 adds a bounded owner/state index. Steps supplies a
concurrency bound; legacy host executors require explicit consistent configuration.
Tests exercise claims racing across different budget units, retained checking
allowance, ordinary release and later-page verification backlog. Cooldown remains
incomplete, as do the adaptive formation application and release-wide gates.
Persistent cooldown is now connected to the latest owner-local choice through
an indexed lookup. Stable priority retains its original start time, and repair or
loss of checker eligibility is not blocked by hysteresis. Formation/application,
lineage-role distinctions, full metrics/experiments, scale and publication gates
remain incomplete.

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
