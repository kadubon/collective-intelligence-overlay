# Configuration

`Config` in `config.py` is the schema. The demo writes complete JSON examples with
separate keys and database URLs. `check-config --config PATH` validates and loads
the pinned local key without migrating or granting rights. Secrets are never printed
by that command; generated files must be protected with OS ownership/ACLs.

| Field | Meaning |
| --- | --- |
| owner | Local receiver and signing identity |
| database_url | PostgreSQL pg8000 URL for this owner's database role |
| private_key | Operator-controlled Ed25519 PKCS8 PEM path |
| identities | Pinned public keys, authenticated trust groups, allowed verifier methods |
| operator_callers | Explicit pinned identities allowed to drain/resume; empty retains owner-only control |
| artifact_directory | Owner-only local storage; no remote URL fetch |
| opa_binary | Trusted OPA executable path |
| url / peers | Exact configured A2A endpoints and pinned identity names |
| local_development | Permit HTTP only at literal loopback addresses |
| share_records | Default false; explicitly expose own signed records to configured peers |
| policy | License allowlist, permissions, evidence/source freshness limits |
| max_concurrency | A2A work concurrency, default 4 |
| max_owner_requests | Concurrent authenticated overlay requests per owner, default 16, range 1..256 |
| max_caller_requests | Concurrent authenticated overlay requests per caller, default 4, range 1..64 |
| max_steps / max_children | Demo per-peer application requests / child-process bound |
| max_rechecks / max_seconds | Demo requalification allowance / overall deadline |
| database_warning_bytes | Owner database size warning, default 8 GiB; no automatic deletion or hard database quota |
| history_warning_days | Warn about retained records received locally more than this many days ago, default 365; no authority or evidence expiry |

Concurrency limits bound simultaneous work, not requests or CPU/DB use over time.
Execution allowance is separate from authentication, inspection and retained
history costs. Database/history warning settings are observations, not hard quotas.
An operator exposing the service to peers with different trust levels must provide
and verify admission-rate limits and storage/resource limits at the trusted
gateway or host. Authenticate identity before using it as a rate-limit key; an IP
limit alone does not identify a peer. This package provides no token-bucket or
separate inspection/execution capacity-pool service.

In published 0.4.0, a nonempty `operator_callers` replaces the
owner's drain/resume grant. The owner can still inspect status and run the
registered application. Each control caller must have its own current public key
in `identities`; keep its private key outside the runtime account's readable files.
This grant confers no binding execution, verification or application-operation
permission. Existing grants remain explicit at their respective boundaries.
The empty default preserves existing configurations and does not establish
runtime/operator separation. See [API](api.md) for authenticated control commands.

The reference worker handles one attempt per request and starts no child agents.
MAF composition is limited to three workflow iterations. Model examples set their
own SDK call/iteration/time limits. These controls do not provide a universal
termination proof for arbitrary user-supplied operations.

The default policy permits no side-effect permissions and only known permissive
artifact licenses. `semantic_fit` defaults to unknown. It must be confirmed by the
trusted application with a meaningful task/domain assessment, not by generated text.
Exact environment/contract matching is deliberately conservative.

Budget initialization uses `Store.set_budget(unit, Decimal(...))` as an operator-only
operation. The demonstration reserves one `work` unit per attempt and starts with
50 per owner. This is not a currency billing estimate. Expired/uncertain attempts keep
their reservation charged. There is no agent API for increasing its budget.
