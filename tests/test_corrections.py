import pytest

from permitengine.learning.corrections import edge, net_update
from permitengine.trees.loader import Model, parse_tree

ANCHORS = {"likelihood": [0.02, 0.10, 0.30], "severity": [0.1, 0.4, 1.0]}
GAMMA = 0.93


def make_model(counts_each=2.0):
    def tree(tree_id, hazard, scale, a, b):
        leaves = [{"when": {a: x, b: y}, "levels": [0.5, 0.3, 0.2]} for x in (True, False) for y in (True, False)]
        return parse_tree({"id": tree_id, "hazard": hazard, "scale": scale, "questions": [{"id": a, "kind": "rule"}, {"id": b, "kind": "rule"}], "leaves": leaves})

    trees = {"traffic.likelihood": tree("traffic.likelihood", "traffic_conflict", "likelihood", "a", "b"),
             "traffic.severity": tree("traffic.severity", "traffic_conflict", "severity", "c", "d"),
             "medical.likelihood": tree("medical.likelihood", "medical_emergency", "likelihood", "e", "f"),
             "medical.severity": tree("medical.severity", "medical_emergency", "severity", "g", "h")}
    levels = {t: [list(d) for d in tr.first_levels] for t, tr in trees.items()}
    counts = {t: [[counts_each * v for v in d] for d in tr.first_levels] for t, tr in trees.items()}
    return Model("first-guess", trees, levels, counts)


ANSWERS = {"a": 1.0, "b": 0.0, "c": 1.0, "d": 1.0, "e": 1.0, "f": 1.0, "g": 0.0, "h": 0.0}
APPLIES = {"traffic_conflict": True, "medical_emergency": False}


def test_a_correction_touches_only_reached_leaves_on_trees_that_apply():
    model = make_model()
    before = {t: [list(d) for d in model.levels[t]] for t in model.levels}
    c0, k = edge(0.05, 0.15)
    changes = net_update(model, ANSWERS, APPLIES, True, c0, k, ANCHORS, {}, GAMMA)
    # The rules send this case to leaf 1 of traffic.likelihood and leaf 0 of traffic.severity.
    assert model.levels["traffic.likelihood"][1] != before["traffic.likelihood"][1]
    assert model.levels["traffic.severity"][0] != before["traffic.severity"][0]
    for leaf in (0, 2, 3):
        assert model.levels["traffic.likelihood"][leaf] == before["traffic.likelihood"][leaf]
    for leaf in (1, 2, 3):
        assert model.levels["traffic.severity"][leaf] == before["traffic.severity"][leaf]
    assert model.levels["medical.likelihood"] == before["medical.likelihood"]
    assert model.levels["medical.severity"] == before["medical.severity"]
    assert {c["tree_id"] for c in changes} == {"traffic.likelihood", "traffic.severity"}
    assert len(changes) == 2


def test_a_blank_name_still_teaches():
    model = make_model()
    before = list(model.levels["traffic.likelihood"][1])
    c0, k = edge(0.05, 0.15)
    net_update(model, ANSWERS, APPLIES, True, c0, k, ANCHORS, {}, GAMMA)
    after = model.levels["traffic.likelihood"][1]
    anchors = ANCHORS["likelihood"]
    assert sum(p * a for p, a in zip(after, anchors)) > sum(p * a for p, a in zip(before, anchors))


def test_not_risky_moves_the_other_way():
    model = make_model()
    before = list(model.levels["traffic.likelihood"][1])
    c0, k = edge(0.0, 0.01)
    net_update(model, ANSWERS, APPLIES, False, c0, k, ANCHORS, {}, GAMMA)
    after = model.levels["traffic.likelihood"][1]
    anchors = ANCHORS["likelihood"]
    assert sum(p * a for p, a in zip(after, anchors)) < sum(p * a for p, a in zip(before, anchors))


def test_a_named_level_is_fixed_as_evidence():
    named, plain = make_model(), make_model()
    c0, k = edge(0.05, 0.15)
    net_update(named, ANSWERS, APPLIES, True, c0, k, ANCHORS, {"traffic.likelihood": 2}, GAMMA)
    net_update(plain, ANSWERS, APPLIES, True, c0, k, ANCHORS, {}, GAMMA)
    assert named.levels["traffic.likelihood"][1][2] > plain.levels["traffic.likelihood"][1][2]


def test_the_one_leaf_hand_calculation_in_the_decision_record():
    """Decision record 0001: [0.056, 0.858, 0.086] on a leaf of 47 cases, right level last, gives [0.055, 0.839, 0.106]."""
    model = make_model()
    tree_id = "traffic.likelihood"
    start = [0.056, 0.858, 0.086]
    model.levels[tree_id][1] = list(start)
    model.counts[tree_id][1] = [47 * v for v in start]
    net_update(model, ANSWERS, APPLIES, None, 0.1, 40, ANCHORS, {tree_id: 2}, GAMMA)
    assert model.levels[tree_id][1] == pytest.approx([0.055, 0.839, 0.106], abs=0.001)
    assert sum(model.levels[tree_id][1]) == pytest.approx(1.0)


def test_changes_show_counts_before_and_after():
    model = make_model()
    c0, k = edge(0.05, 0.15)
    changes = net_update(model, ANSWERS, APPLIES, True, c0, k, ANCHORS, {}, GAMMA)
    for change in changes:
        assert change["count_before"] == pytest.approx(2.0)
        assert change["count_after"] == pytest.approx(2.0 * GAMMA + 1.0)
        assert sum(change["after"]) == pytest.approx(1.0)
