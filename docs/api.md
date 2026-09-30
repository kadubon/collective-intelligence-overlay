# Python API and CLI

## 0.3.2 candidate: bounded invocation cleanup

`InvocationStore.cleanup_expired(owner=..., limit=32, seconds=5, dry_run=False)`
is an operator-local operation; owner must equal Store.owner. Bounds are 1–128
rows and 1–30 seconds of DB work after connection acquisition. Store's finite
pool/connect timeouts apply separately. DB failures propagate, with earlier
committed rows safe to inspect/rerun. Each row follows budget → invocation → lease
locking, in a separate transaction for each budget unit. Missing mappings need
operator reconciliation.

```python
from collective_intelligence_overlay.invocations import InvocationStore

ledger = InvocationStore(overlay.store)  # supplied trusted owner Overlay
preview = ledger.cleanup_expired(owner=overlay.store.owner, limit=16, dry_run=True)
result = ledger.cleanup_expired(owner=overlay.store.owner, limit=16, seconds=5)
```

The CLI shares that SDK operation and needs no running peer:

```sh
collective-intelligence-overlay invocation-cleanup --config owner/config.json --limit 16 --dry-run
collective-intelligence-overlay invocation-cleanup --config owner/config.json --limit 16 --seconds 5
```

Exit 3 / `has_more=true` means another finite batch; exit 2 is failure. Output lists
old caller/ID, state, phase, reason, reservation, lease and planned action, omitting
arguments/results/credentials. Logical slot recovery is separate from physical
task status (`not_observed`) and external effects (`unconfirmed`). Cleanup never
invokes, implicitly queries a provider, creates PASS or proves process termination.

New claims make one bounded cleanup pass only after budget/capacity refusal, then
retry once. Existing IDs always retain the original request/result; changed content
conflicts. Stored UTC deadlines and PostgreSQL `clock_timestamp()` decide expiry.
Matching active reserved/held leases with no actual settlement are fenced and
released once. Dispatched, legacy or mismatched ownership stays UNKNOWN/held;
live work and other owners are retained.

Owner `Reservation.max_unresolved` / `Config.max_unresolved` defaults to 32 (1–1024).
That many terminal uncertain/held reservations stop new independent claims with
`UnresolvedEffectsLimit`; the peer returns `OWNER_UNRESOLVED_EFFECTS_LIMIT`, requiring
original-ID queries and reconciliation. Old queries/retries stay available.
Conversion of already admitted work can exceed the threshold; effects are retained.
A finite `max_concurrent` bounds additional admitted work. These are distinct from
physical tasks and spending balances; changing limits requires owner authority.

`collective-intelligence-overlay opa-install --target PATH` explicitly installs
reviewed native OPA 1.21.0 after HTTPS/size/hash/version/CPU checks and atomic replace.
Failure retains an existing binary. The package helper is the sole asset/checksum
authority; `scripts/fetch_opa.py` is its developer wrapper.

## 0.3.1: exact revocation

The existing owner-only A2A operation uses a bounded exact capability lookup,
including the authenticated owner and every component of `Subject`. Other
issuers' same-subject records and other versions/digests do not establish ownership.
From the operator's configured SDK session:

```python
result = await send(
    config,
    identity,
    config.owner,
    {
        "operation": "revoke",
        "subject": subject.model_dump(mode="json"),
        "reason": "withdrawn",
    },
)
```

`send` is the existing `adapters.a2a.send`. The returned signed revocation remains
an immutable tombstone. Receivers must complete their configured synchronization
before relying on the withdrawal; existing source freshness and dependent
requalification rules apply. Version 0.3.1 is published; see [release evidence](releasing.md).

## 0.3.1: rejected alternatives

`Opportunities.validate_proposal` raises `ProposalRejected` for expected external
input rejection. Its `category` is one of `format`, `authentication`, `authorization`,
`scope`, `expired`, `reference` or `arguments`. `Steps.step` additionally classifies
immutable-ID `conflict`. Database failures, corrupt stored records, mutated host
configuration, assessment errors and cancellation propagate. The pure DSSE and
wire parsers convert only their expected input failures; no catch covers storage
or arbitrary host execution.

`collect` returns `CollectedProposals(replies, unavailable, rejections)`. Keep that
object through selection to retain the distinction between peer unavailability
and rejected alternatives:

```python
batch = await collect(config, store, identity, goal, opportunity.id)
result = await steps.step(opportunity.id, batch)
print(result.reason, result.rejections, result.unavailable)
```

