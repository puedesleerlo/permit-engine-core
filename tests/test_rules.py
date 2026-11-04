from support import ANOTHER_TESTED_MODEL, OTHER_MODEL, OTHER_VENDOR, OtherProvider, TESTED_MODEL, TESTED_SETTINGS, TESTED_VENDOR, MainProvider
import copy
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from generator.cards import TREE_QUESTIONS, leaf_counts  # noqa: E402

REGO = ROOT / "rules" / "rego"
CAPABILITIES = REGO / "capabilities.json"
PENDING = "first guess pending"
MIN_LEAF = 15


def opa_eval(query, payload):
    run = subprocess.run(
        ["opa", "eval", "--capabilities", str(CAPABILITIES), "--data", str(REGO), "--stdin-input", "--format", "raw", query],
        input=json.dumps(payload), capture_output=True, text=True, check=True,
    )
    return json.loads(run.stdout)


def load_yaml(path):
    return yaml.safe_load(Path(path).read_text())


def rule_question_ids():
    sample = {"form": {"expected_runners": 1, "event_date": "2027-06-12", "route": {}, "hospital_distance_km": 1}, "extracted": {"expected_spectators": None}}
    return set(opa_eval("data.permit.questions.answers", sample))


def combinations(question_ids):
    n = len(question_ids)
    return [{q: not (bits >> (n - 1 - i)) & 1 for i, q in enumerate(question_ids)} for bits in range(2 ** n)]


def lint_tree(tree, evidence_map, clause_ids, rule_ids, training_cards=None):
    """Returns (errors, notes). A tree with leaves: [] is first guess pending, which is not a pass of the leaf check."""
    errors, notes = [], []
    type_ids = {t["id"] for t in evidence_map["evidence_types"]}
    allowed_needs = type_ids | set(evidence_map["form_values"])
    questions = tree["questions"]
    for q in questions:
        if q["clause"] not in clause_ids:
            errors.append(f"unknown clause {q['clause']}")
        if q["kind"] == "rule" and q["id"] not in rule_ids:
            errors.append(f"unknown rule {q['id']}")
        if q["kind"] == "evidence":
            errors += [f"unknown evidence type {t}" for t in q["evidence_types"] if t not in type_ids]
        if q["kind"] == "jev":
            errors += [f"unknown need {n}" for n in q["needs"] if n not in allowed_needs]
    ids = [q["id"] for q in questions]
    if not tree["leaves"]:
        notes.append(PENDING)
    else:
        expected = combinations(ids)
        if [leaf["when"] for leaf in tree["leaves"]] != expected:
            errors.append("leaves are not every combination of the questions, in order, true first")
        for leaf in tree["leaves"]:
            if abs(sum(leaf["levels"]) - 1) > 1e-9:
                errors.append(f"leaf {leaf['when']} does not sum to 1")
    if training_cards is not None:
        key = tree["id"] + ("." + tree["proposal"] if tree.get("proposal") else "")
        for leaf, count in leaf_counts(training_cards)[key].items():
            if count < MIN_LEAF:
                errors.append(f"leaf {leaf} of {key} has {count} training cases, under {MIN_LEAF}")
    return errors, notes


def tree_paths():
    return sorted((ROOT / "rules/trees").glob("*.yaml")) + sorted((ROOT / "rules/proposals").glob("*.yaml"))


@pytest.fixture(scope="module")
def evidence_map():
    return load_yaml(ROOT / "rules/evidence_map.yaml")


@pytest.fixture(scope="module")
def clause_ids():
    return {c["id"] for c in load_yaml(ROOT / "rules/ordinance.yaml")["clauses"]}


@pytest.fixture(scope="module")
def rule_ids():
    return rule_question_ids()


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    from generator import generate
    out = tmp_path_factory.mktemp("rules") / "data"
    generate.main(out)
    return out


@pytest.fixture(scope="module")
def train_cards(data_dir):
    cards = [json.loads(line) for line in (data_dir / "cards.jsonl").read_text().splitlines()]
    return [c for c in cards if c["split"] == "train"]


