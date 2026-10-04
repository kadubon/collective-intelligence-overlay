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
No release gate has yet been executed for 0.5.1.

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
| D051-01 | P3 documentation | `SECURITY.md`: support targets latest 0.1.x | Stale support description; latest published 0.5.x maintenance without SLA | fixed; Docs review |
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

An initial caller regression incorrectly expected a conflict for a distinct caller.
The first failure is retained with its oracle correction; the separate public-wheel
run proves the corrected independent-use expectation fails on 0.5.0. A property
initially expected unwrapped Conflict, but Pydantic has always wrapped snapshot
validator errors as ValueError/ValidationError; its original failure and correction
are retained. Neither test correction is represented as a product fix.

## Evidence still required

Candidate normal clean installations/dependency/license/SBOM checks, final native
provenance/gate, exact pair reuse, OIDC publication and actual PyPI/Release
download/install remain pending at this prepublication source snapshot. Full/native
and postpublication results will be separately recorded in versioned release Docs.
