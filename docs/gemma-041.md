# Local Gemma experiment for 0.4.1

Status: initial five-pair allocation pilot complete; corrected-treatment pilot,
preregistration, confirmation, fixed native
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

## Initial allocation-only pilot observations

This first pilot turned off adaptive allocation but exposed all three goals to
both arms' observation API. It is retained as an allocation-only exploratory
comparison. A corrected-treatment pilot will use a fixed one-goal-at-a-time static
plan before the primary comparison is preregistered; the old results will not be
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
80% power at two-sided alpha=.05. Thirty confirmation pairs are planned as an
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
are unavailable for this Windows run. API fee is zero; local compute is not free.

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
