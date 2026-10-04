# Lifecycle SDK, CLI and how-to

This is the canonical lifecycle interface reference. [Concepts](lifecycle-concepts.md)
define its non-claims. [Generated CLI help](cli-help.txt) and packaged JSON schemas
come from actual code; the old [operational API](api.md) remains unchanged.

## SDK

The SDK report's `projection_digest` property hashes its JSON projection. It is
distinct from every referenced original payload digest and is not a signature.

Import from `collective_intelligence_overlay.lifecycle`:

| API | Input / result | Effects |
|---|---|---|
| `snapshot_from_material(material, *, owner, caller, principals=None)` | Explicit finite JSON to `LifecycleSnapshot` | Verify original supplied DSSE; no fetch |
| `inspect_lifecycle(snapshot, target)` | `CapabilityIdentity` to `CapabilityLifecycleView` | Read-only, no qualification |
| `observe_contributions(snapshot)` | Tuple of `ContributionObservation` | Read-only dedup/references |
| `observe_growth(opening, closing, *, history=None)` | Two `StockObservation` to `GrowthObservation` | Read-only set/timeline reconciliation |
| `build_handoff(view, *, source_role, target_role, producer, receiver, contract_identity, state='proposed', state_basis=None)` | `HandoffObservation` | Read-only, no delivery or grant |
| `assess_stock(overlay, requests)` | 1–32 exact `UseRequest` to `StockObservation` | Explicit existing qualification; saves Decisions/costs |

`Residual` is a typed value in reports, not an executable operation.
`CapabilityIdentity` contains issuer, exact Subject (ID/version/full digest) and
binding digest. Missing legacy binding stays null. Assessment requests must share
local receiver and scope, identify an issuer and retain host semantic-fit intent.
The assessment window contains actual per-target Decisions and is explicitly non-atomic.

From `collective_intelligence_overlay.lifecycle_store`:
`read_lifecycle_page(store, target=None, *, caller, receiver=None, record_cursor=None,
decision_cursor=None, limit=128, byte_limit=1048576)` returns bounded existing Store
records. Caller must equal owner before queries. Exact target fixes a subject selection;
optional target None is a partial owner listing. No graph closure is fetched.
`export_originals(store, references, *, caller)` checks 1–256 exact references before
export, preserving DSSE payload bytes and unsigned Decisions. It does not redact a
signature while claiming originality. Foreign material must be explicitly authorized
and supplied through an existing sharing/export path.

## Offline examples

```console
collective-intelligence-overlay lifecycle inspect --fixture
collective-intelligence-overlay lifecycle contributions --fixture
collective-intelligence-overlay lifecycle handoff --fixture --source-role REUSE --target-role ACCOUNT
collective-intelligence-overlay lifecycle schema --type GrowthObservation
```

For private finite JSON use `--input material.json --owner receiver --target target.json`.
Signed entries require `--principals-file public-pins.json`. The owner and pins are
host-selected; a name in JSON is not authentication. File input is local operator
material, not a remotely authenticated endpoint. No path or URL in a record is opened.

Material has `view_schema_version: "1"`, `context` (ObservationContext schema) and
`records`, each with `format` (`dsse`/`unsigned`), `document`, nullable `received_at`,
nullable `sequence`, and optional exact `reference`. An externally exported unsigned
Decision can retain its supplied owner reference; it acquires no signature.
The packaged `fixtures/lifecycle-synthetic-v1.json` is a complete example with an
explicit synthetic provenance wrapper. `lifecycle schema --type TYPE` exposes the
five public schemas plus StockObservation and their nested definitions.

Source `occurred_at` is null when the original JSON has no creation/occurrence/
evaluation clock. `decoder_default_fields` lists top-level fields absent from the
original but supplied by the unchanged legacy typed decoder; those values in a
decoded record are projection defaults, not observed source facts. An empty list
means all top-level fields were present; null means original presence was not
attested by a directly constructed report. Evidence and cost clocks also remain
null, and matching history with an absent clock cannot establish period counts or
gross churn. Store reception clocks remain distinct. Original hashes, signatures
and explicit exports cover the original bytes, never these decoder defaults.
An original without the required record ID cannot supply an exact source reference;
inspection rejects it instead of referring to a newly generated decoder ID.

Recognized duration labels (`ns`/nanoseconds, `us`/microseconds, `ms`/milliseconds,
`s`/seconds, minutes, hours, days, including singular spellings, and `wall_seconds`,
`wall_ms`, `cpu_seconds`, `cpu_ms`) retain their exact units and are listed separately
with `inclusive_or_unspecified` basis. They are never added, even for different
invocations, and no conversion is performed. Other units supply only recorded
quantity subtotals; custom unit meaning and physical-cost correspondence remain
unresolved. Unchanged legacy record validation still applies before inspection;
structural errors remain errors, rather than fabricated historical fields.

## Owner reads, assessment and pagination

Use `lifecycle inspect --config owner.toml --target target.json`. To continue, save
the output's entire `context` as cursor.json and pass `--cursor-file cursor.json` with
the same target/page bounds. Both record/Decision cursors are required; the exhausted
kind does not restart. Continuation is page-local/partial even on its last page.
`lifecycle contributions --config owner.toml` also supports a bounded whole-owner
listing without a target; its coverage remains partial. Fixture bounds/identity are
fixed, and file material does not accept Store pagination flags.

`lifecycle assess --config owner.toml --requests-file requests.json` explicitly runs
current qualification. Retain its JSON independently as opening.json, then later run
a separate assessment as closing.json. Inspecting old ACCEPT does not perform this.
Compare using `lifecycle growth --opening opening.json --closing closing.json`.
Optional `--input history.json --owner OWNER --principals-file public-pins.json` is
finite period material. Churn needs matching complete history; without it, churn,
re-admissions and service totals are null. Read known cost subtotals with their units,
status, owner and original cost positions, rather than calling missing costs free.

For handoff export use `lifecycle handoff` with the same inspection selection and
`--source-role`, `--target-role`, `--producer`, `--receiver`, `--contract`. CLI export
is proposed; the SDK supports received/assessed only with exact visible state_basis.
`lifecycle export-originals --config owner.toml --references-file refs.json` exports
an explicit list of RecordRef. Reports hold references by default, not private bytes.

## Bounds and failures

Schema version 1; derivation version 0.5.0. Finite material ≤256 records / 1 MiB;
Store page 2–256 / 4096–1048576 bytes; contribution aggregate ≤512 / 1 MiB;
each final CLI/report ≤1 MiB. Supplied cycles are rejected; missing links remain
missing. Store statements retain their existing five-second timeout, and the bridge
checks a five-second aggregate deadline between operations. A statement already in
progress can finish before that aggregate check. No retry or hidden fetch follows.

Exit 0: produced a bounded result (not semantic acceptance); 3: continuation cursor
remains; 2: invalid options, unknown schema, denied read, tamper, conflict, timeout,
restore/cursor mismatch or service failure. Errors remain closed and redacted by the
existing CLI. `--fixture`, `--input`, `--config` are exclusive; incompatible mode flags
are rejected. SDK errors retain PermissionError, ValueError/Conflict and TimeoutError.
