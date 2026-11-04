#!/usr/bin/env python3
"""Pilot: do the trained trees beat simply asking Jev for each level directly?

All cases are synthetic. Jev gets the case facts and plain definitions of hazards and levels, and never the truth table,
the system's estimates or an officer's finding. It answers one level question per tree that applies.

Trees are compared two ways, because Jev reads true facts in this pilot: reading noisy answers (as the simulations do)
and reading the same true facts Jev sees. This is a pilot, not the final comparison: there are no documents yet.

Run: python3 jev_direct_pilot.py [--limit N]
Results: results/jev_direct_pilot.txt and results/jev_direct_pilot.json (raw answers, no key)
"""
import json, math, random, statistics as st, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import sim_corrections as sc
import jev_names_probe as probe
m = sc.m
sc.DRIFT['on'] = False
N_VAL, N_TEST = 120, 120
TRUE_KINDS = {n: k for t in m.TREES.values() for n, k in t['q']}

def payload(c):
    qs = {}
    for h, (lt, st_) in m.HAZARDS.items():
        if not m.applies(h, c):
            continue
        name = probe.NAMES[h]
        for t, scale, word in ((lt, 'L', 'likelihood'), (st_, 'S', 'severity')):
            qs[f'level__{t}'] = {'type': 'choice', 'instructions': f'Judging from `case_facts`, which {word} level is right for the {name} hazard at this event? {name} means: {probe.HAZARD_TEXT[name]}', 'criteria': probe.LEVELS[scale]}
    return {'model': probe.MODEL, 'state': {'event': 'A street race that needs a city permit.', 'case_facts': probe.facts(c)}, 'questions': qs}

def with_true_inputs(c):
    """The same case, with every question answered from reality, as Jev sees it."""
    d = dict(c)
    d['obs'] = {n: float(c[n]) for n in c['obs']}
    return d

def tree_dists_trees(model, c, extra):
    out = {}
    for t in sc.TREES:
        if m.applies(m.TREES[t]['hazard'], c):
            out[t] = m.pred(m.names_of(t, extra.get(t, ())), model[t], c)
    return out

def tree_dists_jev(c, ans):
    out = {}
    for t in sc.TREES:
        if m.applies(m.TREES[t]['hazard'], c):
            lv = list(probe.LEVELS['L' if t.endswith('.L') else 'S'])
            p = ans[f'level__{t}']['probabilities']
            out[t] = [float(p[x]) for x in lv]
    return out

def risk_from(d, c):
    tot = 0.0
    for h, (lt, st_) in m.HAZARDS.items():
        if m.applies(h, c):
            tot += sum(p * a for p, a in zip(d[lt], m.L_A)) * sum(p * a for p, a in zip(d[st_], m.S_A))
    return tot

def score(rows):
    """rows: list of (case, dists). Per-tree loss and accuracy, plus per-case mean loss for the bootstrap."""
    losses, hits, per_case = [], [], []
    for c, d in rows:
        cl = []
        for t, p in d.items():
            y = c['y'][t]
            l = -math.log(max(p[y], 1e-6))
            losses.append(l); cl.append(l)
            hits.append(max(range(3), key=lambda j: p[j]) == y)
        per_case.append(st.mean(cl))
    return st.mean(losses), st.mean(hits), per_case

def routes(risks, tl, th):
    n = len(risks)
    auto = [k for r, k in risks if r < tl]
    high = [k for r, k in risks if r >= th]
    return dict(auto=len(auto) / n, risky=(sum(auto) / len(auto)) if auto else float('nan'), band=1 - (len(auto) + len(high)) / n, high=len(high) / n, n_auto=len(auto))

def boot(a, b, n=2000, seed=1):
    rng = random.Random(seed)
    diffs = [x - y for x, y in zip(a, b)]
    means = sorted(st.mean(rng.choices(diffs, k=len(diffs))) for _ in range(n))
    return st.mean(diffs), means[int(.025 * n)], means[int(.975 * n)]

