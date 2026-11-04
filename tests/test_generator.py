import hashlib
import json
import re
import statistics as st
import sys
from collections import Counter
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from generator import generate  # noqa: E402
from generator.cards import TREE_QUESTIONS, leaf_counts  # noqa: E402
from generator.render import load_variants  # noqa: E402

LABEL_WORDS = [
    "adequate", "inadequate", "inadequately", "risky", "severity", "likelihood", "hazard", "hazards", "critical",
    "narrow", "contradicted", "contradicting", "contradiction", "contradicts", "unmapped", "label", "labels", "labelled",
    "likely", "serious", "minor", "rare", "denial", "truth table", "ground truth", "right route", "escort_confirmed",
]
LABEL_PATTERN = re.compile(r"\b(" + "|".join(re.escape(w) for w in LABEL_WORDS) + r")\b", re.IGNORECASE)


def tree_bytes(folder):
    digest = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(folder)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    out = tmp_path_factory.mktemp("first") / "data"
    generate.main(out)
    return out


@pytest.fixture(scope="module")
def cards(data):
    return [json.loads(line) for line in (data / "cards.jsonl").read_text().splitlines()]


@pytest.fixture(scope="module")
def labels(data):
    return {r["case_id"]: r for r in map(json.loads, (data / "labels.jsonl").read_text().splitlines())}


@pytest.fixture(scope="module")
def splits(data):
    return json.loads((data / "splits.json").read_text())


@pytest.fixture(scope="module")
def plain(cards):
    return [c for c in cards if c["tone"] == "plain"]


def documents(data, case_id):
    folder = data / "applications" / case_id
    out = {"cover_letter.txt": (folder / "cover_letter.txt").read_text()}
    for path in sorted((folder / "attachments").iterdir()):
        out[path.name] = path.read_text()
    return out


def form_of(data, case_id):
    return json.loads((data / "applications" / case_id / "form.json").read_text())


def date_forms(iso):
    import datetime
    day = datetime.date.fromisoformat(iso)
    return [iso, f"{day.day} {day.strftime('%B %Y')}", f"{day.strftime('%B')} {day.day}, {day.year}"]


def test_same_seed_gives_identical_bytes(data, tmp_path):
    again = tmp_path / "data"
    generate.main(again)
    assert tree_bytes(data) == tree_bytes(again)
    assert json.loads((data / "manifest.json").read_text()) == json.loads((again / "manifest.json").read_text())


def test_manifest_holds_seed_version_and_hash(data):
    manifest = json.loads((data / "manifest.json").read_text())
    cfg = generate.load_config()
    assert manifest["seed"] == cfg["seed"]
    assert manifest["generator_version"] == cfg["version"]
    assert manifest["dataset_hash"] == generate.dataset_hash(data)


def test_split_sizes_and_disjoint_base_requests(cards, splits):
    assert {k: len(v) for k, v in splits.items()} == {"train": 180, "validation": 120, "test": 100, "tone": 60}
    assert len(cards) == 460
    bases = {name: {case.split("-")[0] for case in ids} for name, ids in splits.items()}
    assert not bases["train"] & bases["validation"]
    assert not bases["train"] & bases["test"]
    assert not bases["validation"] & bases["test"]


def test_tone_cases_are_twenty_test_requests_in_three_tones(cards, splits):
    tone = [c for c in cards if c["split"] == "tone"]
    assert Counter(c["tone"] for c in tone) == {"persuasive": 20, "insistent": 20, "mayor": 20}
    test_bases = {case.split("-")[0] for case in splits["test"]}
    assert {c["base_id"] for c in tone} <= test_bases
    assert len({c["base_id"] for c in tone}) == 20


def test_tones_change_only_the_cover_letter_and_share_labels(data, cards, labels):
    for card in (c for c in cards if c["split"] == "tone"):
        plain_id = f"{card['base_id']}-plain"
        a, b = documents(data, card["case_id"]), documents(data, plain_id)
        assert a.pop("cover_letter.txt") != b.pop("cover_letter.txt")
        assert a == b
        assert form_of(data, card["case_id"]) == form_of(data, plain_id)
        assert {**labels[card["case_id"]], "case_id": plain_id} == labels[plain_id]


