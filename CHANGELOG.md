# Changelog

## 0.3.0 (unreleased)

The external document application adds a fixed-order verified-reuse control. It
shares builders, checkers and materialization with the adaptive path but does not
call discovery or proposal/allocation APIs. Comparison experiments remain pending.

Allocation observations retain each opportunity's eligible rank or deferral reason
and rule digest. Scoped observations reference one shared overhead event, committed
in the same transaction, without duplicating its cost per opportunity.

Local Event v3 observations retain discovery, deduplication and fresh selection
attempts with their original scope/policy and measured overhead. Existing event
metrics expose their stage/result counts separately from durable opportunity counts.
Work observations cannot claim PASS or execution and are not shared by the feed.

Scoped work metrics page local opportunities alongside durable selection and
execution state. `metrics --work` uses the same bounded SDK path; `inspect` accepts
opportunities and proposals. Unrecorded attempt counts and checked outcomes remain
explicitly unavailable rather than inferred from completed invocations.

Capability v3 distinguishes materialized formation inputs from runtime dependencies.
Independent result checking remains required. Formation source withdrawal,
counterexamples or withdrawn evidence require requalification; ordinary-use expiry
alone does not. Old v1/v2 records preserve their original semantics and signed bytes.

Bounded owner goals produce signed opportunities and authenticated peer proposals.
Durable Steps retain alternatives and select installed builders under ordinary
admission, finite budgets and adaptive allocation. Host target transitions preserve
the configured contract. Parameterized local artifacts are content-addressed and
reconstructed only through installed factories. The external document application
now exercises these paths with independently calibrated checker bindings, explicit
rejection versus UNKNOWN, and replay that preserves original evidence expiry.
Protected checking allowance is retained across same-owner, same-unit child
Executor calls and formation-session start reservations; independent checking can
use that allowance after the formation context ends.
Matched experiments, remaining semantics and release-wide validation are incomplete;
see `docs/implementation-status.md` and `docs/validation.md`.

## 0.2.1

New invocation reservations are released exactly once only when the database
transaction confirms a still-owned reserved phase and fences further dispatch.
Pre-dispatch refusal, cancellation and expired-worker cleanup no longer retain
execution allowance indefinitely. Dispatched or historical uncertain work remains
held; a child AdmissionDenied after a parent effect does not trigger release.
Claim/dispatch/cancel/finish/cleanup share budget–invocation–lease lock order.
Cancellation of a DB-thread await does not imply rollback. Inspection overhead
remains an immutable measured event even when execution allowance is returned.
Migration 0009 preserves all old invocation reservations as legacy unknown;
stop old workers before applying it. No opportunity or adaptive formation feature
is included in this patch. See release records for actual publication status.

## 0.2.0

Typed local/MCP/overlay-A2A and standard A2A service bindings, durable owner-scoped invocations,
indexed admission queries and resumable signed paged synchronization. New execution
and formation receipts preserve observed use without asserting verification or
functional novelty. Exact component bindings and separate child applicability
checks protect composed execution. The generic peer is separated from the bundled
compatibility reference application (`peer --reference`).
Admission SQL constrains explicit capability issuers throughout the dependency
closure. Cycle detection includes issuer and artifact digest; issuer-less legacy
references continue to reject ambiguity.
Migration 0008 enables indexed reverse dependency filters on the existing bounded
record pages, with explicit handling of legacy unknown-issuer edges.
The offline `restore-state` command rotates feed generations and invalidates local
sync freshness after database restoration without rewriting signed history or budgets.
CLI `invoke`, `invocation` and `cancel-invocation` use the existing authenticated A2A
operations; `binding-check` validates a manifest without registering executable code.
The default CSV demo now registers v2 bindings, independently checks actual probes
and invokes imported provider capabilities through persistent A2A execution. The
evaluation script uses this same path; legacy hard-coded formation/reuse dispatch
has been removed from the reference peer.

An external document application exercises three independent peer processes:
remote C1 use, MAF C3 composition, C3-based C4 calibration, separate checking,
restart/replay and dependency withdrawal. Operator-granted read-only verification
probes keep pre-PASS testing separate from ordinary reuse. The v2 extension retains
exact business JSON numbers through Protobuf rather than silently changing digests.

Record v2 and migrations 0002–0006 preserve historical v1 signed payloads.
Migration 0007 adds scoped history and decision projections. Inspection and event
metrics now expose bounded cursor pages, including histories beyond 1,000 events.
Current target assessment distinguishes historical independent PASS, local ACCEPT,
obligations and observed receipt delays without inventing scope for legacy events.
The `/extensions/v2` A2A boundary requires coordinated peer upgrades. These changes
are covered by the validation scope in `docs/implementation-status.md`.
See `docs/releasing.md` for actual release and post-publication verification state.

## 0.1.0

Initial implementation: typed signed records, receiver-local OPA qualification,
PostgreSQL persistence and fencing, MAF/A2A/MCP integrations, three-process CSV/report
reference application, bounded evaluation and release tooling. Python 3.12 is the
initial tested interpreter range. See validation and release docs for actual status.
