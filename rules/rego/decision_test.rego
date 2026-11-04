package permit.decision_test

import data.permit.decision

clauses := {"form_complete": "ORD-3.2", "fee_paid": "ORD-3.1", "date_allowed": "ORD-3.3"}

clean := {
	"basic": {"form_complete": true, "fee_paid": true, "date_allowed": true, "failed": [], "clauses": clauses},
	"requirements": {"event_insurance": {"status": "met", "clause": "ORD-7.1", "evidence_type": "certificate_of_insurance"}},
	"evidence_contradicted": false,
	"unmapped_documents": 0,
	"model_failure": false,
	"policy_failure": false,
	"stop_switch": false,
	"highest_severity": 0.4,
	"ceiling": 0.85,
	"risk": 0.05,
	"t_low": 0.08,
	"t_high": 0.25,
}

decide(changes) := r if {
	r := decision.result with input as object.union(clean, changes)
}

basic_fail(form_complete, failed) := {"form_complete": form_complete, "fee_paid": true, "date_allowed": true, "failed": failed, "clauses": clauses}

req(status) := {"event_insurance": {"status": status, "clause": "ORD-7.1", "evidence_type": "certificate_of_insurance"}}

# One test per table row and reason code.

test_row0_returned if {
	r := decide({"basic": basic_fail(false, ["form_complete"])})
	r.row == 0
	r.route == "returned"
	r.reason_code == "form_returned"
	r.clauses == ["ORD-3.2"]
	count(r.text) > 0
}

test_row0_fee_denial if {
	r := decide({"basic": basic_fail(true, ["fee_paid"])})
	r.row == 0
	r.route == "proposed_denial"
	r.reason_code == "basic_rule_failed"
	r.clauses == ["ORD-3.1"]
}

test_row0_date_denial if {
	r := decide({"basic": basic_fail(true, ["date_allowed"])})
	r.row == 0
	r.route == "proposed_denial"
	r.reason_code == "basic_rule_failed"
	r.clauses == ["ORD-3.3"]
}

test_row1_red_flag if {
	r := decide({"evidence_contradicted": true})
	r.row == 1
	r.route == "officer"
	r.reason_code == "red_flag"
	r.clauses == ["ORD-9.3"]
}

test_row1_requirement_unclear if {
	r := decide({"requirements": req("unclear")})
	r.row == 1
	r.route == "officer"
	r.reason_code == "requirement_unclear"
	r.clauses == ["ORD-7.1"]
}

test_row1_unmapped if {
	r := decide({"unmapped_documents": 1})
	r.row == 1
	r.route == "officer"
	r.reason_code == "unmapped_evidence"
	r.clauses == ["ORD-9.2"]
}

test_row1_model_failure if {
	r := decide({"model_failure": true})
	r.row == 1
	r.route == "officer"
	r.reason_code == "model_failure"
}

test_row1_policy_failure if {
	r := decide({"policy_failure": true})
	r.row == 1
	r.route == "officer"
	r.reason_code == "policy_unavailable"
}

test_row1_stop_switch if {
	r := decide({"stop_switch": true})
	r.row == 1
	r.route == "officer"
	r.reason_code == "stop_switch"
	r.clauses == ["ORD-20.3"]
}

test_row1_ceiling if {
	r := decide({"highest_severity": 0.9})
	r.row == 1
	r.route == "officer"
	r.reason_code == "severity_ceiling"
	r.clauses == ["ORD-20.4"]
}

test_row2_requirement_failed if {
	r := decide({"requirements": req("failed")})
	r.row == 2
	r.route == "proposed_denial"
	r.reason_code == "requirement_failed"
	r.clauses == ["ORD-7.1"]
}

test_row3_requirement_missing if {
	r := decide({"requirements": req("missing")})
	r.row == 3
	r.route == "officer"
	r.reason_code == "requirement_missing"
	r.clauses == ["ORD-7.1"]
}

test_row4_approved if {
	r := decide({})
	r.row == 4
	r.route == "approved"
	r.reason_code == "approved"
	r.clauses == ["ORD-20.1"]
}

