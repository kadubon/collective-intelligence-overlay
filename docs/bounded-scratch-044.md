# Bounded semantic procedure assay (0.4.4)

This source-only study measures selection, construction and transfer of finite
SQL/MAF procedures. It does not measure unrestricted SQL programming, arbitrary
program synthesis or general intelligence. The product core keeps its existing
extension and local-admission contracts. No runtime dependency was added.

[日本語](bounded-scratch-044.ja.md) ·
[Actual results](studies/bounded-scratch-044/results-v1/report.en.md) ·
[Audit](audit-044.md)

## Preserved baseline and Stage 0

The checked baseline is main `1892fa59646b2c76cda05b4d9f9b854544d51f2e`.
The previously referenced `a2b4a87ce2d119a565f1bc929030802198f20ede` is the
original successful 0.4.3 native candidate source. Version 0.4.3 is published.
Its archive, protocols, scores, tag and package bytes remain unchanged.

[The failure ledger](studies/bounded-scratch-044/stage0-v1/failure-ledger.json)
reuses the exact previously verified downloaded archive, checks each touched
file against its manifest and each parsed observation against signed CAS, then
replays only bounded installed primitives. It adds zero model observations.
The full old verifier is not repeated. The proof scope and checksum are in
[the summary](studies/bounded-scratch-044/stage0-v1/summary.json).
Of 54 old offers, 53 failed: 12 invisible-reference/schema failures,
19 declared input/output contract failures, 2 SQL execution failures and
20 semantic/numeric mismatches. The original scores are retained. Replay
messages accompany actual plans and outputs; they alone are not causal proof.
No task ambiguity or checker defect was confirmed by this inspection.

## Model, host and checker boundary

| Family | Model selects | Host fixes from public contract | Independent checker knows |
| --- | --- | --- | --- |
| SQL L0/L1/L2 | negative policy; then null policy; then stop boundary | table/column names, quoted `group` alias, `value`, parameter binding, sum, remaining declared policies | private task law, heldout rows and expected aggregates |
| Formation L0/L1/L2 | affine/sum order; then net/gross input mapping; then unit/double scale | installed extraction/affine/sum primitives, public offset/slope, zero quadratic coefficient, MAF builder | private composition law, independent expected output |

All 2/4/8 candidates execute syntactically. Every form has distinguishing
witnesses. SQL includes negative, null-only, duplicate and start/stop/outside
rows. Formation has nonzero intercepts, multiple rows per group and separated
input fields/scales. Heldout forms use fresh group names and a disjoint numeric
range. The oracle computes Python/Decimal expectations independently of SQL/MAF.

