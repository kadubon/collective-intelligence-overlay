# 0.5.0 implementation and verification register

This is a feature release of the existing evidence-preserving capability lifecycle
layer. It introduces no model experiment, inference, benchmark or long soak.
The baseline is `733edaa78c93156d005528c50a3fd280538b964d`; implementation and fixes
are merged into `main` at `e830a6a`. Original tags, distributions, research sources
and raw remain immutable. Completed gates below have separate exact-byte evidence;
publication is not implied by a passing native gate. Actual completed publication,
normal-index installs and downloaded Release asset checks are separately recorded
in [release results](release-050-results.json) and [the Japanese report](release-050-report.ja.md).

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

The corrected `e830a6a` source comparison against that baseline preserves 85 previous
package files byte-for-byte; only the thin CLI dispatcher entry differs. Existing wire schemas,
migrations and runtime implementations are byte-identical. Parsed project/build
metadata differs only in the root version and description, and the parsed lock
differs only in the root version; no dependency was added or updated. This static
comparison complements the retained 53-case target result and does not replace
native, installation or publication evidence.

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

The 43 focused unit/property cases are in [test_lifecycle.py](../tests/unit/test_lifecycle.py).
Ten actual PostgreSQL/OPA bridge cases are in
[test_lifecycle_store.py](../tests/integration/test_lifecycle_store.py).
The representative pre-freeze source run passed 512 / failed 0 / skipped 0,
including existing inspection, lineage, invocations/resolution and binding APIs.
The final feature/release focused run passed 82 / failed 0 / skipped 0; one
subsequent same-clock ambiguity case also passed. These scopes are not a complete
native matrix. Initial collection/fixture failures and the freshness guard rejection
remain in private logs; corrected targeted checks passed without weakening the guards.

After the first full candidate was frozen (run 37182803375, source `4a653a4`), an
additional regression reproduced a missing-original-clock defect: the legacy
decoder's current-time default was displayed as an observed source clock. That
candidate is superseded and cannot be published or attest corrected bytes. The
correction preserves the wire decoder and original payload; source, evidence and
cost clocks are null when absent, and top-level decoder defaults are explicitly
marked. Missing relevant period clocks also prevent exact period counts/churn.
Four actual Store cases cover signed omitted clocks and unchanged exact exports.
The corrected focused suite passed 47 / failed 0 / skipped 0, including the ten
actual PostgreSQL/OPA cases; lint, format, typing and generated Docs checks passed.
The initial reproduction and subsequent fixture failures remain retained. The
corrected candidate requires its own frozen pair and native gate.

A subsequent completion audit reproduced duration alias aggregation: two unspecified
inclusive `milliseconds` observations were added, although `seconds` was already
excluded. Run 37184567824/source `3afc43b` is also superseded for publication. The
correction conservatively lists recognized duration labels without summation or
conversion; six unit variants preserve their original quantities/units. Other custom
unit semantics remain unresolved recorded-quantity observations. The missing-clock
fixture now supplies a future expiry independently of its fixed synthetic cutoff,
so unchanged legacy validation does not make the test date dependent. The initial
failing diagnostic and corrected values are separate retained snapshots; a private
provenance note records the corrected-output split. These are ordinary unit checks,
not research results. Corrected candidate/native validation is separate.
The corrected focused unit/property and actual-service suite passed 53 / failed 0 /
skipped 0; lint, format, typing and generated Docs checks passed.

The superseded first native run's Mac Intel/Python 3.14.7 source suite returned
867 tests / 1 failure / 0 skips: the existing receiptless recovery positive case
returned UNKNOWN after review. Its XML and original job-log bytes are retained;
the incomplete original does not become a release gate. The cause is not established
from that log. A result-only assertion diagnostic was added without changing runtime,
deadlines, authority, UNKNOWN or held allowance. The corresponding local Windows
3.12.14 case first skipped for absent pg_dump/pg_restore, then passed with the real
PostgreSQL 16.15 WSL tools (1 pass / 0 failures / 0 skips). This is narrow local
evidence. The corrected final Mac Intel/Python 3.14.7 run passed all four receiptless
cases, including that positive case, without runtime or authority changes. This
does not establish the cause of the old failure.

