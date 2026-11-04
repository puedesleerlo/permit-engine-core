#!/bin/sh
# Reruns every offline experiment and checks each result matches the saved one. Makes no API calls.
# Standard library only. Run from anywhere: sh experiments/run_all.sh
# The two scripts that call real Jev (jev_names_probe.py, jev_direct_pilot.py) are not rerun here, because a new call
# may answer differently and costs tokens. Their raw answers are saved in results/, and sim_corrections_combined.py
# replays one set of them.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
PY=${PYTHON:-python3}
OUT=$(mktemp -d)
export PYTHONDONTWRITEBYTECODE=1
cd "$OUT" || exit 1
fail=0
check() { # name, saved file, command...
  name=$1; saved=$2; shift 2
  "$@" > "$OUT/$saved" 2>&1
  if diff -q "$OUT/$saved" "$HERE/results/$saved" > /dev/null; then echo "same     $name"; else echo "DIFFERS  $name"; fail=1; fi
}
check "Can the trees learn?"            data_plan.txt               "$PY" "$HERE/sim_data_plan.py"
check "Validation size"                 validation_size.txt         "$PY" "$HERE/sim_check2.py" "$HERE"
check "Corrections, tuned (superseded)" corrections_comparison.txt  "$PY" "$HERE/sim_corrections.py" --sens 0.164 --spec 0.895 --level 0.104
check "Corrections, fixed settings"     corrections_fixed_step.txt  "$PY" "$HERE/sim_corrections_fixed_step.py"
check "Corrections, combined network"   corrections_combined.txt    "$PY" "$HERE/sim_corrections_combined.py"
check "Full decision table"             full_table.txt              "$PY" "$HERE/sim_full_table.py"
check "Candidate pass rules"            pass_rule.txt               "$PY" "$HERE/sim_pass_rule.py"
check "What a demo plot would show"     demo_curve.txt              "$PY" "$HERE/sim_demo_curve.py"
rm -rf "$OUT"
exit $fail
