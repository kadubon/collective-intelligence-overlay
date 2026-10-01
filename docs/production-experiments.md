# Production matched experiment

The source-only runner uses the installed `peer` CLI, public authenticated A2A
operations, restricted per-owner PostgreSQL roles, the reviewed Caddy build,
official authenticated MCP and the reference application's actual MAF workflow.
It reuses the HTTPS test setup and original signed-observation exporter. It does
not implement another executor, budget, planner or checker.

The [predeclared profile](profiles/production-040.json) is the acceptance authority.
Current development observations are not the completed five-pair experiment and
do not establish a general adaptive benefit. Model calls remain off.

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
checkout and editable-import results are development observations. Supply an
The origin metadata may omit an archive hash under the [PyPA specification](https://packaging.python.org/en/latest/specifications/direct-url-data-structure/).
The runner checks the fixed local wheel origin and compares every installed package
file with that wheel, excluding only installer-generated metadata such as RECORD.
This does not skip package code or infer identity from the version string.
operator database DSN through the protected environment; this connection creates
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
