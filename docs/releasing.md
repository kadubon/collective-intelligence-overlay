# Release procedure and current state

Requested destination: `kadubon/collective-intelligence-overlay`, initial version
`0.1.0`, PyPI distribution `collective-intelligence-overlay`.

Current checkpoint: GitHub main CI passed for commit `29d5279`:
[verified run](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36361806108).
The `pypi` GitHub environment exists. Final hardening is being checked before tagging;
tag, GitHub Release and PyPI publication are not yet confirmed. No publication is
inferred from a Pending Publisher configuration.

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

After confirmed publication, the install form is:

```sh
uv pip install 'collective-intelligence-overlay[agents]==0.1.0'
```

This command's availability must be checked against PyPI before claiming it succeeds.
