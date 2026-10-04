# Python API and CLI

New lifecycle projections are documented in the [lifecycle reference](lifecycle-reference.md).
Existing execution, admission, budget and recovery signatures below retain authority.

[Generated command help](cli-help.txt) lists every CLI command and option. Use
`collective-intelligence-overlay COMMAND --help` for your installed version.

`Registry.execute(..., deadline_seconds=30)` keeps its bounded default. An
`Executor` now passes its explicit `Reservation.seconds` to both use-time
admission boundaries; a declared longer safe operation is no longer silently
cancelled by the inner 30-second default. Admission/revocation/input rechecks
still run immediately before actuation. Timeouts remain UNKNOWN/held.

## 0.3.2: bounded invocation cleanup

Published 0.4.1 adds the owner resolution path below. Its completed audit/native
and actual-index verification, with remaining limits, are recorded in
[actual release results](release-041-results.json) and [audit status](audit-041-status.json).

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
Each item's `observed_at` is the PostgreSQL time of the locked inspection.
A dry-run's `not_dispatched` describes that snapshot; it does not fence the worker
or grant permission to retry. Apply cleanup and inspect the committed state before
relying on release proof.

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

The installed `collective_intelligence_overlay.starter.adaptive_documents`
application connects
discovery, A2A alternatives, durable selection and actual formation. Its
`configure_application(configs, training_text)` installs application templates and
writes owner goals, exact installed binding pins and public proposer contracts.
The source example is a small launcher for this same implementation. The owner-only A2A
operation `adaptive-run` accepts `max_steps` from 1 to 16 (also bounded by config).
It returns a reason and observed history; it creates at most the two registered
application candidates, with at most eight child calls per formation (or the lower
configured `max_children`) and a 120-second run deadline. Owner concurrency also
respects configuration; `max_rechecks=0` disables new checks. Concurrent requests
to the same service return `already_running`.
For the standard production host, set the operator-owned `Config.application` to
`collective_intelligence_overlay.starter.adaptive_documents:configure` and
`application_settings` to the prepared application JSON. Start each owner with
`collective-intelligence-overlay peer --config PATH`; use the existing owner `run`
operation. `run` selects the installed application's static or adaptive allocation
mode and returns its `reason` and `history`. The application-specific operations
have the `app.` prefix. Standard `invoke`, `sync`, `qualify` and the other existing
operations keep their existing names. Runtime requests cannot select a factory.
The package requires the `agents` extra for this application, but core import
does not load it. Development loopback tests do not establish the complete HTTPS,
restricted-role, native production profile.

At restart, new settings restore exact saved bindings from finite CAS manifests;
they do not select the newest historical candidate or scan all retained history.
Changed source, subject, parameters, components or binding digest require explicit
requalification. Pins grant no PASS or admission. Legacy settings without pins
retain their bounded compatibility lookup and refuse oversized history rather
than silently choose an incomplete page. Upgrade those settings by explicitly
reviewing and recording the intended installed bindings.

The producer may instead install an actual MCP counter through private application
settings: `counter` is the complete explicit read-only Binding JSON with owner/
registrar `producer`, ID `words`, the document count scope, an HTTPS MCP endpoint
and the observed tool schema/interface digest. `counter_token` is that service's
explicit credential in the same protected private settings file. Do not put this
credential in the public Binding, CAS manifest, shared contracts or logs. The
factory validates the installed contract and registers it with the existing MCP
adapter using verified TLS and a dedicated HTTP client. No A2A token is inherited.
Every call rechecks the actual MCP interface; the independent document checker
still establishes only its finite business cases. Interface delivery is not PASS
or code attestation. Ordinary use still requires receiver qualification.

