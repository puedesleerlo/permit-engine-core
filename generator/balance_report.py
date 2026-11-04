"""Factor counts, labelled-risky share, share at the ceiling, expected approvals in test, and training cases per leaf,
each with PASS or MISS against the brief. Run: uv run python -m generator.balance_report

Approvals come from a small simulation: noisy simulated reads, trees trained from a flat start on the training labels,
thresholds chosen on validation, then the decision table on the test split. No model calls. No leaf weights are written.
"""
import json
import math
import random
import statistics as st
from collections import Counter

from generator.cards import TREE_QUESTIONS, answer, leaf_counts, tree_applies
from generator.generate import DATA, load_config, load_truth_table
from generator.labels import truth_level

L_ANCHORS = [0.02, 0.10, 0.30]
S_ANCHORS = [0.1, 0.4, 1.0]
CEILING = 0.85
SIMULATIONS = 20
READ_OK = 0.92
PLAN_QUESTIONS = ("traffic_plan_adequate", "crowd_plan_adequate", "medical_plan_adequate", "narrow_venue")
HAZARD_TREES = {"traffic": ("traffic.likelihood", "traffic.severity"), "crowd": ("crowd.likelihood", "crowd.severity"), "medical": ("medical.likelihood", "medical.severity")}


def load_jsonl(name):
    return [json.loads(line) for line in (DATA / name).read_text().splitlines()]


def passes_basic(f):
    return f["form_complete"] and f["fee_paid"] and f["date_allowed"]


def simulated_read(f, rng):
    out = {}
    for question in sorted({q for qs in TREE_QUESTIONS.values() for q in qs}):
        truth = answer(question, f)
        if question in ("escort_confirmed", "ambulance_on_site"):
            said = truth if rng.random() < READ_OK else not truth
            out[question] = 0.9 if said else 0.1
            if question == "escort_confirmed" and f["escort_evidence"] == "contradicting":
                out[question] = 0.05
        elif question in PLAN_QUESTIONS:
            out[question] = rng.betavariate(6, 1.5) if truth else rng.betavariate(1.5, 6)
        else:
            out[question] = 1.0 if truth else 0.0
    return out


def reach(questions, read):
    out = []
    for bits in range(2 ** len(questions)):
        p = 1.0
        for i, q in enumerate(questions):
            p *= read[q] if (bits >> i) & 1 else 1 - read[q]
        out.append(p)
    return out


def fit(tree_id, rows):
    questions = TREE_QUESTIONS[tree_id]
    label_key = tree_id.replace(".crossings", "")
    use = [(reach(questions, r["read"]), r["label"]["levels"][label_key]) for r in rows if passes_basic(r["facts"]) and tree_applies(tree_id, r["facts"])]
    n = 2 ** len(questions)
    theta = [[1 / 3] * 3 for _ in range(n)]
    for _ in range(6):
        counts = [[2 / 3] * 3 for _ in range(n)]
        for r, y in use:
            w = [r[leaf] * theta[leaf][y] for leaf in range(n)]
            z = sum(w) or 1e-9
            for leaf in range(n):
                counts[leaf][y] += w[leaf] / z
        theta = [[v / sum(d) for v in d] for d in counts]
    return theta


def predict(tree_id, theta, read):
    r = reach(TREE_QUESTIONS[tree_id], read)
    return [sum(r[leaf] * theta[leaf][j] for leaf in range(len(r))) for j in range(3)]


def score(model, row):
    risk = highest = 0.0
    for lt, st_ in HAZARD_TREES.values():
        if tree_applies(lt, row["facts"]):
            likelihood = sum(p * a for p, a in zip(predict(lt, model[lt], row["read"]), L_ANCHORS))
            severity = sum(p * a for p, a in zip(predict(st_, model[st_], row["read"]), S_ANCHORS))
            risk += likelihood * severity
            highest = max(highest, severity)
    return risk, highest


def thresholds(rows):
    candidates = sorted({r for r, _ in rows})
    t_low = 0.0
    for t in candidates:
        below = [k for r, k in rows if r < t]
        if below and sum(below) / len(below) <= 0.05:
            t_low = t
    t_high = candidates[-1] + 1e-9
    for t in reversed(candidates):
        above = [k for r, k in rows if r >= t]
        if above and (len(above) - sum(above)) / len(above) <= 0.15:
            t_high = t
    if t_high < t_low:
        t_low = t_high = (t_low + t_high) / 2
    return t_low, t_high


def route_row(f, risk, highest, t_low, t_high):
    if not f["form_complete"]:
        return "0 returned"
    if not (f["fee_paid"] and f["date_allowed"]):
        return "0 proposed_denial"
    if f["escort_evidence"] == "contradicting":
        return "1 red_flag"
    if f["insurance"] == "broker_letter":
        return "1 unmapped_evidence"
    if highest >= CEILING:
        return "1 severity_ceiling"
    if f["insurance"] in ("expired", "wrong_venue"):
        return "2 requirement_failed"
    if f["insurance"] == "missing":
        return "3 requirement_missing"
    if risk < t_low:
        return "4 approved"
    if risk >= t_high:
        return "5 high_risk"
    return "6 review_band"