test_row5_high_risk if {
	r := decide({"risk": 0.3})
	r.row == 5
	r.route == "officer"
	r.reason_code == "high_risk"
}

test_row6_review_band if {
	r := decide({"risk": 0.1})
	r.row == 6
	r.route == "officer"
	r.reason_code == "review_band"
}

# Boundaries.

test_ceiling_is_at_or_above if {
	r := decide({"highest_severity": 0.85})
	r.reason_code == "severity_ceiling"
}

test_just_under_ceiling_is_not_stopped if {
	r := decide({"highest_severity": 0.8499})
	r.row == 4
}

test_risk_at_t_low_is_not_approved if {
	r := decide({"risk": 0.08})
	r.row == 6
}

test_risk_at_t_high_is_high if {
	r := decide({"risk": 0.25})
	r.row == 5
}

test_crossed_thresholds_leave_no_band if {
	low := decide({"risk": 0.09, "t_low": 0.1, "t_high": 0.1})
	high := decide({"risk": 0.1, "t_low": 0.1, "t_high": 0.1})
	low.row == 4
	high.row == 5
}

# Precedence: first match wins.

test_row0_returned_beats_denial if {
	r := decide({"basic": basic_fail(false, ["form_complete", "fee_paid"])})
	r.reason_code == "form_returned"
}

test_row0_beats_row1 if {
	r := decide({"basic": basic_fail(true, ["fee_paid"]), "evidence_contradicted": true, "stop_switch": true})
	r.row == 0
}

test_row1_beats_row2 if {
	r := decide({"unmapped_documents": 1, "requirements": req("failed")})
	r.row == 1
}

test_row1_beats_row3 if {
	r := decide({"unmapped_documents": 1, "requirements": req("missing")})
	r.reason_code == "unmapped_evidence"
}

test_row1_beats_row4 if {
	r := decide({"stop_switch": true, "risk": 0.01})
	r.row == 1
}

test_ceiling_beats_requirement_failed if {
	r := decide({"highest_severity": 1.0, "requirements": req("failed")})
	r.reason_code == "severity_ceiling"
}

test_row2_beats_row4 if {
	r := decide({"requirements": req("failed"), "risk": 0.01})
	r.row == 2
}

test_row3_beats_row4 if {
	r := decide({"requirements": req("missing"), "risk": 0.01})
	r.row == 3
}

test_row3_beats_row5 if {
	r := decide({"requirements": req("missing"), "risk": 0.9})
	r.row == 3
}

test_row2_beats_row3_with_two_requirements if {
	r := decide({"requirements": {"event_insurance": {"status": "failed"}, "other": {"status": "missing"}}})
	r.row == 2
}

test_row1_reason_order if {
	r := decide({"evidence_contradicted": true, "requirements": req("unclear"), "unmapped_documents": 2, "model_failure": true, "stop_switch": true, "highest_severity": 1.0})
	r.reason_code == "red_flag"
}

test_row1_unclear_before_unmapped if {
	r := decide({"requirements": req("unclear"), "unmapped_documents": 2})
	r.reason_code == "requirement_unclear"
}

test_row1_model_failure_before_policy_failure if {
	r := decide({"model_failure": true, "policy_failure": true, "stop_switch": true})
	r.reason_code == "model_failure"
}

test_row1_policy_failure_before_stop_switch if {
	r := decide({"policy_failure": true, "stop_switch": true})
	r.reason_code == "policy_unavailable"
}

test_row1_stop_switch_before_ceiling if {
	r := decide({"stop_switch": true, "highest_severity": 1.0})
	r.reason_code == "stop_switch"
}

# Inputs.

test_plain_string_status_is_accepted if {
	r := decide({"requirements": {"event_insurance": "failed"}})
	r.row == 2
	r.clauses == ["ORD-7.1"]
}

test_missing_inputs_fail_safe if {
	r := decision.result with input as object.remove(clean, ["risk"])
	r.route == "officer"
	r.reason_code == "policy_unavailable"
}

test_empty_input_never_approves if {
	r := decision.result with input as {}
	r.route == "officer"
}
