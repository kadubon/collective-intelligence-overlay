# Local Gemma experiment for 0.4.1

Status: corrected-treatment five-pair pilot and preregistered 30-pair assessment
complete; original and public-copy offline verification passed. Corrected native
candidate validation and 0.4.1 publication remain pending. These results do not
replace the [audit register](audit-041.md) or historical 0.4.0 measurements.

## What is tested

Three permissioned native service processes use actual PostgreSQL, HTTPS/A2A,
OPA and public Microsoft Agent Framework workflow execution. One producer calls
the public MAF Ollama provider. Gemma chooses bounded JSON parameters for numeric
normalization, status selection and grouped aggregation. Different valid parameters
change executed results; invalid responses receive no hidden answer or fallback.
The receiver forms C1/C2, obtains scoped independent checker evidence, reuses
them on different public inputs and forms C3. Six fresh hidden-input tasks are
offered per arm. An independent integer/Fraction checker scores actual outputs.
The model has no checker source, hidden seeds, file tools or policy/budget grants.
The shared host operator is trusted; this is not hostile OS-level code isolation.

Static and adaptive arms share contracts, builders, checker, initial pool, model,
permissions, aggregate budget and cache policy. Only existing allocation mode
and shortage observation scope change. Static observes only its current goal in
the fixed numeric/status/aggregate plan. Adaptive observes the bounded three-goal
backlog. Both use the same ordinary admission and signed opportunity references.
A pair is the statistical unit; tasks and three peers are not independent
samples. Each arm has separate databases, CAS, keys and execution history. No
MCP tool is used by this particular tabular task; actual MCP integration is tested
separately by the audit/native service gates. General semantic applicability,
intelligence growth and an ASI claim are outside this experiment.

## Preregistered 30-pair assessment

[Registration](experiments/gemma-041/preregistration-v1.json) was committed and
pushed at `35245df2bc902f52524916f10891f16cfb4904c4` before the first request.
Its SHA256 is `b8dff43a48deab2d3a7d0f5d3aec6657b8ab356eb42244fa141e608456a2763d`.
The fixed run `cio-041-gemma-tabular-confirmation-v1` used that clean source
snapshot, 66 frozen installed distributions and the immutable hosted wheel from
candidate run `36965233400`, SHA256
`2455fcab88a1dc732372b9a5c7c0eb7d16d3661b6bbf76e853ab8d03d52a0fb9`.
That CI run subsequently failed and did not approve publication. The measured
package and experiment sources remain unchanged; later CI profile corrections
are separate validation changes, not changes to these prompts or observations.

All 30 independent paired blocks, 60 isolated arms and 360 offered heldout tasks
finished in 3,277.0687 seconds. Balanced arm order used 15 static-first and 15
adaptive-first blocks. No seeds, attempts or tasks were removed or replaced.
[Offline analysis](experiments/gemma-041/confirmation-v1/analysis.json) and the
[episode table](experiments/gemma-041/confirmation-v1/episodes.csv) retain all
30 paired values and signed cost totals by category, unit and observation status.

| Measure | Static | Adaptive |
| --- | ---: | ---: |
| Heldout tasks passed / offered | 180 / 180 | 180 / 180 |
| Actual model requests | 90 | 90 |
| Input / generated tokens | 27,238 / 2,227 | 27,238 / 2,244 |
| Total measured tokens | 29,465 | 29,482 |
| Mean inclusive active wall, seconds | 50.9598 | 52.6887 |
| Mean wall including cleanup, seconds | 53.6488 | 55.4909 |
| Qualified ordinary execution receipts / formations | 870 / 90 | 870 / 90 |
| Missing usage / false accepts / UNKNOWN tasks | 0 / 0 / 0 | 0 / 0 / 0 |
| Invalid drafts / uncertain A2A execution receipts | 0 / 0 | 0 / 0 |

Primary adaptive-minus-static episode-fraction difference is 0. The preregistered
95% paired percentile bootstrap (9,999 resamples, seed 41031) gives [0,0]; the
paired two-sided randomization p-value is 1 (seed 41032). Every fraction is 1,
so this degenerate interval reflects a ceiling in the observed distribution.
It does not establish population equivalence, superiority, or exclusion of a
meaningful difference on harder tasks. The registration explicitly classified
this fixed N=30 assessment as exploratory with limited power: pilot paired SD=0
was unreliable for power planning, MCID=.10, and conservative SD=1 normal planning
required 785 pairs for 80% power at two-sided alpha=.05. N was not increased.

Adaptive generated 17 more tokens and took 1.7289 seconds longer on mean active
wall, and 1.8421 seconds longer including cleanup. These are secondary descriptive
observations on a shared CPU/cache, without a superiority test or adjustment for
multiple comparisons. Maximum observed verification candidates per allocation
was one in both arms; no sustained verification backlog was induced. Ordinary
receipt counts include nested primitive, provider and calibration executions;
they are not 870 independent tasks or newly created capabilities. Each arm made
three checked formations, including use of C1/C2 on new public inputs during C3
formation. This demonstrates the recorded lineage, not self-accelerating growth.