The existing tuple API remains supported. A finite `Steps.run` callback may return
either tuple replies or the complete `CollectedProposals` object. All unavailable
configured proposers produce `peers_unavailable`; rejected alternatives with no
remaining candidate produce `no_valid_alternatives`. `insufficient_allowance` still
means a valid alternative exists but no execution allowance is available. None is
verification FAIL. If an invocation already exists, replay returns its stored state.

Rejections are bounded `(peer, category, count)` summaries. Selection validates
every individual input, including validly signed unauthorized builders. A safely
interpretable response retains valid siblings; an oversized or malformed whole
response is rejected for that peer. Conflicting contents for the same issuer/ID in
one batch exclude both before persistence. A clash with an existing immutable record
excludes that incoming alternative. Valid candidates retain the original builder,
issuer and proposal-ID ranking. No rejected raw record is inserted into Store.

Owner-local Event v3 observations use `work.result="rejected_CATEGORY"` with no raw
peer errors/arguments or new cost charge. Their zero input count avoids counting
the enclosing selection's inspected proposals twice. They stay outside shared feeds.
Read them with the existing event inspection operation and a query such as
`{"kinds":["event"],"issuer":"receiver","task_id":"OPPORTUNITY_ID"}`:

```sh
collective-intelligence-overlay inspect --config receiver.json event --query-file query.json
```

## 0.3.1: logical remote calls

`Registry.execute(..., call_id=None, call_scope=None)` adds a host-assigned logical
identity. Each distinct A2A call needs its own ID even with identical arguments.
Retry the same call with the same ID and persisted scope. `Executor.invoke` supplies
its existing durable invocation ID and parent scope automatically; named nested
Registry calls inherit that scope. Existing local tools can retain their unscoped
API, without a remote idempotency claim. Missing remote identity raises
`calls.MissingCallIdentity` before RPC; it never invents a retry UUID or counter.

```python
first = await registry.execute(
    binding.id,
    binding.digest,
    arguments,
    context,
    call_id="sample-first",
    call_scope="saved-host-session",
)
second = await registry.execute(
    binding.id,
    binding.digest,
    arguments,
    context,
    call_id="sample-second",
    call_scope="saved-host-session",
)
retry_first = await registry.execute(
    binding.id,
    binding.digest,
    arguments,
    context,
    call_id="sample-first",
    call_scope="saved-host-session",
)
assert retry_first == first
```

Identity binds owner, trusted caller, session/scope, parent and call ID. Content
fingerprints separately bind arguments, exact local/provider bindings, purpose,
environment, permissions and named parent content. A changed request with the same
identity raises `Conflict`, before another provider invocation. Registered children
still require their parent's exact component grant and current admission. Named
contexts have a maximum depth of 16; arrival order never assigns their identities.

Migration 0014 persists `RemoteCall` references before RPC: remote invocation ID,
provider/endpoint, exact local/provider bindings, parent and invocation context, and
content fingerprints. It stores no business result or execution/lease state.
Provider Executor remains authoritative for retry, allowance and completion.
Local proxy verification retains its local verification grant and purpose-bound
fingerprint. Its remote request reuses the independently admitted provider;
it does not delegate verification authority to that resource owner. The provider
still requires ordinary reuse admission, evidence, freshness and allowance. A
direct remote verification request separately requires the provider's grant.
For a nested call after uncertain delivery or a host restart:

```python
refs = registry.remote_calls(context, invocation_id="saved-parent-invocation", limit=32)
for ref in refs:
    result = await registry.query_remote_call(ref.call_key, context, config, identity)
```

Alternatively use `call_scope="saved-host-session"` for standalone calls. Choose
exactly one lookup selector, limit 1–128. A full page can continue with
`after=refs[-1].call_key`; this is a bounded owner/caller lookup. Query uses the
saved remote ID and configured original provider, issues no `invoke`, and returns
the provider row or `None`. The host must authenticate its local caller before
constructing `ExecutionContext`; caller text in tool arguments grants nothing.
Do not replay a nested call as a new standalone call: its parent namespace would
change. Resume the parent through Executor and query its original references.
One completed child cannot settle the uncertain parent or authorize another child.

Legacy 0.3.0 rows remain queryable by their original provider invocation IDs.
0014 never invents missing logical child IDs or a legacy mapping. An empty mapping
does not prove non-execution. Stop old writers and reconcile UNKNOWN/dispatched
work before starting new attempts; [deployment](deployment.md) specifies backup
and offline upgrade. Standard non-overlay A2A services receive the named context
as message ID when available, but their own retry/result guarantees still apply.

## 0.3.0 APIs

