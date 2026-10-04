# Moving from 0.4.x to the lifecycle views

0.5.0 adds read projections and CLI modes. Existing wire Record union, signed
Capability/Evidence/Event models, invocations, reservation semantics, source sync,
admission policy and withdrawals are unchanged. No DB migration is added; existing
0022 remains the latest required migration. Continue the existing offline
[deployment upgrade](deployment.md) requirements when arriving from older schemas.

Old CLI/SDK execution and recovery APIs remain available. Views never change budget,
resume work or grant execution. Only explicitly requested `assess_stock` saves new
Decisions through current qualification. No current-policy replay can manufacture a
historical opening stock. Preserve independently acquired snapshots to compare them.

Legacy missing binding, source, reception or invocation identity stays null/unresolved.
Old unsigned Decisions remain unsigned; historical DSSE payloads retain original
bytes/digests. A view has its own version/digest and is not inserted into the old feed.
Current compromised-key authority does not erase historical verified bytes.

New inspections require owner read authority. Existing peer sharing filters still
apply; do not obtain transitive private originals through a report reference.
Explicit finite exports are the operator's responsibility. Page-local coverage,
unknown costs and residuals remain visible after JSON/handoff round trips.
Changing receiver/scope/policy/universe makes exact stock deltas unavailable.

See [reference](lifecycle-reference.md), [concepts](lifecycle-concepts.md) and
[actual validation register](lifecycle-050-implementation.md). Native/package evidence
must bind the 0.5.0 candidate; an older successful gate does not attest changed files.
