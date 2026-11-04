#!/usr/bin/env python3
"""The one Bayesian network: outcome always, plus optional named evidence, from an officer or from Jev.

Part 1 simulates a namer at stated accuracy, over 20 seeds. Part 2 replays the real Jev answers saved in
results/jev_names_probe.json on the same cases, so it makes no API calls. All settings fixed in advance.
"""
import json, random, statistics as st, sys
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import sim_corrections as sc
import jev_names_probe as probe
m = sc.m
GAMMA = 0.93

def net_update(model, counts, c, outcome, c0, k, evidence, gamma=GAMMA):
    """Exact inference: tree levels -> risk -> outcome, with optional evidence on any tree's level. Then add shares."""
    hz = [pair for h, pair in m.HAZARDS.items() if m.applies(h, c)]
    pi = {}
    for pair in hz:
        for t in pair:
            d = sc.dist(model[t], c['r'][t])
            lam = evidence.get(t, [1, 1, 1])
            pi[t] = [a * b for a, b in zip(d, lam)]
    q = {t: [0.0, 0.0, 0.0] for t in pi}
    def walk(i, w, R, chosen):
        if i == len(hz):
            if outcome is None:
                ww = w
            else:
                sig = 1 / (1 + sc.math.exp(-max(min(k * (R - c0), 30), -30)))
                ww = w * (sig if outcome else 1 - sig)
            for t, j in chosen:
                q[t][j] += ww
            return
        lt, st_ = hz[i]
        for a in range(3):
            for b in range(3):
                walk(i + 1, w * pi[lt][a] * pi[st_][b], R + m.L_A[a] * m.S_A[b], chosen + [(lt, a), (st_, b)])
    walk(0, 1.0, 0.0, [])
    for t, row in q.items():
        z = sum(row) or 1e-9
        row = [v / z for v in row]
        r = c['r'][t]; th = model[t]
        sc.forget(counts, t, r, gamma)
        for j in range(3):
            w = [r[l] * th[l][j] for l in range(len(r))]
            zz = sum(w) or 1e-9
            for l, wi in enumerate(w):
                counts[t][l][j] += row[j] * wi / zz
        model[t] = [[v / sum(d) for v in d] for d in counts[t]]

def hard(level):
    return [1.0 if j == level else 0.0 for j in range(3)]

def namer(model, c, sens, spec, lvl, rng):
    wrong = set(sc.named_trees(model, c))
    out = {}
    for t in sc.applicable(c):
        if rng.random() < (sens if t in wrong else 1 - spec):
            out[t] = c['y'][t] if rng.random() < lvl else rng.choice([j for j in range(3) if j != c['y'][t]])
    return out

def fresh(base, counts):
    return {t: [list(d) for d in base[t]] for t in sc.TREES}, {t: [list(d) for d in counts[t]] for t in sc.TREES}, {t: sc.to_logits(base[t]) for t in sc.TREES}

def stream(kind, base, counts0, pool, K, tl, th, seed, sens=1.0, spec=1.0, lvl=1.0, name_rate=1.0, eta=None):
    model, counts, logits = fresh(base, counts0)
    rng = random.Random(seed + 11)
    c0 = (tl + th) / 2; k = min(4 / max(th - tl, 1e-3), 40)
    made = 0
    for c in pool:
        if made >= K:
            break
        R = sc.risk(model, c)
        if not ((R < tl and c['risky']) or (R >= th and not c['risky'])):
            continue
        made += 1
        names = namer(model, c, sens, spec, lvl, rng) if rng.random() < name_rate else {}
        if kind == 'backprop':
            for t, y in names.items():
                sc.grad_level(model, logits, t, c, eta, y=y)
        elif kind == 'named':
            for t, y in names.items():
                net_update(model, counts, c, None, c0, k, {t: hard(y)})
        elif kind == 'outcome':
            net_update(model, counts, c, c['risky'], c0, k, {})
        elif kind == 'both':
            net_update(model, counts, c, c['risky'], c0, k, {t: hard(y) for t, y in names.items()})
    return model

