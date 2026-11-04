"""Draw case cards from the seed at the stated mix. Reality and evidence are set separately."""
import datetime
import random

TREE_QUESTIONS = {
    "traffic.likelihood": ["escort_confirmed", "traffic_plan_adequate"],
    "traffic.likelihood.crossings": ["escort_confirmed", "traffic_plan_adequate", "many_major_crossings"],
    "traffic.severity": ["arterial_road", "crowd_over_800"],
    "crowd.likelihood": ["crowd_plan_adequate", "crowd_over_800"],
    "crowd.severity": ["narrow_venue", "crowd_over_800"],
    "medical.likelihood": ["medical_plan_adequate", "hot_date"],
    "medical.severity": ["ambulance_on_site", "hospital_far"],
}
HOT_MONTHS = [6, 7, 8]
COOL_MONTHS = [3, 4, 5, 9, 10, 11]
CLOSED_MONTHS = [1, 2, 12]
EVENT_YEAR = 2027


def quota(rng, n, shares):
    """n values in exact proportion to shares, by largest remainder, shuffled."""
    keys = list(shares)
    raw = [n * shares[k] for k in keys]
    counts = [int(r) for r in raw]
    order = sorted(range(len(keys)), key=lambda i: (counts[i] - raw[i], i))
    for i in order[: n - sum(counts)]:
        counts[i] += 1
    out = [k for k, c in zip(keys, counts) for _ in range(c)]
    rng.shuffle(out)
    return out


def yes_no(rng, n, share):
    return quota(rng, n, {True: share, False: 1 - share})


def hazard_applies(facts):
    return {"traffic_conflict": facts["road_closure"], "crowd_pressure": facts["crowd"] >= 300, "medical_emergency": True}


def tree_applies(tree_id, facts):
    hazard = {"traffic": "traffic_conflict", "crowd": "crowd_pressure", "medical": "medical_emergency"}[tree_id.split(".")[0]]
    return hazard_applies(facts)[hazard]


def answer(question, facts):
    """What a tree sees if the documents are read correctly: evidence, not reality."""
    if question == "escort_confirmed":
        return facts["escort_evidence"] in ("letter", "email") and facts["escort_arranged"]
    if question == "ambulance_on_site":
        return facts["ambulance_evidence"] == "letter" and facts["ambulance_arranged"]
    if question == "crowd_over_800":
        return facts["crowd"] > 800
    return facts[question]


def leaf_counts(cards):
    """Training cases per leaf for every tree, counting only cases that pass basic checks and whose hazard applies."""
    out = {}
    for tree_id, questions in TREE_QUESTIONS.items():
        counts = {}
        for bits in range(2 ** len(questions)):
            counts[tuple(not (bits >> (len(questions) - 1 - i)) & 1 for i in range(len(questions)))] = 0
        for card in cards:
            f = card["facts"]
            if f["form_complete"] and f["fee_paid"] and f["date_allowed"] and tree_applies(tree_id, f):
                counts[tuple(answer(q, f) for q in questions)] += 1
        out[tree_id] = counts
    return out


def weekend_date(rng, months):
    month = rng.choice(months)
    while True:
        day = datetime.date(EVENT_YEAR, month, rng.randint(1, 28))
        if day.weekday() >= 5:
            return day.isoformat()


def crowd_numbers(rng, band, mention):
    if band == "under_300":
        crowd = rng.choice([80, 100, 120, 150, 180, 200, 220, 250, 280, 299])
    elif band == "from_300_to_800":
        crowd = rng.choice([300, 320, 350, 400, 450, 500, 550, 600, 650, 700, 750, 800])
    else:
        crowd = rng.choice([801, 850, 900, 950, 1000, 1100, 1200, 1400, 1600, 1800, 2200, 2600])
    if not mention or crowd in (299, 300, 800, 801):
        return crowd, crowd, 0
    spectators = 10 * round(crowd * rng.uniform(0.15, 0.45) / 10)
    return crowd - spectators, crowd, spectators


