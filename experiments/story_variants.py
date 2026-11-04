#!/usr/bin/env python3
"""Which way of teaching from an officer gives a curve that reflects learning?

Starts from the real blind first guess, on stored reading records, simulated or real. The feed is the validation split.
Thresholds are chosen on one half of the train split and every number is read on the other half, so nothing here touches the
test split. The officer rules from the labels at a stated accuracy, so this makes no model calls.

  A  corrections only: the network updates only when the officer disagrees with the system (the plan until now)
  B  every review teaches: the officer's outcome and a level for every tree that applies, discount 0.93
  C  every review teaches, with no discount
  D  every review adds a labelled case, and the trees are refitted from the first guess with EM, as in training

Run from the repository root: uv run python experiments/story_variants.py [--answers simulated|real]
"""
import argparse, json, random, statistics as st
from pathlib import Path
from permitengine.workspace import Workspace
from permitengine.pipeline.case import load_context
from permitengine.trees.loader import first_guess
from permitengine.trees.evaluate import distribution, reach
from permitengine.evaluation.common import answers_folder, choose_thresholds, mean_tree_loss, prepare_split, route_counts, rows_by_tree
from permitengine.evaluation.labels import load_labels
from permitengine.evaluation.demo import split_halves, needs_correction, apply_correction
from permitengine.learning.corrections import edge, net_update
from permitengine.learning.train import train_model
from permitengine.risk.score import score

ap = argparse.ArgumentParser()
ap.add_argument('--answers', default='simulated')
ap.add_argument('--accuracy', type=float, default=.9)
ap.add_argument('--seeds', type=int, default=5)
args = ap.parse_args()
ws = Workspace(Path('.').resolve())
ctx = load_context(ws)
labels = load_labels(ws)
splits = ws.splits()
folder = answers_folder(ws, ctx, args.answers, None)
train = prepare_split(ws, ctx, splits['train'], folder)
validation = prepare_split(ws, ctx, splits['validation'], folder)
half_a, half_b = split_halves(splits['train'])
chooser = [train[c] for c in half_a]
held = [train[c] for c in half_b]
strength = ctx.settings.get('training.first_guess_strength'); iters = ctx.settings.get('training.em_iterations')
discount = ctx.settings.get('corrections.discount')

def right_level(model):
    hit = n = 0
    for p in held:
        if p.stopped or p.policy_failure:
            continue
        for t, tree in model.trees.items():
            y = labels[p.case_id]['levels'].get(t)
            if y is None or not p.applies.get(tree.hazard):
                continue
            d = distribution(model.levels[t], reach(tree, p.answers))
            hit += max(range(3), key=lambda j: d[j]) == y; n += 1
    return hit / n

def point(model, thresholds):
    c = route_counts(model, held, thresholds, labels, ctx)
    return dict(loss=mean_tree_loss(model, held, labels), right=right_level(model), auto=c['decided_without_officer'], approved=c['approved_share'], precision=c['precision'], t_low=thresholds['t_low'], t_high=thresholds['t_high'])

def officer(case_id, seed, model, p, a):
    rng = random.Random(f'{seed}:{case_id}')
    lab = labels[case_id]
    outcome = lab['risky'] if rng.random() < a else not lab['risky']
    levels = {}
    for t, tree in model.trees.items():
        y = lab['levels'].get(t)
        if y is None or not p.applies.get(tree.hazard):
            continue
        levels[t] = y if rng.random() < a else rng.choice([j for j in range(3) if j != y])
    return outcome, levels

def run(kind, seed):
    model = first_guess(ctx.trees, strength)
    th = choose_thresholds(model, chooser, labels, ctx)
    out = {0: point(model, th)}; out[0]['corr'] = 0
    corr = 0; seen = {}
    rows_seen = {t: [] for t in ctx.trees}
    reviews = 0
    for case_id in splits['validation']:
        p = validation[case_id]
        if p.stopped or p.policy_failure:
            continue
        reviews += 1
        outcome, levels = officer(case_id, seed, model, p, args.accuracy)
        s = score(model, p.answers, p.applies, ctx.anchors)
        if kind == 'A':
            if needs_correction(s['risk'], th, outcome):
                named = [{'tree_id': t, 'level': y} for t, y in levels.items() if max(range(3), key=lambda j: distribution(model.levels[t], reach(model.trees[t], p.answers))[j]) != y]
                apply_correction(model, p, outcome, named, th, ctx); corr += 1
        elif kind in 'BC':
            c0, k = edge(th['t_low'], th['t_high'])
            net_update(model, p.answers, p.applies, outcome, c0, k, ctx.anchors, levels, discount if kind == 'B' else 1.0); corr += 1
        else:
            for t, y in levels.items():
                rows_seen[t].append((p.answers, y))
            corr += 1
            if reviews % 10 == 0:
                model = train_model(ctx.trees, rows_seen, strength, iters, f'em-{reviews}')
        if reviews % 20 == 0:
            if kind == 'D':
                model = train_model(ctx.trees, rows_seen, strength, iters, f'em-{reviews}')
            th = choose_thresholds(model, chooser, labels, ctx)
            pt = point(model, th); pt['corr'] = corr; out[reviews] = pt
    return out

print(f'answers={args.answers}, officer accuracy {args.accuracy}, mean of {args.seeds} officer seeds, read on {len(held)} held-out cases. All synthetic.')
rows = {t: [] for t in ctx.trees}
full = train_model(ctx.trees, rows_by_tree({c: train[c] for c in half_a}, labels, ctx.trees), strength, iters, 'trained-half')
th = choose_thresholds(full, chooser, labels, ctx)
pt = point(full, th)
print(f"Reference: trained with EM on the other {len(half_a)} labelled train cases: loss {pt['loss']:.3f}, right level {pt['right']:.3f}, decided without officer {pt['auto']:.3f}, approved {pt['approved']:.3f}, precision {pt['precision']:.3f}\n")
for kind, name in (('A', 'corrections only'), ('B', 'every review teaches, discount 0.93'), ('C', 'every review teaches, no discount'), ('D', 'refit with EM from officer labels')):
    runs = [run(kind, s) for s in range(args.seeds if kind != 'x' else 1)]
    print(f'=== {kind}: {name} ===')
    print(f"{'reviews':>8} {'taught':>7} {'loss':>6} {'right level':>12} {'no officer':>11} {'approved':>9} {'precision':>10} {'t_low':>6} {'t_high':>7}")
    keys = sorted(set().union(*runs))
    for r in keys:
        g = lambda k: st.mean(x[r][k] for x in runs if r in x and x[r][k] is not None)
        print(f"{r:>8} {g('corr'):>7.1f} {g('loss'):>6.3f} {g('right'):>12.3f} {g('auto'):>11.3f} {g('approved'):>9.3f} {g('precision'):>10.3f} {g('t_low'):>6.3f} {g('t_high'):>7.3f}")
    print()
