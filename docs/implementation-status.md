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

See [validation](validation.md) for current checks and [release state](releasing.md)
for publication. Historical development checkpoints are in Git history.

Implemented: typed records, DSSE, distinct peer authentication, PostgreSQL/Alembic,
OPA admission, bounded dependencies, local budgets/fencing, MAF/A2A/MCP connections,
three-process CSV/report lifecycle, opt-in provider example, microbenchmark,
documentation, schemas, skill and package/CI tooling.

Intentional scope: no global manager, new runtime/planner, broker, trustless database,
remote code execution, autonomous model spending or universal intelligence metrics.
Research inspection and non-guarantees are in [research mapping](research-mapping.md).
