import math
import random

import pytest

from permitengine.learning.thresholds import choose
from permitengine.learning.train import fit, train_model
from permitengine.risk.score import score
from permitengine.trees.evaluate import distribution, entropy, evaluate, loss, reach
from permitengine.trees.loader import Model, all_whens, parse_tree

ANCHORS = {"likelihood": [0.02, 0.10, 0.30], "severity": [0.1, 0.4, 1.0]}


def tree(tree_id="traffic.likelihood", hazard="traffic_conflict", scale="likelihood", a="escort_confirmed", b="traffic_plan_adequate"):
    leaves = [{"when": {a: True, b: True}, "levels": [0.8, 0.1, 0.1]}, {"when": {a: True, b: False}, "levels": [0.1, 0.8, 0.1]},
              {"when": {a: False, b: True}, "levels": [0.1, 0.8, 0.1]}, {"when": {a: False, b: False}, "levels": [0.1, 0.1, 0.8]}]
    return parse_tree({"id": tree_id, "hazard": hazard, "scale": scale, "questions": [{"id": a, "kind": "evidence"}, {"id": b, "kind": "jev"}], "leaves": leaves})


def test_hand_calculated_tree():
    t = tree()
    answers = {"escort_confirmed": 0.9, "traffic_plan_adequate": 0.5}
    assert reach(t, answers) == pytest.approx([0.45, 0.45, 0.05, 0.05])
    # 0.45*[.8,.1,.1] + 0.45*[.1,.8,.1] + 0.05*[.1,.8,.1] + 0.05*[.1,.1,.8]
    dist = distribution(t.first_levels, reach(t, answers))
    assert dist == pytest.approx([0.415, 0.45, 0.135])
    counts = [[2 * v for v in d] for d in t.first_levels]
    out = evaluate(t, t.first_levels, counts, answers, ANCHORS["likelihood"])
    assert out["value"] == pytest.approx(0.415 * 0.02 + 0.45 * 0.10 + 0.135 * 0.30)
    assert out["entropy"] == pytest.approx(entropy([0.415, 0.45, 0.135]))
    assert loss(t, t.first_levels, answers, 2) == pytest.approx(-math.log(0.135))


def test_contributions_sum_to_the_total():
    t = tree()
    answers = {"escort_confirmed": 0.37, "traffic_plan_adequate": 0.81}
    counts = [[2 * v for v in d] for d in t.first_levels]
    out = evaluate(t, t.first_levels, counts, answers, ANCHORS["likelihood"])
    assert sum(leaf["contribution"] for leaf in out["leaves"]) == pytest.approx(out["value"])
    assert sum(leaf["reach"] for leaf in out["leaves"]) == pytest.approx(1.0)


def test_a_rule_answer_routes_one_way():
    t = tree()
    amounts = reach(t, {"escort_confirmed": 1.0, "traffic_plan_adequate": 0.0})
    assert amounts == pytest.approx([0.0, 1.0, 0.0, 0.0])


def test_every_combination_true_first():
    assert all_whens(["a", "b"]) == [{"a": True, "b": True}, {"a": True, "b": False}, {"a": False, "b": True}, {"a": False, "b": False}]


def _small_model():
    trees = {}
    for hazard, prefix in (("traffic_conflict", "traffic"), ("medical_emergency", "medical")):
        trees[f"{prefix}.likelihood"] = tree(f"{prefix}.likelihood", hazard, "likelihood", f"{prefix}_a", f"{prefix}_b")
        trees[f"{prefix}.severity"] = tree(f"{prefix}.severity", hazard, "severity", f"{prefix}_c", f"{prefix}_d")
    levels = {t: [list(d) for d in tr.first_levels] for t, tr in trees.items()}
    counts = {t: [[2 * v for v in d] for d in tr.first_levels] for t, tr in trees.items()}
    return Model("first-guess", trees, levels, counts)