def test_records_match_schemas(data, cards, labels):
    card_schema = json.loads((ROOT / "schemas/case_card.json").read_text())
    label_schema = json.loads((ROOT / "schemas/labels.json").read_text())
    form_schema = json.loads((ROOT / "schemas/form.json").read_text())
    for card in cards:
        jsonschema.validate(card, card_schema)
        jsonschema.validate(labels[card["case_id"]], label_schema)
        jsonschema.validate(form_of(data, card["case_id"]), form_schema)


def test_every_case_has_its_files(data, cards):
    for card in cards:
        folder = data / "applications" / card["case_id"]
        form = form_of(data, card["case_id"])
        assert (folder / "cover_letter.txt").exists()
        assert sorted(p.name for p in (folder / "attachments").iterdir()) == form["attachments"]


def test_no_label_words_in_documents(data, cards):
    for card in cards:
        for name, text in documents(data, card["case_id"]).items():
            found = LABEL_PATTERN.findall(text)
            assert not found, (card["case_id"], name, found)
        description = form_of(data, card["case_id"])["description"]
        assert not LABEL_PATTERN.findall(description), (card["case_id"], description)


def test_unfilled_templates_are_absent(data, cards):
    for card in cards:
        for name, text in documents(data, card["case_id"]).items():
            assert "{" not in text and "}" not in text, (card["case_id"], name)


def test_held_out_families_appear_only_in_test(cards):
    variants = load_variants()
    held = {
        "race_plan": variants["race_plan"], "traffic_plan": variants["traffic_plan"], "crowd_plan": variants["crowd_plan"],
        "medical_plan": variants["medical_plan"], "ambulance": variants["ambulance"], "cover_letter": variants["cover_letter"],
        "escort_letter": variants["escort"]["letter"], "escort_email": variants["escort"]["email"],
        "insurance_certificate": variants["insurance"]["certificate"], "broker_letter": variants["insurance"]["broker_letter"],
    }
    held_keys = {doc: {k for k, v in spec["families"].items() if v.get("test_only")} for doc, spec in held.items()}
    assert all(held_keys.values())
    seen_in_test = Counter()
    for card in cards:
        for doc, family in card["families"].items():
            if family in held_keys[doc]:
                assert card["split"] in ("test", "tone"), (card["case_id"], doc)
                seen_in_test[doc] += 1
    for doc in ("race_plan", "traffic_plan", "crowd_plan", "medical_plan", "cover_letter"):
        assert seen_in_test[doc] > 0


def test_facts_are_consistent(plain):
    for card in plain:
        f = card["facts"]
        assert f["crowd"] == f["runners"] + f["spectators_mentioned"]
        assert f["many_major_crossings"] == (f["major_crossings"] >= 3)
        assert f["hospital_far"] == (f["hospital_distance_km"] > 10)
        assert f["hot_date"] == (f["event_date"][5:7] in ("06", "07", "08"))
        if not f["road_closure"]:
            assert f["escort_evidence"] == "none" and not f["arterial_road"] and f["major_crossings"] == 0


def test_form_matches_facts(data, plain):
    for card in plain:
        f = card["facts"]
        form = form_of(data, card["case_id"])
        if f["form_complete"]:
            assert form["expected_runners"] == f["runners"]
            assert form["event_date"] == f["event_date"]
            assert form["hospital_distance_km"] == f["hospital_distance_km"]
            assert form["route"] == {"road_closure": f["road_closure"], "arterial_road": f["arterial_road"], "major_crossings": f["major_crossings"]}
        assert form["fee_paid"] == f["fee_paid"]
        if f["spectators_mentioned"]:
            assert str(f["spectators_mentioned"]) in form["description"]


