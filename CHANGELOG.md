# Changelog

## 0.4.0 (unreleased)

- An optional document recovery query compares a restored database/CAS with an
  operator-pinned preserved original through read-only transactions and the
  existing owner lock. Missing post-backup originals/allowance remain UNKNOWN;
  an available unrewound original and explicit resume are required.
- The installed document receiver reconciles original mapped word-count results
  with an explicitly registered read-only query. Exact original arguments, caller,
  provider, binding and result digest are checked. Unconfirmed results stay UNKNOWN;
  reconciliation does not resend, refund, rewrite the original or create PASS.
- Dispatched parents retain actual nested owner budget/capacity refusal reasons
  and distinguish observed timeout/cancellation from generic UNKNOWN. No exception
  text, effect-absence claim or allowance refund is inferred from those reasons.
- Installed proposal callbacks require an operator-owned allowance and finite
  concurrency. Original opportunity retries return retained signed alternatives
  after restart without generating or reserving twice. Fenced atomic publication
  retains UNKNOWN and allowance on timeout, cancellation or failed output; it
  creates no independent PASS. The earlier direct exchange remains compatible.
- Lease commit authority reads PostgreSQL time after locking the original row,
  matching acquisition/finish and preserving expiry under Python clock skew.
  Native three-peer skew tests retain authentication refusal, allowance and no PASS.
- Loopback demos allocate each topology's ports in one bound socket batch;
  startup uses an actual finite deadline rather than a count of slow RPC attempts.
- Message-only A2A operations use the pinned official SDK's public legacy handler
  so completed replies leave no producer/consumer queues waiting for another call.
  The nonstreaming client iterator finishes and its public close method runs before
  returning. Original invocation, allowance and signed-record storage are unchanged.
- English/Japanese README starts from the published wheel, with native shell
  commands and a checkout-free PostgreSQL tutorial. Candidate operations and open
  acceptance gates are explicit; version history stays in the release records.
- Reference checker contracts now pin calibration helper source and the operator's
  expected threshold as well as the adapter and underlying checker. Contract changes
  receive distinct revisions/subjects and require explicit new checks and goal pins.
  Independent Evidence and its original CAS proof retain this exact checker version.
- Owner process observations expose standard OS CPU seconds and actual PID/parent
  PID. Explicitly unavailable RSS/live-child/historical costs remain distinct.
  Redacted standard logs observe SQLAlchemy cursor, OPA and official A2A exchange
  durations and failures without recording SQL, arguments or credentials.
- Operator-selected installed application host, packaged starter, separate secret
  files, restricted runtime DB bootstrap, owner locking, dependency readiness,
  drain and tracked physical blocking work compose the existing execution APIs.
- Explicit pinned control callers can replace owner drain/resume authority.
  SDK/CLI control uses a separate current signer without loading the owner key;
  no execution grant is inherited. Recovery resumes against the original
  owner-signed review, preserving matched-state checks and closed intake.
- Physically finished thread work releases capacity before a deferred callback,
  without releasing still-running work after cancellation or double-counting it.
  Native CI exposed this race; the restore test also now passes the configured
  PostgreSQL password to the standard client rather than relying on local trust.
- Closing a killed owner session invalidates its connection if the final unlock
  detects the disconnect, retaining closed intake and avoiding a broken pooled
  session or shutdown failure.
  Native Mac also exposed a direct socket reset from pg8000's read boundary;
  readiness closes intake for that error and shutdown discards the lost session.
- Trusted local read-only bindings can be staged without replacing the active
  version. Explicit probes use existing grants/Executor; finite ordinary admission
  checks precede promotion or rollback and preserve the old entry on refusal.
  Retained versions stay bounded. Existing signed Events and private CAS manifests
  record exact operator choices, protected-input decisions and a declared checker
  comparison basis. Stable choice retries retain original bytes and do not reapply
  a rolled-back transition. Config-pinned startup restoration rechecks signed
  identity and never renews admission. The installed document host connects stage,
  independent checking, explicit promotion and retained rollback with exact pins.
  An independent calibration regression retains the old binding. Complete native
  fault/comparability acceptance remains pending.
