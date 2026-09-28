package overlay

import rego.v1

# Structural facts are derived by the host. Admission rules live only here.
default decision := {"outcome": "UNKNOWN", "reasons": ["incomplete_policy_input"]}

reject contains "known_revocation" if input.revoked
reject contains "in_scope_counterexample" if { some e in input.evidence; e.applicable; e.fresh; e.authorized; e.verdict == "FAIL" }
reject contains "authority_denied" if { some p in input.capability.scope.permissions; not p in input.settings.permissions }
reject contains "license_not_allowed" if { input.capability.license != null; not input.capability.license in input.settings.licenses }

unknown contains "semantic_fit_unknown" if {
    input.request.semantic_fit != "confirmed"
    not object.get(input, "dependency_integrity_only", false)
}
unknown contains "license_unknown" if input.capability.license == null
unknown contains "unresolved_obligations" if count(input.capability.obligations) > 0
unknown contains "dependency_unknown" if input.dependency_state == "UNKNOWN"
unknown contains "ambiguous_or_missing_subject" if not input.subject_valid
unknown contains "freshness_unknown" if not input.source_fresh

requalify contains "scope_mismatch" if input.capability.scope != input.request.scope
requalify contains "capability_expired" if not input.capability_fresh
requalify contains "dependency_requires_requalification" if input.dependency_state == "REQUALIFY"
reject contains "dependency_rejected" if input.dependency_state == "REJECT"

valid_pass if {
    some e in input.evidence
    e.applicable
    e.fresh
    e.authorized
    e.independent
    e.verdict == "PASS"
    count(e.obligations) == 0
    e.support_valid
}
requalify contains "independent_evidence_required" if not valid_pass

decision := {"outcome": "REJECT", "reasons": sort(reject)} if count(reject) > 0
else := {"outcome": "UNKNOWN", "reasons": sort(unknown)} if count(unknown) > 0
else := {"outcome": "REQUALIFY", "reasons": sort(requalify)} if count(requalify) > 0
else := {"outcome": "ACCEPT", "reasons": ["dependency_integrity_not_execution_permission"]} if object.get(input, "dependency_integrity_only", false)
else := {"outcome": "ACCEPT", "reasons": ["qualified_for_receiver_and_scope"]}
