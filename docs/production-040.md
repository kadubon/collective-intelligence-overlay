# Production 0.4.0 acceptance declaration

This is a preimplementation declaration, not a supported release or a validation
result. The published baseline is 0.3.2 at `b172c0d0`, with all 12 native tag and
actual-PyPI profiles verified; see [validation](validation.md).

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
the complete production application protocol, promotion, the hour-long soak or ten matched
experiment arms. Those gates remain open in the requirement register.

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
