# Release procedure and current state

## 0.3.1 candidate, unpublished

The four audit fixes are committed locally; Python extension and final gates are
in progress. The required stable matrix is Linux/Windows × CPython
3.12.14/3.13.15/3.14.7, plus minimum/latest mixed installed peers. No successful
0.3.1 CI, tag, GitHub Release or PyPI publication is claimed yet. See
[validation](validation.md) and [exact runtime scope](compatibility.md).

`candidate` builds one wheel/sdist pair on explicit CPython 3.12.14, runs strict
twine and records SHA-256. Every OS/minor downloads those files. The common
`scripts/ci_validate.py` runs frozen full source/service tests, lint/format/type,
docs and supply-chain gates, then normal-resolution independent core, agents and
agents/model installed checks. Each sdist rebuild uses an observed explicit
PEP 517 interpreter; its rebuilt wheel is never substituted for the publish file.
Windows starts a private loopback cluster from the runner's PostgreSQL binaries;
Linux uses PostgreSQL 16.15. Required service tests cannot be skipped.

`mixed` uses the same candidate in two fresh installed interpreters and tests both
directions. `ready` requires exactly six complete OS/patch reports, zero mandatory
failures/errors/skips, matching candidate hashes and the passing mixed report.
`publish` depends on all of those jobs, rechecks the original hashes, and transfers
only the original pair to official PyPA OIDC publishing. Only that job has
`id-token: write` and the protected `pypi` environment. No matrix job publishes.
Exact tag/version and `main` ancestry checks remain required before publication.

Local example, with real services configured:

```sh
uv build --force-pep517 --python 3.12.14 --out-dir .local/candidate/dist
uv run --python 3.14.7 python scripts/check_package.py --python 3.14.7 --dist-dir .local/candidate/dist --test-scope full --report .local/package-3.14.7.json --supply-chain-dir .local/supply-3.14.7
```

The checker rejects a missing requested interpreter, a wrong minor/patch and a
candidate hash mismatch. CLI, pytest, demo subprocesses and backend startup must
use the selected executable and import CIO from their fresh site-packages.
Publication requires fresh actual-PyPI core/agents/model installs on every stable
minor, minimum/latest installed audit regressions, and actual downloaded wheel/
sdist hashes matching the tested candidate. Historical release results below are
not evidence for this candidate.

## 0.3.0 published and verified on 2026-09-30

- Release commit `a2fc32b5511b3c3cec4f2e15fcd6375eb9540c67`, annotated tag `v0.3.0`.
- [Main CI](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36637949588)
  passed before tagging: 189 Linux source tests (381.67 seconds), clean agents
  188 tests (242.96 seconds), one model adapter test (0.82 seconds), and Windows
  source/installed unit 30/30 plus model checks. No mandatory-service skips.
- [Tag CI and official PyPA OIDC publication](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36639581573) passed on the same commit:
  Linux source: 189 passed in 427.35 seconds; clean agents: 188 in 299.24 seconds;
  model adapter: one in 1.10 seconds. Windows source: 30 in 5.36 seconds; clean
  unit: 30 in 3.58 seconds; model adapter: one in 2.61 seconds.
  Linux used CPython 3.12.3; Windows used 3.12.10.
  Lint/format/type, real PostgreSQL/OPA/MAF/A2A/MCP, docs, audit, 128-distribution
  license review, CycloneDX, wheel/sdist build, strict twine and clean package gates
  passed. Core import/CLI/resources and sdist rebuild/reinstall passed outside checkout.
  Required tests had zero failures and zero skips; the provider test used mock HTTP.
