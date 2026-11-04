#!/usr/bin/env python3
"""What would a plot of "the system improving as an officer corrects cases" actually show?

An officer reviews decided cases one at a time and corrects those it believes are wrong, using the chosen Bayesian
network with discount 0.93. An officer at accuracy a reaches the right outcome with probability a, and names trees
with accuracy a. So a below 1 also produces some corrections of decisions that were right.

Stories:
  trained, stable       trees trained on 180 labelled cases, then nothing changes
  trained, change       the same, then the truth for one tree rises one level (planted)
  first guess, stable   no training at all: corrections start from the policy owner's first guess
  retrain from labels   no corrections: an officer labels every tree on N cases, and the trees are retrained from them

Read-outs on 800 held-out cases, at each number of corrections:
  loss          mean over all trees, on the expert labels
  fixed         approved share and precision (share of approvals not labelled risky) with thresholds held at their start
  refit         the same, with thresholds chosen again on 120 validation cases, as a release would do

Mean of 20 seeds. No API calls. Standard library only. Run: python3 sim_demo_curve.py
"""
import random, statistics as st, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import sim_corrections as sc
import sim_corrections_combined as cc
m = sc.m
CHECK = [0, 10, 20, 40, 60, 120]

def read(model, test, val, tl, th):
    o = sc.outcomes(model, test, tl, th)
    rl, rh = m.thresholds([(sc.risk(model, c), c['risky']) for c in val])
    r = sc.outcomes(model, test, rl, rh)
    return (st.mean(sc.tree_loss(model, t, test) for t in sc.TREES), o['auto'], 1 - o['wrong'], r['auto'], 1 - r['wrong'])

def stream(base, counts0, pool, test, val, tl, th, seed, acc):
    model, counts, _ = cc.fresh(base, counts0)
    rng = random.Random(seed + 11)
    c0 = (tl + th) / 2; k = min(4 / max(th - tl, 1e-3), 40)
    out = {0: read(model, test, val, tl, th) + (0,)}
    made = reviewed = 0
    for c in pool:
        if made >= CHECK[-1]:
            break
        R = sc.risk(model, c)
        if tl <= R < th:
            continue
        reviewed += 1
        belief = c['risky'] if rng.random() < acc else not c['risky']
        if not ((R < tl and belief) or (R >= th and not belief)):
            continue
        made += 1
        if acc == 1.0:
            names = {t: c['y'][t] for t in sc.named_trees(model, c)}
        else:
            names = cc.namer(model, c, acc, acc, acc, rng)
        cc.net_update(model, counts, c, belief, c0, k, {t: cc.hard(y) for t, y in names.items()})
        if made in CHECK:
            out[made] = read(model, test, val, tl, th) + (reviewed,)
    return out

def show(title, rows):
    print(f'\n=== {title} ===')
    print(f"{'corrections':>11} {'reviewed':>9} {'loss':>6} {'approved, fixed':>16} {'precision, fixed':>17} {'approved, refit':>16} {'precision, refit':>17}")
    for K in sorted(rows):
        a = rows[K]
        print(f"{K:>11} {st.mean(x[5] for x in a):>9.0f} {st.mean(x[0] for x in a):>6.3f} {st.mean(x[1] for x in a):>16.3f} {st.mean(x[2] for x in a if x[2] == x[2]):>17.3f} {st.mean(x[3] for x in a):>16.3f} {st.mean(x[4] for x in a if x[4] == x[4]):>17.3f}   (seeds {len(a)})")

def main():
    print('All synthetic. Mean of 20 seeds, 800 held-out cases per seed. Precision means the share of automatic approvals not labelled risky.')
    res = {}
    for seed in range(20):
        rng = random.Random(seed)
        sc.DRIFT['on'] = False
        train = sc.sample(rng, 180); val0 = sc.sample(rng, 120)
        pool0 = sc.sample(rng, 1500); test0 = sc.sample(rng, 800)
        base, counts = {}, {}
        for t in sc.TREES:
            base[t], counts[t] = m.fit(t, train)
        first = {t: m.prior(t) for t in sc.TREES}
        fcounts = {t: [[v * m.KAPPA for v in d] for d in first[t]] for t in sc.TREES}
        tl, th = m.thresholds([(sc.risk(base, c), c['risky']) for c in val0])
        fl, fh = m.thresholds([(sc.risk(first, c), c['risky']) for c in val0])
        sc.DRIFT['on'] = True
        val1 = sc.sample(rng, 120); pool1 = sc.sample(rng, 1500); test1 = sc.sample(rng, 800)
        sc.DRIFT['on'] = False
        for acc in (1.0, .9, .7):
            for story, args, drift in (('trained, stable', (base, counts, pool0, test0, val0, tl, th), False),
                                       ('trained, change', (base, counts, pool1, test1, val1, tl, th), True),
                                       ('first guess, stable', (first, fcounts, pool0, test0, val0, fl, fh), False)):
                sc.DRIFT['on'] = drift
                for K, row in stream(*args, seed, acc).items():
                    res.setdefault((story, acc), {}).setdefault(K, []).append(row)
                sc.DRIFT['on'] = False
        for N in CHECK[1:] + [180]:
            model = {t: m.fit(t, pool0[:N])[0] for t in sc.TREES}
            res.setdefault(('retrain from labels', 1.0), {}).setdefault(N, []).append(read(model, test0, val0, fl, fh) + (N,))
        res[('retrain from labels', 1.0)].setdefault(0, []).append(read(first, test0, val0, fl, fh) + (0,))
    for story in ('trained, stable', 'trained, change', 'first guess, stable'):
        for acc in (1.0, .9, .7):
            show(f'{story}; officer {int(acc * 100)}% accurate', res[(story, acc)])
    show('retrain from labels; officer labels every tree on N cases (the first column is N)', res[('retrain from labels', 1.0)])

if __name__ == '__main__':
    main()
