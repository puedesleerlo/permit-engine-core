"""The export contract, and what must never appear in it."""
import json

import pytest

from conftest import FIRST_GUESS
from support import ANOTHER_TESTED_MODEL, OTHER_MODEL, OTHER_VENDOR, OtherProvider, TESTED_MODEL, TESTED_SETTINGS, TESTED_VENDOR, MainProvider
from permitengine.models.providers import vendor_words
from permitengine.evaluation.demo import run_demo
from permitengine.evaluation.report import train_candidates
from permitengine.evaluation.simulated_answers import simulate
from permitengine.export.make import make_export, scan_folder, scan_text
from permitengine.workspace import EngineError

EVENT_TYPES = {"case.submitted", "checks.done", "evidence.linked", "evidence.judged", "requirements.checked", "hazards.screened", "trees.evaluated", "risk.computed", "decision.made",
               "officer.ruled", "correction.made", "weights.updated", "thresholds.rechosen", "permit.issued", "change.released"}


@pytest.fixture
def exported(world):
    simulate(world)
    run_demo(world, "r1", first_guess_dir=FIRST_GUESS)
    train_candidates(world, "simulated", None, FIRST_GUESS)
    make_export(world, "r1")
    return world


def load(world, name):
    return json.loads((world.export / name).read_text(encoding="utf-8"))


def test_manifest_matches_the_contract(exported):
    manifest = load(exported, "manifest.json")
    assert set(manifest) >= {"run_id", "created_at", "source", "synthetic", "officer_label", "jev_model", "case_count", "event_count", "officer_accuracy", "notes"}
    assert manifest["source"] == "simulated" and manifest["synthetic"] is True and manifest["case_count"] == 24
    assert manifest["event_count"] == len(load(exported, "events.json"))
    assert any("synthetic" in note for note in manifest["notes"]) and any("simulated" in note for note in manifest["notes"])


def test_events_are_in_order_and_of_known_types(exported):
    events = load(exported, "events.json")
    assert [e["seq"] for e in events] == sorted(e["seq"] for e in events)
    for event in events:
        assert set(event) >= {"seq", "sim_time", "case_id", "type", "actor", "simulated", "summary"}
        assert event["type"] in EVENT_TYPES
        if event["type"] in ("correction.made", "thresholds.rechosen"):
            assert "learning_index" in event
    assert all(e["simulated"] for e in events if e["type"] == "officer.ruled")


def test_cases_list_and_case_files_match_the_contract(exported):
    cases = load(exported, "cases.json")
    assert len(cases) == 24
    for row in cases:
        assert set(row) >= {"case_id", "title", "first_seq", "decided_seq", "route", "reason_code", "row", "risk", "t_low", "t_high", "weights_version", "officer", "corrected", "label_risky", "agreed_with_label"}
        detail = load(exported, f"cases/{row['case_id']}.json")
        assert set(detail) >= {"case_id", "title", "documents", "checks", "evidence", "unmapped_documents", "requirements", "hazards", "risk", "highest_severity", "t_low", "t_high", "ceiling", "decision", "officer", "correction", "manifest", "events"}
        assert set(detail["documents"]) == {"form", "cover_letter", "attachments"}
        assert detail["decision"]["route"] == row["route"]
        for hazard in detail["hazards"]:
            assert set(hazard) >= {"id", "name", "applies", "why", "likelihood", "severity", "product"}
            if not hazard["applies"]:
                assert hazard["likelihood"] is None and hazard["severity"] is None
            else:
                block = hazard["likelihood"]
                assert set(block) >= {"tree_id", "value", "entropy", "levels", "level_names", "questions", "leaves"}
                assert sum(leaf["contribution"] for leaf in block["leaves"]) == pytest.approx(block["value"])
                assert set(block["leaves"][0]) >= {"when", "reach", "levels", "count", "entropy", "contribution"}
                assert set(block["questions"][0]) >= {"id", "kind", "text", "answer", "clause"}
        if detail["correction"]:
            assert detail["correction"]["bucket"] in ("ai_wrong", "confirmed")
            assert set(detail["correction"]["changes"][0]) >= {"tree_id", "leaf", "before", "after", "count_before", "count_after"}


