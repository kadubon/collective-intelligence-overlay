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
`unknown` and is not automatically rerun. Reservations remain reserved/charged;
they are not measured resource consumption. This version does not implement
automatic settlement/refunds. Existing v0.1 historical `actual` values are retained
by migration; new work does not infer actual consumption from reservation quantity.
The low-level `Overlay.execute(request, operation)` remains a trusted-host API;
registered execution binds the exact actuator and actual arguments instead.

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
| `peer --config PATH [--reference]` | Run an A2A peer; explicitly enable the compatibility reference app |
| `demo --directory PATH [--database-url URL] [--opa PATH]` | Three-process deterministic loop |
| `inspect --config PATH KIND` | capability/evidence/revocation/event/decision JSON |
| `metrics --config PATH` | Typed cost and event aggregates |
| `doctor --config PATH` | DB and OPA presence; no paid model call |

Success exits 0; invalid arguments/configuration/service failures exit 2. Errors are
redacted by default. `CIO_DEBUG=1` is local troubleshooting only and can include
sensitive exception context; never enable it in shared logs.
