"""Build splits.json from the plain cards, and mark the test requests that get tone variants."""
import random


def tone_requests(cards, cfg):
    test_ids = sorted(c["base_id"] for c in cards if c["split"] == "test" and c["facts"]["form_complete"] and c["facts"]["fee_paid"] and c["facts"]["date_allowed"])
    rng = random.Random(f"{cfg['seed']}:tones")
    return sorted(rng.sample(test_ids, cfg["tones"]["requests"]))


def build_splits(cards):
    splits = {"train": [], "validation": [], "test": [], "tone": []}
    for card in cards:
        splits[card["split"]].append(card["case_id"])
    return splits