Discovery and fresh selection attempts now emit `Event(schema_version="3",
work=WorkObservation(...))` with owner, scope, policy, goal and stage/result. Existing
`metrics_page` / CLI `metrics` event queries expose `work_attempt_counts`,
`work_observations` and `proposal_deliveries_at_selection`. These count persisted
attempt observations in the event period, not unique opportunities or validated
proposals. Exact invocation replay does not create another selection observation.
The existing measured overhead event is extended rather than counted twice; discovery
elapsed time now covers qualification and opportunity persistence. Hard failure
before observation commit can leave a gap, so these are not an exhaustive request
audit. Work observations grant no execution or PASS and stay local: the shared
feed excludes events, and generic remote submission rejects work observations.
Allocation now adds a scoped observation for each eligible/deferred opportunity,
including work kind, rule digest, reasons and eligible rank. All observations from
one allocation and its shared overhead Event commit together. Their
`shared_cost_event` points to that one unscoped batch cost; per-opportunity records
carry no duplicated charge. Include the referenced batch cost once when accounting
for a scoped workload. Independent result verification still needs aggregation
with the complete matched experiment report.

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
attempts are explicitly unavailable in this opportunity cohort. Event-period attempt
counts come from `metrics_page`, rather than silently mixing the two cohorts.
`execution_receipt` and `resource_observation` resolve the selected invocation's
original signed local receipt. `resource_observations` labels those observations by
work kind without converting allowance into measured consumption. Root elapsed time
includes contained calls; retain it as an observation instead of adding children.
For child, remote-owner and maintenance costs, complete the corresponding owner
event pages. An unknown/missing receipt remains unavailable. Arbitrary builder output
cannot establish `checked_outcome`; independent Evidence/current qualification and
the application's held-out contract report remain separate.

Event metrics distinguish completed qualified reuse receipts, their A2A remote-use
subset, replication and import events. These overlapping observations are not
four disjoint totals. Import does not prove local executable installation, which
remains unavailable without application observations. Each formation's
`execution_links` resolves its exact signed receipt references (at most 256 distinct
references per page; reduce page size if exceeded). Missing references stay null.
`use_to_formation_seconds` is a nonnegative occurrence-time difference for that
link, not a global first-formation latency or causal improvement. References may
include uncertain attempts, but only a completed ordinary-use receipt from the
same owner gets a delay; UNKNOWN/probe/foreign-owner references remain null.
References may lie outside the page period/prefix; their costs are context and are excluded from
page totals. Signatures authenticate observations; they do not establish the
formation's correctness, current admission or functional novelty.

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
The owner-only `static-run` operation accepts the same finite bounds and uses
the fixed control order described in [evaluation](evaluation.md). Its history
contains actual invocations, formation receipts and checker evidence, without
invented opportunity or proposal records. Run comparison arms in separate fresh
application stores; switching modes in one store is not an isolated experiment.
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
An optional `work_allowances={"verifier": Decimal(14)}` overrides named owners at
initialization only. Unknown owners, negative and nonfinite amounts are rejected
before creating configuration or databases.

Both formation and verification then use authenticated peer proposals and `Steps`.
The core allocator qualifies the checker binding, includes its dependency evidence,
and persists the allocation with the selected work. The application uses explicit
thresholds of one for its two-goal demonstration; operator `allocation` settings in
`application.json` can change them. A checking operation still retains the existing
inner verifier lease for atomic evidence publication. Parent/child wall times must
not be added as separate resource consumption. The isolated matched pilots and
their limitations are reported in [evaluation](evaluation.md).

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
bounded page. Unchanged semantic observations return their current signed instance,
including concurrent discovery. Decision IDs, timestamps and unrelated events do
not create new instances. Relevant evidence revisions,
goal inputs, policy and qualification reasons can create a new observation.

Expired instances appear only in `Discovery.expired`; displaced instances appear
in `superseded`. Neither is an available candidate. `next_action="reobserve"`
identifies the explicit owner operation; ordinary discovery never renews a lifetime.

```python
from collective_intelligence_overlay.reobservation import ReobservationPolicy

host = Opportunities(
    registry,
    identity,
    goals,
    reobservation_policy=ReobservationPolicy(cooldown_seconds=60, max_reissues=3),
)
receipt = await host.reobserve(expired_id, "owner-request-1", "expired", caller=identity.name)
```

The cause digest binds owner and goal ID, retaining unresolved work across host
target/checker revisions. The goal's contract digest remains a separate pin.
Each fresh instance retains `supersedes`, a newly qualified decision basis and its
own expiry. No proposal or selection moves from the prior instance. The operation
rechecks the registered goal, current policy, exact target binding/evidence,
revisions and freshness. Installed checker/actual builder grants are still checked
by allocation and Registry at selection/dispatch; a receipt cannot grant them.

