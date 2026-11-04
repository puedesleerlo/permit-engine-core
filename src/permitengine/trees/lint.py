"""Fail on an unknown rule, evidence type or clause, or a leaf that does not sum to 1. Cards, when given, check training cases per leaf.

A tree with `leaves: []` is first guess pending, which is reported and is not a pass of the leaf check.
"""
from .loader import all_whens

MIN_LEAF = 15
PENDING = "first guess pending"


def read_answer(question: str, facts: dict) -> bool:
    """What a tree sees if the documents are read correctly: evidence, not reality."""
    if question == "escort_confirmed":
        return facts["escort_evidence"] in ("letter", "email") and facts["escort_arranged"]
    if question == "ambulance_on_site":
        return facts["ambulance_evidence"] == "letter" and facts["ambulance_arranged"]
    if question == "crowd_over_800":
        return facts["crowd"] > 800
    return facts[question]


def _applies(hazard: str, facts: dict) -> bool:
    return {"traffic_conflict": facts["road_closure"], "crowd_pressure": facts["crowd"] >= 300, "medical_emergency": True}[hazard]


def leaf_counts(tree: dict, cards: list) -> list:
    ids = [q["id"] for q in tree["questions"]]
    whens = all_whens(ids)
    counts = [0] * len(whens)
    for card in cards:
        facts = card["facts"]
        if facts["form_complete"] and facts["fee_paid"] and facts["date_allowed"] and _applies(tree["hazard"], facts):
            counts[whens.index({q: bool(read_answer(q, facts)) for q in ids})] += 1
    return list(zip(whens, counts))


def lint_tree(tree: dict, evidence_map: dict, clause_ids: set, rule_ids: set, training_cards: list | None = None) -> tuple:
    """Returns (errors, notes)."""
    errors, notes = [], []
    type_ids = {t["id"] for t in evidence_map["evidence_types"]}
    allowed_needs = type_ids | set(evidence_map.get("form_values", []))
    for question in tree["questions"]:
        if question["clause"] not in clause_ids:
            errors.append(f"unknown clause {question['clause']}")
        if question["kind"] == "rule" and question["id"] not in rule_ids:
            errors.append(f"unknown rule {question['id']}")
        if question["kind"] == "evidence":
            errors += [f"unknown evidence type {t}" for t in question["evidence_types"] if t not in type_ids]
        if question["kind"] == "jev":
            errors += [f"unknown need {n}" for n in question["needs"] if n not in allowed_needs]
    ids = [q["id"] for q in tree["questions"]]
    if not tree.get("leaves"):
        notes.append(PENDING)
    else:
        if [leaf["when"] for leaf in tree["leaves"]] != all_whens(ids):
            errors.append("leaves are not every combination of the questions, in order, true first")
        for leaf in tree["leaves"]:
            if abs(sum(leaf["levels"]) - 1) > 1e-9:
                errors.append(f"leaf {leaf['when']} does not sum to 1")
    if training_cards is not None:
        for when, count in leaf_counts(tree, training_cards):
            if count < MIN_LEAF:
                errors.append(f"leaf {when} of {tree['id']} has {count} training cases, under {MIN_LEAF}")
    return errors, notes
