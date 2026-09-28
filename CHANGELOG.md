# Changelog

## 0.2.0 (unreleased)

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
remain under development; see `docs/implementation-status.md` for completed checks
and outstanding release requirements. No 0.2.0 publication is claimed.

## 0.1.0

Initial implementation: typed signed records, receiver-local OPA qualification,
PostgreSQL persistence and fencing, MAF/A2A/MCP integrations, three-process CSV/report
reference application, bounded evaluation and release tooling. Python 3.12 is the
initial tested interpreter range. See validation and release docs for actual status.
