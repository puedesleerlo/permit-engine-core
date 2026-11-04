"""risk = sum over hazards that apply of likelihood x severity. No policy values live here: anchors come from settings."""
from ..trees.evaluate import evaluate


def score(model, answers: dict, applies: dict, anchors: dict) -> dict:
    hazards = {}
    risk = 0.0
    highest = 0.0
    for hazard, scales in sorted(model.by_hazard().items()):
        if not applies.get(hazard):
            hazards[hazard] = {"applies": False, "likelihood": None, "severity": None, "product": 0.0}
            continue
        out = {"applies": True}
        for scale in ("likelihood", "severity"):
            tree_id = scales[scale]
            out[scale] = evaluate(model.trees[tree_id], model.levels[tree_id], model.counts[tree_id], answers, anchors[scale])
        out["product"] = out["likelihood"]["value"] * out["severity"]["value"]
        risk += out["product"]
        highest = max(highest, out["severity"]["value"])
        hazards[hazard] = out
    return {"hazards": hazards, "risk": risk, "highest_severity": highest}


def risk_only(model, answers: dict, applies: dict, anchors: dict) -> float:
    return score(model, answers, applies, anchors)["risk"]
