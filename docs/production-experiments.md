# Production matched experiment

The source-only runner uses the installed `peer` CLI, public authenticated A2A
operations, restricted per-owner PostgreSQL roles, the reviewed Caddy build,
official authenticated MCP and the reference application's actual MAF workflow.
It reuses the HTTPS test setup and original signed-observation exporter. It does
not implement another executor, budget, planner or checker.

The [predeclared profile](profiles/production-040.json) is the acceptance authority.
The final unchanged-pair five-pair run passed the fixed protocol, and complete
production acceptance/publication are recorded in [actual results](release-040-results.json).
The older checkpoint sections below preserve their earlier scope. No general
adaptive benefit is established.
Model calls remain off.

## Fixed protocol

Five fresh matched pairs use seeds 17, 29, 43, 71 and 101, alternating arm order as
declared. Each arm has three fresh owners, signing identities, restricted databases,
private artifact homes, independent evidence and its own durable result cache.
Both arms receive identical installed primitives, builders/checkers, task inputs,
allowances and execution limits. The static arm uses the existing rational fixed
report/check/triage/check policy and may reuse its own completed results. The
adaptive arm uses the existing observation/proposal/allocation loop.

Six formation documents, generated from a seed-specific `formation` namespace,
make one operator calibration document and six practice tasks. The held-out
generator has a separate namespace and produces 24 varying Unicode/whitespace
documents. Neither input set is selected from observed outcomes. The quality
contract is the reference triage result and an independently signed verifier check;
this deterministic contract does not evaluate general reasoning or novelty.

Condition assignments are fixed before running: seed 29 batches eight independent
checks after sequential business uses to exercise the unchanged checker/caller
capacity; seed 43 starts with a v1 report candidate and a requested v2 input adapter.
The other three seeds use normal capacity. Both arms receive the same condition.
No quota refusal, failed check or UNKNOWN is retried as a fresh task to improve the
score. Every held-out task remains in its arm's denominator, including an absent
output or bounded interruption. Conditions with one pair have limited external
validity and are not separate adequately powered studies.

## Execute and inspect

