import yaml

from conftest import REPO
from permitengine.trees.lint import PENDING, lint_tree


def _inputs():
    evidence_map = yaml.safe_load((REPO / "rules" / "evidence_map.yaml").read_text())
    clause_ids = {c["id"] for c in yaml.safe_load((REPO / "rules" / "ordinance.yaml").read_text())["clauses"]}
    rule_ids = {"arterial_road", "crowd_over_800", "hot_date", "hospital_far", "many_major_crossings"}
    return evidence_map, clause_ids, rule_ids


def _tree():
    return yaml.safe_load((REPO / "rules" / "trees" / "traffic.likelihood.yaml").read_text())


def test_pending_first_guess_is_not_a_pass():
    tree = _tree()
    tree["leaves"] = []
    errors, notes = lint_tree(tree, *_inputs())
    assert errors == [] and notes == [PENDING]


def test_complete_leaves_pass_and_broken_ones_fail():
    tree = _tree()
    tree["leaves"] = [{"when": {"escort_confirmed": a, "traffic_plan_adequate": b}, "levels": [0.8, 0.1, 0.1]} for a in (True, False) for b in (True, False)]
    assert lint_tree(tree, *_inputs()) == ([], [])
    tree["leaves"][0]["levels"] = [0.9, 0.9, 0.1]
    assert any("does not sum" in e for e in lint_tree(tree, *_inputs())[0])
    tree["leaves"].pop()
    assert any("every combination" in e for e in lint_tree(tree, *_inputs())[0])


def test_unknown_names_fail():
    for change, expected in (({"kind": "rule", "id": "no_such_rule"}, "unknown rule"), ({"kind": "evidence", "evidence_types": ["no_such_type"]}, "unknown evidence type"),
                             ({"clause": "ORD-999"}, "unknown clause"), ({"kind": "jev", "needs": ["no_such_need"]}, "unknown need")):
        tree = _tree()
        tree["leaves"] = []
        tree["questions"][0].update(change)
        assert any(expected in e for e in lint_tree(tree, *_inputs())[0])


def test_too_few_training_cases_per_leaf_fails():
    tree = _tree()
    tree["leaves"] = []
    cards = [{"facts": {"form_complete": True, "fee_paid": True, "date_allowed": True, "road_closure": True, "crowd": 400, "escort_evidence": "letter", "escort_arranged": True, "traffic_plan_adequate": True}}] * 20
    errors, _ = lint_tree(tree, *_inputs(), cards)
    assert sum("training cases" in e for e in errors) == 3