The [descriptive resource groups](experiments/gemma-041/confirmation-v1/resources.json)
separate all three formation goals and retain every input hash. Aggregate/C3
requests used 9,153 input tokens per arm, with 624 static and 612 adaptive generated
tokens. Their API total-duration sums were 107.0055 and 106.1049 seconds; separate
signed candidate-formation wall observations sum to 47.0157 and 44.6939 seconds.
These nested measurements are not additive total C3 lifecycle costs, and this
post-hoc grouping is not an additional primary comparison. Monetary costs remain
unavailable where signed receipts say so. Recompute with
`uv run python scripts/summarize_gemma_resources.py --run YOUR-RAW-DIR --output YOUR-NEW-RESOURCE-FILE`.

## Corrected-treatment pilot observations

`cio-041-gemma-tabular-pilot-v4` used a clean installed local 0.4.1 wheel,
SHA256 `2455fcab88a1dc732372b9a5c7c0eb7d16d3661b6bbf76e853ab8d03d52a0fb9`,
with 66 frozen runtime distributions. Five distinct paired episodes completed
in 540.2825 seconds. Original and shareable-copy raw verification both passed.
The static one-goal observation and fixed order are checked from signed records.
[Offline analysis](experiments/gemma-041/pilot-v4/analysis.json) and
[episode table](experiments/gemma-041/pilot-v4/episodes.csv) retain every paired value.

| Measure | Static | Adaptive |
| --- | ---: | ---: |
| Heldout tasks passed / offered | 30 / 30 | 30 / 30 |
| Actual model requests | 15 | 15 |
| Input / generated tokens | 4,494 / 347 | 4,494 / 362 |
| Total measured tokens | 4,841 | 4,856 |
| Mean inclusive active wall, seconds | 52.4908 | 49.8572 |
| Mean wall including cleanup, seconds | 55.2270 | 52.7315 |
| Qualified ordinary execution receipts / formations | 145 / 15 | 145 / 15 |
| Missing usage / false accepts / UNKNOWN tasks | 0 / 0 / 0 | 0 / 0 / 0 |

Quality difference is zero; paired randomization p=1 and the degenerate paired
bootstrap interval is [0,0]. The ceiling effect prevents an equivalence or
superiority claim. This task distribution did not create a sustained verification
backlog: maximum observed verification candidates per allocation was one in both
arms. Adaptive used 15 more generated tokens. Its shorter observed wall is a
secondary descriptive result on one shared CPU, without physical isolation or
an independent cache reset. Signed per-stage costs remain available by unit and
status; their nested durations are not added to total elapsed time.

## Historical allocation-only pilot observations

This first pilot turned off adaptive allocation but exposed all three goals to
both arms' observation API. It is retained as an allocation-only exploratory
comparison. The corrected-treatment pilot uses a fixed one-goal-at-a-time static
plan; the old results are not
merged into that cohort.

| Measure | Static | Adaptive |
| --- | ---: | ---: |
| Paired episodes | 5 | 5 |
| Heldout tasks passed / offered | 30 / 30 | 30 / 30 |
| Actual model requests | 15 | 15 |
| Input / generated tokens | 4,587 / 369 | 4,587 / 383 |
| Total measured tokens | 4,956 | 4,970 |
| Mean inclusive active wall, seconds | 55.9068 | 53.7488 |
| Missing usage / false accepts / UNKNOWN tasks | 0 / 0 / 0 | 0 / 0 / 0 |

Adaptive minus static episode fraction is 0; paired two-sided randomization
p=1. The 95% percentile paired bootstrap interval is [0,0] because every episode
fraction is 1. This degenerate finite-sample interval does not establish population
equivalence or exclude a meaningful difference on more difficult tasks. MCID is
0.10. Observed paired SD=0 provides no reliable variance-based power calculation;
a conservative SD=1 normal planning approximation would require 785 pairs for
80% power at two-sided alpha=.05. The completed thirty-pair assessment was registered as an
exploratory resource-bounded assessment, not a powered superiority/equivalence test.
The pilot source/inputs remain frozen in its original snapshot; confirmation uses
different input and model seeds, fixed before the first confirmation request.

## Model and cost scope

Exact model: `gemma4:e4b`, digest
`dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c`.
Actual Ollama 0.35.0 uses its CPU llama-server backend on Windows 11 / Ryzen
7 8840HS. Installed weights are Q4_K_M, 7.5B, 6,583,656,505 bytes. The Radeon
780M is present but not used; resident API reports `size_vram=0`. Requested
context=4096, prediction cap=512, think=false, draft_num_predict=0, temperature=.2,
top_p=.95, top_k=64, keep_alive=5m. API resident context=4096 is observed;
some requested engine settings have no independent effective-state field.
The model's installed template/default parameters are retained as metadata.
Maximum four requests and 18,432 aggregate upper-reserved tokens per arm,
25 seconds per request, 600 seconds per arm, with no automatic model retry.

