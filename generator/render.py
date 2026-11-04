"""Turn a card into a form, a cover letter and attachments. No labels appear in the text."""
import calendar
import datetime
import random
import re
from pathlib import Path

import yaml

VARIANTS_DIR = Path(__file__).parent / "variants"
DATE_STYLES = ["long", "american", "iso"]


def load_variants():
    return {path.stem: yaml.safe_load(path.read_text()) for path in sorted(VARIANTS_DIR.glob("*.yaml"))}


def fill(template, slots):
    text = template.format_map(slots)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def fill_line(template, slots):
    return template.format_map(slots)


def clock(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def join_names(names):
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def width(value):
    return f"{value:g}"


def parse(iso):
    return datetime.date.fromisoformat(iso)


def evidence_date(day, style):
    if style == "long":
        return f"{day.day} {day.strftime('%B %Y')}"
    if style == "american":
        return f"{day.strftime('%B')} {day.day}, {day.year}"
    return day.isoformat()


def plain_date(day):
    return f"{day.strftime('%A')} {day.day} {day.strftime('%B %Y')}"


def long_date(day):
    return f"{day.day} {day.strftime('%B %Y')}"


def pick_family(families, split, rng, cfg):
    general = sorted(k for k, v in families.items() if not v.get("test_only"))
    held = sorted(k for k, v in families.items() if v.get("test_only"))
    if split == "test" and held and rng.random() < cfg["mix"]["held_out_family_in_test"]:
        return rng.choice(held)
    return rng.choice(general)


def build_route(facts, world, rng, slots):
    if facts["road_closure"]:
        locals_ = rng.sample(world["local_streets"], rng.randint(3, 5) + 6)
        streets = locals_[: len(locals_) - 6]
        spare = locals_[len(locals_) - 6:]
        first, mid, last = streets[0], streets[len(streets) // 2], streets[-1]
        if facts["arterial_road"]:
            streets = streets[:1] + [rng.choice(world["arterial_roads"])] + streets[1:]
        crossings = rng.sample(world["crossing_roads"], facts["major_crossings"])
        unused = [r for r in world["crossing_roads"] if r not in crossings]
        closure_rows = []
        for i, street in enumerate(streets):
            a, b = rng.sample(spare, 2)
            closure_rows.append((street, a, b))
        cs, re_ = slots["closure_start"], slots["reopen_time"]
        partial = streets[: max(1, len(streets) // 3)]
        crossing_rows = [(c, rng.choice(streets), rng.randint(2, 4)) for c in crossings]
        detour_rows = [(s, *rng.sample(unused, 2), rng.choice(spare)) for s in streets]
        slots.update(
            streets=join_names(streets), first_street=first, mid_street=mid, last_street=last,
            partial_streets=join_names(partial),
            mid_point=mid,
            start_area=f"the top of {first}",
            finish_area=rng.choice(world["squares"]),
            crossing_phrase=join_names(crossings) if crossings else "none",
            closure_lines="\n".join(f"- {s}, {a} to {b}: closed {cs} to {re_}" for s, a, b in closure_rows),
            closure_sentences=" ".join(f"{s} from {a} to {b}, {cs} until {re_}." for s, a, b in closure_rows),
            closure_terse="\n".join(f"{s} ({a}-{b}) {cs}-{re_}" for s, a, b in closure_rows),
            crossing_lines="\n".join(f"- {c} at {s}: {n} traffic marshals with stop/go boards, one supervisor" for c, s, n in crossing_rows),
            crossing_sentences=" ".join(f"At {c}, where it meets {s}, there will be {n} traffic marshals with stop/go boards and a supervisor." for c, s, n in crossing_rows),
            crossing_terse="\n".join(f"{c} x {s}: {n} marshals w/ boards + sup" for c, s, n in crossing_rows),
            detour_lines="\n".join(f"- {s}: traffic diverted via {a} and {b}, signed from {c}" for s, a, b, c in detour_rows),
            detour_sentences=" ".join(f"Traffic off {s} goes via {a} and {b}, signed from {c}." for s, a, b, c in detour_rows),
            detour_terse="\n".join(f"{s}: via {a} + {b}, signs from {c}" for s, a, b, c in detour_rows),
        )
    else:
        path1, path2 = rng.sample(world["paths"], 2)
        start, finish = rng.sample(world["path_points"], 2)
        slots.update(path1=path1, path2=path2, mid_point=path2, start_area=start, finish_area=finish, crossing_phrase="none")


def build_widths(facts, rng, slots):
    if facts["road_closure"]:
        pool = [3.5, 4, 4.5, 5, 5.5] if facts["narrow_venue"] else [9, 10, 11, 12, 14, 16]
    else:
        pool = [2, 2.5, 3, 3.5] if facts["narrow_venue"] else [7, 8, 9, 10, 12]
    w1, w2, w3 = (rng.choice(pool) for _ in range(3))
    slots.update(w1=width(w1), w2=width(w2), w3=width(w3))


def build_slots(card, world, rng):
    f = card["facts"]
    day = parse(f["event_date"])
    org = rng.choice(world["organizers"])
    dist = rng.choice(world["distances"])
    contact = rng.choice(world["people"])
    style = rng.choice(world["event_styles"])
    start = rng.choice([480, 510, 540, 570, 600])
    before = rng.choice([60, 75, 90])
    today = day - datetime.timedelta(days=rng.randint(30, 150))
    sergeant = rng.choice(world["sergeants"])
    sergeant_user = sergeant.split(" ", 1)[1].lower().replace(" ", ".")
    broker_person = rng.choice(world["people"])
    slots = {
        "city": world["city"], "city_upper": world["city"].upper(),
        "organizer": org["name"], "org_short": org["short"],
        "event_name": f"{org['short']} {style} {dist['label'].title()}",
        "contact_name": contact, "contact_first": contact.split()[0],
        "contact_role": rng.choice(world["roles"]),
        "contact_email": f"{contact.split()[0].lower()}@{org['domain']}",
        "contact_phone": f"555-01{rng.randint(10, 99)}",
        "distance": dist["label"], "distance_km": dist["km"],
        "venue": rng.choice(world["venues"]),
        "date_plain": plain_date(day), "today_long": long_date(today),
        "start_time": clock(start), "end_time": clock(start + dist["minutes"]),
        "closure_start": clock(start - before), "reopen_time": clock(start + dist["minutes"] + 30),
        "runners": f["runners"], "crowd": f["crowd"], "spectators": f["spectators_mentioned"],
        "capacity": 50 * round(f["crowd"] * 1.3 / 50 + 0.5),
        "waves": rng.choice([3, 4, 5]),
        "steward_count": max(6, f["crowd"] // 50), "supervisors": max(2, f["crowd"] // 400),
        "post_count": 3, "medic_count": rng.choice([6, 8, 10, 12]), "medic_name": rng.choice(world["people"]),
        "version": f"{rng.randint(1, 3)}.{rng.randint(0, 4)}",
        "consultant": rng.choice(world["consultants"]), "contractor": rng.choice(world["contractors"]),
        "hospital": rng.choice(world["far_hospitals"] if f["hospital_far"] else world["near_hospitals"]),
        "hospital_km": f["hospital_distance_km"],
        "ambulance_provider": rng.choice(world["ambulance_providers"]), "provider_person": rng.choice(world["people"]),
        "sergeant": sergeant, "sergeant_email": f"{sergeant_user}@phps.example",
        "insurer": rng.choice(world["insurers"]), "policy_no": f"{rng.choice(['EL', 'PL', 'GL'])}-{rng.randint(100000, 999999)}",
        "coverage": rng.choice(["$1,000,000", "$2,000,000", "$5,000,000"]),
        "broker": rng.choice(world["brokers"]), "broker_person": broker_person,
        "broker_person_email": f"{broker_person.split()[0].lower()}@brokerage.example",
        "fee_amount": f"${rng.choice([650, 780, 920, 1150])}",
    }
    build_route(f, world, rng, slots)
    build_widths(f, rng, slots)
    slots["_today"] = today
    slots["_day"] = day
    return slots


def ref(rng):
    return f"{rng.choice(['PH', 'EV', 'RQ', 'AG'])}-{rng.randint(10000, 99999)}"


def add_background(text, lines, document, family_key, slots, rng):
    if rng.random() >= 0.6:
        return text
    passages = lines["plan_background"][document]["terse" if family_key == "c" else "prose"]
    paragraphs = text.rstrip("\n").split("\n\n")
    paragraphs.insert(rng.randint(1, len(paragraphs)), fill_line(rng.choice(passages), slots))
    return "\n\n".join(paragraphs) + "\n"


def render_plan(variants, family_key, slots, adequate, facts, rng):
    family = variants["families"][family_key]
    essential = variants.get("essential")
    passages = family["passages"]
    no_crossings = "crossings" in passages and facts["major_crossings"] == 0
    candidates = [c for c in essential if not (c == "crossings" and no_crossings)]
    thin = set() if adequate else set(rng.sample(candidates, rng.choice([2, 2, 3])))
    filled = {}
    for component, states in passages.items():
        if component == "crossings" and no_crossings:
            state = "none"
        elif component in essential:
            state = "thin" if component in thin else "full"
        else:
            state = rng.choice(["full", "thin"])
        filled[component] = fill_line(rng.choice(states[state]), slots)
    return fill(family["layout"], {**slots, **filled, "ref_no": ref(rng)})


def render_race_plan(variants, family_key, slots, facts, rng):
    family = variants["families"][family_key]
    kind = "closure" if facts["road_closure"] else "path"
    shape = "narrow" if facts["narrow_venue"] else "open"
    filled = {
        "course": fill_line(rng.choice(family["passages"]["course"][kind]), slots),
        "width": fill_line(rng.choice(family["passages"]["width"][f"{kind}_{shape}"]), slots),
    }
    return fill(family["layout"], {**slots, **filled, "ref_no": ref(rng)})


def certificate_slots(facts, slots, world, rng):
    day = slots["_day"]
    if facts["insurance"] == "expired":
        month_end = day.replace(day=1) - datetime.timedelta(days=rng.choice([1, 1, 32, 62]))
        end = month_end.replace(day=calendar.monthrange(month_end.year, month_end.month)[1])
        start = end.replace(year=end.year - 1) + datetime.timedelta(days=1)
        issued = start + datetime.timedelta(days=rng.randint(0, 20))
    elif rng.random() < 0.5:
        start, end = datetime.date(2027, 1, 1), datetime.date(2027, 12, 31)
        issued = slots["_today"]
    else:
        start, end = day - datetime.timedelta(days=1), day + datetime.timedelta(days=1)
        issued = slots["_today"]
    venue = rng.choice(world["other_venues"]) if facts["insurance"] == "wrong_venue" else slots["venue"]
    date_style = rng.choice(DATE_STYLES)
    return {"insured_venue": venue, "period_start": evidence_date(start, date_style), "period_end": evidence_date(end, date_style),
            "today_doc": evidence_date(issued, date_style), "ref_no": ref(rng)}


def other_date(day, rng):
    return day + datetime.timedelta(days=rng.choice([-21, -14, -7, 7, 14, 21, 28]))


def dated_slots(slots, day, rng):
    date_style = rng.choice(DATE_STYLES)
    return {**slots, "letter_date": evidence_date(day, date_style), "today_doc": evidence_date(slots["_today"], date_style), "ref_no": ref(rng)}


def add_hidden_instruction(attachments, world, rng):
    name = rng.choice(sorted(n for n in attachments if n.endswith("plan.txt")))
    paragraphs = attachments[name].rstrip("\n").split("\n\n")
    position = rng.randint(1, len(paragraphs))
    paragraphs.insert(position, rng.choice(world["hidden_instructions"]))
    attachments[name] = "\n\n".join(paragraphs) + "\n"
    return name


def render_base(card, cfg, variants, rng):
    """Everything except the cover letter. Returns the form, attachments, slots and families."""
    f = card["facts"]
    world = variants["world"]
    split = card["split"]
    lines = variants["lines"]
    slots = build_slots(card, world, rng)
    families = {}
    attachments = {}

    if f["escort_evidence"] in ("letter", "contradicting"):
        escort_state = "firm" if f["escort_evidence"] == "contradicting" or f["escort_arranged"] else "soft"
    elif f["escort_evidence"] == "email":
        escort_state = "firm" if f["escort_arranged"] else "soft"
    elif f["escort_arranged"]:
        escort_state = "unproven"
    else:
        escort_state = "none"
    if f["ambulance_evidence"] == "letter":
        ambulance_state = "firm" if f["ambulance_arranged"] else "soft"
    else:
        ambulance_state = "unproven" if f["ambulance_arranged"] else "none"
    slots["escort_line"] = fill_line(rng.choice(lines["escort_line"][escort_state]), slots)
    slots["ambulance_line"] = fill_line(rng.choice(lines["ambulance_line"][ambulance_state]), slots)
    spectator_kind = "mentioned" if f["spectators_mentioned"] else "none"
    slots["spectator_sentence"] = fill_line(rng.choice(lines["spectator_sentence"][spectator_kind]), slots)

    families["race_plan"] = pick_family(variants["race_plan"]["families"], split, rng, cfg)
    attachments["race_plan.txt"] = render_race_plan(variants["race_plan"], families["race_plan"], slots, f, rng)

    if f["road_closure"]:
        families["traffic_plan"] = pick_family(variants["traffic_plan"]["families"], split, rng, cfg)
        plan = render_plan(variants["traffic_plan"], families["traffic_plan"], slots, f["traffic_plan_adequate"], f, rng)
        attachments["traffic_plan.txt"] = add_background(plan, lines, "traffic_plan", families["traffic_plan"], slots, rng)
    if f["crowd"] >= 300:
        families["crowd_plan"] = pick_family(variants["crowd_plan"]["families"], split, rng, cfg)
        plan = render_plan(variants["crowd_plan"], families["crowd_plan"], slots, f["crowd_plan_adequate"], f, rng)
        attachments["crowd_plan.txt"] = add_background(plan, lines, "crowd_plan", families["crowd_plan"], slots, rng)
    families["medical_plan"] = pick_family(variants["medical_plan"]["families"], split, rng, cfg)
    plan = render_plan(variants["medical_plan"], families["medical_plan"], slots, f["medical_plan_adequate"], f, rng)
    attachments["medical_plan.txt"] = add_background(plan, lines, "medical_plan", families["medical_plan"], slots, rng)

    if f["escort_evidence"] in ("letter", "contradicting", "email"):
        kind = "email" if f["escort_evidence"] == "email" else "letter"
        family_key = pick_family(variants["escort"][kind]["families"], split, rng, cfg)
        families[f"escort_{kind}"] = family_key
        day = other_date(slots["_day"], rng) if f["escort_evidence"] == "contradicting" else slots["_day"]
        doc = dated_slots(slots, day, rng)
        attachments[f"police_{kind}.txt"] = fill(variants["escort"][kind]["families"][family_key][escort_state], doc)

    if f["ambulance_evidence"] == "letter":
        family_key = pick_family(variants["ambulance"]["families"], split, rng, cfg)
        families["ambulance"] = family_key
        doc = dated_slots(slots, slots["_day"], rng)
        attachments["ambulance_agreement.txt"] = fill(variants["ambulance"]["families"][family_key][ambulance_state], doc)

    if f["insurance"] in ("valid", "expired", "wrong_venue"):
        family_key = pick_family(variants["insurance"]["certificate"]["families"], split, rng, cfg)
        families["insurance_certificate"] = family_key
        doc = {**slots, **certificate_slots(f, slots, world, rng)}
        attachments["insurance.txt"] = fill(variants["insurance"]["certificate"]["families"][family_key]["text"], doc)
    elif f["insurance"] == "broker_letter":
        family_key = pick_family(variants["insurance"]["broker_letter"]["families"], split, rng, cfg)
        families["broker_letter"] = family_key
        doc = dated_slots(slots, slots["_day"], rng)
        attachments["insurance.txt"] = fill(variants["insurance"]["broker_letter"]["families"][family_key]["text"], doc)

    if "hidden_instruction" in card["planted"]:
        add_hidden_instruction(attachments, world, rng)

    d = variants["description"]
    parts = [fill_line(rng.choice(d["intro"]["closure" if f["road_closure"] else "path"]), slots)]
    parts.append(fill_line(rng.choice(d["spectators"][spectator_kind]), slots))
    if "asserted_insurance" in card["planted"]:
        parts.append(rng.choice(d["insurance_asserted"]))
    description = " ".join(p for p in parts if p)

    form = {
        "organizer": slots["organizer"], "event_name": slots["event_name"], "event_type": "street_race",
        "event_date": f["event_date"], "expected_runners": f["runners"], "venue": slots["venue"], "description": description,
        "route": {"road_closure": f["road_closure"], "arterial_road": f["arterial_road"], "major_crossings": f["major_crossings"]},
        "hospital_distance_km": f["hospital_distance_km"], "fee_paid": f["fee_paid"],
        "attachments": sorted(attachments),
    }
    if not f["form_complete"]:
        drop_field(form, rng)
    families["cover_letter"] = pick_family(variants["cover_letter"]["families"], split, rng, cfg)
    slots["attachment_list"] = ", ".join(sorted(attachments))
    slots["_assertions"] = cover_assertions(card, slots, variants, rng)
    slots["_tone_pick"] = rng.randint(0, 1), rng.randint(0, 1)
    return form, attachments, slots, families


def drop_field(form, rng):
    choice = rng.choice(["event_date", "expected_runners", "hospital_distance_km", "organizer", "major_crossings", "venue"])
    if choice == "major_crossings":
        form["route"]["major_crossings"] = None
    elif rng.random() < 0.5:
        form[choice] = None
    else:
        del form[choice]


def cover_assertions(card, slots, variants, rng):
    f = card["facts"]
    a = variants["cover_letter"]["assertions"]
    out = []
    if f["road_closure"] and f["escort_arranged"] and f["escort_evidence"] == "none":
        out.append(fill_line(rng.choice(a["escort_unproven"]), slots))
    if f["ambulance_arranged"] and f["ambulance_evidence"] == "none":
        out.append(fill_line(rng.choice(a["ambulance_unproven"]), slots))
    if "asserted_insurance" in card["planted"]:
        out.append(fill_line(rng.choice(a["insurance_asserted"]), slots))
    return " ".join(out)


def render_cover_letter(variants, family_key, slots, tone):
    doc = variants["cover_letter"]
    tones = doc["tones"][tone]
    pick_open, pick_close = slots["_tone_pick"]
    return fill(doc["families"][family_key]["layout"],
                {**slots, "tone_open": tones["open"][pick_open], "tone_close": tones["close"][pick_close], "assertions": slots["_assertions"]})


def rng_for(cfg, base_id):
    return random.Random(f"{cfg['seed']}:render:{base_id}")