With explicit owner approval, unfinished jobs in superseded runs
[37182803375](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/37182803375)
and [37184567824](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/37184567824)
were cancelled to release runners. Both runs are now terminal/cancelled; already
completed successes and the first run's failure remain unchanged. Their original
GitHub log ZIPs, candidate distributions and available report files are retained
locally with separate SHA-256 manifests (3,716 and 2,724 retained files respectively).
No 0.4.x run was changed. Corrected source `e830a6a` has its own fixed pair and
[run 37186786810](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/37186786810);
its native gate is complete/success. The exact pair was subsequently published by
tag/OIDC run 37194242517 and verified against actual PyPI downloads. Cancellation
is not a passing gate.

| Requirement | Behavioral evidence; also included in the final native gate |
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
| 20 Clean-wheel CLI/docs | All twelve final native installed packages; actual-index fresh core 43 cases/97 identical package files, four JSON modes, blocked optional imports and actual PostgreSQL/OPA tutorial; generated schema/help/bilingual blocks checked |

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
The final frozen candidate passed all twelve OS/CPU/Python profiles: Linux amd64,
Windows amd64, macOS Intel and Apple Silicon, each on CPython 3.12.14, 3.13.15 and
3.14.7. Every profile passed 886 source tests, 874 installed agents tests, one
model SDK mock, eleven Ollama SDK mocks and 445 rebuilt-sdist tests, with zero
failures/errors/skips. Core import, CLI, resources and optional-import guards also
passed. Every installed actual-service tutorial retained A ACCEPT/B REJECT,
two rows/`5.00`, formation links, unavailable joules and post-withdrawal REJECT,
with zero model requests. Source and installed short fault protocols both passed
the unchanged nineteen required injection groups (24 observed labels), three
owners and 120–600-second bounds; these are not formal production soak approval.
Mixed Python and all four cross-platform signed artifact readers passed.

[Native results](release-050-native-results.json) record those observed scopes;
[the release manifest](release-050.json) binds run 37186786810, its source/tree,
the exact wheel/sdist and original gate SHA-256. All original report files and
the GitHub log ZIP are retained locally (3,803 files). Authenticated trusted-run,
candidate-source and full report-hash reuse checks passed. A private report
collector's incorrect 19-label assumption was corrected to delegate the existing
protocol validator; the original collector and diagnostic remain retained, and
no test, protocol or gate was weakened.

Real model connections and production experiments/soak remain unrun. Tag publication
reused that exact pair and full gate through workflow.yml / pypi / OIDC; candidate,
ready and publish all passed. Actual PyPI metadata and downloaded bytes match the
candidate. Fresh Windows normal-index checks on all three declared CPython patches
passed core/agents/model-mock/Ollama-mock profiles, 444 agents unit cases, 1/11 SDK
mocks and 445 rebuilt-sdist cases per patch, with failures/errors/skips zero. All
twelve runtime advisory/license/SBOM profiles include the published root and have
zero findings/skips. The separate fresh core check passed 43 cases with the one
documented optional-test-plugin config warning, matched 97 package files, blocked
optional SDK imports and completed the actual-service tutorial. The marked local
PostgreSQL cluster alone was stopped with all private data/keys/logs retained.

The six GitHub Release assets were downloaded and matched byte-for-byte. The single
software-only ZIP's 3,864 members matched its manifest. No historical scientific raw
or model weights were repacked. Public metadata redactions have separate original/
public hashes; signed envelopes and original native reports remain unchanged.
Postpublication README/Docs changes belong to main and do not move the tag,
rebuild the pair, recompress the archive or extend the old native source scope.