def draw_split(rng, n, mix):
    n_fail = round(n * mix["basic_fail"])
    m = n - n_fail
    fail_kinds = quota(rng, n_fail, mix["basic_fail_kinds"]) + [None] * m

    n_closure = round(m * mix["road_closure"])
    closure = [True] * n_closure + [False] * (m - n_closure)
    rng.shuffle(closure)
    for _ in range(n_fail):
        closure.insert(0, rng.random() < mix["road_closure"])

    # Stratified traffic draw: escort evidence, then even plan and crossings cells inside confirmed and unconfirmed.
    closed_index = [i for i in range(n) if closure[i] and fail_kinds[i] is None]
    evidence = quota(rng, len(closed_index), mix["escort_evidence"])
    traffic = {i: {"escort_evidence": e} for i, e in zip(closed_index, evidence)}
    for kind, share in mix["escort_arranged_given"].items():
        group = [i for i in closed_index if traffic[i]["escort_evidence"] == kind]
        for i, value in zip(group, yes_no(rng, len(group), share)):
            traffic[i]["escort_arranged"] = value
    cells = [(True, False), (False, True), (True, True), (False, False)]
    for firm in (True, False):
        group = [i for i in closed_index if (traffic[i]["escort_evidence"] in ("letter", "email") and traffic[i]["escort_arranged"]) == firm]
        rng.shuffle(group)
        for pos, i in enumerate(group):
            traffic[i]["traffic_plan_adequate"], traffic[i]["many_major_crossings"] = cells[pos % 4]

    # Crowd bands are exact inside and outside road closures, and arterial is exact inside each band.
    closed_bands = quota(rng, len(closed_index), mix["crowd"])
    open_bands = quota(rng, m - len(closed_index), mix["crowd"])
    for band in mix["crowd"]:
        group = [i for i, b in zip(closed_index, closed_bands) if b == band]
        for i, value in zip(group, yes_no(rng, len(group), mix["arterial_given_closure"])):
            traffic[i]["arterial_road"] = value
    bands = []
    closed_iter, open_iter = iter(closed_bands), iter(open_bands)
    for i in range(n):
        if fail_kinds[i] is None:
            bands.append(next(closed_iter) if closure[i] else next(open_iter))
    mentions = yes_no(rng, m, mix["spectators_mentioned"])
    hot = yes_no(rng, m, mix["hot_date"])
    narrow = yes_no(rng, m, mix["narrow_venue"])
    far = yes_no(rng, m, mix["hospital_far"])
    medical_plan = yes_no(rng, m, mix["medical_plan_adequate"])
    ambulance = quota(rng, m, mix["ambulance_evidence"])
    insurance = quota(rng, m, mix["insurance"])
    hidden = yes_no(rng, m, mix["hidden_instruction"])
    ambulance_arranged = {}
    for kind, share in mix["ambulance_arranged_given"].items():
        group = [j for j in range(m) if ambulance[j] == kind]
        for j, value in zip(group, yes_no(rng, len(group), share)):
            ambulance_arranged[j] = value

    drafts = []
    j = 0
    for i in range(n):
        kind = fail_kinds[i]
        if kind is None:
            band, mention, is_hot, is_narrow, is_far, med_plan, amb, amb_set, ins, hid = (
                bands[j], mentions[j], hot[j], narrow[j], far[j], medical_plan[j], ambulance[j], ambulance_arranged[j], insurance[j], hidden[j])
            j += 1
        else:
            band = rng.choice(list(mix["crowd"]))
            mention = rng.random() < mix["spectators_mentioned"]
            is_hot, is_narrow, is_far, med_plan = (rng.random() < mix[k] for k in ("hot_date", "narrow_venue", "hospital_far", "medical_plan_adequate"))
            amb = rng.choice(["letter", "none"])
            amb_set = rng.random() < mix["ambulance_arranged_given"][amb]
            ins = rng.choice(list(mix["insurance"]))
            hid = False
        runners, crowd, spectators = crowd_numbers(rng, band, mention)
        if i in traffic:
            t = traffic[i]
        elif closure[i]:
            ev = rng.choice(list(mix["escort_evidence"]))
            t = {"escort_evidence": ev, "escort_arranged": rng.random() < mix["escort_arranged_given"][ev],
                 "traffic_plan_adequate": rng.random() < 0.5, "many_major_crossings": rng.random() < 0.5,
                 "arterial_road": rng.random() < mix["arterial_given_closure"]}
        else:
            t = {"escort_evidence": "none", "escort_arranged": False, "traffic_plan_adequate": False, "many_major_crossings": False, "arterial_road": False}
        if closure[i]:
            crossings = rng.choice([3, 3, 4, 4, 5, 6]) if t["many_major_crossings"] else rng.choice([0, 1, 1, 2, 2, 2])
        else:
            crossings = 0
        date_months = CLOSED_MONTHS if kind == "date_not_allowed" else HOT_MONTHS if is_hot else COOL_MONTHS
        distance = rng.choice([11, 12, 14, 16, 18, 22, 27]) if is_far else rng.choice([2, 3, 4, 5, 6, 7, 8, 9, 10])
        date = weekend_date(rng, date_months)
        facts = {
            "runners": runners, "spectators_mentioned": spectators, "crowd": crowd,
            "road_closure": closure[i], "arterial_road": t["arterial_road"], "major_crossings": crossings, "many_major_crossings": crossings >= 3,
            "event_date": date, "hot_date": int(date[5:7]) in HOT_MONTHS, "narrow_venue": is_narrow,
            "hospital_distance_km": distance, "hospital_far": distance > 10,
            "fee_paid": kind != "fee_unpaid", "form_complete": kind != "form_incomplete", "date_allowed": kind != "date_not_allowed",
            "escort_arranged": t["escort_arranged"], "escort_evidence": t["escort_evidence"],
            "ambulance_arranged": amb_set, "ambulance_evidence": amb,
            "traffic_plan_adequate": t["traffic_plan_adequate"], "crowd_plan_adequate": False, "medical_plan_adequate": med_plan,
            "insurance": ins,
        }
        planted = []
        if ins == "wrong_venue":
            planted.append("wrong_venue_insurance")
        if ins == "broker_letter":
            planted.append("broker_letter")
        if t["escort_evidence"] == "contradicting":
            planted.append("letter_other_date")
        if hid:
            planted.append("hidden_instruction")
        drafts.append({"facts": facts, "planted": planted})

    crowded = [d for d in drafts if d["facts"]["crowd"] >= 300]
    for d, value in zip(crowded, yes_no(rng, len(crowded), mix["crowd_plan_adequate"])):
        d["facts"]["crowd_plan_adequate"] = value

    missing = [d for d in drafts if d["facts"]["insurance"] == "missing"]
    for d, value in zip(missing, yes_no(rng, len(missing), mix["asserted_given_missing"])):
        if value:
            d["planted"].append("asserted_insurance")
    return drafts


def draw_cards(cfg):
    mix = cfg["mix"]
    rng = random.Random(f"{cfg['seed']}:cards")
    by_split = {}
    for split, n in cfg["sizes"].items():
        for _ in range(100000):
            drafts = draw_split(rng, n, mix)
            if split != "train":
                break
            counts = leaf_counts(drafts)
            if min(c for leaves in counts.values() for c in leaves.values()) >= cfg["min_training_cases_per_leaf"]:
                break
        else:
            raise SystemExit(f"No draw of {split} met the training-leaf minimum. Change the mix.")
        by_split[split] = drafts
    pool = [(split, d) for split, drafts in by_split.items() for d in drafts]
    rng.shuffle(pool)
    cards = []
    for number, (split, draft) in enumerate(pool, start=1):
        base_id = f"R{number:04d}"
        cards.append({"case_id": f"{base_id}-plain", "base_id": base_id, "split": split, "tone": "plain", "families": {},
                      "planted": draft["planted"], "facts": draft["facts"]})
    return cards
