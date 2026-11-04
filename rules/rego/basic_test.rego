package permit.basic_test

import data.permit.basic

form := {
	"organizer": "Riverside Runners",
	"event_type": "street_race",
	"event_date": "2027-06-12",
	"expected_runners": 400,
	"venue": "Harbourside",
	"description": "A 5K.",
	"route": {"road_closure": true, "arterial_road": false, "major_crossings": 1},
	"hospital_distance_km": 3,
	"fee_paid": true,
	"attachments": ["race_plan.txt"],
}

all_clauses := {"form_complete": "ORD-3.2", "fee_paid": "ORD-3.1", "date_allowed": "ORD-3.3"}

test_all_pass if {
	basic.result == {"form_complete": true, "fee_paid": true, "date_allowed": true, "failed": [], "clauses": all_clauses} with input as {"form": form, "fee_paid": true}
}

test_fee_unpaid if {
	r := basic.result with input as {"form": form, "fee_paid": false}
	r.fee_paid == false
	r.failed == ["fee_paid"]
}

test_fee_absent_counts_as_unpaid if {
	r := basic.result with input as {"form": form}
	r.failed == ["fee_paid"]
}

test_missing_field_is_incomplete if {
	r := basic.result with input as {"form": object.remove(form, ["hospital_distance_km"]), "fee_paid": true}
	r.form_complete == false
	r.failed == ["form_complete"]
}

test_null_field_is_incomplete if {
	r := basic.result with input as {"form": object.union(form, {"organizer": null}), "fee_paid": true}
	r.failed == ["form_complete"]
}

test_empty_field_is_incomplete if {
	r := basic.result with input as {"form": object.union(form, {"venue": ""}), "fee_paid": true}
	r.failed == ["form_complete"]
}

test_missing_route_field_is_incomplete if {
	r := basic.result with input as {"form": json.remove(form, ["route/major_crossings"]), "fee_paid": true}
	r.failed == ["form_complete"]
}

test_false_route_field_is_present if {
	r := basic.result with input as {"form": object.union(form, {"route": {"road_closure": false, "arterial_road": false, "major_crossings": 0}}), "fee_paid": true}
	r.form_complete == true
}

test_missing_date_fails_two_checks if {
	r := basic.result with input as {"form": object.remove(form, ["event_date"]), "fee_paid": true}
	r.failed == ["form_complete", "date_allowed"]
}

test_date_outside_window if {
	r := basic.result with input as {"form": object.union(form, {"event_date": "2027-12-19"}), "fee_paid": true}
	r.date_allowed == false
	r.failed == ["date_allowed"]
}

test_first_and_last_months_allowed if {
	a := basic.result with input as {"form": object.union(form, {"event_date": "2027-03-01"}), "fee_paid": true}
	b := basic.result with input as {"form": object.union(form, {"event_date": "2027-11-30"}), "fee_paid": true}
	a.date_allowed == true
	b.date_allowed == true
}

test_badly_written_date_not_allowed if {
	r := basic.result with input as {"form": object.union(form, {"event_date": "June 12, 2027"}), "fee_paid": true}
	r.date_allowed == false
}

test_all_fail_in_order if {
	r := basic.result with input as {"form": {}, "fee_paid": false}
	r.failed == ["form_complete", "fee_paid", "date_allowed"]
	r.clauses == all_clauses
}