ROWS = [
    ('No correction', 'none', {}),
    ('Backprop, perfect officer, step 0.25', 'backprop', dict(eta=0.25)),
    ('Backprop, perfect officer, step 1.5', 'backprop', dict(eta=1.5)),
    ('Bayesian, perfect officer names only', 'named', {}),
    ('Bayesian, outcome only', 'outcome', {}),
    ('Bayesian, outcome + perfect officer', 'both', {}),
    ('Bayesian, outcome + names half the time', 'both', dict(name_rate=0.5)),
    ('Bayesian, outcome + 90% accurate officer', 'both', dict(sens=.9, spec=.9, lvl=.9)),
    ('Bayesian, outcome + 70% accurate officer', 'both', dict(sens=.7, spec=.7, lvl=.7)),
    ('Backprop 1.5, Jev at measured accuracy', 'backprop', dict(sens=.164, spec=.895, lvl=.104, eta=1.5)),
    ('Bayesian, outcome + Jev at measured accuracy', 'both', dict(sens=.164, spec=.895, lvl=.104)),
]

def part1():
    print('PART 1. Simulated namers, fixed settings (discount 0.93). Mean of 20 seeds, test 800 per seed.')
    for shift in (False, True):
        print(f"\n=== {'After a shift in one tree' if shift else 'Stable world (what the demo plans)'} ===")
        print(f"{'K':>3} {'method':>46} {'all-tree loss':>14} {'shifted tree':>13} {'auto':>6} {'risky|auto':>11}")
        for K in (20, 60):
            acc = {r[0]: [] for r in ROWS}
            for seed in range(20):
                rng = random.Random(seed)
                sc.DRIFT['on'] = False
                train = sc.sample(rng, 180); val0 = sc.sample(rng, 120)
                base, counts = {}, {}
                for t in sc.TREES:
                    base[t], counts[t] = m.fit(t, train)
                tl, th = m.thresholds([(sc.risk(base, c), c['risky']) for c in val0])
                sc.DRIFT['on'] = shift
                pool = sc.sample(rng, 1500); test = sc.sample(rng, 800)
                for name, kind, kw in ROWS:
                    mdl = base if kind == 'none' else stream(kind, base, counts, pool, K, tl, th, seed, **kw)
                    o = sc.outcomes(mdl, test, tl, th)
                    acc[name].append((st.mean(sc.tree_loss(mdl, t, test) for t in sc.TREES), sc.tree_loss(mdl, sc.DRIFT_TREE, test), o['auto'], o['wrong']))
            for name, _, _ in ROWS:
                a = acc[name]
                print(f"{K:>3} {name:>46} {st.mean(x[0] for x in a):>14.3f} {st.mean(x[1] for x in a):>13.3f} {st.mean(x[2] for x in a):>6.3f} {st.mean(x[3] for x in a):>11.3f}")

def level_index(tree, choice):
    return list(probe.LEVELS['L' if tree.endswith('.L') else 'S']).index(choice)

