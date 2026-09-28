# Python API and CLI

For 0.2.0 registered execution, an operator creates a `Registry(overlay)`, then
uses `register_local`, `register_mcp` or `register_a2a` with an explicit `Binding`
and an input applicability checker. `Executor(registry, identity, Reservation())`
adds persistent invocation identity and owner-local work reservations:

```python
result = await executor.invoke(invocation_id, binding.id, binding.digest, arguments, context)
saved = executor.store.get(authenticated_caller, invocation_id)
cancelled = executor.store.cancel(authenticated_caller, invocation_id)
```

`register_a2a_service(binding, assess, auth=..., local=False)` connects a standard
service without installing the overlay there. Pin `target.interface_digest` to
`fingerprint(MessageToDict(card))`, `target.peer` to the configured card name,
and `target.name` to its expected skill ID. The pin is an operator-approved
interface declaration, not authenticated evidence of remote code identity. Actual
service credentials are supplied as an operator-owned HTTPX `Auth` object, not
saved in a binding or receipt. HTTPS is required except explicit loopback testing.

The supported service contract is A2A 1.0 JSONRPC: one JSON data part in, one
immediate JSON data part out. Required extensions, substituted destinations,
redirects, compressed/oversized responses and other result shapes are rejected.
Protocol Tasks require operator reconciliation and remain UNKNOWN locally; this
adapter does not poll or resume them. The SDK handles A2A serialization and
transport. A card's skill declaration cannot prove the service selected the right
implementation: independent output checking and local admission remain required.
The standard protocol's distinction between Messages and Tasks and its required
extension negotiation are described in the
[A2A specification](https://a2a-protocol.org/latest/specification/).

`context` is an operator-constructed `ExecutionContext`, never caller-supplied
permissions. For peers, `PeerService(config, configure=register_application)`
creates the registry and calls the application registration function. The provider
uses `config.execution_environment` and its own policy permissions. Its A2A
business operations are `invoke`, `invocation`, and `cancel_invocation`; the
authenticated caller is always the result/cancellation owner. These use immediate
A2A Messages and do not expose protocol Tasks or promise automatic worker resume.

`completed` means execution/result persistence, not verified correctness. Exact
retries return the existing result or running state; another request with the same
caller/ID conflicts. A lost/expired worker or a cancellation after dispatch becomes
`unknown` and is not automatically rerun. In 0.2.1, a provably undispatched new
reservation is released in the same transaction that fences its worker. Dispatched,
mismatched or legacy reservations remain held; they are not measured resource
consumption. This is allowance release, not automatic monetary settlement.
Existing v0.1 historical `actual` values are retained
by migration; new work does not infer actual consumption from reservation quantity.
The low-level `Overlay.execute(request, operation)` remains a trusted-host API;
registered execution binds the exact actuator and actual arguments instead.

To let an independent checker exercise a candidate before it has PASS evidence,
the operator may set `Binding.verification_callers` for a **read-only** binding.
Those callers request `ExecutionContext(purpose="verification", ...)`, or send
`purpose: "verification"` with an A2A invocation. The ordinary caller allowlist,
actual input/resource checks, semantic applicability, permissions, licenses,
freshness, known counterexamples/withdrawals, child admission and work reservations
still apply. Only the missing-independent-PASS requirement is waived for that root
probe. The wire caller cannot supply an authorization grant. A plain qualification
request with that purpose is rejected unless trusted host code explicitly supplies
the grant; `verification_granted` on the low-level Overlay API is privileged host
input, like its operation callback.

Probe completion persists a `verification` execution receipt and an UNKNOWN
business outcome. It creates no PASS, does not count as first ordinary reuse and
cannot establish an observed-use formation link. An independent checker must
inspect its output and issue separately scoped evidence. Stable invocation identity
includes purpose, so an invocation cannot be retried with a different purpose.
Policy ACCEPT for a probe means permission to verify only; its decision reason and
request purpose distinguish it from reuse permission.

`lineage.FormationSession(registry, identity, max_steps=16, max_seconds=120)`
records completed `Executor` calls observed during bounded operator construction.
Within its async context, install the resulting local binding, then call
`await session.publish(binding.id, candidate)`. The candidate's v2 dependencies
include exact subjects and corresponding `dependency_issuers`. Publication checks
signed execution receipts against durable invocation rows and atomically saves
the candidate and formation event under a fenced work reservation. Missing,
incomplete or cyclic receipt references cannot become observed formation.
The host supplies installed code; this API does not generate or execute received code.

A formation receipt means observed use while constructing a candidate. It leaves
functional novelty unknown and does not prove causal improvement or correctness.
Independent evidence and receiver-local qualification are still required. Each
execution receipt binds the actual argument/result digests, binding, capability
issuer, scope, policy, caller and resource owner. Migration 0006 adds a durable
receipt reference without manufacturing receipts for old invocations. Historical
v1 signed event payloads remain unchanged.

Bindings list exact child binding digests in `components`. Replacing a component
invalidates the installed composition until re-registration. Dependency integrity
checks do not grant child execution permission: each child call reassesses its
actual arguments and environment. Parent semantic applicability is not inherited.
Nested execution `wall_seconds` observations are reported separately rather than
summed as resource costs because their intervals may overlap.

0.2.0 development adds receiver-persisted paged synchronization:

```sh
collective-intelligence-overlay sync --config receiver.json --peer producer --page-size 32 --max-pages 16
```

JSON output includes `complete`, `through`, `cursor`, `pages`, and the completed
snapshot's `anchor`. Exit 0 means completed, 3 means the page budget ended with
a durable continuation, and 2 means failure. Run the same command to resume.
`--filter-file` accepts a `FeedFilter` JSON object containing exact `subjects`;
omitting it synchronizes the complete shared feed. A cursor is bound to source,
receiver, filter and feed generation. On expiration/restoration use `--restart`
explicitly; this resets transport progress without deleting records or revocations.
Partial or failed synchronization does not grant freshness. Neither a heartbeat
nor authenticated connectivity can refresh a Config-created peer's evidence.

The A2A overlay extension is now `/extensions/v2`; package, record schema and DB
migration versions remain separate. 0.1 peers are not rolling-compatible with this
extension: stop peers, back up consistently, upgrade/migrate, then synchronize.

Core imports are side-effect free. Construct `Store(url, owner, principals)` explicitly;
call `migrate(store.engine)` only during controlled deployment. Always call `store.close()`.
Construct `Policy(opa_binary, PolicySettings(...))`, then `Overlay(store, policy)`.

`Identity.sign(record)` creates standard DSSE; `Store.put(envelope)` authenticates and
inserts once. An exact replay returns false. Same issuer/kind/ID with changed content
raises `Conflict`. Invalid signatures and unsupported schemas are rejected. Records
are not updated in place. `read_records`, `capabilities`, `evidence`, `events` and
`decision_records` inspect persisted state without granting execution rights.

Use `Store.record_page(RecordQuery(...), cursor=..., limit=128)` for larger history.
`RecordQuery` filters exact issuer, subject, scope, policy digest, task/attempt and
the half-open occurrence-time interval `since <= time < until`. Decision pages
use evaluation time and must select only `kinds=("decision",)`. Their issuer filter
means the local owner; decisions are local audit records, not shared DSSE evidence.
Other page items are verified against their original signed envelopes.
For forward dependencies, select the exact parent capability with `issuer` and
`subject` and inspect its authenticated `dependencies`/`dependency_issuers` fields.
For reverse dependencies, use `RecordQuery(kinds=("capability",), depends_on=subject,
dependency_issuer="producer")`. The GIN-indexed projection filters full subject
identity and known issuer in PostgreSQL before loading parent envelopes. Omitting
`dependency_issuer` returns all issuer matches for that subject. With an issuer,
legacy unknown-issuer edges are excluded unless `include_legacy_dependencies=True`;
included legacy records retain empty `dependency_issuers`, never an inferred issuer.
These are direct edges, not transitive traversal or permission to execute parents.
The same filter is available to CLI `inspect capability --query-file PATH`.
The fixed committed prefix, owner, generation, filter digest and snapshot anchor
are returned with `next_cursor`. Appends, even with backdated occurrence times,
cannot enter an existing prefix. Changed filters or restored generations require
a new scan. The count limit is 1–256, and the default item byte budget is 196608;
an oversized single item fails rather than being skipped. These local cursors do
not grant access and are not a substitute for the signed peer synchronization feed.

`inspect` now returns a page object rather than an unbounded list. Both `inspect`
and event `metrics` accept `--query-file`, `--cursor-file` and `--page-size`. Save
the returned `next_cursor` object as JSON, pass that file to resume, and retain the
same query. Exit 3 indicates more pages; exit 0 indicates the prefix is complete.
Legacy list helpers explicitly fail above their limits and direct users to paging.

`accounting.metrics_page(store, query, cursor=...)` reports **this page only**:
typed owner costs, per-issuer attribution, event/action/outcome counts, daily
history, observed transport/execution states and formation receipt links. A
complete last page is not a cumulative total. Sum each page once; persist a
consumer's accumulator with its cursor or deduplicate page intervals on replay.
Scope/policy filters exclude old events where those facts were never recorded.
Unfiltered pages expose `scope_unobserved` rather than inventing scope for them.
Top-level costs belong only to `cost_owner`; per-issuer observations are not an
additional set of charges to add to that total.

For current capability assessment, supply 1–32 explicit `UseRequest` values to
`await accounting.capability_metrics(overlay, requests)`, or a JSON list to
`metrics --requests-file PATH`. This reports historical independent PASS records
separately from current local decisions, their scope/policy/evaluation times,
declared unresolved obligations, and first local verification/reuse receipt lags.
The verification backlog counts decisions explicitly requiring independent
evidence; other UNKNOWN/REJECT reasons remain available for separate work planning.
Missing or out-of-order observation times are null, not zero. Each target is
evaluated at its own current time; this is not an atomic historical replay. Input
applicability must be assessed by the caller; metrics never infer `semantic_fit`
from a schema or grant execution authority. Concurrently inconsistent targets are
reported and excluded from the currently accepted count.

`await overlay.qualify(UseRequest(...))` records a local `Decision`. The request binds
receiver, exact subject/version/digest, scope, environment and semantic assessment.
`await overlay.execute(request, operation, deadline_seconds=30)` requalifies and calls
only the supplied trusted async operation. Its deadline includes qualification.
Qualification itself has a 30-second deadline; PostgreSQL socket operations use a
five-second timeout. Non-ACCEPT raises `AdmissionDenied` with
the full decision. Timeout raises `TimeoutError`; cancellation propagates. Neither
is converted into PASS. Storage/connectivity errors propagate instead of allowing use.

`overlay.observed(issuer)` is a trusted host hook for successful authenticated source
refresh, never a field accepted from an agent. Default freshness is 300 seconds.
`recommend(decision)` returns a bounded suggestion such as verification, connection,
repair or alternative formation. It grants neither budget nor authority.

`Store.acquire` reserves owner-local typed budget and returns a monotonically increasing
fence. `commit_work` checks active ownership and writes results plus terminal state
in one transaction. Stale/cancelled/expired workers cannot commit. `finish` terminates
without result records. Unknown external effects are not retried or refunded automatically.

CLI commands all use the SDK:

| Command | Purpose |
| --- | --- |
| `--version` | Distribution version |
| `check-config --config PATH` | Configuration and pinned-key check |
| `migrate --config PATH` | Apply packaged Alembic revisions |
| `binding-check --manifest PATH` | Validate bounded Binding JSON and report its digest; does not register code or grant execution |
| `invoke --config PATH --peer NAME --invocation-id ID --binding-id ID --binding-digest DIGEST --arguments-file PATH` | Invoke an already registered provider binding with a stable ID |
| `invocation --config PATH --peer NAME --invocation-id ID` | Retrieve the authenticated caller's durable result/state |
| `cancel-invocation --config PATH --peer NAME --invocation-id ID` | Request cancellation without assuming external effects were undone |
| `restore-state --config PATH` | Offline post-restore feed rotation and freshness invalidation; reconcile missing work before use |
| `peer --config PATH [--reference]` | Run an A2A peer; explicitly enable the compatibility reference app |
| `demo --directory PATH [--database-url URL] [--opa PATH]` | Three-process deterministic loop |
| `inspect --config PATH KIND` | capability/evidence/revocation/event/decision JSON |
| `metrics --config PATH` | Typed cost and event aggregates |
| `doctor --config PATH` | DB and OPA presence; no paid model call |

Success exits 0; invalid arguments/configuration/service failures exit 2. Errors are
redacted by default. `CIO_DEBUG=1` is local troubleshooting only and can include
sensitive exception context; never enable it in shared logs.

Invocation commands print the provider's JSON state. Completed execution exits 0,
running exits 3, absent caller-owned invocation exits 4, and rejected/conflict/UNKNOWN
or other unsuccessful execution exits 2. `cancel-invocation` also exits 0 for a
confirmed pre-dispatch `cancelled` result; post-dispatch uncertainty remains exit 2.
Cancellation does not undo effects. In 0.2.1, it returns execution allowance only
when reserved ownership is durably verified and fenced before dispatch; other
reservations stay held. JSON results include `reservation_state` and `release_reason`.
The disposition is separate from the business outcome and measured costs. Use the same stable ID
after a lost response and inspect the saved state before authorizing another attempt.
`invoke --purpose verification` requests only an already configured read-only grant;
it cannot grant itself authority or create PASS evidence. Arguments are a JSON object
in a file limited to 64 KiB; CLI identity comes from the protected owner config.

`binding-check` validates the bounded manifest and computes its digest, without
loading code, connecting to a service or registering the manifest. Actual registration
uses the trusted application's `Registry` setup callback. There is deliberately no
CLI that loads executable code named by an untrusted manifest.
