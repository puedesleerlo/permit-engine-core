package permit.screen

import data.permit.questions

default traffic_conflict := false

traffic_conflict if input.form.route.road_closure == true

default crowd_pressure := false

crowd_pressure if questions.crowd >= 300

medical_emergency := true

applies := {
	"traffic_conflict": traffic_conflict,
	"crowd_pressure": crowd_pressure,
	"medical_emergency": medical_emergency,
}
