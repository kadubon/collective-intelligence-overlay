# Evaluation and metrics

The 0.3.0 `examples/adaptive_documents.py` application now has a three-process
integration path where the harness supplies checked initial primitives, then the
receiver discovers deficits and selects authenticated alternatives itself. It
materializes a report workflow from observed component use, checks it independently,
and uses that workflow to derive and form a parameterized document classifier.
Two calibration inputs are tested in separate databases and processes, producing
different thresholds. These are integration cases, not independent statistical
evidence of an adaptive benefit. The application now uses the core allocator and
checks its checker bindings through independent finite contract tests before reuse.
The isolated pilot below supplies initial matched observations. The declared finite workload retains costs and explicit missing resources; do not infer cost savings from
integration-test duration or the number of candidates.

The fixed document control is exposed as the owner-only `static-run` operation in
the same external application. It uses a prespecified report/check/triage/check
order, the first registered builder, the same calibration text, installed
materialization code, independently calibrated checker, initial allowance and
ordinary use-time admission. It caches completed invocations and skips currently
qualified goals. It calls neither opportunity discovery, proposal exchange nor the
adaptive allocator. Host goal persistence is shared configuration plumbing. This
is a 0.2.1-equivalent verified-reuse control on the current implementation, not an
execution of an old installed binary. It is not the allocator's `mode="static"`,
which still participates in opportunity discovery.

## Isolated document pilot (2026-09-28)

Run with the existing PostgreSQL/OPA prerequisites and optional agents dependencies:

```console
uv run python examples/evaluate_documents.py --directory .local/document-comparison --opa PATH_TO_OPA --seed 0
uv run python examples/evaluate_documents.py --verify EXTRACTED_REPORT_DIRECTORY
```

`CIO_TEST_DATABASE_URL` must name a dedicated PostgreSQL admin database. Each arm
creates three new databases, identities and artifact/cache directories; existing
arm directories are rejected. Processes stop after each arm; databases and local
private configuration remain for inspection. The command writes its protocol before
running, retains every failed/censored arm and does not use paid model inference.
Exit zero means the collection completed, not that all business tasks passed.

The current v3 protocol adds a third, matched connection condition. The receiver
starts with an operator-installed report candidate accepting `text`, while its
goal requires `document` (`report.in.v2`). Ordinary qualification observes the
scope mismatch. Adaptive allocation selects connection work before the downstream
formation; the fixed control encounters the same mismatch in its fixed order.
Both use the same installed input adapter, counter, renderer and checker. Actual
transformation occurs inside the report workflow and the subsequent triage caller;
it is not a relabeled scope or permission change. The resulting binding requires
fresh independent evidence. The initial candidate has no PASS or formation receipt.
Initialization time is included in elapsed observations; primitive checking and
later formation/checking draw only from that arm's allowance. This tests
input-contract adaptation, not arbitrary platform or
environment portability. `time_to_success_seconds` stays null for failed or
censored arms; their last-outcome time and unreached tasks remain in the report.

[Pilot 3 raw reports and source snapshots](../experiments/documents-pilot-3.zip)
contain all six preregistered assignments, run serially with seed 0. The package
source was unchanged from commit `765fedd`; the three application sources are
included with their pre-run hashes. No tests ran concurrently with this comparison.

| Condition | Mode | Checked formations | Business passed / unreached | Last-outcome seconds | Time to success seconds |
| --- | --- | --- | --- | --- | --- |
| Normal | Fixed | 2 | 3 / 0 | 53.376 | 53.376 |
| Normal | Adaptive | 2 | 3 / 0 | 59.730 | 59.730 |
| Checking constrained | Fixed | 1 | 0 / 3 | 38.160 | null |
| Checking constrained | Adaptive | 1 | 0 / 3 | 39.444 | null |
| Input connection mismatch | Fixed | 2 | 3 / 0 | 49.253 | 49.253 |
| Input connection mismatch | Adaptive | 2 | 3 / 0 | 54.132 | 54.132 |

Normal and connection conditions started with work allowance 50 for every owner;
the checking condition used producer/verifier/receiver allowances 50/14/50.
Normal/connection arms ended at 39/35/16; checking-constrained arms ended at
43/0/32. The adaptive connection arm records `connection_backlog` and chooses a
connection before later verification and formation. The fixed arm uses the same
adapter in its ordinary fixed order. Both reach identical checked outcomes and
contractual balances; adaptive elapsed observations are higher in each matched
pair. There is no measured quality or allowance benefit in this single-run pilot.
These six arms do not establish statistical superiority, physical resource savings
or general environment portability. CPU, tokens and currency remain unmeasured.
Validation checks all 858 exported signed records, 18 separate databases, key
separation, allowance conservation and reported business/evidence consistency.

[Pilot 2 raw reports and source snapshots](../experiments/documents-pilot-2.zip)
contain one fixed-seed run per condition. The owner order for allowances below is
producer/verifier/receiver. Elapsed time includes database/key/template preparation,
primitive and checker testing, synchronization, formation and attempted business
evaluation; export time is separately retained. It is an inclusive observation,
not the sum of parent/child or peer timings.

| Condition | Mode | Initial work allowance | Formed targets independently checked | Business tasks passed / unreached | Elapsed seconds | Stop |
| --- | --- | --- | --- | --- | --- | --- |
| Normal | Fixed | 50/50/50 | 2 | 3 / 0 | 48.239 | Goals satisfied |
| Normal | Adaptive | 50/50/50 | 2 | 3 / 0 | 52.806 | Goals satisfied |
| Checking constrained | Fixed | 50/14/50 | 1 | 0 / 3 | 34.581 | Check not completed |
| Checking constrained | Adaptive | 50/14/50 | 1 | 0 / 3 | 43.849 | Check not completed |

