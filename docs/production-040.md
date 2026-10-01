# Production 0.4.0 acceptance declaration

0.4.0 is published and the predeclared permissioned single-owner profile passes.
[Immutable tag CI / PyPA OIDC](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36911991678) and
[cache-disabled actual-PyPI CI](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36922605705) are whole-workflow successful at `f3f6ae30de6f088c160e0c69f49796e4f52d2546`.
Both validate all 12 native profiles, four cross readers, mixed Python and the
unchanged formal originals: 20 numerical and three additional gates, no pending validation.
Actual-index verification also matches all 36 root-inclusive resolved name/version audits,
with no findings or skips. [GitHub Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.4.0) contains the exact
tested wheel/sdist and checked evidence ZIP; actual downloads match their recorded hashes.
See [machine-readable actual results](release-040-results.json),
[Japanese final report](release-040-report.ja.md) and [declared scope](production-040.md).
The Linux one-hour observation, negative matched result and unverified wider scope
remain explicit. The immutable tag preserves its historical prepublication documentation;
the current actual results are recorded here on main without changing packaged files.

## Historical declaration and prepublication observations

The observations below retain their original checkpoint scope. Statements that
work was pending describe those historical checkpoints, not the current result above.

The profile was declared before implementation. All prepublication requirements
now pass on the unchanged candidate pair. Production 0.4.0 remains unpublished;
the immutable tag gates, actual publication, fresh PyPI verification and final
actual results are still required. The published baseline is
0.3.2 at `b172c0d0`, with all 12 native tag and
actual-PyPI profiles verified; see [validation](validation.md).

The final packaged candidate is source commit
`9cd9a741709f235bdd8f81d95828ac4c4aee8969`. Its single wheel/sdist pair is retained
in [the original build](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36848707217)
and reused unchanged by
[the formal native and production run](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36848916312).
The original build run was canceled after its candidate was retained; that
cancellation is not a complete matrix success.

- Wheel SHA256: `33898a964443c5276853dc15069247ff8642012332c980d085f9fa9a4faf11d7`.
- Sdist SHA256: `965f848ed12950d0a8cba26e6deb1594d8ce98437022fc9dd5dff0f7e860f8be`.

The formal job in run `36848916312` completed and exported 110 original files.
Their file hashes, profile digest, fixed driver sources and exact candidate pair
were verified. The ten-arm matched experiment passed. The soak failed two gates:
same-ID duplicate delivery returned a transport-side `ValueError`, so neither that
injection nor its unchanged-receipt assertion was established. The later explicit
restart returned the original receipt unchanged; it does not retroactively pass the
failed injection. The precise transport cause remains unknown. Both failed raw
observations and the assessment are retained.

[The complete formal repeat](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36858429932)
passed all 20 numerical and three additional soak gates, plus the five-pair
experiment, on the same pair, profile and driver sources without rebuilding.
The pressure pair retained static 4/24 versus adaptive 3/24; no general adaptive
advantage is established. The first failed soak remains failed and unchanged. Earlier complete native, soak and matched experiment observations
below apply to their named candidate hashes and cannot substitute for this final
pair. The release selector checks tagged packaged source bytes against the
pretested pair; it never rebuilds the pair at publication.

An additional restricted-role readiness regression checks changed policy bytes,
an unavailable OPA executable, a different private key and malformed key bytes.
Fresh normally installed final-wheel environments on Windows and native WSL Linux
CPython 3.12.14 passed all four cases. Each closes intake without an invocation or
allowance change, and repair still requires explicit resume. This adds test coverage
without changing packaged implementation bytes. The expanded test must also pass
the final native recheck before publication.

