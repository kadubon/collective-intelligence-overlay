# Research mapping and non-guarantees

Starting point: [author's research index](https://kadubon.github.io/github.io/collective-intelligence-index.html).
Reviewed on 2026-09-28: index, linked primary TeX abstracts and selected operational
sections from [pinned primary archives](https://github.com/kadubon/paper-tex-backup/tree/7bd9fe246ae0f5a4bf6564b588c0426b5b7f29bd).
This was a scope/design inspection, not a complete reading or independent proof audit.
No CheckedFlow/CCR/CPCF/PIC/VEK/ALT implementation is forked or required.

| Research principle / primary source | Operational interpretation | Implementation | Tests | Conditions and omissions |
| --- | --- | --- | --- | --- |
| [ALT](https://doi.org/10.5281/zenodo.20476200): receiver-qualified reuse | Bind use to receiver, contracts, environment, permissions, freshness and costs | models.py, overlay.py, policy.rego | test_admission.py, test_negative_paths.py | Exact matching; no general distribution-shift detector or surplus certificate |
| [VET](https://doi.org/10.5281/zenodo.21147093): preserve residuals and revisable checks | Retain UNKNOWN, obligations, method/issuer, dissent and withdrawals | Evidence, Revocation, append-only Store | counterexample, scope and evidence-withdrawal tests | Checker trust remains local; no infallible truth oracle |
| [CAIT](https://doi.org/10.5281/zenodo.20061296): scoped composition and lifecycle | Require separately checked composite plus non-revoked dependencies; reject circular support | bounded dependency/evidence traversal | graph/cycle tests, three-peer E2E | No certificate algebra or endogenous-growth theorem implemented |
| [Growth](https://doi.org/10.5281/zenodo.22604358): matched comparisons and full resource charges | Separate formation, reuse and overhead; retain unavailable costs and failed attempts | accounting.py, evaluation.py | cost property tests, matched microbenchmark | Mechanism benchmark only; not a matched distributed/model growth experiment |
| [Bottleneck Inversion](https://doi.org/10.5281/zenodo.20545356): witness-bounded investment | Emit simple verification/connection/observation/repair suggestions from actual unmet conditions | Overlay.recommend | admission/negative-path tests | No optimal planner, capacity theorem or automatic resource authority |
| Index memory-lifecycle route | Known tombstones block dependent future use; refresh after restart | revocation records, source freshness, use-time checks | withdrawal and stale-worker tests | No physical erasure/unlearning; remote change knowledge is delayed |
| Formation feedback and scoped composition | Require completed ordinary-use receipts when publishing a later candidate; retain declared scope, policy and exact bindings | FormationSession, execution receipts, external document application | test_lineage.py, test_document_application.py | C3 output parameterizes C4; this establishes an observed construction process, not novelty or a causal performance improvement |
| Local formation opportunity / witness bottleneck | Deduplicate actual qualification deficits, retain peer alternatives and adjust finite local work allocation using qualified checker readiness, backlog and protected allowance | opportunities.py, proposal_exchange.py, allocation.py, steps.py | test_opportunities.py, test_proposal_exchange.py, test_adaptive_documents.py | Operational diagnostics, no universal optimizer, network-wide capacity or independent-model proof |
| Growth: matched resource conditions | Isolated fixed/adaptive owner stores, same builders/checkers and task sequence, initial costs and censored failures retained | examples/evaluate_documents.py, accounting.py | test_document_experiment.py, test_inspection.py | Single-run pilots show no checked-outcome/allowance benefit; missing CPU/tokens/currency, no significance or general growth theorem |
| Formation versus runtime support | Distinguish materialized formation inputs from live call dependencies; withdrawal/counterexamples demand requalification | Capability v3, FormationSession, Overlay/OPA | test_lineage.py, test_records.py | Observation links are not causal proof; older conservative v2 rules are retained |

Research feedback may influence later work, but no generated record proves itself
through a dependency cycle. Imported/replicated artifacts do not become new functional
capacity by changing their digest. Origin declarations do not establish independence.
These are implemented operational boundaries; the cited theories' stronger guarantees
are not transferred to this software.
