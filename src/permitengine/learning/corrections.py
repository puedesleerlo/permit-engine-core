"""One Bayesian network: tree levels lead to risk, risk leads to the outcome. See decision record 0001.

Inference is exact, by enumerating the levels of up to six trees. Named levels are fixed as evidence. The shares it
gives each tree's levels are split across leaves as in training, after discounting old counts on the leaves reached.
"""
import math

from ..trees.evaluate import distribution, reach

EPS = 1e-9


def edge(t_low: float, t_high: float) -> tuple:
    """The midpoint of the thresholds, and the slope of the soft edge standing for "risky"."""
    return (t_low + t_high) / 2, min(4 / max(t_high - t_low, 1e-3), 40)


def net_update(model, answers: dict, applies: dict, outcome, c0: float, k: float, anchors: dict, evidence: dict, gamma: float) -> list:
    """Updates `model` in place. `outcome` is True, False or None. `evidence` is {tree id: level}. Returns the changes."""
    pairs = []
    for hazard, scales in sorted(model.by_hazard().items()):
        if applies.get(hazard):
            pairs.append((scales["likelihood"], scales["severity"]))
    amounts = {}
    prior = {}
    for pair in pairs:
        for tree_id in pair:
            amounts[tree_id] = reach(model.trees[tree_id], answers)
            dist = distribution(model.levels[tree_id], amounts[tree_id])
            if tree_id in evidence:
                dist = [p if j == evidence[tree_id] else 0.0 for j, p in enumerate(dist)]
            prior[tree_id] = dist
    posterior = {t: [0.0, 0.0, 0.0] for t in prior}

    def walk(i, weight, risk, chosen):
        if i == len(pairs):
            final = weight
            if outcome is not None:
                sig = 1 / (1 + math.exp(-max(min(k * (risk - c0), 30), -30)))
                final = weight * (sig if outcome else 1 - sig)
            for tree_id, j in chosen:
                posterior[tree_id][j] += final
            return
        lt, st = pairs[i]
        for a in range(3):
            for b in range(3):
                w = weight * prior[lt][a] * prior[st][b]
                if w > 0:
                    walk(i + 1, w, risk + anchors["likelihood"][a] * anchors["severity"][b], chosen + [(lt, a), (st, b)])

    walk(0, 1.0, 0.0, [])
    changes = []
    for tree_id, row in posterior.items():
        total = sum(row) or EPS
        row = [v / total for v in row]
        r = amounts[tree_id]
        before_levels = [list(d) for d in model.levels[tree_id]]
        before_counts = [sum(d) for d in model.counts[tree_id]]
        counts = model.counts[tree_id]
        for l in range(len(r)):
            factor = gamma ** r[l]
            counts[l] = [v * factor for v in counts[l]]
        for j in range(3):
            w = [r[l] * before_levels[l][j] for l in range(len(r))]
            z = sum(w) or EPS
            for l, wi in enumerate(w):
                counts[l][j] += row[j] * wi / z
        model.levels[tree_id] = [[v / sum(d) for v in d] for d in counts]
        tree = model.trees[tree_id]
        for l in range(len(r)):
            if r[l] > 0:
                changes.append({"tree_id": tree_id, "leaf": tree.whens[l], "reach": r[l], "before": before_levels[l],
                                "after": list(model.levels[tree_id][l]), "count_before": before_counts[l],
                                "count_after": sum(counts[l])})
    return changes