Run from this repository with a normal installed candidate wheel in a dedicated
Linux Python environment containing the reviewed agents dependencies. The runner
checks local wheel provenance against the unchanged candidate manifest. Source
checkout and editable-import results are development observations.
The origin metadata may omit an archive hash under the [PyPA specification](https://packaging.python.org/en/latest/specifications/direct-url-data-structure/).
The runner checks the fixed local wheel origin and compares every installed package
file with that wheel, excluding only installer-generated metadata such as RECORD.
This does not skip package code or infer identity from the version string.
Supply an operator database DSN through the protected environment; this connection creates
only exclusively generated test databases/roles and is never handed to peers.
The private destination and result destination must be new, distinct directories.

```sh
python scripts/run_production_experiment.py \
  --opa /trusted/opa \
  --caddy /trusted/caddy \
  --candidate /fixed/candidate \
  --output /fresh/results \
  --private /fresh/runtime-homes \
  --contention-notes "Describe actual other work on this machine"
python scripts/validate_production_experiment.py /fresh/results
```

`CIO_TEST_DATABASE_URL` must already contain the operator DSN. `candidate` contains
the unchanged `artifacts.json` and `dist/` wheel/sdist pair. Use the audited custom
proxy from [the proxy build reference](../scripts/proxy/README.md). Neither binary
is downloaded or replaced by this runner. A separate `--development-seed` outside
the formal seed set, optionally with `--development-condition`, tests the harness;
such a run cannot count as a formal pair. The formal assignment cannot be overridden.

The runner preserves its exact sources, protocol, artifact/binary digests, offered
call outcomes, invocation identities, results, original signed records, independent
check artifacts, reservations and resource observations. Results contain public
fixture inputs and public identities. Private keys, database credentials and MCP
tokens stay in protected runtime homes. Do not publish or archive those homes with
the result report. A failed run uses another fresh destination for its complete
repeat; keep the original failure and its source/protocol unchanged.

The validator rechecks original DSSE, per-arm key/database isolation, allowance
conservation, all input/denominator counts, independent check artifacts and the
original signed execution receipts covering each completed input/result. It does
not infer business PASS from transport completion or monitoring logs.

## Resource and statistical limits

Original signed event costs retain formation/check/transfer/failure resources and
unavailable currency. Remaining work allowance is not measured consumption.
Monotonic client wall time and DB cursor/OPA/A2A log durations are separate series:
nested request and child durations must not be added. Linux `/proc` samples actual
owner/descendant, MCP, proxy and shared PostgreSQL resident sets/CPU every five
seconds. Short-lived child peaks may be missed; shared PostgreSQL/background CPU
does not have exact per-arm attribution. CPU counters, RSS, bytes, wall time and
allowance keep their units and periods. Model tokens and currency remain explicitly
unavailable; no counterfactual savings are reported as measured consumption.

Analysis uses five paired differences, their observed range and descriptive paired
bootstrap percentiles. Tasks and peers inside a pair are dependent observations.
The small pair count and deterministic reference application limit interpretation.
A zero or negative difference is valid and does not fail the release gate.

## Development observations

A separate seed 1009 normal run completed both arms with 24/24 independently
checked tasks. Its saved observations verified 992 original signed records across
six separate owner databases and conserved allowances. Three modified copies were
denied for changing a denominator, a business result or a check artifact.
The initial check artifacts were exported from unchanged private CAS after the run;
later runner versions export them before cleanup.

Development seed 1013 under checker pressure retained 3/24 independent PASS in
each arm. Its final protocol validation failed because integer JSON keys changed
the sorted digest after serialization. The raw failure remains retained; it is
not an accepted experiment. The runner now uses string keys and verifies the JSON
round trip before starting any arm. Formal seeds, criteria and quotas were not
changed to repair this report-format failure.

The next checker-pressure repeat reached its post-run transcript guard, which
incorrectly compared completion order with offer order under concurrency. That
failure is also retained. Observations now have a unique `call_index`, and the
validator compares every completion with its original offer. A third complete
repeat validated six distinct databases, 698 signed records and conserved
allowances, with 3/24 independent PASS in each arm. The completed connection
development condition at seed 1019 validated 998 signed records and 24/24 PASS
per arm. These are separate development fixtures, not additional formal pairs.

## Installed five-pair observation

One fixed candidate wheel/sdist pair completed all ten arms on native WSL Linux
CPython 3.12.14. All 83 installed wheel files matched the candidate. Thirty distinct
restricted owner databases and distinct signing identities were verified; 4,679
original signed records, original check artifacts, execution receipts and allowance
conservation passed the saved-result validator. All 240 held-out observations remain
in their original denominators.

| Seed | Condition | Static independent PASS | Adaptive independent PASS |
| --- | --- | --- | --- |
| 17 | Normal | 24/24 | 24/24 |
| 29 | Verification bottleneck | 3/24 | 3/24 |
| 43 | Connection mismatch | 24/24 | 24/24 |
| 71 | Normal | 24/24 | 24/24 |
| 101 | Normal | 24/24 | 24/24 |

All five paired differences were zero. The descriptive paired-bootstrap interval
was [0, 0]; its degeneracy is not evidence that other inputs, systems or workloads
cannot differ. End-to-end arm times including export ranged from 83.33 to 175.76
seconds. The shorter pressure arms refused many checks, so they do not establish
faster successful processing. OS CPU/RSS, nested monitoring durations and typed
signed costs remain separate raw series, with their documented missing resources.

Wheel SHA256: `c763fbe65dd34ec7a42a1ba466d37c028a1c8e058f8dfb433ce256d7a8a4b4f4`.
Sdist SHA256: `f64fd08b323f762c3791c46211b5c25d06a6d1f5c3c87d618d72c8d2cf17f554`.
Protocol SHA256: `fa5e46f4f414495eb5391ce0efbc5554404abf3b35d448fcfefc1690b1502d68`.
These artifacts are still unpublished candidates. Full resource/profile assessment
and final release-candidate matching are required before accepting P25.

The separate `scripts/assess_production_experiment.py` assessment revalidates those
original outcomes and exports typed cost observations by owner/category/unit/status,
owner CPU snapshots, sampled RSS, database/CAS sizes, reservation states, monitoring
and inclusive client duration distributions. Received replicas are not additional
charges. Inclusive parent/child times and live/reaped CPU counters are not summed.
All ten measured inclusive arm times were below 500 seconds, but the profile's
`allowance_per_owner_seconds` is not the executed ledger's `work` unit. The assessor
retains that protocol deviation and returns `passed: false`; it does not convert
500 work credits into 500 seconds or retrospectively accept the experiment.

The revised runner declares a separate 500-second monotonic wall envelope for
each owner. A common deadline begins before setup and includes idle time, checks
and all business work. It reserves 30 seconds for concurrent physical shutdown;
the existing 500 work credits remain a separate constraint. The report saves
each actual process start/stop time and positive exit confirmation. The assessor
requires those original observations, so old runs without them remain unaccepted.
This conservative common envelope gives no owner more than its declared seconds;
it does not estimate consumed CPU from elapsed time. A new complete ten-arm run
is required on the revised fixed artifacts.

The revised formal run on candidate `0747d731aac5eddac527b9ab3f7488e25b2ae4dd`
completed all ten arms and passed the original-record/resource/time-unit assessment.
Seeds 17/43/71/101 yielded 24/24 independently checked tasks in each arm; seed 29's
verification bottleneck yielded 3/24 in each arm. All five paired success-fraction
differences were zero. Inclusive elapsed arm times ranged from 81.94 to 183.65
seconds; actual owner physical shutdown was confirmed within the separate
500-second allowance. Retained raw calls, DSSE, process samples and typed costs are
at `.local/production-040/experiment-formal-0747d73-v1/` in the development evidence.
This deterministic application supplies no evidence of general adaptive advantage;
the zero descriptive paired interval is not a population equivalence claim.
Subsequent capacity/documentation changes require a new final-candidate run.

## First final-pair observation

Run `36848916312` completed the five isolated pairs and all ten arms on the final
`33898a96` wheel / `965f848e` sdist pair. Its original report-file manifest and
fixed source/profile digests were verified; the original-result/resource/time-unit
assessment passed. Every paired success-fraction difference was zero, with the
descriptive paired-bootstrap interval [0, 0]. Inclusive arm times ranged from
46.092 to 66.803 seconds; the separately declared 500-second owner wall allowance
and positive physical shutdown observations passed.

This supplies no general adaptive advantage or population equivalence result.
The same run's soak failed its duplicate-delivery observation, so the complete
production profile remains unaccepted. Both the experiment's positive assessment
and the soak's negative assessment are retained. The complete repeat identified in
[the current acceptance status](production-040.md) uses the same pair and criteria.


## Complete unchanged final-pair repeat

The successful formal repeat in run `36858429932` uses the same fixed pair,
five seeds, conditions, sources and criteria. All ten isolated arms passed original
signature/result/resource/time-envelope validation: 30 separate restricted databases,
4,713 verified original signed records, conserved allowances, all 240 task
denominators and positive physical owner shutdown within 500 wall seconds.

| Seed | Static independent PASS | Adaptive independent PASS |
| --- | --- | --- |
| 17 | 24/24 | 24/24 |
| 29 | 4/24 | 3/24 |
| 43 | 24/24 | 24/24 |
| 71 | 24/24 | 24/24 |
| 101 | 24/24 | 24/24 |

Adaptive-minus-static paired differences are `[0, -1/24, 0, 0, 0]`, with mean
`-0.0083333333` and descriptive paired-bootstrap 95% endpoints `[-0.025, 0]`.
Inclusive arm durations ranged from 48.074 to 71.767 seconds. Pressure refusals
remain in the denominator and do not establish faster successful processing.
Five pairs, dependent tasks and this deterministic contract do not establish
general advantage, statistical superiority or population equivalence. The earlier
same-pair zero-difference observation is retained separately; both results are
reported. Negative effects are valid and are not an operational release failure.

The original ZIP and complete raw manifest are shared with the
[successful soak repeat](production-soak.md). Both formal assessments now pass;
complete production acceptance and actual publication remain separate gates.