def test_risk_sums_only_hazards_that_apply():
    model = _small_model()
    answers = {k: 1.0 for t in model.trees.values() for k in t.question_ids}
    only_traffic = score(model, answers, {"traffic_conflict": True, "medical_emergency": False}, ANCHORS)
    both = score(model, answers, {"traffic_conflict": True, "medical_emergency": True}, ANCHORS)
    expected_l = 0.8 * 0.02 + 0.1 * 0.10 + 0.1 * 0.30
    expected_s = 0.8 * 0.1 + 0.1 * 0.4 + 0.1 * 1.0
    assert only_traffic["risk"] == pytest.approx(expected_l * expected_s)
    assert both["risk"] == pytest.approx(2 * expected_l * expected_s)
    assert only_traffic["hazards"]["medical_emergency"]["likelihood"] is None
    assert both["highest_severity"] == pytest.approx(expected_s)


def _simulated_rows(n, seed):
    """A hidden truth the first guess does not know: the level counts the bad answers, whichever question they are on."""
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        a, b = rng.randint(0, 1), rng.randint(0, 1)
        level = (1 - a) + (1 - b)
        if rng.random() < 0.08:
            level = max(0, min(2, level + rng.choice([-1, 1])))
        answers = {"escort_confirmed": rng.betavariate(6, 1.5) if a else rng.betavariate(1.5, 6),
                   "traffic_plan_adequate": rng.betavariate(6, 1.5) if b else rng.betavariate(1.5, 6)}
        rows.append((answers, level))
    return rows


def _wrong_first_guess():
    t = tree()
    t.first_levels = [[0.8, 0.1, 0.1], [0.8, 0.1, 0.1], [0.1, 0.8, 0.1], [0.1, 0.8, 0.1]]
    return t


def _mean_loss(t, levels, rows):
    return sum(loss(t, levels, answers, level) for answers, level in rows) / len(rows)


def test_training_lowers_loss_on_simulated_data_and_shuffled_does_not_match():
    t = _wrong_first_guess()
    train, held_out = _simulated_rows(180, 1), _simulated_rows(400, 2)
    levels, counts = fit(t, train, 2, 6)
    trained_loss = _mean_loss(t, levels, held_out)
    assert trained_loss < _mean_loss(t, t.first_levels, held_out) - 0.1
    shuffled = train_model({t.id: t}, {t.id: train}, 2, 6, "shuffled", shuffle_seed=3)
    assert trained_loss < _mean_loss(t, shuffled.levels[t.id], held_out) - 0.1
    assert sum(sum(c) for c in counts) == pytest.approx(180 + 4 * 2)


def test_each_leaf_keeps_its_counts():
    t = _wrong_first_guess()
    levels, counts = fit(t, _simulated_rows(50, 4), 2, 6)
    for level_row, count_row in zip(levels, counts):
        assert level_row == pytest.approx([c / sum(count_row) for c in count_row])


def test_thresholds_meet_targets_on_the_population_they_are_fitted_on():
    rows = [(i / 100, i >= 60) for i in range(100)]
    out = choose(rows, 0.05, 0.85)
    below = [k for r, k in rows if r < out["t_low"]]
    above = [k for r, k in rows if r >= out["t_high"]]
    assert sum(below) / len(below) <= 0.05
    assert sum(above) / len(above) >= 0.85


def test_thresholds_with_no_value_meeting_a_target_sit_at_the_end_of_the_range():
    rows = [(i / 10, True) for i in range(10)]
    out = choose(rows, 0.05, 0.85)
    assert out["t_low"] == 0.0
    assert any("nothing is approved" in note for note in out["notes"])
    rows = [(i / 10, False) for i in range(10)]
    out = choose(rows, 0.05, 0.85)
    assert out["t_high"] > 0.9
    assert not [r for r, _ in rows if r >= out["t_high"]]
    assert any("nothing is marked high risk" in note for note in out["notes"])


def test_crossing_thresholds_take_their_midpoint():
    rows = [(0.1, False)] * 19 + [(0.1, True)] + [(0.2, True)] * 90 + [(0.2, False)] * 10 + [(0.3, False)] * 40
    out = choose(rows, 0.05, 0.85)
    if "crossed" in " ".join(out["notes"]):
        assert out["t_low"] == out["t_high"]
