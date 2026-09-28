# Implementation status

## 0.2.0 work in progress

The authoritative request is the 0.2.0 incremental specification supplied on
2026-09-28. This is not a claim that 0.2.0 has been released or completed.
Baseline: clean `main` at `99cd3e4`; existing `v0.1.0` remains at `7e4f119`.
Fresh baseline run on Windows Python 3.12.10 against PostgreSQL 16.15 on WSL
and OPA 1.21.0: **43 passed, zero skipped, 30.96 seconds**.

Required completion evidence, tracked without narrowing the original scope:

- [ ] A: typed local/MCP/A2A bindings, actual argument/resource/issuer enforcement,
  provider-local remote authorization, generic peer, application registration.
- [ ] B: indexed subject/claim/scope/dependency queries, bounded DB work and
  offload, relevant revisions, resumable scope-bound snapshot/delta sync with
  commit-order-safe prefixes and completion-bound freshness.
- [ ] C: persistent idempotent invocation/result/cancel, uncertain effects,
  reservations separated from consumption, actual C1/C2/C3/C4 formation with
  checked receipts, scoped metrics and cost attribution.
- [ ] D: preserved 0.1.0 signed payloads and migration/recovery tests; real-service
  negative cases and three-process E2E; 1k/10k scale measurements and selectable
  100k profile; all named documentation, CLI, skill, clean distribution checks,
  CI and OIDC release with actual PyPI post-install verification.

These groups are a navigation aid, not a replacement for the numbered
requirements and invariants in the specification. Release requires every item,
including adversarial and crash/restart cases, to have direct test or runtime evidence.

First checkpoint: operator-owned `Registry`, immutable copied binding manifests,
exact argument/resource/issuer/environment checks, local callable identity,
real MAF bound tool and real MCP contract observation are implemented. Seven new
binding tests pass against actual PostgreSQL/OPA/MCP. v2 capability/evidence bind
their checked registration digest; legacy v1 records retain their original DSSE
bytes and cannot supply missing binding checks. These are partial A/D results;
A2A invocation, indexing/sync, durable execution and formation lineage remain work
in progress. The initial full run after these changes had 49 passes and one test
expectation failure for the MCP SDK's nested ExceptionGroup; the corrected targeted
run passed all seven.

Second checkpoint: qualification now uses indexed subject/scope/claim/receiver
queries within a repeatable-read dependency snapshot. Subject revisions replace
global COUNT invalidation; the synchronous database work is offloaded with bounded
pool, statement and lock timeouts. A transactional feed counter serializes writers
before sequence allocation. A 1,001-unrelated-capability regression checks that
only the two relevant signatures are read. This is not the required full scale
measurement report, which remains pending.

Migration 0002 retains the immutable 0001 revision and backfills in batches of
256 in a maintenance transaction. `tests/fixtures/v010_database.json` was exported
from an actual database created using the published 0.1.0 wheel (SHA recorded in
the fixture), containing only test public keys and signed records. Tests preserve
original envelopes/payloads, colliding issuer identities, PASS/FAIL/UNKNOWN,
withdrawals, reservations, budgets and lease states. An injected interruption
rolls the upgrade back to 0001 and retry succeeds. Operational backup/restore
and larger backfill profiles remain pending.

Fresh full run after both checkpoints: **56 passed, zero skipped, 47.00 seconds**.
Ruff and strict mypy pass. PyPI 0.2.0 returned HTTP 404 on 2026-09-28; no 0.2.0
tag, release or publication has been attempted. Remaining requirements include
A2A bindings/provider execution, generic peer registration, durable invocation,
pagination/sync/freshness, actual C3/C4 lineage and metrics, complete scale
profiles, documentation/skills, clean artifacts and release gates.

Third checkpoint: `synchronization.Feed` now supplies byte/count-bounded,
receiver/filter/generation-bound snapshot and delta pages with EdDSA JWT receipts
and cursors. Snapshot completion retains its original timestamp; zero-change
deltas are explicit. Oversized records fail without advancing the cursor.
Migration 0003 adds receiver-owned persistent checkpoints. `Receiver.apply`
verifies the page and original signed records, then atomically imports records
and advances the checkpoint. Retransmission does not add records or refresh the
timestamp; explicit restart preserves tombstones. Separate source/receiver DB
tests cover restart, a last-page withdrawal, bad signatures and transaction
interruption. **62 tests passed, zero skipped, 53.24 seconds**; Ruff, strict mypy
and documentation checks pass. These are the synchronization SDK primitives;
the existing peer `discover/sync` path and its freshness handling still require
integration with them, followed by real HTTP/three-process tests. No claim of
completed end-to-end synchronization is made at this checkpoint.

