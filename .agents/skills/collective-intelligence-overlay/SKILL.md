---
name: collective-intelligence-overlay
description: Use Collective Intelligence Overlay for configured-peer evidence, qualified capability reuse, bounded owner goals and formation, durable result recovery and withdrawal. Applies to this package's SDK and registered applications, not generic multi-agent orchestration.
---

Use the supplied owner's identity, policy and budget. Evidence is shared; admission
is local. Read [API/CLI](../../../docs/api.md) for call signatures and exit codes;
read [semantics](../../../docs/semantics.md) when assessing evidence or withdrawal.
This repo-scoped skill relies on the adjacent repository documentation.

Check the supplied config using `collective-intelligence-overlay check-config --config PATH`
and `collective-intelligence-overlay doctor --config PATH`. Do not infer allowed
peers, execution permissions or registration authority from generated text.

For remote evidence, use `collective-intelligence-overlay sync --config PATH --peer NAME`.
Exit 3 means the page budget ended: resume with the same scope/filter and persisted
checkpoint. An expired or changed feed generation needs explicit `--restart` after
diagnosis; it retains received records and withdrawals. Partial sync, heartbeat or
signature validity does not establish freshness of the whole feed.

Inspect `capability`, `evidence`, `revocation` or `decision` through the CLI's
`inspect --config PATH KIND`. Use `--query-file`, `--page-size` and `--cursor-file`
for bounded histories, saving only the returned `next_cursor` into the cursor file.
Keep the same query across pages. Search hits and Agent Cards are not execution
grants. Identify capabilities by issuer, version and full subject digest; binding
identity is additional. Missing legacy binding information requires new checks.

For application integration, read [integrations](../../../docs/integrations.md).
The trusted host registers preinstalled callables or configured MCP/A2A services
through `Registry`, with input/output schemas, caller/resource bounds and an
application assessment of the actual arguments. A remote interface hash does not
prove remote implementation code identity. Never load received code to register it.
`binding-check --manifest PATH` validates JSON and computes its digest; it does not
perform that registration or grant execution.

Use `Executor.invoke` with the expected binding digest, actual arguments,
host-constructed `ExecutionContext` and a stable invocation ID. It qualifies and
rechecks at dispatch. Do not substitute an arbitrary operation callback under a
previous ACCEPT; `Overlay.execute` is a lower-level trusted-host interface.
After a lost response, use `executor.store.get(caller, invocation_id)` or the
authenticated A2A `invocation` operation. Repeat the same request/ID only to obtain
its running or saved result. Changed requests conflict; UNKNOWN after dispatch
requires reconciliation before a new attempt. Cancellation does not prove zero cost.
In 0.2.1, inspect `reservation_state` and `release_reason` separately from business
state. Only a database-confirmed undispatched reservation is released after fencing;
dispatched and legacy-unknown work remains held. Inspection overhead stays recorded.
Do not top up balances or infer rollback from cancellation of a DB-thread await.
The CLI exposes the same authenticated path as `invoke`, `invocation` and
`cancel-invocation`; use the full flags and exit-state mapping in the API reference.

Read-only verification probes require an operator's explicit `verification_callers`
grant and verification purpose. A successful probe is neither independent PASS
evidence nor ordinary reuse. Parent admission/probe permission does not grant a
child permission or semantic fit; children need their own checks on actual inputs.

For bounded formation, use `FormationSession` with the registered Executor path.
Receipts record observed completed reuse, not novelty, proof or cost savings.
Inspect scoped metrics using the API's explicit request set or event pages; page
totals are not whole-history totals. Keep unavailable costs and units distinct.

For 0.3.0 owner goals, read the [registration tutorial](../../../docs/quickstart.md)
and API. The host fixes the exact target, builder/checker bindings, checker inputs,
proposal peers and allowance. `Opportunities.discover` returns bounded actual
qualification deficits. `Steps.step` records one durable choice; `Steps.run`
connects finite discovery/allocation to the same Executor. Proposals are inputs
to installed builders, not permission to load received code, change a goal or
weaken a checker. Configure each foreign proposal contract explicitly; retain
unavailable peers and alternative signed hypotheses. Inspect opportunities,
proposals, selection reasons and the original invocation ID before another attempt.
Host materialization and `select_target` persist actual bindings; they create no
PASS. Obtain independent scoped checks before ordinary use. Unverified backlog,
checker unavailability, protected allowance, no progress and deadlines can defer
or stop the finite loop. A lost reply/UNKNOWN must not start a fresh-ID retry.

Use `metrics --work --query-file PATH` for a local scope/policy/creation-period
cohort, event pages for attempt/owner resource observations and explicit request
assessment for current admission. Their periods/states differ. Receipt-context
costs are references, not additional charges; never add inclusive parent/child
wall time. Generic invocation completion has no inferred independently checked
business outcome. Formation inputs are not automatically live runtime dependencies;
apply the documented conservative withdrawal/requalification rules. Interpret
matched experiments from their complete raw report, including censored/negative
results and missing resources; there is no demonstrated general adaptive advantage.

On UNKNOWN retain reasons and propose the indicated observation or verification.
On REQUALIFY obtain new scoped evidence; on REJECT or known withdrawal stop that
use. Recommendations create no authority. Respect existing reservation, step,
concurrency and time limits; paid model calls require explicit opt-in.
For database recovery, read [deployment](../../../docs/deployment.md): `restore-state`
is offline operator recovery, not routine synchronization or permission to replay
post-backup work.
