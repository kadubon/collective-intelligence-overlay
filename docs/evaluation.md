# Evaluation and metrics

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

`scripts/evaluate_reference.py` additionally uses the public API for a deterministic mechanism
microbenchmark. Four arms use the same installed transformation, checker and three
held-out inputs: single-agent local cache, separate roles without persistent sharing,
shared memory, and overlay admission. Baselines retain competent caching and the
same output checks. All execute serially. The role-based baseline is not a separate
distributed-agent performance experiment; topology, network and real model costs
are not matched by this microbenchmark.

Elapsed times include execution, checking, failed attempts and overlay process/DB
overhead. Setup reports database/identity provisioning, formation, checking and local
transfer separately; maintenance read timing is also explicit. Unknown currency,
long-term maintenance and unmeasured network costs remain unavailable. No cost saving
is inferred from an unmeasured counterfactual. The benchmark may show only overhead.

Metrics group immutable events and typed cost records. They retain formation,
verification, transfer, use, failure, maintenance and other categories when supplied.
Unobserved categories are not zero-valued observations. Receiver decisions and
recommendations identify verification, connection, observation or repair work for
subsequent attempts; recommendations cannot create permissions or budget.

No aggregate intelligence score, ASI probability, general endogenous-growth proof,
statistical independence or production SLO is emitted. Longitudinal resource-matched
multi-organization/model comparisons remain future empirical work.
