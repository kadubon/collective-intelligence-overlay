# Production 0.4.0 acceptance declaration

This is a preimplementation declaration, not a supported release or a validation
result. The published baseline is 0.3.2 at `b172c0d0`, with all 12 native tag and
actual-PyPI profiles verified; see [validation](validation.md).

[The machine-readable profile](profiles/production-040.json) is the authority for
scope, operating limits, numerical acceptance targets, required faults, the actual
60-minute Linux release soak and five isolated matched experiment pairs.
[The requirement register](production-040-acceptance.json) records implementation,
tests, observations and remaining work. Empty implementation lists and null
observations mean unfinished work, not implicit acceptance.

The profile covers a permissioned mesh with one active process per owner, restricted
runtime database roles, trusted installed application factories, HTTPS and independent
application checks. The existing Registry, Executor, Store, OPA and finite goal loop
remain the authoritative execution path. Native Windows/macOS peers are part of the
required installed production gates. Their short gate does not imply an hour-long
soak observation on those systems.

All offered work, failure, UNKNOWN, refusal and censored outcomes stay in reports.
The performance bounds are targets for the declared workload and hardware envelope;
they are not a universal SLA. Positive adaptive benefit is not a release gate.
Paid inference is disabled in mandatory validation.

Do not relax this profile after seeing measurements. Preserve failed reports and
fix the implementation, then run the complete affected protocol again. A separately
motivated future profile needs a new identity and cannot retroactively pass this one.

No 0.4.0 production implementation or acceptance run preceded this declaration.
