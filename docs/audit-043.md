# v0.4.3 audit

Work proceeds on `study/043-near-transfer-cost` from
`a7aab577d1b833324695e5e64b92f7f9a66c0045`. The published v0.4.2 tag and the
original successful native run 37126141569 remain unchanged. No old run was
cancelled/rerun and no old model request was regenerated.

The old offline verifier and analyzer were run once and matched the published
records. Their subsequent inspection helper failed because provenance was read
from observation.json rather than intent.json; a corrected inspection used the
original bytes without rerunning either analysis or inference. All six E
Full/Empty pairs had equal request bytes, seeds, prompts, options and empty visible
stock. The calibration solutions differed despite equal requests. That observation
does not establish a defect or causal stock effect. The retained
[review](studies/near-transfer-043/old-042-review-v1.json) separates measured and
charged tokens, including M's missing-usage reservation.

Pre-inference local checks: 117 affected unit tests passed; lint and strict package
typing passed. One pytest invocation used an unexpanded PowerShell glob and ran no
tests; the explicit-file invocation is the actual result. A service preflight
stopped at installed-wheel origin validation with zero generation requests. The
old confirmation environment was preserved. A new frozen noneditable environment
passed all 86 package-file checks and actual M/C reference controls, 6/6 with zero
generation requests, over owned PostgreSQL, OPA, TLS/A2A and the registered builder.
The failed preflight and original bytes remain locally retained.

The [new methods](near-transfer-043.md) governed 54 real requests. The
[English](studies/near-transfer-043/pilot-v1/report.en.md) and
[Japanese](studies/near-transfer-043/pilot-v1/report.ja.md) reports retain all results.
Locked S1/K1/F0 were 0/6, 1/6, 0/6: `assay_not_ready`, confirmation not performed.
Usage was 26256 measured/charged tokens, zero missing; driver wall 1009.437 seconds
plus a separate conservative startup reservation. Reader failures and repairs are
separate; no inference was repeated. Final native validation/publication are pending.

Targeted real-service regressions passed 20 cases with one skipped because Windows
had no pg_dump/pg_restore prefix. That exact missing case subsequently passed using
the WSL PostgreSQL tools: 21 distinct cases covered, without relabelling the skip.
Final affected unit tests passed 59 cases; lint/format, mypy, documentation and
scientific derivative checks passed. The public raw copy's verification equals the
private original's final offline result, with 953 mapped files and two explicitly
redacted unsigned metadata files. Signed records, model responses and CAS bytes
were not changed. Owned model, observer and PostgreSQL processes physically stopped.
