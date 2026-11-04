"""Choose t_low and t_high from (risk, labelled risky) pairs, by the stated rule."""
EPS = 1e-9


def choose(rows, risky_target: float, high_precision_target: float) -> dict:
    notes = []
    candidates = sorted({r for r, _ in rows})
    if not candidates:
        return {"t_low": 0.0, "t_high": EPS, "notes": ["no cases to choose thresholds on"]}
    t_low = 0.0
    found_low = False
    for t in candidates:
        below = [k for r, k in rows if r < t]
        if below and sum(below) / len(below) <= risky_target:
            t_low = t
            found_low = True
    t_high = candidates[-1] + EPS
    found_high = False
    for t in reversed(candidates):
        above = [k for r, k in rows if r >= t]
        if above and sum(above) / len(above) >= high_precision_target:
            t_high = t
            found_high = True
    if not found_low:
        notes.append("no value of t_low meets the risky-approval target, so nothing is approved automatically")
    if not found_high:
        notes.append("no value of t_high meets the precision target, so nothing is marked high risk")
    if t_high < t_low:
        t_low = t_high = (t_low + t_high) / 2
        notes.append("the thresholds crossed, so both take their midpoint and there is no review band")
    return {"t_low": t_low, "t_high": t_high, "notes": notes}
