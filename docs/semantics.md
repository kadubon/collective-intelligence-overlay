# Evidence, admission and lifecycle

0.2.1 execution allowance is distinct from measured cost. New invocation rows
track `held`, `released` or `consumed`; migrated rows retain `legacy_unknown`.
The standard one-work reservation is permission to make one dispatched execution,
not a non-refundable admission fee or measured price. Successful completion consumes
that allowance by contract; an uncertain dispatched attempt retains it. USD cost
remains unavailable unless measured elsewhere under an explicit accounting contract.

A failed reserved invocation can release its allowance only while its invocation
and lease still agree on worker/fence. Budget, invocation and lease are locked in
that order, dispatch is fenced, and allowance is returned in the same transaction.
The release marker makes repeat cancellation, cleanup and retry idempotent. No
negative measured cost is emitted. Inspection elapsed time remains recorded as
overhead, even when the business result is UNKNOWN and allowance was released.
The reservation state does not replace the business state or manufacture PASS.

After durable dispatch, no exception type proves non-execution: a parent may have
acted before a child refuses. Even dispatch followed by a final admission refusal
retains the reservation conservatively. Cancellation of an asyncio await does not
stop its database thread; dispatch and release compete through the same durable
state. Unknown commits are not refund authority. Process loss can leave inspection
cost unavailable; later cleanup must not invent a zero measurement.

Generated means a candidate exists. Verified means a named checker produced a
scoped result. Reusable means a receiver has currently admitted that exact candidate
for its request. These states do not collapse into one flag.

Standard policy precedence is REJECT, then UNKNOWN, then REQUALIFY, then ACCEPT.
REJECT means a known local prohibition, valid in-scope negative result or known
revocation. UNKNOWN means missing semantic fit, lineage, license, freshness or policy
execution. REQUALIFY means a known mismatch/expiry or lack of qualifying independent
evidence. ACCEPT is bounded to the checked context, never universal certification.

A request's purpose matters. An operator-granted, read-only `verification` probe
may be permitted before independent PASS exists; its ACCEPT reason means permission
to check that candidate only. It is not ordinary reuse permission. Probe completion
remains UNKNOWN as a business result until a checker issues separate evidence.
Verification receipts cannot serve as observed-use formation links or first reuse.
The [API](api.md) documents this restricted host-controlled grant.

Evidence includes claim, scope, subject/version/digest, issuer, method/version,
receivers, origin declarations, expiry, obligations, dissent and support references.
Pinned operator trust groups and method permissions are distinct from declared
origin text. A group distinction is a diversity proxy, not statistical independence.
The standard policy requires one authorized PASS from a different producer/group;
copies are not counted as extra independent evidence.

In-scope authenticated FAIL takes precedence over PASS. An out-of-scope negative
result or unauthorized method is retained but does not globally revoke anything.
Only the capability issuer can withdraw that capability; only an evidence issuer's
withdrawal invalidates its evidence. Local refusal is a Decision, not forged evidence
of a factual counterexample. No majority vote erases dissent.

Capability dependencies must match exact versions/digests. Cycles, ambiguous IDs,
missing support, oversized graphs and circular evidence remain non-admissible.
The standard traversal has node, depth and work limits. A composite needs its own
applicable evidence in addition to admitted dependencies.

Qualification checks known revocations and expiry again at execution. A remote
withdrawal may remain unknown until refresh; admission expires after the configured
producer/verifier source freshness interval. Network failure does not refresh it. This is bounded
staleness, not instant global revocation or an atomic transaction with an external actuator.
Per-subject revisions and committed source observations refuse admission when related
evidence changes during checking. Unrelated events do not invalidate every decision.
This is not a global lock. The actuator owner must enforce its own idempotency/fencing
for external side effects.

Revocation is a retained tombstone. It does not undo past execution, physically erase
artifacts or unlearn model weights. Artifact copying, import, declared formation and
scope qualification are separate classifications; a new hash does not prove a new function.

Costs use Decimal and retain category, unit and measured/estimated/unavailable status.
Missing costs are null, not zero. Metrics deduplicate issuer/event ID and never add
incompatible currencies or units. Resource reservations are not measured API invoices.
