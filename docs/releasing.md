# Release procedure and current state

## 0.4.2 published and verified on 2026-10-04 JST

[PyPI 0.4.2](https://pypi.org/project/collective-intelligence-overlay/0.4.2/),
[GitHub Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.4.2),
[actual machine-readable results](release-042-results.json) and the
[Japanese eleven-part report](release-042-report.ja.md) are complete.
The annotated tag is commit `abbc7bbf000dc6fe2eb43477f212156aa388f133`, object
`7dcd9d923fb86986caf0b41de0fa7331f46112a5`. Standard immutable-tag
[OIDC run 37133055121](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/37133055121)
passed candidate, ready and publish by restoring the same original pair. No
publication rebuild, moved tag, skip-existing or 0.4.1 recovery exception was used.

Actual PyPI files match the study/native candidate hashes. Fresh Windows
CPython 3.12.14/3.13.15/3.14.7 core/agents/model/Ollama installations pass all
twelve root-inclusive advisory/license/SBOM checks. Per interpreter, installed
agents unit 352, model SDK 1, Ollama SDK 5 and rebuilt-sdist 353 cases pass with
zero failures/errors/skips. A separate normal no-cache/no-config installation
matches all 86 package files and passes the real PostgreSQL/OPA/MCP/A2A
three-process demo: ACCEPT, 117.00, REQUALIFY after environment change and REJECT
after dependency withdrawal. These checks do not repeat actual model inference.

All ten public Release assets were downloaded and their bytes/sizes checked.
The frozen 298,576,015-byte research archive has SHA256
`c3698feb03ef32bc06fc5ad6ba25b3c1c9e7383880c8ab53aadcc07f5cd96a24`.
The separate `cio-042-postpublication-v4.zip` has SHA256
`5402b18d40640929d08969f9d82b4b9eada8fb75d45f91c79e2983a554d5f21c`.
Its three unuploaded metadata-export stops and corrected diagnostic are retained;
the final copy passed the targeted privacy/hash/JSON checks. This is not a complete
external privacy audit. The downloaded research archive was independently
extracted and verify/analyze recomputed with sockets blocked: all nine arms/669
model observations and the published analysis agree, with no new inference.
The prepublication snapshot remains in the immutable tag and
[its original record](release-042-prepublication.json); subsequent results live
on main without changing the tag, archive or distribution bytes.

The standard `v0.4.2` selector requires `docs/release-042.json` with the exact
candidate run, source commit/tree, wheel/sdist hashes and original complete gate
hash. It must authenticate the successful main workflow, twelve native profiles,
mixed Python and four cross readers before restoring that same pair. Missing or
rejected proof stops selection rather than rebuilding at the tag. The selected
version-specific manifest is passed to both candidate and ready; the separate
`publish_existing_tag` exception remains confined to the pinned 0.4.1 declaration.
The 0.4.2 native fault profile is included in validation provenance, and installed
wheel inspection requires migration 0022. The affected selector/proof-byte
checks passed 37 cases locally. The final original full gate
[37126141569](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/37126141569)
passed all twelve native profiles, mixed Python, four cross readers and ready.
The original 3,819 report files and unchanged wheel/sdist pair were retrieved and
verified against the gate. Its exact source is
`9cdcb6b4fef53aa0bfcdecc2d2fa5c272de37ad2`; documentation-only descendants retain
the same packaged and validation sources. The earlier preregistration gate
remains separately preserved and is not relabelled as this later gate.

`docs/release-042.json` now selects that authenticated final candidate. Independent
confirmation is complete: all nine E/M/C arms and 669 dispatched model
observations have verified offline, with zero observed C-minus-M final quality
difference and insufficient sensitivity/precision. See [the audit](audit-042.md)
and [bilingual study results](accumulation-042.md). The completed publication and
actual-index checks above are separate from the frozen prepublication evidence.
Negative or limited-power results are publishable; missing required implementation,
provenance or native checks are not a completed release.

## 0.4.1 published and verified on 2026-10-02

[PyPI 0.4.1](https://pypi.org/project/collective-intelligence-overlay/0.4.1/),
[GitHub Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.4.1)
and [actual numerical/provenance results](release-041-results.json) are complete.
The immutable annotated tag remains `bda9e16faeb536b705fd0659e8ca3469941d9f1e`
(object `5e8fd5525db52acaa0d93cea9845e3a232672ca9`). Actual OIDC publication is
[36987219345](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36987219345),
whose separately recorded engine is `91f9a802b50ef81e8cda77ceb89d12ee63e1f772`.
The earlier tag run failed before publication; the first recovery run
[36986961717](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36986961717)
passed candidate/ready but inherited skipped native dependency state and skipped
publish. The successful recovery requires explicit successful candidate, ready
and quick jobs. Neither attempt changed the tag, package or original full gate.

Actual PyPI metadata and downloaded bytes match the original measured pair:

| File | SHA256 |
| --- | --- |
| `collective_intelligence_overlay-0.4.1-py3-none-any.whl` | `2455fcab88a1dc732372b9a5c7c0eb7d16d3661b6bbf76e853ab8d03d52a0fb9` |
| `collective_intelligence_overlay-0.4.1.tar.gz` | `0262c0b53c936b4e08173c2340539e86e101bff4f383f4fef2aa0ee8913f2a99` |

Fresh normal no-cache/no-config PyPI installs on Windows CPython
3.12.14/3.13.15/3.14.7 pass 113 agents unit, one model SDK, five Ollama SDK and
114 rebuilt-sdist cases per interpreter, with zero failures/errors/skips. Twelve
separate installed core/agents/model/Ollama environments include the published
root in advisory audits and pass license review/SBOM generation. The first 3.12
resolver could not see the new version; its original log is retained and the
fresh same-condition v2 succeeds. Its exact index edge cause remains unproven.
A separate normal PyPI installation matches all 85 package files and passes the
real PostgreSQL/OPA/MCP/A2A three-process reference demo. These postpublication
checks do not rerun the full native matrix or model experiment.

All ten Release assets were downloaded from their public URLs and match their
recorded SHA256, including the three raw/failure/native-publication ZIPs,
original wheel/sdist, licenses/provenance, collection manifest and checksums.
There are 11,568 retained original file copies, 359 transformed unsigned metadata
files and zero omitted failure records; copies and nested receipts are not
independent samples. No weights, private keys or operator configs are published.
[The Japanese nine-part report](release-041-report.ja.md) records the zero primary
contrast at a ceiling and wider scientific/operational limits.

## 0.4.1 milestone and immutable publication procedure

Ordinary main pushes and pull requests run lightweight formatting, typing,
documentation and focused local-boundary tests. Dispatch `workflow.yml` with
`validation_scope=representative`, `verify_pypi=false` for the Linux/native
checkpoint, and with `validation_scope=full`, `verify_pypi=false` after freezing
the publication candidate. Full validation builds one wheel/sdist pair and
requires all twelve declared native profiles, installed optional-provider scopes,
actual PostgreSQL/OPA/A2A/MCP tests, proxy supply-chain/source review, mixed Python,
cross-native signature/artifact readers and an actual installed legacy upgrade.
Hosted CI does not run Ollama or download model weights.

The complete run retains candidate source/tree, lock, workflow/gate source and
toolchain pins, original artifact hashes, and a hash-bound `release-gate` of all
original reports. [The completed full run](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36973489591)
passed all required gates. `docs/release-041.json` records its trusted main run ID,
source commit/tree, wheel/sdist hashes and gate file SHA256. The tag publication
requires the original successful repository/workflow/main run with all twelve
native jobs and four cross readers completed. It restores the unchanged bytes
and original evidence, compares all report hashes and rechecks the matrix. An
altered pin, workflow/gate file, packaged source/README, missing report or failed
original run refuses publication. It does not rerun identical native workloads
at the tag. The first immutable-tag run
[36984866375](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36984866375)
stopped in ready: its depth-one checkout lacked the candidate ancestor required
by `git merge-base`. Candidate validation passed, but the publisher never ran.
The tag object and its sources remain unchanged.

The narrowly declared recovery input `publish_existing_tag=true` on trusted main
uses the existing workflow and `pypi` OIDC environment. Require
`validation_scope=full`, `production_protocols=false`, `verify_pypi=false` and
either the declared candidate run ID or an empty candidate input. It fetches the
complete pinned tag history, executes the original package/native gate code on
that unchanged tag, and restores all original report bytes. A separate checkout
records the actual dispatch workflow commit/tree and workflow/selector/declaration
hashes in `publication-resume-provenance.json`; it does not relabel the changed
publication engine as original native validation. The selector verifies live
GitHub run/tag identity, refuses an already published version, and binds the same
candidate and gate. No tag movement, rebuild, model inference, repeated native
workload or protection/environment setting change is involved. Other manual
validation runs still do not publish. This explicit exception applies only to
the pinned 0.4.1 declaration in `.github/publication-resume-041.json`; historical
tag-only publication behavior below describes those historical releases.

Proxy Go module/build caches use explicit OS/architecture/toolchain/source-pin
keys. Every restored graph still receives `go mod verify`, native build and fresh
license/vulnerability/SBOM checks. Cache presence is not evidence of passing.
Actual PyPI file hashes and cache-disabled dependency installation are checked
after publication. Scientific results are recorded separately from package
gates: a negative, ceiling or statistically inconclusive result is publishable.
The historical 0.4.0 formal report and acceptance logic below remain unchanged
for that version; they are not relabeled evidence for the new artifact.

## 0.4.0 candidate validation and immutable publication

Before publication, dispatch this same `workflow.yml` with `production_protocols=true`.
It builds one pair and runs all native gates, an installed Linux formal soak and
five sequential isolated matched pairs. Native PostgreSQL permits actual server
PID/resource sampling; the runner is a trusted test operator and each peer uses a
restricted runtime role. Reports exclude private homes and backup secrets.
The ready job rechecks the original DSSE, outcomes, resource units, faults,
assembly/header hashes and notices. An incomplete acceptance register still refuses
publication even when individual protocols pass.

After inspecting all actual gates, record `docs/release-040.json` with the original
`candidate_run_id` (decimal string), `source_commit`, exact `artifacts` object, and
`production_manifest_sha256` for that run's `reports-production/file-manifest.json`.
Update the acceptance register with actual observed evidence. These operational
records are outside the package artifacts. Do not change packaged sources, README,
metadata or licenses after fixing the pair.

If external tests or operational records change after that run, dispatch with its
`candidate_run_id`, `production_protocols=false`, and `verify_pypi=false` before
publication. This restores the original formal reports and reruns all native gates
against the original pair without querying an unpublished PyPI version. The ready
job still reassesses the originals, matches their fixed driver sources, and requires
the complete prepublication register. This option does not publish or waive a gate.

The `v0.4.0` tag requires that manifest. Its job downloads the original pair and
formal reports, checks the run's repository/main provenance and commit ancestry,
compares every wheel/sdist package file and the packaged README/metadata/licenses
with the tag, reruns all native gates and reassesses the retained formal reports.
Changed or added package files, altered archives or missing/changed originals fail
closed. It does not build a replacement publication pair. OIDC and the protected
`pypi` environment remain confined to the existing tag-only publish job.
After publication, dispatch with `candidate_run_id` and the defaults
`production_protocols=false` and `verify_pypi=true` to retain the cache-disabled actual-PyPI
verification path. See the [official workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
and [artifact download requirements](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts).

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

Publication occurred 2026-10-01 20:29 UTC / 2026-10-02 05:29 JST.

| Asset | SHA256 |
| --- | --- |
| `collective_intelligence_overlay-0.4.0-py3-none-any.whl` | `33898a964443c5276853dc15069247ff8642012332c980d085f9fa9a4faf11d7` |
| `collective_intelligence_overlay-0.4.0.tar.gz` | `965f848ed12950d0a8cba26e6deb1594d8ce98437022fc9dd5dff0f7e860f8be` |
| `collective-intelligence-overlay-0.4.0-evidence.zip` | `1135a9e487340279ee56a4e4edf11f32869ee88d8901a3078c5fac352307674d` |

## 0.3.2 published and verified on 2026-09-30

Release commit `b172c0d0ef208ede4ae3a663a158f1713d7f49a0`, immutable annotated
tag `v0.3.2`, passed all 12 native source/installed gates, four shared-artifact
readers, mixed-Python HTTP and final report/hash validation in
[tag CI / OIDC publication, attempt 2](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36705746853).
The official PyPA job published the original pair to
[PyPI](https://pypi.org/project/collective-intelligence-overlay/0.3.2/).
Actual PyPI downloads were checked byte-for-byte against that original candidate.

The first tag attempt had two Mac Intel / CPython 3.14.7 source failures;
their causes remain unestablished. The same immutable commit, original candidate,
test inputs and deadlines passed the failed-job retry. The other 11 successful
native jobs were reused, not reexecuted. Original failures and the completed
representative 100k stress results are retained in [validation](validation.md).

[Actual-index native verification](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36716542836)
passed against this same release pair on all 12 identities. Each passed 291 source,
290 installed agents, one model and 41 rebuilt-sdist tests, plus core smoke and
actual child/backend patch/CPU checks, with zero mandatory failures/errors/skips.
All 36 installed profiles passed published-root audits, reviewed licensing and
SBOM; four readers, mixed HTTP and final report validation passed. A manual run
cannot publish and its publish job was skipped.

The [GitHub Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.3.2)
attaches the exact PyPI wheel/sdist and 641 selected sanitized reports with a
report-byte hash manifest. Archive SHA-256 is
`b02a97c07915d62657b148766818d65fe5c4c52b4e136380f840c5058c259a1b`;
all three public asset digests match the local verified files. This patch contains
no v0.4.0 production features. Paid inference and independent external audit were not run.

Published SHA-256 values:

```text
cc4086d5e27cbdc1d13d2d79b7438e4c787cea208b9e321b8fc0fcbc4e279ae9  collective_intelligence_overlay-0.3.2-py3-none-any.whl
1baf14abad570f7f5e209af23c3c29252ab2932d19843414cb64dd02c045773d  collective_intelligence_overlay-0.3.2.tar.gz
```

One Linux build fixes the original wheel/sdist hashes.
All 12 native OS/CPU/patch/full-scope jobs must pass source, real services/E2E,
core/agents/model normal installation, rebuilt sdist and supply-chain reports.
The manifest controls matrix/report/docs identities; each Mac CPU has separate
reports. Four installed native readers separately verify shared golden artifacts
and new signatures from all installed producers; no cross-runner public ports are
opened. Existing mixed-Python actual HTTP peers stay mandatory. Mac/Windows always
stop/remove only the temporary PostgreSQL cluster whose ownership marker matches.

Ready rejects absent, duplicate, wrong-interpreter/CPU, changed-hash or skipped
reports. Publish remains a single official PyPA/OIDC job in environment `pypi`,
only on a matching tag after every required gate. Do not substitute rebuilt Mac
wheels for the fixed candidate. After publication, actual cache-disabled PyPI
installs and major regressions are required on both native Mac CPUs and representative
Linux/Windows, with hashes compared to this same pair. Do not start v0.4.0 features
until 0.3.2's safety gates pass; publication order remains 0.3.2 then 0.4.0.

The actual-index run was dispatched with:

```sh
gh workflow run workflow.yml --ref main -f candidate_run_id=36705746853
```

The manual run restores that run's `candidate-distributions`, downloads the actual
published wheel/sdist and checks both hashes before proceeding. Each native job
then uses cache-disabled normal PyPI resolution (`--from-pypi`), retaining root
package audit and interpreter/CPU checks. A manual run cannot publish. Use the
actual immutable tag run ID; a failed or different candidate must not substitute
for the published pair.

## 0.3.1 published on 2026-09-30

Release commit `e7e245920be3687eebb4b0a0817d60a82ed2c1b9`, immutable annotated
tag `v0.3.1`, passed [main CI](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36672022262)
and [tag CI / official PyPA OIDC publication](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/36674642405).
Both runs passed Linux/Windows × CPython 3.12.14/3.13.15/3.14.7: each pair passed
258 frozen source tests, 257 installed agents tests, one separate mocked-model
test and 31 rebuilt-sdist tests, plus core version/import/CLI/resources.
There were zero mandatory failures, errors and skips; minimum/latest mixed
installed peers passed both directions. Lint/format/type, docs, strict twine,
actual per-runtime vulnerability/license/SBOM and final hash gates passed.
See [validation](validation.md) and [exact runtime scope](compatibility.md).

[Actual PyPI 0.3.1](https://pypi.org/project/collective-intelligence-overlay/0.3.1/)
was published by one tag job at 06:09 UTC. Actual index metadata and downloaded
bytes both match the original tested wheel and sdist:

| File | SHA-256 |
| --- | --- |
| `collective_intelligence_overlay-0.3.1-py3-none-any.whl` | `caa5acb140e5e2a09067ee4fa4e074e019fb02a68dd8a59a70ff9e973a6f9a41` |
| `collective_intelligence_overlay-0.3.1.tar.gz` | `87a6a1e2a90987831194680f3d26dcf60dc4e6a8b54d2e76b5b95b43d63a54a0` |

Fresh cache-disabled actual-PyPI installs passed core/agents/model profiles on
CPython 3.13.15, with 30 agents unit tests, one model test, 31 rebuilt-sdist tests,
31/60/64 resolved distributions and zero known vulnerabilities, including the
published first-party root. CPython 3.12.14 and 3.14.7 each passed 257 full installed
agents tests in 1,060.63/1,060.79 seconds, one separate model test and 31 rebuilt
sdist tests, with core import/CLI/resources. Every suite had zero failures/errors/
skips. All nine actual profiles passed license/audit/SBOM, with no skipped root.
Exact post-publication time/dependency/runtime tables are in [compatibility](compatibility.md).
The [GitHub Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.3.1)
attaches both exact PyPI files and `collective-intelligence-overlay-0.3.1-evidence.zip`
(174 selected reports; SHA-256 `9d7b77878001a0c5d17091fb65922d3087fa901afdba6cd1b4a4d3f7f11bb963`).
The evidence archive has a sanitized-report hash manifest; local user prefixes are
redacted and raw logs/private configs/keys/credentials are omitted.
The first 3.13.15 install attempt briefly could not see the newly published index
version. Its failure log was retained; a new clean ordinary-index attempt passed.
No cached wheel, alternate index, dependency bypass or tag movement was used.

`candidate` builds one wheel/sdist pair on explicit CPython 3.12.14, runs strict
twine and records SHA-256. Every OS/minor downloads those files. The common
`scripts/ci_validate.py` runs frozen full source/service tests, lint/format/type,
docs and supply-chain gates, then normal-resolution independent core, agents and
agents/model installed checks. Each sdist rebuild uses an observed explicit
PEP 517 interpreter; its rebuilt wheel is never substituted for the publish file.
Windows starts a private loopback cluster from the runner's PostgreSQL binaries;
Linux uses PostgreSQL 16.15; Windows CI used native PostgreSQL 17.11. OPA is 1.21.0.
Required service tests cannot be skipped.

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
Release verification requires fresh actual-PyPI core/agents/model installs on every stable
minor, minimum/latest installed audit regressions, and actual downloaded wheel/
sdist hashes matching the tested candidate. Historical release results below are
not evidence for this release.

The post-publication verifier uses the actual index with normal resolution. Use
`artifacts.json` downloaded from the tag CI candidate, or the release evidence
archive's `tag-36674642405/candidate/artifacts.json`. Do not generate a different
manifest by rebuilding the published version from later main documentation.
Place that original manifest at `.local/candidate/artifacts.json` for this example:

```sh
uv run python scripts/fetch_pypi_release.py --version 0.3.1 --hash-file .local/candidate/artifacts.json --output .local/pypi-031/dist --report .local/pypi-031/download.json
uv run python scripts/check_package.py --from-pypi --python 3.14.7 --dist-dir .local/pypi-031/dist --hash-file .local/candidate/artifacts.json --test-scope full --report .local/pypi-031/package-3.14.7.json --supply-chain-dir .local/pypi-031/supply-3.14.7
```

Configure real services for `full`; repeat on the minimum patch and run smoke/unit
checks on every other stable minor. `--from-pypi` passes `--no-cache --no-config`
and the explicit PyPI default index to independent core/agents/model installations.
The audit includes the now-published root. The same interpreter guard checks every
CLI, pytest, demo and PEP 517 phase. This verifier and final result documentation
are added to main after publication, without changing the release tag or files.

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
