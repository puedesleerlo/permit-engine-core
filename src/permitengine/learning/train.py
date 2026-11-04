"""EM on a fixed tree, starting from the first guess as pseudo-cases. Reads rows it is given, never files."""
import random

from ..trees.evaluate import reach
from ..trees.loader import Model

EPS = 1e-9


def fit(tree, rows, strength: float, iterations: int):
    """`rows` are (answers, level). Returns (levels, counts) per leaf."""
    start = [[strength * v for v in d] for d in tree.first_levels]
    levels = [list(d) for d in tree.first_levels]
    counts = [list(d) for d in start]
    routed = [(reach(tree, answers), level) for answers, level in rows]
    for _ in range(iterations):
        counts = [list(d) for d in start]
        for amounts, level in routed:
            weights = [amounts[l] * levels[l][level] for l in range(len(amounts))]
            total = sum(weights) or EPS
            for l, weight in enumerate(weights):
                counts[l][level] += weight / total
        levels = [[v / sum(d) for v in d] for d in counts]
    return levels, counts


def train_model(trees: dict, rows_by_tree: dict, strength: float, iterations: int, version: str, shuffle_seed: int | None = None) -> Model:
    levels, counts = {}, {}
    for tree_id, tree in trees.items():
        rows = list(rows_by_tree.get(tree_id, []))
        if shuffle_seed is not None:
            shuffled = [level for _, level in rows]
            random.Random(f"{shuffle_seed}:{tree_id}").shuffle(shuffled)
            rows = [(answers, level) for (answers, _), level in zip(rows, shuffled)]
        levels[tree_id], counts[tree_id] = fit(tree, rows, strength, iterations)
    return Model(version, dict(trees), levels, counts)