- [PyPI 0.3.0](https://pypi.org/project/collective-intelligence-overlay/0.3.0/) wheel/sdist match the exact tag CI files, by both index
  metadata and actual downloaded SHA-256. The publish job transferred tested artifacts
  without rebuilding them; no API token, overwrite or skip-existing was used.
- A cache-disabled actual-index install in a fresh Python 3.12.10 environment
  outside checkout passed distribution/import/path/CLI and **89 tests in 532.69 seconds**,
  zero failures/errors/skips. This includes all eight three-process E2E cases,
  opportunities, peer alternatives, checking/lineage/metrics, invocation reservation,
  real migration/backup/restore and saved experiment consistency.
- The actual-index environment's 72 distributions, including published 0.3.0,
  passed known-vulnerability audit without an index skip and the existing license
  allowlist. Public audit and license reports accompany the release evidence.
- [GitHub Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.3.0) attaches those distributions, CI SBOM/licenses,
  sanitized post-install verification and the six-arm raw experiment archive.
  No publication or authentication blocker remains. Stop all old workers and back up
  database, keys and saved artifacts before migrations 0009–0012; rolling old-peer
  interoperability is untested. Local signing identities do not establish independent
  organizations. Paid inference, external audit and long-term operation are untested.

```text
c482e567f44c4336014885b58fc625654345fffd5753225285aca70369934497  collective_intelligence_overlay-0.3.0-py3-none-any.whl
9f83afad28d0ab18a82d34469dd7d400c8f0f761f0f265e5d5f40eb7532eea11  collective_intelligence_overlay-0.3.0.tar.gz
```

## 0.2.1 published and verified on 2026-09-28

- Release commit `3026c39b7cb3a4808e4b1eaf45332b1b81f4df8a`, annotated tag `v0.2.1`.
- [Main CI](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36382765828)
  passed before tagging. [Tag CI and OIDC publication](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36383207196)
  passed: 129 Linux source tests (190.77 seconds), 128 clean agents tests
  (126.45 seconds), one model adapter test (1.08 seconds), Windows unit/package
  checks, audit/license/SBOM/build/docs gates. No mandatory-service skips.
- [PyPI 0.2.1](https://pypi.org/project/collective-intelligence-overlay/0.2.1/)
  wheel/sdist match the exact tested CI artifacts. A cache-disabled actual-index
  install in a new Python 3.12 environment outside the checkout passed import,
  version, CLI and 34 allowance/migration/restore/E2E tests (105.58 seconds), zero skips.
- The first immediate install preceded simple-index propagation. An ordinary retry
  after the version appeared succeeded; no distribution was replaced or overwritten.
- [GitHub Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.2.1)
  includes distributions, CI licenses/SBOM, hash/install verification and both
  application results. Stop all old workers before migration 0009; legacy
  reservations remain unknown and are not automatically refunded.

```text
5d5c35188aaee07c25731d096f05e424ea59cdeb15b19f721dc13be0d98336a7  collective_intelligence_overlay-0.2.1-py3-none-any.whl
988c71482d60430e5cc57bd48eba0f269528d3a1ba2a41b473d1e23fc4a62750  collective_intelligence_overlay-0.2.1.tar.gz
```

The 0.2.1 artifacts remain unchanged. The 0.2.0 publication record below was
already accurate at the start of this two-stage work.

## 0.2.0 published and verified on 2026-09-28

- Release commit: `394ba59aa6ec9e95b4f725862747f5198826cf9b`; annotated tag `v0.2.0`.
- [Main CI](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36378773155)
  passed before tagging. The [tag workflow](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36379126931)
  then passed Linux validation, Windows checks and official PyPA OIDC publication.
- Linux: 108 source tests (176.18 seconds), 107 clean agents tests (117.30 seconds)
  and one separately installed model adapter test (1.09 seconds), with no mandatory
  skips. Windows: 22 source unit tests, 22 clean unit tests and one model test.
  Docs, build, strict metadata, dependency audit, 128-distribution Linux license
  review and CycloneDX generation passed.
- [PyPI 0.2.0](https://pypi.org/project/collective-intelligence-overlay/0.2.0/)
  contains the exact tested wheel and sdist. Both actual downloaded hashes match
  the CI distributions artifact; the publish job did not rebuild them.
- A fresh Python 3.12 environment outside the checkout installed
  `collective-intelligence-overlay[agents]==0.2.0` from the actual PyPI index with
  cache disabled. Distribution/import/CLI and both three-process E2Es passed:
  **2 passed, zero skips, 68.97 seconds**. These cover registered CSV execution and
  C3-to-C4 document formation, independent checking, restart and withdrawal.
- The first installation immediately after publication could not yet resolve
  0.2.0. The index subsequently listed it and an ordinary retry succeeded;
  no artifact substitution or release overwrite was used.
- [GitHub Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.2.0)
  attaches those distributions, CI licenses/SBOM, hash verification, E2E output and
  both installed-application result records. No publication blocker remains.

Published SHA-256 values:

```text
e9fe99ed6073995483eadffcab3e6dd0e0266c0bb69ec2c1666f1e34baa61d0b  collective_intelligence_overlay-0.2.0-py3-none-any.whl
f4e6a98098fc612f746b35952cb8a3d8663ea19dfdb8a1577b9e06e7a5ffcb71  collective_intelligence_overlay-0.2.0.tar.gz
```

## Historical 0.1.0 publication

Published and verified on 2026-09-28, before 0.2.0:

- Release commit: `7e4f1191aaf7e9bca8a6091e1758204e189cb924`; annotated tag `v0.1.0`.
- [Tag workflow](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36362453372)
  succeeded: Linux validation, Windows checks and official PyPA OIDC publication.
- [PyPI 0.1.0](https://pypi.org/project/collective-intelligence-overlay/0.1.0/) contains
  the wheel and sdist; both SHA-256 values match the checked CI artifacts.
- [GitHub Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.1.0)
  attaches those exact distributions, dependency licenses, CycloneDX SBOM, hash
  verification and the installed-package demo result.
- A fresh Python 3.12 environment installed from the actual PyPI index with cache
  disabled. Distribution/version, import from site-packages, CLI and three-process
  demo passed from outside the source checkout. No publication blocker remains.

Published SHA-256 values:

```text
07498d00996e89a5b88908bed450981aabf024aa3bb9dd204d18c7c959b87aaa  collective_intelligence_overlay-0.1.0-py3-none-any.whl
3fe3147dd08ec765d00df9d7e0b95d54776bf07dc4ce0bd25df511953e13b34d  collective_intelligence_overlay-0.1.0.tar.gz
```

Post-publication documentation updates on `main` do not move the release tag or
rebuild its distributions. The `pypi` GitHub environment exists; future releases
remain subject to the configured GitHub/PyPI permissions and protection rules.

The only publication workflow is `.github/workflows/workflow.yml`. It requires
successful mandatory stable Linux/Windows source/service/package/security/docs
matrix and mixed-interpreter checks. Tags must equal `v<pyproject version>` and
their commit must be in `main`.
Only the tag-push publish job receives `id-token: write`, and only that job uses the
`pypi` environment. PRs cannot enter publishing. `pull_request_target` is not used.

Configure the PyPI Trusted Publisher with exactly:

- Owner: `kadubon`
- Repository: `collective-intelligence-overlay`
- Workflow filename: `workflow.yml`
- Environment: `pypi`
- Project: `collective-intelligence-overlay`

Create/review the GitHub environment's protection rules without weakening existing
settings. The official PyPA publish action performs OIDC exchange. No long-lived
PyPI token is requested or stored. All actions are pinned to commits verified through
GitHub's API. The publish job downloads the checked wheel/sdist artifact and performs
no source checkout or rebuild. Do not use skip-existing to hide conflicting releases.

Release steps: run frozen checks, build, twine check, clean wheel/sdist installation,
license/vulnerability/SBOM checks; commit/push; verify CI; create the matching
`v<pyproject version>` tag; verify tag
workflow and PyPI; install from the actual index in a fresh environment; then create
GitHub Release notes describing scope, compatibility and unverified boundaries, and
attach the exact published distributions and supply-chain reports.

For local checks alongside historical artifacts, build into a separate directory
with `uv build --out-dir .local/dist-candidate` and run
`uv run python scripts/check_package.py --dist-dir .local/dist-candidate`.
Use a fresh directory per version; never mix two releases in the publish artifact.
The checker verifies packaged schemas/migrations/licenses and uses independent
fresh core, agents and agents/model environments outside checkout. It verifies
the installed version/path/CLI, runs agents tests and the mocked provider test,
then rebuilds/reinstalls the sdist wheel. It reports the unchanged original release
hashes and actual resolved profiles. CI uses `.local/candidate/dist` and publishes
only that originally built pair; a manifest sits outside the publish directory.

If name ownership conflicts, OIDC is rejected or environment approval is required,
stop that operation and record the exact error here. Never rename the project,
disable protections, request an API token or overwrite an existing distribution.

After verifying publication, activate a fresh environment for each tested Python and substitute
the version just published (for example the verified 0.3.0). The historical
0.1.0 hashes above are not the version selector for a future release:

```sh
uv pip install --index-url https://pypi.org/simple 'collective-intelligence-overlay[agents]==0.3.0'
```

The optional `model` extra supplies the provider adapter; actual paid calls remain
explicitly opt-in and were not used for release validation.
