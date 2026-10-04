# 0.5.1 stabilization audit

This is a finite maintainer review, not an independent security audit or a claim
of complete safety. The five 0.5.0 projections and existing execution authority
remain the scope. No inference, model pull or scientific rerun is authorized.

Baseline: clean `main` at `d39ac26a342dc0e040e2368e5e364f534c08328c`;
published 0.5.0 tag commit `1c7e3527dc48580f92e70f2a3752d54e970808d4`.
The source/package/test/workflow trees match that tag; later publication Docs are
separate from its immutable metadata. Work starts on `stabilization/051-audit`.
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
candidate is excluded from publication. It was not cancelled or rerun. The revised
source and its complete native release gate still need validation.

Findings below are confirmed reproductions unless explicitly marked otherwise.
Private diagnostic inputs and raw logs are retained under `.local/audit-051*`;
the final software evidence archive will contain sanitized, bounded evidence.

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
| R051-01 | P2 operability | Release selectors/package checks/profile stop at 0.5.0 | 051 could not reuse pair/load profile; inherit unchanged gates | implemented; focused regression passed |

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

## Evidence still required

The revised local preflight wheel/sdist passed normal clean installations and
dependency/license/SBOM checks; these bytes are not the final CI candidate.
Final native provenance/gate, exact pair reuse, OIDC publication and actual PyPI/Release
download/install remain pending at this prepublication source snapshot. Full/native
and postpublication results will be separately recorded in versioned release Docs.

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
README identifies unpublished 0.5.1 and links actual publication records separately.
