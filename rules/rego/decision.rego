package permit.decision

import data.permit.requirements

required_inputs := ["basic", "requirements", "highest_severity", "ceiling", "risk", "t_low", "t_high"]

policy_failed if input.policy_failure == true

policy_failed if {
	some key in required_inputs
	not has_key(input, key)
}

has_key(object_value, key) if {
	object_value[key] = _
}

status_value(value) := value.status if {
	is_object(value)
} else := value

with_status(wanted) := sort([id | some id, value in input.requirements; status_value(value) == wanted])

clauses_for(wanted) := [requirements.definitions[id].clause | some id in with_status(wanted)]

failed_check_clauses := [input.basic.clauses[check] | some check in input.basic.failed]

row(number, route, reason_code, clauses, text) := {
	"row": number,
	"route": route,
	"reason_code": reason_code,
	"clauses": clauses,
	"text": text,
}

result := row(0, "returned", "form_returned", [input.basic.clauses.form_complete], "The form is incomplete, so it goes back to the applicant.") if {
	input.basic.form_complete == false
} else := row(0, "proposed_denial", "basic_rule_failed", failed_check_clauses, "A basic rule was not met, so a denial is proposed for an officer to sign.") if {
	count(input.basic.failed) > 0
} else := row(1, "officer", "red_flag", ["ORD-9.3"], "A document disagrees with the application, so an officer decides.") if {
	input.evidence_contradicted == true
} else := row(1, "officer", "requirement_unclear", clauses_for("unclear"), "It is unclear whether a requirement is met, so an officer decides.") if {
	count(with_status("unclear")) > 0
} else := row(1, "officer", "unmapped_evidence", ["ORD-9.2"], "The file holds a document of a type the map does not list, so an officer decides.") if {
	input.unmapped_documents > 0
} else := row(1, "officer", "model_failure", ["ORD-20.5"], "A reading model failed on this case, so an officer decides.") if {
	input.model_failure == true
} else := row(1, "officer", "policy_unavailable", ["ORD-20.5"], "The policy check could not run, so an officer decides.") if {
	policy_failed
} else := row(1, "officer", "stop_switch", ["ORD-20.3"], "The stop switch is on, so an officer decides.") if {
	input.stop_switch == true
} else := row(1, "officer", "severity_ceiling", ["ORD-20.4"], "The highest severity reaches the ceiling, so an officer decides however small the likelihood.") if {
	input.highest_severity >= input.ceiling
} else := row(2, "proposed_denial", "requirement_failed", clauses_for("failed"), "A requirement failed, so a denial is proposed for an officer to sign.") if {
	count(with_status("failed")) > 0
} else := row(3, "officer", "requirement_missing", clauses_for("missing"), "Proof of a requirement is missing, so an officer decides.") if {
	count(with_status("missing")) > 0
} else := row(4, "approved", "approved", ["ORD-20.1"], "Every check passed and the risk is below the lower threshold, so the race is approved.") if {
	input.risk < input.t_low
} else := row(5, "officer", "high_risk", ["ORD-20.2"], "The risk is at or above the upper threshold, so an officer decides.") if {
	input.risk >= input.t_high
} else := row(6, "officer", "review_band", ["ORD-20.2"], "The risk is inside the review band, so an officer decides.")
