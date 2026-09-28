# Python API and CLI

## 0.3.0 development APIs (unreleased)

`accounting.work_metrics_page(store, query, cursor=None, limit=128)` reports a
bounded cohort of locally issued opportunities with durable selection and current
invocation states. The `RecordQuery` must specify opportunity kind, local issuer,
scope, policy digest and a half-open creation period. The CLI uses the same API:
`collective-intelligence-overlay metrics --config PATH --work --query-file QUERY.json`.
`inspect opportunity` and `inspect proposal` expose the original bounded records.
Output is page-local JSON; `next_cursor` continues the fixed record prefix. Mutable
invocation state is read separately at `execution_observed_at`, not replayed at the
cohort cutoff. Re-reading a page must replace its previous observations rather than
adding them again. Reservations remain separate from measured costs; completion
does not establish independent verification. Selected alternatives and estimates
are retained, while unrecorded discovery, deduplication, deferral and total proposal
attempts are explicitly unavailable. Full work-effect measurement remains incomplete.

`Capability(schema_version="3", formation_inputs=(FormationInput(...), ...))`
distinguishes materialized construction inputs from runtime `dependencies`. Each
input pins `subject`, `issuer` and `binding_digest`. Keep live call dependencies in
`dependencies` and exact callable authorization in Binding `components`; duplicate
declarations and self inputs are rejected. `FormationSession.publish` accepts v3
and validates its inputs against real local completed-use receipts. See
[semantics](semantics.md) for expiry, withdrawal and requalification behavior.

The external [document application](../examples/adaptive_documents.py) connects
discovery, A2A alternatives, durable selection and actual formation. Its
`configure_application(configs, training_text)` installs application templates and
writes owner goals plus public proposer contracts. Serve each existing owner with
`uv run python examples/adaptive_documents.py --config PATH`. The owner-only A2A
operation `adaptive-run` accepts `max_steps` from 1 to 16 (also bounded by config).
It returns a reason and observed history; it creates at most the two registered
application candidates, with at most eight child calls per formation (or the lower
configured `max_children`) and a 120-second run deadline. Owner concurrency also
respects configuration; `max_rechecks=0` disables new checks. Concurrent requests
to the same service return `already_running`.
The independent checker retains its own allowance and read-only invocation grants.
Its reference pins a registered Binding, including the installed checker source;
the explicit application route checks caller, binding and actual argument shape.
Completed check requests are bound to their attempt, target binding and input.
Replaying an identical request returns the original signed evidence and saved probe
result even while the target is offline. It does not renew timestamps or admission.
A changed request conflicts before another reservation. An interrupted check with
no saved result remains unresolved; its expired lease is not automatically reclaimed.

The reproducible three-process setup, initial primitive checks, later autonomous
choices and cleanup are exercised by
`uv run pytest tests/e2e/test_adaptive_documents.py -q` with the documented PostgreSQL
and OPA environment. A selected count/report is an input to an installed application
factory; only observed completed uses enter its FormationSession. Candidate
registration remains UNKNOWN until independent checks and local admission succeed.
Initial setup tests the installed checker and its receiver-side A2A binding from
the producer identity, using a known count and an explicitly mismatched target.
Normal checker invocation is denied before this evidence exists. A completed,
explicit target rejection is distinguished from an unavailable/UNKNOWN probe;
the latter cannot establish checker PASS. The fixed tests establish only their
declared contract cases, not exhaustive correctness or remote code attestation.
An exact calibration replay returns its original certificate without contacting
the target. Reused probe results cannot extend the certificate expiry; incomplete
calibration retains UNKNOWN and its original timestamps on identical replay.
`demo.initialize(..., work_allowance=Decimal(50))` permits an explicit nonnegative
initial allowance for fresh application owners; it does not top up existing stores.

Both formation and verification then use authenticated peer proposals and `Steps`.
The core allocator qualifies the checker binding, includes its dependency evidence,
and persists the allocation with the selected work. The application uses explicit
thresholds of one for its two-goal demonstration; operator `allocation` settings in
`application.json` can change them. A checking operation still retains the existing
inner verifier lease for atomic evidence publication. Parent/child wall times must
not be added as separate resource consumption. Matched experiments remain incomplete.

`Executor.invoke(..., minimum_remaining=...)` protects the remaining allowance
through nested Executor calls for the same owner and unit. A child cannot lower
its inherited floor; another unit or owner retains its own allowance contract.
The floor is scoped to the execution context and restored on return or failure,
so a separate authorized checking request can spend the retained allowance.
`FormationSession(..., minimum_remaining=...)` applies the work-unit floor to both
its start reservation and enclosed Executor calls. The external application passes
the allocation's reserve to this session and stops with `insufficient_allowance`
when its start reservation cannot preserve that reserve. These bounds apply to SDK
reservations, not arbitrary resource use by trusted installed Python code.

