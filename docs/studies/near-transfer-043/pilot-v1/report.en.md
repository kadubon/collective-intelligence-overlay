# v0.4.3 pilot: assay not ready

The locked entrance gate failed. Confirmation was not performed. H_ACC, H_CIO,
H_FORM, Full/Empty effects, C/M additional value and amortization remain unestimated.
This is a sensitivity diagnostic, not evidence of no benefit or equivalence.

Registration: 2026-10-03 16:52:56 UTC, pushed commit
`4f1403dfe1b5da022a8378ceb032c25faa950cd5` on `study/043-near-transfer-cost`.
The frozen 106-file source snapshot differs from the corrected offline reader and
the final 0.4.3 native release gate. The actual noneditable runtime was the published
0.4.2 wheel, SHA256 `5d1ce6292a6519db8fc157cf9e34d277465c3380f76ed2a92a3b768bd9fac804`.
Final 0.4.3 retains its package implementation bytes and updates distribution metadata.

Gemma4:e4b was the actual installed 7.5B Q4_K_M model, digest
`dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c`,
under Ollama 0.35.0. Requests fixed CPU, context 4096, output 1024, temperature .2,
top_p .95, top_k 64, no draft prediction, think=false, serial inference and blank
per-request conversations. Resident VRAM after the cohort was zero. There was no
pull, cloud/paid API call or cached-answer substitution.

Eight screen worlds provided four examples for each of S1/S2, K1/K2, F0/F1; all
levels were 0/4. The ascending tie rule selected S1/K1/F0. Six unused locked worlds
tested that choice without subsequent difficulty changes.

| Locked family | Level | PASS/offered | Target | Descriptive exact 95% interval |
| --- | --- | ---: | --- | --- |
| SQL | S1 | 0/6 | 30–70% | 0–45.93% |
| Calibration | K1 | 1/6 | 30–70% | 0.42–64.12% |
| Formation | F0 | 0/6 | 20–80% | 0–45.93% |

Finite proportions do not precisely estimate underlying success probability.
Intervals are descriptive; common pilot conditions may induce dependence.
Independent references passed 42/42. All 54 sent requests completed normally with
measured usage. Transport completion is separate from valid/correct solutions.
Failures were 20 semantic mismatches, 19 program ValueError rejections, two
OperationalError rejections and 12 invisible-skill references. All 54 offerings,
including failures, appear in [paired.csv](paired.csv).

One further natural-stock world used M/C with four training episodes each. Both
formed empty stock. Qualification and probes after physical provider stop were
retained; each family/arm failed, retrieved zero executables and made one scratch
request. These are path checks, not confirmation worlds or C/M efficacy estimates.

Total: 54 requests, 26,256 measured/charged input/output tokens, missing usage zero,
driver wall 1009.437 seconds. A separate 300-second preceding-service reservation
made conservative wall charge 1309.422 seconds. Adjacent timer reports differ
slightly; this is not a sum of nested wall. Model/observer cleanup took .593 seconds
and both physically stopped. The 256/400000/14400 bounds were not increased.

| Locked family | Restricted mean seconds | Restricted mean charged tokens | Actual probe wall sum | Actual token sum |
| --- | ---: | ---: | ---: | ---: |
| SQL | 600.000 | 10240.000 | 69.874 | 2875 |
| Calibration | 501.456 | 8601.333 | 54.468 | 2497 |
| Formation | 600.000 | 10240.000 | 91.485 | 3478 |

Failed offers receive common analysis horizons 600 seconds / 10240 tokens, separate
from actual consumption. Half-horizon quality uses recorded prefixes without new
inference. Success-only comparisons are not primary. Formation, checks, storage,
transfer, setup and retrieval remain in original records and inclusive cohort wall;
parent/child wall is not added. Future maintenance, energy and full compute/money
ROI are unknown. There is no justified finite break-even estimate.

The original offline reader stopped on the records API's three-value return;
the first repair stopped on invalid SQL escaping its classifier. The corrected
reader uses the installed factory, matching online rejection. Later checks preserved
original bytes, endpoints, denominators and calls. Repairs and reader hashes have
[separate provenance](reader-repair-provenance.json). Identity/signature checks do
not prove truth against a malicious operator. The [results](results.json),
[verification](verification.json) and [methods](../../../near-transfer-043.md)
give exact observations and scope.

The old 0.4.2 verifier/analyzer each ran once and matched published results. All
six E Full/Empty request pairs had equal bytes/seeds/options and empty visible
stock. Different calibration outputs alone establish no defect. Old raw, protocols,
failures, tags and distributions remain unchanged.
