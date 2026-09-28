# Release procedure and current state

Requested destination: `kadubon/collective-intelligence-overlay`, initial version
`0.1.0`, PyPI distribution `collective-intelligence-overlay`.

Published and verified on 2026-09-28:

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
successful Linux integration/E2E/package/security/docs checks and Windows unit/package
checks. Tags must equal `v<pyproject version>` and their commit must be in `main`.
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
license/vulnerability/SBOM checks; commit/push; verify CI; create `v0.1.0`; verify tag
workflow and PyPI; install from the actual index in a fresh environment; then create
GitHub Release notes describing scope, compatibility and unverified boundaries, and
attach the exact published distributions and supply-chain reports.

If name ownership conflicts, OIDC is rejected or environment approval is required,
stop that operation and record the exact error here. Never rename the project,
disable protections, request an API token or overwrite an existing distribution.

Verified installation (activate a Python 3.12 virtual environment first):

```sh
uv pip install --index-url https://pypi.org/simple 'collective-intelligence-overlay[agents]==0.1.0'
```

The optional `model` extra supplies the provider adapter; actual paid calls remain
explicitly opt-in and were not used for release validation.