Receipt states are `issued`, `existing_instance`, `satisfied`, `cooldown` and
`reissue_limit`, with cause, bounded reason, observed time, known reissue count and
optional opportunity. Retry the same request ID to retrieve the same historical
receipt (`replayed=True`); changed command arguments conflict. A later observation
requires a new explicit command ID, including after a cooldown refusal. Defaults
are 60 seconds and three reissues; bounds are 1–86,400 seconds and 1–16 reissues.
The first issue starts the cooldown. Counters and receipts survive restart and
concurrent requests converge on a valid current instance. A satisfied goal issues
nothing. Legacy historical counts/times remain unknown; the counter covers newly
tracked reissues. These are owner-local projections, not another execution ledger.

```bash
collective-intelligence-overlay reobserve --config owner.json --goal-file goal.json \
  --opportunity-id OPPORTUNITY_ID --request-id owner-request-1 --reason expired
```

The CLI reads bounded trusted Goal configuration and uses the same SDK operation.
It does not install artifacts or load received code. The optional `--new-attempt`
(SDK `new_attempt=True`) records owner intent. `Steps` independently requires
persisted proof of reserved phase, terminal refusal/cancellation, fenced cancelled
lease and released reservation before retrying undispatched work. No exception or
Python cancellation proves that. A valid closed instance can be reissued after
cooldown for this explicit request. A refused business result can remain UNKNOWN
while these positive facts prove that dispatch never occurred; the original
UNKNOWN result is retained. Running/dispatched or unresolved UNKNOWN effects, or a prior choice
without an invocation returns `reconciliation_required`; an unresolved legacy
cause also needs explicit reconciliation. `new_attempt_required` distinguishes a
safe closed history without owner intent. Same-content completed work is queried
only when its signed observation is also unchanged; its original choice and ID
are returned. Changed evidence is not turned into a current result by replay.

Migration 0013 retains signed bytes and execution/lease/budget states. It projects
known cause and invocation links from existing records, leaving missing legacy
contract/count/time/reason facts unknown. An old missing contract can be adopted
only against the owner's exact registered goal digest; unrelated configuration
cannot silently supply historical facts. Stop old writers for this upgrade; see
[deployment](deployment.md) and [validation](validation.md).

The installed adaptive document example explicitly records owner checker intent
before a distinct bounded check. Its fixed checker arguments and target digest
still come from trusted host configuration; proposals cannot set this flag. It
requires the current instance and fresh replies, and pending/uncertain work remains
blocked even with the flag. This adds no automatic retry on expiry.

After an installed builder publishes an actual candidate, the trusted host can call
`opportunities.select_target(goal_id, expected_goal_digest, binding_id, candidate_ref)`.
It requires an exact signed v2/v3 capability matching the installed binding, original
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
It returns `replies` for `Steps.step`, `unavailable` peers and categorical rejections. A peer
failure does not erase another peer's alternatives or count as verification FAIL.
Each reply has at most eight proposals; request concurrency follows configuration,
the complete collection has at most 60 seconds (or the lower configured limit),
and failed requests are not retried. Signed payload references and each origin are
checked before returning. Host goal/builder/permission checks still run in the step.

`steps.Steps(opportunities, executor, owner_context).step(opportunity_id, replies)`
accepts at most 128 `(authenticated_caller, signed_proposal)` replies or a complete
`CollectedProposals` result. It retains
the alternatives and atomically stores one immutable owner-local choice. The
current rule follows registered builder order, then stable issuer/proposal order;
it does not rank claimed prices or treat votes as truth. The chosen operation uses
the existing Executor and a stable owner/opportunity invocation ID. Repeating a
step, including after restart, returns that invocation's running or saved state.
An UNKNOWN execution is never automatically retried with a fresh ID. A crash
after choice but before claim resumes the same choice, with current grant and
observation checks. Selection overhead is recorded separately before execution.
Migration `0010` adds only the local choice table and preserves all existing signed
records, reservations and invocation states. The finite loop is described below;
the release state is recorded separately in [releasing](releasing.md).

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

0.2.0 adds receiver-persisted paged synchronization:

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
Reuse receipt lags are restricted to the current report's `historical_reuse_policy_digest`;
another policy's successful execution does not become this policy's first reuse.
Each candidate, active obligation and active UNKNOWN evidence report includes its
original local receipt time and observed age. Re-delivery does not reset that age.
Expired or withdrawn evidence does not contribute active obligations/UNKNOWN reports.
These ages describe local observations, not the onset or uninterrupted duration of
a verification gap. UNKNOWN evidence counts are observations per requested target,
not distinct unresolved tasks or a claim that all UNKNOWN decisions have evidence.
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