`configure_application` preserves these operator-supplied settings while writing
the public proposer contracts and owner pins, with private file permissions. That
private settings file is already included in owner backup and its recovery state
digest. Use existing OS permissions on Windows as described in deployment; POSIX
mode bits do not establish Windows ACL isolation. An unavailable MCP service leaves
the original dispatched invocation UNKNOWN/held. Its identical replay, including
after service restart, returns the original result without a new MCP call or refund.
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
On the unreleased 0.4.0 production host, `ApplicationHost.register_proposer`
reserves one owner `work` credit before invoking the installed callback. The
operator can specify `allowance_unit` and a positive Decimal `allowance_quantity`;
the unit must already have an initialized owner budget. Received contracts,
opportunities and draft estimates do not set these grants. Callback concurrency
is at most four and no greater than `Config.max_concurrency`; excess requests
are refused without entering a wait queue or reserving allowance. The callback
deadline is at most ten seconds and no greater than `Config.max_seconds`.

A stable work identity binds the authenticated caller and original opportunity ID.
Successful alternatives and the measured wall/unavailable-currency cost Event are
published atomically through the existing fenced lease transaction. Repeating the
request, including after restart, returns those original signed alternatives and
does not call the proposer or reserve again. Changed content under the same
opportunity ID conflicts. Timeout, cancellation, invalid output and an expired
lease retain the reservation; no automatic replay, refund or PASS follows.
Reservations remain separate from measured consumption. This bound covers the
registered proposal callback; ordinary Executor and HTTP capacity retain their
own existing limits. A noncooperative installed callback requires the host's
physical-work tracking and shutdown rules.

For direct `ProposalExchange` construction, pass `allowance_unit`,
`allowance_quantity` and `max_concurrent` explicitly for the same behavior.
Omitting `allowance_unit` preserves the earlier unbudgeted API for compatibility;
the installed production host and document factory always set an allowance.
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
On the unreleased 0.4.0 path, a dispatched parent retains an actual nested
`owner_budget_refused`, `owner_execution_capacity_refused`,
`owner_unresolved_effects_refused` or `owner_blocking_capacity_refused` reason.
Observed timeout/cancellation has a distinct reason; other exceptions retain
`execution_unknown`. These codes do not prove physical termination, absence of
effects or independent PASS. No raw exception text is persisted, and earlier
signed UNKNOWN history and generic legacy reasons are retained.
`invoke --purpose verification` requests only an already configured read-only grant;
it cannot grant itself authority or create PASS evidence. Arguments are a JSON object
in a file limited to 64 KiB; CLI identity comes from the protected owner config.

`binding-check` validates the bounded manifest and computes its digest, without
loading code, connecting to a service or registering the manifest. Actual registration
uses the trusted application's `Registry` setup callback. There is deliberately no
CLI that loads executable code named by an untrusted manifest.

## 0.4.0 installed operations

These operations passed the declared native production profile in the published 0.4.0.
See [actual results](release-040-results.json) for scope and limits. The public
`ApplicationHost` uses the existing Registry/Executor/Opportunities/Steps. An
operator-selected installed `module:factory` receives the host and returns None.
Remote inputs cannot select that factory or register executable code.

