"""The `lint` command. Lives here because the check on training cases per leaf reads cards."""
import yaml

from ..pipeline.case import QUESTIONS
from ..policy.opa import Policy
from ..trees.lint import lint_tree
from ..workspace import EngineError, Workspace
from .labels import load_cards


def lint_all(ws: Workspace) -> dict:
    evidence_map = yaml.safe_load((ws.rules / "evidence_map.yaml").read_text(encoding="utf-8"))
    clause_ids = {c["id"] for c in yaml.safe_load((ws.rules / "ordinance.yaml").read_text(encoding="utf-8"))["clauses"]}
    sample = {"form": {"expected_runners": 1, "event_date": "2027-06-12", "route": {}, "hospital_distance_km": 1}, "extracted": {"expected_spectators": None}}
    rule_ids = set(Policy(ws.rules).one(QUESTIONS, sample))
    train = set(ws.splits()["train"])
    cards = [card for case_id, card in load_cards(ws).items() if case_id in train]
    out = {}
    failed = []
    for path in sorted((ws.rules / "trees").glob("*.yaml")) + sorted((ws.rules / "proposals").glob("*.yaml")):
        tree = yaml.safe_load(path.read_text(encoding="utf-8"))
        errors, notes = lint_tree(tree, evidence_map, clause_ids, rule_ids, cards)
        out[path.name] = {"errors": errors, "notes": notes}
        failed += errors
    if failed:
        raise EngineError("lint failed: " + "; ".join(failed[:10]))
    return out
