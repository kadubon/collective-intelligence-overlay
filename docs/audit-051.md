# 0.5.1 stabilization audit

This is a finite maintainer review, not an independent security audit or a claim
of complete safety. The five 0.5.0 projections and existing execution authority
remain the scope. No inference, model pull or scientific rerun was performed.

Publication and declared verification are complete. See [PyPI 0.5.1](https://pypi.org/project/collective-intelligence-overlay/0.5.1/),
[GitHub Release](https://github.com/kadubon/collective-intelligence-overlay/releases/tag/v0.5.1),
[actual results](release-051-results.json), [native results](release-051-native-results.json)
and [Japanese report](release-051-report.ja.md). The Release publication time was
2026-10-04 19:24:57 UTC (2026-10-05 04:24:57 JST). These results do not turn the
finite review into an external audit or establish complete safety.

Baseline: clean `main` at `d39ac26a342dc0e040e2368e5e364f534c08328c`;
published 0.5.0 tag commit `1c7e3527dc48580f92e70f2a3752d54e970808d4`.
The source/package/test/workflow trees match that tag; later publication Docs are
separate from its immutable metadata. Work began on `stabilization/051-audit`.
The published wheel SHA256 is
`ffa714868281925c500803cbf6762bb130c28e832ab68c70c8aa0f38e917690e`,
and sdist SHA256 is
`916b0d16440b7888341a59ca452eb587030964da6d8de56f61cd59d8ff0ce752`.
The original tag, distributions, native gate and raw failure evidence are retained.

## Scope and risk map

| Entry point | Trust boundary / persistence | Effects / public contract | Verification |
| --- | --- | --- | --- |
| `snapshot_from_material`, CLI input | Operator-selected finite file; signed bytes versus unsigned projections; nested defaults | No fetch or execution; original refs and missing clocks retained | Bounds, DSSE, source conflicts, malformed input and independent fixture differential |
| `read_lifecycle_page`, `export_originals` | Host caller versus Store owner; records/Decisions, fixed prefix and revision | Read-only, bounded owner queries and exact original payloads | Dedicated PostgreSQL/OPA; transaction state, auth-before-query and pagination |
| Lifecycle/Contribution/Residual/Growth/Handoff | Historical observation versus current receiver admission; fixed scope/policy/time | No execution, settlement, quality upgrade or global coverage | Finite property/regression tests, cost and clock oracles |
| `assess_stock` | Explicit host authorization; existing qualification/budget paths | Writes only through existing APIs; bounded exact targets | Invalid-input preflight and real Store state checks |
| Executor, A2A/MCP, recovery/backup | Operator bindings, caller/owner, provider IDs and signed evidence | UNKNOWN/held and physical quiescence remain distinct | Existing fault suites and finite official-SDK/service regressions |
| Packaging/Docs/release | Source-bound callable identity; installed APIs; protected OIDC | Same import/CLI/wire/DB contracts; exact pair publication | Clean outside-checkout baseline/candidate, native matrix, hash-bound reuse |

## Review status

Pass 1: broad static review followed by risk-directed finite reproductions is complete.
Focused baselines were saved before source edits.
Pass 2: finite review of fixes/refactors found and corrected two patch regressions:
UTF-16/32 input was unintentionally excluded, and a global Decision-ID uniqueness
check rejected a valid owner's basis. Their first failures are retained; supported
JSON encodings and source-order owner correlation now pass positive/negative cases.
No further broad redesign or repeated audit loop is part of this patch.
The first aggregate native run on `eda1599`,
[37200404588](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/37200404588),
completed with eleven successful native profiles and one dependency-transfer
failure before product tests. Its original attempt, reports and fixed distributions
are retained. No release gate or publication passed. The user then supplied an
additional review requiring a pre-actuation accounting correction; this source
candidate is excluded from publication. It was not cancelled or rerun; all 3,482
original files remain retained separately. The revised source's native gate is
verified below; publication and postpublication verification are complete.

Findings below are confirmed reproductions unless explicitly marked otherwise.
Private diagnostic inputs and raw logs are retained under `.local/audit-051*`;
the published software evidence archive contains sanitized, bounded evidence.

| ID | Priority / class | Location and condition | Observed impact / expected correction | State |
| --- | --- | --- | --- | --- |
| L051-01 | P2 bug | `lifecycle._gross_stock_changes`: equal clocks with one missing sequence | Sorting invented additions/loss/readmissions; gross values now stay unknown | fixed; failing regression verified |
| L051-02 | P2 bug | `observe_growth`: execution/formation/work has foreign receiver, scope or policy | Wrong period count/cost attribution; match available exact coordinates | fixed; failing regression verified |
| L051-03 | P2 bug | `original_record_metadata`, contribution/expiry/gross: absent nested purpose or `valid_until` | Decoder defaults appeared observed; mark purpose absence, keep unknown reuse/validity and null period/gross | fixed; original bytes retained |
| L051-04 | P2 bug | `observe_contributions`: same owner/caller/invocation but contradictory receipt, or same owner/ID different caller | Silent dedup lost contradictions or distinct uses; full key independent, contradictory same key rejected | fixed; original oracle correction retained |
| L051-05 | P2 bug | `build_handoff`: foreign basis, colliding owner IDs, incompatible reuse receipt | Misattributes state/transition; source-order exact basis owner/request correlation and receipt coordinates | fixed; positive and negative collisions verified |
| L051-06 | P2 bug | `assess_stock`: duplicate exact targets/differing arguments or >32 requests | Qualification ran before rejection; entire bounded set is checked before effects | fixed; actual PostgreSQL state regression passed |
| J051-01 | P2 operability | `lifecycle_cli._file`, `snapshot_from_material`: excessive nesting, duplicate keys/nonfinite constants | No depth preflight / ambiguous JSON accepted; bounded lexical/tree checks before decode/serialization | fixed; UTF-8/16/32 retained |
| E051-01 | P2 operability | `adapters.a2a_service.invoke`: returns at first SDK yield | Iterator/client not closed; exhaust one response and close on all exits, retain JSON null | fixed; official SDK ASGI regression |
| E051-02 | P2 bug / accounting | `Registry.execute` / `Executor.invoke`: inner admission denies after durable dispatch but before actuator entry | The live process knows the actuator was not entered, but UNKNOWN/held strands allowance; narrow private origin proof and fenced atomic release | fixed in `958e1e7`; public-wheel first failure and real PostgreSQL/OPA regression verified |
| D051-01 | P3 documentation | `SECURITY.md`: support targets latest 0.1.x | Stale support description; latest published 0.5.x maintenance without SLA | fixed; Docs review |
| D051-02 | P3 documentation | Security/configuration/API/release description: execution binding scope and concurrency/resource limits | Clarify authenticated peer inspection, concurrency versus rate quotas, source identity and unmeasured availability; record superseded candidate without claiming publication | fixed; static Docs/configuration review, not a dynamic DoS or penetration test |
| R051-01 | P2 operability | Release selectors/package checks/profile stop at 0.5.0 | 051 could not reuse pair/load profile; inherit unchanged gates | fixed; focused regression passed |

Nested mutable models and `model_copy(update=...)` remain a **deferred trusted-host
consistency limitation**, not evidence of an unauthenticated remote attack.
Changing all legacy models or adding original-body persistence would exceed this
patch. The API reference requires validated original ingestion and prohibits
mutating typed original projections. No remote permission bypass was reproduced.
Legacy observations without scope/policy cannot attest unknown coordinates; known
subtotals/nonclaims remain, without inventing scope or zero cost.
The old Mac Intel/Python 3.14
receiptless positive-proof failure has preserved original logs; its cause remains
unestablished. Its exact anchored dispatch case ran once on current Windows 3.12.14
with real PG/OPA/A2A and passed; classification is **not_reproduced in that environment**,
not a diagnosis of Darwin 3.14. Later passes do not explain the old failure. Original
log SHA256 `d705391d29a38ebbbc8c850453b87ec7617e2bffe481b2eb8dde9feca2259ab2`
is retained. No timeout was increased and no retry loop was introduced.

## Compatibility boundary

Keep public API signatures, CLI/exit codes, JSON fields/enums, schema and digest
algorithms, DB migrations and runtime dependencies. `derivation_version=0.5.0`
denotes the projection contract and remains independent of package 0.5.1.
Source-bound registered operations/factories are not moved or reformatted.
Bug corrections intentionally change the rejected/misattributed/unknown cases
above. `aa68e32` implements the lifecycle fixes, `8b3ce38` the A2A lifetime fix,
and `3e67606` the finite second-review compatibility corrections.
`ddb5994` separately factors the duplicated exact DSSE read and historical key-state
tests from explicit material and Store ingestion. It preserves check/verify order,
original payload digest, missing metadata, unsigned-source handling and authority.
These are local projection helpers, not registered/factory source-bound operations.

The same explicit bundled fixture is compared with public 0.5.0 and before/after
refactor. Six schemas and eight API signatures match exactly. Views, contributions,
handoff, all original refs/IDs/clocks and costs match after excluding only derivative
Report `generated_at` (twelve explicitly recorded JSON paths). No original clock,
digest or source field is excluded. Canonical comparison SHA256 is
`138a0a9f81d403bb1acd8b6c5c5ae50571e56e41bf9466b7dc071dc05c5d389e`.

The static boundary was rebound to source `77db860` without rerunning that fixture.
The retained manifest SHA256 is
`6cd4b70077d281bb75ccb9d07697971d57cc945507e9270b98e917310edad5e4`:
nineteen public signatures, fourteen packaged schemas and unchanged migrations/
runtime dependencies were compared. Ninety of the old ninety-seven package files
are byte-identical; seven intentional changes, one new private JSON helper and
zero removed files are distinguished. Static comparison is separate from native
and actual-index evidence. The [verified software-evidence ZIP](https://github.com/kadubon/collective-intelligence-overlay/releases/download/v0.5.1/collective-intelligence-overlay-0.5.1-evidence.zip)
contains this static boundary at
`release-evidence/finite-audit/compatibility-boundary-v2.json`. Its original and
public SHA256 are both
`6cd4b70077d281bb75ccb9d07697971d57cc945507e9270b98e917310edad5e4`;
the original/public mappings remain explicit even when these bytes are unchanged.

## Executed focused evidence

Windows CPython 3.12.14, uv 0.12.19, dedicated PostgreSQL 16.15 loopback and OPA:

| Evidence | Actual result | Scope / limit |
| --- | --- | --- |
| Existing Lifecycle baseline | 43 pass, 0 fail/error/skip | Before source edits |
| Existing Store baseline | 10 pass, 0 fail/error/skip | Real PG/OPA |
| Public 0.5.0 against corrected bug regressions | 43 pass, 24 fail, 0 error/skip | Installed normally outside checkout; intentional differences |
| JSON first failures | 5 fail, 1 pass | Bounds/duplicate/nonfinite; retained |
| A2A lifetime first/fixed | 5 fail → 8 pass, 0 error/skip | Official SDK ASGI, model-free |
| Release integration baseline/first/fixed | 55 pass → 55 pass/19 fail → 74 pass | Version wiring only; no thresholds relaxed |
| Lifecycle/JSON/properties before refactor | 79 pass, 0 fail/error/skip | Five finite seeded properties plus existing finite endpoint property |
| Refactor after | 91 pass, 0 fail/error/skip | Same focused units plus 12 real Store tests |
| Second-review first/fixed | 5 fail/2 pass → 86 pass | Encoding/owner correlation corrections; final expanded collision cases 8 pass |
| Runtime current actual services | 8 pass, 0 fail/error/skip | Receiptless, delayed commits/barrier, standard A2A; no Darwin diagnosis |
| Actual read-only state | 12 Store cases pass | All registered Store tables unchanged: originals, budgets, held invocation/lease, admission/Decision and feed state |
| Pre-actuation public 0.5.0 first failures | 2 fail, 0 error/skip | Normally installed public package outside checkout; outer ACCEPT, inner REJECT/UNKNOWN, zero actuator calls, old UNKNOWN/held result |
| Pre-actuation corrected local installed wheel | 8 pass, 0 fail/error/skip | Fresh outside-checkout normal install; all 98 package files match wheel; real PG/OPA; preflight pair, not final native/PyPI bytes |
| Revised execution/recovery suites | 119 pass, 0 fail/error/skip | Seven real PG/OPA suites on `958e1e7`, including eight new cases; no native Darwin claim |

An initial caller regression incorrectly expected a conflict for a distinct caller.
The first failure is retained with its oracle correction; the separate public-wheel
run proves the corrected independent-use expectation fails on 0.5.0. A property
initially expected unwrapped Conflict, but Pydantic has always wrapped snapshot
validator errors as ValueError/ValidationError; its original failure and correction
are retained. Neither test correction is represented as a product fix.
The first revised seven-suite run retained 117 pass, one test-setup failure from
initializing the same owner's budget twice, and one skip because the local PG
tool prefix was omitted. Both setup/environment corrections and raw results are
retained; they are not product fixes. The completed 119-case run sets the WSL PG
tool prefix and has no failures, errors or skips.

## Final native and publication provenance

The revised local preflight wheel/sdist passed normal clean installations and
dependency/license/SBOM checks; these bytes are not the final CI candidate.
Frozen source `77db860ad5cfb5c0fc67befd8c5a267916527979` / tree
`a08d7facea20827024e59e9348e772946d184e2a` passed the complete
[native gate](release-051-native-results.json), bound by the [manifest](release-051.json).
All twelve native profiles, mixed Python, four actual cross readers and mandatory
checks passed. Each final profile has source969/installed agents957/model mock1/
Ollama mock11/rebuilt-sdist513 passes, no failures/errors/skips, and nineteen
required source/installed fault groups with unchanged numerical bounds.
These overlapping scopes are not additive; this is not formal soak approval.

The original gate SHA256
`0d5691a7507ada4cfa375e91ab70b2205b06e5b1370ef9008470dfc1b07cf4b6`
authenticates successful reports and wheel
`35da08b11de4fa7bd35fb517055f60edf8dd8b866de7a1b4005dcbc07a3c29e9` /
sdist `86326198bb82a5c7ef0afc27a739cb1bc337a8cb93c89dd13a13fc7af3695703`.
The canonical 3,842-file original manifest SHA256 is
`b83e89a46459c9243b2ca51015d32d56c71b41c6582d3b382a519d4f002c52d2`.
Gate JSON alone does not carry failed-attempt/authorization history; separately
retained provenance binds those records in the published software archive.

The initial attempt's 3,790 originals remain. Intel313 had source968 pass/one
fail/zero error/skip in 969 cases, with its installed phase unreached; its eight
new pre-actuation cases passed within that failed suite. Startup readiness failed
before application invocation, and cause remains undetermined. One explicitly
authorized targeted request was accepted at 2026-10-04 17:04:50.044071 UTC;
six actual target/dependent jobs succeeded: Intel313, four cross readers and ready.
No full-run rerun or second request was requested. A pass does not diagnose the
initial cause or historical Darwin314; no timeout/assertion was relaxed.

Fourteen initial successful jobs (eleven native, quick/candidate/mixed) retain
distinct original execution IDs and latest API bookkeeping IDs/attempt labels.
Their fifteen execution fields, 249 steps and original execution timestamps
match; original artifact IDs, digests and bytes remain bound separately. The
retained mapping SHA256 is
`5f367598129bca1c38526f42f7bb7847839725fd4a1964aa4de10d908ad8382e`.
This finite API/artifact proof does not establish GitHub internal copy mechanics
or absolute absence of hidden execution. The old eda run and its 3,482 originals
remain superseded, without retry.

[OIDC publication run 37226613301](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/37226613301)
passed candidate, ready and publish through the existing protected workflow.yml /
pypi path, restoring the pair and original gate without rebuilding or repeating
native work. The immutable annotated tag has object
`53f1e7bb47f6c5668bf029611e59554c0eb88477` and peeled publication commit
`7540ae5bd6150e95038d27b39b4f1c17ac808456`. Tag quick was skipped with no execution
steps; separate [main quick run 37226417161](https://github.com/kadubon/collective-intelligence-overlay/actions/runs/37226417161)
passed at that publication commit. Actual PyPI metadata and downloaded bytes
match the frozen candidate.

Completed outside-checkout actual-index verification used one Windows AMD64 /
CPython 3.12.14 patch with four profiles: core installation checks, agents 512
unit cases, agents-model 1 SDK mock plus 513 rebuilt-sdist cases and agents-ollama
11 SDK mocks. Reported tests had zero failures, errors and skips. Published-root-
inclusive advisory/license/SBOM checks completed for 31/64/67/66 distributions
respectively, with zero known advisory findings. The original global Python 3.13
orchestrator failure on missing piplicenses occurred before profile pytest;
its log and two partial core supply-chain files are retained separately from the
completed execution using existing locked development tools.

Fresh actual-package core 92, A2A lifetime 8, Store 12 and direct pre-actuation 8
cases passed separately, with zero failures, errors and skips. Four read-only
JSON CLI examples and the actual PostgreSQL/OPA service tutorial passed A ACCEPT,
B REJECT, two rows/`5.00` and post-withdrawal REJECT. All 98 installed files matched
the downloaded wheel; core optional SDK imports were blocked. No other-OS
actual-index full matrix was repeated, and overlapping counts are not additive.

All six Release assets were downloaded and verified against their original bytes,
sizes and SHA256. The [single software-evidence ZIP](https://github.com/kadubon/collective-intelligence-overlay/releases/download/v0.5.1/collective-intelligence-overlay-0.5.1-evidence.zip)
contains 4,073 verified members, is 31,969,754 bytes and has SHA256
`e4b39b061a152cd165a18c5dbbc883bfcfaba0725afb8e1e7a27d0fed1cd4443`.
Bounded failed native XML/runtime/log copies and original/public hash mappings
are included; original failed ZIPs and private human authorization transcripts
remain private. Signed envelopes are unchanged. Only the dedicated tutorial
PostgreSQL cluster was stopped, retaining data/logs and leaving other services
unchanged. No model inference/pull, research comparison, benchmark or long soak ran.

The compact per-finding evidence below supplements this existing ledger; full
JSON is in the single software-evidence archive with original/public hashes
distinguished. Local-v4 installed proof and focused/static fixed states are
separate from this actual publication and installation evidence.

## User-supplied prepublication review supplement

The supplied static review did not execute a PoC and its severity ratings are
review opinions. A finite maintainer reproduction on the frozen `eda1599` product
confirmed E051-02 with real PostgreSQL/OPA: outer ACCEPT, durable dispatch, inner
REJECT after withdrawal or UNKNOWN after source freshness loss, and operation
call count zero. The stronger two-case first-failure report is retained as
`preactuation-firstfail-v2.xml`; both fail because the result is UNKNOWN instead
of cancelled/released. The first six-case report also retains four passing safety
cases, including an entered parent's child denial and delayed dispatch DB threads.
The two primary cases also fail on the normally installed public 0.5.0 wheel,
independently of the frozen checkout. The correction commit is
`958e1e781b590c8f5957d375e3b65194d6c473e9`; its focused and installed regression
records remain separate from the later mandatory native and publication gate.

The correction preserves double admission and original dispatch history. A
private proof is produced only around inner admission after the exact dispatch
callback returned and before the actuator's first statement. Live DB ownership,
worker/fence, active unexpired lease, no prior receipt/actual and exact original
request/receipt are checked before fencing, returning allowance and signing a
cancelled overhead receipt in one transaction. Generic AdmissionDenied, entered
operations, child denial, crashes, cancelled awaits and lost ownership gain no
release authority. DB failure rolls back the disposition and receipt together.
Explicit owner new-attempt selection requires the persisted fenced release proof,
fresh observation and current admission; exact original-ID replay remains terminal.
No new public phase/state, schema, DB migration or runtime dependency is added.

The other observations are addressed by precise existing-boundary documentation:
request concurrency is not a rate or cumulative resource quota; allowed peers can
sustain inspection/authentication/storage work; function-source digests do not
attest all dependencies/globals/environment; owner critical-section serialization
has no measured high-load throughput guarantee. The existing host/DB/OPA/key/clock
TCB and absent external pentest, multi-organization key-management assurance and
long-running availability proof remain explicit. No authentication/signature bypass
or concrete PyPI metadata defect was reproduced by that static review. The current
packaged/tagged README retains the prepublication snapshot; the current main
README identifies published 0.5.1 and links actual publication records separately.

## Per-finding preserved evidence (bounded appendix)

This supplements the existing finding table; it is not a second audit ledger. Original ten findings' confirmation baseline is `d39ac26a342dc0e040e2368e5e364f534c08328c` (public 0.5.0 tag commit `1c7e3527dc48580f92e70f2a3752d54e970808d4`); fixed source is `77db860ad5cfb5c0fc67befd8c5a267916527979`. Class, priority, conditions, trust boundary, correction and state remain in the table above.

`L` = `src/collective_intelligence_overlay/lifecycle.py`. Test identifiers below use exact pytest NodeID syntax. One or two cases are representative; counts cover the full selected case set in the preserved mapping, not only the displayed representatives. Counts are pass/fail/error/skip and are not additive across overlapping runs.

| ID | Fixed file/symbol; correction commit | Representative preserved NodeIDs | Original → fixed selected counts |
| --- | --- | --- | --- |
| L051-01 | `L:_gross_stock_changes`; `aa68e32` | `tests/unit/test_lifecycle.py::test_same_clock_partially_sequenced_decisions_keep_gross_unknown[0]`; `tests/unit/test_lifecycle.py::test_same_clock_partially_sequenced_decisions_keep_gross_unknown[1]` | 0/2/0/0 → 2/0/0/0 |
| L051-02 | `L:observe_growth`; `aa68e32` | `tests/unit/test_lifecycle.py::test_growth_service_counts_only_fixed_receiver_and_policy_receipts[caller]`; `tests/unit/test_lifecycle.py::test_growth_work_costs_require_matching_nested_coordinates[scope]` | 0/7/0/0 → 7/0/0/0 |
| L051-03 | `L:original_record_metadata`, `observe_contributions`, expiry/gross projections; `aa68e32` | `tests/unit/test_lifecycle.py::test_missing_nested_execution_purpose_is_not_observed_reuse`; `tests/unit/test_lifecycle.py::test_missing_decision_validity_is_not_reported_as_observed_expiry` | 0/3/0/0 → 3/0/0/0 |
| L051-04 | `L:observe_contributions`; `aa68e32` | `tests/unit/test_lifecycle.py::test_same_invocation_id_for_distinct_callers_remains_two_uses`; `tests/unit/test_lifecycle.py::test_same_invocation_conflicting_receipt_identity_is_never_silently_deduplicated[policy_digest]` | 0/6/0/0 → 6/0/0/0 |
| L051-05 | `L:build_handoff`; `aa68e32`, `3e67606` | `tests/unit/test_lifecycle.py::test_assessed_handoff_requires_basis_owner_to_be_receiver`; `tests/unit/test_lifecycle.py::test_reuse_account_handoff_does_not_use_incompatible_receipt[scope]` | 0/4/0/0 → 5/0/0/0; collision expanded from 1 to 2 cases, final 8-way collision run: 8/0/0/0 |
| L051-06 | `L:assess_stock`; `aa68e32` | `tests/unit/test_lifecycle.py::test_assessment_duplicate_stock_targets_fail_before_any_delegation`; `tests/integration/test_lifecycle_store.py::test_invalid_assessment_targets_reject_before_actual_qualification_writes` | unit 0/2/0/0 → 2/0/0/0; actual Store invalid-input case fixed-only: 1/0/0/0 |
| J051-01 | `_lifecycle_json.py:check_json_bytes/load_json/validate_json_tree`, `lifecycle_cli.py:_file`, material/Store ingestion; `aa68e32`, `3e67606` | `tests/unit/test_lifecycle_json.py::test_json_duplicate_keys_are_rejected`; `tests/unit/test_lifecycle_json.py::test_valid_json_byte_encodings_keep_existing_decode_contract[utf-16]` | initial JSON 0/5/0/0 → 5/0/0/0; encoding patch regression 1/4/0/0 → 5/0/0/0 |
| E051-01 | `adapters/a2a_service.py:invoke`; `8b3ce38` | `tests/integration/test_a2a_service_lifetime.py::test_standard_sdk_exchange_owns_request_and_client_until_return[data]`; `tests/integration/test_a2a_service_lifetime.py::test_standard_sdk_exchange_owns_request_and_client_until_return[null]` | 0/5/0/0 → 5/0/0/0; added client cases fixed-only: 3/0/0/0 |
| D051-01 | `SECURITY.md`, maintenance paragraph; `a858a4f` | Static Git blobs: baseline “latest 0.1.x” → fixed “latest published 0.5.x”; no SLA | Static before/after only; no failing/fixed JUnit executed |
| R051-01 | `scripts/release_candidate.py:select`, `release_gate.py:check_reuse`, `native_fault_profile.py:load`, package metadata; `d49066e` | `tests/unit/test_release_candidate.py::test_standard_tag_reuses_its_own_trusted_complete_candidate[0.5.1]`; `tests/unit/test_native_fault_profile.py::test_version_profiles_retain_identical_short_fault_requirements[0.5.1]` | 0/19/0/0 → 19/0/0/0; finite selector/profile checks, not publication |
| E051-02 | `bindings.py:_PreActuationDenied/Registry.execute`, `invocations.py:InvocationStore._finish_pre_actuation_denial/Executor.invoke`, `steps.py:Steps._choice`; `958e1e7` | `tests/integration/test_invocations.py::test_inner_admission_denial_before_actuator_releases_once[withdrawal]`; `tests/integration/test_invocations.py::test_child_inner_gate_proof_cannot_refund_entered_parent` | primary 0/2/0/0 → 2/0/0/0; six other cases fixed-only: 6/0/0/0 |
| D051-02 | `docs/security.md`, `docs/configuration.md`; existing `config.py:Config`, `peer.py:PeerService.handle`; `5212d7b` | Static Git/Config/source: registered binding execution versus authenticated submit; existing owner/caller concurrency defaults 16/4 | Static before/after only; no failing/fixed JUnit executed |

Original Lifecycle first-fail selections are from `all-public050-before-v1.xml` (normally installed public 0.5.0 outside checkout; 43 pass, 24 fail, no errors/skips), fixed selections from `second-review-fixed-v1.xml`. L051-05 additionally uses `handoff-correlation-fixed-v2.xml`; L051-06 uses `store-expanded-v1.xml`. J051-01 uses `json-firstfail-v1.xml`, `json-fixed-v3.xml` and `second-review-firstfail-v1.xml`; E051-01 uses `runtime-a2a-lifetime-firstfail-v1.xml`/`fixed-v1.xml`; R051-01 uses `release-gates-before-integration-v1.xml`/`after-integration-v1.xml`.

The full `audit-finding-evidence-appendix-v2.json` is in the [single verified Release software-evidence ZIP](https://github.com/kadubon/collective-intelligence-overlay/releases/download/v0.5.1/collective-intelligence-overlay-0.5.1-evidence.zip) at `release-evidence/finite-audit/finding-evidence-mapping-v2.json`. It contains full commits, file/symbol lines and source hashes, exact selected NodeIDs, original XML hashes/counts, trust scopes and limits. Original JSON SHA-256: `4d19a889b42f634b6ea1865e83970d72c11f47ec7305b078353906190aebc6c8`; separately recorded public derivative SHA-256: `4d19a889b42f634b6ea1865e83970d72c11f47ec7305b078353906190aebc6c8`. These particular bytes are unchanged; original/public labels remain separate. No second full public Markdown ledger is added.

Evidence limits: D051-01 is directly verified text, with no implementation-mirroring test. Missing `request.purpose`, material-depth/signed-duplicate JSON subcases, the actual Store preflight case, three added A2A client cases and package/upgrade additions have fixed-only/supporting evidence, not separately archived pre-fix failures. Their parent defects have the first-fail evidence listed above; absent failures are not manufactured.

Oracle limits: the original distinct-caller test incorrectly expected Conflict; DB identity includes caller. Its raw failure is retained and excluded from product-defect proof; the corrected two-use public-wheel case fails. The property `test_same_source_changed_content_is_rejected` originally expected unwrapped Conflict although Pydantic already wrapped it; its oracle correction is not a product exception change. Both original failed XMLs and correction explanations remain in the mapping.

Deferred/not-reproduced limits remain separate: mutable nested models/`model_copy` and manually reordered views require trusted-host consistency; old Mac Intel/3.14 receiptless failure cause is unestablished, and one current Windows/3.12 service pass is only `not_reproduced` there. Focused/static `fixed` status does not attest final native gates, actual OIDC publication, fresh PyPI installs or an independent external audit.

E051-02 and D051-02 confirmation is `eda15996c8451f06d88399d13d3ddb3cfe972b90`; current source tree is `a08d7facea20827024e59e9348e772946d184e2a`. The explicit runtime fix and actual documentation correction commits are in their rows and the mapping. Current source/test hash rebinding is not a test rerun or native/publication proof.

E051-02 focused17 contains seven new cases and ten supporting cases; the eighth actual child-proof case was added later. Its explicit completed runtime XML/log contains all eight new cases within the bounded 119-pass seven-suite run. Primary two archived failures establish the defect; six other new cases are fixed-only safety/positive evidence. The original seven-suite 117-pass/1-failure/1-skip run remains separate: duplicate budget initialization and missing explicit PG tools were test/setup corrections, not further product fixes or a diagnosis of historical Darwin failure.

Additional outside-checkout Windows Python3.12.14 comparison records two exact primary failures in the normally installed public050 package and eight exact passes in a fresh local-dist-v4 wheel[agents] installation, with all98 package files verified. These retained XML/log/runtime records are supporting local preflight evidence, not the final native pair or actual-PyPI051 publication proof; overlapping runs are not additive.

E051-02 refund requires private exact callback/request proof, current owner/worker/fence and active unexpired lease; host/DB administrator remain trusted. General denial, entered/child effects, cancellation, uncertain late work and lost ownership provide no refund authority. D051-02 is static text correction only; cumulative DoS severity and throughput were not measured. Original v1 JSON/compact bytes remain retained; the full v2 JSON belongs only in the single Release evidence archive.