The first final-pair Windows 3.12/3.14 jobs passed their source and installed agents
tests but failed tutorial `initdb`: the Python-created temporary directory denied
PostgreSQL's restricted Windows process. Their original logs and reports remain
retained. The harness now grants only that fresh directory to the current user SID,
preserving its protected ACL and leaving other directories unchanged. The diagnosis
follows [Python's 0700 DACL implementation](https://github.com/python/cpython/blob/v3.12.14/Modules/posixmodule.c)
and [PostgreSQL's restricted-token implementation](https://github.com/postgres/postgres/blob/REL_17_STABLE/src/common/restricted_token.c);
the repaired native tutorial remains a required gate.

[The expanded native recheck](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36854239260)
has completed Linux 3.12/3.13/3.14, Windows 3.12/3.13/3.14 and Mac ARM 3.13/3.14.
Their original archive hashes, source and installed tests, short fault proofs,
tutorial results and 24 Python resolution audit/license/SBOM reports were reviewed.
All three Windows profiles now pass the native PostgreSQL tutorial.
Other expanded native profiles and all four cross-platform
readers remain required. Mac Intel 3.13 failed while installing pinned
`go-licenses`, before source tests; its artifact upload also timed out. The failed
Actions log is retained, and the exact Go installation cause remains unknown.

The final-pair supply review additionally includes four completed original Mac
profiles, covering all twelve native proxy reports and all 36 installed Python
resolutions with verified archive/file provenance. Go assembly/header/include and
original notices passed the existing review; all declared Python audit name/version
sets matched, with zero findings or skipped dependencies. This accepts P29's supply
scope without claiming the expanded readiness regression has passed on those four
older profiles. See [compatibility](compatibility.md) and
[proxy source/license review](../scripts/proxy/README.md).

Onboarding/documentation requirements P04, P26 and P27 also have final-pair
evidence across those twelve native profiles. Every core/agents/model import and
CLI came from a fresh installed environment with the selected child interpreter.
All twelve sequential README/quickstart/starter tutorials match the current Git
document hashes and passed the actual three-peer demo and positive DB/OPA doctor
checks. Setup regressions preserve secret/public separation and refuse overwrite.
The developer AGENTS, canonical user skill and `slills.md` entry were reviewed
separately; generated CLI/schema/local-link checks and eleven minimum-Python
syntax compilations passed. Compilation is not arbitrary snippet execution.
These closures preserve the remaining expanded readiness, soak, cross-platform
and publication gates.

Restricted-role/compatibility requirements P05 and P28 have also been reviewed.
All twelve native source reports passed the runtime DML versus DDL boundaries,
ordinary/interrupted published-0.3.2 dump/migration preservation and exact
checker/policy/digest regressions. The separate installed Linux 3.12 live upgrade
used the actual `cc4086d5` published wheel and final `33898a96` candidate. Its
35-call original transcript passed stopped-writer backup/migration, preserved
completed and UNKNOWN/held originals, closed restore/full sync/external review,
explicit resume and subsequent business reuse. Its 14.980-second result covers
the POSIX loopback CSV compatibility path. It establishes neither rolling updates
nor a legacy Windows/macOS graceful-stop or HTTPS deployment; fresh production
and expanded native readiness remain separate gates.

[The machine-readable profile](profiles/production-040.json) is the authority for
scope, operating limits, numerical acceptance targets, required faults, the actual
60-minute Linux release soak and five isolated matched experiment pairs.
[The requirement register](production-040-acceptance.json) records implementation,
tests, observations and remaining work. Empty implementation lists and null
observations mean unfinished work, not implicit acceptance.

The profile covers a permissioned mesh with one active process per owner, restricted
runtime database roles, trusted installed application factories, HTTPS and independent
application checks. The existing Registry, Executor, Store, OPA and finite goal loop
remain the authoritative execution path. Native Windows/macOS peers are part of the
required installed production gates. Their short gate does not imply an hour-long
soak observation on those systems.

All offered work, failure, UNKNOWN, refusal and censored outcomes stay in reports.
The performance bounds are targets for the declared workload and hardware envelope;
they are not a universal SLA. Positive adaptive benefit is not a release gate.
Paid inference is disabled in mandatory validation.
The [matched experiment runner](production-experiments.md) documents its fixed
assignments, actual production path, original-result validation and resource limits.
Development fixture runs remain separate from the formal five pairs.
The [soak driver](production-soak.md) records the fixed offered mix, faults,
resource measurements and retained development failures. The complete independent
prepublication assessment below passes; publication verification remains pending.

Do not relax this profile after seeing measurements. Preserve failed reports and
fix the implementation, then run the complete affected protocol again. A separately
motivated future profile needs a new identity and cannot retroactively pass this one.

The prepublication gate requires all operating, security, distribution and research
work. Only P31's actual publication/post-publication verification and P32's final
results report can remain as explicitly named post-publication actions after their
prepublication paths pass. This avoids requiring already published results to
authorize the first publication; it does not waive soak, experiment or native gates.

No 0.4.0 production implementation or acceptance run preceded this declaration.

The declaration was committed as `aa8cfe8` before production source changes.
Current development connects the installed application factory, separate secret
DSN/public config, packaged starter, restricted runtime role, owner process lock,
dependency readiness, drain and tracked physical DB work. It also adds bounded
HTTP capacity/read-only retry, original-ID remote reconciliation, offline coherent
backup, durable restore closure and explicit business review/resume, current versus
historical/compromised keys, standard redacted rotating logs and finite atomic CAS
publication. These compose the existing Registry/Executor/Store/signed events.
See [API](api.md) for their authority, failure states and exact commands.

Windows/CPython 3.12 development observations are partial evidence:

- Installed proposal allowance/restart/cancellation/fencing and existing
  application/exchange regressions passed 11 tests in 22.18 seconds. The original
  zero-budget heavy callback ran under `706d1d5`; its failing regression is retained.
  The corrected actual three-process document host normal and checker-bottleneck
  paths passed two tests in 151.20 seconds. These are targeted source observations;
  full native, soak and matched-profile acceptance remain pending.
- A full source regression passed 316 tests in 1288.17 seconds, with zero failures,
  errors or skips. It preceded the later recovery review, CAS capacity and logging
  additions and used the subsequently rejected official proxy binary.
- The updated recovery/reconciliation/quota/sync/migration/operations group passed
  27 tests in 56.33 seconds. Real restoration into a new PostgreSQL database retained
  UNKNOWN, original signed bytes and allowance, refused incomplete synchronization
  and external-budget mismatch, remained closed across restart and required explicit
  resume. Local DB completion time handles restore ordering without comparing
  clocks from different peers; source timestamps still govern evidence freshness.
- Eight focused logging/CAS/HTTPS/backup/recovery tests passed in 22.17 seconds
  using the audited custom Caddy build. Known bearer/DSN/raw input values were absent
  from service logs; four actual processes could not race CAS capacity. The preceding
  run had seven passes and one test-teardown variable-shadowing failure; its report
  was retained and the test corrected before the complete group was repeated.
- Routine/compromise key and withdrawal tests passed as a five-test group. Historical
  origin remains inspectable; compromised signatures cannot authorize current use.
- A frozen source run at `275c49d` retained 320 passes and two failures in 1115.50
  seconds: a fixture lacked Config's new artifacts helper, and native Windows
  concurrent creators wrote an empty lock file before holding its lock. Both were
  corrected. The deterministic native capacity group passed three tests in 1.30
  seconds. This failed full-suite report is retained; it is not a complete pass.
- The packaged document implementation passed its existing 15-test group in 304.01
  seconds. Standard host formation/check/reuse/restart/withdrawal and checker
  bottleneck cases passed two tests in 70.36 seconds. A later six-test host group
  passed in 80.64 seconds, including exact-pin restart with 24 unrelated retained
  candidates, unchanged signed envelopes and original-signature observation reads.
  These three peers still used loopback development URLs and demo database roles.
- A ten-test host/native-lock/actual-HTTPS group passed in 21.07 seconds with the
  audited custom proxy. The actual published 0.3.2 wheel produced a fixture with
  14 original signed records and one original remote mapping. Fresh PostgreSQL
  dump/restore and ordinary/interrupted migration passed two tests in 8.23 seconds.
  That fixture regression does not establish the full live three-peer upgrade.
- Frozen source `58874b3` passed all 329 tests in 1242.10 seconds, with zero failures,
  errors or skips. Its fixed wheel/sdist passed normal clean core import/CLI,
  54 agents unit tests, one model adapter test and 55 tests after rebuilding the
  sdist with the observed native CPython 3.12.14. This checkpoint preceded the
  later three-peer HTTPS/MCP reference integration.
- The later three-owner standard CLI path uses installed setup, separate secrets,
  restricted runtime roles, HTTPS Caddy and an explicitly registered authenticated
  official MCP counter. Actual MAF composition uses A2A to this counter; independent
  checks, scoped reuse, subsequent formation, restart and withdrawal remain active.
  A four-test native group passed in 166.82 seconds, including at least 120 seconds
  of actual continued service observations in the normal case. MCP stop/restart
  leaves the original request UNKNOWN/held; its ready-service replay makes no new
  external tool call and no refund, verified with a private test call oracle.
  Known credential and held-out input strings were absent from service logs.
  The full required fault protocol and all native installed profiles remain open.
- The positive MCP-binding/call assertions and normal/bottleneck host cases passed
  two tests in 152.21 seconds. Eleven PostgreSQL/OPA feed/key regressions passed in
  20.55 seconds: current receipts transport unchanged known historical signatures,
  while old feed keys, direct compromised submissions and compromised admission
  remain denied/UNKNOWN. Neither an anchor nor an old timestamp grants authority.
- Frozen source `fbc1273` passed all 340 tests in 1339.88 seconds with zero failures,
  errors or skips. This includes bounded staged Registry revisions and the raw
  native socket-disconnect fix. Later recorded-choice integration is a separate
  development change and is not included in that frozen source result.
- Fifteen Registry/persisted-binding tests passed in 31.07 seconds after adding
  signed operator choices, private CAS comparison/decision references, publication
  capacity failure, compromised choice denial and exact restoration. One actual
  three-owner HTTPS/MCP/MAF reference test passed in 129.16 seconds: independently
  detected calibration FAIL and unchecked refusal retain the original; a checked
  replacement and explicit rollback survive process restart. Historical command
  replay preserves original signed bytes and completed invocation results.
  Those cases do not establish general checker comparability or the complete
  all-native production fault protocol.

- Frozen source `0a6ce62` passed all 340 tests in 1539.23 seconds with zero
  failures/errors/skips and unraisable pytest warnings treated as errors. It covers
  recorded choices/startup diagnostics, before later checker/CPU observations.
- Checker source/calibration-contract pinning passed one complete normal actual
  HTTPS/MAF/authenticated MCP case on Windows in 131.04 seconds and native WSL
  Linux in 134.79 seconds. Incorrect checker identity does not spend verification
  allowance. These are working-source observations, separate from frozen source.
- Standard OS CPU observations passed seven actual TLS/owner tests in 34.12 seconds.
  DB cursor/OPA/A2A monitoring then passed eight tests in 34.47 seconds. Windows
  venv launcher versus actual Python PID, and one nonexistent test path, caused
  earlier retained development failures. No failure or overlapping group is hidden.
- Native Linux custom Caddy passed standard upstream/module/license/vulnerability/
  SBOM checks with Go 1.27.1 and 1007 linked packages. Its separate report ZIP is
  retained. The WSL Linux fixture observed 16 logical CPUs and about 30,988 MiB
  memory without caps; these build reports do not establish bare-metal or accepted
  hour-long operation. The later [first full-duration soak](production-soak.md)
  preserves its failed RSS bound and two failed fault fixtures.

The preceding development reports remain retained: two successful HTTPS business
cases with one 5-second administrative teardown timeout; two MCP manifest failures
from noncompact JSON in the test setup; and a run with a reused wrong test binding
digest plus an HTTP/3 UDP bind refusal on Windows. Administrative cleanup now uses
its separate finite operator connection; runtime limits stay unchanged. Manifest
encoding and the test's exact binding reference were corrected. The packaged
listener explicitly uses standard HTTP/1.1 and HTTP/2, the TCP transports required
by this profile. These fixes do not lower the acceptance targets.

These groups overlap and are not an additional complete-suite count. Local tests
do not establish all native installed profiles, networked three-peer recovery,
the complete production application protocol or all-native promotion faults.
The first full-duration soak failed acceptance, and the first ten-arm experiment
used work credits where the profile also required a separate wall-time envelope.
Their failures remain retained. Subsequent complete corrected candidate runs
passed [the soak assessment](production-soak.md) and
[the matched experiment assessment](production-experiments.md). Final-pair results
are still required before closing those gates in the requirement register.

The later short protocol adds physical checker unavailability, quiescent signed
Evidence withdrawal followed by a new independent check, four execution slots,
finite budget exhaustion and the unchanged 32-unresolved ceiling. Actual HTTPS
pressure fills all 16 owner/four caller slots and observes 429/503 with
Retry-After. It exposed a smaller Uvicorn transport gate, which now permits the
authenticated request gate to respond without changing the declared limits.
Routine/current-key rotations restart all three owners; historical bytes stay
unchanged, old HTTP authority is refused and known compromised origin becomes
UNKNOWN. Windows development passed this combined path in 220.61 seconds.
Earlier combined failure and transport-pressure failures remain retained.

A normally resolved wheel outside checkout then passed the expanded nineteen
injections on native WSL Linux CPython 3.12.14 in 129.76 seconds. Its retained
bounded report checks all declared injections and hashes ten proof files;
Windows export validation then passed in 223.61 seconds; the complete final native
matrix remains a separate gate.
The tested wheel SHA256 is
`7f1c3db17bc7bd7c4c039e7b83676512b55482cfdd2ca5aa6ec3416d0a19e65f`;
sdist SHA256 is
`626a7bd2765f4a6f52f1bb45806518fb53f1e4a8798a08127fb091d9084edacf`.
CI retains source and installed short-protocol proof files without copying keys,
private homes or backup secret archives. These observations do not accept the
hour-long soak, live 0.3.2 upgrade or complete production profile.

The official Caddy 2.11.4 release binary was rejected after standard govulncheck
reported 28 affecting vulnerabilities. Its functional test and verified archive
digest do not override that result. Its SBOM also omitted most license fields.
Both findings and original reports remain part of the development evidence.

The reference proxy is now explicitly `v2.11.4+cio.1`: the same pinned upstream
commit, a frozen security-updated Go dependency graph, two public CEL API type
adjustments and native Go 1.27.1. This is a reviewed custom build, not an official
Caddy release binary. The Windows build passed upstream HTTP/TLS tests, standard
module verification, go-licenses check/notice collection, govulncheck and CycloneDX
package/file/license SBOM generation. One module-only OpenPGP advisory remains
visible and was reviewed as nonapplicable because no affected package is imported;
there were zero package/symbol findings. See [proxy build and license review](../scripts/proxy/README.md).
The font OFL and MySQL MPL obligations are retained explicitly. Other native
proxy builds and the complete Python resolution audits remain required.

## Final-pair operational review

The existing final-pair originals were independently checked as 12 native
profiles: eight expanded `fdf0f96` reports from run `36854239260` and four
`9cd9a74` Mac reports from run `36848916312`. All selected application,
operation, reconciliation, recovery, TLS, MCP, proposal, invocation, binding and
logging test sources are identical. Each source suite reports 374 and each
installed agents suite 373 tests, with zero failures, errors or skips. The
review retains the archive and every input-file hash, actual native interpreter
and 22 selected JUnit case groups.

All 24 source/installed short protocols passed their unchanged 19 required
injection categories and ten original proof hashes. Independent review checks
identical duplicate receipts; UNKNOWN/held preservation after provider restart
and delayed MCP response; positive reserved-phase release; unchanged 4 execution,
32 unresolved and HTTP 16/4 limits; drain refusal; duplicate owner denial; actual
DB disconnect/owner kill; old/current standard PostgreSQL restore differences;
routine/compromise key rotation; physical checker unavailability; withdrawal;
and protected trial refusal. The old restore remains business unknown, and a
matched restore does not create independent PASS. No uncertainty refund, source
freshness inference or external replay is accepted.

This closes individual application and operation requirements P06-P08,
P10-P19 and P21. It does not establish all twelve expanded readiness tests,
the new formal soak, the current complete cross matrix or publication. The
failed first formal soak and all earlier negative originals remain retained.
Whole-profile acceptance stays closed. P22 change/comparison and P20 full
resource evidence are assessed separately.


## Complete unchanged final-pair formal repeat

Run `36858429932` retained original artifact `11164682635`, ZIP SHA256
`d4463e903f853a4fb9eac8c4e1b7e3128ec472ad6a6d2a410ab058f8810f0a53`.
All 110 original report files match raw manifest SHA256
`aa9384792b9e1405dfd71d4fd6f3b51c37c993f95d79cd806abd454921a4f135`.
Independent assessment verifies the exact final pair, predeclared profile and
unchanged driver sources. Soak and matched experiment both pass. The negative
first final-pair soak and earlier experiments remain retained separately.

P20 and P24 are now verified for their declared scopes. The complete native/cross
matrix, the new settings-publication fault and P22 change/comparison review,
whole integrated acceptance and publication remain open. No release manifest or
tag is created before those requirements pass. See the exact
[soak observations](production-soak.md) and
[paired negative observation](production-experiments.md).

## Settings-publication fault added to the same candidate

The updated host-normal source and installed protocol obstructs only its own
settings temporary path after an independently checked replacement and committed
signed choice. Fresh ordinary final-wheel installations passed this complete
three-owner path on Windows and native WSL Linux CPython 3.12.14. They verify
closed intake, unchanged persisted settings/external calls, old active binding
after restart and historical-choice retry without reapplying the transition.
Package implementation bytes remain unchanged. The added assertions must pass
all twelve updated native profiles before P22 and whole acceptance close.
The [operator change procedure](deployment.md) also covers isolated finite
checker/allocation trials and explicit retained configuration activation.

## Complete final-pair readiness review

All twelve native profiles in run `36858429932` passed the expanded restricted-role
readiness cases in source and installed suites. The unchanged bootstrap test checks
modified policy bytes, unavailable OPA, a different valid private key and malformed
key bytes; intake stays closed without new invocation or allowance change, and
repair requires explicit resume. Every profile also passes the seven operation
regressions and actual authorized/private TLS health cases. Archive provenance and
unchanged source hash are retained in `readiness-review12-v1.json`. P09 is verified;
this does not replace the full updated settings-fault/native/cross gates or publication.

## Portable native notice review failure and correction

The formal repeat's twelve native jobs and all four cross readers completed
successfully; each reader verified 228 original signatures from all twelve origins.
Its ready job `110412664876` then failed at `check_proxy_sources.py:140` before
integrated production assessment or the acceptance-register check. Windows native
`saved_notices` values used backslashes, which Linux treated as part of one filename.
The original failure log is retained with SHA256
`ff412a3efe00e0f0cc08456d730a4ac1f651ca298cc1c5712dfa17e90fad70d9`.
This whole workflow is not a pass.

The reviewer now reads both native relative separator forms while rejecting empty,
absolute, drive-qualified, parent-traversing and missing paths. New proxy reports
write portable forward slashes. The original native reports are not rewritten.
Eight release/path guard tests pass. An actual Linux review of all twelve coherent
formal-repeat native originals passes with 2,814 retained files, no unresolved
literal assembly includes, and source/notice ZIP SHA256
`dd0b69b10b5e1e6b192ea3204a820bb95ca0cfb49654333158fea091656dc3d6`.
The frozen wheel/sdist and every formal driver remain unchanged. The complete
updated native/cross gates, integrated acceptance and publication remain required.

## Complete prepublication assessment of the updated final pair

Run `36870275184` completed all twelve native source and normally installed groups:
374 source, 373 installed agents, one separate mocked-model and 63 rebuilt-sdist
tests per profile, with zero failures, errors or mandatory skips. All 24 original
source/installed short fault protocols satisfy the nineteen declared categories
and their ten-file proof hashes. The added settings-publication recovery passes
on every native OS/CPU/patch. All four installed cross readers verify 228 original
signatures from all twelve origins; mixed minimum/latest Python also passes.
All 36 actual installed dependency name/version sets exactly match their original
audits without findings or skipped dependencies, with paired licenses and SBOMs.
The unpublished first-party root's actual-index audit remains post-publication work.

This run's old ready job `110443929442` failed at the same corrected notice lookup;
its original log SHA256 is
`a54c07ac6dc4f3a5e369428674ad80d78986f91dcd29dabb5923c80c16f69ea3`.
Neither failed whole workflow is called a pass. Using the current fixed reviewer,
an actual Linux assessment of all twelve updated native originals passes: 2,814
source/notice files, no unresolved literal includes, and source/notice ZIP SHA256
`b1b86f015a0e835a4deed1211a77e49b3015e79d6e3496f1efe9f856b155a0a9`.

Canonical Git source bytes match all ten original formal driver files. Existing
`check_production_reports.py` independently reassesses the unchanged 110 originals:
20 numerical and three additional soak gates, and the five-pair matched experiment,
all pass. Derived assessments remain outside the original set. The complete
`check_matrix.py` passes against the combined updated native/cross/mixed/formal
reports and the accurate prepublication register. P03-P30 are verified at their
declared scopes. Only actual publication/post-publication verification (P31) and
the final actual report (P32) remain.

The [release selector](release-040.json) fixes original run `36858429932`, source
`fdf0f961351f7d18bcd314eb5c3e6d28916db4e1`, exact artifacts and raw `aa938` manifest.
The immutable tag must rerun the current complete native/source/ready gates,
including the newly added portable-path regression, before OIDC publication.
It restores these tested artifacts rather than rebuilding a publication pair.
