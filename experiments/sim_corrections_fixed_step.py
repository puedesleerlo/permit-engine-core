#!/usr/bin/env python3
"""Stress test of correction methods with fixed settings, with and without a world shift.

sim_corrections.py chose each method's step on post-shift data, and only tested after a shift. The demo plans no shift,
so here settings are fixed in advance, and each method runs in a stable world as well. Also prints what one correction
does to one leaf. Offline, simulated answers, no API calls.
"""
import math, random, statistics as st, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import sim_corrections as sc
m = sc.m

METHODS = [('none', None), ('grad-named', 0.1), ('grad-named', 0.25), ('grad-named', 0.5), ('grad-named', 1.5),
           ('level-named', None), ('bayes-named-forget', 0.93), ('bayes-outcome', None), ('bayes-outcome-forget', 0.93)]

def one(seed, K, shift):
    rng = random.Random(seed)
    sc.DRIFT['on'] = False
    train = sc.sample(rng, 180); val0 = sc.sample(rng, 120)
    base, counts = {}, {}
    for t in sc.TREES:
        base[t], counts[t] = m.fit(t, train)
    tl, th = m.thresholds([(sc.risk(base, c), c['risky']) for c in val0])
    sc.DRIFT['on'] = shift
    pool = sc.sample(rng, 1500); test = sc.sample(rng, 800)
    out = {}
    for name, eta in METHODS:
        mdl, made = sc.run_stream(name, base, counts, pool, K, tl, th, eta)
        o = sc.outcomes(mdl, test, tl, th)
        o['all'] = st.mean(sc.tree_loss(mdl, t, test) for t in sc.TREES)
        o['made'] = made
        out[(name, eta)] = o
    return out

def main():
    print('Trained on 180, thresholds fixed, settings fixed in advance. Mean of 20 seeds, test 800 per seed.')
    for shift in (False, True):
        print(f"\n=== {'After a shift in one tree' if shift else 'Stable world: no shift (what the demo plans)'} ===")
        print(f"{'K':>3} {'method':>21} {'setting':>8} {'made':>6} {'all-tree loss':>14} {'auto':>6} {'risky|auto':>11} {'band':>6}")
        for K in (5, 20, 60):
            rows = [one(s, K, shift) for s in range(20)]
            for key in METHODS:
                g = lambda k: st.mean(x for x in (r[key][k] for r in rows) if x == x)
                print(f"{K:>3} {key[0]:>21} {str(key[1] if key[1] else '-'):>8} {g('made'):>6.1f} {g('all'):>14.3f} {g('auto'):>6.3f} {g('wrong'):>11.3f} {g('band'):>6.3f}")
    print('\n=== One correction on one fully reached leaf: [0.056, 0.858, 0.086], right level is the last ===')
    a = sc.m.S_A
    start = [0.056, 0.858, 0.086]
    print(f"  expected severity before: {sum(p*x for p,x in zip(start,a)):.3f}")
    for eta in (0.1, 0.25, 0.5, 1.5):
        z = [math.log(v) + eta * ((1.0 if i == 2 else 0.0) - start[i]) for i, v in enumerate(start)]
        p = sc.softmax(z)
        print(f"  step {eta:<4}: {[round(v,3) for v in p]}  expected severity {sum(q*x for q,x in zip(p,a)):.3f}")
    n = 46.6
    c = [v*n for v in start]; c[2] += 1
    p = [v/sum(c) for v in c]
    print(f"  soft count, leaf holding {n} cases: {[round(v,3) for v in p]}  expected severity {sum(q*x for q,x in zip(p,a)):.3f}")

if __name__ == '__main__':
    main()
