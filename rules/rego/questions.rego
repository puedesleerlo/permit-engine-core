package permit.questions

hot_months := {"06", "07", "08"}

spectators := s if {
	s := input.extracted.expected_spectators
	is_number(s)
} else := 0

crowd := input.form.expected_runners + spectators

default arterial_road := false

arterial_road if input.form.route.arterial_road == true

default crowd_over_800 := false

crowd_over_800 if crowd > 800

default hot_date := false

hot_date if substring(input.form.event_date, 5, 2) in hot_months

default hospital_far := false

hospital_far if input.form.hospital_distance_km > 10

default many_major_crossings := false

many_major_crossings if input.form.route.major_crossings >= 3

answers := {
	"arterial_road": arterial_road,
	"crowd_over_800": crowd_over_800,
	"hot_date": hot_date,
	"hospital_far": hospital_far,
	"many_major_crossings": many_major_crossings,
}