`opportunities.Goal` is operator configuration: a versioned goal, exact ordinary-use
`UseRequest`, fixed checker binding, bounded installed-builder allowlist and explicit
proposal peers. `Opportunities(registry, identity, goals)` owns isolated copies.
`await opportunities.discover(max_candidates=8, start=0)` performs existing local
qualification against bounded indexed snapshots. Use its `next_goal` for another
bounded page. Results preserve the original signed opportunity when the semantic
cause is unchanged, including concurrent discovery. Decision IDs, timestamps and
unrelated events do not create new opportunities. Relevant evidence revisions,
goal inputs, policy and qualification reasons can create a new observation.

After an installed builder publishes an actual candidate, the trusted host can call
`opportunities.select_target(goal_id, expected_goal_digest, binding_id, candidate_ref)`.
It requires an exact signed v2 capability matching the installed binding, original
issuer, logical subject ID and complete scope. Only the subject version/digest,
binding digest and goal revision change; checker, arguments, permissions and
allowlists remain fixed. Old proposals become inapplicable. Repeating selection of
the current target is a no-op; a stale expected goal digest raises `Conflict`.
Persist the returned `Goal` with application configuration and restore it on startup.
This host configuration operation is not exposed to peers and is not a distributed
goal store. Selection does not establish PASS or admission.

`Store.reference(kind, issuer, record_id)` and `resolve_reference(ref)` bind records
to original signed payload bytes; local decisions instead use the existing local
projection digest. Neither operation grants execution or evidence authority.
`ProposalDrafts` accepts at most eight alternatives. `propose(...)` assigns stable
IDs and preserves separate hypotheses and issuers. `validate_proposal(envelope,
authenticated_caller, owner_context)` checks the registered goal, source reference,
current revisions, deadlines, builder identity and actual argument permissions.
It does not execute work or mark it verified. Generic evidence synchronization and
`submit` do not implicitly share or accept these new work records.

Optional `adapters.maf.propose_structured(client, inputs, max_attempts=2, seconds=30,
max_tokens=2048)` invokes a real MAF `Agent` with structured output and no tools.
The host explicitly supplies the client; paid inference remains opt-in. Invalid
JSON/schema output gets bounded repair, transport uncertainty gets no retry, and
returned costs separate measured elapsed time from unavailable tokens/prices.
Returned drafts still require the same host validation.

For configured A2A peers, the host assigns `service.proposal_exchange =
ProposalExchange(service.overlay.store, service.identity, approved_foreign_goals,
installed_async_proposer)`. Export foreign configuration using
`ProposalContract.from_goal(goal)` and its normal model JSON methods; this omits
private checker arguments and request argument digests. The constructor also
accepts a `Goal` for local host convenience and retains only its public contract.
Contracts pin the owner, target, scope, checker and builder allowlist; the local
proposer must be explicitly named in `peers`.
The `propose` operation is denied by default even when evidence sharing is enabled.
The installed callback returns `ProposalDrafts`; it cannot change the contract.
The default pins the exact target. An operator can set `allow_target_updates=True`
when constructing the exchange to allow another version/digest of the same logical
subject under the registered contract. New opportunities include an optional
`goal_contract_digest`, excluding only goal revision and candidate version/digests.
Scope, checker, output contract, permission set and lifetime are checked explicitly;
returned drafts still use the original builder allowlist. A commitment is an
authenticated assertion by the owner, not proof of its private decision. The owner
rechecks its exact live goal before executing a reply. Neither a received goal nor
checker inputs are transmitted by `collect`, and no received data replaces the
proposer's registration. Digests are not encryption; keep credentials and held-out
answers outside exported goal configuration. Observations without the new digest
can use exact contracts but cannot request candidate transitions.
`await proposal_exchange.collect(config, store, identity, goal, opportunity_id)`
uses existing authenticated A2A destinations to obtain each peer's signed reply.
It returns `replies` for `Steps.step` and a separate `unavailable` peer list. A peer
failure does not erase another peer's alternatives or count as verification FAIL.
Each reply has at most eight proposals; request concurrency follows configuration,
the complete collection has at most 60 seconds (or the lower configured limit),
and failed requests are not retried. Signed payload references and each origin are
checked before returning. Host goal/builder/permission checks still run in the step.

`steps.Steps(opportunities, executor, owner_context).step(opportunity_id, replies)`
accepts at most 128 `(authenticated_caller, signed_proposal)` replies. It retains
the alternatives and atomically stores one immutable owner-local choice. The
current rule follows registered builder order, then stable issuer/proposal order;
it does not rank claimed prices or treat votes as truth. The chosen operation uses
the existing Executor and a stable owner/opportunity invocation ID. Repeating a
step, including after restart, returns that invocation's running or saved state.
An UNKNOWN execution is never automatically retried with a fresh ID. A crash
after choice but before claim resumes the same choice, with current grant and
observation checks. Selection overhead is recorded separately before execution.
Migration `0010` adds only the local choice table and preserves all existing signed
records, reservations and invocation states. The full adaptive bounded loop and
the 0.3.0 release contract remain in development.

