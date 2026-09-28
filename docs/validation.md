# Validation status

Registered-demo checkpoint: the complete local service suite passed **106 tests,
zero skips, 242.72 seconds**. The subsequent commit/rollback parameterization and
registered checker mismatch/FAIL tests passed with their focused suites (**10 tests,
17.09 seconds**). Both changes are included in the next distribution run.
The standalone evaluation command also completed its three-process registered-A2A
path: ACCEPT, 117.00, REQUALIFY, REJECT, with a durable execution receipt. All four
deterministic comparison arms returned 3/3 correct; their timings do not establish
model-quality or speed gains. Ruff, format, mypy and documentation checks pass.

Local 0.2.0 distribution preparation: wheel/sdist build and strict twine checks
passed. A fresh environment outside the checkout passed the core import/version/path
checks, **96 agents tests (251.90 seconds, zero skips)** and **one model adapter test
(6.98 seconds)** after installing that extra separately. The sdist rebuilt and its
wheel reinstalled successfully; CLI reported 0.2.0. The installed
development environment's pip-audit check found no known vulnerabilities among
auditable dependencies; the unpublished project 0.2.0 was explicitly skipped by
the index lookup. License metadata checks passed for 129 distributions, and
CycloneDX 1.6 generation produced 133 components. These are point-in-time tool
observations, not an external audit or a completed CI/release gate.

Tested local checkpoint artifact hashes (not published release artifacts):

```text
e0ffdbd07915615730614f7c093e631763d5313301d1ac08bcd12a0035dd651a  collective_intelligence_overlay-0.2.0-py3-none-any.whl
a340a95e407925fd851d52e2915b41e521082d45f376ccb0522d32983a7f542e  collective_intelligence_overlay-0.2.0.tar.gz
```

Latest full-service checkpoint: **96 passed, zero skipped, 244.02 seconds**, with
PostgreSQL/OPA, real dump/restore, migrations through 0008 and A2A response limits.
The CSV registration example added after collection passed separately (**1 passed,
3.65 seconds**). The separate stress run passed 1,000/10,000/100,000 profiles; see
[scale observations](scale.md). These local checks do not establish CI/publication.

0.2.0 development: the latest full local PostgreSQL/OPA/SDK run passed 84 tests
with zero skips (179.25 seconds), including the external three-process C1–C4
document application. Subsequent numeric/formation-cost checks passed 5 focused
tests, and the final MAF proposal-tool version of that E2E passed in 39.19 seconds.
The subsequent exact-issuer dependency-query and cycle-identity fixes passed 17
indexed-storage/negative-path tests with real PostgreSQL/OPA (19.82 seconds, no skips).
The new mixed signed-history harness passed its 1,000/10,000 profiles (2 tests,
65.82 seconds). Both returned nine SELECT rows, executed nine DB statements and
verified four signatures per qualification over five repetitions. An enum-only
fixture correction removed serializer warnings and passed the 1,000 profile again
(8.73 seconds). The first 100,000 profile failed with UNKNOWN after bulk setup;
the full three-profile run took 672.68 seconds. The fixture's source observations
were established before setup and exceed the unchanged 300-second freshness limit
at that scale. The harness now establishes direct local-fixture observations after
setup and prints full decision reasons on failure. The revised three-profile run
passed all three tests in 673.69 seconds, including 100,000 records. Each of the
15 target qualifications verified four signatures, executed nine DB statements and
returned nine SELECT rows. Raw observations and limits are in [scale methodology](scale.md).
Migration and restore tests subsequently passed five checks (6.77 seconds, zero
skips), including actual PostgreSQL custom dump/restore through the WSL client
tools, original signed 0.1.0 data, post-restore cursor/freshness invalidation and the
offline CLI path. Full production artifact/key recovery remains operator-specific.
Migration 0008 and exact reverse dependency filters passed 11 inspection/migration
tests (18.70 seconds). With the new projection installed, indexed-storage and the
1,000 profile passed another seven tests (21.83 seconds), all with zero skips.
Shared A2A HTTP response limits passed six tests (50.25 seconds, zero skips),
including real chunked HTTP rejection, standard service execution and the complete
three-process document formation E2E.
Ruff/format, strict mypy and documentation checks pass. Detailed scope and unfinished
0.2.0 release gates are tracked in [implementation status](implementation-status.md).
The release and package observations below concern 0.1.0 unless explicitly stated.

Local observations before release:

- 43 tests passed against real PostgreSQL and OPA, including the three-process A2A
  lifecycle, actual MAF Agent/tool execution and workflow composition, MCP HTTP,
  provider adapter with mock HTTP, signature/identity/expiry failures, graph cycles,
  evidence withdrawal, lease competition and stale-worker result rejection.
- Ruff and strict mypy passed at the local release-preparation checkpoint.
- Wheel/sdist built; twine strict metadata check passed. A fresh external environment
  installed the wheel, ran CLI/core SDK checks and rebuilt a wheel from the sdist.
- pip-audit reported no known vulnerabilities for the checked environment. The
  unpublished local project itself had no PyPI entry to audit.
- License metadata was reviewed using pip-licenses, and CycloneDX generation is
  part of the release checks.

These are checkpoint results. The release workflow reruns checks on the release
commit and publishes the same tested distributions. Refer to [releasing](releasing.md)
for actual CI/publication state; presence of a workflow is not a successful run.

Not established: paid model quality, resource-matched real-model comparisons,
multi-organization operation, external security audit, long-duration availability,
general semantic correctness, instantaneous remote revocation, arbitrary external
effect exactly-once behavior, physical memory erasure or intelligence-growth theorems.
No production SLO or universal commercial-readiness claim is made.

`pytest` skips service tests if explicit service configuration is absent. CI's main
Linux job provides both services and executes the complete suite. Its Windows job
checks portable unit/package behavior; it does not claim a Windows-hosted PostgreSQL
production deployment. Local Windows-to-WSL full tests are separately reported.

GitHub release-tag CI succeeded for `7e4f119` (`v0.1.0`): 43 source tests and 43
clean-wheel tests passed on Linux, alongside Windows unit/package checks and
license/security/SBOM checks. The earlier e710c59 Linux startup-readiness failure
was fixed with a regression test.

After OIDC publication, both actual PyPI file hashes matched the CI artifacts.
A fresh Python 3.12 environment installed `collective-intelligence-overlay[agents]`
from PyPI with cache disabled and ran outside the repository. Version/import/CLI
checks and the three-process lifecycle passed: ACCEPT, report total 117.00,
environment change REQUALIFY, dependency revocation REJECT. Each of the four
network comparison modes produced 3/3 correct results; these deterministic checks
do not establish model-quality gains or an overlay speed advantage. The result
and supply-chain reports are attached to the [release](releasing.md).