def test_reality_and_evidence_vary_separately(plain):
    closed = [c["facts"] for c in plain if c["facts"]["road_closure"]]
    assert any(f["escort_arranged"] and f["escort_evidence"] == "none" for f in closed)
    assert any(not f["escort_arranged"] and f["escort_evidence"] == "none" for f in closed)
    assert any(not f["escort_arranged"] and f["escort_evidence"] in ("letter", "email") for f in closed)
    facts = [c["facts"] for c in plain]
    assert any(f["ambulance_arranged"] and f["ambulance_evidence"] == "none" for f in facts)
    assert any(not f["ambulance_arranged"] and f["ambulance_evidence"] == "letter" for f in facts)


def test_planted_patterns_in_every_split(plain):
    for split in ("train", "validation", "test"):
        found = Counter(p for c in plain if c["split"] == split for p in c["planted"])
        for pattern in ("asserted_insurance", "wrong_venue_insurance", "broker_letter", "letter_other_date", "hidden_instruction"):
            assert found[pattern] > 0, (split, pattern)


def test_asserted_insurance_has_a_claim_and_no_document(data, plain):
    for card in (c for c in plain if "asserted_insurance" in c["planted"]):
        form = form_of(data, card["case_id"])
        assert "insur" in form["description"].lower() or "covered" in form["description"].lower()
        assert "insurance.txt" not in form["attachments"]
        assert card["facts"]["insurance"] == "missing"


def test_wrong_venue_certificate_names_another_venue(data, plain):
    checked = 0
    for card in plain:
        if not card["facts"]["form_complete"]:
            continue
        text = documents(data, card["case_id"]).get("insurance.txt")
        venue = form_of(data, card["case_id"])["venue"]
        if card["facts"]["insurance"] == "wrong_venue":
            assert venue not in text
            checked += 1
        elif card["facts"]["insurance"] in ("valid", "expired"):
            assert venue in text
    assert checked > 0


def test_letter_naming_another_date(data, plain):
    for card in plain:
        f = card["facts"]
        if f["escort_evidence"] == "contradicting":
            text = documents(data, card["case_id"])["police_letter.txt"]
            assert not any(form in text for form in date_forms(f["event_date"]))
        elif f["escort_evidence"] in ("letter", "email"):
            name = "police_letter.txt" if f["escort_evidence"] == "letter" else "police_email.txt"
            text = documents(data, card["case_id"])[name]
            assert any(form in text for form in date_forms(f["event_date"]))


def test_broker_letter_is_not_a_certificate(data, plain):
    for card in (c for c in plain if c["facts"]["insurance"] == "broker_letter"):
        text = documents(data, card["case_id"])["insurance.txt"].lower()
        assert "certificate of" not in text
        assert "policy number" not in text and "policy no" not in text


def test_hidden_instructions_sit_in_a_plan(data, plain):
    world = load_variants()["world"]["hidden_instructions"]
    for card in plain:
        docs = documents(data, card["case_id"])
        has_it = any(line in text for line in world for text in docs.values())
        assert has_it == ("hidden_instruction" in card["planted"]), card["case_id"]


