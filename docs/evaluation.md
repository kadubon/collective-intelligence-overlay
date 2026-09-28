# Evaluation and metrics

The unreleased `examples/adaptive_documents.py` application now has a three-process
integration path where the harness supplies checked initial primitives, then the
receiver discovers deficits and selects authenticated alternatives itself. It
materializes a report workflow from observed component use, checks it independently,
and uses that workflow to derive and form a parameterized document classifier.
Two calibration inputs are tested in separate databases and processes, producing
different thresholds. These are integration cases, not independent statistical
evidence of an adaptive benefit. The application now uses the core allocator and
checks its checker bindings through independent finite contract tests before reuse.
It has no matched adaptive-versus-static results. Initial setup and full
experiment cost reporting remain work in progress; do not infer cost savings from
the test duration or the number of candidates.

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

Functional integration of this control is separate from a matched experiment.
Matched runs must initialize independent databases, identities, artifacts and
caches per arm; include primitive/checker setup costs; use the same predeclared
task order, bounds and held-out evaluation contract; and retain failure/censoring
and all arm results. Verification and connection/environment bottlenecks, full
cost output and a reproducible comparison command are still required. A positive
effect is not an acceptance criterion.

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

No aggregate intelligence score, ASI probability, general endogenous-growth proof,
statistical independence or production SLO is emitted. Longitudinal resource-matched
multi-organization/model comparisons remain future empirical work.
