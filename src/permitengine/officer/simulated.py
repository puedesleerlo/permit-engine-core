"""Rules from labels at a stated accuracy, as in experiments/sim_demo_curve.py. Makes no model calls."""
import random

from .base import Ruling

LABEL = "Simulated officer: rules from the labels, standing in for the LLM officer"


class SimulatedOfficer:
    label = LABEL

    def __init__(self, labels: dict, accuracy: float, seed: int = 0):
        self.labels = labels
        self.accuracy = accuracy
        self.seed = seed

    def rule(self, view: dict) -> Ruling:
        case_id = view["case_id"]
        label = self.labels[case_id]
        rng = random.Random(f"{self.seed}:{case_id}")
        accuracy = self.accuracy
        outcome = label["risky"] if rng.random() < accuracy else not label["risky"]
        named = []
        model, answers = view.get("model"), view.get("answers")
        if model is not None and answers is not None:
            for tree_id in sorted(model.trees):
                truth = label["levels"].get(tree_id)
                if truth is None or not view["applies"].get(model.trees[tree_id].hazard):
                    continue
                level = truth if rng.random() < accuracy else rng.choice([j for j in range(3) if j != truth])
                named.append({"tree_id": tree_id, "level": level})
        ruling = "approve" if label["allowed"] and not outcome else "deny"
        word = "risky" if outcome else "not risky"
        return Ruling(ruling, outcome, f"Simulated ruling from the case labels: {word}, so {ruling}.", named)
