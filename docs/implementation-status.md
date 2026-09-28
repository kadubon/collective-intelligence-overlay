# Implementation status

## 0.2.0 implementation and validation

The 0.2.0 incremental specification was supplied on 2026-09-28. Implementation
and validation are complete. Release CI, OIDC publication and actual PyPI
post-install verification succeeded; exact commits, hashes and observations are
recorded in [releasing](releasing.md).

- [x] Typed local/MCP/A2A bindings, actual argument/resource/issuer enforcement,
  provider-local authorization, generic peer and application-side registration.
- [x] Indexed exact subject/claim/scope/dependency queries and reverse dependency
  pages; bounded database work, asynchronous offload and relevant revisions.
- [x] Resumable receiver/filter/generation-bound snapshot/delta synchronization,
  commit-order-safe prefixes, atomic checkpoints and completion-bound freshness.
- [x] Persistent caller-scoped invocation/result/cancel, uncertain-effect retention,
  fencing and reservations separated from measured consumption.
- [x] Actual C1/C2/C3/C4 construction with independent checking, ordinary-use
  execution receipts, scoped lineage/metrics and cost attribution.
- [x] Original 0.1.0 signed payload preservation, transactional migration and
  actual PostgreSQL backup/restore, including post-restore freshness invalidation.
- [x] Real PostgreSQL, OPA, MAF, A2A HTTP and MCP tests; three-process CSV and
  external document applications; 1k/10k/100k mixed signed-history measurements.
- [x] CLI, API, deployment/recovery, research mapping, dependency review and skill
  documentation. No paid model calls are needed for these checks.
- [x] Final exact-commit CI, OIDC release and clean installation from actual PyPI,
  followed by both three-process E2Es (2 passed, zero skips, 68.97 seconds).

The default CSV application uses explicit registrations, independently checked
provider and receiver-imported bindings, and persistent A2A execution. It installs
known functions; it does not claim algorithm discovery. The external document
application, outside the package, demonstrates observed C3 use in subsequent C4
formation with actual MAF composition, held-out inputs, restart/replay and source
withdrawal. Remote service use does not transfer executable code or attest it.

See [validation](validation.md) for test observations and their limits,
[scale](scale.md) for raw measurements, and [research mapping](research-mapping.md)
for the operational interpretation and omitted theoretical guarantees. Earlier
implementation checkpoints remain in Git history; the original v0.1.0 tag is
unchanged at `7e4f1191aaf7e9bca8a6091e1758204e189cb924`.

Intentional scope: no global manager, new runtime/planner, broker, trustless
database, received-code execution, automatic model spending or universal
intelligence metric. Standard non-overlay A2A support covers immediate JSON
responses; unexpected long-running tasks remain UNKNOWN and require reconciliation.