def test_opa_test_suite_passes():
    run = subprocess.run(["opa", "test", str(REGO), "--capabilities", str(CAPABILITIES)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr


def test_capabilities_block_network_time_random_and_ids(tmp_path):
    caps = json.loads(CAPABILITIES.read_text())
    names = {b["name"] for b in caps["builtins"]}
    assert not [n for n in names if n.startswith(("http.", "net.", "time.", "rand.", "uuid.")) or n == "opa.runtime"]
    for call in ('http.send({"method": "get", "url": "http://x"})', "time.now_ns()", 'rand.intn("a", 1)', 'uuid.rfc4122("a")'):
        policy = tmp_path / "p.rego"
        policy.write_text(f"package probe\n\nv := {call}\n")
        run = subprocess.run(["opa", "eval", "--capabilities", str(CAPABILITIES), "--data", str(policy), "data.probe.v"], capture_output=True, text=True)
        assert run.returncode != 0, call


def test_rule_files_match_schemas(evidence_map):
    jsonschema.validate(evidence_map, json.loads((ROOT / "schemas/evidence_map.json").read_text()))
    tree_schema = json.loads((ROOT / "schemas/tree.json").read_text())
    for path in tree_paths():
        jsonschema.validate(load_yaml(path), tree_schema)
    hazard_schema = json.loads((ROOT / "schemas/hazard.json").read_text())
    for path in (ROOT / "rules/hazards").glob("*.yaml"):
        jsonschema.validate(load_yaml(path), hazard_schema)


def test_real_trees_have_no_lint_errors(evidence_map, clause_ids, rule_ids, train_cards):
    for path in tree_paths():
        errors, notes = lint_tree(load_yaml(path), evidence_map, clause_ids, rule_ids, train_cards)
        assert errors == [], path


def test_empty_leaves_are_pending_and_not_a_pass(evidence_map, clause_ids, rule_ids):
    for path in tree_paths():
        tree = load_yaml(path)
        _, notes = lint_tree(tree, evidence_map, clause_ids, rule_ids)
        assert (PENDING in notes) == (tree["leaves"] == []), path
    tree = load_yaml(ROOT / "rules/trees/traffic.likelihood.yaml")
    tree["leaves"] = []
    errors, notes = lint_tree(tree, evidence_map, clause_ids, rule_ids)
    assert errors == []
    assert notes == [PENDING]


def filled(tree):
    ids = [q["id"] for q in tree["questions"]]
    out = copy.deepcopy(tree)
    out["leaves"] = [{"when": when, "levels": [0.2, 0.3, 0.5]} for when in combinations(ids)]
    return out


def test_lint_accepts_complete_leaves(evidence_map, clause_ids, rule_ids):
    tree = filled(load_yaml(ROOT / "rules/trees/medical.severity.yaml"))
    assert lint_tree(tree, evidence_map, clause_ids, rule_ids) == ([], [])


def test_lint_fails_on_leaf_not_summing_to_one(evidence_map, clause_ids, rule_ids):
    tree = filled(load_yaml(ROOT / "rules/trees/medical.severity.yaml"))
    tree["leaves"][0]["levels"] = [0.5, 0.5, 0.5]
    assert any("does not sum" in e for e in lint_tree(tree, evidence_map, clause_ids, rule_ids)[0])


def test_lint_fails_on_missing_leaf(evidence_map, clause_ids, rule_ids):
    tree = filled(load_yaml(ROOT / "rules/trees/medical.severity.yaml"))
    tree["leaves"].pop()
    assert any("every combination" in e for e in lint_tree(tree, evidence_map, clause_ids, rule_ids)[0])


def test_lint_fails_on_unknown_rule(evidence_map, clause_ids, rule_ids):
    tree = load_yaml(ROOT / "rules/trees/traffic.severity.yaml")
    tree["questions"][0]["id"] = "not_a_rule"
    assert any("unknown rule" in e for e in lint_tree(tree, evidence_map, clause_ids, rule_ids)[0])


def test_lint_fails_on_unknown_evidence_type(evidence_map, clause_ids, rule_ids):
    tree = load_yaml(ROOT / "rules/trees/traffic.likelihood.yaml")
    tree["questions"][0]["evidence_types"] = ["broker_letter"]
    assert any("unknown evidence type" in e for e in lint_tree(tree, evidence_map, clause_ids, rule_ids)[0])


def test_lint_fails_on_unknown_clause(evidence_map, clause_ids, rule_ids):
    tree = load_yaml(ROOT / "rules/trees/traffic.severity.yaml")
    tree["questions"][0]["clause"] = "ORD-99.9"
    assert any("unknown clause" in e for e in lint_tree(tree, evidence_map, clause_ids, rule_ids)[0])


def test_lint_fails_on_too_few_training_cases(evidence_map, clause_ids, rule_ids, train_cards):
    tree = load_yaml(ROOT / "rules/proposals/traffic.likelihood.crossings.yaml")
    errors, _ = lint_tree(tree, evidence_map, clause_ids, rule_ids, train_cards[:60])
    assert any("training cases" in e for e in errors)


def test_tree_files_match_the_brief():
    expected = {
        "traffic.likelihood": ("traffic_conflict", {"escort_confirmed": "evidence", "traffic_plan_adequate": "jev"}),
        "traffic.severity": ("traffic_conflict", {"arterial_road": "rule", "crowd_over_800": "rule"}),
        "crowd.likelihood": ("crowd_pressure", {"crowd_plan_adequate": "jev", "crowd_over_800": "rule"}),
        "crowd.severity": ("crowd_pressure", {"narrow_venue": "jev", "crowd_over_800": "rule"}),
        "medical.likelihood": ("medical_emergency", {"medical_plan_adequate": "jev", "hot_date": "rule"}),
        "medical.severity": ("medical_emergency", {"ambulance_on_site": "evidence", "hospital_far": "rule"}),
    }
    for tree_id, (hazard, questions) in expected.items():
        tree = load_yaml(ROOT / f"rules/trees/{tree_id}.yaml")
        assert tree["id"] == tree_id
        assert tree["hazard"] == hazard
        assert {q["id"]: q["kind"] for q in tree["questions"]} == questions
        assert [q["id"] for q in tree["questions"]] == TREE_QUESTIONS[tree_id]
    proposal = load_yaml(ROOT / "rules/proposals/traffic.likelihood.crossings.yaml")
    assert proposal["authored_in_advance"] is True
    assert [q["id"] for q in proposal["questions"]] == TREE_QUESTIONS["traffic.likelihood.crossings"]
    assert proposal["questions"][-1]["kind"] == "rule"
    assert len(combinations([q["id"] for q in proposal["questions"]])) == 8


def test_hazards_and_event_connect():
    event = load_yaml(ROOT / "rules/events/street_race.yaml")
    assert event["hazards"] == ["traffic_conflict", "crowd_pressure", "medical_emergency"]
    for hazard_id in event["hazards"]:
        hazard = load_yaml(ROOT / f"rules/hazards/{hazard_id}.yaml")
        for scale, tree_id in hazard["trees"].items():
            tree = load_yaml(ROOT / f"rules/trees/{tree_id}.yaml")
            assert tree["hazard"] == hazard_id
            assert tree["scale"] == scale


def test_every_cited_clause_exists(evidence_map, clause_ids):
    cited = {r["clause"] for r in evidence_map["requirements"]} | {d["clause"] for d in evidence_map["does_not_count"]}
    for path in (ROOT / "rules/hazards").glob("*.yaml"):
        cited.add(load_yaml(path)["clause"])
    import re
    for path in REGO.glob("*.rego"):
        cited |= set(re.findall(r"ORD-[0-9]+\.[0-9]+", path.read_text()))
    assert cited <= clause_ids, cited - clause_ids


def test_broker_letter_is_not_in_the_evidence_map(evidence_map):
    assert "broker" not in json.dumps(evidence_map).lower()


def test_evidence_map_requirements_match_rego(evidence_map):
    out = opa_eval("data.permit.requirements.status", {"records": {}})
    for requirement in evidence_map["requirements"]:
        assert out[requirement["id"]] == {"status": "missing", "clause": requirement["clause"], "evidence_type": requirement["evidence_type"]}
    assert set(out) == {r["id"] for r in evidence_map["requirements"]}


def test_evidence_map_terms_and_sources(evidence_map):
    assert set(evidence_map["never_sources"]) == {"form", "cover_letter"}
    for evidence_type in evidence_map["evidence_types"]:
        assert evidence_type["terms"]
        assert evidence_type["allowed_sources"] == ["attachment"]


def test_rego_contract_outputs():
    form = {"organizer": "x", "event_type": "street_race", "event_date": "2027-06-12", "expected_runners": 400, "venue": "v", "description": "d",
            "route": {"road_closure": True, "arterial_road": False, "major_crossings": 1}, "hospital_distance_km": 3, "fee_paid": True, "attachments": []}
    basic = opa_eval("data.permit.basic.result", {"form": form, "fee_paid": True})
    assert basic == {"form_complete": True, "fee_paid": True, "date_allowed": True, "failed": [],
                     "clauses": {"form_complete": "ORD-3.2", "fee_paid": "ORD-3.1", "date_allowed": "ORD-3.3"}}
    answers = opa_eval("data.permit.questions.answers", {"form": form, "extracted": {"expected_spectators": 500}})
    assert answers == {"arterial_road": False, "crowd_over_800": True, "hot_date": True, "hospital_far": False, "many_major_crossings": False}
    applies = opa_eval("data.permit.screen.applies", {"form": form, "extracted": {"expected_spectators": None}})
    assert applies == {"traffic_conflict": True, "crowd_pressure": True, "medical_emergency": True}
    status = opa_eval("data.permit.requirements.status", {"records": {"certificate_of_insurance": {"status": "found", "verdict": "supported", "field_failed": False, "field_mismatch": False}}})
    assert status == {"event_insurance": {"status": "met", "clause": "ORD-7.1", "evidence_type": "certificate_of_insurance"}}
    decision = opa_eval("data.permit.decision.result", {
        "basic": basic, "requirements": status, "evidence_contradicted": False, "unmapped_documents": 0, "model_failure": False,
        "policy_failure": False, "stop_switch": False, "highest_severity": 0.4, "ceiling": 0.85, "risk": 0.1, "t_low": 0.08, "t_high": 0.25})
    assert decision["row"] == 6
    assert decision["route"] == "officer"
    assert decision["reason_code"] == "review_band"
    assert decision["clauses"] == ["ORD-20.2"]
    assert decision["text"].endswith(".")


def test_rego_agrees_with_every_card(data_dir):
    cards = [json.loads(line) for line in (data_dir / "cards.jsonl").read_text().splitlines()]
    payload = {"cases": []}
    for card in cards:
        form = json.loads((data_dir / "applications" / card["case_id"] / "form.json").read_text())
        payload["cases"].append({"form": form, "fee_paid": form["fee_paid"], "extracted": {"expected_spectators": card["facts"]["spectators_mentioned"] or None}})
    query = ("[{\"basic\": b, \"answers\": a, \"applies\": s} | some c in input.cases; "
             "b := data.permit.basic.result with input as c; a := data.permit.questions.answers with input as c; s := data.permit.screen.applies with input as c]")
    results = opa_eval(query, payload)
    assert len(results) == len(cards)
    for card, result in zip(cards, results):
        f = card["facts"]
        assert result["basic"]["form_complete"] == f["form_complete"], card["case_id"]
        assert result["basic"]["fee_paid"] == f["fee_paid"], card["case_id"]
        if f["form_complete"]:
            assert result["basic"]["date_allowed"] == f["date_allowed"], card["case_id"]
            assert result["answers"] == {"arterial_road": f["arterial_road"], "crowd_over_800": f["crowd"] > 800, "hot_date": f["hot_date"],
                                         "hospital_far": f["hospital_far"], "many_major_crossings": f["many_major_crossings"]}, card["case_id"]
            assert result["applies"] == {"traffic_conflict": f["road_closure"], "crowd_pressure": f["crowd"] >= 300, "medical_emergency": True}, card["case_id"]


def settings():
    return yaml.safe_load((ROOT / "settings/settings.yaml").read_text())


def test_settings_match_schema():
    jsonschema.validate(settings(), json.loads((ROOT / "schemas/settings.json").read_text()))


def within_limits(value, limits):
    if "allowed" in limits:
        return value in limits["allowed"]
    values = value if isinstance(value, list) else [value]
    return all(limits["min"] <= v <= limits["max"] for v in values)


def test_every_setting_has_owner_limits_and_a_value_inside_them():
    for setting in settings():
        assert setting["owner"], setting["key"]
        assert setting["limits"], setting["key"]
        assert within_limits(setting["value"], setting["limits"]), setting["key"]
        assert setting["why"] and setting["if_raised"], setting["key"]
        assert setting["recheck_after_days"] > 0, setting["key"]


def test_settings_catalog():
    values = {s["key"]: s["value"] for s in settings()}
    assert values["decision.severity_ceiling"] == 0.85
    assert values["decision.risky_approval_target"] == 0.05
    assert values["decision.high_risk_precision_target"] == 0.85
    assert values["officer.accuracy_simulated"] == 0.9
    assert values["curve.rechoose_every"] == 10
    assert values["corrections.discount"] == 0.93
    assert not [k for k in values if k.startswith("letters.")]


def test_settings_naming_the_vendor_stay_out_of_the_public_list():
    for setting in settings():
        text = json.dumps([setting["key"], setting["value"], setting["why"], setting["if_raised"]]).lower()
        if TESTED_SETTINGS in text or TESTED_VENDOR in text:
            assert setting["public"] is False, setting["key"]