The installed `peer --reference` compatibility mode also uses that owner lifecycle.
`reference_peer.load_reference(config)` returns its host with an acquired owner lock;
call its Operations/lifespan and close it after draining. Direct
`ReferencePeerService(config)` construction retains its trusted in-process API and
does not acquire a daemon lock. The CSV bindings and old signed records stay pinned.
See [the stopped-writer upgrade](deployment.md#stopped-writer-032-csv-compatibility-upgrade).

`Config.operator_callers` grants only `drain` and `resume` to unique pinned
identities (at most 32). A nonempty tuple replaces the owner's control grant;
an empty tuple retains legacy owner control. `status` permits the owner and these
callers. It does not grant execution or access to owner-only recovery review,
original-call queries, metrics or installed application operations.

The CLI's `status`, `drain` and `resume` accept the paired flags
`--identity-name NAME --identity-private-key PATH` for a separate control signer.
The current uncompromised public key must match that identity's configured pin.
For example, after pinning `operator` and setting `operator_callers: ["operator"]`:

```console
collective-intelligence-overlay drain --config owner/config.json --identity-name operator --identity-private-key control/operator.pem
collective-intelligence-overlay status --config owner/config.json --identity-name operator --identity-private-key control/operator.pem
collective-intelligence-overlay resume --config owner/config.json --identity-name operator --identity-private-key control/operator.pem
```

These commands use the same authenticated A2A client and configured HTTPS peer;
`--peer NAME` overrides the destination owner. They load config, TLS trust and the
explicit caller key without loading the owner key or constructing a Store.
`load_config` still resolves its configured secret DSN file. Protect control
credentials with separate OS accounts/ACLs; these flags do not install filesystem
isolation. Error exit 2 and successful JSON exit 0 retain the existing CLI behavior.

For trusted installed local read-only operations,
`Registry.register_local(binding, operation, assess, staged=True)` retains the
active binding and stages a distinct revision. At most eight versions are staged
and sixteen retained. `registry.inspect(id, expected_digest=digest)` returns the
exact installed version. Ordinary execution still requires the active digest;
only an explicit `verification` context with that version's caller/probe grants
can execute a staged version through the same Executor. Registration and a
completed probe produce no independent PASS.

After independently checking the candidate, a trusted host can call
`await registry.promote(id, digest, protected_inputs, context,
expected_active=old_digest)`. The context must be local-owner ordinary `reuse`;
one to eight argument dictionaries are copied and assessed against the actual
candidate, then qualified by the existing policy. The returned tuple contains all
persisted Decisions. Every result must be ACCEPT before the active entry changes;
FAIL, UNKNOWN or other refusal preserves the old entry. Concurrent active changes
refuse the switch. The old version stays retained for explicit rollback through
the same current admission checks; changing the pointer undoes no earlier effect.
Once staged management begins, direct registration cannot bypass promotion.

This primitive performs no trial, independent verification or application-specific
regression comparison itself. The installed checker must justify its scoped
evidence on the actual protected cases. The lower-level `promote` pointer is
process-local.

For a durable observation use `await registry.promote_recorded(id, digest,
protected_inputs, context, expected_active=old_digest, identity=owner_identity,
artifacts=owner_artifacts, command_id="owner-choice", checker_comparison="unchanged",
comparison_artifact=local_digest)`. Comparison is `unchanged`, `changed` or `unknown`;
the CAS artifact records the operator's basis and limitations. This declaration
does not establish scientific comparability. The API stores full binding/scope,
argument digests, exact local Decision references and the comparison basis in a
bounded private CAS manifest. An existing signed recommendation Event points to
that manifest, including refused choices. It carries no truth verdict. Publication
precedes the pointer change and adds no reservation or external invocation.

The returned exact `RecordRef` belongs in operator application settings alongside
the installed active/retained pins. Reusing the command ID returns the original
receipt, including a refusal, and does not reapply a later-rolled-back transition.
Changed requests conflict. At startup, register the exact installed versions and
call `registry.restore_choice(reference, owner_artifacts)`. It rejects refused,
mismatched or compromised signed choices. It neither searches for a latest record
nor renews historical admission: ordinary Executor use still checks current inputs,
expiry, dependencies and withdrawals. A crash before the application settings are
saved leaves the last persisted choice authoritative for restart.

The packaged document host exposes owner-only `app.stage-change` and
`app.promote-change` through the standard authenticated A2A `send` API. Stage data
has `name` (`report`/`triage`), `command_id` and `parameters` (`input_key`/`threshold`).
It publishes generated status and retains the old active binding. `app.describe`
accepts `binding_digest` to inspect a staged/retained version and reports
`requested_version_available`; the independent checker verifies that exact pin.
Promote data has `name`, `binding_digest`, `expected_active`, `command_id`,
`protected_inputs` (one to eight dictionaries), `checker_comparison`, and a private
JSON `comparison` basis. Its result has `choice`, historical `accepted`, and current
`active_digest`. The installed operator goal contract must remain intact. The
adaptive triage checker derives expected calibration from its own operator settings;
the candidate cannot redefine that expectation. Failed/unchecked versions retain
the original. Checker identity includes the installed adapter, underlying checker,
calibration helper source and explicit operator threshold. The revision and subject
version contain that complete contract digest. Source or calibration changes require
new explicit goal/checker pins and independent checks; old evidence is not renewed.
An incorrect expected checker digest is rejected before spending verification allowance.
Exact staged/choice pins survive restart. Rollback uses the same
operation with the retained original digest and a new command ID. A settings-save
failure closes intake with `APPLICATION_PINS_SAVE_FAILED`; restart restores the
last persisted configuration. Complete all-native faults and broader checker
comparability remain part of production acceptance.

Factories can call `host.register_operation("app.NAME", async_handler, callers=(...))`
for at most 32 application operations. Names must have that prefix, be unique and
use explicitly pinned caller identities. They cannot replace standard operations.
The handler receives the authenticated caller and request object. These operations
share standard request capacity, readiness and drain; drain refuses them before
the callback. This registration grants only that application route, not execution
of arbitrary bindings or changes to goals, policy or budgets.

After `host.register_goals(goals)`, an installed factory can call
`host.register_goal_runner(async_runner)` once. The runner accepts `max_steps` and
`max_candidates`, uses the same Steps/Executor and returns an application dictionary.
Standard owner `run` applies its configured step/window/time limits to that runner.
Its output schema is application-specific; the default generic Steps runner retains
its existing RunResult schema. Cancellation/timeouts still require physical work
and UNKNOWN reconciliation; the hook is not a new workflow engine.

`remote-calls --config PATH --invocation-id ORIGINAL` queries one bounded page of
the owner's saved child mappings. Alternatively use `--call-scope SCOPE` for a
persisted standalone host scope. A full page continues with `--after LAST_CALL_KEY`;
an empty page proves no absence of legacy effects. `reconcile --config PATH
--call-key KEY --command-id OBSERVATION --invocation-id ORIGINAL` queries the exact
saved provider ID. Repeat the same command ID to recover its historical signed
observation and original stored DSSE envelope without signing it again; use a new
operator command ID for a new observation.

For C→B→A, B uses `--original-caller C` with `remote-calls` and `reconcile` to
select the C-origin parent stored inside B. Authorization actor/resource owner
remain B, and A still sees the original outbound authentication principal B.
The SDK exposes `original_caller` on `Registry.remote_calls/query_remote_call`
and `Reconciliations.observe`. C and other peers cannot list B's private history.
The persisted `[B,C,invocation]` context and provider ID remain unchanged.
`query_remote_call` reads an immutable saved ID even if the installed local binding
has changed; it never executes that binding. Signed reconciliation with an original
receipt uses that receipt's subject. A standalone legacy call without a receipt
needs its original manifest for a new observation, while raw ID lookup remains
available. Missing historical arguments stay UNKNOWN.

Reconciliation matches caller, provider, binding, argument digest, result digest
and original parent. Event v4 retains the local request fingerprint, provider
fingerprint, response digest, original UNKNOWN receipt and observed cost. Older
record media types and signed payloads remain unchanged. Legacy mappings without
an argument digest remain UNKNOWN; migration does not invent it. Provider
completion is a report, not independently confirmed effect or PASS.

For application-specific effect confirmation, the installed factory registers an
ordinary read-only query binding and calls `host.reconciliations.register(ID)`.
The query receives an object with `call` and `provider_report` and returns the
public `EffectObservation` JSON shape. It runs through the same Registry with an
owner verification grant and actual argument checks. `--reconciler ID` selects
only that explicitly registered binding. Mismatched or missing observations stay
UNKNOWN. Neither query path invokes the original uncertain action, changes its
result, releases its reservation, issues a fresh attempt or creates PASS.

### Owner resolution of historical uncertain effects

`host.resolutions.register(BINDING_ID)` installs an owner-approved read-only
whole-invocation query, separately from individual child effect queries. It receives
`{"state": REVIEW_STATE, "arguments": OWNER_ARGUMENTS}`. The state includes the
original caller/ID, fingerprint, immutable uncertain receipt, logical lease fence,
complete saved child keys, observation references and state digest. The application
must inspect authoritative local/remote originals itself and return
`ResolutionObservation`: matching caller/ID/state digest, known `effect`, positive
`all_effects_checked`, `all_results_checked`, `worker_quiescent`, an external
`observation_digest` and reason. A cancelled lease alone does not prove physical
quiescence. Normal provider completion, not-found, one confirmed child, unknown
legacy identity and incomplete local-result inspection cannot close the parent.
The installed query and its operational authority are a stated trust assumption;
the overlay cannot infer arbitrary external effects from a hash or model answer.

In 0.4.2, a fenced dispatched UNKNOWN/held invocation with no terminal receipt
can use the same review API. New Executor claims and dispatches append owner-signed
Event v6 anchors in the corresponding database transactions. They bind the full
immutable request, scope/environment, binding, lease/worker/fence and observed local
parent. The read-only review state additionally includes `request`, `basis`,
`binding` and `local_children`. The query must positively return
`original_request_checked: true` and `all_children_checked: true` as well as the
existing effect/result/quiescence checks. Every recorded local descendant must
have an authenticated completed result or its own active owner resolution; every
remote descendant needs the exact independent original-ID observation. The bound
is 64 descendants/observations. Exceeding it or encountering partial anchors fails
closed. A local completed result still does not prove arbitrary external effects.

For an older writer with neither anchor, explicit review first signs a **current**
recovery observation over the retained row and lease. It does not invent acceptance,
dispatch, a parent relationship or a worker receipt. The installed authoritative
query must establish the full original request and all local/remote/MCP work,
including work absent from the overlay's mappings. Missing external provenance or
physical termination leaves UNKNOWN. The resulting v6 recovery resolution has
`original_receipt: null`, a separate basis reference and origin, and independent
verification UNKNOWN. The original row and held allowance are unchanged. Old
terminal-receipt resolution remains v5. Anchor costs are nested in execution wall
observations; do not count them as an additional charge or treat killed work's
unmeasured consumption as zero. Owner review records inclusive inspection/query
wall overhead; command replay returns its original observation without another query.

```python
event = await host.resolutions.review(
    config.owner,
    original_id,
    command_id,
    installed_query_id,
    tuple(original_child_observation_refs),
    original_caller=original_caller,
)
active = host.resolutions.active(original_caller, original_id)
```

The corresponding owner CLI is:

```text
collective-intelligence-overlay resolve-invocation --config owner/config.json --invocation-id ORIGINAL --original-caller CALLER --command-id REVIEW --checker INSTALLED_QUERY --observations-file ORIGINAL_REFS.json
```

`ORIGINAL_REFS.json` contains the array of exact `{issuer,id}` child reconciliation
receipt references; optional `--arguments-file PATH` supplies installed-query
arguments. Query registration is trusted application code, not a CLI/model grant.
Read-only review remains available at the default 32 unresolved limit and during
drain. Restored intake requires the separate recovery procedure first.

Event v5 records an explicit owner resolution and measured review overhead; it
asserts no independent quality PASS. Migration 0021 starts the indexed current
projection empty, preserving every original invocation/receipt/balance and v1–v4
signed bytes. Claim subtracts only active owner closures from current unresolved
capacity. Budget remains held, original outcome remains UNKNOWN, and no operation
is resent. Concurrent close/claim is serialized with the existing budget→capacity
→invocation→lease→feed order. Historical closed parents cannot dispatch new children.
Repeating the same command/contract returns the historical resolution; changed
contracts conflict and a second close does not recover another slot. Failed owner
reviews retain signed UNKNOWN observation costs without a closure projection.

Resolution is a historical effect disposition, separate from current quality
admission: ordinary evidence updates/expiry and foreign withdrawals do not retract
it. An owner's whole-subject withdrawal of a reviewed local binding reopens its
projection, retaining the historical resolution. Restore invalidates all closures.
A later explicit review needs fresh original observations and unchanged state;
neither inactive history nor a prior closure authorizes refund or re-execution.

The installed document receiver registers `document-original-result`. Supply
`--reconciler document-original-result` with the receiver's original
`remote-words` invocation. This query verifies the saved mapping and original
arguments against the provider's original `words` report, then compares its
integer count and result digest with the whitespace count of that exact text.
`ORIGINAL_DOCUMENT_RESULT_MATCHED` confirms this read-only result;
`DOCUMENT_RESULT_UNCONFIRMED` retains UNKNOWN. This does not establish physical
provider execution, hidden effect absence, general business validity or independent
PASS. Unsupported caller/operation identity and missing legacy argument identity
are refused. The query never reruns the counter or changes the original allowance.

Authenticated ASGI capacity defaults to 16 owner requests and four per caller,
including reads, proposals and body receipt. The configuration fields are
`max_owner_requests` and `max_caller_requests`. Refusals use standard HTTP 503 or
429 with `Retry-After: 1`; body receipt is bounded to 262144 bytes and 30 seconds.
The installed CLI bounds Uvicorn transport connections separately at twice the
owner request limit (32 by default). This leaves room to return the authenticated
capacity refusal; it does not increase the 16/4 request or four execution limits.
Read-only transport retries 429/503 at most three times, with each wait at most
five seconds and the existing network deadline. The same serialized request is
retained. A larger server-requested wait is returned without an early retry.
Invoke/cancel/reconcile/sync/run and other state-changing POSTs are not retried.
The independently bounded Agent Card GET may retry before an invocation is sent.

`backup --config PATH --directory NEW --database-url-env CIO_BACKUP_DATABASE_URL`
requires a stopped owner and a separate explicit PostgreSQL operator connection.
`--pg-prefix-file PATH` accepts JSON argv for an installed native client wrapper;
otherwise `pg_dump` must be on PATH. `--tls-private-key PATH` explicitly includes
an operator-managed proxy private key. The exclusive protected directory includes
the PostgreSQL custom dump, content-addressed artifacts, private identity/DSN,
portable config, application settings/CA when configured, runtime and feed metadata,
and a final digest manifest. It contains secrets: protect/encrypt it with existing
backup tooling. A failed/interrupted backup has no accepted final manifest and is
retained for diagnosis. Existing destinations are refused.

`verify-backup --directory PATH` checks schema-1 manifest structure, exact required
and conditional file references, key self-pin, bounded inventories, digests and
the PostgreSQL custom-archive directory through `pg_restore --list`. The official
`pg_restore` client must be on PATH (or supplied by `CIO_PG_TOOL_PREFIX` JSON argv).
It reports `checksums_verified`, `structure_complete` and `dump_format_verified`
separately from `restoration_tested: false`, `manifest_authenticated: false`,
`external_reconciliation: "not_performed"` and `business_restore_verified: false`.
`complete` retains the compatibility meaning of structure/checksum completion.
These checks do not test archive data restoration, authenticate an unsigned
manifest or reconcile its declared generation with restored database contents.
It does not restore a database or establish
that external work since the backup is represented. `restore-state --config PATH`
requires an offline owner lock, rotates the feed and invalidates freshness. It now
persists closed intake and the commit-ordered publication boundary across restart.
Migration 0020 leaves older restored boundaries unknown; run offline `restore-state`
again before review rather than inventing a boundary from the current counter.
Explicit operator review uses the existing
Registry and signed event path below. Do not manually clear the database flag to
substitute for that review.

The installed application registers a read-only business-state query with an
owner verification grant, then calls `host.recovery.register(BINDING_ID)`.
`recovery-state --config PATH` inspects signed payloads and their database
projections, content-addressed files, invocation/lease/remote-call identity,
allowance, runtime/application settings and completed full-source synchronization.
Every configured foreign source must complete full synchronization after the
restore. Source-declared time governs evidence freshness; local database completion
time establishes ordering after the local restore. Running work must first be
fenced using the existing cleanup path. This inspection grants no intake permission.

`recovery-review --config PATH --command-id ID --checker BINDING_ID
--arguments-file PATH` runs only the explicitly registered read-only query. It
receives `state` and the operator's bounded `arguments` and returns the public
`RecoveryObservation` JSON shape. The application must query authoritative
external state, consumption and original call IDs, including work missing from
the backup. Echoing the restored inputs does not meet that contract. Missing
external inventory, insufficient provenance or unexplained consumption requires
`post_backup_state: unknown`; do not manufacture or discard missing mappings.
The observation must match the exact owner, restored generation, inspected state
digest, independently established balances and uncertain original caller/ID pairs.

The signed receipt and private proof retain UNKNOWN or mismatch. Reusing its
command ID returns the original historical observation without another query.
UNKNOWN exits 2; matched exits 0 but still leaves intake closed. `resume --config
PATH` is a separate control-granted operation: it rechecks the exact inspected state and
query authority before opening intake. A restart does not bypass this check;
changed budgets, records, artifacts, sync or settings require a new review.
These operations never rewrite the original UNKNOWN, refund allowance, issue
independent PASS, or imply that structural restoration recovered external effects.
The complete native production recovery protocol remains an acceptance gate.

For document rollback recovery with a preserved original database, the installed
receiver can additionally set `recovery_reference_config` in its private application
settings to an operator-protected original config path (relative to the settings
file or absolute). Preserve that config and its original database/CAS outside the
restore destination. Configure this before the coherent backup. The factory then
registers `document-recovery-state`; use it as `--checker` with an arguments file
containing `{}`. No request can choose the reference database or file.

For `peer --reference`, the same private setting registers
`reference-recovery-state` for the CSV compatibility application. The settings file
is bounded to 262144 bytes and the reference path to 4096 characters. Both queries
retain an unchecked candidate, an explicit owner-only read-only verification grant
and the same external-original comparison. The query result is not independent PASS.

This optional query opens the original through the existing Store, acquires its
owner lock, uses read-only repeatable-read transactions and compares actual
invocations, leases, remote mappings, allowance, original owner DSSE, CAS bytes
and private application settings/Goal pins.
Recovery observations of the exact restored generation remain separate measured
overhead. Full-sync transfer costs committed after the offline restore boundary
also remain separate in this business comparison. Their original signed bytes and
real measured costs remain in storage and the complete core recovery proof.
Transfer costs from the preserved original, including post-backup costs, remain
part of the comparison. Classification uses committed sequence, not record time.
Missing artifacts, maps, work or consumption produce
`REFERENCE_POST_BACKUP_MISMATCH`. An active original owner, unavailable original
or another closed restored generation produces UNKNOWN. Exact original artifact
bytes can be transferred explicitly before a new review; this creates no PASS.

Keep the original owner stopped and its database/CAS protected from writes through
review and explicit resume. Resume rechecks the saved local proof and query pin;
it does not monitor subsequent changes to that external reference. This query
supports rollback with an available unrewound original. It cannot establish
business consistency after loss of that original, recover arbitrary external
effects or account for inference outside the read-only document contract. Those
cases require a different installed authoritative query and remain closed/UNKNOWN.

`key-rotate --config PATH --directory NEW [--compromised-key-id PINNED_ID]` prepares
an offline key/config/public-pin bundle without overwriting the old files. The
operator updates each peer's current pin and restarts both sides. Historical pins
verify stored DSSE origin; only the current uncompromised key authenticates HTTP
and fresh feed tokens. `historical_keys` maps exact key IDs to public key objects;
`compromised_keyids` explicitly marks known compromised pins. Backdated payload
timestamps never exempt a compromised key. Such history remains inspectable but
cannot authorize admission: qualify returns UNKNOWN pending new checks/version.
An exact page receipt signed by the current uncompromised source key can transport
known historical DSSE origins, including compromised ones, for inspection. The
original envelopes remain unchanged. The receiver verifies the current receipt,
record-set digest, original issuer and historical signature before atomic import.
Unknown keys, bad signatures, altered pages and third-party relays are refused.
Direct submission and admission still require signature authority; a fresh source
checkpoint cannot turn a compromised capability or evidence into an ACCEPT.
Rotation retains the database, artifacts, original call IDs and budgets. It does
not automatically distribute trust, requalify an old scope or undo external effects.

The generated installed runtime configuration shape is
[config.json](../src/collective_intelligence_overlay/schemas/config.json).
`load_config` additionally accepts `database_url_file` instead of `database_url`;
these two credential sources are mutually exclusive. Relative local paths are
resolved against the config file's parent.

`metrics --config PATH --operational` queries the authenticated owner endpoint.
It reports physical request/blocking work, authoritative invocation states,
unresolved held effects, expired running invocations, remaining allowance,
completed source prefixes, retained record counts, actual database size and CAS
usage. `last_allocation` is the configured finite loop's last observation, not a
measurement of all current work. `process` reports actual PID/parent PID and standard
OS user/system CPU seconds since process start. POSIX child counters cover reaped
children only; Windows child counters and RSS remain explicitly unavailable here.
`service_observation_seconds` is a monotonic observation interval, not CPU time.
Use external OS sampling for live descendants/RSS. Historical CPU, model tokens,
currency and provider costs not measured by budget projections remain unavailable;
remaining allowance is not measured consumption.
Service or authorization errors exit 2. This mode cannot combine history/query
flags; existing event/cohort/current-admission metric semantics remain separate.

The service CLI configures standard JSON logging in `log_directory` (default:
the protected identity directory's `logs` child). `log_segment_bytes` defaults
to 8388608 and `log_backup_segments` to seven: at most eight retained segments.
The formatter emits bounded owner/reason/state/correlation/numeric metadata and
exception type, excluding library message bodies, headers and tracebacks.
Standard observations include `DATABASE_CURSOR_FINISHED`/`DATABASE_CURSOR_FAILED`
through SQLAlchemy's public cursor events, `POLICY_DECISION`/`POLICY_INTERRUPTED`,
and `A2A_EXCHANGE_FINISHED`/`A2A_EXCHANGE_FAILED`. Their monotonic durations cover
cursor execution, complete OPA evaluation, and client card-resolution/message exchange
respectively. DB cursor duration excludes connection/pool waits and commit. A returned
A2A result may be an application refusal or UNKNOWN. These process logs are monitoring,
not signed consumption receipts; their nested durations must not be added to request
wall time. Missing observations or rotated history do not mean zero consumption.
SDK imports do not reconfigure an application's logging. Custom application
handlers remain the trusted host's responsibility. Protect native Windows
directories with OS ACLs; POSIX mode bits do not establish Windows isolation.

`Artifacts` defaults to 1048576 bytes per object, 268435456 bytes total and 65536
files. Trusted applications can pass `max_bytes`, `capacity_bytes` and `max_files`
to its constructor. `Config.artifacts()` applies the owner's configured
`artifact_capacity_bytes` and `artifact_max_files` to each standard service instance;
the production profile keeps their defaults. Raising capacity is not acceptance
of a larger workload. Standard native file locking serializes capacity checks and
atomic publication; identical content replay remains allowed at capacity.
Capacity refusal retains existing bytes. `usage()` reports a 90-percent warning;
it never purges signed evidence, withdrawal, call mappings or uncertain leases.
Backup/archive retained history before adjusting limits; deleting such rows is
not a supported retention operation.

The same-volume sibling staging directory separates incomplete writes from the
published CAS. Construction and `recover_staging()` acquire the same bounded
native writer lock. They remove abandoned staging writes and quarantine legacy
CAS `.write-*` bytes outside published inventory. Quarantined bytes remain for
owner review; they are neither promoted nor silently deleted. Unknown entries,
symlinks and staging capacity exhaustion fail closed. `usage()` separates
`staging_bytes`, `staging_files` and `legacy_quarantined_files` from published
`bytes`/`files`. Restart the owner's artifact store before retrying a backup after
a killed legacy writer. POSIX file/directory fsync and atomic rename are used;
Windows has no portable directory-fsync guarantee here. Process-kill recovery
does not establish power-loss durability.

Operational database observations include `database_capacity_warning` at the
configured `database_warning_bytes` threshold (default 8 GiB), and
`history_retention_warning` for locally received records older than
`history_warning_days` (default 365). These are review/backup warnings, not hard
database quotas, expiry decisions or deletion authority. Use `backup` with stopped
writers to archive the complete coherent generation. Preserve current evidence,
withdrawals, original mappings and unresolved leases. Monitor actual server disk
space separately; raising these thresholds does not establish a larger accepted profile.
