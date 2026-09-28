# Validation status

0.2.0 development: the latest full local PostgreSQL/OPA/SDK run passed 80 tests
with zero skips (109.39 seconds). A subsequent decimal-aggregation correction
passed the 9-test record/accounting unit module, including a new precision case.
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
