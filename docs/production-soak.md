# Installed production soak protocol

The [predeclared profile](profiles/production-040.json) remains the acceptance
authority. This source-only driver operates the normally installed standard `peer`
host, actual HTTPS/official A2A, authenticated official MCP, MAF workflows and three
restricted owner databases. It creates no alternative executor, checker or queue.
Neither a clean driver exit nor a development run establishes production acceptance.

The revised driver saves a consecutive slot number and nominal deadline with
each OS sample, together with its actual start/end. The original-ID export also
retains complete invocation projections and remote mappings. Run
`python scripts/assess_production_soak.py /fresh/results` after quantitative
validation to audit these observations. Missing old projections remain pending;
unknown execution causes still require review. Sampling jitter is disclosed,
and a sample begun after its following nominal slot fails coverage. Original
requests and signed records are public deterministic fixtures in this harness;
these exports are not a safe default for private application data.

Cause review retains exact original requests, signed parent/child receipt lineage
and original remote mappings. A known owner resource refusal can explain retained
work; an observed MCP outage also needs the failing owned transport and an original
journal interval that overlaps its positively confirmed stop/exit interval. A later
retry cannot move an original failure into another fault window. This is an
operational inference about failure, not proof of effect absence or independent
PASS. Missing or mismatched witnesses remain pending. New Linux outage injections
confirm the owned process's stopped status before timing unavailability.
The older development run with 12 held originals remains unaccepted because it
lacks these exact physical outage witnesses and stored specific refusal reasons.

A normally installed CI `5928881` wheel ran seed 2221 through all 11 soak faults.
The 360-second development run preserved 508 signed records, 18 original check
artifacts, 202 invocations and 45 mappings. Its 11 held originals had retained
causes, but the final stop event woke the sampler before its next deadline and
created an invalid early slot. That 75-sample failure is retained.
After the source-only sampler correction, a 180-second development repeat retained
359 signed records, ten check artifacts, 124 invocations, 30 mappings and conserved
allowance. Its 38 consecutive slots had maximum start lateness 0.061747592 seconds;
all applicable quantitative and additional gates passed. The 16 held originals
had bounded retained causes. Removing outage witnesses, physical confirmation or
original signed receipts left unresolved causes; a changed mapping was rejected.
Both reports remain `passed=false` and `release_approval=false`. Different durations
do not support a performance comparison, and neither replaces the required
300-second warmup, 3,600-second measurement and 900 regular offers on the final pair.

The generated render parameter is the document's actual word count. It reaches
the registered render component through the words/report/triage composition;
the protocol records this relationship rather than storing an unused random value.

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

## Preserved first full-duration result

The first formal seed-401 run completed 300 warmup and 3,600 measurement seconds
against the candidate hashes reported in [the matched experiment](production-experiments.md).
It retained 75 warmup, 900 regular and 176 burst offers: 1,151 total.
Original exports verified 3,592 signed records, 149 independent check artifacts,
completed invocation receipts and conserved allowances. No offered row was removed.

| Measured bound | Observation | Result |
| --- | --- | --- |
| Read-only p95 / p99 | 0.452 / 0.704 seconds | Within 2 / 5 seconds |
| Invoke p99, all outcomes | 2.991 seconds | Within 35 seconds |
| Finite loop/check p95 / p99 | 3.651 / 8.487 seconds | Within 120 / 180 seconds |
| Absolute operation wall | 21.967 seconds | Within 180 seconds |
| Normal classified fraction / throughput | 1.0 / 0.25 per second | Within declared targets |
| Owner RSS peak | 312,582,144 bytes | Within 768 MiB |
| Owner RSS growth after warmup | 142,512,128 bytes | **Exceeds 128 MiB** |
| Known uncertainty / current unverified targets | 13 / 1 maximum | Within 32 / 8 |

This is a failed acceptance run. Withdrawal and drain injections failed, and
complete safety/sample/backlog assessment remains open. During the withdrawal
snapshot/delivery, a regular independent check issued fresh PASS evidence. Its
original DSSE and CAS proof cover a completed result under the fixed threshold;
the later ACCEPT references that new evidence. This is not proof of reuse relying
only on withdrawn support. The fixture now stops and positively locks the checker,
delivers actual signed withdrawals, checks receiver admission, then restarts the
checker for an explicit independent requalification.

The drain request returned a transport error during a scheduled burst; the fixture
then tested an owner without confirming intake was closed. It now retains up to
three explicit idempotent control attempts and positively queries state before
offering the new effect. It never retries an uncertain invocation. The complete
360-second development repeat executed all eleven injections and validated 519
original signed records; it does not count as the new formal hour.

