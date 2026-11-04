package permit.basic

required_fields := ["organizer", "event_type", "event_date", "expected_runners", "venue", "description", "hospital_distance_km"]

required_route_fields := ["road_closure", "arterial_road", "major_crossings"]

check_order := ["form_complete", "fee_paid", "date_allowed"]

clauses := {"form_complete": "ORD-3.2", "fee_paid": "ORD-3.1", "date_allowed": "ORD-3.3"}

allowed_months := {"03", "04", "05", "06", "07", "08", "09", "10", "11"}

present(value) if {
	value != null
	value != ""
}

default form_complete := false

form_complete if {
	every field in required_fields {
		present(input.form[field])
	}
	every field in required_route_fields {
		present(input.form.route[field])
	}
	is_array(input.form.attachments)
}

default fee_paid := false

fee_paid if input.fee_paid == true

default date_allowed := false

date_allowed if {
	regex.match(`^[0-9]{4}-[0-9]{2}-[0-9]{2}$`, input.form.event_date)
	substring(input.form.event_date, 5, 2) in allowed_months
}

passed := {"form_complete": form_complete, "fee_paid": fee_paid, "date_allowed": date_allowed}

failed := [check | some check in check_order; passed[check] == false]

result := {
	"form_complete": form_complete,
	"fee_paid": fee_paid,
	"date_allowed": date_allowed,
	"failed": failed,
	"clauses": clauses,
}
