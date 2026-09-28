# Python API and CLI

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
only the supplied trusted async operation. Non-ACCEPT raises `AdmissionDenied` with
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
| `peer --config PATH` | Run one A2A reference peer |
| `demo --directory PATH [--database-url URL] [--opa PATH]` | Three-process deterministic loop |
| `inspect --config PATH KIND` | capability/evidence/revocation/event/decision JSON |
| `metrics --config PATH` | Typed cost and event aggregates |
| `doctor --config PATH` | DB and OPA presence; no paid model call |

Success exits 0; invalid arguments/configuration/service failures exit 2. Errors are
redacted by default. `CIO_DEBUG=1` is local troubleshooting only and can include
sensitive exception context; never enable it in shared logs.
