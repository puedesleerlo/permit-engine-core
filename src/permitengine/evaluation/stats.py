"""Wilson intervals, and a bootstrap of paired differences clustered by base request."""
import math
import random

_Z = 1.959963984540054


def wilson(successes: float, n: float) -> tuple:
    if n <= 0:
        return None, None
    p = successes / n
    z2 = _Z * _Z
    denominator = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denominator
    half = _Z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def bootstrap_difference(pairs, clusters=None, samples: int = 2000, seed: int = 1) -> dict:
    """`pairs` are (a, b) per case. Returns the mean of a - b and a 95% interval. `clusters` names each case's base request."""
    if not pairs:
        return {"mean": None, "low": None, "high": None}
    clusters = clusters or list(range(len(pairs)))
    groups = {}
    for (a, b), cluster in zip(pairs, clusters):
        groups.setdefault(cluster, []).append(a - b)
    keys = sorted(groups, key=str)
    rng = random.Random(seed)
    means = []
    for _ in range(samples):
        total, count = 0.0, 0
        for key in rng.choices(keys, k=len(keys)):
            total += sum(groups[key])
            count += len(groups[key])
        means.append(total / count)
    means.sort()
    return {"mean": sum(a - b for a, b in pairs) / len(pairs), "low": means[int(0.025 * samples)], "high": means[int(0.975 * samples)]}