Requests are serialized on one dedicated loopback server with cloud disabled.
Other existing Ollama services and installed models are unchanged. No warmup
is omitted: setup and loading are included in active wall. Shared cache cannot
be reset without affecting the model server, so arm order is balanced and cache
limits remain explicit. Raw API nanoseconds are converted to seconds; overlapping
nested receipt times are not added to wall. Missing/partial response usage is
charged by its upper reservation rather than zero. Energy and CPU/RAM usage
are not comprehensively measured for this Windows run. Peer lifetime CPU snapshots
are retained. A supplemental read-only Windows collector made 185 samples from
04:48:28 through 05:34:48 UTC, starting after inference began. The owned model
runner's process-lifetime peak working set reached 8,509,886,464 bytes; its final
point working set was 8,430,227,456 bytes and private memory 9,135,665,152 bytes.
These process metrics are distinct from the API model-size counter and installed
weight size. They do not establish a whole-run/episode RAM peak or energy budget.
Complete peer/descendant RSS, full model CPU time per arm and energy are unavailable.
API fee is zero; local compute is not free.

## Reproduce and inspect

Use a source checkout, native PostgreSQL test cluster, verified OPA and audited
Caddy `v2.11.4+cio.1`. Install development dependencies with
`uv sync --all-extras --frozen`. A dedicated loopback Ollama server must already
have the exact installed model and a log confirming cloud is disabled; the harness
does not start/pull a model. Set `CIO_TEST_DATABASE_URL` to the test cluster.

```sh
uv run python scripts/run_gemma_tabular.py --classification pilot --pairs 5 --run-id YOUR-NEW-ID --host http://127.0.0.1:11439 --server-log YOUR-SERVER-LOG --opa YOUR-OPA --caddy YOUR-CADDY --output YOUR-NEW-RAW-DIR --home YOUR-NEW-PRIVATE-DIR
uv run python scripts/analyze_gemma_tabular.py verify --run YOUR-RAW-DIR --output YOUR-NEW-VERIFICATION-DIR
uv run python scripts/analyze_gemma_tabular.py analyze --run YOUR-RAW-DIR --output YOUR-NEW-ANALYSIS-DIR
```

`verify` rechecks raw request bytes, exact model/options, same-response usage,
draft/selected-proposal/executable-manifest correspondence, independent hidden
inputs, CAS hashes and original signed receipts. It never invokes a model.
Missing or inconsistent records yield UNKNOWN. Signatures and hashes establish
record integrity under the retained public identity pins, not ground truth.
Analysis uses development-only NumPy/SciPy public paired statistics APIs.

Each run keeps a unique manifest, source snapshot, all calls and inference attempts,
raw model bytes, signed originals and independent evaluation cases. Setup failures
and unsuccessful task smokes are retained separately with their actual source
snapshots; they are not quietly relabeled successful pilot pairs. The first offline
pilot verification failed because concurrent monitoring completion order was
mistaken for dispatch order; a corrected verifier checks unique contiguous IDs
without changing the raw journal. Original failed verification is retained.
Public raw asset locations and redaction/checksum records will be added after
candidate publication; no weights, private keys or private home configuration
belong in those assets.

The first corrected-treatment launch (pilot-v2) failed before inference because
its server-log argument was wrong; the distinct retry pilot-v3 completed all
offered arms but dispatched no model requests. Its clean peer processes could
not import the then source-only observer. Both are retained as invalid
zero-inference attempts, and offline verification reports UNKNOWN for pilot-v3.
The observer is now a packaged public transport module, allowing the installed
producer to record inference without implicit development PYTHONPATH settings.
Pilot-v4 is the separate successful corrected-treatment cohort. The first hosted
representative checkpoint (`36962813882`) retained 488 passing source cases and one
failure: an old exception-message expectation. The targeted actual PostgreSQL/A2A
case passes with the exact new `PROVIDER_REPORTED_UNKNOWN` reason, retaining the
actuator-count denial assertion. It is not reported as a passing checkpoint.

Code is Apache-2.0; Ollama and the optional MAF provider/Python client are MIT.
The installed model's `/api/show` supplies Apache-2.0 text, also shown for the
matching llama.cpp digest on the [official model page](https://ollama.com/library/gemma4:e4b).
Model files and any supplemental notices retain their upstream terms; no weights
are redistributed here. Synthetic fixtures are generated by the project's code.
Raw model outputs and signed third-party records are retained as experiment
observations, not automatically relicensed as this project's implementation.

## Recovery boundaries

[Audit changes](audit-041.md) document saved-ID reconciliation, owner resolution,
backup structure and CAS crash recovery. A whole-invocation resolution preserves
UNKNOWN and the original allowance. It closes a current capacity obligation only
with the owner's applicable signed whole-effect/result/quiescence disposition.
Restoring a backup invalidates closure projections and requires fresh owner review.
Do not infer external-effect certainty from a backup checksum or one child result.
The tabular starter is a finite experiment application; this experiment does not
test reconstruction of its newly formed application pins after process restart.
