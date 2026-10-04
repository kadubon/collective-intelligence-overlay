# 0.5.0 implementation and verification register

This is a feature release of the existing evidence-preserving capability lifecycle
layer. It introduces no model experiment, inference, benchmark or long soak.
The baseline is `733edaa78c93156d005528c50a3fd280538b964d`; work is on
`feature/050-lifecycle`. Original tags, distributions, research sources and raw
remain immutable. This register is a work record, not evidence of completed gates.

## Responsibility mapping

| New read model | Existing authority reused | Boundary |
| --- | --- | --- |
| CapabilityLifecycleView | Capability/Evidence/Event/Revocation/Decision, Store.record_page/reference | A projection, never a new global status or signed Record |
| ContributionObservation | ExecutionReceipt, FormationReceipt, formation_inputs, classification | Recorded copy/import/use/input/candidate; no causal credit or novelty |
| Residual | Existing obligations/reasons/UNKNOWN and exact record references | Does not resolve effects, authorize, refund or retry |
| GrowthObservation | Explicit capability_metrics/Overlay.qualify and independently retained stock observations | Fixed receiver/scope/policy/identity universe; stock, service and costs separate |
| HandoffObservation | Original records/receipts, Opportunity/Proposal references | Read/export only; no transport, execution, scheduler or budget mutation |

Store remains the PostgreSQL record authority; DSSE digests cover original payload
bytes. Decisions remain unsigned owner projections. Existing Registry/Executor,
use-time qualification, OPA, keys, reservations, resolution and recovery retain
their responsibilities. No DB migration or new runtime dependency is planned.

## Baseline evidence

At the initial authenticated checks, 0.4.4 was present on PyPI and its GitHub Release
was published with eight assets. 0.5.0/tag v0.5.0 were absent. Existing recent CI
was terminal/success. Worktree was clean. All three raw revisions from the previously
byte-verified downloaded 0.4.4 archive were passed through their frozen existing
offline reader once each, with network blocked and no inference. Their complete
analysis objects equal the published verification objects: 36/0/4 historical
generation calls and 44 offered rows in total. The first host wrapper expected
`verification.json` rather than the reader's actual `analysis.json`; only the
wrapper lookup was corrected, without repeating that reader invocation.

The historical result remains `assay_not_ready`: SQL 8/8,8/8; composition 6/8,7/8;
public-rule controls 96/96 at every visited setting; G2/confirmation absent.
G3 copied two successful Gemma candidates into four histories and completed eight
mechanism diagnostics. It establishes no CIO advantage or four new abilities.
Historical generation was 40 and measured/charged tokens 28178, missing usage zero.
New generation for this feature release is zero.

The [research index](https://kadubon.github.io/github.io/collective-intelligence-index.html)
was inspected for definitions, copy/source/service distinctions and conceptual
Generate/Verify/Reuse/Account/Reallocate handoffs. Its conceptual workflow does not
grant execution authority or establish interoperability; no upstream research
runtime is added. Historical results, protocols and signed raw are unchanged.

## Required regression evidence (local scope)

The 28 focused unit/property cases are in [test_lifecycle.py](../tests/unit/test_lifecycle.py).
Six actual PostgreSQL/OPA bridge cases are in
[test_lifecycle_store.py](../tests/integration/test_lifecycle_store.py).
The representative pre-freeze source run passed 512 / failed 0 / skipped 0,
including existing inspection, lineage, invocations/resolution and binding APIs.
The final feature/release focused run passed 82 / failed 0 / skipped 0; one
subsequent same-clock ambiguity case also passed. These scopes are not a complete
native matrix. Initial collection/fixture failures and the freshness guard rejection
remain in private logs; corrected targeted checks passed without weakening the guards.

| Requirement | Local evidence; final native gate still pending |
| --- | --- |
| 1 Candidate without evidence/decision/use | Missing observations remain missing |
| 2 Different receiver judgments | Both exact scoped Decisions retained |
| 3 PASS, later FAIL/withdrawal/expiry | Concurrent history, residual/current unknown |
| 4 Replay/page/copy deduplication | Exact source and cost-position identities |
| 5 Two genuine uses | Distinct original invocation IDs counted |
| 6 One source copied four times | Copy observations, no functional novelty count |
| 7 Remote completion | No inferred installation, quality or new ability |
| 8 Input/dependency/support | Distinct typed relation/source references |
| 9 Costs | Owner/unit/status, wall/reservation/unknown separation |
| 10 Residual preservation | Inspection/export/handoff retain residuals and coverage |
| 11 Read-only | No DB write, HTTP/model/tool/policy/budget call |
| 12 Explicit qualification | Delegation to existing capability_metrics/qualify |
| 13 Clock/late/key/revision/partial | Cutoff, original payload, explicit inconsistency |
| 14 Incomparable stock | Null deltas, residuals for policy/universe/coverage changes |
| 15 Complete stock | Independently acquired endpoint set identity |
| 16 Churn/readmission | Separate from endpoint changes and new candidates |
| 17 Denial/tampering/cycle/limits/version | Fail closed before disclosure/unsafe work |
| 18 Handoff reception | No verification/execution/allocation promotion |
| 19 Wire/hash compatibility | Original DSSE fixtures and projection digest distinction |
| 20 Clean-wheel CLI/docs | Final preliminary wheel: offline four-mode CLI, blocked optional imports, 27 core cases, actual PostgreSQL/OPA tutorial; generated schema/help/bilingual blocks checked |

The initial preliminary wheel/sdist passed clean normal-resolution core, agents,
model-mock and Ollama-mock profiles, sdist rebuild, advisory/license/SBOM checks.
Installed tests were 427 agents + 1 model-mock + 11 Ollama-mock; rebuilt sdist ran
428 cases, with failures/skips zero. The final preliminary wheel includes the
Residual coordinate identity fix and CLI option checks. Its fresh core check passed
27 cases with one pytest config warning (`asyncio_mode` without the optional test
plugin), and its installed actual-service tutorial passed A ACCEPT/B REJECT,
actual two-row sum `5.00`, formation receipt, unavailable joules and post-withdrawal
REJECT. This tutorial is not a network benchmark or growth experiment; model calls
remain zero. Databases, original records and the failed initial tutorial are retained.

Local preliminary hashes (these are not the future GitHub release candidate pair):

| Distribution | SHA-256 |
|---|---|
| Final preliminary wheel | `3da84863c685baff525e7f3c340b7ea36b19ea238af42bb255d5207eee2bc778` |
| Final preliminary sdist | `3c9961072631c87fb653faf835e59bfe248c894d4c2466019dbf61fd9a2b2188` |

Existing deterministic fixture comparison code remains ordinary API regression,
not a new research panel or measured benefit. No production comparison dispatch,
long soak, actual model connection, additional pilot or parameter search is run.

Unit/property and actual PostgreSQL/OPA regressions precede release packaging.
After candidate freeze, the existing native compatibility matrix must pass for
the actual candidate; real model connections and production experiments/soak
remain unrun. Tag publication must reuse that exact pair through workflow.yml,
environment pypi/OIDC. Actual PyPI hashes, ordinary clean install and smoke are
separate final evidence. No completion claim is made before those checks pass.
