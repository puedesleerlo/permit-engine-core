package permit.questions_test

import data.permit.questions
import data.permit.screen

form := {
	"expected_runners": 400,
	"event_date": "2027-06-12",
	"route": {"road_closure": true, "arterial_road": true, "major_crossings": 3},
	"hospital_distance_km": 11,
}

test_all_true if {
	a := questions.answers with input as {"form": object.union(form, {"expected_runners": 801}), "extracted": {"expected_spectators": null}}
	a == {"arterial_road": true, "crowd_over_800": true, "hot_date": true, "hospital_far": true, "many_major_crossings": true}
}

test_all_false if {
	a := questions.answers with input as {
		"form": {
			"expected_runners": 800,
			"event_date": "2027-05-12",
			"route": {"road_closure": true, "arterial_road": false, "major_crossings": 2},
			"hospital_distance_km": 10,
		},
		"extracted": {"expected_spectators": 0},
	}
	a == {"arterial_road": false, "crowd_over_800": false, "hot_date": false, "hospital_far": false, "many_major_crossings": false}
}

test_spectators_count_toward_crowd if {
	a := questions.answers with input as {"form": form, "extracted": {"expected_spectators": 401}}
	a.crowd_over_800 == true
}

test_null_spectators_count_as_zero if {
	a := questions.answers with input as {"form": form, "extracted": {"expected_spectators": null}}
	a.crowd_over_800 == false
}

test_hot_months if {
	june := questions.hot_date with input as {"form": {"event_date": "2027-06-01"}}
	august := questions.hot_date with input as {"form": {"event_date": "2027-08-31"}}
	september := questions.hot_date with input as {"form": {"event_date": "2027-09-01"}}
	june == true
	august == true
	september == false
}

test_screen_all_apply if {
	applies := screen.applies with input as {"form": form, "extracted": {"expected_spectators": null}}
	applies == {"traffic_conflict": true, "crowd_pressure": true, "medical_emergency": true}
}

test_screen_no_closure_small_crowd if {
	applies := screen.applies with input as {
		"form": {"expected_runners": 200, "route": {"road_closure": false}},
		"extracted": {"expected_spectators": 99},
	}
	applies == {"traffic_conflict": false, "crowd_pressure": false, "medical_emergency": true}
}

test_screen_spectators_reach_300 if {
	applies := screen.applies with input as {
		"form": {"expected_runners": 200, "route": {"road_closure": false}},
		"extracted": {"expected_spectators": 100},
	}
	applies.crowd_pressure == true
}