Fourth checkpoint: the A2A `/extensions/v2` peer discover/sync path now uses the
paged feed and persistent receiver checkpoints. Config-created overlays require
scope-bound committed synchronization observations, rechecked at execution;
reachability cannot refresh them. Migration 0004 stores synchronization subjects.
The real three-process E2E sends one record per page. A separate admission test
proves that starting an incomplete delta changes ACCEPT to UNKNOWN and importing
the last-page withdrawal changes it to REJECT. Transfer events and cursor updates
commit with the imported page; replay does not create another transfer charge.
The CLI exposes bounded/resumable `sync`, explicit `--restart`, JSON continuation
and exit code 3 for incomplete page budgets. Fresh full run: **63 passed, zero
skipped, 72.66 seconds**; Ruff/format, strict mypy and docs checks pass. The optional
model example uses the same synchronization API; paid model calls remain untested.
Durable invocation/provider bindings, generic reference registration, C3/C4
formation/lineage, scoped metrics, additional adversarial sync/recovery/scale
profiles, full documentation and release validation remain incomplete.

Fifth checkpoint: migration 0005 and `Executor`/`InvocationStore` connect stable
caller/invocation/request identity to the existing budget and fenced lease in one
transaction. Results survive reconnect/retry; conflicting ID reuse is rejected;
cancel/expiry preserves uncertain effects and reservations. The old reservation
helper is shared, not reimplemented. New completions no longer copy reservation
quantity into measured actual consumption. A real subprocess test terminates
after an external file effect and before result commit, then verifies UNKNOWN,
no automatic replay and retained budget. Dispatch-time withdrawal blocks actuation.

`Registry.register_a2a` and provider invoke/result/cancel operations now use real
A2A HTTP with caller-bound authorization and separate consumer/provider
qualification, state and allowance. Tests use separate owner databases and check
exact retry, result privacy and wrong-binding/caller rejection. They do not yet
establish the required three-process C1-through-C4 formation scenario. Fresh full
run: **70 passed, zero skipped, 77.84 seconds**; Ruff/format, strict mypy and docs
checks pass. Generic reference extraction/registration, standard non-overlay A2A
service binding, signed formation receipts/lineage/scoped metrics, expanded
recovery/scale checks, all remaining documentation and 0.2.0 publication are pending.

Sixth checkpoint: the generic peer no longer dispatches CSV/reference work;
`ReferencePeerService` is selected explicitly by `peer --reference`. Registered
composition pins component manifests, and child execution checks actual child
arguments independently. Migration 0006 links durable invocations to signed v2
execution receipts. `FormationSession` validates observed receipt references
against completed local invocations before publishing a candidate and formation
record. Original v1 payload bytes remain preserved. Nested wall-time observations
are not added as resource consumption.

The new real PostgreSQL/OPA/MAF integration scenario composes document primitives
into C3, uses C3's output to construct C4, independently checks outputs, executes
held-out work and rejects both descendants after C1 withdrawal. This is an
in-process construction test, not the still-pending three-process scenario.
Fresh full run: **72 passed, zero skipped, 84.03 seconds**; Ruff, strict mypy and
generated schema checks pass. Standard non-overlay A2A, external application
registration examples, new three-process lifecycle, scoped paged metrics,
scale/recovery profiles, complete docs and release gates remain pending.

Seventh checkpoint: `Registry.register_a2a_service` supports a pinned standard
non-overlay A2A service using the official SDK's JSONRPC 1.0 immediate JSON Message
contract. Credentials stay in host-owned HTTPX authentication, and the transport
restricts SDK requests to configured card/RPC destinations with bounded response
bytes. Card changes, substituted endpoints, required extensions, unexpected Task
or text responses and oversized output do not become accepted results. Real HTTP
tests show that external checking is required before ordinary admitted use, exact
retry does not redispatch and uncertain results persist as UNKNOWN. No remote
code identity or long-running Task support is claimed.