def tree_loss(tree_id, theta, rows):
    label_key = tree_id.replace(".crossings", "")
    values = [-math.log(max(predict(tree_id, theta, r["read"])[r["label"]["levels"][label_key]], 1e-6))
              for r in rows if passes_basic(r["facts"]) and tree_applies(tree_id, r["facts"])]
    return sum(values) / len(values)


def entropy(d):
    return -sum(p * math.log(p) for p in d if p > 0)


def simulate(rows, seed):
    rng = random.Random(f"balance:{seed}")
    for r in rows:
        r["read"] = simulated_read(r["facts"], rng)
    train = [r for r in rows if r["split"] == "train"]
    validation = [r for r in rows if r["split"] == "validation"]
    test = [r for r in rows if r["split"] == "test"]
    model = {t: fit(t, train) for t in TREE_QUESTIONS}
    eligible = []
    for r in validation:
        if passes_basic(r["facts"]):
            risk, highest = score(model, r)
            if highest < CEILING:
                eligible.append((risk, r["label"]["risky"]))
    t_low, t_high = thresholds(eligible)
    routes = Counter()
    risky_approved = 0
    for r in test:
        risk, highest = score(model, r)
        row = route_row(r["facts"], risk, highest, t_low, t_high)
        routes[row] += 1
        if row == "4 approved":
            risky_approved += r["label"]["risky"]
    at_ceiling = sum(score(model, r)[1] >= CEILING for r in rows) / len(rows)
    return {
        "approved": routes["4 approved"], "risky_approved": risky_approved, "routes": routes, "t_low": t_low, "t_high": t_high, "at_ceiling": at_ceiling,
        "entropy": {t: st.mean(entropy(d) for d in model[t]) for t in model},
        "loss_before": tree_loss("traffic.likelihood", model["traffic.likelihood"], validation),
        "loss_after": tree_loss("traffic.likelihood.crossings", model["traffic.likelihood.crossings"], validation),
    }


def verdict(ok):
    return "PASS" if ok else "MISS"


