"""The commands wired together, with no keys in the environment, so nothing here could reach a model."""
import json

import pytest

from conftest import FIRST_GUESS
from support import ANOTHER_TESTED_MODEL, OTHER_MODEL, OTHER_VENDOR, OtherProvider, TESTED_MODEL, TESTED_SETTINGS, TESTED_VENDOR, MainProvider
from permitengine.cli import main


@pytest.fixture(autouse=True)
def no_keys(monkeypatch):
    for name in ("LLM_API_KEY", "JEV_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def run(world, *args):
    main(["--root", str(world.root), *args])


def test_the_whole_offline_path(world, capsys):
    guess = ["--first-guess", str(FIRST_GUESS)]
    run(world, "simulate")
    run(world, "run-demo", "--run-id", "r1", *guess)
    run(world, "train", *guess)
    run(world, "thresholds", *guess)
    run(world, "report", *guess)
    run(world, "removal", *guess)
    run(world, "routing-check", *guess)
    run(world, "make-export", "--run-id", "r1")
    capsys.readouterr()
    run(world, "replay", "--run-id", "r1")
    assert json.loads(capsys.readouterr().out)["mismatched"] == []
    run(world, "release", "--kind", "crossings", "--version", "v1")
    assert (world.export / "manifest.json").exists() and (world.web_data / "manifest.json").exists()
    assert (world.reports / "validation.json").exists() and (world.reports / "removal.json").exists() and (world.reports / "routing_check.json").exists()
    assert json.loads((world.weights / "v1" / "weights.json").read_text())["trees"]["traffic.likelihood"]["questions"][2]["id"] == "many_major_crossings"


@pytest.mark.parametrize("model,name", [(None, "LLM_API_KEY"), (OTHER_MODEL, "LLM_API_KEY")])
def test_read_with_no_key_stops_with_a_clear_message_and_makes_no_call(world, capsys, model, name):
    extra = ["--model", model] if model else []
    with pytest.raises(SystemExit):
        run(world, "read", "--limit", "1", "--split", "train", *extra)
    assert name in capsys.readouterr().err
    assert not (world.ledger / "spend.jsonl").exists()


def test_a_real_run_needs_real_records(world, capsys):
    with pytest.raises(SystemExit):
        run(world, "run-demo", "--run-id", "r2", "--answers", "real", "--first-guess", str(FIRST_GUESS))
    assert "records are missing" in capsys.readouterr().err


def test_lint_runs_on_the_real_rules_and_real_cards_if_generated(capsys):
    from conftest import REPO

    if not (REPO / "data" / "cards.jsonl").exists():
        pytest.skip("the data has not been generated")
    main(["--root", str(REPO), "lint"])
    assert all(row["errors"] == [] for row in json.loads(capsys.readouterr().out).values())


def test_final_report_with_no_records_stops_and_leaves_no_ledger(world, capsys):
    with pytest.raises(SystemExit):
        run(world, "final-report", "--version", "v1", "--first-guess", str(FIRST_GUESS))
    assert not (world.ledger / "test_ledger.json").exists()


def test_unknown_model_stops(world, capsys):
    with pytest.raises(SystemExit):
        run(world, "read", "--limit", "1", "--model", "some-other-model")
    assert "no provider" in capsys.readouterr().err
