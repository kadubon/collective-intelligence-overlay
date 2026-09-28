# Validation status

Local observations before release:

- 36 tests passed against real PostgreSQL and OPA, including the three-process A2A
  lifecycle, actual MAF Agent/tool execution and workflow composition, MCP HTTP,
  provider adapter with mock HTTP, signature/identity/expiry failures, graph cycles,
  evidence withdrawal, lease competition and stale-worker result rejection.
- Ruff and strict mypy passed at that checkpoint.
- Wheel/sdist built; twine strict metadata check passed. A fresh external environment
  installed the wheel, ran CLI/core SDK checks and rebuilt a wheel from the sdist.
- pip-audit reported no known vulnerabilities for the checked environment. The
  unpublished local project itself had no PyPI entry to audit.
- License metadata was reviewed using pip-licenses, and CycloneDX generation is
  part of the release checks.

These are checkpoint results. The release workflow reruns checks on the release
commit and publishes the same tested distributions. Refer to [releasing](releasing.md)
for actual CI/publication state; presence of a workflow is not a successful run.

Not established: paid model quality, a fully resource-matched distributed baseline,
multi-organization operation, external security audit, long-duration availability,
general semantic correctness, instantaneous remote revocation, arbitrary external
effect exactly-once behavior, physical memory erasure or intelligence-growth theorems.
No production SLO or universal commercial-readiness claim is made.

`pytest` skips service tests if explicit service configuration is absent. CI's main
Linux job provides both services and executes the complete suite. Its Windows job
checks portable unit/package behavior; it does not claim a Windows-hosted PostgreSQL
production deployment. Local Windows-to-WSL full tests are separately reported.
