"""A small world, using the real rules, Rego and settings, with hand-made cases and a temporary first guess."""
import json
import random
import shutil
from pathlib import Path

import pytest

from permitengine.pipeline.case import load_context
from permitengine.workspace import Workspace

REPO = Path(__file__).parents[1]
FIRST_GUESS = REPO / "tests" / "fixtures" / "first_guess"
COVER_MARKER = "COVERLETTERMARKER"
TRAFFIC_GOOD = "Traffic plan. Every closed road, a staffed control at each major crossing, signed diversions and a clear way for ambulances."
RACE_PLAN = "Race plan. Course on wide carriageways, 16 metres kerb to kerb, start in an open square."
CROWD_PLAN = "Crowd plan. Marked areas with capacities, a staged start and stewards in stated positions."
MEDICAL_PLAN = "Medical plan. Staffed first aid posts, a named hospital and a named qualified lead."


def insurance(organizer="Test Club", venue="South Pier", start="2027-01-01", end="2027-12-31"):
    return (f"CERTIFICATE OF LIABILITY INSURANCE\nNAMED INSURED: {organizer}\nVENUE: {venue}, Port Halden\n"
            f"Effective: {start}\nExpiry: {end}\nLIMIT OF LIABILITY: $2,000,000 each occurrence\n")


def police_letter(day="2027-05-16"):
    return f"PORT HALDEN POLICE SERVICE\nFebruary 27, 2027\nRe: Test Race, {day}\nI confirm a police escort for the above event on {day}.\nSgt. Miguel Santos\n"


def ambulance(day="2027-05-16"):
    return f"EVENT MEDICAL SERVICES AGREEMENT\nBetween: Harbour Ambulance (\"the Provider\")\nEvent date: {day}\nOne ambulance stays on site.\n"


def form(**changes) -> dict:
    body = {"organizer": "Test Club", "event_name": "Test Race 5K", "event_type": "street_race", "event_date": "2027-05-16", "expected_runners": 400, "venue": "South Pier",
            "description": "A 5K road race.", "route": {"road_closure": True, "arterial_road": False, "major_crossings": 1}, "hospital_distance_km": 3, "fee_paid": True, "attachments": []}
    body.update(changes)
    return body


def write_case(ws: Workspace, case_id: str, body: dict, attachments: dict, cover: str = f"Hello. {COVER_MARKER} I know the mayor. Please approve.") -> None:
    folder = ws.data / "applications" / case_id
    (folder / "attachments").mkdir(parents=True, exist_ok=True)
    body = {**body, "attachments": sorted(attachments)}
    (folder / "form.json").write_text(json.dumps(body), encoding="utf-8")
    (folder / "cover_letter.txt").write_text(cover, encoding="utf-8")
    for name, text in attachments.items():
        (folder / "attachments" / name).write_text(text, encoding="utf-8")


def _world_case(rng: random.Random, case_id: str):
    """Hidden truth for the small world: an unproved escort, bad plans and a big crowd raise the levels."""
    escort, plan_ok, crowd_ok, medical_ok, ambulance_on = (rng.random() < 0.5 for _ in range(5))
    road, big = rng.random() < 0.7, rng.random() < 0.3
    runners = 900 if big else 400
    facts = {"runners": runners, "spectators_mentioned": 0, "crowd": runners, "road_closure": road, "arterial_road": False, "major_crossings": 1, "many_major_crossings": False, "event_date": "2027-05-16",
             "hot_date": False, "narrow_venue": False, "hospital_distance_km": 3, "hospital_far": False, "fee_paid": True, "form_complete": True, "date_allowed": True, "escort_arranged": escort,
             "escort_evidence": ("letter" if escort else "none") if road else "none", "ambulance_arranged": ambulance_on, "ambulance_evidence": "letter" if ambulance_on else "none",
             "traffic_plan_adequate": plan_ok, "crowd_plan_adequate": crowd_ok, "medical_plan_adequate": medical_ok, "insurance": "valid"}
    attachments = {"insurance.txt": insurance(), "race_plan.txt": RACE_PLAN, "crowd_plan.txt": CROWD_PLAN, "medical_plan.txt": MEDICAL_PLAN}
    if road:
        attachments["traffic_plan.txt"] = TRAFFIC_GOOD
        if escort:
            attachments["police_letter.txt"] = police_letter()
    if ambulance_on:
        attachments["ambulance_agreement.txt"] = ambulance()
    traffic_l = (not escort) + (not plan_ok)
    medical_l = 1 - medical_ok
    medical_s = 1 - ambulance_on
    crowd_l = 1 - crowd_ok
    levels = {"traffic.likelihood": traffic_l if road else None, "traffic.severity": (1 if big else 0) if road else None, "crowd.likelihood": crowd_l, "crowd.severity": 1 if big else 0,
              "medical.likelihood": medical_l, "medical.severity": medical_s}
    risky = (traffic_l == 2 and road) or (crowd_l and big)
    label = {"case_id": case_id, "applies": {"traffic_conflict": road, "crowd_pressure": True, "medical_emergency": True}, "levels": levels, "requirements": {"event_insurance": "met"},
             "allowed": True, "risk": 0.2 if risky else 0.05, "risky": risky, "right_route": "officer" if risky else "approve"}
    card = {"case_id": case_id, "base_id": case_id.split("-")[0], "split": None, "tone": "plain", "families": {}, "planted": [], "facts": facts}
    return form(expected_runners=runners, route={"road_closure": road, "arterial_road": False, "major_crossings": 1}), attachments, card, label


def build_world(root: Path, n_train=30, n_validation=24, n_test=12, seed=5) -> Workspace:
    ws = Workspace(root)
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO / "rules", root / "rules")
    shutil.copytree(REPO / "settings", root / "settings")
    (root / "generator").mkdir()
    (root / "generator" / "expert_rubric.md").write_text("Fixture rubric. RUBRICMARKER. A race with no escort and a bad plan is risky.", encoding="utf-8")
    rng = random.Random(seed)
    splits, cards, labels = {"train": [], "validation": [], "test": [], "tone": []}, [], []
    number = 0
    for split, count in (("train", n_train), ("validation", n_validation), ("test", n_test)):
        for _ in range(count):
            number += 1
            case_id = f"R{number:04d}-plain"
            body, attachments, card, label = _world_case(rng, case_id)
            card["split"] = split
            write_case(ws, case_id, body, attachments)
            splits[split].append(case_id)
            cards.append(card)
            labels.append(label)
    (ws.data / "splits.json").write_text(json.dumps(splits), encoding="utf-8")
    (ws.data / "manifest.json").write_text(json.dumps({"seed": seed, "generator_version": "fixture", "dataset_hash": f"fixture-{seed}"}), encoding="utf-8")
    (ws.data / "cards.jsonl").write_text("\n".join(json.dumps(c) for c in cards) + "\n", encoding="utf-8")
    (ws.data / "labels.jsonl").write_text("\n".join(json.dumps(l) for l in labels) + "\n", encoding="utf-8")
    return ws


@pytest.fixture(scope="session")
def world_template(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("template") / "world"
    build_world(root)
    return root


@pytest.fixture
def world(world_template, tmp_path) -> Workspace:
    root = tmp_path / "world"
    shutil.copytree(world_template, root)
    return Workspace(root)


@pytest.fixture
def ctx(world):
    return load_context(world, FIRST_GUESS)
