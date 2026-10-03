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

Release preparation also verified the new candidate's 86 runtime package files
against the study's published wheel. The first inspection included uv's .gitignore
in a two-distribution comparison and stopped; filtering distributions corrected it
without a rebuild. The archive-only offline launcher stopped on a missing unchanged
source shim and then Windows asyncio's internal socketpair under a blanket network
block. Both stops and launcher versions are preserved. Adding the prereg-commit
shim separately and initializing the internal event loop before blocking subsequent
connections reproduced the original verification and analysis with no inference.

The [cost observations](studies/near-transfer-043/cost-observations-v1.json) separate
offer walls and tokens from overlapping client RPC latency. The inherited call
phase label remained `setup` for every call, so it cannot identify separate setup,
formation or maintenance wall categories. Fixed investment attribution is incomplete;
no marginal saving, F/s, full compute or monetary ROI is estimated.

Initial full native run 37141746108 failed Linux 3.12 at the installed agents
tests: 790 passed, one failed because the new source-only leakage test read a
relative source path from the package test's external working directory. This is
a test defect, not an infrastructure flake. The test now resolves its source from
its own location and deliberately changes to an external temporary directory.
Original candidate bytes/logs/reports and manifest v1 are retained. No existing run
is cancelled or rerun; a corrected source requires a new hash-bound gate. Package
sources, README and build metadata are unchanged, and candidate byte equality must
be checked before publication. The scientific protocol, reader and raw are unchanged.