Model output contains only required enums, with extra fields forbidden. There
is no model-generated SQL, coefficient, skill ID or explanation. Full and Empty
receive the same schema and primitive implementations. Direct executable reuse
is performed by the existing session and verified using receipts. Displayed
partial plans can be cognitive context; naming one is not execution lineage.
Candidate order depends on independently generated public examples and never
on the correct slots. Opaque operational task/world IDs are omitted from scratch
prompts. [Ollama's native structured outputs](https://docs.ollama.com/capabilities/structured-outputs)
are passed through the installed public MAF/Ollama SDK, with original request
bytes retained to verify `format` and all options.

## Prospective stages and finite stops

The separate protocol `cio-044-bounded-scratch-v1` freezes scientific sources,
schemas, task laws, seeds, controls, options and all caps before generation.
It uses the previously published noneditable 0.4.2 runtime; its exact wheel
and implementation-file checksums are separate from the new research sources
and the eventual 0.4.4 release gate.

G0 uses nonmodel all-candidate/strict-wire/adverse-reader/phase tests, followed by
four charged short native smoke requests (L1/L2, both families). The actual
PostgreSQL/OPA/A2A/MAF builder/checker route exercises every smoke candidate.
All six schema shapes are tested through real public SDK HTTP serialization
with explicitly synthetic responses. A schema not visited by native generation
is not reported as an actual model observation. Any boundary failure stops
before bulk generation.

G1 starts at L1, eight scratch offers per family/setting. 0–1/8 narrows one slot,
6–8/8 expands one slot, and 2–5/8 selects the current setting. No setting is
revisited, and a floor/ceiling at the endpoint does not select an unobserved
level. At most three settings/family and 48 requests are permitted. Selection
uses scratch quality/interface observations; no Full–Empty or C–M contrast is
used. Boundary failures stop the stage and require a new prospective revision.

G2 fixes the selected setting and offers twelve unused worlds/family, in two
counterbalanced blocks of six. Entry requires 3–8/12, successes and failures in
each block, and all twelve normal/schema/executable outcomes. Independent
96-world nonlearning random, best-constant and public-text automation controls
are separate diagnostics. L0 alone cannot authorize primary comparison. The
observed locked rate must exceed random and best-constant control rates;
descriptive binomial intervals/p-values do not establish true probability
20–70% or a significant intelligence effect.

G3 reconstructs actual passed G1/G2 native outputs, then uses the same diagnostic
candidate separately in M/C owner histories. A fresh receiver imports,
independently qualifies and executes the artifact after the original providers
physically stop. Full must use a real copied-executable receipt with zero new
inference; Empty must retrieve zero skills and dispatch one scratch draft.
At most eight new generations are allowed. Diagnostic stock is never initial
confirmation stock and these path checks are not benefit comparisons.

Only G0–G3 success authorizes a separately committed/pushed confirmation
protocol: six unused paired worlds, M/C × Full/Empty, four learning episodes and
one draft per near/formation probe (at most 96 calls). Each arm must form its own
stock. Empty training trajectories remain in every primary denominator.
An observed negative or unavailable assay remains a valid release outcome.

## Resource and evidence boundaries

One all-stage cap enforces at most 256 calls, 400,000 charged tokens including
uncertain reservations, 14,400 seconds including setup/normal cleanup, and
concurrency one. Extra physical-stop grace is at most 300 seconds. Only study
processes are controlled. There is no pull, cloud or paid API substitution.
The pilot allocation is four smoke + at most 48 screen + 24 locked + eight G3
requests. Native options use 4096 context, 256 output, temperature .2, top-p .95,
top-k 64, zero draft tokens, CPU and `think=false`; no uncharged warmup exists.

Per-offer endpoints use T=300 seconds and B=4352 tokens, with one draft.
Unsuccessful restricted endpoints receive T/B separately from actual consumed
time/tokens. Missing native usage retains its complete reservation. Explicit
phase/offer context records setup, training, import, qualification, probe,
formation and cleanup. RPC latency is nested inside inclusive wall, never added
to it. Energy, complete compute and future maintenance remain unavailable.
Finite amortization is not reported without equal quality and positive measured
same-unit savings. Old RPC phases are not retrospectively repaired.

Original response/request/usage, signed CAS, plans, checks, snapshots, source
and runtime contracts are retained. `analyze_bounded_scratch.py` prohibits
network/inference and recomputes all offered outcomes. Conditional unoffered
stages and unfinished offered intents are retained separately. Statuses are
`READY_FOR_COMPARISON`, `assay_not_ready`, `chance_dominated_or_unresolved`,
`intervention_unavailable` and (for small comparisons) `limited_power`.
These operational distinctions follow the
[research boundaries](https://kadubon.github.io/github.io/collective-intelligence-index.html);
they do not transfer formal theoretical guarantees to this finite assay.

## Commands

Use the repository's locked environment and configured private services;
scientific scripts are intentionally excluded from the product wheel.

```powershell
uv run --frozen pytest tests/unit/test_bounded_scratch.py -q
uv run --frozen python scripts/run_bounded_scratch.py prepare --protocol docs/studies/bounded-scratch-044/pilot-v1/protocol.json
# Commit and push the exact protocol/source before using its commit below.
python scripts/run_bounded_scratch.py pilot --protocol docs/studies/bounded-scratch-044/pilot-v1/protocol.json --prereg-commit <pushed-sha> --output <new-run-directory> --home <new-private-home>
python scripts/analyze_bounded_scratch.py --run <original-run-directory> --output <new-offline-analysis-directory>
# A separate preregistered G3 repair preserves calibration and all prior resources:
python scripts/run_bounded_stock.py prepare --protocol <new-G3-protocol> --source-run <original-pilot> --previous-run <prior-G3-run>
# Commit/push the new source/protocol before the G3 run operation.
```

The driver needs `CIO_TEST_DATABASE_URL`, `CIO_OPA` and `CIO_CADDY`. Model/runtime
identity is inspected locally; an existing unrelated server is not reconfigured.
The protocol's wheel guard requires the ordinary installed runtime in a fresh
environment. Package-only import, CLI and general overlay use remain described
in [quickstart](quickstart.md).

Actual G1 visits ended at ceiling, with no selected setting and no G2 or
confirmation. Original G3 pre-offer home/ID conflicts and the separately pushed
G3-v2/v3 repairs are retained. The final reader and generated reports are separately
hash-bound; frozen original gate fields retain their original meaning. No old
inference was regenerated and diagnostic M/C stock was not used as comparison
stock. Native validation/publication have their own version-specific gate.