def main():
    k = probe.key()
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else None
    rng = random.Random(0)
    train = sc.sample(rng, 180); val = sc.sample(rng, N_VAL); test = sc.sample(rng, N_TEST)
    if limit:
        val, test = val[:limit], test[:limit]
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=4) as ex:
        a_val = list(ex.map(lambda c: probe.call(payload(c), k), val))
        a_test = list(ex.map(lambda c: probe.call(payload(c), k), test))
    usage = [a['usage'] for a in a_val + a_test]
    print(f'requests {len(usage)}; input tokens {sum(u["input_tokens"] for u in usage)}; output tokens {sum(u["output_tokens"] for u in usage)}; returned model {sorted({a["model"] for a in a_val + a_test})}; {time.time() - t0:.0f} s')
    print(f'{N_VAL if not limit else limit} validation and {N_TEST if not limit else limit} test cases, one seed. All cases synthetic. Jev reads true facts in this pilot.\n')

    X = {'traffic.L': ('crossings',)}
    train_true = [with_true_inputs(c) for c in train]
    arms = {}
    first = {t: m.prior(t) for t in sc.TREES}
    noisy = {t: m.fit(t, train)[0] for t in sc.TREES}
    true_ = {t: m.fit(t, train_true)[0] for t in sc.TREES}
    true_x = dict(true_); true_x['traffic.L'] = m.fit('traffic.L', train_true, extra=('crossings',))[0]
    def tv(c): return with_true_inputs(c)
    arms['First guess, noisy inputs'] = ([(c, tree_dists_trees(first, c, {})) for c in val], [(c, tree_dists_trees(first, c, {})) for c in test])
    arms['Trained trees, noisy inputs'] = ([(c, tree_dists_trees(noisy, c, {})) for c in val], [(c, tree_dists_trees(noisy, c, {})) for c in test])
    arms['Trained trees, true inputs'] = ([(c, tree_dists_trees(true_, tv(c), {})) for c in val], [(c, tree_dists_trees(true_, tv(c), {})) for c in test])
    arms['Trained trees + crossings, true inputs'] = ([(c, tree_dists_trees(true_x, tv(c), X)) for c in val], [(c, tree_dists_trees(true_x, tv(c), X)) for c in test])
    arms['Jev asked directly, true inputs'] = ([(c, tree_dists_jev(c, a['answers'])) for c, a in zip(val, a_val)], [(c, tree_dists_jev(c, a['answers'])) for c, a in zip(test, a_test)])

    print(f"{'method':>40} {'loss':>6} {'right level':>12} {'auto':>6} {'risky|auto':>11} {'band':>6} {'high':>6} {'t_low':>6} {'t_high':>7}")
    per = {}
    for name, (rv, rt) in arms.items():
        L, H, pc = score(rt); per[name] = pc
        tl, th = m.thresholds([(risk_from(d, c), c['risky']) for c, d in rv])
        o = routes([(risk_from(d, c), c['risky']) for c, d in rt], tl, th)
        print(f"{name:>40} {L:>6.3f} {H:>12.3f} {o['auto']:>6.3f} {o['risky']:>11.3f} {o['band']:>6.3f} {o['high']:>6.3f} {tl:>6.3f} {th:>7.3f}")
    print('\nDifference in per-case mean loss, Jev minus trees (negative favours Jev), with a 95% bootstrap interval:')
    for name in ('Trained trees, noisy inputs', 'Trained trees, true inputs', 'Trained trees + crossings, true inputs'):
        d, lo, hi = boot(per['Jev asked directly, true inputs'], per[name])
        print(f'  against {name}: {d:+.3f} ({lo:+.3f} to {hi:+.3f})')
    print('\nJev loss per tree, and the same for trees + crossings on true inputs:')
    for t in sc.TREES:
        rows_j = [(c, {t: d[t]}) for c, d in arms['Jev asked directly, true inputs'][1] if t in d]
        rows_x = [(c, {t: d[t]}) for c, d in arms['Trained trees + crossings, true inputs'][1] if t in d]
        print(f'  {t:10s} Jev {score(rows_j)[0]:.3f}, right {score(rows_j)[1]:.3f}; trees {score(rows_x)[0]:.3f}, right {score(rows_x)[1]:.3f}; n={len(rows_j)}')
    if not limit:
        (HERE / 'results' / 'jev_direct_pilot.json').write_text(json.dumps({'model': sorted({a['model'] for a in a_val + a_test}), 'usage': usage,
            'validation': [{'facts': probe.facts(c), 'labels': c['y'], 'risky': c['risky'], 'answers': a['answers']} for c, a in zip(val, a_val)],
            'test': [{'facts': probe.facts(c), 'labels': c['y'], 'risky': c['risky'], 'answers': a['answers']} for c, a in zip(test, a_test)]}, indent=1))

if __name__ == '__main__':
    main()