def main():
    cfg = load_config()
    table = load_truth_table()
    cards = load_jsonl("cards.jsonl")
    labels = {r["case_id"]: r for r in load_jsonl("labels.jsonl")}
    plain = [c for c in cards if c["tone"] == "plain"]
    rows = [{**c, "label": labels[c["case_id"]]} for c in plain]
    results = []

    print("FACTOR COUNTS (plain cases)")
    splits = ["train", "validation", "test"]
    print(f"{'factor':<42}" + "".join(f"{s:>12}" for s in splits))
    def factor(name, fn):
        print(f"{name:<42}" + "".join(f"{sum(1 for c in plain if c['split'] == s and fn(c['facts'])):>12}" for s in splits))
    print(f"{'cases':<42}" + "".join(f"{sum(1 for c in plain if c['split'] == s):>12}" for s in splits))
    factor("fails a basic check", lambda f: not passes_basic(f))
    factor("crowd under 300", lambda f: f["crowd"] < 300)
    factor("crowd 300 to 800", lambda f: 300 <= f["crowd"] <= 800)
    factor("crowd over 800", lambda f: f["crowd"] > 800)
    factor("spectators mentioned", lambda f: f["spectators_mentioned"] > 0)
    factor("road closure", lambda f: f["road_closure"])
    factor("arterial road", lambda f: f["arterial_road"])
    factor("many major crossings", lambda f: f["many_major_crossings"])
    for kind in ("letter", "email", "contradicting"):
        factor(f"escort evidence {kind}", lambda f: f["escort_evidence"] == kind)
    factor("escort evidence none, road closes", lambda f: f["road_closure"] and f["escort_evidence"] == "none")
    factor("escort arranged, no evidence", lambda f: f["road_closure"] and f["escort_evidence"] == "none" and f["escort_arranged"])
    factor("ambulance evidence letter", lambda f: f["ambulance_evidence"] == "letter")
    factor("ambulance arranged, no evidence", lambda f: f["ambulance_evidence"] == "none" and f["ambulance_arranged"])
    factor("traffic plan adequate, road closes", lambda f: f["road_closure"] and f["traffic_plan_adequate"])
    factor("crowd plan adequate, crowd 300+", lambda f: f["crowd"] >= 300 and f["crowd_plan_adequate"])
    factor("medical plan adequate", lambda f: f["medical_plan_adequate"])
    factor("hot date", lambda f: f["hot_date"])
    factor("narrow venue", lambda f: f["narrow_venue"])
    factor("hospital far", lambda f: f["hospital_far"])
    for kind in ("valid", "expired", "wrong_venue", "broker_letter", "missing"):
        factor(f"insurance {kind}", lambda f: f["insurance"] == kind)
    print(f"{'planted':<42}" + "  ".join(f"{k} {v}" for k, v in sorted(Counter(p for c in plain for p in c["planted"]).items())))
    print(f"{'right route':<42}" + "  ".join(f"{k} {v}" for k, v in sorted(Counter(r["label"]["right_route"] for r in rows).items())))
    print(f"{'right route, test':<42}" + "  ".join(f"{k} {v}" for k, v in sorted(Counter(r["label"]["right_route"] for r in rows if r["split"] == "test").items())))
    print(f"{'tone cases':<42}{sum(1 for c in cards if c['split'] == 'tone')}")

    print("\nLABELLED RISKY")
    share = sum(r["label"]["risky"] for r in rows) / len(rows)
    by_split = {s: sum(r["label"]["risky"] for r in rows if r["split"] == s) / sum(1 for r in rows if r["split"] == s) for s in splits}
    print(f"risky cut {cfg['risky_cut']}: {share:.1%} overall; " + ", ".join(f"{s} {v:.1%}" for s, v in by_split.items()))
    results.append(("About 20% labelled risky (18% to 22%)", f"{share:.1%}", 0.18 <= share <= 0.22))

    print("\nSHARE AT THE CEILING")
    severity_trees = ["traffic.severity", "crowd.severity", "medical.severity"]
    labelled = sum(any(r["label"]["levels"][t] == 2 for t in severity_trees) for r in rows) / len(rows)
    clean = sum(any(tree_applies(t, r["facts"]) and truth_level(table, t, r["facts"]) == 2 for t in severity_trees) for r in rows) / len(rows)
    print(f"highest labelled severity critical {labelled:.1%}; before label noise {clean:.1%}")

    sims = [simulate(rows, s) for s in range(SIMULATIONS)]
    approvals = st.mean(s["approved"] for s in sims)
    at_ceiling = st.mean(s["at_ceiling"] for s in sims)
    print(f"highest simulated severity at or over {CEILING}: {at_ceiling:.1%}")
    results.append(("At most 15% at the ceiling, labelled", f"{labelled:.1%}", labelled <= 0.15))
    results.append(("At most 15% at the ceiling, simulated engine", f"{at_ceiling:.1%}", at_ceiling <= 0.15))

    print(f"\nEXPECTED ROUTES IN TEST (mean of {SIMULATIONS} simulated reads of 100 cases)")
    for row in ["0 returned", "0 proposed_denial", "1 red_flag", "1 unmapped_evidence", "1 severity_ceiling", "2 requirement_failed", "3 requirement_missing", "4 approved", "5 high_risk", "6 review_band"]:
        print(f"  row {row:<26}{st.mean(s['routes'][row] for s in sims):>6.1f}")
    risky_approved = sum(s["risky_approved"] for s in sims) / max(sum(s["approved"] for s in sims), 1)
    print(f"  labelled risky among approved {risky_approved:.1%}; t_low {st.mean(s['t_low'] for s in sims):.3f}, t_high {st.mean(s['t_high'] for s in sims):.3f}")
    print(f"  approvals by run: min {min(s['approved'] for s in sims)}, max {max(s['approved'] for s in sims)}")
    results.append(("At least 50 approvals expected in test", f"{approvals:.1f}", approvals >= 50))

    print("\nTRAINING CASES PER LEAF (passing basic checks, hazard applies, answers read correctly)")
    counts = leaf_counts([r for r in rows if r["split"] == "train"])
    for tree_id, leaves in counts.items():
        low = min(leaves.values())
        print(f"  {tree_id:<30} min {low:>3}   " + " ".join(f"{v:>3}" for v in leaves.values()))
        results.append((f"At least 15 per leaf, {tree_id}", str(low), low >= cfg["min_training_cases_per_leaf"]))

    print("\nPLANTED GAP (simulated training; flag rule: highest mean leaf entropy, above 0.6)")
    mean_entropy = {t: st.mean(s["entropy"][t] for s in sims) for t in TREE_QUESTIONS}
    for t, v in mean_entropy.items():
        print(f"  {t:<30} mean leaf entropy {v:.3f}")
    first_trees = {t: v for t, v in mean_entropy.items() if t != "traffic.likelihood.crossings"}
    flagged = max(first_trees, key=first_trees.get)
    before, after = st.mean(s["loss_before"] for s in sims), st.mean(s["loss_after"] for s in sims)
    print(f"  traffic.likelihood validation loss {before:.3f}, with the crossings question {after:.3f}")
    results.append(("Flag falls on traffic.likelihood", f"{flagged} {first_trees[flagged]:.3f}", flagged == "traffic.likelihood" and first_trees[flagged] > 0.6))
    results.append(("Crossings question lowers validation loss", f"{before:.3f} to {after:.3f}", after < before))

    print("\nTARGETS")
    for name, value, ok in results:
        print(f"  {verdict(ok)}  {name}: {value}")
    if not all(ok for _, _, ok in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