`await steps.run(proposal_callback, max_steps=16, max_candidates=8, seconds=120)`
connects discovery to the same durable step, one operation at a time within this
call. The installed async callback receives an immutable-copy opportunity and
returns the authenticated reply tuples accepted by `step`; it can call A2A
`collect` or an installed reference proposer. Bounds allow at most 64 observation
rounds, 32 targets per page and 300 seconds. The result reports rounds, discovered
and deduplicated opportunities, observed invocation results and a stop reason:
`no_progress`, `insufficient_allowance`, `deadline` or `step_limit`. No progress
does not mean every goal succeeded. Running, completed and UNKNOWN work is read
from existing invocation state without another proposal request or fresh attempt.
Qualification observations have their own measured overhead events. This current
loop accepts `allocation_policy=AllocationPolicy(mode="static")` for registered
target order. Its default adaptive rules inspect the bounded observation page:
repair takes priority for known failures; a verification backlog gets priority
only with a currently qualified registered checker; connection and observation deficits
can change priority. The operator sets minimum sample count, backlog thresholds
and an unverified-page limit. At the latter limit, formation is deferred. Missing
checker grants, invalid fixed checker inputs, missing evidence and withdrawal do
not count as checker availability. `Goal.checker_arguments` fixes the host input
used for this readiness assessment; actual invocation still rechecks its own input.
Local and registered remote checkers use the same actual argument, binding and
evidence checks. An authenticated Agent Card alone cannot qualify a remote checker.
Qualification is a scoped readiness observation, not a guarantee of future network
availability or a reservation of remote capacity. The resource owner still checks
its own admission, budget and concurrency at invocation.

Every returned `AllocationObservation` identifies the receiver, rule/policy
digests, observation window, exact signed sources, checker decisions, page counts,
ordering and deferrals. The selected observation is retained in the immutable
local selection, and the allocation's elapsed cost is measured separately.
Direct `allocate` counts describe its supplied page, not independent statistical
samples or an all-network backlog. `Steps.run` completes all pages of the registered
goal set (at most 32 goals) before allocation, so a later page cannot hide a local
verification queue from generation. The operator's `reserve_operations` retains
that many normal invocation allowances for qualified checking work; it is not
a price estimate or a claim about remote slots. Formation's claim atomically checks
the protected remainder in the existing budget unit. No conversion is performed.
External finite host loops can call `Steps.last_allocation()` to restore the latest
persisted owner choice when passing a previous observation to `allocate`.

`Reservation(minimum_remaining=..., max_concurrent=...)` controls these claim checks.
`Steps(..., max_concurrent=4)` sets a bounded allowance on its supplied executor,
retaining any stricter limit. All owner workers must use the same operator limits;
the legacy trusted-host Executor default remains opt-in. Claim serialization is
local to the owner and database, includes budget units, and counts running child
invocations too. An operator must allow capacity for intended nested work; excess
claims defer rather than wait indefinitely. Expired/uncertain rows are reconciled
through the existing invocation lookup, not silently reclassified by the allocator.
Migration `0011` adds an owner/state index without changing records or balances.
`AllocationPolicy.cooldown_seconds` controls priority hysteresis. The loop reads
the latest owner-local selection through migration 0012's owner/time index and
keeps its prior priority only while that work kind remains eligible. Keeping the
same priority does not reset the original switch time. Known-failure repair can
override cooldown immediately; a withdrawn checker cannot retain verification
priority. A changed rule/policy digest also prevents inheriting an old cooldown.
This is a finite local rule, not an estimate of globally optimal allocation.

`bindings.ArtifactSpec` stores an installed builder ID/version/source digest,
bounded parameters, environment, component bindings and content-addressed data
references. `spec.persist(Artifacts(owner_directory))` returns the manifest digest.
A local `Binding(binding_schema="2", artifact_digest=..., ...)` must use that digest
as its subject digest. The host restores it through `registry.register_artifact(
binding, artifacts, installed_factory, assess, builder_id=..., builder_version=...)`.
The installed factory takes the saved parameters and returns an async operation;
it cannot be selected by a received import path. Registration checks configuration,
source, environment and components. Each call verifies persisted data and creates
fresh parameters before invoking the reconstructed callable. The host still owns
installed code and its global dependencies; this is not code attestation. Candidate
registration never supplies PASS evidence. Binding v1 keeps its original digest
calculation; its new optional artifact field is excluded from that calculation.

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
For a host path that must never automatically resume an uncertain legacy lease,
pass `reclaim_expired=False`. Within the existing budget/lease transaction, any
previous lease then causes `Conflict`, including an expired active row. Its worker,
fence and allowance remain unchanged. The default retains the existing explicit
expired-lease takeover behavior. This option does not grant permission to retry
an unknown external effect; use persisted Executor results for normal bound calls.

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
