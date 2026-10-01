# Installed production soak protocol

The [predeclared profile](profiles/production-040.json) remains the acceptance
authority. This source-only driver operates the normally installed standard `peer`
host, actual HTTPS/official A2A, authenticated official MCP, MAF workflows and three
restricted owner databases. It creates no alternative executor, checker or queue.
Neither a clean driver exit nor a development run establishes production acceptance.

The release run has a 300-second warmup and 3,600 measured seconds. Seed 401 fixes
900 regular offers at 0.25 requests/second in the declared 15/20/20/25/15/5 mix.
Each 20-offer block has those exact proportions. Fixed 16-request bursts at each
300-second boundary are recorded separately, in addition to the regular denominator.
Every failed, refused, UNKNOWN, absent or censored offer is retained.

Discovery offers synchronize the producer/verifier reciprocally and the receiver
with one configured source. This updates local complete-prefix observations, never
old evidence or capability expiry. Finite formation/check offers run the existing
bounded goal loop and a distinct independent check. Original-result queries use
actual completed IDs. The reference's one-hour signed validity is retained; expired
records cannot be renewed by copying or restarting. The report must show business
outcomes separately from classified transport responses.

Eleven fault injections follow the declared order, each 300 seconds apart. Their
fixed 60-second windows are excluded from normal-window metrics by offer time;
all outcomes remain in overall metrics. The driver records explicit stop/restart,
SIGSTOP/SIGCONT delay, original-ID duplicate queries, signed evidence withdrawal
and distinct new checking, owner crash, physical owner-DB backend termination,
drain/refusal/resume, caller pressure and missing effect confirmation. The final
budget-pressure injection uses an explicit operator `Store.acquire` reservation of
remaining work allowance. It retains that reservation and does not top up or refund.
Remaining allowance is not measured CPU, wall time or money.

OS `/proc` sampling runs every five seconds independently of HTTP/DB observations.
Each owner and living descendant has separate RSS/CPU counters. MCP, proxy and the
shared PostgreSQL cluster are separate groups. A maximum of one monitoring request
per owner and one assessment of the two actual report/triage targets remains pending;
unavailable observations are not invented as zero. Existing `capability_metrics`
supplies current scoped verification counts/age, distinct from historical allocation.
Short-lived child peaks and exact per-owner shared-PostgreSQL CPU stay unavailable.
Nested DB/OPA/A2A intervals are not additive consumption.

Use a fresh normally installed candidate environment and protected operator DSN:

```sh
python scripts/run_production_soak.py \
  --opa /trusted/opa --caddy /trusted/caddy \
  --candidate /fixed/candidate \
  --output /fresh/results --private /fresh/private-runtime \
  --contention-notes "Describe actual other work on the machine"
python scripts/validate_production_soak.py /fresh/results
```

The candidate manifest and installed file bytes are checked before setup. Sources,
original signed records, CAS bytes, latencies, offers, failures, resource samples,
held reservations and bounded rotated-log sizes are retained separately from keys,
DSNs and tokens. Do not archive private runtime homes with shareable observations.
The validator currently reports quantitative observations and explicit outstanding
validation; it cannot mark the release accepted.

A separate seed 1409 development run used five warmup and 360 measured seconds,
with compressed fault intervals. It retained 90 regular offers, 176 burst offers
and one warmup offer. Ten fault injections executed, but its missing-reconciliation
fixture incorrectly queried a workflow root as if it were the nested A2A child's
parent ID. That failure and source are preserved. The fixture now performs one
explicit direct registered A2A call with its own original ID before querying its
map. This is a separate declared operation, never a retry of uncertain workflow
work under a fresh ID. The initial export verified 470 original signed records
and conserved allowances; it is not a successful release soak.

The complete seed-1409 development repeat retained all 267 offers and executed
all eleven injections. Its saved exports verified 515 original signed records,
17 independently signed check artifacts, unchanged completed execution receipts
and conserved allowances. Observed latency/RSS/disk/backlog bounds passed that short
fixture. The driver now keeps an explicit direct A2A invocation from setup for
later original-ID reconciliation, so caller-capacity refusal cannot manufacture
a replacement mapping. The initial quantitative-validator attempt used the wrong
`items` key for the existing API's `targets` and failed; that output is retained.
The corrected assessment still leaves full-duration, sample coverage, uncertainty
explanation and complete safety assessment unaccepted. Short results are not
extrapolated into an hour-long observation.
