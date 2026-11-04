"""Compute levels from the truth table, apply label noise, and derive requirement status, allowed, risky and the right route."""
import random

from generator.cards import hazard_applies

REQUIREMENT_STATUS = {"valid": "met", "expired": "failed", "wrong_venue": "failed", "broker_letter": "missing", "missing": "missing"}


def truth_level(table, tree_id, facts):
    tree = table["trees"][tree_id]
    derived = {**facts, "crowd_over_800": facts["crowd"] > 800}
    values = [derived[f] for f in tree["factors"]]
    for row in tree["rows"]:
        if row[:-1] == values:
            return row[-1]
    raise ValueError(f"truth table {tree_id} has no row for {values}")


def noisy(level, rng, noise):
    if rng.random() >= noise:
        return level
    if level == 0:
        return 1
    if level == 2:
        return 1
    return rng.choice([0, 2])


def make_label(card, cfg, table):
    facts = card["facts"]
    rng = random.Random(f"{cfg['seed']}:noise:{card['base_id']}")
    applies = hazard_applies(facts)
    levels = {}
    risk = 0.0
    for hazard, trees in table["hazards"].items():
        for scale in ("likelihood", "severity"):
            levels[trees[scale]] = noisy(truth_level(table, trees[scale], facts), rng, cfg["label_noise"]) if applies[hazard] else None
        if applies[hazard]:
            risk += table["anchors"]["likelihood"][levels[trees["likelihood"]]] * table["anchors"]["severity"][levels[trees["severity"]]]
    requirements = {"event_insurance": REQUIREMENT_STATUS[facts["insurance"]]}
    allowed = all(s == "met" for s in requirements.values()) and facts["form_complete"] and facts["fee_paid"] and facts["date_allowed"]
    risky = risk >= cfg["risky_cut"]
    if not facts["form_complete"]:
        route = "returned"
    elif not allowed:
        route = "denial"
    elif risky:
        route = "officer"
    else:
        route = "approve"
    return {"case_id": card["case_id"], "applies": applies, "levels": levels, "requirements": requirements,
            "allowed": allowed, "risk": round(risk, 4), "risky": risky, "right_route": route}
