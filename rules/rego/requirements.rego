package permit.requirements

definitions := {"event_insurance": {"evidence_type": "certificate_of_insurance", "clause": "ORD-7.1"}}

status_of(evidence_type) := "missing" if {
	not input.records[evidence_type].status == "found"
} else := "failed" if {
	input.records[evidence_type].field_failed == true
} else := "met" if {
	input.records[evidence_type].verdict == "supported"
	not input.records[evidence_type].field_mismatch == true
} else := "unclear"

status := {id: {"status": status_of(def.evidence_type), "clause": def.clause, "evidence_type": def.evidence_type} |
	some id, def in definitions
}