The initial quantitative validator represented missing recovery time with a numeric
sentinel. That report remains retained. Corrected reports separately list faults
without recovery confirmation and measure only actual observed recovery intervals.
An unconfirmed fault cannot become a measured one-billion-second recovery.

Memory diagnosis additionally reproduced SDK producer/consumer queues remaining
after completed Message exchanges. The host now uses the pinned official public
handler described in [compatibility](compatibility.md). The diagnostic launcher
records traced Python allocations separately from OS RSS and a final explicit GC;
neither tracing nor that intervention is part of formal performance acceptance.
The original failure and sources are preserved. These fixes required a complete
new run under unchanged numerical gates; the result follows.

## Complete repeat after the memory and fault fixes

The subsequent formal seed-401 run on candidate `900a955` completed the unchanged
300-second warmup and 3,600-second measurement. All 1,151 offered rows were retained,
all eleven injections executed, and the original-result assessment passed all
twenty quantitative gates and three additional safety/sample/backlog gates. It
verified 150 original independent check artifacts. The earlier failed run remains
retained and is not reclassified by this result.

| Measured bound | Observation | Result |
| --- | --- | --- |
| Read-only p50 / p95 / p99, 716 outcomes | 0.119 / 0.454 / 1.125 seconds | Passed |
| Invoke p50 / p95 / p99, all 225 outcomes | 1.717 / 2.470 / 2.795 seconds | Passed |
| Finite loop/check p50 / p95 / p99, all 135 outcomes | 2.444 / 3.459 / 4.439 seconds | Passed |
| Maximum operation wall | 21.981 seconds | Within 180 seconds |
| Normal classified fraction / throughput | 1.0 / 0.25 per second | Passed |
| Owner RSS peak | 234,369,024 bytes | Within 768 MiB |
| Maximum owner RSS growth after warmup | 99,782,656 bytes | Within 128 MiB |
| DB / CAS / rotated-log growth | 39,583,744 / 420,765 / 37,184,795 bytes | Passed |
| Maximum unresolved effects / selected unverified targets | 14 / 1 | Within 32 / 8 |
| Maximum confirmed fault recovery | 31.153 seconds | All eleven confirmed |

Verification backlog observations cover the two operator-selected report/triage
UseRequests, not every historical candidate. OS resource samples and original
effect/signature/refusal observations were checked separately. These results apply
to the declared workload and measured host; they do not establish a universal SLA
or an hour-long macOS/Windows soak.

Wheel SHA256: `df3df71b44df5bcc81e8edc131d8f4bfb607b8427e5ea5c0b190428fda6e95b9`.
Sdist SHA256: `bffec2d6be137846d4c434a068ce9de49438f20c27824449114ad298e9668161`.
The retained original reports and assessment are at
`.local/production-040/soak-formal-900a955-v1/` in the development evidence. This
successful earlier candidate is not the final release pair. Capacity and packaged
documentation changes require the new final-candidate run identified in
[the current acceptance status](production-040.md).

## Preserved first final-pair result

Run `36848916312` completed the unchanged seed-401 300+3,600-second protocol on
the final `33898a96` wheel and `965f848e` sdist. Original archive digest
`7ce803f8cc572aefab65cff83b31cc95f12b05473e47dc90abf392248791bc64`
and all 110 report-file hashes were verified. The raw file-manifest SHA256 is
`a937947d27c50e5ea8dba7c1a1c60a7f4f95b9781909e145b7db2dbc0c27107f`.
This manifest identifies failed evidence and is not an accepted release manifest.

Nineteen quantitative gates and two additional gates passed. The same-ID duplicate
injection failed: the initial completed invocation `warmup-regular-2` was offered
again with the same request at session second 1,513.422, but the client recorded a
`ValueError` after 0.183 seconds without a response. This does not prove a changed
receipt or establish the required successful duplicate observation. The later
owner restart returned exactly the original completed receipt, with no changed
fields. Its success is preserved separately and cannot repair the earlier gate.
The precise transport failure cause is unconfirmed.

The assessment therefore returns `passed: false`, despite the driver's successful
job exit. Both `all_predeclared_faults_executed` and
`original_effect_signature_and_refusal_audit` remain false. A complete repeat in
run `36858429932` uses the same fixed pair, sources, workload and numerical gates;
the failed first run remains failed, with its original reports unchanged.
