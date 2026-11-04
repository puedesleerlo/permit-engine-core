"""Routing through one tree: reach per leaf, the level distribution, its value on the anchors, entropy and contributions."""
import math

LOSS_FLOOR = 1e-6


def entropy(dist) -> float:
    return -sum(p * math.log(p) for p in dist if p > 0)


def reach(tree, answers: dict) -> list:
    """How much of the case arrives at each leaf. A missing answer goes half each way; the pipeline flags it as a failure."""
    out = []
    for when in tree.whens:
        amount = 1.0
        for question_id, branch in when.items():
            yes = answers.get(question_id, 0.5)
            amount *= yes if branch else 1 - yes
        out.append(amount)
    return out


def distribution(levels, amounts) -> list:
    return [sum(amounts[l] * levels[l][j] for l in range(len(amounts))) for j in range(3)]


def evaluate(tree, levels, counts, answers: dict, anchors) -> dict:
    amounts = reach(tree, answers)
    dist = distribution(levels, amounts)
    value = sum(p * a for p, a in zip(dist, anchors))
    leaves = []
    for l, when in enumerate(tree.whens):
        leaf_value = sum(p * a for p, a in zip(levels[l], anchors))
        leaves.append({"when": when, "reach": amounts[l], "levels": list(levels[l]), "count": sum(counts[l]),
                       "entropy": entropy(levels[l]), "contribution": amounts[l] * leaf_value})
    return {"tree_id": tree.id, "value": value, "entropy": entropy(dist), "levels": dist, "leaves": leaves}


def loss(tree, levels, answers: dict, level: int) -> float:
    dist = distribution(levels, reach(tree, answers))
    return -math.log(max(dist[level], LOSS_FLOOR))