def test_learning_matches_the_contract(exported):
    learning = load(exported, "learning.json")
    assert set(learning) >= {"curve", "cards", "arms", "final_test", "trees", "crossings", "corrections", "officer"}
    assert set(learning["curve"][0]) >= {"index", "corrections", "seq", "decided_without_officer", "precision", "loss", "t_low", "t_high", "held_out_cases"}
    assert learning["cards"]["final"]["decided_without_officer"] == learning["curve"][-1]["decided_without_officer"]
    assert [a["name"] for a in learning["arms"]] == ["First guess", "Trained on labelled cases", "Shuffled labels (control)", "One LLM reads and decides (baseline)", "Jev asked directly"]
    assert learning["arms"][1]["split"] == "validation" and learning["arms"][4]["status"] == "not_run"
    assert learning["final_test"]["status"] == "not_run" and learning["final_test"]["verdict"] is None
    assert all(c["passed"] is None for c in learning["final_test"]["conditions"])
    assert len(learning["trees"]) == 6
    assert set(learning["trees"][0]) >= {"tree_id", "mean_leaf_entropy", "flagged", "loss", "leaves"}
    assert set(learning["trees"][0]["leaves"][0]) >= {"when", "count", "entropy", "levels_first", "levels_now"}
    assert set(learning["crossings"]) >= {"status", "loss_before", "loss_after", "text"}
    assert set(learning["officer"]) >= {"reviewed", "corrections", "accuracy", "label"}


def test_rules_are_public_only(exported):
    rules = load(exported, "rules.json")
    assert set(rules) == {"ordinance", "evidence_types", "requirements", "does_not_count", "settings", "hazards"}
    keys = [row["key"] for row in rules["settings"]]
    assert "decision.severity_ceiling" in keys
    assert not [k for k in keys if k.startswith((f"models.{TESTED_SETTINGS}", "prices."))]
    assert set(rules["settings"][0]) >= {"key", "value", "limits", "owner", "why", "if_raised"}
    assert {"id", "text"} == set(rules["ordinance"][0])


def test_export_is_copied_for_the_web_and_holds_no_vendor_name_or_key(exported):
    assert scan_folder(exported.export) == []
    assert sorted(p.name for p in exported.web_data.iterdir()) == sorted(p.name for p in exported.export.iterdir())
    assert len(list((exported.web_data / "cases").iterdir())) == 24


def test_a_vendor_name_in_any_file_fails_and_leaves_the_old_export(exported):
    before = load(exported, "manifest.json")
    web_before = (exported.web_data / "manifest.json").read_text(encoding="utf-8")
    text = exported.settings_file.read_text(encoding="utf-8")
    hidden = "key: models.@S.id\n  value: @M\n  limits: {allowed: [@M]}\n  owner: project_owner\n  moves_by: person_only\n  recheck_after_days: 30\n  public: false".replace("@S", TESTED_SETTINGS).replace("@M", TESTED_MODEL)
    assert hidden in text
    exported.settings_file.write_text(text.replace(hidden, hidden.replace("public: false", "public: true")), encoding="utf-8")
    with pytest.raises(EngineError, match="names a vendor"):
        make_export(exported, "r1")
    assert load(exported, "manifest.json") == before
    assert (exported.web_data / "manifest.json").read_text(encoding="utf-8") == web_before
    assert not [p for p in (exported.root / "export").iterdir() if p.name.startswith("demo-")]


def test_a_simulated_export_never_shows_a_real_final_result(exported):
    (exported.reports / "final.json").write_text(json.dumps({"answers": "real", "status": "run", "verdict": "pass", "conditions": [], "arms": [{"name": "First guess"}]}), encoding="utf-8")
    make_export(exported, "r1")
    assert load(exported, "learning.json")["final_test"]["status"] == "not_run"


def test_candidates_trained_on_other_answers_are_not_shown(exported):
    path = exported.weights / "candidates" / "trained" / "weights.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    body["fitted_on"]["answers"] = "real"
    path.write_text(json.dumps(body), encoding="utf-8")
    make_export(exported, "r1")
    assert all(arm["status"] == "not_run" for arm in load(exported, "learning.json")["arms"])


@pytest.mark.parametrize("text", ["sk-ant-api03-abcdefghijklmnopqrstuvwxyz", "Authorization: Bearer abcdefghijklmnopqrstuvwx", "the api_key is here", "AKIAABCDEFGHIJKLMNOP",
                                  "token aB3dE6gH9jK2mN5pQ8sT1vW4yZ7bC0eF3hJ6kL9n"])
def test_anything_resembling_a_key_fails(text):
    assert any("key" in why for why in scan_text(text))


def test_a_key_in_the_environment_is_looked_for_by_value(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "plainwordsecret")
    assert scan_text("this holds plainwordsecret somewhere") == ["holds a key"]


@pytest.mark.parametrize("text", [*vendor_words(), TESTED_MODEL.title(), TESTED_VENDOR.upper(), OTHER_MODEL])
def test_vendor_and_model_names_fail(text):
    assert any("vendor" in why for why in scan_text(text))


@pytest.mark.parametrize("text", ["an agentic LLM read this", "Jev and TypeSafe and Rego and OPA", "27597bc48e063d04d8a1a6a2f5a575dd1d87f028e8667b8931a532bf9fc04691", "Octopus Running Club", "police_escort_letter"])
def test_public_words_and_hashes_pass(text):
    assert scan_text(text) == []
