package permit.requirements_test

import data.permit.requirements

status_with(record) := s if {
	result := requirements.status with input as {"records": {"certificate_of_insurance": record}}
	s := result.event_insurance.status
}

test_met if {
	status_with({"status": "found", "verdict": "supported", "field_failed": false, "field_mismatch": false}) == "met"
}

test_output_shape if {
	result := requirements.status with input as {"records": {"certificate_of_insurance": {"status": "found", "verdict": "supported", "field_failed": false, "field_mismatch": false}}}
	result == {"event_insurance": {"status": "met", "clause": "ORD-7.1", "evidence_type": "certificate_of_insurance"}}
}

test_failed_field if {
	status_with({"status": "found", "verdict": "supported", "field_failed": true, "field_mismatch": false}) == "failed"
}

test_failed_field_beats_mismatch if {
	status_with({"status": "found", "verdict": "contradicted", "field_failed": true, "field_mismatch": true}) == "failed"
}

test_missing_when_absent if {
	status_with({"status": "absent", "verdict": null, "field_failed": false, "field_mismatch": false}) == "missing"
}

test_missing_when_no_record if {
	result := requirements.status with input as {"records": {}}
	result.event_insurance.status == "missing"
}

test_unclear_when_fields_match_but_verdict_unsupported if {
	status_with({"status": "found", "verdict": "unsupported", "field_failed": false, "field_mismatch": false}) == "unclear"
}

test_unclear_when_supported_but_field_mismatch if {
	status_with({"status": "found", "verdict": "supported", "field_failed": false, "field_mismatch": true}) == "unclear"
}

test_unclear_when_contradicted if {
	status_with({"status": "found", "verdict": "contradicted", "field_failed": false, "field_mismatch": true}) == "unclear"
}

test_unclear_when_verdict_null if {
	status_with({"status": "found", "verdict": null, "field_failed": false, "field_mismatch": false}) == "unclear"
}