Both normal arms retained allowance 39/35/16; both constrained arms retained
43/0/32. These are contractual balances, not measured CPU, tokens or currency.
Neither outcome count nor allowance saving favored adaptation in this pilot.
Adaptive elapsed observations were higher; a single run does not estimate an
expected difference or statistical significance. The three business tasks are
dependent tasks within an arm, not three independent trials.

The [first pilot](../experiments/documents-pilot-1.zip) used verifier allowance 10.
Both constrained arms stopped during initial checker calibration, before testing
formation allocation. Both normal arms passed all three business outputs. Those
negative results were retained; pilot 2 declared the revised allowance before its
run. Pilot 1 has raw observations and public keys but no complete source snapshot;
it is exploratory evidence, not a fully reproducible release benchmark.

Pilot 2 validation checks 12 distinct databases, distinct signing identities across
arms, 550 signed records, budget conservation and held-out count consistency.
It also binds reported checker evidence to signed records. This is consistency
checking of operator-produced observations, not an external audit or universal
correctness proof. Raw reports separate original estimates, elapsed observations,
reservations, missing CPU/token/currency costs and unreached tasks. Missing costs
are not zero. Pilot 3 adds input-connection conditions and retains each stage's signed owner
costs. Final artifact/CI gates remain separate. Positive benefit is not a gate.

The [mixed-history scale harness](scale.md) measures indexed qualification at
1,000/10,000 records and offers a selectable 100,000-record stress profile.

0.2.0 adds bounded history pages and current assessment of an explicit target set;
the [API reference](api.md) defines filters, cursors and aggregation rules. Historical
independent PASS reports are counted separately from current ACCEPT decisions.
Distinct capability counts use issuer/subject/binding identity; multiple use requests
for the same capability are also reported as targets, without asserting multiple new
capabilities. Historical PASS does not imply a currently valid support chain, lack of
counterevidence, current installation or universal correctness. Keep each request's
scope, applicability assessment and evaluation time alongside its result.

First verification and reuse delays use local record receipt times. They measure
local observation lag, not provider computation time or cross-organization clocks.
Missing, legacy or out-of-order observations remain null. New wall-time observations
and legacy undifferentiated `seconds` are not additive resource consumption.
Historical measurements retain their original units as observations; they are not
retroactively reclassified as invoices or measured API charges.

The three-process demo measures real interoperability and lifecycle enforcement.
Its formation input differs from the held-out CSV used by the receiver. Separate
checks validate row count and decimal aggregate consistency; composite output is
checked again. These tests do not prove universal algorithm correctness or semantic
transfer beyond the declared reference domain.

The demo also runs four network arms against the same three live peer processes:
- single agent: producer transforms and checks locally, with its own bounded cache;
- multiple agents without persistent capability sharing: producer computes and the
  verifier checks each result, without receiver-side evidence reuse;
- shared memory: a plain result cache, followed by the same independent checker;
- overlay: the receiver qualifies and executes the capability, followed by the same
  output checker.

All arms use the same held-out CSVs, preinstalled function and serial work bound.
Network, verification and overlay overhead are timed. Initial formation/transfer time
is reported separately, and no counterfactual saving is inferred. Real model budgets,
long-term maintenance and organization effects remain unmeasured.

`scripts/evaluate_reference.py` runs the same three-process registered demo and
writes `evaluation.json`; it does not maintain a second execution path. The overlay
arm uses a checked receiver-side A2A binding, provider admission and durable
invocations. Setup includes registration, checking, synchronization and service
import. The historical `shared_formation_transfer_seconds` output key is retained
for compatibility; it does not claim the preinstalled CSV algorithm was invented.
Elapsed times include network, execution, checking and overlay overhead. Unknown
currency and long-term maintenance remain unavailable. No cost saving is inferred
from an unmeasured counterfactual; this test may show only overhead.

Metrics group immutable events and typed cost records. They retain formation,
verification, transfer, use, failure, maintenance and other categories when supplied.
Unobserved categories are not zero-valued observations. Receiver decisions and
recommendations identify verification, connection, observation or repair work for
subsequent attempts; recommendations cannot create permissions or budget.

Work reports join selected invocations to original signed local execution receipts
and label resource observations by formation/connection/verification/observation/
repair kind. They preserve original selection estimates and current reservation/
UNKNOWN state. Scoped event pages supply attempt/deferral counts and owner costs
for children, remote work, failures and maintenance. Shared allocation overhead is
referenced once, not charged to every opportunity. This is not another ledger.
The [API](api.md) explains the opportunity cohort versus event period, fixed cursors
and finite receipt-reference budget. Use the isolated application's contract report
for independently checked business outputs and unreached/censored tasks; generic
completion has no inferred checked outcome. Unobserved future maintenance is
unavailable, not a zero lifetime cost. Keep owner quantities separate and use
inclusive elapsed time for time-to-success without adding parent/child timings.

Lineage pages expose exact authenticated execution links and use-to-formation
timestamp differences; missing/out-of-order observations are null. These are
follow-on construction delays, not a global first-formation statistic or causal
acceleration. Completed reuse and its remote A2A subset are distinguished from
replication/import events. An import cannot prove code installation; the document
host independently persists/reconstructs and checks installed parameters. These
classifications do not count functionally new capacity.

No aggregate intelligence score, ASI probability, general endogenous-growth proof,
statistical independence or production SLO is emitted. Longitudinal resource-matched
multi-organization/model comparisons remain future empirical work.