- The existing document application is packaged, with source launchers using the
  same implementation. Explicitly granted `app.*` operations and a bounded owner
  runner connect its actual MAF formation/check/reuse loop to standard host intake.
  Exact installed pins restore without scanning unrelated retained history.
- The same reference host supports an explicitly pinned authenticated HTTPS MCP
  counter with a dedicated client. Its credential stays in protected application
  settings included in owner backup, outside public bindings and artifacts.
  Native three-owner tests exercise restricted roles, actual MAF/A2A/MCP/TLS and
  original UNKNOWN replay after provider restart without another tool call/refund.
- The reference Caddy listener uses standard HTTP/1.1 and HTTP/2, avoiding an
  observed native Windows HTTP/3 UDP bind refusal without changing TLS or gates.
- Native CAS publication locks before initializing an empty lock file, preventing
  the observed Windows concurrent-creator failure. A deterministic process test
  retains the originally empty locked file until its holder releases it.
- An actual installed immutable 0.3.2 wheel generated the retained upgrade fixture;
  PostgreSQL dump/restore, interrupted migration and repeated upgrade preserve its
  original signed records, allowance and remote mapping without inferred identity.
- Bounded authenticated HTTP capacity and read-only retries preserve operation
  identity. Original provider-ID reconciliation appends provenance observations,
  separates reported completion/effect/PASS and retains UNKNOWN and allowance.
- Offline coherent PostgreSQL/CAS/config/key backup and additive 0016-0019
  projections preserve old signed bytes. Restored intake stays closed through
  restart; full post-restore sync and an explicitly registered external-state
  query precede a separately authorized, unchanged-state resume.
- Routine/compromised keyrings separate historical origin from current authority.
  Current uncompromised feed receipts can carry unchanged known historical origins;
  direct submissions and admission keep strict signature authority checks.
  Standard redacted rotating logs, owner-only metrics and configured atomic CAS
  quotas retain uncertain mappings, signed history and unavailable costs.
- The official Caddy binary failed vulnerability review. An explicit pinned
  native v2.11.4+cio.1 build uses security-updated dependencies, a two-line public
  CEL API adjustment and standard native upstream/license/security/SBOM audits.
  OFL/MPL obligations and the unlinked OpenPGP advisory are retained in the review.
- The predeclared complete production/native/fault/soak/experiment gates remain
  unfinished. This candidate has not been tagged, released or published to PyPI.

## 0.3.2 (2026-09-30)

- CIO-031-01: owner-bounded expiry cleanup shares the existing fenced transition
  with get. New capacity/budget refusals make one maintenance pass and retry once.
  Reserved positive proof releases allowance once; dispatched/legacy/mismatched
  work remains UNKNOWN/held. Operator dry-run/CLI and a separate unresolved-effects
  limit retain original IDs and provide recovery reasons. Migration 0015 adds only
  an ordered index. Real PostgreSQL process-kill, interruption, rollback, races and
  actual-0.3.1 migration/restore regressions preserve signed rows and remote maps.
- CIO-031-02: explicit atomic OPA installation includes reviewed native Darwin
  arm64/amd64 assets, size/hash/version/CPU checks and clear unsupported-platform
  errors. The source script delegates to the installed package helper.
  One manifest expands mandatory CI to Linux/Windows/Mac Intel/Mac arm64 across
  three stable CPython patches, with private native PostgreSQL and distinct reports.
  Native golden signature/artifact exchange has separate installed reader gates.
  Completed native support and publication evidence are recorded in validation
  and release documentation.
- Native PostgreSQL startup captures diagnostics in files, avoiding inherited
  Windows daemon pipes. The reviewed pg8000 connection close has a small scoped
  compatibility shim that explicitly closes its buffer after a failed protocol
  flush; original DB errors propagate. Real transport-disconnect tests retain
  strict finalizer-warning checks. Dependencies and license exceptions are unchanged.
- All 12 native release profiles passed 291 source, 290 installed agents,
  one model and 41 rebuilt-sdist tests with zero failures/errors/skips. Four native
  readers and mixed-Python HTTP passed. Representative 100k profiles completed;
  tag publication and actual-index status remain recorded separately in Docs.

## 0.3.1 (2026-09-30)

