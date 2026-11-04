"""`uv run permitengine <command>`. Offline commands need no keys. `read`, a real officer, `baseline` and `direct-jev` go through the keys named in .env.example."""
import argparse
import json
import sys
from pathlib import Path

from .workspace import EngineError, Workspace


def _print(value) -> None:
    print(json.dumps(value, indent=1, sort_keys=True, default=str))


def _simulate(ws, args):
    from .evaluation.simulated_answers import simulate

    return simulate(ws, args.seed)


def _read(ws, args):
    from .evaluation.read_report import compare_with_cards
    from .models.budget import Budget
    from .models.jev import JevClient
    from .models.llm import LlmClient, choose_model
    from .pipeline.case import load_context
    from .reading.read import RealReader, read_many
    from .store.cache import Cache
    from .store.records import records_dir

    ctx = load_context(ws)
    settings = ctx.settings
    model = choose_model(settings, args.model)
    jev_model = settings.get("models.jev.id")
    if not jev_model:
        raise EngineError("models.jev.id is not set in settings")
    budget = Budget(ws.ledger / "spend.jsonl", settings.get("budget.max_usd_total"), settings.get("budget.max_jev_input_tokens"))
    cache = Cache(ws.cache / "answers")
    llm = LlmClient.from_env(settings, cache, budget, model)
    jev = JevClient.from_env(jev_model, cache, budget, settings.get("models.max_concurrency"))
    case_ids = ws.splits()[args.split]
    if args.limit:
        case_ids = case_ids[:args.limit]
    folder = records_dir(ws, "real", model)
    start = budget.entries()
    result = read_many(ws, case_ids, RealReader(ws, llm, jev), ctx, folder, settings.get("models.max_concurrency"))
    report = {"model": model, "split": args.split, "cases_read": len(result["done"]), "stopped_by": result["stopped_by"], "calls_made": {"llm": llm.calls, "jev": jev.calls},
              "answered_from_stored": {"llm": llm.stored_hits, "jev": jev.stored_hits}, "used_by_this_read": budget.usage_since(start), "meter": budget.summary()}
    if args.split in ("train", "validation"):  # test cards stay closed before the one look
        report["against_cards"] = compare_with_cards(ws, result["done"], folder)
    return report


def _fg(args) -> Path | None:
    return Path(args.first_guess).resolve() if args.first_guess else None


def _run_demo(ws, args):
    from .evaluation.demo import run_demo

    return run_demo(ws, args.run_id, args.answers, args.officer, args.model, _fg(args))


def _train(ws, args):
    from .evaluation.report import train_candidates

    return train_candidates(ws, args.answers, args.model, _fg(args))


def _thresholds(ws, args):
    from .evaluation.report import choose_candidate_thresholds

    return choose_candidate_thresholds(ws, args.answers, args.model, _fg(args))


def _report(ws, args):
    from .evaluation.report import validation_report

    return validation_report(ws, args.answers, args.model, _fg(args))


def _release(ws, args):
    from .learning.release import release

    return release(ws, args.kind, args.version, args.role)


def _removal(ws, args):
    from .evaluation.removal import removal

    return removal(ws, args.answers, args.model, _fg(args))


def _routing(ws, args):
    from .evaluation.routing_check import routing_check

    return routing_check(ws, args.answers, args.model, _fg(args))


def _final(ws, args):
    from .evaluation.final import final_report

    return final_report(ws, args.version, "real", args.model, _fg(args))


def _baseline(ws, args):
    from .evaluation.baseline import command

    return command(ws, args.model)


def _tone(ws, args):
    from .evaluation.tone import tone_report
    return tone_report(ws, args.version, args.model)


def _stability(ws, args):
    from .evaluation.tone import stability_read
    return stability_read(ws, args.model)


def _direct(ws, args):
    from .evaluation.direct_jev import command

    return command(ws, args.model)


def _export(ws, args):
    from .export.make import make_export

    return make_export(ws, args.run_id, args.model)


def _replay(ws, args):
    from .export.make import latest_run
    from .replay.reproduce import reproduce

    return reproduce(ws, args.run_id or latest_run(ws), args.case)


def _lint(ws, args):
    from .evaluation.lint_rules import lint_all

    return lint_all(ws)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="permitengine")
    parser.add_argument("--root", help="the repository folder; by default the one holding this code")
    commands = parser.add_subparsers(dest="command", required=True)

    def add(name, function, **options):
        sub = commands.add_parser(name)
        sub.set_defaults(function=function)
        if options.get("answers"):
            sub.add_argument("--answers", choices=["simulated", "real"], default="simulated")
        if options.get("model"):
            sub.add_argument("--model", help="the LLM model id, which also selects its provider. By default, from settings")
        if options.get("first_guess"):
            sub.add_argument("--first-guess", help="a folder of tree files to take first-guess leaves from, for a temporary check")
        return sub

    add("simulate", _simulate).add_argument("--seed", type=int, default=7)
    add("lint", _lint)
    read = add("read", _read, model=True)
    read.add_argument("--limit", type=int)
    read.add_argument("--split", default="train")
    demo = add("run-demo", _run_demo, answers=True, model=True, first_guess=True)
    demo.add_argument("--run-id", default="demo-1")
    demo.add_argument("--officer", choices=["simulated", "real"], default="simulated")
    for name, function in (("train", _train), ("thresholds", _thresholds), ("report", _report), ("removal", _removal), ("routing-check", _routing)):
        add(name, function, answers=True, model=True, first_guess=True)
    rel = add("release", _release)
    rel.add_argument("--kind", required=True)
    rel.add_argument("--version", required=True)
    rel.add_argument("--role", default="policy_owner")
    final = add("final-report", _final, model=True, first_guess=True)
    final.add_argument("--version", required=True)
    add("baseline", _baseline, model=True)
    add("direct-jev", _direct, model=True)
    tone = add("tone", _tone, model=True)
    tone.add_argument("--version", required=True)
    add("stability", _stability, model=True)
    add("make-export", _export, model=True).add_argument("--run-id")
    replay = add("replay", _replay)
    replay.add_argument("--run-id")
    replay.add_argument("--case")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    ws = Workspace(Path(args.root).resolve()) if args.root else Workspace.default()
    try:
        _print(args.function(ws, args))
    except EngineError as exc:
        print(f"stopped: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