def part2():
    print('\n\nPART 2. Real Jev answers from the probe, replayed with no new calls. One seed. Same fixed list of corrections.')
    saved = json.loads((HERE / 'results' / 'jev_names_probe.json').read_text())
    rng = random.Random(0)
    sc.DRIFT['on'] = False
    train = sc.sample(rng, 180); val0 = sc.sample(rng, 120)
    base, counts0 = {}, {}
    for t in sc.TREES:
        base[t], counts0[t] = m.fit(t, train)
    tl, th = m.thresholds([(sc.risk(base, c), c['risky']) for c in val0])
    stable_pool = sc.sample(rng, 900)
    stable_cases = probe.wrong_cases(base, tl, th, stable_pool, 20)
    sc.DRIFT['on'] = True
    pool = sc.sample(rng, 900); test_shift = sc.sample(rng, 800)
    drift_cases = probe.wrong_cases(base, tl, th, pool, 40)
    sc.DRIFT['on'] = False
    test_stable = sc.sample(random.Random(99), 800)
    assert all(probe.facts(c) == s['facts'] for c, s in zip(drift_cases, saved['drift'])), 'cases do not match the saved probe'
    assert all(probe.facts(c) == s['facts'] for c, s in zip(stable_cases, saved['stable'])), 'cases do not match the saved probe'
    print('Checked: every case matches the saved probe.')
    c0 = (tl + th) / 2; k = min(4 / max(th - tl, 1e-3), 40)

    def jev_names(c, ans):
        return {t: level_index(t, ans[f'level__{t}']['choice']) for t in sc.applicable(c) if ans[f'wrong__{t}']['noul'] >= .5}
    def jev_soft(c, ans, rho=.5):
        out = {}
        for t in sc.applicable(c):
            lv = list(probe.LEVELS['L' if t.endswith('.L') else 'S'])
            p = [ans[f'level__{t}']['probabilities'][x] for x in lv]
            out[t] = [rho * v + (1 - rho) / 3 for v in p]
        return out

    def apply(mode, cases, recs):
        model, counts, logits = fresh(base, counts0)
        for c, rec in zip(cases, recs):
            a = rec['answers']
            if mode == 'none':
                continue
            if mode == 'backprop officer 0.25':
                for t in sc.named_trees(model, c):
                    sc.grad_level(model, logits, t, c, 0.25)
            elif mode == 'backprop officer 1.5':
                for t in sc.named_trees(model, c):
                    sc.grad_level(model, logits, t, c, 1.5)
            elif mode == 'backprop Jev 1.5':
                for t, y in jev_names(c, a).items():
                    sc.grad_level(model, logits, t, c, 1.5, y=y)
            elif mode == 'Bayesian outcome only':
                net_update(model, counts, c, c['risky'], c0, k, {})
            elif mode == 'Bayesian outcome + officer':
                net_update(model, counts, c, c['risky'], c0, k, {t: hard(c['y'][t]) for t in sc.named_trees(model, c)})
            elif mode == 'Bayesian Jev named only':
                for t, y in jev_names(c, a).items():
                    net_update(model, counts, c, None, c0, k, {t: hard(y)})
            elif mode == 'Bayesian outcome + Jev named':
                net_update(model, counts, c, c['risky'], c0, k, {t: hard(y) for t, y in jev_names(c, a).items()})
            elif mode == 'Bayesian outcome + Jev soft, all trees':
                net_update(model, counts, c, c['risky'], c0, k, jev_soft(c, a))
        return model

    MODES = ['none', 'backprop officer 0.25', 'backprop officer 1.5', 'backprop Jev 1.5', 'Bayesian outcome only', 'Bayesian outcome + officer', 'Bayesian Jev named only', 'Bayesian outcome + Jev named', 'Bayesian outcome + Jev soft, all trees']
    for label, cases, recs, test, shifted in (('20 corrections, stable world', stable_cases, saved['stable'], test_stable, False), ('40 corrections, after the shift', drift_cases, saved['drift'], test_shift, True)):
        print(f"\n=== {label} ===")
        print(f"{'method':>42} {'all-tree loss':>14} {'shifted tree':>13} {'auto':>6} {'risky|auto':>11}")
        sc.DRIFT['on'] = shifted
        for mode in MODES:
            mdl = apply(mode, cases, recs)
            o = sc.outcomes(mdl, test, tl, th)
            print(f"{mode:>42} {st.mean(sc.tree_loss(mdl, t, test) for t in sc.TREES):>14.3f} {sc.tree_loss(mdl, sc.DRIFT_TREE, test):>13.3f} {o['auto']:>6.3f} {o['wrong']:>11.3f}")

if __name__ == '__main__':
    part1()
    part2()