Fresh full run: **74 passed, zero skipped, 80.33 seconds**; Ruff/format, strict
mypy and documentation checks pass. The external application/three-process C1–C4
lifecycle, scoped paged metrics, scale and restore profiles, complete documentation,
clean distribution tests, CI and 0.2.0 publishing remain pending. Changes are local;
no new tag, release or PyPI publication has been attempted.

Eighth checkpoint: migration 0007 adds scoped event and decision history projections
with bounded backfills. `RecordQuery`/`record_page` provide count/byte-bounded,
committed-prefix inspection with exact filters and local continuation state.
Decision writes share the commit-order counter without changing subject revisions
or entering the shared evidence feed. CLI inspection and event metrics expose page
continuations and exit 3 for unfinished prefixes. A 1,105-event regression covers
complete paging, typed totals, replay deduplication and exclusion of late backdated
appends; it is not the required mixed-record performance profile.

`capability_metrics` evaluates up to 32 explicit use requests and distinguishes
historical independent PASS reports from current local ACCEPT, target/capability
identity counts, declared obligations, policy reasons requiring verification and
first local receipt delays. Unknown applicability and withdrawals remain barriers
to current acceptance. Event pages expose receipt links, not an independent proof
of remote receipt references. Page totals are explicitly partial; costs are
attributed to owners and wall/legacy undifferentiated seconds remain observations.

Full service run: **80 passed, zero skipped, 109.39 seconds**. A subsequent exact
decimal aggregation correction passed **9 unit tests**, including its new large
quantity regression. Ruff/format, strict mypy and documentation checks pass.
Migration tests cover 0.1 signed records and pre-0007 execution/decision history.
The external application and three-process C1–C4 lifecycle, full scale/restore
profiles, remaining documentation/skills, distribution tests, CI and publication
remain incomplete. No 0.2.0 tag or publication has been attempted.

Ninth checkpoint: `examples/document_application.py` registers its own executable
application outside the package. Three real peer processes publish/probe/check C1,
install a remote-service binding and C2, form C3 using actual MAF workflow calls,
and use C3's observed calibration output to parameterize C4. The artifact digest
binds that configuration. Separate checker probes, held-out ordinary use, receiver
restart with exact persisted result replay, one-record delta pages and C1 withdrawal
are tested end to end. C3/C4 both become REJECT after the source withdrawal.
The application exposes a bounded MAF FunctionTool proposal interface; the no-key
test invokes it deterministically. There is no claim of autonomous discovery.

Read-only bindings can grant specific callers verification purpose. Missing PASS
alone may be waived for that root probe; other policy/input/resource/withdrawal
checks remain. Probe receipts do not become PASS, first reuse or observed-use
formation links. The E2E found Protobuf integer-to-double conversion changing
manifest digests. The v2 extension now carries exact application JSON inside its
ordinary A2A data part. Native standard services reject non-preservable numeric
inputs instead of silently rounding them.

Full service run: **84 passed, zero skipped, 179.25 seconds**. Subsequent native
numeric-bound and formation-cost changes passed **5 focused tests (60.78 seconds)**;
the final MAF proposal-tool route passed the full document E2E again in **39.19
seconds**. Ruff/format, strict package mypy and schema/docs checks pass. The
compatibility reference registration cleanup, mixed-record scale/restore profiles,
remaining docs/skills, distribution/security/license/CI gates and 0.2.0 publication
remain pending. No new release/tag/publication has been attempted.

See [validation](validation.md) for current checks and [release state](releasing.md)
for publication. Historical development checkpoints are in Git history.

Implemented: typed records, DSSE, distinct peer authentication, PostgreSQL/Alembic,
OPA admission, bounded dependencies, local budgets/fencing, MAF/A2A/MCP connections,
three-process CSV/report lifecycle, opt-in provider example, microbenchmark,
documentation, schemas, skill and package/CI tooling.

Intentional scope: no global manager, new runtime/planner, broker, trustless database,
remote code execution, autonomous model spending or universal intelligence metrics.
Research inspection and non-guarantees are in [research mapping](research-mapping.md).