def test_insurance_dates_cover_or_miss_the_race(data, plain):
    months = "January February March April May June July August September October November December".split()
    for card in plain:
        f = card["facts"]
        if f["insurance"] == "valid":
            assert "insurance.txt" in documents(data, card["case_id"])
        if f["insurance"] == "expired" and f["date_allowed"]:
            text = documents(data, card["case_id"])["insurance.txt"]
            assert any(m in text for m in months) or re.search(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", text)


def test_plans_differ_in_substance_not_length(data, plain):
    for doc, key in (("traffic_plan", "traffic_plan_adequate"), ("crowd_plan", "crowd_plan_adequate"), ("medical_plan", "medical_plan_adequate")):
        by_family = {}
        for card in plain:
            family = card["families"].get(doc)
            if family:
                length = len(documents(data, card["case_id"])[f"{doc}.txt"])
                by_family.setdefault(family, {True: [], False: []})[card["facts"][key]].append(length)
        for family, groups in by_family.items():
            ratio = st.mean(groups[False]) / st.mean(groups[True])
            assert 0.78 <= ratio <= 1.22, (doc, family, ratio)


def test_right_route_follows_the_labels(cards, labels):
    for card in cards:
        f, label = card["facts"], labels[card["case_id"]]
        met = label["requirements"]["event_insurance"] == "met"
        assert label["allowed"] == (met and f["form_complete"] and f["fee_paid"] and f["date_allowed"])
        if not f["form_complete"]:
            assert label["right_route"] == "returned"
        elif not label["allowed"]:
            assert label["right_route"] == "denial"
        elif label["risky"]:
            assert label["right_route"] == "officer"
        else:
            assert label["right_route"] == "approve"


def test_levels_are_null_when_a_hazard_does_not_apply(cards, labels):
    for card in cards:
        f, label = card["facts"], labels[card["case_id"]]
        assert label["applies"] == {"traffic_conflict": f["road_closure"], "crowd_pressure": f["crowd"] >= 300, "medical_emergency": True}
        for tree in ("traffic.likelihood", "traffic.severity"):
            assert (label["levels"][tree] is None) == (not f["road_closure"])
        for tree in ("crowd.likelihood", "crowd.severity"):
            assert (label["levels"][tree] is None) == (f["crowd"] < 300)


def test_label_risk_follows_levels_and_cut(cards, labels):
    table = generate.load_truth_table()
    cut = generate.load_config()["risky_cut"]
    for card in cards:
        label = labels[card["case_id"]]
        total = 0.0
        for hazard, trees in table["hazards"].items():
            if label["applies"][hazard]:
                total += table["anchors"]["likelihood"][label["levels"][trees["likelihood"]]] * table["anchors"]["severity"][label["levels"][trees["severity"]]]
        assert label["risk"] == pytest.approx(total, abs=1e-4)
        assert label["risky"] == (total >= cut)


def test_label_noise_is_about_eight_percent(plain, labels):
    from generator.labels import truth_level
    table = generate.load_truth_table()
    moved = total = 0
    for card in plain:
        for tree in table["trees"]:
            level = labels[card["case_id"]]["levels"][tree]
            if level is not None:
                total += 1
                moved += level != truth_level(table, tree, card["facts"])
    assert 0.05 <= moved / total <= 0.11


def test_truth_table_covers_every_combination():
    table = generate.load_truth_table()
    for tree, spec in table["trees"].items():
        keys = {tuple(row[:-1]) for row in spec["rows"]}
        assert len(keys) == 2 ** len(spec["factors"]), tree
        assert all(row[-1] in (0, 1, 2) for row in spec["rows"])


def test_truth_table_anchors_match_settings():
    table = generate.load_truth_table()
    settings = {s["key"]: s["value"] for s in yaml.safe_load((ROOT / "settings/settings.yaml").read_text())}
    assert table["anchors"]["likelihood"] == settings["risk.anchors.likelihood"]
    assert table["anchors"]["severity"] == settings["risk.anchors.severity"]


def test_rubric_states_the_risky_cut():
    rubric = (ROOT / "generator/expert_rubric.md").read_text()
    assert f"risk is {generate.load_config()['risky_cut']} or more" in rubric


def test_training_leaves_reach_the_minimum(plain):
    counts = leaf_counts([c for c in plain if c["split"] == "train"])
    assert set(counts) == set(TREE_QUESTIONS)
    for tree, leaves in counts.items():
        assert min(leaves.values()) >= 15, (tree, leaves)
        assert len(leaves) == 2 ** len(TREE_QUESTIONS[tree])


def test_no_leaf_weights_in_generator_or_rules():
    for path in [*(ROOT / "generator").rglob("*.yaml"), *(ROOT / "generator").rglob("*.py")]:
        text = path.read_text()
        assert "levels: [" not in text, path
    for path in [*(ROOT / "rules/proposals").glob("*.yaml")]:
        assert "first_guess" not in str(path), path  # the proposal now holds the blind first guess, from rules/first_guess.json


def test_balance_report_passes(data, monkeypatch, capsys):
    from generator import balance_report
    monkeypatch.setattr(balance_report, "DATA", data)
    balance_report.main()
    out = capsys.readouterr().out
    assert "MISS" not in out