Standard authenticated peer revocation now checks the exact owner, subject ID,
version and digest with an indexed bounded query. Signing, persistence and cost
observation run off the asynchronous handler's event loop. Mixed imported/legacy
histories no longer hit the compatibility full-history reader's 1,000-record limit.

Proposal collection and selection isolate expected untrusted-input rejections per
alternative. Valid siblings remain eligible, malformed/oversized remote replies
are isolated per peer, and stable ranking of valid candidates is preserved. Owner
observations retain categories without raw payloads. Same-ID content conflicts,
transport unavailability and allowance shortages remain distinct from internal
errors; cancellation joins outstanding requests. No dependency versions changed.

Expired opportunities are excluded from available discovery results. Explicit
owner reobservation issues a fresh signed instance with `supersedes`, persisted
reason/count/cooldown and idempotent request receipts. Cause identity remains in
the owner/goal namespace across target and checker revisions. Migration 0013 adds
only observation/command and selection projections; original payloads and unknown
legacy facts remain unchanged. New choices consult existing invocation/lease rows:
uncertain or pending work blocks another attempt, matching completed observations
are queried, and proven undispatched releases require explicit owner intent.

Logical remote call IDs are separate from request fingerprints, with persisted
owner/caller/session/parent namespaces and exact provider/binding references.
Registry accepts explicit call IDs; Executor supplies existing invocation identity;
MAF uses public tool-call parameters/context. Distinct identical-input calls execute
separately, retry preserves the remote ID, and changed content conflicts. Missing
remote identity fails clearly. Migration 0014 preserves legacy IDs without inventing
missing mappings. Querying a completed child never settles an uncertain parent.

Python metadata is >=3.12 without an upper bound. Explicit interpreter selection
reaches clean core/agents/model environments, CLI, demos, pytest and PEP 517
sdist rebuilds. Required stable Linux/Windows matrix jobs share one candidate
build, unique reports and a final hash gate; publication stays in one OIDC job.
The existing frozen dependency versions and original content hashes are retained.
Mixed installed 3.12.14/3.14.7 peers pass both signature/hash and real HTTP exchange
directions. Local proxy verification preserves provider reuse admission.

All six stable Linux/Windows source and installed-artifact gates passed, with zero
mandatory failures/errors/skips. One OIDC job published the original tested wheel
and sdist; actual PyPI download hashes match. Post-publication cache-disabled
core/agents/model installs passed on every stable minor, with 257 full installed
agents regressions each on minimum/latest patches and zero failures/errors/skips.
GitHub Release includes the exact distributions and sanitized verification reports.
Final evidence is recorded in Docs without moving the immutable release tag.

## 0.3.0

Work metrics resolve original signed invocation receipts and expose resources by
selected work kind. Event pages distinguish qualified reuse, remote A2A use,
replication and import, with explicit unavailable installation facts. Formation
links expose authenticated receipt context and follow-on delay without duplicating
charges. Generic completion still does not establish a checked business outcome.
New 1k/10k signed-work discovery profiles run by default; saved 100k stress
measurements retain source hashes, bounded-work assertions and diagnostic timings.

Capability metrics now expose original local receipt times and ages for candidates,
active obligations and UNKNOWN evidence. Replays retain those times, withdrawn
evidence leaves active counts, and first-reuse latency is restricted to the report's
policy digest instead of accepting a receipt from another policy.

An isolated document comparison command records predeclared assignments, fresh
owner stores, setup/run timings, signed observations, allowance and negative/censored
outcomes. Initial pilots show equal checked outcome counts and no allowance saving;
the current protocol also includes a matched input-contract connection condition.
Original estimates, reservations, owner costs and missing resources are retained.
Exact-commit release gates and actual-PyPI install/regressions passed;
see `docs/releasing.md` for immutable artifact provenance.

The external document application adds a fixed-order verified-reuse control. It
shares builders, checkers and materialization with the adaptive path but does not
call discovery or proposal/allocation APIs. Both paths can construct an installed
input adapter following an actual scope mismatch, then independently check its new
binding before reuse. Restart restores its exact input contract and parameters.

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
Matched pilots and relationship semantics are implemented and release validation
passed; see `docs/implementation-status.md` and `docs/validation.md`.

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
